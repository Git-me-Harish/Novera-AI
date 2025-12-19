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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.generation.context_manager import ConversationContext


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
        include_context: bool = True,
        conversation_context: Optional['ConversationContext'] = None  # NEW
    ) -> Dict[str, Any]:
        """
        Complete retrieval pipeline with conversation context awareness.
        
        Args:
            query: User's search query
            db: Database session
            top_k: Number of final chunks to return
            doc_type: Filter by document type
            department: Filter by department
            include_context: Whether to expand with neighboring chunks
            conversation_context: Conversation context for document scoping
            
        Returns:
            Dictionary with retrieved chunks and metadata
        """
        logger.info(f"🔍 Starting retrieval pipeline for query: '{query[:50]}...'")
        
        # Step 1: Process and enhance query
        logger.info("Step 1: Processing query...")
        processed_query = query_processor.process_query(query)
        
        logger.info(f"  Intent: {processed_query['intent']}")
        logger.info(f"  Complexity: {processed_query['complexity']}")
        
        # Step 2: Apply conversation context filtering
        document_filter = None
        boost_documents = []
        
        if conversation_context:
            logger.info("Step 2: Applying conversation context...")
            
            # Get document filter if we should scope
            if conversation_context.should_use_document_scope():
                document_filter = conversation_context.get_document_filter()
                logger.info(f"  📄 Document scope: {document_filter}")
            
            # Get documents to boost in ranking
            if conversation_context.primary_document:
                boost_documents = [conversation_context.primary_document]
                logger.info(f"  ⬆️ Boosting: {boost_documents}")
        
        # Step 3: Determine search strategy
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
        
        # Step 4: Hybrid search with context
        logger.info("Step 3: Performing hybrid search...")
        
        if include_context:
            search_results = await hybrid_search_service.search_with_context_expansion(
                query=query,
                db=db,
                top_k=top_k or settings.retrieval_top_k,
                expand_neighbors=True,
                document_filter=document_filter, 
                boost_documents=boost_documents
            )
        else:
            search_results = await hybrid_search_service.search(
                query=query,
                db=db,
                top_k=top_k or settings.retrieval_top_k,
                use_semantic=use_semantic,
                use_keyword=use_keyword,
                doc_type=doc_type,
                department=department,
                document_filter=document_filter,
                boost_documents=boost_documents   
            )
        
        logger.info(f"  Retrieved {len(search_results)} chunks")
        
        # Step 5: Rerank results
        if self.rerank_enabled and len(search_results) > 1:
            logger.info("Step 4: Reranking results...")
            reranked_results = await reranking_service.rerank(
                query=query,
                chunks=search_results,
                top_n=top_k or settings.rerank_top_k
            )
            
            stats = reranking_service.calculate_score_statistics(reranked_results)
            logger.info(f"  Rerank scores: min={stats['min_score']:.3f}, max={stats['max_score']:.3f}, avg={stats['avg_score']:.3f}")
        else:
            logger.info("Step 4: Skipping reranking")
            reranked_results = search_results[:top_k or settings.rerank_top_k]
        
        # Step 6: Assemble final context
        logger.info("Step 5: Assembling context...")
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
                'complexity': processed_query['complexity'],
                'document_scoped': document_filter is not None,
                'scoped_to': document_filter if document_filter else None,
                'boosted_documents': boost_documents
            }
        }
    
    def _safe_get_metadata(self, chunk: Dict[str, Any]) -> dict:
        """
        Safely extract metadata from chunk, handling SQLAlchemy objects.
        
        Args:
            chunk: Chunk dictionary (may contain SQLAlchemy objects)
            
        Returns:
            Plain dictionary with metadata
        """
        metadata = {}
        
        # Try different metadata keys
        for meta_key in ['chunk_metadata', 'metadata', 'doc_metadata']:
            if meta_key in chunk:
                meta_obj = chunk[meta_key]
                
                # Handle different types
                if isinstance(meta_obj, dict):
                    metadata = meta_obj
                    break
                elif hasattr(meta_obj, '__dict__'):
                    # SQLAlchemy object - convert to dict
                    try:
                        metadata = {k: v for k, v in meta_obj.__dict__.items() if not k.startswith('_')}
                        break
                    except Exception as e:
                        logger.debug(f"Could not extract __dict__ from metadata: {e}")
                        pass
                elif hasattr(meta_obj, 'keys') and hasattr(meta_obj, '__getitem__'):
                    # Mapping-like object
                    try:
                        metadata = {k: meta_obj[k] for k in meta_obj.keys()}
                        break
                    except Exception as e:
                        logger.debug(f"Could not extract keys from metadata: {e}")
                        pass
        
        # Fallback: Extract from chunk itself if metadata is empty
        if not metadata:
            metadata = {
                'document_title': chunk.get('document_name') or chunk.get('filename', 'Unknown'),
                'doc_type': chunk.get('doc_type'),
                'department': chunk.get('department'),
            }
        
        return metadata
    
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
        if not chunks:
            return []
        
        intent = processed_query.get('intent', 'general')
        entities = processed_query.get('entities', {})
        has_financial_entities = 'amount' in entities or 'financial' in intent.lower()
        
        def get_priority(chunk: Dict[str, Any]) -> tuple:
            # Higher number = higher priority (sort descending)
            priority = 0
            
            # Boost tables for financial/analytical queries
            chunk_type = chunk.get('chunk_type', 'text')
            if chunk_type == 'table' and (intent in ['financial', 'analytical'] or has_financial_entities):
                priority += 1000
            
            # Use rerank score as primary sort
            rerank_score = chunk.get('rerank_score', chunk.get('fused_score', chunk.get('similarity_score', 0)))
            
            return (priority, rerank_score)
        
        # Sort by priority
        try:
            sorted_chunks = sorted(chunks, key=get_priority, reverse=True)
        except Exception as e:
            logger.warning(f"Error sorting chunks: {e}, returning unsorted")
            sorted_chunks = chunks
        
        return sorted_chunks
    
    def _assemble_context(
        self,
        chunks: List[Dict[str, Any]],
        processed_query: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Assemble final context with intelligent truncation.
        """
        context_parts = []
        total_tokens = 0
        sources = []
        final_chunks = []
        
        if not chunks:
            logger.warning("No chunks to assemble context from")
            return {
                'chunks': [],
                'context_text': '',
                'total_tokens': 0,
                'sources': []
            }
        
        sorted_chunks = self._prioritize_chunks(chunks, processed_query)
        
        max_tokens = min(self.max_context_tokens, 6000)
        
        for chunk in sorted_chunks:
            chunk_tokens = chunk.get('token_count', 0)
            
            if chunk_tokens > 800:
                chunk['content'] = chunk['content'][:3200]
                chunk_tokens = 800
            
            if total_tokens + chunk_tokens > max_tokens:
                logger.warning(f"Reached token limit ({max_tokens}), stopping context assembly")
                break
            
            chunk_text = self._format_chunk_for_context(chunk)
            context_parts.append(chunk_text)
            
            chunk_metadata = self._safe_get_metadata(chunk)
            
            source_info = {
                'document': chunk_metadata.get('document_title', chunk.get('document_name', 'Unknown Document')),
                'page': chunk.get('page_numbers', [None])[0] if chunk.get('page_numbers') else None,
                'section': chunk.get('section_title'),
                'chunk_id': str(chunk.get('chunk_id', chunk.get('id', '')))
            }
            
            if source_info not in sources:
                sources.append(source_info)
            
            final_chunks.append(chunk)
            total_tokens += chunk_tokens
        
        context_text = "\n\n---\n\n".join(context_parts)
        
        logger.info(f"Assembled context: {len(final_chunks)} chunks, {total_tokens} tokens, {len(sources)} sources")
        
        return {
            'chunks': final_chunks,
            'context_text': context_text,
            'total_tokens': total_tokens,
            'sources': sources
        }
    
    def _format_chunk_for_context(self, chunk: Dict[str, Any]) -> str:
        """
        Format chunk with metadata for LLM context.
        
        Returns:
            Formatted chunk text with source information
        """
        # ✅ FIXED: Use safe metadata extraction
        chunk_metadata = self._safe_get_metadata(chunk)
        
        # Build header
        header_parts = []
        
        # Try to get document title from multiple sources
        doc_title = (
            chunk_metadata.get('document_title') or 
            chunk_metadata.get('filename') or
            chunk.get('document_name') or 
            chunk.get('filename')
        )
        
        if doc_title:
            header_parts.append(f"Document: {doc_title}")
        
        section_title = chunk.get('section_title')
        if section_title:
            header_parts.append(f"Section: {section_title}")
        
        page_numbers = chunk.get('page_numbers', [])
        if page_numbers and isinstance(page_numbers, list) and len(page_numbers) > 0:
            if len(page_numbers) == 1:
                header_parts.append(f"Page: {page_numbers[0]}")
            else:
                header_parts.append(f"Pages: {page_numbers[0]}-{page_numbers[-1]}")
        
        chunk_type = chunk.get('chunk_type', 'text')
        if chunk_type and chunk_type != 'text':
            header_parts.append(f"Type: {chunk_type.title()}")
        
        # Get content
        content = chunk.get('content', '')
        
        # Format final output
        if header_parts:
            header = " | ".join(header_parts)
            return f"[{header}]\n{content}"
        else:
            return content
    
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