"""Anchor golden-set labels to evidence text instead of chunk ids.

For every example labelled only by ``relevant_chunk_ids``, read those chunks
and store the sentences that actually state the expected answer as
``evidence`` (document id, filename, pages, quote). Evaluation then matches
any chunk containing the quote, so labels survive re-chunking.

Run once against the corpus the ids were labelled on, review the diff, keep
the original file (a ``.bak`` copy is written next to it):

    python -m app.evaluation.anchor_golden --dataset evals/test_evals/golden_questions.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.evaluation.metrics import _set
from app.models.document import Chunk, Document

# Function words carry no evidence; scoring on them picks boilerplate sentences.
_STOP = set("""a an and are as at be by for from has have in is it its of on or that the this to was were
will with which who what when where how why do does not no can may shall should under""".split())
MAX_QUOTE_TOKENS = 60
MIN_SENTENCE_TOKENS = 6


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [" ".join(p.split()) for p in parts if len(p.split()) >= MIN_SENTENCE_TOKENS]


def best_quote(content: str, answers: list[str]) -> str:
    """The shortest run of sentences that covers the answer's content words."""
    target = set().union(*(_set(a) for a in answers)) - _STOP
    sentences = _sentences(content)
    if not sentences or not target:
        return " ".join(content.split()[:MAX_QUOTE_TOKENS])
    scored = sorted(
        enumerate(sentences),
        key=lambda pair: len((_set(pair[1]) - _STOP) & target),
        reverse=True,
    )
    chosen: list[int] = []
    covered: set[str] = set()
    for index, sentence in scored:
        gain = (_set(sentence) - _STOP) & target - covered
        if not gain:
            continue
        chosen.append(index)
        covered |= gain
        if sum(len(sentences[i].split()) for i in chosen) >= MAX_QUOTE_TOKENS:
            break
    if not chosen:
        chosen = [scored[0][0]]
    return " ".join(sentences[i] for i in sorted(chosen))


async def anchor(path: Path) -> tuple[int, int]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = {cid for row in rows if not row.get("evidence") for cid in row.get("relevant_chunk_ids", [])}
    async with AsyncSessionLocal() as db:
        found = (await db.execute(
            select(Chunk.id, Chunk.content, Chunk.page_numbers, Document.id.label("doc_id"), Document.filename)
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.id.in_([UUID(i) for i in ids]))
        )).all() if ids else []
    chunks = {str(row.id): row for row in found}

    anchored = missing = 0
    for row in rows:
        if row.get("evidence") or not row.get("relevant_chunk_ids"):
            continue
        answers = [row.get("expected_answer", "")] + list(row.get("acceptable_answers") or [])
        evidence = []
        for chunk_id in row["relevant_chunk_ids"]:
            chunk = chunks.get(chunk_id)
            if chunk is None:
                missing += 1
                continue
            evidence.append({
                "document_id": str(chunk.doc_id),
                "document": chunk.filename,
                "pages": list(chunk.page_numbers or []),
                "quote": best_quote(chunk.content, answers),
            })
        if evidence:
            row["evidence"] = evidence
            anchored += 1

    shutil.copyfile(path, path.with_suffix(path.suffix + ".bak"))
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return anchored, missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", required=True, type=Path)
    args = parser.parse_args()
    anchored, missing = asyncio.run(anchor(args.dataset))
    print(f"Anchored {anchored} examples; {missing} labelled chunk ids no longer exist")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
