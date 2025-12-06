"""
LLM generation service using Google Gemini.
Handles answer generation with strict sourcing and formatting.
Supports both document-based and conversational responses.
"""
from typing import List, Dict, Any, Optional, AsyncGenerator
import asyncio
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential
from loguru import logger

from app.core.config import settings


class LLMService:
    """
    Service for generating answers using Google Gemini.
    Implements strict prompting for accurate, source-based responses.
    Also handles natural conversational queries.
    """
    
    def __init__(self):
        # Configure Gemini
        genai.configure(api_key=settings.gemini_api_key)
        
        self.model_name = settings.gemini_chat_model
        self.temperature = settings.temperature
        self.max_tokens = settings.gemini_max_tokens
        
        # Initialize model
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config={
                "temperature": self.temperature,
                "max_output_tokens": settings.max_response_tokens,
                "top_p": 0.95,
            }
        )
        
        # System prompt for document-based RAG
        self.system_instruction = """You are Mentanova, a helpful AI assistant specializing in Finance and HRMS documentation.

Your role is to provide accurate, helpful answers based on the provided document context.

Guidelines:
1. Answer questions using ONLY the information from the provided context when documents are available
2. Be conversational and friendly, but professional
3. For financial figures: Always cite the source document and page
4. If information is not in the context: Politely say you don't have that information in the available documents
5. For policies: Reference the exact document and section
6. Use format [Document: X, Page: Y] for citations
7. If unsure, acknowledge it and suggest alternatives

Response style:
- Use natural, conversational language
- Structure responses with:
  - Clear paragraphs
  - Bullet points for lists
  - Bold for emphasis (use **text**)
  - Proper spacing
- Be concise but thorough
- For greetings and general conversation, respond naturally without forcing document references"""
        
        logger.info(f"LLM service initialized: {self.model_name}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_conversational_response(
        self,
        query: str,
        context_message: str,
        history: Optional[List[Dict[str, str]]] = None,
        is_error: bool = False
    ) -> Dict[str, Any]:
        """
        Generate a natural conversational response (no document context).
        Used for greetings, small talk, and general conversation.
        
        Args:
            query: User's query
            context_message: Context or guidance message
            history: Conversation history
            is_error: Whether this is an error response
            
        Returns:
            Dictionary with answer and metadata
        """
        logger.info(f"Generating conversational response for: '{query[:50]}...'")
        
        # Build conversational prompt
        if is_error:
            prompt = f"""The user asked: "{query}"

However, there's an issue: {context_message}

Please respond in a helpful, friendly way that explains the limitation while guiding the user on how they can get help with their Finance and HRMS documents."""
        else:
            prompt = f"""The user said: "{query}"

Please respond naturally and helpfully. You are Mentanova, an AI assistant that helps with Finance and HRMS documents. 

Be conversational, friendly, and guide the user on how you can help them find information from documents.

Use natural language, be warm and helpful."""
        
        # Build message history
        messages = []
        
        # Add conversational system prompt
        messages.append({
            "role": "user",
            "parts": ["You are Mentanova, a friendly AI assistant. Respond naturally to user queries. Be helpful, conversational, and professional. Use markdown formatting (bullet points, bold, etc.) when appropriate."]
        })
        messages.append({
            "role": "model",
            "parts": ["I understand. I'll be helpful, conversational, and use proper formatting."]
        })
        
        # Add history if exists
        if history:
            for msg in history[-4:]:
                role = "model" if msg["role"] == "assistant" else "user"
                messages.append({"role": role, "parts": [msg["content"]]})
        
        # Add current prompt
        messages.append({"role": "user", "parts": [prompt]})
        
        try:
            loop = asyncio.get_event_loop()
            
            response = await loop.run_in_executor(
                None,
                lambda: self.model.generate_content(
                    messages,
                    generation_config={
                        "temperature": 0.7,  # More creative for conversation
                        "max_output_tokens": 500,
                    }
                )
            )
            
            answer = response.text
            
            return {
                'answer': answer,
                'confidence': 'high',
                'citations': [],
                'usage': {
                    'prompt_tokens': response.usage_metadata.prompt_token_count if hasattr(response, 'usage_metadata') else 0,
                    'completion_tokens': response.usage_metadata.candidates_token_count if hasattr(response, 'usage_metadata') else 0,
                    'total_tokens': response.usage_metadata.total_token_count if hasattr(response, 'usage_metadata') else 0
                }
            }
            
        except Exception as e:
            logger.error(f"Conversational generation failed: {str(e)}")
            # Fallback to context message
            return {
                'answer': context_message,
                'confidence': 'medium',
                'citations': [],
                'usage': {'total_tokens': 0}
            }
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_answer(
        self,
        query: str,
        context: str,
        sources: List[Dict[str, Any]],
        conversation_history: Optional[List[Dict[str, str]]] = None,
        is_conversational: bool = False
    ) -> Dict[str, Any]:
        """
        Generate answer using Gemini with retrieved context.
        Now handles both document-based and conversational queries.
        
        Args:
            query: User's question
            context: Retrieved context (can be empty for conversational)
            sources: Source documents
            conversation_history: Previous messages
            is_conversational: If True, focus on natural conversation
            
        Returns:
            Dictionary with answer, citations, and metadata
        """
        logger.info(f"Generating answer: conversational={is_conversational}, sources={len(sources)}")
        
        # Build prompt based on query type
        if is_conversational or not context or len(context.strip()) < 50:
            # Conversational mode - no strong document context
            user_prompt = f"""Question: {query}

Note: No specific document context is available for this query.

Please respond naturally and conversationally. If this is a greeting or general question, respond appropriately. If the user is asking about documents but no context is available, guide them helpfully on what you can assist with.

Use proper markdown formatting:
- **Bold** for important points
- Bullet points for lists
- Clear paragraphs for readability"""
        else:
            # Document-based mode
            user_prompt = self._build_prompt(query, context, sources)
        
        # Build messages
        messages = []
        
        # System instruction
        messages.append({"role": "user", "parts": [self.system_instruction]})
        messages.append({"role": "model", "parts": ["Understood. I'll provide accurate, well-formatted responses with proper citations when using documents."]})
        
        # Add history
        if conversation_history:
            for msg in conversation_history[-6:]:
                role = "model" if msg["role"] == "assistant" else "user"
                messages.append({"role": role, "parts": [msg["content"]]})
        
        # Add current query
        messages.append({"role": "user", "parts": [user_prompt]})
        
        try:
            loop = asyncio.get_event_loop()
            
            response = await loop.run_in_executor(
                None,
                lambda: self.model.generate_content(
                    messages,
                    generation_config={
                        "temperature": 0.7 if is_conversational else self.temperature,
                        "max_output_tokens": settings.max_response_tokens,
                    }
                )
            )
            
            answer = response.text
            citations = self._extract_citations(answer, sources)
            confidence = self._assess_confidence(answer, context)
            
            usage = {
                'prompt_tokens': response.usage_metadata.prompt_token_count if hasattr(response, 'usage_metadata') else 0,
                'completion_tokens': response.usage_metadata.candidates_token_count if hasattr(response, 'usage_metadata') else 0,
                'total_tokens': response.usage_metadata.total_token_count if hasattr(response, 'usage_metadata') else 0
            }
            
            logger.info(f"✅ Generated: {len(answer)} chars, {len(citations)} citations")
            
            return {
                'answer': answer,
                'citations': citations,
                'confidence': confidence,
                'finish_reason': 'stop',
                'usage': usage
            }
            
        except Exception as e:
            logger.error(f"Generation failed: {str(e)}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_answer_stream(
        self,
        query: str,
        context: str,
        sources: List[Dict[str, Any]],
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate answer with streaming for real-time display.
        
        Args:
            query: User's question
            context: Retrieved context
            sources: Source documents
            conversation_history: Previous messages
            
        Yields:
            Chunks of the generated answer
        """
        logger.info(f"Streaming answer for query: '{query[:50]}...'")
        
        # Build prompt
        user_prompt = self._build_prompt(query, context, sources)
        
        # Build chat messages
        messages = []
        
        messages.append({
            "role": "user",
            "parts": [self.system_instruction]
        })
        messages.append({
            "role": "model",
            "parts": ["Understood. I'll follow these rules strictly."]
        })
        
        if conversation_history:
            for msg in conversation_history[-6:]:
                role = "model" if msg["role"] == "assistant" else "user"
                messages.append({
                    "role": role,
                    "parts": [msg["content"]]
                })
        
        messages.append({
            "role": "user",
            "parts": [user_prompt]
        })
        
        try:
            # Stream response
            loop = asyncio.get_event_loop()
            
            response_stream = await loop.run_in_executor(
                None,
                lambda: self.model.generate_content(
                    messages,
                    stream=True,
                    generation_config={
                        "temperature": self.temperature,
                        "max_output_tokens": settings.max_response_tokens,
                    }
                )
            )
            
            for chunk in response_stream:
                if chunk.text:
                    yield chunk.text
            
            logger.info("✅ Streaming completed")
            
        except Exception as e:
            logger.error(f"Streaming failed: {str(e)}")
            raise
    
    def _build_prompt(
        self,
        query: str,
        context: str,
        sources: List[Dict[str, Any]]
    ) -> str:
        """Build the complete prompt with query and context."""
        # Format sources for reference
        sources_text = "\n".join([
            f"- {src['document']}, Page {src.get('page', 'N/A')}" + 
            (f", Section: {src['section']}" if src.get('section') else "")
            for src in sources
        ])
        
        prompt = f"""Question: {query}

Available Context from Documents:
{context}

Source Documents Referenced:
{sources_text}

Instructions:
1. Answer the question using ONLY the information from the context above
2. Cite specific sources in your answer using format: [Document: X, Page: Y]
3. If the context doesn't contain enough information, clearly state what's missing
4. For financial data, include the exact figures and their source
5. Be precise and avoid speculation

Formatting:
- Use **bold** for important points
- Use bullet points for lists
- Use clear paragraphs
- Use markdown formatting

Answer:"""
        
        return prompt
    
    def _extract_citations(
        self,
        answer: str,
        sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Extract citation references from the generated answer."""
        import re
        
        citations = []
        
        # Pattern to match [Document: X, Page: Y] format
        citation_pattern = r'\[Document:\s*([^,]+),\s*Page:\s*(\d+)\]'
        
        for match in re.finditer(citation_pattern, answer):
            doc_name = match.group(1).strip()
            page_num = int(match.group(2))
            
            # Find matching source
            for source in sources:
                if (source['document'].lower() in doc_name.lower() or 
                    doc_name.lower() in source['document'].lower()) and \
                   source.get('page') == page_num:
                    
                    citations.append({
                        'document': source['document'],
                        'page': page_num,
                        'chunk_id': source.get('chunk_id'),
                        'position': match.start()
                    })
                    break
        
        return citations
    
    def _assess_confidence(self, answer: str, context: str) -> str:
        """Assess confidence level of the answer."""
        # High confidence indicators
        high_indicators = [
            'according to', 'states that', 'specified in',
            'the document shows', 'as per', 'clearly mentions'
        ]
        
        # Low confidence indicators
        low_indicators = [
            'not available', 'unclear', 'doesn\'t specify',
            'may', 'might', 'possibly', 'appears to'
        ]
        
        answer_lower = answer.lower()
        
        # Check for uncertainty
        if any(indicator in answer_lower for indicator in low_indicators):
            return 'low'
        
        # Check for strong sourcing
        if any(indicator in answer_lower for indicator in high_indicators):
            if '[Document:' in answer:
                return 'high'
        
        return 'medium'
    
    async def summarize_document(
        self,
        document_content: str,
        document_title: str,
        max_length: int = 500
    ) -> str:
        """
        Generate a concise summary of a document.
        
        Args:
            document_content: Full or partial document content
            document_title: Title of the document
            max_length: Maximum summary length
            
        Returns:
            Summary text
        """
        prompt = f"""Summarize the following document concisely in {max_length} words or less.
Focus on key points, main topics, and important information.

Use proper markdown formatting:
- **Bold** for key terms
- Bullet points for main topics
- Clear paragraphs

Document: {document_title}

Content:
{document_content[:4000]}

Summary:"""
        
        try:
            loop = asyncio.get_event_loop()
            
            response = await loop.run_in_executor(
                None,
                lambda: self.model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.3,
                        "max_output_tokens": max_length * 2,
                    }
                )
            )
            
            summary = response.text
            logger.info(f"Generated summary for '{document_title}'")
            
            return summary
            
        except Exception as e:
            logger.error(f"Summary generation failed: {str(e)}")
            return f"Summary unavailable for {document_title}"


# Global instance
llm_service = LLMService()

__all__ = ['LLMService', 'llm_service']