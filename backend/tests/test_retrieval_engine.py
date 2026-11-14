"""Retrieval engine: query construction, evidence selection, reranker input,
and SQL behaviour (isolation, weighting, neighbours, savepoints) on PostgreSQL."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text

from app.core.config import settings
from app.services.embedding.embedding_service import embedding_service
from app.services.retrieval.keyword_search import build_tsquery
from app.services.retrieval.pipeline import select_evidence
from app.services.retrieval.reranker import RerankingService


# ── Query construction ───────────────────────────────────────────────────────

def test_tsquery_prefixes_long_words_only_and_is_injection_safe():
    query = build_tsquery("What's the repayment fee for a PF loan in 2024? DROP TABLE x; -- ' | & !")
    terms = query.split(" | ")
    assert "repayment:*" in terms and "loan:*" in terms                  # 4+ letters: prefix
    assert "pf" in terms and "fee" in terms                               # short words exact
    assert "2024" in terms                                                # numbers exact
    assert all(ch.isalnum() or ch in ":*" for term in terms for ch in term)
    assert terms.count("drop:*") == 1                                     # de-duplicated
    assert len(build_tsquery(" ".join(f"w{i}" for i in range(100))).split(" | ")) == 32
    assert build_tsquery("?? !!") == ""


# ── Evidence selection ───────────────────────────────────────────────────────

def _chunk(i, score, tokens=100, content=None, **extra):
    return {"chunk_id": f"c{i}", "rerank_score": score, "token_count": tokens,
            "content": content or f"distinct passage number {i} about topic{i} subject{i}", **extra}


def test_selection_applies_floor_cap_and_budget():
    scored = [_chunk(1, 0.99, 900), _chunk(2, 0.9, 900), _chunk(3, 0.8, 300), _chunk(4, 0.1)]
    picked = select_evidence(scored, query="topic", degraded=False, chunk_cap=10, token_budget=1500)
    # c2 does not fit the budget and is skipped; c3 (smaller) still fits; c4 is below the floor.
    assert [c["chunk_id"] for c in picked] == ["c1", "c3"]
    assert len(select_evidence(scored, query="x", degraded=False, chunk_cap=1, token_budget=10)) == 1  # best kept


def test_selection_drops_near_duplicates():
    text_ = "joint liability group members guarantee each other's weekly repayments at centre meetings"
    scored = [_chunk(1, 0.99, content=text_), _chunk(2, 0.98, content=text_ + " always"), _chunk(3, 0.97)]
    assert [c["chunk_id"] for c in select_evidence(scored, query="q", degraded=False, chunk_cap=5, token_budget=5000)] == ["c1", "c3"]


def test_degraded_selection_needs_similarity_or_top_keyword_rank():
    scored = [
        {**_chunk(1, None), "similarity_score": settings.similarity_threshold + 0.1, "rerank_degraded": True},
        {**_chunk(2, None), "keyword_rank": 2, "keyword_score": 0.01},
        {**_chunk(3, None), "keyword_rank": 9, "keyword_score": 0.5, "similarity_score": 0.01},
    ]
    picked = select_evidence(scored, query="q", degraded=True, chunk_cap=5, token_budget=5000)
    assert [c["chunk_id"] for c in picked] == ["c1", "c2"]  # any keyword hit used to pass


def test_keyword_rescue_is_guarded_and_never_replaces_evidence():
    strong = _chunk(1, 0.99)
    exact = _chunk(9, 0.08, content="Ring leader identification checklist for fraud teams", keyword_rank=1)
    picked = select_evidence([strong, exact], query="How to identify a ring leader in fraud?",
                             degraded=False, chunk_cap=5, token_budget=5000)
    assert [c["chunk_id"] for c in picked] == ["c1", "c9"] and picked[1]["retrieval_rescue"]
    # No cross-encoder signal at all, or poor term coverage: no rescue.
    junk = _chunk(9, 0.0, content="Ring leader identification checklist", keyword_rank=1)
    assert [c["chunk_id"] for c in select_evidence([strong, junk], query="How to identify a ring leader?",
                                                   degraded=False, chunk_cap=5, token_budget=5000)] == ["c1"]
    off_topic = _chunk(9, 0.3, content="Branch opening hours and holidays", keyword_rank=1)
    assert len(select_evidence([strong, off_topic], query="How to identify a ring leader?",
                               degraded=False, chunk_cap=5, token_budget=5000)) == 2  # 0.3 passes the floor itself


def test_reranker_reads_document_title_and_section():
    text_ = RerankingService._document_text({
        "document_name": "Module_5_Products_Pricing.pdf", "section_title": "Fees › Processing",
        "content": "The fee is 1%.",
    })
    assert text_ == "Document: Module 5 Products Pricing | Section: Fees › Processing\nThe fee is 1%."


# ── SQL behaviour (PostgreSQL) ───────────────────────────────────────────────

def _vec(axis: int, weight: float = 1.0):
    v = [0.0] * settings.embedding_dimensions
    v[axis] = weight
    v[(axis + 1) % len(v)] = 1.0 - weight
    return v


@pytest.fixture
async def corpus():
    from app.db.session import AsyncSessionLocal, engine
    from app.models.document import Chunk, Document
    from app.models.organization import Organization

    await engine.dispose()
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT search_vector FROM chunks LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL with migrations not available: {type(exc).__name__}")

    tag = uuid4().hex[:10]
    orgs = [Organization(id=uuid4(), name=f"rt-{tag}-{i}", slug=f"rt-{tag}-{i}", display_name="R") for i in range(2)]
    docs = [Document(id=uuid4(), organization_id=org.id, filename=f"Manual-{i}.pdf", original_filename="m.pdf",
                     file_path="/dev/null", file_size_bytes=1, file_hash=f"{tag}{i}", doc_type="policy", status="completed")
            for i, org in enumerate(orgs)]
    stamp = dict(embedding_provider=embedding_service.provider, embedding_model=embedding_service.model_name,
                 embedding_dimensions=embedding_service.dimensions)
    chunks = [
        # Tenant 0, document 0: index 0-1 share a section; index 2 is another section.
        Chunk(id=uuid4(), document_id=docs[0].id, chunk_index=0, section_title="Repayment schedule",
              content="Borrowers repay in weekly instalments.", embedding=_vec(0), **stamp),
        Chunk(id=uuid4(), document_id=docs[0].id, chunk_index=1, section_title="Repayment schedule",
              content="Late instalments are followed up within two days.", embedding=_vec(0, 0.9), **stamp),
        Chunk(id=uuid4(), document_id=docs[0].id, chunk_index=2, section_title="Office hours",
              content="Branches open at nine and the repayment desk closes at five.", embedding=_vec(5), **stamp),
        # Same tenant, vector from another embedding model: never compared.
        Chunk(id=uuid4(), document_id=docs[0].id, chunk_index=3, section_title="Old",
              content="Old vector.", embedding=_vec(0), embedding_provider="google",
              embedding_model="models/old", embedding_dimensions=settings.embedding_dimensions),
        # Another tenant with an identical vector: never visible.
        Chunk(id=uuid4(), document_id=docs[1].id, chunk_index=0, section_title="Repayment schedule",
              content="Other tenant repayment secret.", embedding=_vec(0), **stamp),
    ]
    async with AsyncSessionLocal() as db:
        db.add_all(orgs)
        await db.flush()
        db.add_all(docs)
        await db.flush()
        db.add_all(chunks)
        await db.commit()
    yield SimpleNamespace(org=orgs[0].id, other_org=orgs[1].id, chunks=chunks, doc=docs[0].id)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Organization).where(Organization.id.in_([o.id for o in orgs])))
        await db.commit()
    await engine.dispose()


async def test_vector_search_is_tenant_and_model_isolated(corpus):
    from app.db.session import AsyncSessionLocal
    from app.services.retrieval.vector_search import vector_search_service

    async with AsyncSessionLocal() as db:
        hits = await vector_search_service.search_similar_chunks(_vec(0), db, corpus.org, top_k=10)
    contents = [h["content"] for h in hits]
    assert contents[0] == "Borrowers repay in weekly instalments."
    assert "Other tenant repayment secret." not in contents and "Old vector." not in contents
    assert [h["similarity_score"] for h in hits] == sorted((h["similarity_score"] for h in hits), reverse=True)


async def test_keyword_search_weights_section_titles_and_isolates_tenants(corpus):
    from app.db.session import AsyncSessionLocal
    from app.services.retrieval.keyword_search import keyword_search_service

    async with AsyncSessionLocal() as db:
        hits = await keyword_search_service.search_keywords("repayment", db, corpus.org, top_k=10)
    contents = [h["content"] for h in hits]
    # "repayment" is in the section title of the first two (weight A) and only
    # in the body of the third (weight B).
    assert set(contents[:2]) == {"Borrowers repay in weekly instalments.", "Late instalments are followed up within two days."}
    assert contents[2].startswith("Branches open")
    assert "Other tenant repayment secret." not in contents


async def test_neighbours_are_batched_and_stay_in_section(corpus):
    from app.db.session import AsyncSessionLocal
    from app.services.retrieval.vector_search import vector_search_service

    first, second = str(corpus.chunks[0].id), str(corpus.chunks[1].id)
    async with AsyncSessionLocal() as db:
        neighbours = await vector_search_service.get_neighbors_batch([first, second], db, corpus.org)
    assert [n["chunk_id"] for n in neighbours[first]] == [second]
    # chunk 1's other neighbour (index 2) is a different section.
    assert [n["chunk_id"] for n in neighbours[second]] == [first]
    async with AsyncSessionLocal() as db:
        assert await vector_search_service.get_neighbors_batch([first], db, corpus.other_org) == {}


async def test_failed_search_does_not_roll_back_the_request(corpus):
    """Searches used to call session.rollback() on error, discarding anything
    the request had already written in that transaction."""
    from app.db.session import AsyncSessionLocal
    from app.models.document import Chunk
    from app.services.retrieval.vector_search import vector_search_service

    async with AsyncSessionLocal() as db:
        await db.execute(text("UPDATE chunks SET title = 'kept' WHERE id = :id"), {"id": corpus.chunks[2].id})
        assert await vector_search_service.search_similar_chunks([0.1, 0.2], db, corpus.org) == []  # wrong size
        await db.commit()
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(Chunk.title).where(Chunk.id == corpus.chunks[2].id))).scalar_one() == "kept"


async def test_hybrid_survives_embedding_outage_with_keyword_results(corpus, monkeypatch):
    from app.db.session import AsyncSessionLocal
    from app.services.retrieval.hybrid_search import hybrid_search_service

    async def down(_query):
        raise RuntimeError("provider down")

    monkeypatch.setattr(embedding_service, "embed_query", down)
    async with AsyncSessionLocal() as db:
        hits = await hybrid_search_service.search_with_context_expansion(
            query="weekly repayment", db=db, organization_id=corpus.org, top_k=5)
    assert hits and all("keyword" in h.get("retrieval_method", []) or h.get("is_expanded_context") for h in hits)
