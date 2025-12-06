"""
Vector similarity search using pgvector.
Implements cosine similarity search with filtering and ranking.
"""
from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from loguru import logger

from app.models.document import Chunk, Document
from app.core.config import settings


class VectorSearchService:
    """
    Service for semantic similarity search using vector embeddings.
    Leverages pgvector's cosine similarity for efficient retrieval.
    """
    
    def __init__(self):
        self.top_k = settings.retrieval_top_k
        self.similarity_threshold = settings.similarity_threshold
    
    def _safe_extract_metadata(self, metadata_obj: Any) -> dict:
        """
        Safely extract metadata from SQLAlchemy object or dict.
        
        Args:
            metadata_obj: Metadata object (could be dict, SQLAlchemy object, etc.)
            
        Returns:
            Plain Python dictionary
        """
        if metadata_obj is None:
            return {}
        
        # If already a dict, return it
        if isinstance(metadata_obj, dict):
            return metadata_obj
        
        # If it has __dict__, try to extract
        if hasattr(metadata_obj, '__dict__'):
            try:
                return {k: v for k, v in metadata_obj.__dict__.items() if not k.startswith('_')}
            except:
                pass
        
        # If it's mapping-like
        if hasattr(metadata_obj, 'keys') and hasattr(metadata_obj, '__getitem__'):
            try:
                return {k: metadata_obj[k] for k in metadata_obj.keys()}
            except:
                pass
        
        # Fallback: empty dict
        logger.warning(f"Could not extract metadata from {type(metadata_obj)}")
        return {}
    
    async def search_similar_chunks(
        self,
        query_embedding: List[float],
        db: AsyncSession,
        top_k: Optional[int] = None,
        doc_type: Optional[str] = None,
        department: Optional[str] = None,
        document_ids: Optional[List[UUID]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for chunks similar to query embedding.
        
        Args:
            query_embedding: Vector embedding of search query
            db: Database session
            top_k: Number of results (default from config)
            doc_type: Filter by document type
            department: Filter by department
            document_ids: Filter by specific documents
            
        Returns:
            List of chunk dictionaries with similarity scores
        """
        k = top_k or self.top_k
        
        logger.info(f"Vector search: top_k={k}, threshold={self.similarity_threshold}")
        
        try:
            # Build the query with vector similarity
            # Note: pgvector uses <=> for cosine distance (lower is better)
            # We convert to similarity: similarity = 1 - distance
            query = (
                select(
                    Chunk,
                    Document,
                    (1 - Chunk.embedding.cosine_distance(query_embedding)).label('similarity')
                )
                .join(Document, Chunk.document_id == Document.id)
                .where(Document.status == "completed")
            )
            
            # Apply filters
            if doc_type:
                query = query.where(Document.doc_type == doc_type)
            
            if department:
                query = query.where(Document.department == department)
            
            if document_ids:
                query = query.where(Document.id.in_(document_ids))
            
            # Order by similarity and limit
            query = (
                query
                .order_by(text('similarity DESC'))
                .limit(k * 2)  # Get extra for filtering
            )
            
            # Execute query
            result = await db.execute(query)
            rows = result.all()
            
            # Format results
            chunks = []
            for chunk, document, similarity in rows:
                # Filter by similarity threshold
                if similarity < self.similarity_threshold:
                    continue
                
                # ✅ FIXED: Safely extract metadata
                chunk_metadata = self._safe_extract_metadata(chunk.chunk_metadata)
                doc_metadata = self._safe_extract_metadata(document.doc_metadata)
                
                chunk_dict = {
                    'chunk_id': str(chunk.id),
                    'id': str(chunk.id),
                    'document_id': str(document.id),
                    'document_name': document.filename,
                    'content': chunk.content,
                    'chunk_type': chunk.chunk_type,
                    'chunk_index': chunk.chunk_index,
                    'page_numbers': chunk.page_numbers,
                    'section_title': chunk.section_title,
                    'token_count': chunk.token_count,
                    'similarity_score': float(similarity),
                    'chunk_metadata': chunk_metadata,
                    'metadata': {
                        'document_title': document.filename,
                        'doc_type': document.doc_type,
                        'department': document.department,
                        **chunk_metadata,  # Now safe to unpack
                    }
                }
                
                chunks.append(chunk_dict)
            
            logger.info(f"Vector search found {len(chunks)} chunks above threshold {self.similarity_threshold}")
            
            # Return top_k results
            return chunks[:k]
            
        except Exception as e:
            logger.error(f"Vector search failed: {str(e)}", exc_info=True)
            return []
    
    async def search_by_document(
        self,
        query_embedding: List[float],
        document_id: UUID,
        db: AsyncSession,
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Search within a specific document only.
        Useful for document-specific queries.
        """
        return await self.search_similar_chunks(
            query_embedding=query_embedding,
            db=db,
            top_k=top_k,
            document_ids=[document_id]
        )
    
    async def get_chunk_neighbors(
        self,
        chunk_id: UUID,
        db: AsyncSession,
        n_before: int = 1,
        n_after: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Get neighboring chunks for context expansion.
        
        Args:
            chunk_id: Target chunk ID
            db: Database session
            n_before: Number of chunks before
            n_after: Number of chunks after
            
        Returns:
            List of neighboring chunks in order
        """
        try:
            # Get target chunk
            result = await db.execute(
                select(Chunk, Document)
                .join(Document, Chunk.document_id == Document.id)
                .where(Chunk.id == chunk_id)
            )
            row = result.first()
            
            if not row:
                logger.warning(f"Chunk {chunk_id} not found for neighbor expansion")
                return []
            
            target_chunk, document = row
            target_index = target_chunk.chunk_index
            
            # Get neighbors
            query = (
                select(Chunk)
                .where(
                    Chunk.document_id == target_chunk.document_id,
                    Chunk.chunk_index >= target_index - n_before,
                    Chunk.chunk_index <= target_index + n_after
                )
                .order_by(Chunk.chunk_index)
            )
            
            result = await db.execute(query)
            chunks = result.scalars().all()
            
            # Format results
            neighbor_chunks = []
            for chunk in chunks:
                chunk_metadata = self._safe_extract_metadata(chunk.chunk_metadata)
                
                chunk_dict = {
                    'chunk_id': str(chunk.id),
                    'id': str(chunk.id),
                    'document_id': str(chunk.document_id),
                    'document_name': document.filename,
                    'content': chunk.content,
                    'chunk_type': chunk.chunk_type,
                    'chunk_index': chunk.chunk_index,
                    'page_numbers': chunk.page_numbers,
                    'section_title': chunk.section_title,
                    'token_count': chunk.token_count,
                    'is_target': chunk.id == chunk_id,
                    'chunk_metadata': chunk_metadata,
                    'metadata': {
                        'document_title': document.filename,
                        **chunk_metadata,
                    }
                }
                neighbor_chunks.append(chunk_dict)
            
            return neighbor_chunks
            
        except Exception as e:
            logger.error(f"Failed to get chunk neighbors: {str(e)}", exc_info=True)
            return []


# Global instance
vector_search_service = VectorSearchService()

__all__ = ['VectorSearchService', 'vector_search_service']