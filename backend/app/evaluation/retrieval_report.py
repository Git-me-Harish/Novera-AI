"""Summarise a retrieval-only run (see live_runner --retrieval-only).

    python -m app.evaluation.retrieval_report --dataset <golden.jsonl> --predictions <run.jsonl>

Answerable questions report recall@k, MRR, nDCG and reranker lift; questions
that should be refused report how often retrieval still passed evidence to
the generator (each one is a hallucination risk the prompt must absorb).
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from app.evaluation.runner import evaluate_case, load_jsonl
from app.evaluation.schemas import GoldenExample


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def summarise(examples: list[GoldenExample], predictions: dict[str, dict]) -> dict:
    answerable, refusals = [], []
    for example in examples:
        prediction = predictions.get(example.id)
        if prediction is None or prediction.get("error"):
            continue
        if example.should_abstain:
            refusals.append(len(prediction.get("retrieved") or []))
            continue
        result = evaluate_case(example, prediction)
        answerable.append((example, result, prediction))

    def mean(get) -> float:
        return round(statistics.fmean(get(r) for _, r, _ in answerable), 4) if answerable else 0.0

    latencies = [p.get("latency_ms", 0.0) for _, _, p in answerable]
    misses = [e.id for e, r, _ in answerable if r.recall_at.get("10", 0.0) == 0.0]
    return {
        "answerable": len(answerable),
        "recall@1": mean(lambda r: r.recall_at["1"]),
        "recall@5": mean(lambda r: r.recall_at["5"]),
        "recall@10": mean(lambda r: r.recall_at["10"]),
        "mrr": mean(lambda r: r.reciprocal_rank),
        "ndcg@5": mean(lambda r: r.ndcg_at["5"]),
        "context_precision": mean(lambda r: r.context_precision),
        "reranker_lift@5": mean(lambda r: r.reranker_lift),
        "avg_final_chunks": round(statistics.fmean(len(p.get("retrieved") or []) for _, _, p in answerable), 2)
        if answerable else 0.0,
        "latency_p50_ms": round(_pct(latencies, 0.5), 1),
        "latency_p95_ms": round(_pct(latencies, 0.95), 1),
        "missed_entirely": misses,
        "refusal_questions": len(refusals),
        "refusals_with_evidence_passed": sum(1 for n in refusals if n > 0),
        "errors": sum(1 for p in predictions.values() if p.get("error")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    args = parser.parse_args()
    examples = load_jsonl(args.dataset, GoldenExample)
    predictions = {
        row["id"]: row
        for row in (json.loads(line) for line in args.predictions.read_text(encoding="utf-8").splitlines() if line.strip())
    }
    print(json.dumps(summarise(examples, predictions), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
