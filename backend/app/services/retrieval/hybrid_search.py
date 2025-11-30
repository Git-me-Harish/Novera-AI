"""
Hybrid search combining semantic (vector) and keyword (BM25) search.
Implements Reciprocal Rank Fusion for result merging.
"""
from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.core.config import settings
from app.services.retrieval.vector_search import vector_search_service
from app.services.retrieval.keyword_search import keyword_search_service
from app.services.embedding.embedding_service import embedding_service


class HybridSearchService:
    """
    Combines semantic and keyword search for optimal retrieval.
    Uses Reciprocal Rank Fusion (RRF) to merge results.
    """
    
    def __init__(self):
        self.alpha = settings.hybrid_alpha  # Weight for semantic vs keyword (0.7 = 70% semantic)
        self.top_k = settings.retrieval_top_k
        self.rrf_k = 60  # RRF constant
    
    async def search(
        self,
        query: str,
        db: AsyncSession,
        top_k: Optional[int] = None,
        use_semantic: bool = True,
        use_keyword: bool = True,
        doc_type: Optional[str] = None,
        department: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining multiple retrieval methods.
        
        Args:
            query: User's search query
            db: Database session
            top_k: Number of results to return
            use_semantic: Enable vector similarity search
            use_keyword: Enable keyword search
            doc_type: Filter by document type
            department: Filter by department
            
        Returns:
            Ranked list of chunks with combined scores
        """
        k = top_k or self.top_k
        
        logger.info(f"Hybrid search: query='{query[:50]}...', k={k}")
        
        results = {}
        
        # 1. Semantic search
        if use_semantic:
            logger.info("Running semantic search...")
            query_embedding = await embedding_service.embed_query(query)
            
            semantic_results = await vector_search_service.search_similar_chunks(
                query_embedding=query_embedding,
                db=db,
                top_k=k * 2,  # Get more candidates for fusion
                doc_type=doc_type,
                department=department
            )
            
            # Add semantic results to combined pool
            for idx, chunk in enumerate(semantic_results, 1):
                chunk_id = chunk['chunk_id']
                if chunk_id not in results:
                    results[chunk_id] = chunk.copy()
                    results[chunk_id]['semantic_rank'] = idx
                    results[chunk_id]['semantic_score'] = chunk['similarity_score']
                else:
                    results[chunk_id]['semantic_rank'] = idx
                    results[chunk_id]['semantic_score'] = chunk['similarity_score']
            
            logger.info(f"Semantic search returned {len(semantic_results)} results")
        
        # 2. Keyword search
        if use_keyword:
            logger.info("Running keyword search...")
            keyword_results = await keyword_search_service.search_keywords(
                query=query,
                db=db,
                top_k=k,
                doc_type=doc_type,
                department=department
            )
            
            # Add keyword results to combined pool
            for idx, chunk in enumerate(keyword_results, 1):
                chunk_id = chunk['chunk_id']
                if chunk_id not in results:
                    results[chunk_id] = chunk.copy()
                    results[chunk_id]['keyword_rank'] = idx
                    results[chunk_id]['keyword_score'] = chunk.get('keyword_score', 0)
                else:
                    results[chunk_id]['keyword_rank'] = idx
                    results[chunk_id]['keyword_score'] = chunk.get('keyword_score', 0)
            
            logger.info(f"Keyword search returned {len(keyword_results)} results")
        
        # 3. Fuse results using Reciprocal Rank Fusion
        logger.info("Fusing results...")
        fused_results = self._reciprocal_rank_fusion(results)
        
        # 4. Sort by fused score and return top-k
        sorted_results = sorted(
            fused_results.values(),
            key=lambda x: x['fused_score'],
            reverse=True
        )[:k]
        
        logger.info(f"Hybrid search completed: {len(sorted_results)} final results")
        
        return sorted_results
    
    def _reciprocal_rank_fusion(
        self,
        results: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Apply Reciprocal Rank Fusion to combine rankings.
        
        RRF formula: score = Σ(1 / (k + rank_i))
        where k is a constant (usually 60) and rank_i is the rank in each list.
        """
        for chunk_id, chunk in results.items():
            rrf_score = 0.0
            
            # Semantic contribution
            if 'semantic_rank' in chunk:
                semantic_contribution = 1.0 / (self.rrf_k + chunk['semantic_rank'])
                rrf_score += semantic_contribution * self.alpha
            
            # Keyword contribution
            if 'keyword_rank' in chunk:
                keyword_contribution = 1.0 / (self.rrf_k + chunk['keyword_rank'])
                rrf_score += keyword_contribution * (1 - self.alpha)
            
            chunk['fused_score'] = rrf_score
            
            # Preserve original scores for transparency
            chunk['retrieval_method'] = []
            if 'semantic_rank' in chunk:
                chunk['retrieval_method'].append('semantic')
            if 'keyword_rank' in chunk:
                chunk['retrieval_method'].append('keyword')
        
        return results
    
    async def search_with_context_expansion(
        self,
        query: str,
        db: AsyncSession,
        top_k: Optional[int] = None,
        expand_neighbors: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search with automatic context expansion.
        Retrieves neighboring chunks for better context.
        
        Args:
            query: Search query
            db: Database session
            top_k: Number of results
            expand_neighbors: Whether to include neighboring chunks
            
        Returns:
            Chunks with expanded context
        """
        # Get initial results
        initial_results = await self.search(
            query=query,
            db=db,
            top_k=top_k
        )
        
        if not expand_neighbors:
            return initial_results
        
        # Expand context for top results
        expanded_results = []
        seen_chunk_ids = set()
        
        for result in initial_results[:5]:  # Expand top 5 results
            chunk_id = UUID(result['chunk_id'])
            
            # Get neighbors
            neighbors = await vector_search_service.get_chunk_neighbors(
                chunk_id=chunk_id,
                db=db,
                n_before=1,
                n_after=1
            )
            
            # Add all neighbors to results
            for neighbor in neighbors:
                nid = neighbor['chunk_id']
                if nid not in seen_chunk_ids:
                    # Mark as expanded context
                    neighbor['is_expanded_context'] = not neighbor['is_target']
                    neighbor['parent_chunk_id'] = result['chunk_id'] if not neighbor['is_target'] else None
                    
                    if neighbor['is_target']:
                        # Preserve original scores
                        neighbor.update({
                            'fused_score': result['fused_score'],
                            'semantic_score': result.get('semantic_score'),
                            'keyword_score': result.get('keyword_score'),
                            'retrieval_method': result['retrieval_method']
                        })
                    
                    expanded_results.append(neighbor)
                    seen_chunk_ids.add(nid)
        
        # Add remaining results without expansion
        for result in initial_results[5:]:
            if result['chunk_id'] not in seen_chunk_ids:
                result['is_expanded_context'] = False
                expanded_results.append(result)
                seen_chunk_ids.add(result['chunk_id'])
        
        logger.info(f"Context expansion: {len(initial_results)} → {len(expanded_results)} chunks")
        
        return expanded_results


# Global instance
hybrid_search_service = HybridSearchService()

__all__ = ['HybridSearchService', 'hybrid_search_service']