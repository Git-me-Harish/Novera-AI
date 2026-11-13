# Novera RAG evaluation contract

The evaluation runner is intentionally data-driven. It does not create or infer
HR/Finance ground truth. The approved golden set must be supplied by the
business/evaluation owner and reviewed whenever a document corpus changes.

## Golden set

Use one JSON object per line. The schema is defined by `GoldenExample` and the
starter shape is in `backend/evals/golden_questions.template.jsonl`.

Required fields:

- `id`, `tenant`, `question`
- `expected_answer` or `acceptable_answers`
- `relevant_document_ids` and/or `relevant_chunk_ids`
- `must_cite`, `answer_type`, and `should_abstain`

Chunk/document IDs must be stable identifiers from the evaluation corpus. Do
not commit raw HR or Finance content to the repository unless that is explicitly
approved; store sensitive golden sets in the protected evaluation artifact
store and pass the path at runtime.

Source PDFs and other corpus documents are not golden sets. A document such as
`backend/evals/Module_3_Operational_Processes.pdf` may be indexed for retrieval,
but it cannot establish expected answers, relevance labels, citation requirements,
or abstention cases by itself. Those labels must be reviewed and exported as the
JSONL contract above before a release-quality baseline can be recorded.

## Prediction contract

The system-under-test records one JSON object per golden example:

```json
{
  "id": "finance_001",
  "retrieved": [
    {"chunk_id": "chunk-123", "content": "...", "score": 0.91}
  ],
  "sources": [
    {"chunk_id": "chunk-123", "document": "policy.pdf", "page": 4}
  ],
  "answer": "The approved amount is ... [1]",
  "context": "...",
  "source_count": 1,
  "abstained": false,
  "latency_ms": 842.4,
  "prompt_tokens": 950,
  "completion_tokens": 120,
  "estimated_cost_usd": 0.00042
}
```

The `sources` order is authoritative because it is the exact deduplicated source
list shown to the LLM; `sources[0]` is citation `[1]`. The recorder also includes
the final post-rerank chunk order and retrieval metadata separately when
available. Legacy fixtures without `sources` fall back to retrieved order.

## Run the gate

The gate has three steps. Predictions are recorded once from the real
production chat path (`chat_service.chat`: input guardrails, classification,
reformulation, retrieval, generation, output policy), judged once, then scored
repeatably. From `backend` with `$env:PYTHONPATH = "."`:

```powershell
# 1. Record predictions (semantic cache bypassed; --include-content is required
#    for judging and must only be written to an access-controlled location)
python -m app.evaluation.live_runner `
  --dataset ..\path\to\golden_questions.jsonl `
  --output ..\artifacts\predictions.jsonl --include-content

# 2. Judge claim by claim (EVAL_JUDGE_PROVIDER/EVAL_JUDGE_MODEL, any provider;
#    defaults to the platform chat model — prefer a stronger one). The output
#    file doubles as a cache keyed by judge version + model + inputs.
python -m app.evaluation.judge `
  --dataset ..\path\to\golden_questions.jsonl `
  --predictions ..\artifacts\predictions.jsonl `
  --output ..\artifacts\judgments.jsonl

# 3. Score and gate
python -m app.evaluation.runner `
  --dataset ..\path\to\golden_questions.jsonl `
  --predictions ..\artifacts\predictions.jsonl `
  --judgments ..\artifacts\judgments.jsonl `
  --output ..\artifacts\rag-evaluation.json `
  --min-recall-at-5 0.90 --min-answer-correctness 0.85 `
  --min-faithfulness 0.90 --min-citation-recall 0.95 --max-p95-latency-ms 2000
```

`answer_correctness` (reference key facts covered, zero on contradiction) and
`faithfulness` (claims supported by the cited evidence) are judged metrics and
are the ones gated. `answer_token_f1` and `faithfulness_baseline` are lexical
overlap signals kept for cheap regression tracking; they penalise correct
paraphrases and must not be used as release gates. A judgment is bound to the
exact answer and evidence it judged, so a changed answer without a fresh
judgment fails the gate. Provider outages and rejected inputs are recorded as
prediction errors, never as wrong answers or abstentions.

Exit code `0` means all thresholds pass and every case has a successful,
judged prediction; `1` means the gate failed; `2` means a contract is invalid.

Reports also include `reranker_lift` (Recall@5 after reranking minus before
reranking) and `cache_hit_rate`. The prediction recorder captures the
pre-rerank candidate IDs and the production LLM cache-hit flag for these
measurements.

Abstention is reported as accuracy plus precision and recall, so a system that
avoids hallucinations by refusing every question cannot appear healthy.

The reusable workflow at `.github/workflows/rag-quality.yml` runs the focused
regression tests and the same quality gate in CI. A caller must materialize the
protected golden/prediction artifacts in the checkout and pass all four
thresholds and the judgments path to the reusable workflow; sensitive evaluation data is not committed
to this repository.

Changing the judge prompt requires bumping `JUDGE_VERSION` in `judge.py`.
Spot-check a sample of judge verdicts against human review whenever the judge
model or prompt changes.
