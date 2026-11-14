"""
Document editor API endpoints.
Handles chunk viewing, editing, and document preview.
Admin-only for editing, read-only for regular users.
"""
from pathlib import Path
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, field_validator
from loguru import logger

from app.db.session import get_db
from app.models.user import User
from app.api.dependencies.auth import get_current_active_user, get_current_admin_user
from app.services.document_editing.chunk_editor import chunk_editor_service
from app.services.document_editing.document_viewer import document_viewer_service
from app.services.generation.title_generator import title_generator
from app.services.tenancy import audit
from app.services.tenancy.audit import Action
from app.models.document import Chunk as ChunkModel, Document


router = APIRouter()


async def _assert_chunk_access(chunk_id: UUID, db: AsyncSession, user: User) -> None:
    """Fail closed before any chunk read or mutation."""
    if not user.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not assigned to an organization")
    result = await db.execute(
        select(ChunkModel.id)
        .join(Document, ChunkModel.document_id == Document.id)
        .where(
            ChunkModel.id == chunk_id,
            Document.organization_id == user.organization_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found")


# Request/Response Models
class ChunkEditRequest(BaseModel):
    """Request to edit a chunk."""
    chunk_id: str
    new_content: str = Field(..., min_length=10, max_length=10000)
    metadata: Optional[dict] = None


class BatchChunkEditRequest(BaseModel):
    """Request to edit multiple chunks."""
    edits: List[dict] = Field(..., min_items=1, max_items=50)


class ChunkResponse(BaseModel):
    """Single chunk response."""
    id: str
    document_id: str
    chunk_index: int
    content: str
    chunk_type: str
    page_numbers: List[int]
    section_title: Optional[str]
    token_count: int
    title: Optional[str] = None
    is_edited: bool
    edited_at: Optional[str]
    edited_by: Optional[str]
    edit_count: int
    metadata: dict


class DocumentInfoResponse(BaseModel):
    """Document information response."""
    id: str
    filename: str
    original_filename: str
    file_size_mb: float
    doc_type: str
    department: Optional[str]
    total_pages: int
    total_chunks: int
    has_tables: bool
    has_images: bool
    status: str
    upload_date: str
    processed_date: Optional[str]
    mime_type: str
    preview_type: str
    is_previewable: bool


class EditHistoryResponse(BaseModel):
    """Edit history item."""
    id: str
    edited_at: str
    edited_by: str
    edited_by_name: Optional[str] = None
    old_content: str
    new_content: str
    change_summary: Optional[str]
    metadata: dict


class DocumentMetadataUpdate(BaseModel):
    """Editable document metadata. Omitted fields are left unchanged."""
    filename: Optional[str] = Field(None, max_length=255)
    doc_type: Optional[str] = Field(None, max_length=50)
    department: Optional[str] = Field(None, max_length=100)

    @field_validator("filename")
    @classmethod
    def _safe_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if not value or any(c in value for c in ("/", "\\", "\x00")):
            raise ValueError("Name must not be empty or contain path separators")
        return value

    @field_validator("doc_type")
    @classmethod
    def _type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip().lower()
        if not value:
            raise ValueError("Document type must not be empty")
        return value

    @field_validator("department")
    @classmethod
    def _department(cls, value: Optional[str]) -> Optional[str]:
        return (value.strip() or None) if isinstance(value, str) else value


class DocumentEditStatsResponse(BaseModel):
    """Document editing statistics."""
    total_chunks: int
    edited_chunks: int
    unedited_chunks: int
    total_edits: int
    edit_percentage: float


# Endpoints

@router.get("/documents/{document_id}/info", response_model=DocumentInfoResponse)
async def get_document_info(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get document information including preview capabilities.
    Available to all authenticated users.
    """
    doc_info = await document_viewer_service.get_document_info(
        document_id, db, current_user.organization_id
    )
    
    if not doc_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    return DocumentInfoResponse(
        **doc_info,
        preview_type=document_viewer_service.get_preview_type(doc_info['filename']),
        is_previewable=document_viewer_service.is_previewable(doc_info['filename'])
    )


@router.patch("/documents/{document_id}", response_model=DocumentInfoResponse)
async def update_document_metadata(
    document_id: UUID,
    payload: DocumentMetadataUpdate,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """Rename a document or change its type/department. ADMIN ONLY.

    The name is what citations show; the stored file keeps its path and its
    original upload name (used for downloads). Retrieval reads name, type and
    department from this row, so changes apply to the next query without
    re-indexing.
    """
    if not admin.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not assigned to an organization")
    document = (
        await db.execute(
            select(Document).where(Document.id == document_id, Document.organization_id == admin.organization_id)
        )
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    changes = {}
    if payload.filename is not None:
        # The extension decides how the file is previewed; keep it.
        extension = Path(document.filename).suffix
        name = payload.filename
        if extension and not name.lower().endswith(extension.lower()):
            name = f"{name}{extension}"
        if len(name) > 255:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name is too long")
        if name != document.filename:
            changes["filename"] = {"from": document.filename, "to": name}
            document.filename = name
    if payload.doc_type is not None and payload.doc_type != document.doc_type:
        changes["doc_type"] = {"from": document.doc_type, "to": payload.doc_type}
        document.doc_type = payload.doc_type
    if "department" in payload.model_fields_set and payload.department != document.department:
        changes["department"] = {"from": document.department, "to": payload.department}
        document.department = payload.department

    if changes:
        audit.record(db, Action.DOCUMENT_UPDATED, actor=admin, target_type="document",
                     target_id=document_id, details=changes, request=http_request)
        await db.commit()

    doc_info = await document_viewer_service.get_document_info(document_id, db, admin.organization_id)
    return DocumentInfoResponse(
        **doc_info,
        preview_type=document_viewer_service.get_preview_type(doc_info['filename']),
        is_previewable=document_viewer_service.is_previewable(doc_info['filename'])
    )


@router.get("/documents/{document_id}/chunks", response_model=List[ChunkResponse])
async def get_document_chunks(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all chunks for a document.
    Available to all authenticated users (read-only for non-admins).
    """
    # Verify tenant ownership before returning chunk contents.
    doc_info = await document_viewer_service.get_document_info(
        document_id, db, current_user.organization_id
    )
    if not doc_info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    chunks = await chunk_editor_service.get_document_chunks(
        document_id,
        db,
        include_edit_info=True
    )
    
    return [ChunkResponse(**chunk) for chunk in chunks]


@router.get("/documents/{document_id}/preview/text")
async def get_text_preview(
    document_id: UUID,
    max_chars: int = 5000,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get text preview for text-based documents.
    Available to all authenticated users.
    """
    preview = await document_viewer_service.get_text_preview(
        document_id,
        db,
        max_chars=max_chars,
        organization_id=current_user.organization_id,
    )
    
    if not preview:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Preview not available for this document type"
        )
    
    return preview


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Download the original document file.
    Available to all authenticated users.
    """
    from pathlib import Path
    
    doc_info = await document_viewer_service.get_document_info(
        document_id, db, current_user.organization_id
    )
    
    if not doc_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    file_path = Path(doc_info['file_path'])
    
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file not found on disk"
        )
    
    return FileResponse(
        path=str(file_path),
        filename=doc_info['original_filename'],
        media_type=doc_info['mime_type']
    )


@router.put("/chunks/{chunk_id}/edit", response_model=ChunkResponse)
async def edit_chunk(
    chunk_id: UUID,
    request: ChunkEditRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Edit a chunk's content.
    ADMIN ONLY - automatically regenerates embedding.
    """
    await _assert_chunk_access(chunk_id, db, admin)
    success, chunk_data, error = await chunk_editor_service.edit_chunk(
        chunk_id=chunk_id,
        new_content=request.new_content,
        edited_by=admin.id,
        db=db,
        metadata=request.metadata
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error
        )
    
    await audit.record_independent(Action.CHUNK_EDITED, actor=audit.snapshot(admin), target_type="chunk",
                                   target_id=chunk_id, details={"document_id": chunk_data.get("document_id")}, request=http_request)
    
    return ChunkResponse(**chunk_data)


@router.post("/chunks/batch-edit")
async def batch_edit_chunks(
    request: BatchChunkEditRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Edit multiple chunks in batch.
    ADMIN ONLY.
    """
    for edit in request.edits:
        await _assert_chunk_access(UUID(str(edit["chunk_id"])), db, admin)
    results = await chunk_editor_service.batch_edit_chunks(
        edits=request.edits,
        edited_by=admin.id,
        db=db
    )
    
    logger.info(f"Admin {admin.email} batch edited {results['successful']} chunks")
    
    return results


@router.post("/chunks/{chunk_id}/revert")
async def revert_chunk(
    chunk_id: UUID,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Revert chunk to its original content.
    ADMIN ONLY.
    """
    await _assert_chunk_access(chunk_id, db, admin)
    success, error = await chunk_editor_service.revert_chunk(chunk_id, db)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error
        )
    
    await audit.record_independent(Action.CHUNK_REVERTED, actor=audit.snapshot(admin), target_type="chunk",
                                   target_id=chunk_id, request=http_request)
    
    return {"message": "Chunk reverted successfully", "chunk_id": str(chunk_id)}


@router.delete("/chunks/{chunk_id}")
async def delete_chunk(
    chunk_id: UUID,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Delete a chunk.
    ADMIN ONLY - use with caution.
    """
    await _assert_chunk_access(chunk_id, db, admin)
    success, error = await chunk_editor_service.delete_chunk(chunk_id, db)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error
        )
    
    await audit.record_independent(Action.CHUNK_DELETED, actor=audit.snapshot(admin), target_type="chunk",
                                   target_id=chunk_id, request=http_request)
    
    return {"message": "Chunk deleted successfully", "chunk_id": str(chunk_id)}


@router.get("/chunks/{chunk_id}/history", response_model=List[EditHistoryResponse])
async def get_chunk_history(
    chunk_id: UUID,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get edit history for a chunk.
    Available to all authenticated users.
    """
    await _assert_chunk_access(chunk_id, db, current_user)
    history = await chunk_editor_service.get_chunk_edit_history(
        chunk_id,
        db,
        limit=limit
    )
    
    return [EditHistoryResponse(**item) for item in history]


@router.get("/documents/{document_id}/edit-stats", response_model=DocumentEditStatsResponse)
async def get_document_edit_stats(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get editing statistics for a document.
    Available to all authenticated users.
    """
    if not await document_viewer_service.get_document_info(document_id, db, current_user.organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    stats = await chunk_editor_service.get_document_edit_stats(document_id, db)
    
    return DocumentEditStatsResponse(**stats)

@router.post("/chunks/{chunk_id}/generate-title")
async def generate_chunk_title(
    chunk_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Generate/regenerate AI title for a specific chunk.
    ADMIN ONLY.
    """
    from sqlalchemy import update
    await _assert_chunk_access(chunk_id, db, admin)
    
    # Get chunk
    result = await db.execute(
        select(ChunkModel).where(ChunkModel.id == chunk_id)
    )
    chunk = result.scalar_one_or_none()
    
    if not chunk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chunk not found"
        )
    
    try:
        # Generate new title
        title = await title_generator.generate_title(
            content=chunk.content,
            chunk_type=chunk.chunk_type,
            section_title=chunk.section_title,
            page_numbers=chunk.page_numbers,
            chunk_index=chunk.chunk_index
        )
        
        # Update chunk
        await db.execute(
            update(ChunkModel)
            .where(ChunkModel.id == chunk_id)
            .values(title=title)
        )
        await db.commit()
        
        logger.info(f"Admin {admin.email} generated title for chunk {chunk_id}: '{title}'")
        
        return {
            "chunk_id": str(chunk_id),
            "title": title,
            "message": "Title generated successfully"
        }
        
    except Exception as e:
        logger.error(f"Title generation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Title generation failed: {str(e)}"
        )


@router.post("/documents/{document_id}/generate-all-titles")
async def generate_all_titles(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Generate titles for all chunks in a document.
    ADMIN ONLY - runs in background.
    """
    from sqlalchemy import update
    if not await document_viewer_service.get_document_info(document_id, db, admin.organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    
    # Get all chunks for document
    result = await db.execute(
        select(ChunkModel)
        .where(ChunkModel.document_id == document_id)
        .order_by(ChunkModel.chunk_index)
    )
    chunks = result.scalars().all()
    
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No chunks found for this document"
        )
    
    logger.info(f"Admin {admin.email} requested title generation for {len(chunks)} chunks")
    
    # Generate titles for all chunks
    success_count = 0
    failed_count = 0
    
    for chunk in chunks:
        try:
            title = await title_generator.generate_title(
                content=chunk.content,
                chunk_type=chunk.chunk_type,
                section_title=chunk.section_title,
                page_numbers=chunk.page_numbers,
                chunk_index=chunk.chunk_index
            )
            
            await db.execute(
                update(ChunkModel)
                .where(ChunkModel.id == chunk.id)
                .values(title=title)
            )
            
            success_count += 1
            
        except Exception as e:
            logger.error(f"Failed to generate title for chunk {chunk.id}: {e}")
            failed_count += 1
            continue
    
    await db.commit()
    
    logger.info(f"Generated {success_count} titles, {failed_count} failed")
    
    return {
        "document_id": str(document_id),
        "total_chunks": len(chunks),
        "success": success_count,
        "failed": failed_count,
        "message": f"Generated titles for {success_count} chunks"
    }


@router.put("/chunks/{chunk_id}/title")
async def update_chunk_title(
    chunk_id: UUID,
    title: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Manually update chunk title.
    ADMIN ONLY.
    """
    from sqlalchemy import update
    await _assert_chunk_access(chunk_id, db, admin)
    
    if len(title) > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Title too long (max 200 characters)"
        )
    
    # Update title
    result = await db.execute(
        update(ChunkModel)
        .where(ChunkModel.id == chunk_id)
        .values(title=title)
        .returning(ChunkModel.id)
    )
    
    updated = result.scalar_one_or_none()
    
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chunk not found"
        )
    
    await db.commit()
    
    logger.info(f"Admin {admin.email} manually updated title for chunk {chunk_id}")
    
    return {
        "chunk_id": str(chunk_id),
        "title": title,
        "message": "Title updated successfully"
    }


__all__ = ['router']
