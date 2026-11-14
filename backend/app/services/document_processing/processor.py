"""
Document processing orchestrator.
Coordinates extraction, chunking, embedding, and storage operations.
"""
from pathlib import Path
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal
from sqlalchemy import select
from loguru import logger

from app.models.document import Document, Chunk as ChunkModel
from app.services.document_processing.text_extractor import ExtractionError, text_extractor
from app.services.document_processing.chunker import semantic_chunker
from app.services.embedding.embedding_service import embedding_service
from app.services.generation.title_generator import title_generator
from app.services.document_processing.identity import stable_chunk_id


GENERIC_PROCESSING_ERROR = "Processing failed. Try again later or contact your administrator."


def user_facing_error(exc: Exception) -> str:
    """What the uploader sees. File problems explain themselves; anything
    else is an internal failure whose details stay in the server log."""
    if isinstance(exc, ExtractionError):
        return str(exc)[:500]
    return GENERIC_PROCESSING_ERROR


class DocumentProcessor:
    """
    Orchestrates the complete document processing pipeline.
    Handles extraction → chunking → embedding → storage.
    """
    
    async def process_document(
        self,
        document_id: UUID,
        file_path: Path,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Process a document through the complete pipeline.
        
        Args:
            document_id: UUID of document record
            file_path: Path to uploaded file
            db: Database session
            
        Returns:
            Processing statistics
        """
        start_time = datetime.now(timezone.utc)
        
        try:
            # Update status to processing
            document = await self._get_document(document_id, db)
            document.status = "processing"
            await db.commit()
            
            logger.info(f"Starting processing for document {document_id}")
            
            # Step 1: Extract text and structure
            logger.info("Step 1: Extracting document structure")
            doc_structure = text_extractor.extract_document(file_path)

            # Update document metadata
            document.total_pages = doc_structure.total_pages
            document.has_tables = doc_structure.has_tables
            document.has_images = doc_structure.has_images

            # Properly update JSONB metadata field
            current_metadata = document.doc_metadata or {}
            updated_metadata = {**current_metadata, **doc_structure.metadata}
            document.doc_metadata = updated_metadata
            
            # Step 2: Chunk the document
            logger.info("Step 2: Chunking document")
            chunks = semantic_chunker.chunk_document(
                doc_structure,
                document_title=document.filename
            )
            
            document.total_chunks = len(chunks)
            
            # Step 3: Generate embeddings
            logger.info("Step 3: Generating embeddings")
            chunks_with_embeddings = await embedding_service.embed_chunks_with_context(
                [chunk.to_dict() for chunk in chunks],
                document_title=document.filename
            )
            
            # Step 4: Store chunks in database WITH TITLE GENERATION
            logger.info("Step 4: Storing chunks with embeddings and generating titles")
            await self._store_chunks(
                document_id,
                chunks_with_embeddings,
                db
            )
            
            # Update document status
            document.status = "completed"
            document.processed_date = datetime.now(timezone.utc)
            await db.commit()
            
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            stats = {
                "document_id": str(document_id),
                "total_pages": doc_structure.total_pages,
                "total_chunks": len(chunks),
                "has_tables": doc_structure.has_tables,
                "processing_time_seconds": processing_time,
                "status": "success"
            }
            
            logger.info(f"✅ Document processing completed: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"❌ Error processing document {document_id}: {str(e)}")
            
            # Update document with error
            try:
                await db.rollback()
                document = await self._get_document(document_id, db)
                document.status = "failed"
                document.processing_error = user_facing_error(e)
                await db.commit()
            except Exception as db_error:
                logger.error(f"Failed to update error status: {str(db_error)}")
            
            raise
    
    async def _get_document(self, document_id: UUID, db: AsyncSession) -> Document:
        """Fetch document by ID."""
        result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()
        
        if not document:
            raise ValueError(f"Document {document_id} not found")
        
        return document
    
    async def _build_chunk_models(
        self,
        document_id: UUID,
        chunks: list[Dict[str, Any]],
    ) -> list[ChunkModel]:
        """
        Build Chunk ORM models without writing them to the database.

        Used by reprocessing so all extraction, chunking, embedding,
        and title-generation work completes before existing chunks
        are replaced.
        """
        chunk_models = []

        for chunk_data in chunks:
            title = None

            try:
                title = await title_generator.generate_title(
                    content=chunk_data["content"],
                    chunk_type=chunk_data["chunk_type"],
                    section_title=chunk_data.get("section_title"),
                    page_numbers=chunk_data.get("page_numbers"),
                    chunk_index=chunk_data["chunk_index"],
                )

                logger.debug(
                    f"Generated title for chunk "
                    f"{chunk_data['chunk_index']}: '{title}'"
                )

            except Exception as e:
                logger.warning(
                    f"Title generation failed for chunk "
                    f"{chunk_data['chunk_index']}: {e}"
                )

            chunk_models.append(
                ChunkModel(
                    id=stable_chunk_id(
                        document_id=document_id,
                        chunk_index=chunk_data["chunk_index"],
                        content=chunk_data["content"],
                    ),
                    document_id=document_id,
                    chunk_index=chunk_data["chunk_index"],
                    content=chunk_data["content"],
                    content_length=len(chunk_data["content"]),
                    token_count=chunk_data["token_count"],
                    chunk_type=chunk_data["chunk_type"],
                    page_numbers=chunk_data["page_numbers"],
                    section_title=chunk_data.get("section_title"),
                    title=title,
                    embedding=chunk_data["embedding"],
                    embedding_provider=embedding_service.provider,
                    embedding_model=embedding_service.model_name,
                    embedding_dimensions=embedding_service.dimensions,
                    embedding_task="retrieval_document",
                    chunk_metadata=chunk_data.get("metadata", {}),
                )
            )

        return chunk_models
    
    async def _store_chunks(
        self,
        document_id: UUID,
        chunks: list[Dict[str, Any]],
        db: AsyncSession
    ) -> None:
        """
        Store chunks with embeddings and AI-generated titles in database.
        
        Args:
            document_id: Parent document ID
            chunks: List of chunk dictionaries with embeddings
            db: Database session
        """
        chunk_models = []
        
        for chunk_data in chunks:
            # Generate AI title for this chunk
            title = None
            try:
                title = await title_generator.generate_title(
                    content=chunk_data['content'],
                    chunk_type=chunk_data['chunk_type'],
                    section_title=chunk_data.get('section_title'),
                    page_numbers=chunk_data.get('page_numbers'),
                    chunk_index=chunk_data['chunk_index']
                )
                logger.debug(f"Generated title for chunk {chunk_data['chunk_index']}: '{title}'")
            except Exception as e:
                logger.warning(f"Title generation failed for chunk {chunk_data['chunk_index']}: {e}")
                title = None  # Will use fallback in frontend
            
            chunk_model = ChunkModel(
                id=stable_chunk_id(
                    document_id=document_id,
                    chunk_index=chunk_data['chunk_index'],
                    content=chunk_data['content'],
                ),
                document_id=document_id,
                chunk_index=chunk_data['chunk_index'],
                content=chunk_data['content'],
                content_length=len(chunk_data['content']),
                token_count=chunk_data['token_count'],
                chunk_type=chunk_data['chunk_type'],
                page_numbers=chunk_data['page_numbers'],
                section_title=chunk_data.get('section_title'),
                title=title,
                embedding=chunk_data['embedding'],
                embedding_provider=embedding_service.provider,
                embedding_model=embedding_service.model_name,
                embedding_dimensions=embedding_service.dimensions,
                embedding_task="retrieval_document",
                chunk_metadata=chunk_data.get('metadata', {})
            )
            
            chunk_models.append(chunk_model)
        
        # Bulk insert chunks
        db.add_all(chunk_models)
        await db.commit()
        
        titles_generated = sum(1 for c in chunk_models if c.title)
        logger.info(f"Stored {len(chunk_models)} chunks for document {document_id}, generated {titles_generated} titles")
    
    async def reprocess_document(
        self,
        document_id: UUID
    ) -> Dict[str, Any]:
        """
        Reprocess an existing document safely.

        The existing chunks remain untouched while extraction,
        chunking, embedding, and title generation are performed.

        Existing chunks are replaced only after the complete new
        chunk set has been successfully prepared.
        """
        async with AsyncSessionLocal() as db:
            try:
                start_time = datetime.now(timezone.utc)
                document = await self._get_document(document_id, db)
                file_path = Path(document.file_path)

                logger.info(
                    f"Starting safe reprocessing for document "
                    f"{document_id}: {document.filename}"
                )

                # Step 1: Extract
                logger.info("Step 1: Extracting document structure")
                doc_structure = text_extractor.extract_document(file_path)
                
                # Step 2: Chunk using corrected page provenance
                logger.info("Step 2: Chunking document")
                chunks = semantic_chunker.chunk_document(
                    doc_structure,
                    document_title=document.filename
                )

                logger.info(
                    f"Generated {len(chunks)} chunks for "
                    f"{document.filename}"
                )

                # Step 3: Generate embeddings
                logger.info("Step 3: Generating embeddings")
                chunks_with_embeddings = (
                    await embedding_service.embed_chunks_with_context(
                        [chunk.to_dict() for chunk in chunks],
                        document_title=document.filename
                    )
                )

                # Step 4: Build ORM models in memory
                logger.info(
                    "Step 4: Preparing new chunks and generating titles"
                )

                new_chunk_models = await self._build_chunk_models(
                    document_id=document_id,
                    chunks=chunks_with_embeddings,
                )

                logger.info(
                    f"Prepared {len(new_chunk_models)} new chunks "
                    f"for {document.filename}"
                )

                # Step 5: Only now replace the existing chunks
                logger.info(
                    f"Replacing existing chunks for document "
                    f"{document_id}"
                )

                from sqlalchemy import delete

                await db.execute(
                    delete(ChunkModel).where(
                        ChunkModel.document_id == document_id
                    )
                )

                db.add_all(new_chunk_models)

                # Update document metadata/status
                document.total_pages = doc_structure.total_pages
                document.total_chunks = len(chunks)
                document.has_tables = doc_structure.has_tables
                document.has_images = doc_structure.has_images

                current_metadata = document.doc_metadata or {}
                document.doc_metadata = {
                    **current_metadata,
                    **doc_structure.metadata,
                }

                document.status = "completed"
                document.processing_error = None
                document.processed_date = datetime.now(timezone.utc)

                # Step 6: Single commit for replacement
                await db.commit()

                processing_time = (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds()

                titles_generated = sum(
                    1 for chunk in new_chunk_models
                    if chunk.title
                )

                stats = {
                    "document_id": str(document_id),
                    "filename": document.filename,
                    "total_pages": doc_structure.total_pages,
                    "total_chunks": len(chunks),
                    "titles_generated": titles_generated,
                    "has_tables": doc_structure.has_tables,
                    "processing_time_seconds": processing_time,
                    "status": "success",
                }

                logger.info(
                    f"✅ Safe document reprocessing completed: {stats}"
                )

                return stats

            except Exception:
                await db.rollback()

                logger.exception(
                    f"Failed to safely reprocess document {document_id}. "
                    "Existing chunks were preserved unless replacement "
                    "transaction had already begun."
                )

                raise

            finally:
                await db.close()
    
    async def get_processing_status(
        self,
        document_id: UUID,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Get current processing status of a document.
        
        Args:
            document_id: Document ID
            db: Database session
            
        Returns:
            Status information
        """
        document = await self._get_document(document_id, db)
        
        return {
            "document_id": str(document.id),
            "filename": document.filename,
            "status": document.status,
            "total_pages": document.total_pages,
            "total_chunks": document.total_chunks,
            "upload_date": document.upload_date.isoformat() if document.upload_date else None,
            "processed_date": document.processed_date.isoformat() if document.processed_date else None,
            "error": document.processing_error
        }


# Global instance
document_processor = DocumentProcessor()

__all__ = ['DocumentProcessor', 'document_processor']
