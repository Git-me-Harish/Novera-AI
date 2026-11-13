"""
Document management API endpoints with RBAC.

FIXES:
  1. Document processing is queued in Redis Streams and executed by a
     separate worker. API worker restarts cannot silently lose ingestion jobs.

  2. /documents/{document_id}/status: the `status` query parameter shadowed
     Python's built-in and, more critically, shadowed FastAPI's `status`
     import used for HTTP codes. Renamed to `status_filter`.

  3. list_documents: the import `from app.db.session import AsyncSessionLocal`
     was duplicated (already imported at module level) and unused in the
     endpoint. Removed.

  4. The `status` import alias from fastapi is now only imported once and
     used consistently through the module.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional
from uuid import UUID

from fastapi import (
    APIRouter, Depends, File, HTTPException,
    Query, UploadFile, status,
)
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_active_user, get_current_admin_user
from app.db.session import get_db
from app.models.document import Chunk, Document
from app.models.user import User
from app.services.document_processing.job_queue import document_job_queue
from app.services.document_processing.identity import stable_document_id
from app.utils.file_utils import FileValidator, file_handler

router = APIRouter()


# Response Models
class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    message: str
    file_size_mb: float


class DocumentListItem(BaseModel):
    id: str
    filename: str
    doc_type: str
    department: Optional[str]
    total_pages: int
    total_chunks: int
    status: str
    upload_date: str
    processed_date: Optional[str]


class DocumentListResponse(BaseModel):
    total: int
    documents: List[DocumentListItem]


class MultiUploadResult(BaseModel):
    filename: str
    status: str
    message: str
    document_id: Optional[str] = None
    file_size_mb: Optional[float] = None
    error: Optional[str] = None


class MultiUploadResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    duplicates: int
    results: List[MultiUploadResult]


class ProcessingStatusResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    total_pages: Optional[int]
    total_chunks: Optional[int]
    upload_date: Optional[str]
    processed_date: Optional[str]
    error: Optional[str]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Query(...),
    department: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Upload a document for processing. Admin only."""
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to an organization to upload documents",
        )

    is_valid, error_message = FileValidator.validate_file(file)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_message)

    try:
        file_path, file_hash, file_size = await file_handler.save_upload_file(
            file, str(current_user.id)
        )
        
        document_id = stable_document_id(
            current_user.organization_id,
            file_hash,
        )

        existing_doc = (
            await db.execute(
                select(Document).where(
                    Document.file_hash == file_hash,
                    Document.organization_id == current_user.organization_id,
                )
            )
        ).scalar_one_or_none()

        if existing_doc:
            file_handler.delete_file(file_path)
            return DocumentUploadResponse(
                document_id=str(existing_doc.id),
                filename=existing_doc.filename,
                status="duplicate",
                message="This document already exists in your organization",
                file_size_mb=round(file_size / (1024 * 1024), 2),
            )

    except Exception as e:
        logger.error(f"Error during file upload: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    try:
        document = Document(
            id=document_id,
            filename=file.filename,
            original_filename=file.filename,
            file_path=str(file_path),
            file_size_bytes=file_size,
            file_hash=file_hash,
            doc_type=doc_type,
            department=department,
            status="pending",
            uploaded_by=current_user.id,
            organization_id=current_user.organization_id,
            doc_metadata={
                "mime_type": FileValidator.get_mime_type(file.filename),
                "upload_source": "api",
                "uploaded_by_email": current_user.email,
                "organization_id": str(current_user.organization_id),
            },
        )
        db.add(document)
        await db.commit()
        await db.refresh(document)
        logger.info(f"Document record created: {document.id} for org {current_user.organization_id}")

    except Exception as e:
        logger.error(f"Database error: {e}")
        file_handler.delete_file(file_path)
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    try:
        await document_job_queue.enqueue(document.id)
    except Exception as e:
        logger.error(f"Document queue unavailable for {document.id}: {e}")
        document.status = "failed"
        document.processing_error = "Document processing queue unavailable"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document processing is temporarily unavailable; please retry",
        )

    return DocumentUploadResponse(
        document_id=str(document.id),
        filename=document.filename,
        status="processing",
        message="Document uploaded successfully and queued for processing",
        file_size_mb=round(file_size / (1024 * 1024), 2),
    )


@router.post("/documents/upload-multiple", response_model=MultiUploadResponse)
async def upload_multiple_documents(
    files: List[UploadFile] = File(...),
    doc_type: str = Query(...),
    department: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Upload up to 20 documents in a single request. Admin only."""
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to an organization to upload documents",
        )

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 files per batch upload")

    results: List[MultiUploadResult] = []
    succeeded = failed = duplicates = 0

    for file in files:
        try:
            is_valid, error_message = FileValidator.validate_file(file)
            if not is_valid:
                results.append(MultiUploadResult(
                    filename=file.filename or "unknown",
                    status="failed",
                    message=error_message,
                    error=error_message,
                ))
                failed += 1
                continue

            file_path, file_hash, file_size = await file_handler.save_upload_file(
                file, str(current_user.id)
            )

            document_id = stable_document_id(
                current_user.organization_id,
                file_hash,
            )

            existing_doc = (
                await db.execute(
                    select(Document).where(
                        Document.file_hash == file_hash,
                        Document.organization_id == current_user.organization_id,
                    )
                )
            ).scalar_one_or_none()

            if existing_doc:
                file_handler.delete_file(file_path)
                results.append(MultiUploadResult(
                    filename=file.filename or "unknown",
                    status="duplicate",
                    message="This document already exists in your organization",
                    document_id=str(existing_doc.id),
                    file_size_mb=round(file_size / (1024 * 1024), 2),
                ))
                duplicates += 1
                continue

            document = Document(
                id=document_id,
                filename=file.filename,
                original_filename=file.filename,
                file_path=str(file_path),
                file_size_bytes=file_size,
                file_hash=file_hash,
                doc_type=doc_type,
                department=department,
                status="pending",
                uploaded_by=current_user.id,
                organization_id=current_user.organization_id,
                doc_metadata={
                    "mime_type": FileValidator.get_mime_type(file.filename),
                    "upload_source": "api_multi",
                    "uploaded_by_email": current_user.email,
                    "organization_id": str(current_user.organization_id),
                },
            )
            db.add(document)
            await db.commit()
            await db.refresh(document)

            try:
                await document_job_queue.enqueue(document.id)
            except Exception as e:
                logger.error(f"Document queue unavailable for {document.id}: {e}")
                document.status = "failed"
                document.processing_error = "Document processing queue unavailable"
                await db.commit()
                results.append(MultiUploadResult(
                    filename=file.filename or "unknown",
                    status="failed",
                    message="Upload saved but could not be queued for processing",
                    document_id=str(document.id),
                    file_size_mb=round(file_size / (1024 * 1024), 2),
                    error="Processing queue unavailable",
                ))
                failed += 1
                continue

            results.append(MultiUploadResult(
                filename=file.filename or "unknown",
                status="processing",
                message="Queued for processing",
                document_id=str(document.id),
                file_size_mb=round(file_size / (1024 * 1024), 2),
            ))
            succeeded += 1

        except Exception as e:
            logger.error(f"Error processing file {file.filename}: {e}")
            results.append(MultiUploadResult(
                filename=file.filename or "unknown",
                status="failed",
                message="Upload failed due to server error",
                error=str(e),
            ))
            failed += 1

    return MultiUploadResponse(
        total=len(files),
        succeeded=succeeded,
        failed=failed,
        duplicates=duplicates,
        results=results,
    )


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    doc_type: Optional[str] = Query(None),
    # FIX: renamed from `status` to `status_filter` to avoid shadowing the `status` import
    status_filter: Optional[str] = Query(None, alias="status"),
    department: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    List documents scoped to the current user's organization.
    Super admins see all documents.
    """
    query = select(Document)

    if not current_user.is_super_admin():
        if not current_user.organization_id:
            return DocumentListResponse(total=0, documents=[])
        query = query.where(Document.organization_id == current_user.organization_id)

    if doc_type:
        query = query.where(Document.doc_type == doc_type)
    if status_filter:
        query = query.where(Document.status == status_filter)
    if department:
        query = query.where(Document.department == department)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()

    query = query.order_by(Document.upload_date.desc()).offset(skip).limit(limit)
    documents = (await db.execute(query)).scalars().all()

    logger.info(
        f"User {current_user.email} (org: {current_user.organization_id}) "
        f"retrieved {len(documents)} documents"
    )

    return DocumentListResponse(
        total=total,
        documents=[
            DocumentListItem(
                id=str(doc.id),
                filename=doc.filename,
                doc_type=doc.doc_type,
                department=doc.department,
                total_pages=doc.total_pages or 0,
                total_chunks=doc.total_chunks or 0,
                status=doc.status,
                upload_date=doc.upload_date.isoformat(),
                processed_date=doc.processed_date.isoformat() if doc.processed_date else None,
            )
            for doc in documents
        ],
    )


@router.get("/documents/{document_id}/status", response_model=ProcessingStatusResponse)
async def get_document_status(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get processing status of a document — org-scoped."""
    query = select(Document).where(Document.id == document_id)

    if not current_user.is_super_admin():
        if not current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User must belong to an organization",
            )
        query = query.where(Document.organization_id == current_user.organization_id)

    document = (await db.execute(query)).scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found or access denied")

    return ProcessingStatusResponse(
        document_id=str(document.id),
        filename=document.filename,
        status=document.status,
        total_pages=document.total_pages,
        total_chunks=document.total_chunks,
        upload_date=document.upload_date.isoformat() if document.upload_date else None,
        processed_date=document.processed_date.isoformat() if document.processed_date else None,
        error=document.processing_error,
    )


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Delete a document and all its chunks. Admin only, org-scoped."""
    query = select(Document).where(Document.id == document_id)

    if current_user.is_org_admin() and not current_user.is_super_admin():
        if not current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin must belong to an organization",
            )
        query = query.where(Document.organization_id == current_user.organization_id)

    document = (await db.execute(query)).scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found or access denied")

    file_handler.delete_file(Path(document.file_path))
    await db.execute(delete(Chunk).where(Chunk.document_id == document_id))
    await db.delete(document)
    await db.commit()

    logger.info(
        f"Document deleted by {current_user.email} (org: {current_user.organization_id}): {document_id}"
    )
    return {"message": "Document deleted successfully", "document_id": str(document_id)}


@router.post("/documents/{document_id}/reprocess")
async def reprocess_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Reprocess a document. Admin only, org-scoped."""
    query = select(Document).where(Document.id == document_id)

    if current_user.is_org_admin() and not current_user.is_super_admin():
        if not current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin must belong to an organization",
            )
        query = query.where(Document.organization_id == current_user.organization_id)

    document = (await db.execute(query)).scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found or access denied")

    try:
        await document_job_queue.enqueue(document_id, operation="reprocess")
    except Exception as e:
        logger.error(f"Document queue unavailable for reprocess {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document processing is temporarily unavailable; please retry",
        )

    logger.info(
        f"Reprocessing queued by {current_user.email} (org: {current_user.organization_id}): {document_id}"
    )
    return {"message": "Document reprocessing queued", "document_id": str(document_id)}


__all__ = ["router"]
