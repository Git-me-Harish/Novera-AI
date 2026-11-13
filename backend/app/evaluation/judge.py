"""Claim-level LLM judge for answer correctness and faithfulness.

The lexical metrics in ``metrics.py`` reward wording overlap, so a correct but
paraphrased answer scores ~0.5 and a fluent answer that copies context words
can look "faithful" while asserting something the evidence does not say. This
judge decomposes every answer into claims and checks each one:

* faithfulness = supported claims / total claims, judged ONLY against the
  evidence the system actually showed the generator (cited sources first).
* correctness  = reference key facts covered by the answer / total key facts,
  forced to 0 when the answer contradicts the reference.

Judgments are cached by a content hash that includes the judge version and
model, so re-running the gate on unchanged predictions is free and
deterministic. Changing the prompt requires bumping ``JUDGE_VERSION``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .metrics import citation_numbers
from .schemas import GoldenExample

JUDGE_VERSION = "claim-judge-v1"
_MAX_EVIDENCE_CHARS = 24_000

_JUDGE_PROMPT = """You are a strict evaluator for an enterprise retrieval-augmented QA system.
You will receive a QUESTION, a REFERENCE answer written by a human reviewer, the
EVIDENCE passages the system retrieved (numbered as the system cited them), and
the system ANSWER. Citation markers such as [1] refer to evidence numbers.

Do the following and return ONLY JSON matching the schema below.

1. claims: split the ANSWER into atomic factual claims. Ignore greetings,
   citation markers and statements that the documents lack information. For
   each claim decide "supported" = true only if the EVIDENCE explicitly states
   or directly entails it. Use only the EVIDENCE, never outside knowledge.
2. key_facts: split the REFERENCE into the atomic facts a correct answer must
   contain. For each, "covered" = true if the ANSWER states it (paraphrase is
   fine; numbers, units, conditions and exceptions must match).
3. contradicts_reference: true if any ANSWER claim conflicts with the REFERENCE.
4. abstained: true if the ANSWER declines to answer for lack of information.

Schema:
{"claims": [{"claim": str, "supported": bool}],
 "key_facts": [{"fact": str, "covered": bool}],
 "contradicts_reference": bool,
 "abstained": bool,
 "rationale": str}

QUESTION:
{question}

REFERENCE:
{reference}

EVIDENCE:
{evidence}

ANSWER:
{answer}
"""


class ClaimVerdict(BaseModel):
    claim: str
    supported: bool


class FactVerdict(BaseModel):
    fact: str
    covered: bool


class Judgment(BaseModel):
    """One cached judge verdict; ``key`` binds it to its exact inputs."""

    id: str
    key: str
    judge_version: str = JUDGE_VERSION
    judge_model: str
    claims: list[ClaimVerdict] = Field(default_factory=list)
    key_facts: list[FactVerdict] = Field(default_factory=list)
    contradicts_reference: bool = False
    abstained: bool = False
    rationale: str = ""
    error: str | None = None

    @property
    def faithfulness(self) -> float:
        if not self.claims:
            return 1.0
        return sum(c.supported for c in self.claims) / len(self.claims)

    @property
    def correctness(self) -> float:
        if self.contradicts_reference or not self.key_facts:
            return 0.0
        return sum(f.covered for f in self.key_facts) / len(self.key_facts)


def cited_evidence(prediction: dict[str, Any]) -> str:
    """Render the evidence the generator saw, numbered exactly as cited.

    Cited sources come first; when an answer cites nothing, all sources are
    shown so unsupported claims are still judged against what was available.
    """
    sources = prediction.get("sources") or []
    retrieved = prediction.get("retrieved") or []
    by_id = {
        str(chunk.get("chunk_id") or chunk.get("id") or ""): str(chunk.get("content") or "")
        for chunk in retrieved
    }
    numbers = citation_numbers(prediction.get("answer", "")) or list(range(1, len(sources) + 1))
    parts = []
    for number in numbers:
        if 1 <= number <= len(sources):
            content = by_id.get(str(sources[number - 1].get("chunk_id") or ""), "")
            if content:
                parts.append(f"[{number}] {content}")
    if not parts and not sources:
        parts = [f"[{i}] {c.get('content', '')}" for i, c in enumerate(retrieved, 1) if c.get("content")]
    return "\n\n".join(parts)[:_MAX_EVIDENCE_CHARS]


def judgment_key(model: str, example: GoldenExample, prediction: dict[str, Any], evidence: str) -> str:
    raw = json.dumps(
        [
            JUDGE_VERSION,
            model,
            example.question,
            example.expected_answer,
            example.acceptable_answers,
            prediction.get("answer", ""),
            evidence,
        ],
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def needs_judgment(example: GoldenExample, prediction: dict[str, Any]) -> bool:
    """Abstention cases and failed predictions are scored without a judge."""
    return not example.should_abstain and not prediction.get("error") and bool(
        (prediction.get("answer") or "").strip()
    )


def judge_model_label() -> str:
    """'provider:model' of the judge: EVAL_JUDGE_* or the platform chat model."""
    from app.core.config import settings

    provider = settings.eval_judge_provider or settings.llm_provider
    model = settings.eval_judge_model or settings.llm_model
    if not (provider and model):
        raise ValueError("Configure EVAL_JUDGE_PROVIDER/EVAL_JUDGE_MODEL or LLM_PROVIDER/LLM_MODEL")
    return f"{provider}:{model}"


async def _call_judge(model_label: str, prompt: str) -> dict[str, Any]:
    from app.core.config import settings
    from app.services.ai.chat import build_chat_client
    from app.services.ai.types import ChatMessage, ModelSpec

    provider, _, model = model_label.partition(":")
    same = provider == settings.llm_provider
    client = build_chat_client(ModelSpec(
        provider, model,
        settings.llm_api_key if same else settings.credential_for(provider),
        settings.llm_base_url if same else None,
    ))
    result = await client.complete(
        [ChatMessage("user", prompt)], temperature=0.0, max_tokens=4000,
        json_mode=True, timeout=90,
    )
    if result.text is None:
        raise ValueError("judge model returned no content")
    text = result.text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    return json.loads(text)


async def judge_predictions(
    examples: list[GoldenExample],
    predictions: dict[str, dict[str, Any]],
    *,
    model_name: str,
    cache: dict[str, Judgment] | None = None,
    concurrency: int = 4,
) -> list[Judgment]:
    cache = cache or {}
    semaphore = asyncio.Semaphore(concurrency)

    async def _one(example: GoldenExample) -> Judgment | None:
        prediction = predictions.get(example.id)
        if prediction is None or not needs_judgment(example, prediction):
            return None
        evidence = cited_evidence(prediction)
        key = judgment_key(model_name, example, prediction, evidence)
        if key in cache and not cache[key].error:
            return cache[key]
        reference = " | ".join([example.expected_answer, *example.acceptable_answers]).strip(" |")
        prompt = (
            _JUDGE_PROMPT.replace("{question}", example.question)
            .replace("{reference}", reference)
            .replace("{evidence}", evidence or "(no evidence was retrieved)")
            .replace("{answer}", prediction.get("answer", ""))
        )
        async with semaphore:
            for attempt in range(3):
                try:
                    data = await _call_judge(model_name, prompt)
                    return Judgment(id=example.id, key=key, judge_model=model_name, **data)
                except Exception as exc:  # judged as an error, never silently passed
                    error = f"{type(exc).__name__}: {str(exc)[:200]}"
                    await asyncio.sleep(2 ** attempt * 5)
            return Judgment(id=example.id, key=key, judge_model=model_name, error=error)

    results = await asyncio.gather(*(_one(example) for example in examples))
    return [result for result in results if result is not None]


def load_judgments(path: str | Path) -> dict[str, Judgment]:
    """Return cached judgments keyed by their input hash."""
    path = Path(path)
    if not path.exists():
        return {}
    judgments = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            judgment = Judgment.model_validate_json(line)
            judgments[judgment.key] = judgment
    return judgments


async def _cli_async(args: argparse.Namespace) -> int:
    from app.core.config import settings

    from .runner import load_jsonl, load_predictions

    examples = load_jsonl(args.dataset, GoldenExample)
    predictions = load_predictions(args.predictions)
    model_name = args.model or judge_model_label()
    cache = load_judgments(args.output)
    judgments = await judge_predictions(
        examples, predictions, model_name=model_name, cache=cache, concurrency=args.concurrency
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for judgment in judgments:
            handle.write(judgment.model_dump_json() + "\n")
    errors = [j.id for j in judgments if j.error]
    print(f"Judged {len(judgments)} predictions with {model_name} ({JUDGE_VERSION}); errors={errors}")
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Judge recorded Novera predictions claim by claim")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output", required=True, help="Judgments JSONL (also used as the cache)")
    parser.add_argument("--model", default=None,
                        help="Judge as provider:model; defaults to EVAL_JUDGE_PROVIDER/EVAL_JUDGE_MODEL")
    parser.add_argument("--concurrency", type=int, default=4)
    return asyncio.run(_cli_async(parser.parse_args()))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"judge error: {exc}", file=sys.stderr)
        raise SystemExit(2)
