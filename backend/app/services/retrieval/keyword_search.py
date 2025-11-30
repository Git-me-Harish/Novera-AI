"""
Keyword-based search using PostgreSQL full-text search.
Implements BM25-like ranking for exact match queries.
"""
from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, or_
from loguru import logger

from app.models.document import Chunk, Document


class KeywordSearchService:
    """
    Service for keyword-based search using PostgreSQL full-text search.
    Complements vector search for exact matches and specific terms.
    """
    
    def __init__(self):
        self.default_top_k = 10
    
    async def search_keywords(
        self,
        query: str,
        db: AsyncSession,
        top_k: Optional[int] = None,
        doc_type: Optional[str] = None,
        department: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search chunks using keyword matching.
        
        Args:
            query: Search query string
            db: Database session
            top_k: Number of results
            doc_type: Filter by document type
            department: Filter by department
            
        Returns:
            List of matching chunks with relevance scores
        """
        k = top_k or self.default_top_k
        
        # Prepare search query for PostgreSQL
        # Replace spaces with & for AND operation
        search_query = ' & '.join(query.split())
        
        # Build query using PostgreSQL full-text search
        query_stmt = (
            select(
                Chunk,
                Document,
                func.ts_rank_cd(
                    func.to_tsvector('english', Chunk.content),
                    func.plainto_tsquery('english', query)
                ).label('rank')
            )
            .join(Document, Chunk.document_id == Document.id)
            .where(
                Document.status == "completed",
                func.to_tsvector('english', Chunk.content).op('@@')(
                    func.plainto_tsquery('english', query)
                )
            )
        )
        
        # Apply filters
        if doc_type:
            query_stmt = query_stmt.where(Document.doc_type == doc_type)
        
        if department:
            query_stmt = query_stmt.where(Document.department == department)
        
        # Order by rank
        query_stmt = query_stmt.order_by(text('rank DESC')).limit(k)
        
        # Execute
        result = await db.execute(query_stmt)
        rows = result.all()
        
        # Format results
        chunks = []
        for chunk, document, rank in rows:
            chunk_dict = {
                'chunk_id': str(chunk.id),
                'document_id': str(document.id),
                'content': chunk.content,
                'chunk_type': chunk.chunk_type,
                'page_numbers': chunk.page_numbers,
                'section_title': chunk.section_title,
                'token_count': chunk.token_count,
                'keyword_score': float(rank),
                'metadata': {
                    **chunk.metadata,
                    'document_title': document.filename,
                    'doc_type': document.doc_type,
                    'department': document.department,
                }
            }
            
            chunks.append(chunk_dict)
        
        logger.info(f"Keyword search found {len(chunks)} matching chunks")
        
        return chunks
    
    async def search_exact_phrase(
        self,
        phrase: str,
        db: AsyncSession,
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for exact phrase matches.
        Useful for specific terms, IDs, or policy numbers.
        """
        k = top_k or self.default_top_k
        
        query = (
            select(Chunk, Document)
            .join(Document, Chunk.document_id == Document.id)
            .where(
                Document.status == "completed",
                Chunk.content.ilike(f'%{phrase}%')
            )
            .limit(k)
        )
        
        result = await db.execute(query)
        rows = result.all()
        
        chunks = []
        for chunk, document in rows:
            chunk_dict = {
                'chunk_id': str(chunk.id),
                'document_id': str(document.id),
                'content': chunk.content,
                'chunk_type': chunk.chunk_type,
                'page_numbers': chunk.page_numbers,
                'section_title': chunk.section_title,
                'exact_match': True,
                'metadata': {
                    **chunk.metadata,
                    'document_title': document.filename,
                    'doc_type': document.doc_type,
                }
            }
            chunks.append(chunk_dict)
        
        logger.info(f"Exact phrase search found {len(chunks)} chunks")
        
        return chunks
    
    async def search_by_metadata(
        self,
        metadata_filters: Dict[str, Any],
        db: AsyncSession,
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Search chunks by metadata fields.
        
        Args:
            metadata_filters: Dictionary of metadata key-value pairs
            db: Database session
            top_k: Number of results
            
        Returns:
            Matching chunks
        """
        k = top_k or self.default_top_k
        
        query = (
            select(Chunk, Document)
            .join(Document, Chunk.document_id == Document.id)
            .where(Document.status == "completed")
        )
        
        # Add metadata filters
        for key, value in metadata_filters.items():
            query = query.where(
                Chunk.metadata[key].astext == str(value)
            )
        
        query = query.limit(k)
        
        result = await db.execute(query)
        rows = result.all()
        
        chunks = []
        for chunk, document in rows:
            chunk_dict = {
                'chunk_id': str(chunk.id),
                'document_id': str(document.id),
                'content': chunk.content,
                'chunk_type': chunk.chunk_type,
                'metadata': {
                    **chunk.metadata,
                    'document_title': document.filename,
                }
            }
            chunks.append(chunk_dict)
        
        return chunks


# Global instance
keyword_search_service = KeywordSearchService()

__all__ = ['KeywordSearchService', 'keyword_search_service']