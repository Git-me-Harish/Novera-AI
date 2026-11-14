"""Golden-set runner and CI quality gate.

The runner accepts predictions as JSONL so retrieval/generation can be run with
real services, recorded once, and evaluated repeatably without re-paying for
LLM calls during every CI run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .metrics import (
    aggregate,
    answer_correctness,
    citation_metrics,
    faithfulness,
    _matched_ids,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
    relevant_ids,
    relevant_keys,
    mark_evidence_completion,
)
from .judge import (
    JUDGE_VERSION,
    Judgment,
    cited_evidence,
    judgment_key,
    load_judgments,
    needs_judgment,
)
from .schemas import EvaluationCaseResult, EvaluationReport, GoldenExample


def load_jsonl(path: str | Path, model):
    records = []
    try:
        handle = Path(path).open("r", encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Unable to read JSONL at {path}: {exc}") from exc
    with handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                records.append(model.model_validate_json(line))
            except Exception as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
    if not records:
        raise ValueError(f"Dataset is empty: {path}")
    return records


def _ensure_unique_ids(records: list[Any], label: str) -> None:
    ids = [record.id for record in records]
    duplicates = sorted({record_id for record_id in ids if ids.count(record_id) > 1})
    if duplicates:
        raise ValueError(f"Duplicate {label} id(s): {', '.join(duplicates)}")


def load_predictions(path: str | Path) -> dict[str, dict[str, Any]]:
    records = load_jsonl(path, _Prediction)
    _ensure_unique_ids(records, "prediction")
    return {record.id: record.model_dump() for record in records}


def evaluate_case(
    example: GoldenExample,
    prediction: dict[str, Any],
    judgment: Judgment | None = None,
) -> EvaluationCaseResult:
    retrieved = mark_evidence_completion(example, prediction.get("retrieved", []) or [])
    pre_rerank = mark_evidence_completion(example, prediction.get("pre_rerank_retrieved", []) or [])
    answer = str(prediction.get("answer", "") or "")
    relevant = relevant_keys(example)
    found_relevant = relevant_ids(example, retrieved)
    sources = prediction.get("sources", []) or []
    source_count = int(prediction.get("source_count") or len(sources) or len(retrieved))
    citation_precision, citation_recall, citations = citation_metrics(
        answer, source_count, example.must_cite
    )

    cited_context_parts = []
    for index in citations:
        if sources and 1 <= index <= len(sources):
            source_chunk_id = str(sources[index - 1].get("chunk_id") or "")
            matching_chunk = next(
                (
                    chunk for chunk in retrieved
                    if str(chunk.get("chunk_id") or chunk.get("id") or "") == source_chunk_id
                ),
                None,
            )
            if matching_chunk:
                cited_context_parts.append(str(matching_chunk.get("content", "")))
        elif not sources and 1 <= index <= len(retrieved):
            # Backward-compatible path for hand-authored prediction fixtures.
            cited_context_parts.append(str(retrieved[index - 1].get("content", "")))
    cited_context = "\n".join(cited_context_parts) or str(prediction.get("context", ""))

    prediction_failed = bool(prediction.get("error"))
    if example.should_abstain:
        abstention_correct = bool(prediction.get("abstained", False))
    else:
        abstention_correct = not bool(prediction.get("abstained", False))
    if prediction_failed:
        abstention_correct = False

    retrieval_ids = [
        str(x.get("chunk_id") or x.get("id") or x.get("document_id"))
        for x in retrieved
    ]
    relevant_retrieved_items = sum(
        1 for item in retrieved if _matched_ids(item, relevant)
    )
    token_f1 = (
        1.0 if example.should_abstain and abstention_correct else answer_correctness(
            answer, example.expected_answer, example.acceptable_answers
        )
    )
    lexical_faithfulness = faithfulness(answer, cited_context, example.must_cite, source_count)
    if example.should_abstain or prediction_failed:
        # Abstention correctness is binary; failed predictions score zero.
        judged_correctness = 1.0 if abstention_correct else 0.0
        judged_faithfulness = 1.0 if abstention_correct else 0.0
        judged = True
    elif judgment is not None and not judgment.error:
        judged_correctness = judgment.correctness
        judged_faithfulness = judgment.faithfulness
        judged = True
    else:
        judged_correctness = judged_faithfulness = 0.0
        judged = False
    return EvaluationCaseResult(
        example_id=example.id,
        retrieval_ids=retrieval_ids,
        cited_source_numbers=citations,
        retrieved_relevant_ids=sorted(found_relevant),
        recall_at={str(k): recall_at_k(retrieved, relevant, k) for k in (1, 5, 10)},
        reciprocal_rank=reciprocal_rank(retrieved, relevant),
        ndcg_at={str(k): ndcg_at_k(retrieved, relevant, k) for k in (5, 10)},
        # Precision is item-based. A chunk can match both its chunk ID and its
        # parent document ID; counting both IDs would produce values above 1.
        context_precision=(
            relevant_retrieved_items / len(retrieved) if retrieved else 0.0
        ),
        context_recall=(len(found_relevant) / len(relevant) if relevant else 0.0),
        reranker_lift=(
            recall_at_k(retrieved, relevant, 5) - recall_at_k(pre_rerank, relevant, 5)
            if pre_rerank else 0.0
        ),
        answer_correctness=judged_correctness,
        faithfulness=judged_faithfulness,
        answer_token_f1=token_f1,
        faithfulness_lexical=lexical_faithfulness,
        judged=judged,
        unsupported_claims=(
            [c.claim for c in judgment.claims if not c.supported] if judgment else []
        ),
        missing_facts=(
            [f.fact for f in judgment.key_facts if not f.covered] if judgment else []
        ),
        judge_rationale=judgment.rationale if judgment else "",
        citation_precision=citation_precision,
        citation_recall=citation_recall,
        expected_abstention=example.should_abstain,
        predicted_abstention=bool(prediction.get("abstained", False)),
        abstention_correct=abstention_correct,
        latency_ms=float(prediction.get("latency_ms", 0.0) or 0.0),
        retrieval_latency_ms=float(prediction.get("retrieval_latency_ms", 0.0) or 0.0),
        generation_latency_ms=float(prediction.get("generation_latency_ms", 0.0) or 0.0),
        prompt_tokens=int(prediction.get("prompt_tokens", 0) or 0),
        completion_tokens=int(prediction.get("completion_tokens", 0) or 0),
        estimated_cost_usd=float(prediction.get("estimated_cost_usd", 0.0) or 0.0),
        cache_hit=bool(prediction.get("cache_hit", False)),
        answer=answer,
        error=prediction.get("error"),
    )


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((percentile / 100) * len(ordered) + 0.5)) - 1))
    return ordered[index]


def build_report(
    examples: list[GoldenExample],
    predictions: dict[str, dict[str, Any]],
    dataset_path: str,
    configuration: dict[str, Any] | None = None,
    thresholds: dict[str, float] | None = None,
    judgments: dict[str, Judgment] | None = None,
) -> EvaluationReport:
    """Score every example. ``judgments`` maps example id -> judge verdict."""
    judgments = judgments or {}
    cases = [
        evaluate_case(
            example,
            predictions.get(example.id, {"error": "missing prediction"}),
            judgments.get(example.id),
        )
        for example in examples
    ]
    true_positive = sum(
        1 for case in cases if case.expected_abstention and case.predicted_abstention
    )
    false_positive = sum(
        1 for case in cases if not case.expected_abstention and case.predicted_abstention
    )
    false_negative = sum(
        1 for case in cases if case.expected_abstention and not case.predicted_abstention
    )
    metrics = {
        "recall_at_1": aggregate(c.recall_at["1"] for c in cases),
        "recall_at_5": aggregate(c.recall_at["5"] for c in cases),
        "recall_at_10": aggregate(c.recall_at["10"] for c in cases),
        "mrr": aggregate(c.reciprocal_rank for c in cases),
        "ndcg_at_5": aggregate(c.ndcg_at["5"] for c in cases),
        "ndcg_at_10": aggregate(c.ndcg_at["10"] for c in cases),
        "context_precision": aggregate(c.context_precision for c in cases),
        "context_recall": aggregate(c.context_recall for c in cases),
        "reranker_lift": aggregate(c.reranker_lift for c in cases),
        "answer_correctness": aggregate(c.answer_correctness for c in cases),
        "faithfulness": aggregate(c.faithfulness for c in cases),
        "judged_coverage": aggregate(float(c.judged) for c in cases),
        "answer_token_f1": aggregate(c.answer_token_f1 for c in cases),
        "faithfulness_baseline": aggregate(c.faithfulness_lexical for c in cases),
        "citation_precision": aggregate(c.citation_precision for c in cases),
        "citation_recall": aggregate(c.citation_recall for c in cases),
        "abstention_accuracy": aggregate(float(c.abstention_correct) for c in cases),
        "abstention_precision": (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive else 0.0
        ),
        "abstention_recall": (
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative else 0.0
        ),
        "p50_latency_ms": _percentile([c.latency_ms for c in cases], 50),
        "p95_latency_ms": _percentile([c.latency_ms for c in cases], 95),
        "p99_latency_ms": _percentile([c.latency_ms for c in cases], 99),
        "p95_retrieval_latency_ms": _percentile(
            [c.retrieval_latency_ms for c in cases], 95
        ),
        "p95_generation_latency_ms": _percentile(
            [c.generation_latency_ms for c in cases], 95
        ),
        "average_prompt_tokens": aggregate(c.prompt_tokens for c in cases),
        "average_completion_tokens": aggregate(c.completion_tokens for c in cases),
        "average_cost_usd": aggregate(c.estimated_cost_usd for c in cases),
        "cache_hit_rate": aggregate(float(c.cache_hit) for c in cases),
        "error_rate": aggregate(float(bool(c.error)) for c in cases),
    }
    failures = []
    expected_ids = {example.id for example in examples}
    prediction_ids = set(predictions)
    for missing_id in sorted(expected_ids - prediction_ids):
        failures.append(f"missing prediction: {missing_id}")
    for unexpected_id in sorted(prediction_ids - expected_ids):
        failures.append(f"prediction has no dataset example: {unexpected_id}")
    for case in cases:
        if case.error:
            failures.append(f"{case.example_id}: prediction error={case.error}")
        elif not case.judged and judgments:
            failures.append(f"{case.example_id}: missing or failed judgment")
    for key, minimum in (thresholds or {}).items():
        if key.startswith("max_"):
            metric_key = key[4:]
            actual = metrics.get(metric_key)
            if actual is None:
                continue
            if actual > minimum:
                failures.append(f"{metric_key}={actual:.4f} > maximum={minimum:.4f}")
            continue
        actual = metrics.get(key)
        if actual is not None and actual < minimum:
            failures.append(f"{key}={actual:.4f} < minimum={minimum:.4f}")
    return EvaluationReport(
        git_sha=_git_sha(),
        dataset_path=str(dataset_path),
        dataset_size=len(examples),
        configuration=configuration or {},
        metrics=metrics,
        cases=cases,
        passed=not failures,
        failures=failures,
    )


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return None


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Novera RAG predictions against a golden JSONL set")
    parser.add_argument("--dataset", required=True, help="Golden examples JSONL")
    parser.add_argument("--predictions", required=True, help="Recorded predictions JSONL")
    parser.add_argument("--output", required=True, help="Evaluation report JSON")
    parser.add_argument(
        "--judgments",
        required=True,
        help="Judge verdicts JSONL from app.evaluation.judge; correctness and "
        "faithfulness cannot be gated on lexical overlap",
    )
    parser.add_argument("--min-recall-at-5", type=float, default=None)
    parser.add_argument("--min-answer-correctness", type=float, default=None)
    parser.add_argument("--min-faithfulness", type=float, default=None)
    parser.add_argument("--min-citation-recall", type=float, default=None)
    parser.add_argument("--max-p95-latency-ms", type=float, default=None)
    args = parser.parse_args()
    required_thresholds = {
        "--min-recall-at-5": args.min_recall_at_5,
        "--min-answer-correctness": args.min_answer_correctness,
        "--min-faithfulness": args.min_faithfulness,
        "--min-citation-recall": args.min_citation_recall,
        "--max-p95-latency-ms": args.max_p95_latency_ms,
    }
    missing_thresholds = [name for name, value in required_thresholds.items() if value is None]
    if missing_thresholds:
        raise ValueError(
            "A production quality gate requires all thresholds: "
            + ", ".join(missing_thresholds)
        )
    examples = load_jsonl(args.dataset, GoldenExample)
    _ensure_unique_ids(examples, "dataset")
    predictions = load_predictions(args.predictions)
    configurations = [p["configuration"] for p in predictions.values() if p.get("configuration")]
    # Bind each verdict to the exact prediction it judged; a stale verdict for
    # a changed answer must not be reused.
    cached = load_judgments(args.judgments)
    if not cached:
        raise ValueError(f"No judgments found at {args.judgments}")
    judge_model = next(iter(cached.values())).judge_model
    judgments = {}
    for example in examples:
        prediction = predictions.get(example.id)
        if prediction is None or not needs_judgment(example, prediction):
            continue
        key = judgment_key(judge_model, example, prediction, cited_evidence(prediction))
        if key in cached:
            judgments[example.id] = cached[key]
    thresholds = {
        "recall_at_5": args.min_recall_at_5,
        "answer_correctness": args.min_answer_correctness,
        "faithfulness": args.min_faithfulness,
        "citation_recall": args.min_citation_recall,
        "max_p95_latency_ms": args.max_p95_latency_ms,
    }
    report = build_report(
        examples,
        predictions,
        args.dataset,
        configuration={
            **(configurations[0] if configurations else {}),
            "judge_model": judge_model,
            "judge_version": JUDGE_VERSION,
        },
        thresholds=thresholds,
        judgments=judgments,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(json.dumps({"passed": report.passed, "metrics": report.metrics, "failures": report.failures}, indent=2))
    return 0 if report.passed else 1


class _Prediction(BaseModel):
    id: str
    retrieved: list[dict[str, Any]] = Field(default_factory=list)
    answer: str = ""
    context: str = ""
    source_count: int | None = None
    abstained: bool = False
    latency_ms: float = 0.0
    retrieval_latency_ms: float = 0.0
    generation_latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0
    error: str | None = None
    retrieval_metadata: dict[str, Any] = Field(default_factory=dict)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    pre_rerank_retrieved: list[dict[str, Any]] = Field(default_factory=list)
    cache_hit: bool = False
    configuration: dict[str, Any] = Field(default_factory=dict)


if __name__ == "__main__":
    try:
        raise SystemExit(_cli())
    except ValueError as exc:
        print(f"evaluation error: {exc}", file=sys.stderr)
        raise SystemExit(2)
