"""
Complete retrieval pipeline orchestrator.
Coordinates query processing, hybrid search, reranking, and context assembly.
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.core.config import settings
from app.services.retrieval.query_processor import query_processor
from app.services.retrieval.hybrid_search import hybrid_search_service
from app.services.retrieval.reranker import reranking_service


class RetrievalPipeline:
    """
    Complete retrieval pipeline for RAG system.
    Orchestrates: Query Processing → Hybrid Search → Reranking → Context Assembly
    """
    
    def __init__(self):
        self.max_context_tokens = settings.max_context_tokens
        self.rerank_enabled = True
    
    async def retrieve(
        self,
        query: str,
        db: AsyncSession,
        top_k: Optional[int] = None,
        doc_type: Optional[str] = None,
        department: Optional[str] = None,
        include_context: bool = True
    ) -> Dict[str, Any]:
        """
        Complete retrieval pipeline.
        
        Args:
            query: User's search query
            db: Database session
            top_k: Number of final chunks to return
            doc_type: Filter by document type
            department: Filter by department
            include_context: Whether to expand with neighboring chunks
            
        Returns:
            Dictionary with retrieved chunks and metadata
        """
        logger.info(f"🔍 Starting retrieval pipeline for query: '{query[:50]}...'")
        
        # Step 1: Process and enhance query
        logger.info("Step 1: Processing query...")
        processed_query = query_processor.process_query(query)
        
        logger.info(f"  Intent: {processed_query['intent']}")
        logger.info(f"  Complexity: {processed_query['complexity']}")
        logger.info(f"  Entities: {processed_query['entities']}")
        
        # Step 2: Determine search strategy
        use_semantic = True
        use_keyword = True
        
        if query_processor.should_use_semantic_only(processed_query):
            logger.info("  Strategy: Semantic only")
            use_keyword = False
        elif query_processor.should_use_keyword_only(processed_query):
            logger.info("  Strategy: Keyword only")
            use_semantic = False
        else:
            logger.info("  Strategy: Hybrid (semantic + keyword)")
        
        # Step 3: Hybrid search
        logger.info("Step 2: Performing hybrid search...")
        
        if include_context:
            search_results = await hybrid_search_service.search_with_context_expansion(
                query=query,
                db=db,
                top_k=top_k or settings.retrieval_top_k,
                expand_neighbors=True
            )
        else:
            search_results = await hybrid_search_service.search(
                query=query,
                db=db,
                top_k=top_k or settings.retrieval_top_k,
                use_semantic=use_semantic,
                use_keyword=use_keyword,
                doc_type=doc_type,
                department=department
            )
        
        logger.info(f"  Retrieved {len(search_results)} chunks")
        
        # Step 4: Rerank results
        if self.rerank_enabled and len(search_results) > 1:
            logger.info("Step 3: Reranking results...")
            reranked_results = await reranking_service.rerank(
                query=query,
                chunks=search_results,
                top_n=top_k or settings.rerank_top_k
            )
            
            # Calculate statistics
            stats = reranking_service.calculate_score_statistics(reranked_results)
            logger.info(f"  Rerank scores: min={stats['min_score']:.3f}, max={stats['max_score']:.3f}, avg={stats['avg_score']:.3f}")
        else:
            logger.info("Step 3: Skipping reranking")
            reranked_results = search_results[:top_k or settings.rerank_top_k]
        
        # Step 5: Assemble final context
        logger.info("Step 4: Assembling context...")
        final_context = self._assemble_context(
            chunks=reranked_results,
            processed_query=processed_query
        )
        
        logger.info(f"✅ Retrieval complete: {len(final_context['chunks'])} chunks, {final_context['total_tokens']} tokens")
        
        return {
            'query': query,
            'processed_query': processed_query,
            'chunks': final_context['chunks'],
            'context_text': final_context['context_text'],
            'total_tokens': final_context['total_tokens'],
            'sources': final_context['sources'],
            'retrieval_metadata': {
                'search_strategy': 'hybrid' if (use_semantic and use_keyword) else ('semantic' if use_semantic else 'keyword'),
                'total_retrieved': len(search_results),
                'after_reranking': len(reranked_results),
                'final_chunks': len(final_context['chunks']),
                'intent': processed_query['intent'],
                'complexity': processed_query['complexity']
            }
        }
    
    def _assemble_context(
        self,
        chunks: List[Dict[str, Any]],
        processed_query: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Assemble final context from retrieved chunks.
        
        Args:
            chunks: Retrieved and reranked chunks
            processed_query: Processed query information
            
        Returns:
            Assembled context with metadata
        """
        context_parts = []
        total_tokens = 0
        sources = []
        final_chunks = []
        
        # Prioritize chunks based on type and relevance
        sorted_chunks = self._prioritize_chunks(chunks, processed_query)
        
        for chunk in sorted_chunks:
            chunk_tokens = chunk.get('token_count', 0)
            
            # Check if adding this chunk would exceed limit
            if total_tokens + chunk_tokens > self.max_context_tokens:
                logger.warning(f"Reached token limit ({self.max_context_tokens}), stopping context assembly")
                break
            
            # Format chunk with metadata
            chunk_text = self._format_chunk_for_context(chunk)
            context_parts.append(chunk_text)
            
            # Track sources
            source_info = {
                'document': chunk['metadata'].get('document_title', 'Unknown'),
                'page': chunk.get('page_numbers', [None])[0],
                'section': chunk.get('section_title'),
                'chunk_id': chunk['chunk_id']
            }
            
            if source_info not in sources:
                sources.append(source_info)
            
            final_chunks.append(chunk)
            total_tokens += chunk_tokens
        
        # Combine context parts
        context_text = "\n\n---\n\n".join(context_parts)
        
        return {
            'chunks': final_chunks,
            'context_text': context_text,
            'total_tokens': total_tokens,
            'sources': sources
        }
    
    def _prioritize_chunks(
        self,
        chunks: List[Dict[str, Any]],
        processed_query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Prioritize chunks based on type and relevance.
        
        Priority order:
        1. Tables (for financial/data queries)
        2. High rerank score chunks
        3. Exact matches
        4. Regular text chunks
        """
        intent = processed_query['intent']
        has_financial_entities = 'amount' in processed_query.get('entities', {})
        
        def get_priority(chunk: Dict[str, Any]) -> tuple:
            # Higher number = higher priority (sort descending)
            priority = 0
            
            # Boost tables for financial/analytical queries
            if chunk.get('chunk_type') == 'table' and (intent in ['financial', 'analytical'] or has_financial_entities):
                priority += 1000
            
            # Use rerank score as primary sort
            rerank_score = chunk.get('rerank_score', chunk.get('fused_score', 0))
            
            return (priority, rerank_score)
        
        # Sort by priority
        sorted_chunks = sorted(chunks, key=get_priority, reverse=True)
        
        return sorted_chunks
    
    def _format_chunk_for_context(self, chunk: Dict[str, Any]) -> str:
        """
        Format chunk with metadata for LLM context.
        
        Returns:
            Formatted chunk text with source information
        """
        metadata = chunk.get('metadata', {})
        
        # Build header
        header_parts = []
        
        if metadata.get('document_title'):
            header_parts.append(f"Document: {metadata['document_title']}")
        
        if chunk.get('section_title'):
            header_parts.append(f"Section: {chunk['section_title']}")
        
        if chunk.get('page_numbers'):
            pages = chunk['page_numbers']
            if len(pages) == 1:
                header_parts.append(f"Page: {pages[0]}")
            else:
                header_parts.append(f"Pages: {pages[0]}-{pages[-1]}")
        
        if chunk.get('chunk_type') and chunk['chunk_type'] != 'text':
            header_parts.append(f"Type: {chunk['chunk_type'].title()}")
        
        # Format
        if header_parts:
            header = " | ".join(header_parts)
            return f"[{header}]\n{chunk['content']}"
        else:
            return chunk['content']
    
    async def retrieve_from_document(
        self,
        query: str,
        document_id: str,
        db: AsyncSession,
        top_k: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Retrieve from a specific document only.
        Useful for document-specific questions.
        """
        from uuid import UUID
        
        logger.info(f"Retrieving from document {document_id}")
        
        # Process query
        processed_query = query_processor.process_query(query)
        
        # Search within document
        from app.services.embedding.embedding_service import embedding_service
        from app.services.retrieval.vector_search import vector_search_service
        
        query_embedding = await embedding_service.embed_query(query)
        
        search_results = await vector_search_service.search_by_document(
            query_embedding=query_embedding,
            document_id=UUID(document_id),
            db=db,
            top_k=top_k or settings.retrieval_top_k
        )
        
        # Rerank
        if self.rerank_enabled and search_results:
            reranked_results = await reranking_service.rerank(
                query=query,
                chunks=search_results,
                top_n=top_k or settings.rerank_top_k
            )
        else:
            reranked_results = search_results
        
        # Assemble context
        final_context = self._assemble_context(
            chunks=reranked_results,
            processed_query=processed_query
        )
        
        return {
            'query': query,
            'document_id': document_id,
            'chunks': final_context['chunks'],
            'context_text': final_context['context_text'],
            'total_tokens': final_context['total_tokens'],
            'sources': final_context['sources']
        }


# Global instance
retrieval_pipeline = RetrievalPipeline()

__all__ = ['RetrievalPipeline', 'retrieval_pipeline']