"""
Document management API endpoints.
Handles upload, processing, listing, and deletion of documents.
"""
from typing import List, Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from pydantic import BaseModel, Field
from datetime import datetime
from loguru import logger

from app.db.session import get_db
from app.models.document import Document, Chunk
from app.utils.file_utils import FileValidator, file_handler
from app.services.document_processing.processor import document_processor


router = APIRouter()


# Pydantic Models for Request/Response
class DocumentUploadResponse(BaseModel):
    """Response model for document upload."""
    document_id: str
    filename: str
    status: str
    message: str
    file_size_mb: float


class DocumentListItem(BaseModel):
    """Individual document in list response."""
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
    """Response model for document listing."""
    total: int
    documents: List[DocumentListItem]


class ProcessingStatusResponse(BaseModel):
    """Response model for processing status."""
    document_id: str
    filename: str
    status: str
    total_pages: Optional[int]
    total_chunks: Optional[int]
    upload_date: Optional[str]
    processed_date: Optional[str]
    error: Optional[str]


# Temporary: Mock user authentication until we implement auth
async def get_current_user_id() -> UUID:
    """Temporary function returning mock user ID."""
    # TODO: Replace with actual JWT auth
    return UUID("00000000-0000-0000-0000-000000000001")


@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Query(..., description="Document type: finance, hrms, policy, etc."),
    department: Optional[str] = Query(None, description="Department name"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    Upload a new document for processing.
    
    Flow:
    1. Validate file
    2. Save to disk
    3. Create database record
    4. Queue background processing
    """
    logger.info(f"Document upload request: {file.filename} (type: {doc_type})")
    
    # Step 1: Validate file
    is_valid, error_message = FileValidator.validate_file(file)
    if not is_valid:
        logger.warning(f"File validation failed: {error_message}")
        raise HTTPException(status_code=400, detail=error_message)
    
    # Step 2: Check for duplicate (by hash)
    try:
        # Save file temporarily to calculate hash
        file_path, file_hash, file_size = await file_handler.save_upload_file(
            file, 
            str(user_id)
        )
        
        # Check if file already exists
        result = await db.execute(
            select(Document).where(Document.file_hash == file_hash)
        )
        existing_doc = result.scalar_one_or_none()
        
        if existing_doc:
            logger.info(f"Duplicate document detected: {file_hash}")
            # Delete the newly uploaded file
            file_handler.delete_file(file_path)
            
            return DocumentUploadResponse(
                document_id=str(existing_doc.id),
                filename=existing_doc.filename,
                status="duplicate",
                message="This document already exists in the system",
                file_size_mb=round(file_size / (1024 * 1024), 2)
            )
        
    except Exception as e:
        logger.error(f"Error during file upload: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    
    # Step 3: Create database record
    try:
        document = Document(
            filename=file.filename,
            original_filename=file.filename,
            file_path=str(file_path),
            file_size_bytes=file_size,
            file_hash=file_hash,
            doc_type=doc_type,
            department=department,
            status="pending",
            uploaded_by=user_id,
            metadata={
                "mime_type": FileValidator.get_mime_type(file.filename),
                "upload_source": "api"
            }
        )
        
        db.add(document)
        await db.commit()
        await db.refresh(document)
        
        logger.info(f"✅ Document record created: {document.id}")
        
    except Exception as e:
        logger.error(f"Database error: {str(e)}")
        # Clean up uploaded file
        file_handler.delete_file(file_path)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    # Step 4: Queue background processing
    background_tasks.add_task(
        process_document_background,
        document.id,
        file_path,
        db
    )
    
    return DocumentUploadResponse(
        document_id=str(document.id),
        filename=document.filename,
        status="processing",
        message="Document uploaded successfully and queued for processing",
        file_size_mb=round(file_size / (1024 * 1024), 2)
    )


async def process_document_background(
    document_id: UUID,
    file_path,
    db: AsyncSession
):
    """
    Background task for document processing.
    Runs asynchronously after upload.
    """
    try:
        logger.info(f"Starting background processing for {document_id}")
        
        # Process document
        stats = await document_processor.process_document(
            document_id,
            file_path,
            db
        )
        
        logger.info(f"✅ Background processing completed: {stats}")
        
    except Exception as e:
        logger.error(f"❌ Background processing failed: {str(e)}")


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    doc_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    List all documents with optional filtering.
    
    Query parameters:
    - skip: Pagination offset
    - limit: Number of documents to return
    - doc_type: Filter by document type
    - status: Filter by processing status
    - department: Filter by department
    """
    # Build query
    query = select(Document).where(Document.uploaded_by == user_id)
    
    if doc_type:
        query = query.where(Document.doc_type == doc_type)
    
    if status:
        query = query.where(Document.status == status)
    
    if department:
        query = query.where(Document.department == department)
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Get documents
    query = query.order_by(Document.upload_date.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    documents = result.scalars().all()
    
    # Convert to response model
    document_list = [
        DocumentListItem(
            id=str(doc.id),
            filename=doc.filename,
            doc_type=doc.doc_type,
            department=doc.department,
            total_pages=doc.total_pages or 0,
            total_chunks=doc.total_chunks or 0,
            status=doc.status,
            upload_date=doc.upload_date.isoformat(),
            processed_date=doc.processed_date.isoformat() if doc.processed_date else None
        )
        for doc in documents
    ]
    
    return DocumentListResponse(
        total=total,
        documents=document_list
    )


@router.get("/documents/{document_id}/status", response_model=ProcessingStatusResponse)
async def get_document_status(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    Get processing status of a specific document.
    """
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.uploaded_by == user_id
        )
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return ProcessingStatusResponse(
        document_id=str(document.id),
        filename=document.filename,
        status=document.status,
        total_pages=document.total_pages,
        total_chunks=document.total_chunks,
        upload_date=document.upload_date.isoformat() if document.upload_date else None,
        processed_date=document.processed_date.isoformat() if document.processed_date else None,
        error=document.processing_error
    )


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    Delete a document and all its chunks.
    Also removes the file from disk.
    """
    # Get document
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.uploaded_by == user_id
        )
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Delete file from disk
    from pathlib import Path
    file_path = Path(document.file_path)
    file_handler.delete_file(file_path)
    
    # Delete chunks (cascade should handle this, but explicit is better)
    await db.execute(
        delete(Chunk).where(Chunk.document_id == document_id)
    )
    
    # Delete document record
    await db.delete(document)
    await db.commit()
    
    logger.info(f"✅ Document deleted: {document_id}")
    
    return {
        "message": "Document deleted successfully",
        "document_id": str(document_id)
    }


@router.post("/documents/{document_id}/reprocess")
async def reprocess_document(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    Reprocess a document (useful if chunking/embedding parameters changed).
    """
    # Verify document exists and belongs to user
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.uploaded_by == user_id
        )
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Queue reprocessing
    from pathlib import Path
    background_tasks.add_task(
        document_processor.reprocess_document,
        document_id,
        db
    )
    
    return {
        "message": "Document reprocessing queued",
        "document_id": str(document_id)
    }


__all__ = ['router']