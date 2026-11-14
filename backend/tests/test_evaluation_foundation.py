import json

import pytest

from app.evaluation.metrics import citation_metrics, faithfulness, ndcg_at_k
from app.evaluation.runner import build_report, load_jsonl
from app.evaluation.schemas import GoldenExample
from app.evaluation.live_runner import _safe_retrieved_chunk
from app.services.embedding.embedding_service import EmbeddingService
from app.services.generation.semantic_cache import SemanticCache
from app.core.rag_trace import RAGTrace, hash_value


def test_retrieval_metrics_are_deterministic():
    example = GoldenExample(
        id="q1",
        tenant="t1",
        question="What is the policy?",
        expected_answer="The policy is approved.",
        relevant_chunk_ids=["good"],
    )
    predictions = {
        "q1": {
            "retrieved": [
                {"chunk_id": "wrong", "content": "unrelated"},
                {"chunk_id": "good", "content": "The policy is approved."},
            ],
            "answer": "The policy is approved. [2]",
            "latency_ms": 42,
        }
    }
    report = build_report([example], predictions, "dataset.jsonl")
    assert report.metrics["recall_at_5"] == 1.0
    assert report.metrics["mrr"] == 0.5
    assert report.metrics["answer_token_f1"] > 0.8
    assert report.metrics["citation_recall"] == 1.0
    assert report.metrics["p95_latency_ms"] == 42


def test_invalid_citations_are_not_counted_as_supported():
    precision, recall, citations = citation_metrics("Answer [4]", 2, True)
    assert citations == [4]
    assert precision == 0.0
    assert recall == 0.0
    assert faithfulness("Answer [4]", "Answer", True, source_count=2) == 0.0


def test_document_level_relevance_does_not_overcount_duplicate_chunks():
    example = GoldenExample(
        id="q2",
        tenant="t1",
        question="Question",
        expected_answer="Answer",
        relevant_document_ids=["doc-1"],
    )
    report = build_report(
        [example],
        {
            "q2": {
                "retrieved": [
                    {"chunk_id": "c1", "document_id": "doc-1", "content": "evidence"},
                    {"chunk_id": "c2", "document_id": "doc-1", "content": "evidence"},
                ],
                "answer": "",
            }
        },
        "dataset.jsonl",
    )
    assert report.metrics["recall_at_5"] == 1.0
    assert report.metrics["ndcg_at_5"] == 1.0


def test_live_prediction_redacts_content_by_default():
    chunk = {"chunk_id": "c1", "document_id": "d1", "content": "salary: confidential"}
    safe = _safe_retrieved_chunk(chunk, include_content=False)
    assert "content" not in safe
    assert safe["content_sha256"]
    assert _safe_retrieved_chunk(chunk, include_content=True)["content"] == chunk["content"]


def test_missing_or_failed_predictions_cannot_pass_the_gate():
    examples = [
        GoldenExample(
            id="q1",
            tenant="t1",
            question="Question",
            expected_answer="Answer",
            relevant_chunk_ids=["c1"],
        ),
        GoldenExample(
            id="q2",
            tenant="t1",
            question="Question 2",
            expected_answer="Answer 2",
            relevant_chunk_ids=["c2"],
        ),
    ]
    report = build_report(
        examples,
        {"q1": {"error": "timeout", "answer": ""}},
        "dataset.jsonl",
    )
    assert report.passed is False
    assert report.metrics["error_rate"] == 1.0
    assert any("missing prediction: q2" in failure for failure in report.failures)
    assert any("prediction error=timeout" in failure for failure in report.failures)


def test_report_enforces_maximum_latency_threshold():
    example = GoldenExample(
        id="latency",
        tenant="t1",
        question="Question",
        expected_answer="Answer",
        relevant_chunk_ids=["c1"],
    )
    report = build_report(
        [example],
        {
            "latency": {
                "retrieved": [{"chunk_id": "c1"}],
                "answer": "Answer",
                "latency_ms": 2500,
            }
        },
        "dataset.jsonl",
        thresholds={"max_p95_latency_ms": 2000},
    )
    assert report.passed is False
    assert any("p95_latency_ms" in failure for failure in report.failures)


def test_context_precision_counts_evidence_items_not_duplicate_parent_ids():
    example = GoldenExample(
        id="precision",
        tenant="00000000-0000-0000-0000-000000000001",
        question="What is the policy?",
        expected_answer="The policy is documented.",
        relevant_chunk_ids=["chunk-1"],
        relevant_document_ids=["doc-1"],
        must_cite=False,
    )
    predictions = {
        "precision": {
            "retrieved": [
                {"chunk_id": "chunk-1", "document_id": "doc-1", "content": "policy"},
                {"chunk_id": "chunk-2", "document_id": "doc-2", "content": "other"},
            ],
            "answer": "The policy is documented.",
        }
    }
    report = build_report([example], predictions, "dataset.jsonl")
    assert report.metrics["context_precision"] == 0.5


def test_semantic_cache_scope_isolated_by_filters():
    cache = SemanticCache()
    assert cache.scope_key("finance", "treasury") != cache.scope_key("hr", "treasury")
    assert cache.scope_key(None, None) != cache.scope_key("finance", None)


@pytest.mark.asyncio
async def test_embedding_provider_failure_fails_closed_without_local_fallback(monkeypatch):
    from app.services.ai import registry
    from app.services.ai.types import ProviderError

    class FailingClient:
        async def embed(self, texts, *, task, timeout=None):
            raise ProviderError("provider unavailable", provider="test", retryable=True)

    monkeypatch.setattr(registry, "embedding_client", lambda: FailingClient())
    service = EmbeddingService()
    with pytest.raises(RuntimeError, match="mixing embedding spaces"):
        await service.embed_query("confidential query")
    assert service.use_local_fallback is False


async def test_embedding_dimension_mismatch_is_rejected():
    from app.services.ai.embeddings import EmbeddingClient
    from app.services.ai.types import ModelSpec, ProviderError

    class ShortVectors(EmbeddingClient):
        async def _embed_batch(self, texts, *, task, timeout):
            return [[0.1] * 768 for _ in texts]

    client = ShortVectors(ModelSpec("openai", "m"), dimensions=1536)
    with pytest.raises(ProviderError, match="requires 1536-d"):
        await client.embed(["text"], task="document")


def test_rag_trace_contains_hashes_and_safe_metrics_only():
    trace = RAGTrace(request_id="req-1")
    trace.set_principal(tenant_id="tenant-1", user_id="user-1")
    trace.set_query("What is the confidential salary policy?")
    started = trace.stage_start("retrieval")
    trace.stage_end("retrieval", started, retrieved=5, strategy="hybrid")
    trace.event("unsafe", query="raw secret text", content="document body")
    payload = trace.to_dict()
    assert payload["query_hash"] == hash_value("What is the confidential salary policy?")
    assert payload["stages"]["retrieval"]["retrieved"] == 5
    assert "query" not in payload["events"][0]
    assert "content" not in payload["events"][0]


def test_report_includes_reranker_lift_and_cache_hit_rate():
    example = GoldenExample(
        id="q3",
        tenant="t1",
        question="Question",
        expected_answer="Answer",
        relevant_chunk_ids=["good"],
    )
    report = build_report(
        [example],
        {
            "q3": {
                "pre_rerank_retrieved": [{"chunk_id": "wrong"}],
                "retrieved": [{"chunk_id": "good", "content": "Answer"}],
                "answer": "Answer [1]",
                "cache_hit": True,
            }
        },
        "dataset.jsonl",
    )
    assert report.metrics["reranker_lift"] == 1.0
    assert report.metrics["cache_hit_rate"] == 1.0


def test_report_persists_runtime_configuration():
    example = GoldenExample(
        id="q4",
        tenant="t1",
        question="Question",
        expected_answer="Answer",
        relevant_chunk_ids=["c1"],
    )
    report = build_report(
        [example],
        {"q4": {"retrieved": [{"chunk_id": "c1", "content": "Answer"}], "answer": "Answer [1]"}},
        "dataset.jsonl",
        configuration={"embedding_model": "models/test", "chunk_size": 600},
    )
    assert report.configuration["embedding_model"] == "models/test"
    assert report.configuration["chunk_size"] == 600


def test_citations_follow_deduplicated_source_order_not_chunk_order():
    example = GoldenExample(
        id="q5",
        tenant="t1",
        question="Question",
        expected_answer="Approved answer",
        relevant_chunk_ids=["good"],
    )
    report = build_report(
        [example],
        {
            "q5": {
                "retrieved": [
                    {"chunk_id": "wrong", "content": "unrelated"},
                    {"chunk_id": "good", "content": "Approved answer"},
                ],
                "sources": [
                    {"chunk_id": "good", "document": "policy.pdf"},
                    {"chunk_id": "wrong", "document": "other.pdf"},
                ],
                "answer": "Approved answer [1]",
            }
        },
        "dataset.jsonl",
    )
    assert report.cases[0].faithfulness_lexical == 1.0
    assert report.cases[0].citation_recall == 1.0


def test_abstention_precision_and_recall_are_reported():
    examples = [
        GoldenExample(
            id="q6-abstain",
            tenant="t1",
            question="Unknown",
            answer_type="abstention",
            should_abstain=True,
        ),
        GoldenExample(
            id="q6-answer",
            tenant="t1",
            question="Known",
            expected_answer="Answer",
            relevant_chunk_ids=["c1"],
        ),
    ]
    report = build_report(
        examples,
        {
            "q6-abstain": {"abstained": True},
            "q6-answer": {
                "retrieved": [{"chunk_id": "c1", "content": "Answer"}],
                "answer": "Answer [1]",
            },
        },
        "dataset.jsonl",
    )
    assert report.metrics["abstention_precision"] == 1.0
    assert report.metrics["abstention_recall"] == 1.0


def test_jsonl_loader_rejects_invalid_records(tmp_path):
    path = tmp_path / "golden.jsonl"
    path.write_text(
        json.dumps({
            "id": "q1",
            "tenant": "t1",
            "question": "Question",
            "should_abstain": True,
        }) + "\n",
        encoding="utf-8",
    )
    assert load_jsonl(path, GoldenExample)[0].id == "q1"

    path.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSONL"):
        load_jsonl(path, GoldenExample)


def test_jsonl_loader_reports_missing_artifact_as_validation_error(tmp_path):
    with pytest.raises(ValueError, match="Unable to read JSONL"):
        load_jsonl(tmp_path / "missing.jsonl", GoldenExample)


def test_golden_schema_rejects_unlabelled_answerable_case():
    with pytest.raises(ValueError, match="expected_answer|relevant_document_ids"):
        GoldenExample(
            id="incomplete",
            tenant="t1",
            question="What is the policy?",
        )


def test_golden_schema_rejects_template_placeholders():
    with pytest.raises(ValueError, match="template placeholders"):
        GoldenExample(
            id="template",
            tenant="t1",
            question="Replace with a question from the approved golden set.",
            expected_answer="Replace with the human-approved answer.",
            relevant_document_ids=["replace-with-document-id"],
        )
