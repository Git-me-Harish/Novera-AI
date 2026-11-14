"""Strict, versioned schemas for the RAG golden set and reports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Evidence(BaseModel):
    """Where the answer is stated, anchored to text rather than to a chunk id.

    Chunk ids change whenever a document is re-chunked (better table
    extraction, new chunk sizes), which silently invalidated id-only labels.
    A retrieved chunk is relevant when it belongs to the same document and
    contains (most of) the quoted passage.
    """

    document_id: str = ""
    document: str = Field(default="", max_length=500)
    quote: str = Field(min_length=1, max_length=4000)
    pages: list[int] = Field(default_factory=list)

    @field_validator("quote", mode="before")
    @classmethod
    def normalize_quote(cls, value: Any) -> str:
        return " ".join(str(value or "").split())


class GoldenExample(BaseModel):
    """One evaluation question and its human-authored expectations."""

    id: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=10_000)
    tenant: str = Field(min_length=1, max_length=200)
    expected_answer: str = ""
    acceptable_answers: list[str] = Field(default_factory=list)
    relevant_document_ids: list[str] = Field(default_factory=list)
    relevant_chunk_ids: list[str] = Field(default_factory=list)
    # Preferred over chunk ids when present; see Evidence.
    evidence: list[Evidence] = Field(default_factory=list)
    must_cite: bool = True
    answer_type: Literal["factual", "numeric", "abstention", "list", "conversational"] = "factual"
    should_abstain: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("question", "expected_answer", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").split())

    @model_validator(mode="after")
    def validate_ground_truth(self) -> "GoldenExample":
        placeholder_fields = {
            "question": self.question,
            "expected_answer": self.expected_answer,
            "acceptable_answers": " ".join(self.acceptable_answers),
            "relevant_document_ids": " ".join(self.relevant_document_ids),
            "relevant_chunk_ids": " ".join(self.relevant_chunk_ids),
        }
        if any(
            "replace with" in value.lower() or "replace-with" in value.lower()
            for value in placeholder_fields.values()
        ):
            raise ValueError("golden examples cannot contain template placeholders")
        if self.answer_type not in {"conversational", "abstention"} and not self.should_abstain:
            if not self.expected_answer and not self.acceptable_answers:
                raise ValueError(
                    "non-abstention examples require expected_answer or acceptable_answers"
                )
            if not self.relevant_document_ids and not self.relevant_chunk_ids and not self.evidence:
                raise ValueError(
                    "non-abstention examples require evidence, relevant_document_ids or relevant_chunk_ids"
                )
        return self


class EvaluationCaseResult(BaseModel):
    """Machine-generated metrics for a single golden example."""

    example_id: str
    retrieval_ids: list[str] = Field(default_factory=list)
    cited_source_numbers: list[int] = Field(default_factory=list)
    retrieved_relevant_ids: list[str] = Field(default_factory=list)
    recall_at: dict[str, float] = Field(default_factory=dict)
    reciprocal_rank: float = 0.0
    ndcg_at: dict[str, float] = Field(default_factory=dict)
    context_precision: float = 0.0
    context_recall: float = 0.0
    reranker_lift: float = 0.0
    # Judged (claim-level) scores gate releases; the lexical ones are cheap
    # regression signals that measure wording overlap, not truth.
    answer_correctness: float = 0.0
    faithfulness: float = 0.0
    answer_token_f1: float = 0.0
    faithfulness_lexical: float = 0.0
    judged: bool = False
    unsupported_claims: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    judge_rationale: str = ""
    citation_precision: float = 0.0
    citation_recall: float = 0.0
    expected_abstention: bool = False
    predicted_abstention: bool = False
    abstention_correct: bool = False
    latency_ms: float = 0.0
    retrieval_latency_ms: float = 0.0
    generation_latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0
    cache_hit: bool = False
    answer: str = ""
    error: str | None = None


class EvaluationReport(BaseModel):
    """Reproducible aggregate report, suitable for CI and artifact storage."""

    schema_version: str = "2.0"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    git_sha: str | None = None
    dataset_path: str
    dataset_size: int
    configuration: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    cases: list[EvaluationCaseResult] = Field(default_factory=list)
    passed: bool = False
    failures: list[str] = Field(default_factory=list)
