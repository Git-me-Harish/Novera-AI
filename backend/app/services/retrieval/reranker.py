"""
Reranking service using Cohere Rerank API.
Significantly improves retrieval accuracy by reordering results.
"""
from typing import List, Dict, Any
import cohere
from tenacity import retry, stop_after_attempt, wait_exponential
from loguru import logger

from app.core.config import settings


class RerankingService:
    """
    Service for reranking retrieved chunks using Cohere's Rerank model.
    Dramatically improves relevance by understanding query-document relationships.
    """
    
    def __init__(self):
        self.client = cohere.Client(api_key=settings.cohere_api_key)
        self.model = settings.cohere_rerank_model
        self.top_n = settings.rerank_top_k
        
        logger.info(f"Reranking service initialized: {self.model}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def rerank(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_n: int = None
    ) -> List[Dict[str, Any]]:
        """
        Rerank chunks based on relevance to query using async API call.
        
        Args:
            query: User's search query
            chunks: List of retrieved chunks
            top_n: Number of top results to return (default from config)
            
        Returns:
            Reranked list of chunks with relevance scores
        """
        if not chunks:
            logger.warning("No chunks to rerank")
            return []
        
        n = top_n or self.top_n
        
        logger.info(f"Reranking {len(chunks)} chunks, returning top {n}")
        
        # Prepare documents for reranking
        documents = [chunk['content'] for chunk in chunks]
        
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            
            response = await loop.run_in_executor(
                None,
                lambda: self.client.rerank(
                    model=self.model,
                    query=query,
                    documents=documents,
                    top_n=min(n, len(documents))
                )
            )
            
            # Map rerank results back to chunks
            reranked_chunks = []
            
            for result in response.results:
                # Get original chunk
                original_chunk = chunks[result.index].copy()
                
                # Add rerank score
                original_chunk['rerank_score'] = result.relevance_score
                original_chunk['rerank_position'] = result.index
                
                reranked_chunks.append(original_chunk)
            
            logger.info(f"✅ Reranking completed: {len(reranked_chunks)} results")
            
            return reranked_chunks
            
        except Exception as e:
            logger.error(f"❌ Reranking failed: {str(e)}")
            logger.warning("Falling back to original ranking")
            
            # Fallback: return original chunks with preserved scores
            fallback_chunks = []
            for i, chunk in enumerate(chunks[:n]):
                chunk_copy = chunk.copy()
                chunk_copy['rerank_score'] = chunk.get('similarity_score', 0) or chunk.get('fused_score', 0)
                chunk_copy['rerank_position'] = i
                fallback_chunks.append(chunk_copy)
            
            return fallback_chunks
    
    async def rerank_with_threshold(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        relevance_threshold: float = 0.5,
        top_n: int = None
    ) -> List[Dict[str, Any]]:
        """
        Rerank and filter by relevance threshold.
        
        Args:
            query: Search query
            chunks: Retrieved chunks
            relevance_threshold: Minimum relevance score (0-1)
            top_n: Maximum results
            
        Returns:
            Filtered and reranked chunks
        """
        reranked = await self.rerank(query, chunks, top_n)
        
        # Filter by threshold
        filtered = [
            chunk for chunk in reranked
            if chunk.get('rerank_score', 0) >= relevance_threshold
        ]
        
        logger.info(f"Filtered to {len(filtered)} chunks above threshold {relevance_threshold}")
        
        return filtered
    
    def calculate_score_statistics(
        self,
        chunks: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """
        Calculate statistics about rerank scores.
        Useful for debugging and threshold tuning.
        """
        if not chunks:
            return {}
        
        scores = [chunk.get('rerank_score', 0) for chunk in chunks]
        
        return {
            'min_score': min(scores),
            'max_score': max(scores),
            'avg_score': sum(scores) / len(scores),
            'median_score': sorted(scores)[len(scores) // 2],
            'total_chunks': len(chunks)
        }


# Global instance
reranking_service = RerankingService()

__all__ = ['RerankingService', 'reranking_service']
