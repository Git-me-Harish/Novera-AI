"""
LLM generation service using OpenAI GPT-4.
Handles answer generation with strict sourcing and formatting.
"""
from typing import List, Dict, Any, Optional, AsyncGenerator
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from loguru import logger

from app.core.config import settings


class LLMService:
    """
    Service for generating answers using GPT-4.
    Implements strict prompting for accurate, source-based responses.
    """
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_chat_model
        self.temperature = settings.temperature
        self.max_tokens = settings.max_response_tokens
        
        # System prompt for finance/HRMS RAG
        self.system_prompt = """You are Mentanova's AI Knowledge Assistant, specializing in Finance and HRMS documentation.

STRICT RULES:
1. Answer ONLY using the provided context from approved documents
2. For financial figures: Always cite the source document and date
3. If context lacks information: State "This information is not available in the current knowledge base"
4. For calculations: Show your work step-by-step
5. For policies: Quote the exact policy section and document name
6. Never make assumptions about financial data
7. Always cite sources in [Document: X, Page: Y] format

RESPONSE FORMAT:
- Direct answer first
- Supporting details from context
- Source citations (Document name, Page number)
- If uncertain, state confidence level

Be concise, accurate, and professional."""
        
        logger.info(f"LLM service initialized: {self.model}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_answer(
        self,
        query: str,
        context: str,
        sources: List[Dict[str, Any]],
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Generate answer using GPT-4 with retrieved context.
        
        Args:
            query: User's question
            context: Retrieved and assembled context
            sources: List of source documents/pages
            conversation_history: Previous messages for context
            
        Returns:
            Dictionary with answer, citations, and metadata
        """
        logger.info(f"Generating answer for query: '{query[:50]}...'")
        
        # Build messages
        messages = [{"role": "system", "content": self.system_prompt}]
        
        # Add conversation history if exists
        if conversation_history:
            messages.extend(conversation_history[-6:])  # Last 3 exchanges
        
        # Build user prompt with context
        user_prompt = self._build_prompt(query, context, sources)
        messages.append({"role": "user", "content": user_prompt})
        
        try:
            # Call GPT-4
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                top_p=0.95,
                frequency_penalty=0.0,
                presence_penalty=0.0
            )
            
            answer = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
            
            # Extract citations from answer
            citations = self._extract_citations(answer, sources)
            
            # Calculate confidence
            confidence = self._assess_confidence(answer, context)
            
            result = {
                'answer': answer,
                'citations': citations,
                'confidence': confidence,
                'finish_reason': finish_reason,
                'usage': {
                    'prompt_tokens': response.usage.prompt_tokens,
                    'completion_tokens': response.usage.completion_tokens,
                    'total_tokens': response.usage.total_tokens
                }
            }
            
            logger.info(f"✅ Answer generated: {len(answer)} chars, {len(citations)} citations")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Generation failed: {str(e)}")
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
        
        # Build messages
        messages = [{"role": "system", "content": self.system_prompt}]
        
        if conversation_history:
            messages.extend(conversation_history[-6:])
        
        user_prompt = self._build_prompt(query, context, sources)
        messages.append({"role": "user", "content": user_prompt})
        
        try:
            # Stream response
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True
            )
            
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            
            logger.info("✅ Streaming completed")
            
        except Exception as e:
            logger.error(f"❌ Streaming failed: {str(e)}")
            raise
    
    def _build_prompt(
        self,
        query: str,
        context: str,
        sources: List[Dict[str, Any]]
    ) -> str:
        """
        Build the complete prompt with query and context.
        
        Returns:
            Formatted prompt string
        """
        # Format sources for reference
        sources_text = "\n".join([
            f"- {src['document']}, Page {src['page']}" + 
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

Answer:"""
        
        return prompt
    
    def _extract_citations(
        self,
        answer: str,
        sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Extract citation references from the generated answer.
        
        Returns:
            List of cited sources with positions
        """
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
        """
        Assess confidence level of the answer.
        
        Returns:
            Confidence level: high, medium, low
        """
        # Simple heuristic-based confidence
        
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
            # Also check if citations present
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

Document: {document_title}

Content:
{document_content[:4000]}  # Limit input length

Summary:"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a precise document summarizer."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=max_length * 2
            )
            
            summary = response.choices[0].message.content
            logger.info(f"Generated summary for '{document_title}'")
            
            return summary
            
        except Exception as e:
            logger.error(f"Summary generation failed: {str(e)}")
            return f"Summary unavailable for {document_title}"


# Global instance
llm_service = LLMService()

__all__ = ['LLMService', 'llm_service']