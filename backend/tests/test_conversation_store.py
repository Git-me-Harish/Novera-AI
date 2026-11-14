"""Integration tests for durable chat history against real PostgreSQL.

Keyset pagination, full-text search, DISTINCT ON previews and row-lock
sequencing are SQL behaviour, so these run against the database. Each test
gets its own organizations and users, removed by cascade afterwards. Skipped
when the database is unreachable.
"""
import asyncio
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, text, update

from app.db.session import AsyncSessionLocal, engine
from app.models.conversation import Conversation
from app.models.organization import Organization
from app.models.user import User
from app.services.generation.conversation_manager import (
    HIGHLIGHT_END,
    HIGHLIGHT_START,
    ConversationStore,
    clean_title,
    title_from_question,
)

store = ConversationStore()


@pytest.fixture
async def tenants():
    # The shared engine pool is bound to the loop that created it; each test
    # runs in its own loop, so start from a fresh pool.
    await engine.dispose()
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1 FROM conversations LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL with migrations not available: {type(exc).__name__}")

    tag = uuid4().hex[:10]
    orgs = [Organization(id=uuid4(), name=f"t-{tag}-{i}", slug=f"t-{tag}-{i}", display_name="T")
            for i in range(2)]
    users = [
        User(id=uuid4(), email=f"a-{tag}@example.invalid", username=f"a-{tag}",
             hashed_password="x", organization_id=orgs[0].id),
        User(id=uuid4(), email=f"b-{tag}@example.invalid", username=f"b-{tag}",
             hashed_password="x", organization_id=orgs[0].id),
        User(id=uuid4(), email=f"c-{tag}@example.invalid", username=f"c-{tag}",
             hashed_password="x", organization_id=orgs[1].id),
    ]
    async with AsyncSessionLocal() as db:
        db.add_all(orgs)
        await db.flush()
        db.add_all(users)
        await db.commit()
    yield SimpleNamespace(org=orgs[0].id, other_org=orgs[1].id, alice=users[0].id,
                          bob=users[1].id, carol=users[2].id)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.id.in_([u.id for u in users])))
        await db.execute(delete(Organization).where(Organization.id.in_([o.id for o in orgs])))
        await db.commit()
    await engine.dispose()


async def _conversation(t, user=None, org=None, question="What is the leave policy?", messages=()):
    async with AsyncSessionLocal() as db:
        conv = await store.create(db, organization_id=org or t.org, user_id=user or t.alice,
                                  first_question=question)
        for role, content in messages:
            await store.append_message(db, conv, role, content)
        return conv


def test_titles_are_clean_and_bounded():
    assert title_from_question("  what   is the PF rate? ") == "What is the PF rate?"
    long = title_from_question("word " * 40)
    assert long.endswith("…") and len(long) <= 61
    assert clean_title('Title: "Leave Policy Overview."\nextra') == "Leave Policy Overview"
    assert clean_title("  \n  ") is None


async def test_messages_are_durable_ordered_and_counted(tenants):
    t = tenants
    conv = await _conversation(t, messages=[("user", "q1"), ("assistant", "a1"),
                                            ("user", "q2"), ("assistant", "a2")])
    async with AsyncSessionLocal() as db:
        fresh = await store.get_owned(db, conv.id, organization_id=t.org, user_id=t.alice)
        assert fresh.message_count == 4 and fresh.title == "What is the leave policy?"
        messages, has_more = await store.messages(db, fresh)
        assert [m.sequence for m in messages] == [1, 2, 3, 4] and not has_more
        # Prompt history: last N turns, oldest first.
        assert await store.recent_history(db, fresh, 1) == [
            {"role": "user", "content": "q2"}, {"role": "assistant", "content": "a2"}]
        page, has_more = await store.messages(db, fresh, limit=2, before_sequence=4)
        assert [m.sequence for m in page] == [2, 3] and has_more


async def test_concurrent_appends_get_unique_gap_free_sequences(tenants):
    t = tenants
    conv = await _conversation(t)

    async def append(i):
        async with AsyncSessionLocal() as db:
            await store.append_message(db, conv, "user", f"message {i}")

    await asyncio.gather(*(append(i) for i in range(12)))
    async with AsyncSessionLocal() as db:
        fresh = await store.get_owned(db, conv.id, organization_id=t.org, user_id=t.alice)
        messages, _ = await store.messages(db, fresh)
    assert sorted(m.sequence for m in messages) == list(range(1, 13))
    assert fresh.message_count == 12


async def test_conversations_are_invisible_across_users_and_tenants(tenants):
    t = tenants
    conv = await _conversation(t, messages=[("user", "secret salary question")])
    async with AsyncSessionLocal() as db:
        assert await store.get_owned(db, conv.id, organization_id=t.org, user_id=t.bob) is None
        assert await store.get_owned(db, conv.id, organization_id=t.other_org, user_id=t.alice) is None
        assert await store.exists_for_other_owner(db, conv.id)
        for org, user in ((t.org, t.bob), (t.other_org, t.carol)):
            items, _ = await store.list(db, organization_id=org, user_id=user, q="salary")
            assert items == []
        # Bulk delete ignores ids the caller does not own.
        assert await store.soft_delete(db, organization_id=t.org, user_id=t.bob,
                                       conversation_ids=[conv.id]) == 0


async def test_list_pins_first_and_paginates_every_item_exactly_once(tenants):
    t = tenants
    created = [await _conversation(t, question=f"question {i}", messages=[("user", f"q{i}")])
               for i in range(7)]
    async with AsyncSessionLocal() as db:
        pinned = await store.get_owned(db, created[0].id, organization_id=t.org, user_id=t.alice)
        await store.set_pinned(db, pinned, True)

        seen, cursor = [], None
        while True:
            items, cursor = await store.list(db, organization_id=t.org, user_id=t.alice,
                                             limit=3, cursor=cursor)
            seen.extend(items)
            if not cursor:
                break
    assert len(seen) == 7 and len({i["id"] for i in seen}) == 7
    assert seen[0]["id"] == str(created[0].id) and seen[0]["is_pinned"]
    unpinned = [i["last_message_at"] for i in seen[1:]]
    assert unpinned == sorted(unpinned, reverse=True)
    assert seen[1]["preview"] == "q6"


async def test_search_matches_titles_and_message_text_with_snippets(tenants):
    t = tenants
    await _conversation(t, question="Travel reimbursement", messages=[("user", "hello")])
    by_body = await _conversation(t, question="Misc", messages=[
        ("user", "How many days of maternity leave are allowed?"),
        ("assistant", "Maternity leave is 26 weeks [1]."),
    ])
    await _conversation(t, question="Unrelated", messages=[("user", "office hours")])
    async with AsyncSessionLocal() as db:
        items, _ = await store.list(db, organization_id=t.org, user_id=t.alice, q="reimburs")
        assert [i["title"] for i in items] == ["Travel reimbursement"]
        items, _ = await store.list(db, organization_id=t.org, user_id=t.alice, q="matern lea")
        assert [i["id"] for i in items] == [str(by_body.id)]
        snippet = items[0]["snippet"]
        assert HIGHLIGHT_START in snippet and HIGHLIGHT_END in snippet
        # LIKE wildcards in the query are literal, not patterns.
        items, _ = await store.list(db, organization_id=t.org, user_id=t.alice, q="%")
        assert items == []


async def test_user_title_is_never_overwritten_by_auto_title(tenants):
    t = tenants
    renamed = await _conversation(t)
    untouched = await _conversation(t)
    async with AsyncSessionLocal() as db:
        conv = await store.get_owned(db, renamed.id, organization_id=t.org, user_id=t.alice)
        await store.rename(db, conv, "  My leave notes ")
        assert not await store.apply_auto_title(db, renamed.id, "Generated title")
        assert await store.apply_auto_title(db, untouched.id, '"Leave Policy."')
        rows = {c.id: c for c in (await db.execute(
            Conversation.__table__.select().where(Conversation.id.in_([renamed.id, untouched.id]))
        )).all()}
    assert (rows[renamed.id].title, rows[renamed.id].title_source) == ("My leave notes", "user")
    assert (rows[untouched.id].title, rows[untouched.id].title_source) == ("Leave Policy", "auto")


async def test_archive_unpins_and_moves_out_of_the_main_list(tenants):
    t = tenants
    conv = await _conversation(t)
    async with AsyncSessionLocal() as db:
        c = await store.get_owned(db, conv.id, organization_id=t.org, user_id=t.alice)
        await store.set_pinned(db, c, True)
        await store.set_archived(db, c, True)
        assert not c.is_pinned
        main, _ = await store.list(db, organization_id=t.org, user_id=t.alice)
        archived, _ = await store.list(db, organization_id=t.org, user_id=t.alice, archived=True)
    assert str(conv.id) not in {i["id"] for i in main}
    assert [i["id"] for i in archived] == [str(conv.id)]


async def test_soft_delete_restore_and_retention_purge(tenants):
    t = tenants
    keep = await _conversation(t, messages=[("user", "keep me")])
    expired = await _conversation(t, messages=[("user", "old")])
    async with AsyncSessionLocal() as db:
        await store.set_pinned(db, await store.get_owned(
            db, keep.id, organization_id=t.org, user_id=t.alice), True)
        assert await store.soft_delete(db, organization_id=t.org, user_id=t.alice,
                                       conversation_ids=[keep.id, expired.id]) == 2
        assert await store.get_owned(db, keep.id, organization_id=t.org, user_id=t.alice) is None
        trash, _ = await store.list(db, organization_id=t.org, user_id=t.alice, deleted=True)
        assert {i["id"] for i in trash} == {str(keep.id), str(expired.id)}

        restored = await store.get_owned(db, keep.id, organization_id=t.org, user_id=t.alice,
                                         include_deleted=True)
        assert (await store.owner_stats(db, organization_id=t.org, user_id=t.alice))["pinned"] == 0
        await store.restore(db, restored)
        assert restored.is_pinned, "undo must bring back a pinned conversation still pinned"

        await db.execute(update(Conversation).where(Conversation.id == expired.id)
                         .values(deleted_at=Conversation.deleted_at - timedelta(days=31)))
        await db.commit()
        assert await store.purge_deleted(db, older_than=timedelta(days=30)) >= 1
        assert await store.get_owned(db, keep.id, organization_id=t.org, user_id=t.alice)
        assert not await store.exists_for_other_owner(db, expired.id)
        stats = await store.owner_stats(db, organization_id=t.org, user_id=t.alice)
    assert stats["total"] == 1 and stats["deleted"] == 0 and stats["messages"] == 1


# ── HTTP API ─────────────────────────────────────────────────────────────────

@pytest.fixture
async def client(tenants):
    from app.api.dependencies.auth import get_current_user
    from app.main import app

    principal = {"user": SimpleNamespace(id=tenants.alice, organization_id=tenants.org)}
    app.dependency_overrides[get_current_user] = lambda: principal["user"]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c, principal
    app.dependency_overrides.clear()


async def test_api_rename_pin_search_delete_restore(tenants, client):
    http, _ = client
    conv = await _conversation(tenants, messages=[("user", "Explain the gratuity formula"),
                                                  ("assistant", "Gratuity is 15/26 of salary [1].")])
    base = f"/api/v1/chat/conversations/{conv.id}"

    assert (await http.patch(base, json={"title": "Gratuity"})).json()["title_source"] == "user"
    assert (await http.patch(base, json={"is_pinned": True})).json()["is_pinned"]
    assert (await http.patch(base, json={})).status_code == 422

    listing = (await http.get("/api/v1/chat/conversations", params={"q": "gratuity"})).json()
    assert listing["items"][0]["id"] == str(conv.id)
    detail = (await http.get(base)).json()
    assert [m["sequence"] for m in detail["messages"]] == [1, 2]

    # Permanent delete is only allowed as a second step after a soft delete.
    assert (await http.delete(f"{base}/permanent")).status_code == 409
    deleted = (await http.delete(base)).json()
    assert deleted["restorable_until"]
    assert (await http.get(base)).status_code == 404
    trash = (await http.get("/api/v1/chat/conversations", params={"deleted": True})).json()
    assert [i["id"] for i in trash["items"]] == [str(conv.id)]
    assert (await http.post(f"{base}/restore")).json()["deleted_at"] is None
    assert (await http.get(base)).status_code == 200

    await http.delete(base)
    assert (await http.delete(f"{base}/permanent")).status_code == 200
    assert (await http.post(f"{base}/restore")).status_code == 404


async def test_api_hides_other_users_conversations(tenants, client):
    http, principal = client
    conv = await _conversation(tenants)
    principal["user"] = SimpleNamespace(id=tenants.bob, organization_id=tenants.org)
    base = f"/api/v1/chat/conversations/{conv.id}"
    for response in (await http.get(base), await http.patch(base, json={"title": "x"}),
                     await http.delete(base), await http.get(f"{base}/export")):
        assert response.status_code == 404
    bulk = await http.post("/api/v1/chat/conversations/bulk-delete", json={"ids": [str(conv.id)]})
    assert bulk.json()["deleted"] == 0


async def test_selective_export_picks_messages_by_sequence(tenants, client):
    """A client showing only the newest page must still export what it ticked:
    sequences are stable where list positions are not."""
    http, _ = client
    conv = await _conversation(tenants, messages=[("user", "first question"), ("assistant", "first answer"),
                                                  ("user", "second question"), ("assistant", "second answer")])
    url = f"/api/v1/chat/conversations/{conv.id}/export-selected"

    body = (await http.post(url, json={"message_sequences": [3, 4], "format": "json"})).json()
    assert [m["content"] for m in body["messages"]] == ["second question", "second answer"]
    assert body["metadata"]["exported_sequences"] == [3, 4]

    legacy = (await http.post(url, json={"message_indices": [0], "format": "json"})).json()
    assert [m["content"] for m in legacy["messages"]] == ["first question"]

    assert (await http.post(url, json={"message_sequences": [99], "format": "json"})).status_code == 400


# ── chat pipeline → durable store ────────────────────────────────────────────

@pytest.fixture
def stubbed_pipeline(monkeypatch):
    """Real chat_service and store; retrieval and the model are stubbed."""
    from app.services.generation import chat_service as chat_module
    from app.services.generation import conversation_titles

    seen_histories = []

    async def fake_retrieve(**kwargs):
        source = {"document": "policy.pdf", "page": 3, "section": None, "chunk_id": "c-1"}
        return {"context_text": "[1] [Document: policy.pdf]\n" + "Leave is 24 days a year. " * 4,
                "sources": [source], "chunks": [{"chunk_id": "c-1"}], "retrieval_metadata": {}}

    async def fake_generate(**kwargs):
        seen_histories.append(kwargs["conversation_history"])
        return {"answer": "Employees get 24 days of leave [1].", "citations": [
            {"document": "policy.pdf", "page": 3, "chunk_id": "c-1", "citation_number": 1}],
            "confidence": "medium", "finish_reason": "stop", "cache_hit": False,
            "usage": {"prompt_tokens": 50, "completion_tokens": 9, "total_tokens": 59,
                      "cached_tokens": 0}, "model": "test:model"}

    titled = []
    monkeypatch.setattr(chat_module.retrieval_pipeline, "retrieve", fake_retrieve)
    monkeypatch.setattr(chat_module.llm_service, "generate_answer", fake_generate)
    monkeypatch.setattr(chat_module, "schedule_title", lambda *a: titled.append(a))
    monkeypatch.setattr(conversation_titles.settings, "conversation_auto_title", True)
    return SimpleNamespace(module=chat_module, histories=seen_histories, titled=titled)


async def test_chat_turns_persist_without_duplicating_the_question(tenants, stubbed_pipeline):
    t, chat = tenants, stubbed_pipeline.module.chat_service
    async with AsyncSessionLocal() as db:
        first = await chat.chat(query="How much annual leave do I get?", conversation_id=None,
                                user_id=str(t.alice), organization_id=t.org, db=db,
                                use_semantic_cache=False)
        second = await chat.chat(query="And for part-time staff?", conversation_id=first["conversation_id"],
                                 user_id=str(t.alice), organization_id=t.org, db=db,
                                 use_semantic_cache=False)
    assert first["conversation_id"] == second["conversation_id"]
    # First turn has no history; the second sees only the PREVIOUS turn.
    assert stubbed_pipeline.histories[0] == []
    assert stubbed_pipeline.histories[1] == [
        {"role": "user", "content": "How much annual leave do I get?"},
        {"role": "assistant", "content": "Employees get 24 days of leave [1]."},
    ]
    assert len(stubbed_pipeline.titled) == 1, "auto-title once, after the first real answer"

    async with AsyncSessionLocal() as db:
        conv = await store.get_owned(db, first["conversation_id"], organization_id=t.org, user_id=t.alice)
        messages, _ = await store.messages(db, conv)
    assert [m.role for m in messages] == ["user", "assistant", "user", "assistant"]
    meta = messages[1].message_metadata
    assert meta["citations"][0]["chunk_id"] == "c-1" and meta["model"] == "test:model"
    assert conv.title == "How much annual leave do I get?" and conv.context


async def test_streamed_answers_persist_the_same_metadata(tenants, stubbed_pipeline):
    t, chat = tenants, stubbed_pipeline.module.chat_service
    async with AsyncSessionLocal() as db:
        stream = await chat.chat(query="How much annual leave do I get?", conversation_id=None,
                                 user_id=str(t.alice), organization_id=t.org, db=db, stream=True)
        events = [event async for event in stream]
    conversation_id = events[0]["conversation_id"]
    assert [e["type"] for e in events] == ["metadata", "content", "done"]
    async with AsyncSessionLocal() as db:
        conv = await store.get_owned(db, conversation_id, organization_id=t.org, user_id=t.alice)
        messages, _ = await store.messages(db, conv)
    assert messages[1].message_metadata["citations"], "stream path used to drop citations"
    assert messages[1].message_metadata["tokens"]["total_tokens"] == 59


async def test_evaluation_store_writes_nothing(tenants, stubbed_pipeline):
    from app.services.generation.conversation_manager import InMemoryConversationStore

    t, chat = tenants, stubbed_pipeline.module.chat_service
    async with AsyncSessionLocal() as db:
        result = await chat.chat(query="How much annual leave do I get?", conversation_id=None,
                                 user_id=str(t.alice), organization_id=t.org, db=db,
                                 use_semantic_cache=False, store=InMemoryConversationStore())
        assert result["answer"]
        stats = await store.owner_stats(db, organization_id=t.org, user_id=t.alice)
    assert stats["total"] == 0 and not stubbed_pipeline.titled


async def test_background_title_uses_tenant_chain_and_respects_renames(tenants, monkeypatch):
    from app.services.ai.types import ChatResult
    from app.services.generation import conversation_titles
    from app.services.generation.llm_service import llm_service

    chains = []

    async def fake_chain(db, organization_id):
        chains.append(organization_id)
        return "tenant-chain"

    async def fake_complete(prompt, *, chain, **kwargs):
        assert chain == "tenant-chain", "titles must use the tenant's own model"
        return ChatResult('"Annual Leave Entitlement."', "m", "p")

    import app.services.ai.registry as registry
    monkeypatch.setattr(registry, "chat_chain_for", fake_chain)
    monkeypatch.setattr(llm_service, "complete", fake_complete)

    auto = await _conversation(tenants)
    await conversation_titles.generate_title(tenants.org, auto.id, "How much leave?")
    async with AsyncSessionLocal() as db:
        conv = await store.get_owned(db, auto.id, organization_id=tenants.org, user_id=tenants.alice)
    assert (conv.title, conv.title_source) == ("Annual Leave Entitlement", "auto")
    assert chains == [tenants.org]
