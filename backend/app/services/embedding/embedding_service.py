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

try:
    TORCH_AVAILABLE = True
except ImportError as e:
    logger.warning(f"PyTorch/SentenceTransformers not available: {e}")
    TORCH_AVAILABLE = False

from app.core.config import settings

class EmbeddingService:
    """
    Service for generating embeddings with Google Gemini API.
    Falls back to local model if API fails.
    """
    
    def __init__(self):
        genai.configure(api_key=settings.gemini_api_key)
    
        # Gemini model
        self.model_name = f"models/{settings.gemini_embedding_model}"
    
        # Required attributes (YOU REMOVED THESE)
        self.dimensions = settings.gemini_embedding_dimensions
        self.batch_size = 100
    
        logger.info(
            f"Embedding service initialized: Gemini {self.model_name} ({self.dimensions}D)"
        )
    
        
    def _init_local_model(self):
        """
        Initialize local sentence-transformers model as fallback.
        
        Uses all-mpnet-base-v2 (768D) which provides excellent quality
        and matches common Gemini embedding dimensions.
        """
        if self.local_model is not None:
            return  # Already initialized
        
        if not TORCH_AVAILABLE:
            logger.error("Local embeddings disabled: torch not installed.")
            raise RuntimeError("Local embeddings are disabled in production.")
        
        try:
            # Log PyTorch environment
            logger.info(f"PyTorch version: {torch.__version__}")
            logger.info(f"CUDA available: {torch.cuda.is_available()}")
            
            # Verify _pytree availability (diagnostic)
            if hasattr(torch.utils, '_pytree'):
                if hasattr(torch.utils._pytree, 'register_pytree_node'):
                    logger.debug("✅ torch.utils._pytree.register_pytree_node available")
                else:
                    logger.warning("⚠️ torch.utils._pytree exists but missing register_pytree_node")
            else:
                logger.error("❌ torch.utils._pytree module not found")
            
            # Select device
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            logger.info(f"Loading local embedding model on device: {device}")
            
            # Initialize model with explicit device
            # Using 'all-mpnet-base-v2' (768D) for better quality
            # Alternative: 'all-MiniLM-L6-v2' (384D) for faster processing
            model_name = 'all-MiniLM-L6-v2'
            
            logger.warning(f"Initializing local embedding model: {model_name}")
            self.local_model = SentenceTransformer(model_name, device=device)
            
            # Validate model works
            test_embedding = self.local_model.encode("test", convert_to_numpy=True)
            logger.info(
                f"✅ Local embedding model loaded successfully "
                f"(device={device}, dims={len(test_embedding)})"
            )
            
        except AttributeError as e:
            # Specific handling for _pytree error
            if "_pytree" in str(e) or "register_pytree_node" in str(e):
                error_msg = (
                    f"PyTorch installation incomplete: {str(e)}. "
                    "This typically indicates missing torchvision or torchaudio packages. "
                    f"Current torch version: {torch.__version__}. "
                    "Please ensure requirements.txt includes: "
                    "torch==2.1.2, torchvision==0.16.2, torchaudio==2.1.2"
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg) from e
            else:
                logger.error(f"Failed to load local model (AttributeError): {str(e)}")
                raise
                
        except Exception as e:
            logger.error(f"Gemini embedding failed: {str(e)}")
            raise RuntimeError("Gemini embedding failed. Local fallback disabled.") from e

        
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
                task_type="retrieval_document",
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
            logger.error(f"Gemini embedding failed: {e}")
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
            
            try:
                loop = asyncio.get_event_loop()
                
                # Add timeout wrapper
                async def embed_with_timeout():
                    try:
                        # Run blocking call in executor with timeout
                        future = loop.run_in_executor(
                            None,
                            lambda: genai.embed_content(
                                model=self.model_name,
                                content=batch,
                                task_type="retrieval_document"
                            )
                        )
                        # Wait max 30 seconds
                        return await asyncio.wait_for(future, timeout=30.0)
                    except asyncio.TimeoutError:
                        logger.error(f"Batch {batch_num} timed out after 30 seconds")
                        raise
                
                result = await embed_with_timeout()
                
                # Extract embeddings
                if isinstance(result['embedding'][0], list):
                    # Multiple embeddings returned
                    batch_embeddings = [self._adjust_dimensions(emb) for emb in result['embedding']]
                else:
                    # Single embedding for batch
                    batch_embeddings = [self._adjust_dimensions(result['embedding'])]
                
                logger.info(f"✅ Batch {batch_num} completed: {len(batch_embeddings)} embeddings")
                all_embeddings.extend(batch_embeddings)
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.2)
                
            except asyncio.TimeoutError as e:
                logger.error(f"Timeout in batch {batch_num}: {str(e)}")
                logger.warning("Switching to local embeddings due to timeout")
                self.use_local_fallback = True
                return await self._generate_embeddings_batch_local(texts, show_progress)
                
            except Exception as e:
                logger.error(f"Error in batch {batch_num}: {str(e)}")
                error_str = str(e).lower()
                if any(err in error_str for err in ['quota', 'rate limit', 'authentication', '429', '401', '403']):
                    logger.warning(f"Gemini batch error, switching to local: {str(e)}")
                    self.use_local_fallback = True
                    return await self._generate_embeddings_batch_local(texts, show_progress)
                raise
        
        logger.info(f"✅ Generated {len(all_embeddings)} Gemini embeddings successfully")
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
            logger.error(f"Gemini query embedding failed: {str(e)}")
            raise



# Global instance
embedding_service = EmbeddingService()

__all__ = ['EmbeddingService', 'embedding_service']
