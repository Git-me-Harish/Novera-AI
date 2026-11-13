"""Focused regression tests for Phase 0 release blockers."""
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.generation.guardrails import GuardrailsService


ROOT = Path(__file__).resolve().parents[1]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_input_normalization_is_canonical_and_control_safe():
    service = GuardrailsService()
    assert service.normalize_input("  Salary\u00a0 policy\n\n") == "Salary policy"
    assert "\x00" not in service.normalize_input("salary\x00 policy")


def test_numeric_citations_must_reference_available_sources():
    service = GuardrailsService()
    sources = [{"document": "policy.pdf"}, {"document": "finance.xlsx"}]
    assert service._check_citations("The rate is 10% [1].", sources)
    assert service._check_citations("The rate is 10% [1, 2].", sources)
    assert not service._check_citations("The rate is 10% [3].", sources)
    assert not service._check_citations("The rate is 10%.", sources)


def test_retrieval_sql_requires_organization_scope():
    vector = _source("app/services/retrieval/vector_search.py")
    keyword = _source("app/services/retrieval/keyword_search.py")
    assert "d.organization_id = :organization_id" in vector
    assert "d.organization_id = :organization_id" in keyword
    assert '"organization_id": str(organization_id)' in vector
    assert '"organization_id": str(organization_id)' in keyword


def test_search_and_chat_routes_require_organization_context():
    search = _source("app/api/endpoints/search.py")
    chat = _source("app/api/endpoints/chat.py")
    assert "Depends(get_current_active_user)" in search
    assert "current_user.organization_id" in search
    assert "current_user.organization_id" in chat


def test_debug_database_and_chunk_diagnostics_are_admin_and_tenant_scoped():
    chat = _source("app/api/endpoints/chat.py")
    assert "current_user: User = Depends(get_current_admin_user)" in chat
    assert "Document.organization_id == current_user.organization_id" in chat
    assert "d.organization_id = :organization_id" in chat
    assert "async def test_chat(current_user: User = Depends(get_current_admin_user))" in chat


def test_development_test_routes_are_not_public():
    auth = _source("app/api/endpoints/auth.py")
    search = _source("app/api/endpoints/search.py")
    assert "async def test_auth(current_user: User = Depends(get_current_admin_user))" in auth
    assert '@router.get("/search/test", dependencies=[Depends(get_current_active_user)])' in search


def test_document_qa_prompt_forbids_ungrounded_fallbacks():
    llm = _source("app/services/generation/llm_service.py")
    assert "answer ONLY from the supplied retrieved context" in llm
    assert "Do not use general knowledge" in llm
    assert "insufficient_context" in llm
    # Generation goes through the provider-agnostic chain, not a vendor SDK.
    assert "chat_chain_for" in llm
    assert "google.generativeai" not in llm


def test_document_ingestion_uses_durable_worker_queue():
    documents = _source("app/api/endpoints/documents.py")
    queue = _source("app/services/document_processing/job_queue.py")
    worker = _source("app/workers/document_worker.py")
    assert "BackgroundTasks" not in documents
    assert "document_job_queue.enqueue" in documents
    assert "xgroup_create" in queue
    assert "xack" in worker
    assert "DEAD_LETTER_STREAM_KEY" in worker


def test_generated_answers_are_not_truncated_by_golden_set_heuristics():
    # The old post-processor cut answers to two sentences using phrase lists
    # taken from golden questions, which dropped qualifiers and citations.
    from app.services.generation.llm_service import LLMService

    assert not hasattr(LLMService, "_compact_direct_answer")
    assert not hasattr(LLMService, "_answer_shape")


def test_confidence_uses_word_boundaries():
    from app.services.generation.llm_service import LLMService

    service = LLMService.__new__(LLMService)
    assert service._assess_confidence("The maximum FOIR is 50% [1].", "", None) == "medium"
    assert service._assess_confidence("It may apply [1].", "", None) == "low"


def test_billing_exhaustion_is_not_treated_as_a_rate_limit():
    from app.services.generation.llm_service import _is_billing_exhausted

    assert _is_billing_exhausted("429 Your prepayment credits are depleted.")
    assert not _is_billing_exhausted("429 Resource has been exhausted (e.g. check quota).")


def test_retrieval_limits_focused_context_before_generation():
    pipeline = _source("app/services/retrieval/pipeline.py")
    assert "focused_context_chunks" in pipeline
    assert "context_chunk_limit" in pipeline
    assert "top_n=context_chunk_limit" in pipeline
    hybrid = _source("app/services/retrieval/hybrid_search.py")
    assert "use_semantic: bool = True" in hybrid
    assert "use_keyword: bool = True" in hybrid
    assert "doc_type=doc_type" in hybrid
    assert "department=department" in hybrid


def test_hallucination_guard_does_not_treat_citations_as_numeric_claims():
    from app.services.generation.guardrails import guardrails_service

    assert guardrails_service._detect_hallucination(
        "The limit is 50% [1].", "The limit is 50%."
    ) == 0.0


def test_initial_admin_migration_has_no_hardcoded_password():
    migration = _source("alembic/versions/002_create_default_admin.py")
    assert "DEFAULT_ADMIN_PASSWORD" in migration
    assert "Admin@123" not in migration


def test_compose_does_not_embed_default_credentials():
    compose = (ROOT.parent / "docker-compose.yml").read_text(encoding="utf-8")
    assert "novera_pass_2025" not in compose
    assert "novera_redis_2025" not in compose
    assert "PGADMIN_DEFAULT_PASSWORD: admin" not in compose
    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?" in compose
    assert "REDIS_PASSWORD:?" in compose


def test_production_startup_does_not_run_create_all():
    session = _source("app/db/session.py")
    assert "is_development = settings.environment.lower()" in session
    assert "if not is_development:" in session
    assert "production schema is migration-managed" in session


def test_production_configuration_requires_ai_models():
    config = _source("app/core/config.py")
    assert 'self.environment.lower() in {"production", "prod"}' in config
    assert "LLM_PROVIDER and LLM_MODEL are required in production" in config
    assert "RERANK_PROVIDER is required in production" in config
    assert "llm_answer_timeout_seconds" in config
    assert "llm_attempt_timeout_seconds" in config


def test_production_settings_fail_fast_for_missing_provider_keys():
    base = {
        "_env_file": None,
        "database_url": "postgresql+asyncpg://u:p@localhost/db",
        "secret_key": "x" * 32,
        "environment": "production",
    }
    with pytest.raises(ValidationError, match="LLM_PROVIDER"):
        Settings(**base)
    with pytest.raises(ValidationError, match="EMBEDDING_PROVIDER"):
        Settings(**base, llm_provider="openai", llm_model="m")
    with pytest.raises(ValidationError, match="RERANK_PROVIDER"):
        Settings(**base, llm_provider="openai", llm_model="m",
                 embedding_provider="openai", embedding_model="e")
    # Reranking may be disabled, but only explicitly.
    Settings(**base, llm_provider="openai", llm_model="m",
             embedding_provider="openai", embedding_model="e", rerank_provider="none")
    # Legacy GEMINI_*/COHERE_* deployments still resolve to complete settings.
    legacy = Settings(**base, gemini_api_key="g" * 20, gemini_chat_model="chat-x",
                      gemini_embedding_model="models/embed-y", cohere_api_key="c" * 20,
                      cohere_rerank_model="rerank-z")
    assert (legacy.llm_provider, legacy.llm_model, legacy.llm_api_key) == ("gemini", "chat-x", "g" * 20)
    assert legacy.embedding_provider == "gemini" and legacy.rerank_provider == "cohere"
