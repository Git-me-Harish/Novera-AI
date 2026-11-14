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
from app.core.rag_trace import get_current_trace
from app.core.rag_trace import hash_value

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.generation.context_manager import ConversationContext


_EXCERPT_CHARS = 600


def _within_token_budget(chunks: List[Dict[str, Any]], budget: int) -> List[Dict[str, Any]]:
    """Best-ranked chunks until the evidence budget is spent.

    The top chunk is always kept, even when it alone exceeds the budget.
    A chunk that does not fit is skipped, not truncated, so a smaller one
    further down can still be used.
    """
    selected, used = [], 0
    for chunk in chunks:
        tokens = int(chunk.get("token_count") or 0)
        if selected and used + tokens > budget:
            continue
        selected.append(chunk)
        used += tokens
    return selected


def _excerpt(content: str) -> str:
    """First ~600 characters of a chunk, cut at a word boundary."""
    text = " ".join((content or "").split())
    if len(text) <= _EXCERPT_CHARS:
        return text
    return text[:_EXCERPT_CHARS].rsplit(" ", 1)[0] + "…"


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
        organization_id,
        top_k: Optional[int] = None,
        doc_type: Optional[str] = None,
        department: Optional[str] = None,
        include_context: bool = True,
        conversation_context: Optional['ConversationContext'] = None,
        force_global: bool = False,
        query_embedding: Optional[list[float]] = None,
    ) -> Dict[str, Any]:
        """
        Complete retrieval pipeline with conversation context awareness and dynamic scoping.
        
        Args:
            query: User's search query
            db: Database session
            top_k: Number of final chunks to return
            doc_type: Filter by document type
            department: Filter by department
            include_context: Whether to expand with neighboring chunks
            conversation_context: Conversation context for document scoping
            force_global: Force global search (skip scoping)
            
        Returns:
            Dictionary with retrieved chunks and metadata
        """
        logger.info(f"🔍 Starting retrieval pipeline: query_hash={hash_value(query)}, chars={len(query)}")
        
        # Step 1: Process and enhance query
        logger.info("Step 1: Processing query...")
        processed_query = query_processor.process_query(query)
        
        logger.info(f"  Intent: {processed_query['intent']}")
        logger.info(f"  Complexity: {processed_query['complexity']}")
        
        # Step 2: Apply conversation context - BOOST not FILTER
        boost_documents = []
        use_scoped_search = False
        document_filter_for_boosting = None

        if conversation_context and not force_global:
            logger.info("Step 2: Applying conversation context...")
            
            # Get documents to BOOST (not hard filter)
            document_filter_for_boosting = conversation_context.get_document_filter()
            
            if document_filter_for_boosting:
                boost_documents = document_filter_for_boosting
                use_scoped_search = True
                logger.info(f"  ⬆️ Will boost results from: {boost_documents}")
            else:
                logger.info("  🌐 No document boosting - global search")
        else:
            logger.info("Step 2: Global search (no context or forced)")

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

        # Step 4: Execute search with dynamic scoping
        initial_top_k = settings.scoped_search_top_k if use_scoped_search else settings.global_search_top_k

        logger.info(f"Step 3: Performing {'scoped' if use_scoped_search else 'global'} hybrid search (k={initial_top_k})...")

        if include_context:
            search_results = await hybrid_search_service.search_with_context_expansion(
                query=query,
                db=db,
                organization_id=organization_id,
                top_k=initial_top_k,
                expand_neighbors=True,
                use_semantic=use_semantic,
                use_keyword=use_keyword,
                doc_type=doc_type,
                department=department,
                document_filter=None,  # CRITICAL: No hard filtering
                boost_documents=boost_documents,  # Only boosting
                query_embedding=query_embedding,
            )
        else:
            search_results = await hybrid_search_service.search(
                query=query,
                db=db,
                organization_id=organization_id,
                top_k=initial_top_k,
                use_semantic=use_semantic,
                use_keyword=use_keyword,
                doc_type=doc_type,
                department=department,
                document_filter=None,  # CRITICAL: No hard filtering
                boost_documents=boost_documents,  # Only boosting
                query_embedding=query_embedding,
            )

        logger.info(f"  Initial search: {len(search_results)} chunks")

        # Step 5: DYNAMIC EXPANSION - Check if we need global search
        should_expand = False

        if use_scoped_search and conversation_context and settings.enable_dynamic_scope:
            should_expand = conversation_context.should_expand_search(search_results)
            
            if should_expand:
                logger.info("🔄 Scoped search insufficient - performing GLOBAL search...")
                
                global_results = await hybrid_search_service.search(
                    query=query,
                    db=db,
                    organization_id=organization_id,
                    top_k=settings.global_search_top_k,
                    use_semantic=use_semantic,
                    use_keyword=use_keyword,
                    doc_type=doc_type,
                    department=department,
                    document_filter=None,
                    boost_documents=[]  # No boosting in global search
                )
                
                logger.info(f"  Global search: {len(global_results)} chunks")
                
                # Merge results: prioritize scoped but include global
                seen_ids = set()
                merged_results = []
                
                # Add scoped results first (boosted)
                for chunk in search_results:
                    chunk_id = chunk.get('chunk_id')
                    if chunk_id and chunk_id not in seen_ids:
                        chunk['source_type'] = 'scoped'
                        merged_results.append(chunk)
                        seen_ids.add(chunk_id)
                
                # Add global results
                for chunk in global_results:
                    chunk_id = chunk.get('chunk_id')
                    if chunk_id and chunk_id not in seen_ids:
                        chunk['source_type'] = 'global'
                        merged_results.append(chunk)
                        seen_ids.add(chunk_id)
                
                search_results = merged_results
                logger.info(f"  Merged results: {len(search_results)} total chunks")

        # Step 6: Rerank results
        pre_rerank_chunk_ids = [str(chunk.get("chunk_id")) for chunk in search_results]
        reranked_results = []

        # Focused factual questions usually have one evidence-bearing chunk;
        # sending every neighboring hit increases prompt cost and invites the
        # generator to answer adjacent questions. Broader procedural and
        # analytical questions retain a larger evidence budget.
        broad_intents = {"procedural", "analytical", "compliance"}
        broad = processed_query["complexity"] == "complex" or processed_query["intent"] in broad_intents
        context_chunk_limit = settings.complex_context_chunks if broad else settings.focused_context_chunks
        context_token_budget = settings.complex_context_tokens if broad else settings.focused_context_tokens
        if top_k:
            context_chunk_limit = min(context_chunk_limit, top_k)

        # Decide if reranking is needed
        should_rerank = (
            self.rerank_enabled and
            len(search_results) > 1 and
            len(search_results) >= 3
        )

        # Step 6: Rerank results
        if should_rerank:
            logger.info("Step 4: Reranking results...")
            try:
                reranked_results = await reranking_service.rerank(
                    query=query,
                    chunks=search_results,
                    top_n=context_chunk_limit,
                )
                stats = reranking_service.calculate_score_statistics(reranked_results)
                logger.info(
                    f"  Rerank scores: min={stats['min_score']:.3f}, "
                    f"max={stats['max_score']:.3f}, avg={stats['avg_score']:.3f}"
                )
            except Exception as e:
                logger.error(f"Reranking failed: {e} — using original order")
                reranked_results = [
                    {**chunk, "rerank_degraded": True}
                    for chunk in search_results[:context_chunk_limit]
                ]
        else:
            logger.info("Step 4: Skipping reranking (disabled or insufficient results)")
            reranked_results = search_results[:context_chunk_limit]

        # Exact domain terms are a recall safety net. A cross-encoder can
        # occasionally score a chunk containing the requested named concept
        # below generic explanatory text. Preserve the strongest sparse hit in
        # the final evidence budget so hybrid retrieval cannot discard an exact
        # lexical match before generation.
        keyword_rescue = max(
            (chunk for chunk in search_results if float(chunk.get("keyword_score", 0.0) or 0.0) > 0),
            key=lambda chunk: float(chunk.get("keyword_score", 0.0) or 0.0),
            default=None,
        )
        if keyword_rescue and not any(
            chunk.get("chunk_id") == keyword_rescue.get("chunk_id")
            for chunk in reranked_results
        ):
            if len(reranked_results) >= context_chunk_limit:
                reranked_results[-1] = keyword_rescue
            else:
                reranked_results.append(keyword_rescue)
            keyword_rescue["retrieval_rescue"] = "keyword_exact_match"
            logger.info(
                "Preserved strongest keyword match in context: %s",
                keyword_rescue.get("chunk_id"),
            )

        # Do not send weakly relevant evidence to generation. A low-scoring
        # context can make the model produce a plausible but unsupported answer
        # instead of taking the required abstention path.
        # The floor is calibrated for cross-encoder scores only. RRF fused
        # scores are ~0.01, so applying it to them after a reranker outage
        # silently filtered every chunk and the system abstained on all
        # questions. When reranking is degraded, fall back to the cosine
        # similarity floor and record the degradation.
        rerank_degraded = any(chunk.get("rerank_degraded") for chunk in reranked_results) or (
            not should_rerank
        )

        def _passes_floor(chunk: Dict[str, Any]) -> bool:
            if chunk.get("retrieval_rescue") == "keyword_exact_match":
                return True
            if not rerank_degraded:
                return float(chunk.get("rerank_score") or 0.0) >= settings.min_rerank_score
            if chunk.get("keyword_score"):
                return True
            return float(chunk.get("similarity_score") or chunk.get("semantic_score") or 0.0) >= (
                settings.similarity_threshold
            )

        before_relevance_filter = len(reranked_results)
        reranked_results = [chunk for chunk in reranked_results if _passes_floor(chunk)]
        reranked_results = _within_token_budget(reranked_results, context_token_budget)
        if rerank_degraded and should_rerank:
            logger.warning("Reranker degraded — using similarity floor instead of rerank floor")
            trace = get_current_trace()
            if trace:
                trace.event("rerank_degraded", status="degraded")
        if before_relevance_filter != len(reranked_results):
            logger.info(
                f"Relevance floor filtered {before_relevance_filter} -> "
                f"{len(reranked_results)} chunks "
                f"(minimum rerank score {settings.min_rerank_score:.3f})",
            )

        logger.info(f"  After reranking: {len(reranked_results)} chunks")
        
        # Step 7: Assemble final context
        logger.info("Step 5: Assembling context...")
        final_context = self._assemble_context(
            chunks=reranked_results,
            processed_query=processed_query
        )
        
        logger.info(f"✅ Retrieval complete: {len(final_context['chunks'])} chunks, {final_context['total_tokens']} tokens")

        ranking_scores = [
            float(chunk.get("rerank_score", chunk.get("fused_score", 0.0)) or 0.0)
            for chunk in final_context["chunks"]
        ]
        score_summary = {
            "min": min(ranking_scores) if ranking_scores else 0.0,
            "max": max(ranking_scores) if ranking_scores else 0.0,
            "avg": sum(ranking_scores) / len(ranking_scores) if ranking_scores else 0.0,
        }

        trace = get_current_trace()
        if trace:
            trace.set_principal(tenant_id=organization_id)
            trace.set_query(query)
            trace.event(
                "retrieval_completed",
                strategy="hybrid" if (use_semantic and use_keyword) else ("semantic" if use_semantic else "keyword"),
                candidate_k=len(search_results),
                final_k=len(final_context["chunks"]),
                context_tokens=final_context["total_tokens"],
                min_score=score_summary["min"],
                max_score=score_summary["max"],
                avg_score=score_summary["avg"],
            )
        
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
                'min_rerank_score': settings.min_rerank_score,
                'final_chunks': len(final_context['chunks']),
                'context_chunk_limit': context_chunk_limit,
                'context_token_budget': context_token_budget,
                'intent': processed_query['intent'],
                'complexity': processed_query['complexity'],
                'used_scoped_search': use_scoped_search,
                'expanded_to_global': should_expand,
                'boosted_documents': boost_documents,
                'search_type': 'global' if should_expand else ('scoped' if use_scoped_search else 'global'),
                'pre_rerank_chunk_ids': pre_rerank_chunk_ids,
                'rerank_degraded': rerank_degraded,
                'score_summary': score_summary,
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
        
        # max_tokens = min(self.max_context_tokens, 6000)
        max_tokens = self.max_context_tokens  # use the configured 12,000 — Gemini handles it

        
        seen_chunk_ids: set = set()
        for chunk in sorted_chunks:
            chunk_key = str(chunk.get('chunk_id', chunk.get('id', '')))
            if chunk_key in seen_chunk_ids:
                continue
            chunk_tokens = chunk.get('token_count', 0)
            
            # if chunk_tokens > 800:
            #     chunk['content'] = chunk['content'][:3200]
            #     chunk_tokens = 800

            if chunk_tokens > 1200:
                chunk['content'] = chunk['content'][:4800]
                chunk_tokens = 1200
            
            if total_tokens + chunk_tokens > max_tokens:
                logger.warning(f"Reached token limit ({max_tokens}), stopping context assembly")
                break
            
            # Label the block with the same number as its source entry so
            # citation [n] is unambiguous even when two chunks share a page.
            source_number = len(sources) + 1
            chunk_text = self._format_chunk_for_context(chunk)
            context_parts.append(f"[{source_number}] {chunk_text}")

            chunk_metadata = self._safe_get_metadata(chunk)

            sources.append({
                'document': chunk_metadata.get('document_title', chunk.get('document_name', 'Unknown Document')),
                'document_id': str(chunk.get('document_id')) if chunk.get('document_id') else None,
                'page': chunk.get('page_numbers', [None])[0] if chunk.get('page_numbers') else None,
                'section': chunk.get('section_title'),
                'chunk_id': chunk_key,
                # The cited passage, so readers can verify a claim in place
                # without opening the document. Tenant-scoped like the answer.
                'excerpt': _excerpt(chunk.get('content', '')),
            })
            seen_chunk_ids.add(chunk_key)
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
        # ✅ Use safe metadata extraction
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
        organization_id,
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
            organization_id=organization_id,
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
