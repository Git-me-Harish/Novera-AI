"""Document editor API: tenant guard and metadata updates."""
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.api.dependencies.auth import get_current_admin_user
from app.api.endpoints import document_editor
from app.db.session import get_db
from app.main import app
from app.models.tenancy import AuditEvent

ORG_ID = uuid4()


class FakeSession:
    """Answers every select with one preset row and records adds/commits."""

    def __init__(self, row):
        self.row = row
        self.added = []
        self.commits = 0

    async def execute(self, statement):
        return SimpleNamespace(scalar_one_or_none=lambda: self.row)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


async def test_chunk_guard_runs_and_fails_closed():
    """Regression: the guard referenced names that were never imported, so every
    chunk edit, revert, delete and history call failed with a server error."""
    user = SimpleNamespace(organization_id=ORG_ID)
    await document_editor._assert_chunk_access(uuid4(), FakeSession(uuid4()), user)

    with pytest.raises(HTTPException) as missing:
        await document_editor._assert_chunk_access(uuid4(), FakeSession(None), user)
    assert missing.value.status_code == 404

    with pytest.raises(HTTPException) as orphan:
        await document_editor._assert_chunk_access(uuid4(), FakeSession(uuid4()), SimpleNamespace(organization_id=None))
    assert orphan.value.status_code == 403


@pytest.fixture
def api(monkeypatch):
    document = SimpleNamespace(
        id=uuid4(), organization_id=ORG_ID, filename="handbook.pdf",
        original_filename="handbook.pdf", doc_type="policy", department="People",
    )
    session = FakeSession(document)
    admin = SimpleNamespace(id=uuid4(), email="admin@example.test", role="admin", organization_id=ORG_ID)

    async def fake_db():
        yield session

    async def fake_info(document_id, db, organization_id):
        return {
            "id": str(document.id), "filename": document.filename, "original_filename": document.original_filename,
            "file_size_mb": 1.0, "doc_type": document.doc_type, "department": document.department,
            "total_pages": 3, "total_chunks": 9, "has_tables": False, "has_images": False,
            "status": "completed", "upload_date": "2026-01-01T00:00:00", "processed_date": None,
            "mime_type": "application/pdf",
        }

    monkeypatch.setattr(document_editor.document_viewer_service, "get_document_info", fake_info)
    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_admin_user] = lambda: admin
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    yield client, document, session
    app.dependency_overrides.clear()


async def test_rename_keeps_extension_and_is_audited(api):
    client, document, session = api
    response = await client.patch(f"/api/v1/documents/{document.id}",
                                  json={"filename": "  Employee handbook ", "doc_type": " Handbook "})
    assert response.status_code == 200, response.text
    assert document.filename == "Employee handbook.pdf"
    assert document.original_filename == "handbook.pdf"  # downloads keep the uploaded name
    assert document.doc_type == "handbook"
    assert document.department == "People"  # omitted -> unchanged
    assert response.json()["filename"] == "Employee handbook.pdf"

    events = [e for e in session.added if isinstance(e, AuditEvent)]
    assert len(events) == 1 and events[0].action == "document.updated"
    assert events[0].details["filename"] == {"from": "handbook.pdf", "to": "Employee handbook.pdf"}
    assert session.commits == 1


async def test_department_can_be_cleared_and_no_op_writes_nothing(api):
    client, document, session = api
    response = await client.patch(f"/api/v1/documents/{document.id}", json={"department": "  "})
    assert response.status_code == 200
    assert document.department is None

    session.added.clear()
    session.commits = 0
    response = await client.patch(f"/api/v1/documents/{document.id}", json={"doc_type": "policy"})
    assert response.status_code == 200
    assert session.added == [] and session.commits == 0


@pytest.mark.parametrize("payload", [{"filename": "../etc/passwd"}, {"filename": "   "}, {"doc_type": ""}])
async def test_invalid_metadata_is_rejected(api, payload):
    client, document, _ = api
    response = await client.patch(f"/api/v1/documents/{document.id}", json=payload)
    # Custom-validator errors used to crash the 422 handler into a 500.
    assert response.status_code == 422
    body = response.json()
    field = next(iter(payload))
    assert body["detail"].startswith(f"{field}: ") and body["errors"][0]["field"] == field
    assert "passwd" not in response.text  # the submitted value is never echoed
    assert document.filename == "handbook.pdf"


async def test_other_organizations_document_is_not_found(api):
    client, document, session = api
    session.row = None  # the org-scoped select finds nothing
    response = await client.patch(f"/api/v1/documents/{document.id}", json={"doc_type": "x"})
    assert response.status_code == 404
