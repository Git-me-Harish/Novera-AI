"""Phase 3 multi-tenancy: roles, lifecycle, quotas, invitations, audit, limits.

Runs against real PostgreSQL with real JWTs and the real auth dependencies,
so authorization is exercised exactly as in production. Each test provisions
its own organizations and users and removes them afterwards.
"""
import asyncio
import io
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select, text, update

from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal, engine
from app.models.document import Document
from app.models.organization import Organization
from app.models.tenancy import AuditEvent, OrganizationInvitation
from app.models.user import RefreshToken, User

API = "/api/v1"
PASSWORD = "Tenant-Test-Passw0rd!"


async def _make_user(org_id, role="user", tag=None, active=True):
    tag = tag or uuid4().hex[:10]
    user = User(id=uuid4(), email=f"{role}-{tag}@example.com", username=f"{role}-{tag}",
                hashed_password=get_password_hash(PASSWORD), organization_id=org_id,
                role=role, is_active=active, is_verified=True)
    async with AsyncSessionLocal() as db:
        db.add(user)
        await db.commit()
    return user


def _token(user) -> dict:
    from app.core.security import create_access_token

    token = create_access_token(data={"sub": str(user.id), "email": user.email, "role": user.role,
                                      "organization_id": str(user.organization_id) if user.organization_id else None})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def world():
    await engine.dispose()
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1 FROM audit_events LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL with migrations not available: {type(exc).__name__}")
    tag = uuid4().hex[:8]
    orgs = [Organization(id=uuid4(), name=f"tn-{tag}-{i}", slug=f"tn-{tag}-{i}", display_name=f"Org {i}")
            for i in range(2)]
    async with AsyncSessionLocal() as db:
        db.add_all(orgs)
        await db.commit()
    w = SimpleNamespace(org=orgs[0], other=orgs[1])
    w.admin = await _make_user(orgs[0].id, "org_admin")
    w.member = await _make_user(orgs[0].id, "user")
    w.other_admin = await _make_user(orgs[1].id, "org_admin")
    w.root = await _make_user(None, "super_admin")
    yield w
    async with AsyncSessionLocal() as db:
        ids = [o.id for o in orgs]
        users = select(User.id).where((User.organization_id.in_(ids)) | (User.id == w.root.id))
        await db.execute(delete(RefreshToken).where(RefreshToken.user_id.in_(users)))
        await db.execute(delete(AuditEvent).where(AuditEvent.actor_user_id.in_(users)))
        await db.execute(delete(OrganizationInvitation).where(OrganizationInvitation.organization_id.in_(ids)))
        await db.execute(delete(Document).where(Document.organization_id.in_(ids)))
        await db.execute(delete(User).where((User.organization_id.in_(ids)) | (User.id == w.root.id)))
        await db.execute(delete(Organization).where(Organization.id.in_(ids)))
        await db.commit()
    await engine.dispose()


@pytest.fixture
async def http(world):
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        yield client


async def _role(user_id):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(User.role).where(User.id == user_id))).scalar_one()


# ── privilege escalation ─────────────────────────────────────────────────────

@pytest.mark.parametrize("role", ["super_admin", "org_admin"])
async def test_org_admin_cannot_escalate_anyone(world, http, role):
    for target in (world.admin, world.member):
        if target.role == role:
            continue  # a no-op is not an escalation
        response = await http.put(f"{API}/admin/users/{target.id}", headers=_token(world.admin),
                                  json={"role": role})
        assert response.status_code == 403, response.text
        assert await _role(target.id) == target.role


async def test_org_admin_cannot_touch_another_organization(world, http):
    # 404, not 403: another tenant's user ids must not be confirmable.
    target = f"{API}/admin/users/{world.other_admin.id}"
    for response in (await http.put(target, headers=_token(world.admin), json={"is_active": False}),
                     await http.get(target, headers=_token(world.admin)),
                     await http.delete(target, headers=_token(world.admin)),
                     await http.post(f"{target}/reset-password", headers=_token(world.admin),
                                     json={"new_password": "Takeover-Passw0rd!"})):
        assert response.status_code == 404, response.text
    async with AsyncSessionLocal() as db:
        other = (await db.execute(select(User).where(User.id == world.other_admin.id))).scalar_one()
    assert other.is_active


async def test_org_admin_cannot_take_over_a_super_admin(world, http):
    # The reset endpoint had no scoping at all: any org admin could set a
    # super admin's password.
    response = await http.post(f"{API}/admin/users/{world.root.id}/reset-password",
                               headers=_token(world.admin), json={"new_password": "Takeover-Passw0rd!"})
    assert response.status_code == 404


async def test_admin_cannot_demote_or_deactivate_the_last_admin(world, http):
    root = _token(world.root)
    demote = await http.put(f"{API}/admin/users/{world.admin.id}", headers=root, json={"role": "user"})
    assert demote.status_code == 403 and "at least one active admin" in demote.text
    deactivate = await http.put(f"{API}/admin/users/{world.admin.id}", headers=root, json={"is_active": False})
    assert deactivate.status_code == 403


async def test_deleting_a_user_keeps_the_documents_they_uploaded(world, http):
    async with AsyncSessionLocal() as db:
        doc = Document(id=uuid4(), filename="kept.pdf", original_filename="kept.pdf", file_path="/nonexistent",
                       file_size_bytes=10, file_hash=uuid4().hex, doc_type="policy", status="completed",
                       uploaded_by=world.member.id, organization_id=world.org.id)
        db.add(doc)
        await db.commit()
    response = await http.delete(f"{API}/admin/users/{world.member.id}", headers=_token(world.admin))
    assert response.status_code == 200
    async with AsyncSessionLocal() as db:
        kept = (await db.execute(select(Document).where(Document.id == doc.id))).scalar_one_or_none()
    assert kept is not None and kept.uploaded_by is None


# ── helpers for the rest of the suite ────────────────────────────────────────

async def _set_org(org_id, **values):
    async with AsyncSessionLocal() as db:
        await db.execute(update(Organization).where(Organization.id == org_id).values(**values))
        await db.commit()


async def _audit(org_id, action):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(AuditEvent).where(
            AuditEvent.organization_id == org_id, AuditEvent.action == action
        ))).scalars().all()


@pytest.fixture
def no_queue(monkeypatch):
    """Uploads normally hand off to the Redis worker queue; not under test here."""
    from app.services.document_processing.job_queue import document_job_queue

    async def enqueue(*args, **kwargs):
        return "test"

    monkeypatch.setattr(document_job_queue, "enqueue", enqueue)


async def _upload(http, user, name, size=200):
    content = (name.encode() * (size // max(len(name), 1) + 1))[:size]
    return await http.post(f"{API}/documents/upload", headers=_token(user), params={"doc_type": "policy"},
                           files={"file": (name, io.BytesIO(content), "text/plain")})


# ── registration ─────────────────────────────────────────────────────────────

async def test_signup_never_joins_an_existing_tenant(world, http, monkeypatch):
    from app.core import config

    body = {"email": f"stranger-{uuid4().hex[:6]}@example.com", "username": f"stranger{uuid4().hex[:6]}",
            "password": PASSWORD}
    for mode in ("invite_only", "disabled"):
        monkeypatch.setattr(config.settings, "registration_mode", mode)
        assert (await http.post(f"{API}/auth/register", json=body)).status_code == 403

    monkeypatch.setattr(config.settings, "registration_mode", "self_serve")
    response = await http.post(f"{API}/auth/register", json={**body, "organization_name": "Acme Labs"})
    assert response.status_code == 201, response.text
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == body["email"]))).scalar_one()
        org = (await db.execute(select(Organization).where(Organization.id == user.organization_id))).scalar_one()
        assert user.role == "org_admin" and org.display_name == "Acme Labs"
        assert org.id not in (world.org.id, world.other.id)
        orgs_before = len((await db.execute(select(Organization.id))).all())
    # A failed sign-up (duplicate email) must not leave an empty org behind.
    assert (await http.post(f"{API}/auth/register", json=body)).status_code == 400
    async with AsyncSessionLocal() as db:
        assert len((await db.execute(select(Organization.id))).all()) == orgs_before
        await db.execute(delete(AuditEvent).where(AuditEvent.organization_id == org.id))
        await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))
        await db.execute(delete(User).where(User.id == user.id))
        await db.execute(delete(Organization).where(Organization.id == org.id))
        await db.commit()


# ── invitations ──────────────────────────────────────────────────────────────

async def test_invitation_lifecycle(world, http):
    email = f"invitee-{uuid4().hex[:6]}@example.com"
    created = await http.post(f"{API}/organization/invitations", headers=_token(world.admin),
                              json={"email": email, "role": "admin"})
    assert created.status_code == 201, created.text
    token = created.json()["invite_url"].split("token=")[1]
    async with AsyncSessionLocal() as db:
        stored = (await db.execute(select(OrganizationInvitation.token_hash)
                                   .where(OrganizationInvitation.email == email))).scalar_one()
    assert token not in stored, "only the hash may be stored"

    duplicate = await http.post(f"{API}/organization/invitations", headers=_token(world.admin), json={"email": email})
    assert duplicate.status_code == 409

    preview = (await http.get(f"{API}/auth/invitations/{token}")).json()
    assert preview["organization"] == world.org.display_name and preview["role"] == "admin"

    accepted = await http.post(f"{API}/auth/invitations/accept",
                               json={"token": token, "username": f"inv{uuid4().hex[:6]}", "password": PASSWORD})
    assert accepted.status_code == 201, accepted.text
    async with AsyncSessionLocal() as db:
        joined = (await db.execute(select(User).where(User.email == email))).scalar_one()
    assert (joined.organization_id, joined.role, joined.is_verified) == (world.org.id, "admin", True)

    reuse = await http.post(f"{API}/auth/invitations/accept",
                            json={"token": token, "username": f"inv{uuid4().hex[:6]}", "password": PASSWORD})
    assert reuse.status_code == 400, "an invitation is single use"
    assert await _audit(world.org.id, "invitation.accepted")


async def test_invitation_rules(world, http):
    # Org admins cannot hand out org_admin; existing accounts cannot be invited.
    escalate = await http.post(f"{API}/organization/invitations", headers=_token(world.admin),
                               json={"email": f"x-{uuid4().hex[:6]}@example.com", "role": "org_admin"})
    assert escalate.status_code == 403
    existing = await http.post(f"{API}/organization/invitations", headers=_token(world.admin),
                               json={"email": world.other_admin.email})
    assert existing.status_code == 409
    member = await http.post(f"{API}/organization/invitations", headers=_token(world.member),
                             json={"email": f"x-{uuid4().hex[:6]}@example.com"})
    assert member.status_code == 403

    created = (await http.post(f"{API}/organization/invitations", headers=_token(world.admin),
                               json={"email": f"rev-{uuid4().hex[:6]}@example.com"})).json()
    token = created["invite_url"].split("token=")[1]
    # Another org's admin cannot see or revoke it.
    assert (await http.delete(f"{API}/organization/invitations/{created['id']}",
                              headers=_token(world.other_admin))).status_code == 404
    assert (await http.delete(f"{API}/organization/invitations/{created['id']}",
                              headers=_token(world.admin))).json()["status"] == "revoked"
    assert (await http.get(f"{API}/auth/invitations/{token}")).status_code == 404


async def test_expired_invitation_cannot_be_used(world, http):
    from datetime import datetime, timedelta, timezone

    created = (await http.post(f"{API}/organization/invitations", headers=_token(world.admin),
                               json={"email": f"exp-{uuid4().hex[:6]}@example.com"})).json()
    token = created["invite_url"].split("token=")[1]
    async with AsyncSessionLocal() as db:
        await db.execute(update(OrganizationInvitation).where(OrganizationInvitation.id == created["id"])
                         .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
        await db.commit()
    response = await http.post(f"{API}/auth/invitations/accept",
                               json={"token": token, "username": f"exp{uuid4().hex[:6]}", "password": PASSWORD})
    assert response.status_code == 400


# ── lifecycle ────────────────────────────────────────────────────────────────

async def test_suspension_locks_out_existing_sessions_and_logins(world, http):
    member_headers = _token(world.member)
    assert (await http.get(f"{API}/chat/conversations", headers=member_headers)).status_code == 200
    login = await http.post(f"{API}/auth/login", json={"email": world.member.email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    refresh_token = login.json()["refresh_token"]

    suspended = await http.post(f"{API}/super-admin/organizations/{world.org.id}/suspend",
                                headers=_token(world.root), json={"reason": "Unpaid invoice"})
    assert suspended.status_code == 200, suspended.text

    locked = await http.get(f"{API}/chat/conversations", headers=member_headers)
    assert locked.status_code == 403 and locked.json()["code"] == "organization_suspended"
    assert (await http.post(f"{API}/auth/login",
                            json={"email": world.member.email, "password": PASSWORD})).status_code == 401
    assert (await http.post(f"{API}/auth/refresh", json={"refresh_token": refresh_token})).status_code == 401
    # Other tenants and super admins are unaffected.
    assert (await http.get(f"{API}/chat/conversations", headers=_token(world.other_admin))).status_code == 200

    await http.post(f"{API}/super-admin/organizations/{world.org.id}/reactivate", headers=_token(world.root))
    assert (await http.get(f"{API}/chat/conversations", headers=member_headers)).status_code == 200
    assert await _audit(world.org.id, "organization.suspended")
    assert await _audit(world.org.id, "organization.reactivated")


async def test_org_admins_cannot_suspend_or_change_limits(world, http):
    assert (await http.post(f"{API}/super-admin/organizations/{world.org.id}/suspend", headers=_token(world.admin),
                            json={"reason": "nope"})).status_code == 403
    assert (await http.put(f"{API}/super-admin/organizations/{world.org.id}/limits", headers=_token(world.admin),
                           json={"api_per_minute": 1})).status_code == 403


async def test_settings_update_cannot_wipe_ai_settings_and_limits_can_be_cleared(world, http):
    await _set_org(world.org.id, settings={"ai": {"temperature": 0.1}}, max_users=50)
    root = _token(world.root)
    protected = await http.put(f"{API}/super-admin/organizations/{world.org.id}", headers=root,
                               json={"settings": {"ai": {}}})
    assert protected.status_code == 400
    merged = await http.put(f"{API}/super-admin/organizations/{world.org.id}", headers=root,
                            json={"settings": {"theme": "dark"}, "max_users": None})
    assert merged.status_code == 200, merged.text
    async with AsyncSessionLocal() as db:
        org = (await db.execute(select(Organization).where(Organization.id == world.org.id))).scalar_one()
    assert org.settings == {"ai": {"temperature": 0.1}, "theme": "dark"} and org.max_users is None


async def test_permanent_delete_requires_suspension_and_removes_files(world, http, tmp_path):
    victim = Organization(id=uuid4(), name=f"del-{uuid4().hex[:6]}", slug=f"del-{uuid4().hex[:6]}",
                          display_name="Del")
    async with AsyncSessionLocal() as db:
        db.add(victim)
        await db.commit()
    owner = await _make_user(victim.id, "org_admin")
    stored = tmp_path / "upload.pdf"
    stored.write_bytes(b"%PDF-1.4 customer data")
    async with AsyncSessionLocal() as db:
        db.add(Document(id=uuid4(), filename="c.pdf", original_filename="c.pdf", file_path=str(stored),
                        file_size_bytes=22, file_hash=uuid4().hex, doc_type="policy", status="completed",
                        uploaded_by=owner.id, organization_id=victim.id))
        await db.commit()
    root = _token(world.root)
    url = f"{API}/super-admin/organizations/{victim.id}"
    assert (await http.request("DELETE", url, headers=root, json={"confirm_name": victim.name})).status_code == 409
    await http.post(f"{url}/suspend", headers=root, json={"reason": "Contract ended"})
    assert (await http.request("DELETE", url, headers=root, json={"confirm_name": "wrong"})).status_code == 409
    done = await http.request("DELETE", url, headers=root, json={"confirm_name": victim.name})
    assert done.status_code == 200, done.text
    assert done.json()["removed"] == {"users": 1, "documents": 1, "files_removed": 1}
    assert not stored.exists(), "customer files must be removed, not orphaned"
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(User).where(User.id == owner.id))).scalar_one_or_none() is None
        platform_event = (await db.execute(select(AuditEvent).where(
            AuditEvent.action == "organization.deleted", AuditEvent.target_id == str(victim.id)
        ))).scalar_one()
        assert platform_event.organization_id is None
        await db.execute(delete(AuditEvent).where(AuditEvent.id == platform_event.id))
        await db.commit()


# ── quotas ───────────────────────────────────────────────────────────────────

async def test_document_quota_and_concurrent_uploads(world, http, no_queue):
    await _set_org(world.org.id, max_documents=1)
    first, second = await asyncio.gather(_upload(http, world.admin, "alpha.txt"),
                                         _upload(http, world.admin, "bravo.txt"))
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 403], (first.text, second.text)
    denied = first if first.status_code == 403 else second
    assert denied.json()["code"] == "quota_exceeded"
    assert denied.json()["resource"] == "documents"
    async with AsyncSessionLocal() as db:
        count = len((await db.execute(select(Document.id).where(Document.organization_id == world.org.id))).all())
    assert count == 1, "the row lock must stop two uploads from both taking the last slot"
    assert await _audit(world.org.id, "quota.exceeded")
    assert await _audit(world.org.id, "document.uploaded")


async def test_storage_quota(world, http, no_queue):
    await _set_org(world.org.id, max_storage_gb=1)
    async with AsyncSessionLocal() as db:
        db.add(Document(id=uuid4(), filename="big.pdf", original_filename="big.pdf", file_path="/nonexistent",
                        file_size_bytes=1024 ** 3 - 100, file_hash=uuid4().hex, doc_type="policy",
                        status="completed", organization_id=world.org.id))
        await db.commit()
    response = await _upload(http, world.admin, "over.txt", size=500)
    assert response.status_code == 403 and response.json()["resource"] == "storage"
    usage = (await http.get(f"{API}/organization/usage", headers=_token(world.admin))).json()
    assert usage["quotas"]["storage_bytes"]["remaining"] == 100


async def test_seat_quota_covers_creation_and_invitations(world, http):
    await _set_org(world.org.id, max_users=2)  # admin + member already active
    create = await http.post(f"{API}/admin/users", headers=_token(world.admin),
                             json={"email": f"s-{uuid4().hex[:6]}@example.com", "username": f"s{uuid4().hex[:6]}",
                                   "password": PASSWORD, "role": "user", "is_active": True})
    assert create.status_code == 403 and create.json()["resource"] == "users"
    invite = await http.post(f"{API}/organization/invitations", headers=_token(world.admin),
                             json={"email": f"s-{uuid4().hex[:6]}@example.com"})
    assert invite.status_code == 403


# ── audit log ────────────────────────────────────────────────────────────────

async def test_audit_log_is_tenant_scoped_and_append_only(world, http):
    # Plain members cannot read the audit log (checked before the promotion below).
    assert (await http.get(f"{API}/organization/audit-log", headers=_token(world.member))).status_code == 403
    await http.put(f"{API}/admin/users/{world.member.id}", headers=_token(world.admin), json={"role": "admin"})
    await http.put(f"{API}/admin/users/{world.other_admin.id}", headers=_token(world.root),
                   json={"full_name": "Other"})
    own = (await http.get(f"{API}/organization/audit-log", headers=_token(world.admin))).json()["items"]
    assert own and all(e["organization_id"] == str(world.org.id) for e in own)
    change = next(e for e in own if e["action"] == "user.role_changed")
    assert change["details"] == {"from": "user", "to": "admin"} and change["actor_email"] == world.admin.email

    assert (await http.get(f"{API}/organization/audit-log", headers=_token(world.admin),
                           params={"organization_id": str(world.other.id)})).status_code == 403
    assert (await http.get(f"{API}/organization/audit-log", headers=_token(world.admin),
                           params={"all_organizations": True})).status_code == 403
    every = (await http.get(f"{API}/organization/audit-log", headers=_token(world.root),
                            params={"all_organizations": True, "action": "user."})).json()["items"]
    assert {str(world.org.id), str(world.other.id)} <= {e["organization_id"] for e in every}

    async with AsyncSessionLocal() as db:
        with pytest.raises(Exception, match="append-only"):
            await db.execute(update(AuditEvent).where(AuditEvent.organization_id == world.org.id)
                             .values(action="tampered"))
            await db.commit()


async def test_failed_logins_are_audited_without_secrets(world, http):
    await http.post(f"{API}/auth/login", json={"email": world.member.email, "password": "Wrong-Passw0rd!"})
    async with AsyncSessionLocal() as db:
        event = (await db.execute(select(AuditEvent).where(
            AuditEvent.action == "auth.login_failed",
            AuditEvent.details["email"].astext == world.member.email,
        ))).scalars().first()
        assert event is not None and "Wrong-Passw0rd!" not in str(event.details)
        await db.execute(delete(AuditEvent).where(AuditEvent.id == event.id))
        await db.commit()


# ── rate limits ──────────────────────────────────────────────────────────────

async def test_per_organization_rate_limit_is_isolated(world, http):
    from app.services.tenancy import limits

    response = await http.put(f"{API}/super-admin/organizations/{world.org.id}/limits", headers=_token(world.root),
                              json={"api_per_minute": 3})
    assert response.json()["effective"]["api_per_minute"] == 3
    limits.invalidate(world.org.id)
    codes = [(await http.get(f"{API}/organization/usage", headers=_token(u))).status_code
             for u in (world.admin, world.admin, world.admin)]
    assert codes == [200, 200, 200], codes
    # A different user in the same organization shares the organization bucket.
    blocked = await http.get(f"{API}/chat/conversations", headers=_token(world.member))
    assert blocked.status_code == 429 and blocked.json()["scope"] == "organization"
    # The other tenant's bucket is untouched.
    assert (await http.get(f"{API}/organization/usage", headers=_token(world.other_admin))).status_code == 200


def test_forwarded_for_is_ignored_without_trusted_proxies(monkeypatch):
    from starlette.requests import Request

    from app.core import config
    from app.core.net import client_ip

    scope = {"type": "http", "headers": [(b"x-forwarded-for", b"1.2.3.4, 10.0.0.9")], "client": ("10.0.0.9", 1)}
    monkeypatch.setattr(config.settings, "trusted_proxy_hops", 0)
    assert client_ip(Request(scope)) == "10.0.0.9", "a client must not choose its own IP"
    scope["headers"] = [(b"x-forwarded-for", b"6.6.6.6, 1.2.3.4")]
    monkeypatch.setattr(config.settings, "trusted_proxy_hops", 1)
    assert client_ip(Request(scope)) == "1.2.3.4", "only the hop appended by our proxy is trusted"


async def test_batch_upload_keeps_going_after_a_quota_denial(world, http, no_queue):
    # A rollback after one denied file used to expire the user object and
    # break every remaining file in the batch.
    await _set_org(world.org.id, max_documents=1)
    files = [("files", (f"batch-{i}.txt", io.BytesIO(f"batch document {i} ".encode() * 20), "text/plain"))
             for i in range(3)]
    response = await http.post(f"{API}/documents/upload-multiple", headers=_token(world.admin),
                               params={"doc_type": "policy"}, files=files)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["succeeded"], body["failed"]) == (1, 2), body
    assert {r["error"] for r in body["results"] if r["status"] == "failed"} == {"quota_exceeded"}
