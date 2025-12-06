"""
Embedding generation service using Google Gemini.
Includes batching, retry logic, and local fallback.
"""
from typing import List, Dict, Any, Optional
import asyncio
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential
from loguru import logger
import numpy as np

from app.core.config import settings


class EmbeddingService:
    """
    Service for generating embeddings with Google Gemini API.
    Falls back to local model if API fails.
    """
    
    def __init__(self):
        # Configure Gemini
        genai.configure(api_key=settings.gemini_api_key)
        
        self.model_name = settings.gemini_embedding_model
        self.dimensions = settings.gemini_embedding_dimensions
        self.batch_size = 100
        
        # Local fallback
        self.local_model = None
        self.use_local_fallback = False
        
        logger.info(f"Embedding service initialized: Gemini {self.model_name} ({self.dimensions}D)")
    
    def _init_local_model(self):
        """Initialize local sentence-transformers model as fallback."""
        if self.local_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.warning("Initializing local embedding model...")
                self.local_model = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')
                logger.info("Local embedding model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load local model: {str(e)}")
                raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        if self.use_local_fallback:
            return await self._generate_embedding_local(text)
        
        try:
            return await self._generate_embedding_gemini(text)
        except Exception as e:
            error_str = str(e).lower()
            if any(err in error_str for err in ['quota', 'rate limit', 'authentication', '429', '401', '403']):
                logger.warning(f"Gemini API error, switching to local: {str(e)}")
                self.use_local_fallback = True
                self._init_local_model()
                return await self._generate_embedding_local(text)
            raise
    
    async def _generate_embedding_gemini(self, text: str) -> List[float]:
        """Generate embedding using Gemini API."""
        loop = asyncio.get_event_loop()
        
        # Run blocking call in executor
        result = await loop.run_in_executor(
            None,
            lambda: genai.embed_content(
                model=self.model_name,
                content=text,
                task_type="retrieval_document"
            )
        )
        
        embedding = result['embedding']
        
        # Adjust dimensions if needed
        embedding = self._adjust_dimensions(embedding)
        
        logger.debug(f"Generated Gemini embedding for text (length: {len(text)})")
        return embedding
    
    async def _generate_embedding_local(self, text: str) -> List[float]:
        """Generate embedding using local model."""
        if self.local_model is None:
            self._init_local_model()
        
        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(
            None,
            lambda: self.local_model.encode(text, convert_to_numpy=True).tolist()
        )
        
        embedding = self._adjust_dimensions(embedding)
        logger.debug(f"Generated local embedding for text (length: {len(text)})")
        return embedding
    
    def _adjust_dimensions(self, embedding: List[float]) -> List[float]:
        """Adjust embedding dimensions to match expected size."""
        current_dim = len(embedding)
        target_dim = self.dimensions
        
        if current_dim == target_dim:
            return embedding
        elif current_dim < target_dim:
            return embedding + [0.0] * (target_dim - current_dim)
        else:
            return embedding[:target_dim]
    
    async def generate_embeddings_batch(
        self,
        texts: List[str],
        show_progress: bool = False
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts efficiently.
        
        Args:
            texts: List of texts to embed
            show_progress: Whether to log progress
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        if self.use_local_fallback:
            return await self._generate_embeddings_batch_local(texts, show_progress)
        
        try:
            return await self._generate_embeddings_batch_gemini(texts, show_progress)
        except Exception as e:
            error_str = str(e).lower()
            if any(err in error_str for err in ['quota', 'rate limit', 'authentication', '429', '401', '403']):
                logger.warning(f"Gemini batch error, switching to local: {str(e)}")
                self.use_local_fallback = True
                self._init_local_model()
                return await self._generate_embeddings_batch_local(texts, show_progress)
            raise
    
    async def _generate_embeddings_batch_gemini(
        self,
        texts: List[str],
        show_progress: bool = False
    ) -> List[List[float]]:
        """Generate embeddings using Gemini API in batches."""
        all_embeddings = []
        total_batches = (len(texts) + self.batch_size - 1) // self.batch_size
        
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            batch_num = i // self.batch_size + 1
            
            if show_progress:
                logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} texts) [Gemini]")
            
            loop = asyncio.get_event_loop()
            
            # Process batch
            result = await loop.run_in_executor(
                None,
                lambda: genai.embed_content(
                    model=self.model_name,
                    content=batch,
                    task_type="retrieval_document"
                )
            )
            
            # Extract embeddings
            if isinstance(result['embedding'][0], list):
                # Multiple embeddings returned
                batch_embeddings = [self._adjust_dimensions(emb) for emb in result['embedding']]
            else:
                # Single embedding for batch
                batch_embeddings = [self._adjust_dimensions(result['embedding'])]
            
            all_embeddings.extend(batch_embeddings)
            
            # Small delay to avoid rate limits
            await asyncio.sleep(0.1)
        
        logger.info(f"Generated {len(all_embeddings)} Gemini embeddings successfully")
        return all_embeddings
    
    async def _generate_embeddings_batch_local(
        self,
        texts: List[str],
        show_progress: bool = False
    ) -> List[List[float]]:
        """Generate embeddings using local model in batches."""
        if self.local_model is None:
            self._init_local_model()
        
        if show_progress:
            logger.info(f"Processing {len(texts)} texts with local model...")
        
        loop = asyncio.get_event_loop()
        embeddings_array = await loop.run_in_executor(
            None,
            lambda: self.local_model.encode(texts, convert_to_numpy=True, show_progress_bar=show_progress)
        )
        
        embeddings = [self._adjust_dimensions(emb.tolist()) for emb in embeddings_array]
        
        logger.info(f"Generated {len(embeddings)} local embeddings successfully")
        return embeddings
    
    def enhance_text_for_embedding(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Enhance text with contextual information for better embeddings."""
        enhanced_parts = []
        
        if context:
            if 'document_title' in context:
                enhanced_parts.append(f"Document: {context['document_title']}")
            if 'section' in context:
                enhanced_parts.append(f"Section: {context['section']}")
            if 'page' in context:
                enhanced_parts.append(f"Page: {context['page']}")
            if 'chunk_type' in context and context['chunk_type'] != 'text':
                enhanced_parts.append(f"Type: {context['chunk_type']}")
        
        if enhanced_parts:
            context_str = " | ".join(enhanced_parts)
            return f"{context_str}\n\n{text}"
        
        return text
    
    async def embed_chunks_with_context(
        self,
        chunks: List[Dict[str, Any]],
        document_title: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Generate embeddings for chunks with contextual enhancement."""
        enhanced_texts = []
        for chunk in chunks:
            context = {
                'document_title': document_title,
                'section': chunk.get('section_title'),
                'page': chunk.get('page_numbers', [None])[0],
                'chunk_type': chunk.get('chunk_type', 'text')
            }
            
            enhanced_text = self.enhance_text_for_embedding(chunk['content'], context)
            enhanced_texts.append(enhanced_text)
        
        logger.info(f"Generating embeddings for {len(chunks)} chunks")
        embeddings = await self.generate_embeddings_batch(enhanced_texts, show_progress=True)
        
        for chunk, embedding in zip(chunks, embeddings):
            chunk['embedding'] = embedding
        
        return chunks
    
    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        vec1_np = np.array(vec1)
        vec2_np = np.array(vec2)
        
        dot_product = np.dot(vec1_np, vec2_np)
        norm1 = np.linalg.norm(vec1_np)
        norm2 = np.linalg.norm(vec2_np)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    async def embed_query(self, query: str) -> List[float]:
        """Generate embedding for a search query."""
        enhanced_query = f"Query: {query}"
        
        if self.use_local_fallback:
            return await self._generate_embedding_local(enhanced_query)
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: genai.embed_content(
                    model=self.model_name,
                    content=enhanced_query,
                    task_type="retrieval_query"  # Different task type for queries
                )
            )
            return self._adjust_dimensions(result['embedding'])
        except Exception as e:
            logger.warning(f"Query embedding failed, using local: {str(e)}")
            self.use_local_fallback = True
            self._init_local_model()
            return await self._generate_embedding_local(enhanced_query)


# Global instance
embedding_service = EmbeddingService()

__all__ = ['EmbeddingService', 'embedding_service']