"""Re-embed stored chunks with the configured embedding model.

Changing EMBEDDING_PROVIDER / EMBEDDING_MODEL / EMBEDDING_DIMENSIONS moves the
corpus to a new vector space. Search only compares vectors stamped with the
current model, so until this runs, semantic search finds nothing for the old
chunks (keyword search keeps working). Nothing is mixed or padded.

The command is safe to stop and re-run: it only selects chunks whose stamp
differs from the current model and commits after every batch.

    python -m app.cli.reembed --dry-run
    python -m app.cli.reembed
    python -m app.cli.reembed --organization <uuid> --all
"""
from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from loguru import logger
from sqlalchemy import and_, func, not_, or_, select

from app.db.session import AsyncSessionLocal
from app.models.document import Chunk, Document
from app.services.ai import registry
from app.services.ai.types import ProviderError
from app.services.embedding.embedding_service import chunk_embedding_text_for, embedding_service

MAX_ATTEMPTS = 6


@dataclass
class Report:
    candidates: int = 0
    embedded: int = 0
    batches: int = 0
    retries: int = 0
    seconds: float = 0.0
    failed_documents: set[str] = field(default_factory=set)


def _stale_filter(force_all: bool):
    """Chunks whose vector is missing or from another model space."""
    if force_all:
        return Chunk.id.isnot(None)
    current = and_(
        Chunk.embedding.isnot(None),
        Chunk.embedding_provider == embedding_service.provider,
        Chunk.embedding_model == embedding_service.model_name,
        Chunk.embedding_dimensions == embedding_service.dimensions,
    )
    return or_(Chunk.embedding_provider.is_(None), not_(current))


def _scope(query, organization: Optional[UUID], document: Optional[UUID]):
    query = query.join(Document, Document.id == Chunk.document_id).where(Document.status == "completed")
    if organization:
        query = query.where(Document.organization_id == organization)
    if document:
        query = query.where(Document.id == document)
    return query


async def _embed_with_retry(texts: list[str], report: Report) -> list[list[float]]:
    client = registry.embedding_client()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return await client.embed(texts, task="document", timeout=120.0)
        except ProviderError as exc:
            if exc.billing:
                raise SystemExit(
                    f"{embedding_service.provider}:{embedding_service.model_name} reports exhausted "
                    "credits or quota. Top up, then re-run: finished batches are kept."
                ) from exc
            if not exc.retryable or attempt == MAX_ATTEMPTS:
                raise
            wait = exc.retry_after or min(60.0, 2.0 ** attempt)
            report.retries += 1
            logger.warning(f"Embedding provider busy (HTTP {exc.status}); retrying in {wait:.0f}s")
            await asyncio.sleep(wait)
    raise AssertionError("unreachable")


async def reembed(
    *,
    organization: Optional[UUID] = None,
    document: Optional[UUID] = None,
    force_all: bool = False,
    batch_size: int = 64,
    dry_run: bool = False,
) -> Report:
    if not embedding_service.configured:
        raise SystemExit("No embedding model configured (EMBEDDING_PROVIDER / EMBEDDING_MODEL).")
    report = Report()
    started = time.monotonic()
    stale = _stale_filter(force_all)

    async with AsyncSessionLocal() as db:
        count_query = _scope(select(func.count(Chunk.id)), organization, document).where(stale)
        report.candidates = (await db.execute(count_query)).scalar_one()
        target = f"{embedding_service.provider}:{embedding_service.model_name} ({embedding_service.dimensions}-d)"
        logger.info(f"{report.candidates} chunks to embed with {target}")
        if dry_run or not report.candidates:
            report.seconds = time.monotonic() - started
            return report

        last_id: Optional[UUID] = None
        while True:
            # Keyset paging by id: rows updated in a batch drop out of the
            # stale filter, so paging by offset would skip chunks.
            page = _scope(select(Chunk, Document.filename), organization, document).where(stale)
            if last_id is not None:
                page = page.where(Chunk.id > last_id)
            rows = (await db.execute(page.order_by(Chunk.id).limit(batch_size))).all()
            if not rows:
                break
            last_id = rows[-1][0].id
            texts = [chunk_embedding_text_for(chunk, filename) for chunk, filename in rows]
            try:
                vectors = await _embed_with_retry(texts, report)
            except ProviderError as exc:
                ids = {str(chunk.document_id) for chunk, _ in rows}
                report.failed_documents.update(ids)
                logger.error(f"Batch failed permanently (HTTP {exc.status}); skipping {len(rows)} chunks")
                continue
            for (chunk, _), vector in zip(rows, vectors, strict=True):
                chunk.embedding = vector
                chunk.embedding_provider = embedding_service.provider
                chunk.embedding_model = embedding_service.model_name
                chunk.embedding_dimensions = embedding_service.dimensions
                chunk.embedding_task = "retrieval_document"
            await db.commit()
            report.batches += 1
            report.embedded += len(rows)
            logger.info(f"  {report.embedded}/{report.candidates} embedded")

    report.seconds = time.monotonic() - started
    return report


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--organization", type=UUID, help="Only this organization's documents")
    parser.add_argument("--document", type=UUID, help="Only this document")
    parser.add_argument("--all", action="store_true", help="Re-embed even chunks already on the current model")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--dry-run", action="store_true", help="Count what would be embedded, change nothing")
    args = parser.parse_args(argv)
    report = asyncio.run(reembed(
        organization=args.organization, document=args.document, force_all=args.all,
        batch_size=max(1, args.batch_size), dry_run=args.dry_run,
    ))
    verb = "would embed" if args.dry_run else "embedded"
    print(f"{verb} {report.embedded if not args.dry_run else report.candidates} of {report.candidates} chunks "
          f"in {report.batches} batches, {report.retries} retries, {report.seconds:.1f}s")
    if report.failed_documents:
        print(f"Failed documents (re-run to retry): {', '.join(sorted(report.failed_documents))}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
