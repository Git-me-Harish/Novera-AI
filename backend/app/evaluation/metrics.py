"""Deterministic retrieval and answer metrics used by the evaluation gate."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence

_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
# Must accept the same grouped form ("[1, 2]") the production citation
# extractor accepts, otherwise valid multi-source answers score as uncited.
_CITATION_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _set(text: str) -> set[str]:
    return set(_tokens(text))


EVIDENCE_COVERAGE = 0.8


def relevant_keys(example) -> set[str]:
    """What counts as relevant for an example.

    Text-anchored evidence ("evidence:<i>") when the example has it; chunk and
    document ids otherwise (legacy labels, valid only until re-chunking).
    """
    evidence = getattr(example, "evidence", None) or []
    if evidence:
        return {f"evidence:{index}" for index in range(len(evidence))}
    return set(example.relevant_chunk_ids) | set(example.relevant_document_ids)


def evidence_matches(example, *, document_id: str, document_name: str, content: str) -> list[int]:
    """Indices of the example's evidence passages contained in this chunk."""
    matches = []
    chunk_tokens = _set(content)
    for index, evidence in enumerate(getattr(example, "evidence", None) or []):
        same_document = (
            (evidence.document_id and evidence.document_id == document_id)
            or (evidence.document and evidence.document.casefold() == (document_name or "").casefold())
        )
        quote_tokens = _set(evidence.quote)
        if not same_document or not quote_tokens:
            continue
        if len(quote_tokens & chunk_tokens) / len(quote_tokens) >= EVIDENCE_COVERAGE:
            matches.append(index)
    return matches


def _matched_ids(item: dict, relevant: set[str]) -> set[str]:
    keys = {
        str(item[key])
        for key in ("chunk_id", "id", "document_id")
        if item.get(key) is not None
    }
    keys.update(f"evidence:{index}" for index in item.get("evidence_matches") or [])
    return keys & relevant


def relevant_ids(example, retrieved: Sequence[dict]) -> set[str]:
    expected = relevant_keys(example)
    found: set[str] = set()
    for item in retrieved:
        found.update(_matched_ids(item, expected))
    return found


def recall_at_k(retrieved: Sequence[dict], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    matched = set()
    for item in retrieved[:k]:
        matched.update(_matched_ids(item, relevant))
    return len(matched) / len(relevant)


def reciprocal_rank(retrieved: Sequence[dict], relevant: set[str]) -> float:
    for rank, item in enumerate(retrieved, 1):
        if _matched_ids(item, relevant):
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved: Sequence[dict], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    ranked = retrieved[:k]
    seen_relevant: set[str] = set()
    dcg = 0.0
    for i, item in enumerate(ranked):
        matched = _matched_ids(item, relevant) - seen_relevant
        if matched:
            dcg += 1.0 / math.log2(i + 2)
            seen_relevant.update(matched)
    ideal_hits = min(len(relevant), k)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    return dcg / ideal if ideal else 0.0


def citation_numbers(answer: str) -> list[int]:
    return sorted(
        {int(n) for group in _CITATION_RE.findall(answer or "") for n in group.split(",")}
    )


def citation_metrics(answer: str, source_count: int, must_cite: bool) -> tuple[float, float, list[int]]:
    citations = citation_numbers(answer)
    valid = [n for n in citations if 1 <= n <= source_count]
    precision = len(valid) / len(citations) if citations else (0.0 if must_cite else 1.0)
    recall = 1.0 if (valid and must_cite) or not must_cite else 0.0
    return precision, recall, citations


def answer_correctness(answer: str, expected: str, acceptable: Iterable[str] = ()) -> float:
    candidates = [expected, *acceptable]
    actual_tokens = _set(answer)
    if not actual_tokens:
        return 0.0
    best = 0.0
    for candidate in candidates:
        expected_tokens = _set(candidate)
        if not expected_tokens:
            continue
        overlap = len(actual_tokens & expected_tokens)
        precision = overlap / len(actual_tokens)
        recall = overlap / len(expected_tokens)
        score = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
        best = max(best, score)
    return best


def faithfulness(
    answer: str,
    cited_context: str,
    must_cite: bool = True,
    source_count: int | None = None,
) -> float:
    """Conservative lexical evidence score.

    This is intentionally labelled as a deterministic baseline, not an NLI judge.
    It provides a repeatable CI signal until a separately versioned entailment
    evaluator is enabled.
    """
    # Citation markers are metadata, not factual claim tokens.
    answer_without_citations = _CITATION_RE.sub("", answer or "")
    answer_tokens = _set(answer_without_citations)
    if not answer_tokens:
        return 1.0
    citations = citation_numbers(answer)
    if must_cite and not citations:
        return 0.0
    if source_count is not None and any(n < 1 or n > source_count for n in citations):
        return 0.0
    context_tokens = _set(cited_context)
    return len(answer_tokens & context_tokens) / len(answer_tokens)


def aggregate(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0
