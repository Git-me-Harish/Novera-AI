"""Phase 5 foundations: Cohere embeddings, Gemini thinking, one embedding
text shape, resumable re-embedding and text-anchored evaluation labels."""
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select, text

from app.core.config import settings
from app.services.ai import http as ai_http
from app.services.ai import registry
from app.services.ai.chat import GeminiChat, gemini_thinking_budget
from app.services.ai.embeddings import CohereEmbeddings, build_embedding_client
from app.services.ai.types import ChatMessage, ModelSpec, ProviderError
from app.services.embedding.embedding_service import (
    chunk_embedding_text,
    chunk_embedding_text_for,
    embedding_service,
)
from app.evaluation.anchor_golden import best_quote
from app.evaluation.metrics import evidence_matches, recall_at_k, relevant_ids, relevant_keys
from app.evaluation.schemas import GoldenExample


@pytest.fixture
def transport(monkeypatch):
    calls, state = [], {"responder": None}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        calls.append({"url": str(request.url), "headers": request.headers, "json": body})
        return state["responder"](request, body)

    monkeypatch.setattr(ai_http, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return calls, state


def _cohere_ok(request, body):
    return httpx.Response(200, json={"embeddings": {"float": [[0.5] * 4 for _ in body["texts"]]}})


# ── Cohere embeddings ─────────────────────────────────────────────────────────

async def test_cohere_uses_native_api_with_asymmetric_input_types(transport):
    calls, state = transport
    state["responder"] = _cohere_ok
    client = build_embedding_client(ModelSpec("cohere", "embed-v4.0", "co-key"), dimensions=4)
    assert isinstance(client, CohereEmbeddings)

    await client.embed(["what is the fee?"], task="query")
    await client.embed(["The fee is 1%."], task="document")
    query, document = calls[0], calls[1]
    assert query["url"] == "https://api.cohere.com/v2/embed"  # not the compatibility endpoint
    assert query["headers"]["authorization"] == "Bearer co-key"
    assert query["json"]["input_type"] == "search_query"
    assert document["json"]["input_type"] == "search_document"
    assert query["json"]["output_dimension"] == 4 and query["json"]["embedding_types"] == ["float"]


async def test_cohere_batches_at_96_and_omits_dimension_for_v3(transport):
    calls, state = transport
    state["responder"] = _cohere_ok
    client = CohereEmbeddings(ModelSpec("cohere", "embed-english-v3.0", "k"), dimensions=4, batch_size=96)
    vectors = await client.embed([f"t{i}" for i in range(100)], task="document")
    assert len(vectors) == 100
    assert [len(c["json"]["texts"]) for c in calls] == [96, 4]
    assert "output_dimension" not in calls[0]["json"]  # v3 models are fixed-size


async def test_cohere_wrong_dimension_is_refused(transport):
    _, state = transport
    state["responder"] = lambda r, b: httpx.Response(200, json={"embeddings": {"float": [[0.1] * 3]}})
    with pytest.raises(ProviderError, match="re-embed"):
        await CohereEmbeddings(ModelSpec("cohere", "embed-v4.0", "k"), dimensions=4).embed(["x"], task="query")


# ── Gemini thinking ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("model,setting,expected", [
    ("gemini-2.5-flash", 0, 0),           # thinking off for grounded QA
    ("gemini-2.5-pro", 0, 128),           # Pro cannot turn it off: its minimum
    ("gemini-2.5-flash", 512, 512),
    ("gemini-2.5-flash", -1, None),       # provider default
    ("gemini-2.0-flash", 0, None),        # no thinking budget on older models
])
def test_thinking_budget_per_model(monkeypatch, model, setting, expected):
    monkeypatch.setattr(settings, "llm_thinking_budget", setting)
    assert gemini_thinking_budget(ModelSpec("gemini", model, "k")) == expected


async def test_gemini_reserves_thinking_tokens_and_bills_them(transport, monkeypatch):
    calls, state = transport
    monkeypatch.setattr(settings, "llm_thinking_budget", 0)
    state["responder"] = lambda r, b: httpx.Response(200, json={
        "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "ready"}]}}],
        "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 2, "thoughtsTokenCount": 130},
    })
    result = await GeminiChat(ModelSpec("gemini", "gemini-2.5-pro", "k")).complete(
        [ChatMessage("user", "hi")], max_tokens=100)
    config = calls[0]["json"]["generationConfig"]
    assert config["thinkingConfig"] == {"thinkingBudget": 128}
    assert config["maxOutputTokens"] == 228  # the answer keeps its full 100
    assert result.usage.completion_tokens == 132  # thinking is billed as output


# ── One embedding text shape ──────────────────────────────────────────────────

def test_ingestion_edit_and_reembed_embed_the_same_text():
    row = SimpleNamespace(content="Fee is 1%.", section_title="Pricing", page_numbers=[4, 5], chunk_type="table")
    ingestion = embedding_service.enhance_text_for_embedding(
        "Fee is 1%.", {"document_title": "Rates.pdf", "section": "Pricing", "page": 4, "chunk_type": "table"})
    assert ingestion == chunk_embedding_text_for(row, "Rates.pdf")
    assert ingestion == "Document: Rates.pdf | Section: Pricing | Page: 4 | Type: table\n\nFee is 1%."
    assert chunk_embedding_text("plain") == "plain"


# ── Re-embedding (PostgreSQL) ─────────────────────────────────────────────────

class _FakeEmbedder:
    label = "fake"

    def __init__(self, fail_first: int = 0):
        self.calls = 0
        self.fail_first = fail_first

    async def embed(self, texts, *, task, timeout=60.0):
        self.calls += 1
        if self.calls <= self.fail_first:
            raise ProviderError("busy", provider="fake", status=429, retryable=True, retry_after=0.01)
        assert task == "document"
        return [[0.01] * settings.embedding_dimensions for _ in texts]


@pytest.fixture
async def corpus():
    from app.db.session import AsyncSessionLocal, engine
    from app.models.document import Chunk, Document
    from app.models.organization import Organization

    await engine.dispose()
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1 FROM chunks LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL with migrations not available: {type(exc).__name__}")
    tag = uuid4().hex[:10]
    org = Organization(id=uuid4(), name=f"re-{tag}", slug=f"re-{tag}", display_name="R")
    doc = Document(id=uuid4(), organization_id=org.id, filename="Handbook.pdf", original_filename="Handbook.pdf",
                   file_path="/dev/null", file_size_bytes=1, file_hash=tag, doc_type="policy", status="completed")
    chunks = [
        Chunk(id=uuid4(), document_id=doc.id, content=f"Passage {i}", chunk_index=i, page_numbers=[i + 1],
              embedding=[0.2] * settings.embedding_dimensions, embedding_provider="google",
              embedding_model="models/old", embedding_dimensions=settings.embedding_dimensions)
        for i in range(5)
    ]
    async with AsyncSessionLocal() as db:
        db.add(org)
        await db.flush()
        db.add(doc)
        await db.flush()
        db.add_all(chunks)
        await db.commit()
    yield SimpleNamespace(org=org.id, doc=doc.id)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Organization).where(Organization.id == org.id))
        await db.commit()
    await engine.dispose()


async def test_reembed_moves_stale_chunks_resumably(corpus, monkeypatch):
    from app.cli import reembed as cli
    from app.db.session import AsyncSessionLocal
    from app.models.document import Chunk

    fake = _FakeEmbedder(fail_first=1)  # one 429 first: retried, not lost
    monkeypatch.setattr(registry, "embedding_client", lambda: fake)
    monkeypatch.setattr(type(embedding_service), "configured", property(lambda self: True))

    assert (await cli.reembed(document=corpus.doc, dry_run=True)).candidates == 5
    report = await cli.reembed(document=corpus.doc, batch_size=2)
    assert (report.embedded, report.batches, report.retries) == (5, 3, 1)

    async with AsyncSessionLocal() as db:
        stamps = set((await db.execute(
            select(Chunk.embedding_provider, Chunk.embedding_model).where(Chunk.document_id == corpus.doc)
        )).all())
    assert stamps == {(embedding_service.provider, embedding_service.model_name)}
    # Re-running finds nothing left to do.
    assert (await cli.reembed(document=corpus.doc)).candidates == 0


# ── Text-anchored evaluation labels ───────────────────────────────────────────

def _example(**extra) -> GoldenExample:
    return GoldenExample(id="q1", question="What is the processing fee?", tenant=str(uuid4()),
                         expected_answer="The processing fee is 1% of the loan amount.", **extra)


def test_evidence_survives_rechunking():
    example = _example(evidence=[{"document": "Rates.pdf", "quote": "The processing fee is 1% of the loan amount."}])
    # A different chunking that still contains the passage matches; ids do not matter.
    hit = {"chunk_id": "new-1", "evidence_matches": evidence_matches(
        example, document_id="d", document_name="rates.pdf",
        content="Section 3. Charges. The processing fee is 1% of the loan amount, collected upfront.")}
    other_doc = {"chunk_id": "new-2", "evidence_matches": evidence_matches(
        example, document_id="d2", document_name="Other.pdf",
        content="The processing fee is 1% of the loan amount.")}
    assert relevant_keys(example) == {"evidence:0"}
    assert hit["evidence_matches"] == [0] and other_doc["evidence_matches"] == []
    assert relevant_ids(example, [other_doc, hit]) == {"evidence:0"}
    assert recall_at_k([other_doc, hit], relevant_keys(example), 1) == 0.0
    assert recall_at_k([other_doc, hit], relevant_keys(example), 2) == 1.0


def test_legacy_id_labels_still_work_without_evidence():
    example = _example(relevant_chunk_ids=["c1"])
    assert relevant_ids(example, [{"chunk_id": "c1"}]) == {"c1"}


def test_anchor_quotes_the_sentences_that_state_the_answer():
    content = ("Loans are disbursed weekly at branch meetings. Borrowers must attend. "
               "The processing fee is 1% of the loan amount and is deducted at disbursement. "
               "Branch managers review attendance every month.")
    quote = best_quote(content, ["The processing fee is 1% of the loan amount."])
    assert "processing fee is 1%" in quote and "attendance" not in quote
