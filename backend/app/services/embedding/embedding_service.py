"""
Embedding generation service using OpenAI's text-embedding-3-large model.
Includes batching, retry logic, and caching for efficiency.
"""
from typing import List, Dict, Any, Optional
import asyncio
from openai import AsyncOpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
from loguru import logger
import numpy as np

from app.core.config import settings


class EmbeddingService:
    """
    Service for generating embeddings with OpenAI API.
    Handles batching, retries, and contextual enhancement.
    """
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_embedding_model
        self.dimensions = settings.openai_embedding_dimensions
        self.batch_size = 100  # OpenAI allows up to 2048 texts per request
        
        logger.info(f"Embedding service initialized: {self.model} ({self.dimensions}D)")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception)
    )
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=text,
                dimensions=self.dimensions
            )
            
            embedding = response.data[0].embedding
            logger.debug(f"Generated embedding for text (length: {len(text)})")
            
            return embedding
            
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception)
    )
    async def generate_embeddings_batch(
        self, 
        texts: List[str],
        show_progress: bool = False
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts efficiently.
        Processes in batches to respect API limits.
        
        Args:
            texts: List of texts to embed
            show_progress: Whether to log progress
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        all_embeddings = []
        total_batches = (len(texts) + self.batch_size - 1) // self.batch_size
        
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            batch_num = i // self.batch_size + 1
            
            if show_progress:
                logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} texts)")
            
            try:
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=batch,
                    dimensions=self.dimensions
                )
                
                # Extract embeddings in correct order
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)
                
            except Exception as e:
                logger.error(f"Error in batch {batch_num}: {str(e)}")
                raise
        
        logger.info(f"Generated {len(all_embeddings)} embeddings successfully")
        return all_embeddings
    
    def enhance_text_for_embedding(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Enhance text with contextual information for better embeddings.
        
        Args:
            text: Original text
            context: Dictionary with metadata (document_title, section, page, etc.)
            
        Returns:
            Enhanced text with context
        """
        enhanced_parts = []
        
        if context:
            # Add document context
            if 'document_title' in context:
                enhanced_parts.append(f"Document: {context['document_title']}")
            
            # Add section context
            if 'section' in context:
                enhanced_parts.append(f"Section: {context['section']}")
            
            # Add page context
            if 'page' in context:
                enhanced_parts.append(f"Page: {context['page']}")
            
            # Add type context
            if 'chunk_type' in context and context['chunk_type'] != 'text':
                enhanced_parts.append(f"Type: {context['chunk_type']}")
        
        # Combine context with original text
        if enhanced_parts:
            context_str = " | ".join(enhanced_parts)
            return f"{context_str}\n\n{text}"
        
        return text
    
    async def embed_chunks_with_context(
        self,
        chunks: List[Dict[str, Any]],
        document_title: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate embeddings for chunks with contextual enhancement.
        
        Args:
            chunks: List of chunk dictionaries
            document_title: Title of the source document
            
        Returns:
            Chunks with embeddings added
        """
        # Prepare enhanced texts
        enhanced_texts = []
        for chunk in chunks:
            context = {
                'document_title': document_title,
                'section': chunk.get('section_title'),
                'page': chunk.get('page_numbers', [None])[0],
                'chunk_type': chunk.get('chunk_type', 'text')
            }
            
            enhanced_text = self.enhance_text_for_embedding(
                chunk['content'],
                context
            )
            enhanced_texts.append(enhanced_text)
        
        # Generate embeddings in batches
        logger.info(f"Generating embeddings for {len(chunks)} chunks")
        embeddings = await self.generate_embeddings_batch(
            enhanced_texts,
            show_progress=True
        )
        
        # Add embeddings to chunks
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
        """
        Generate embedding for a search query.
        Optimized for query understanding.
        
        Args:
            query: User's search query
            
        Returns:
            Query embedding vector
        """
        # Optionally enhance query with instructions
        enhanced_query = f"Query: {query}"
        
        return await self.generate_embedding(enhanced_query)


# Global instance
embedding_service = EmbeddingService()

__all__ = ['EmbeddingService', 'embedding_service']