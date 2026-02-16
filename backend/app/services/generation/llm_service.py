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
import tiktoken

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
    
        # FIX: Remove 'models/' prefix if SDK adds it automatically
        raw_model_name = settings.gemini_chat_model
        if raw_model_name.startswith('models/'):
            self.model_name = raw_model_name.replace('models/', '', 1)
        else:
            self.model_name = raw_model_name
        
        self.temperature = settings.temperature
        
        # Initialize model
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config={
                "temperature": self.temperature,
                "max_output_tokens": settings.max_response_tokens,
                "top_p": 0.95,
            }
        )
        
        # System prompt for document-based RAG # I have manually added point 3 just check them:
        self.system_instruction = """You are Novera, an AI assistant specializing in Finance and HRMS documentation.

Core Guidelines:
1. Answer questions using ONLY information from provided context when documents are available
2. Be conversational, friendly, and professional
3. Understand the situation properly and answer accordingly with empathy
4. For financial figures: Include exact numbers with proper citations
5. If information is not in context: Clearly state what's missing
6. CRITICAL: Use numbered citations [1], [2], [3] to reference sources
7. Place citations IMMEDIATELY after each fact: "The policy states X [1]."

Citation Rules:
- Use [1], [2], [3] format (NOT [Document: X, Page: Y])
- Each unique source gets a unique number
- Multiple sources: "This is confirmed [1,2,3]"
- Place citation right after the relevant statement
- Sources are numbered in the order provided below

Response Formatting:
- Use natural, conversational language
- Structure clearly: paragraphs, bullet points (- or *), bold (**text**)
- For tabular data, use Markdown tables:
  | Header 1 | Header 2 |
  |----------|----------|
  | Value 1  | Value 2  |

Examples:
❌ BAD: "According to Branch_Manager_Manual.docx, the eligibility is 2 years."
✅ GOOD: "The eligibility criteria is 2 years of service [1]."

❌ BAD: "The document mentions a 30-day notice period."
✅ GOOD: "The notice period is 30 days [2], which applies to all permanent employees [2]."

Remember: Each fact from documents MUST have a citation number."""
        
        # Initialize token encoder for accurate counting
        try:
            self.encoding = tiktoken.get_encoding("cl100k_base")
            logger.info(f"LLM service initialized: {self.model_name} with tiktoken encoder")
        except Exception as e:
            logger.warning(f"Failed to load tiktoken encoder: {e}, using estimation fallback")
            self.encoding = None
    
    def count_tokens(self, text: str) -> int:
        """
        Accurately count tokens in text using tiktoken.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Token count (accurate if tiktoken loaded, estimated otherwise)
        """
        if self.encoding:
            try:
                return len(self.encoding.encode(text))
            except Exception as e:
                logger.warning(f"Token counting failed, using estimation: {e}")
        
        # Fallback: rough estimation (1 token ≈ 4 characters)
        return len(text) // 4
    
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

Please respond naturally and helpfully. You are Novera, an AI assistant that helps with Finance and HRMS documents. 

Be conversational, friendly, and guide the user on how you can help them find information from documents.

Use natural language, be warm and helpful."""
        
        # Build message history
        messages = []
        
        # Add conversational system prompt
        messages.append({
            "role": "user",
            "parts": ["You are Novera, a friendly AI assistant. Respond naturally to user queries. Be helpful, conversational, and professional. Use markdown formatting (bullet points, bold, etc.) when appropriate."]
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
                        "temperature": 0.7,
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
        reformulated_query: Optional[str] = None,
        conversation_context: Optional[Dict[str, Any]] = None,
        is_conversational: bool = False
    ) -> Dict[str, Any]:
        """
        Generate answer using Gemini with context awareness.
        Enhanced to handle conversational flow and document scoping.
        
        Args:
            query: User's original question
            context: Retrieved context (can be empty for conversational)
            sources: Source documents
            conversation_history: Previous messages
            reformulated_query: Query enhanced with context (optional)
            conversation_context: Summary of conversation state
            is_conversational: If True, focus on natural conversation
            
        Returns:
            Dictionary with answer, citations, and metadata
        """
        logger.info(f"Generating answer: conversational={is_conversational}, sources={len(sources)}")
        
        recent_history = []
        if conversation_history and len(conversation_history) > 0:
            if len(conversation_history) > 2:
                recent_history = conversation_history[-2:]
            else:
                recent_history = [] 
        
        # Build the cacheable system context (changes infrequently)
        system_instruction = self._get_context_aware_system_instruction(conversation_context)
        
        # Build the variable user prompt
        if is_conversational or not context or len(context.strip()) < 50:
            user_prompt = self._build_conversational_prompt(
                query, recent_history, conversation_context
            )
        else:
            user_prompt = self._build_contextual_prompt(
                query, context, sources, reformulated_query, conversation_context
            )
        
        # Build messages array
        messages = []
        
        # Add system instruction (will be cached in future)
        messages.append({
            "role": "user",
            "parts": [system_instruction]
        })
        messages.append({
            "role": "model",
            "parts": ["Understood. I'll provide accurate, context-aware responses."]
        })
        
        # OPTIMIZATION: Only add last 2 history messages instead of 6
        for msg in recent_history:
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
            confidence = self._assess_confidence(answer, context, conversation_context)
            
            # Extract or calculate usage metadata
            usage = {}
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage_meta = response.usage_metadata
                
                # DEBUG: Log all available metadata attributes
                logger.info(f"🔍 DEBUG - Available metadata attributes: {dir(usage_meta)}")
                logger.info(f"🔍 DEBUG - Raw metadata: {usage_meta}")
                
                usage = {
                    'prompt_tokens': getattr(usage_meta, 'prompt_token_count', 0),
                    'completion_tokens': getattr(usage_meta, 'candidates_token_count', 0),
                    'total_tokens': getattr(usage_meta, 'total_token_count', 0),
                    'cached_tokens': getattr(usage_meta, 'cached_content_token_count', 0)
                }
                
                logger.info(f"📊 Token breakdown: Prompt={usage['prompt_tokens']}, "
                            f"Completion={usage['completion_tokens']}, "
                            f"Cached={usage['cached_tokens']}, "
                            f"Total={usage['total_tokens']}")
            else:
                # Use accurate token counting
                logger.warning(f"⚠️ API didn't return usage metadata, counting tokens manually")
                
                # Count tokens for each component
                system_tokens = self.count_tokens(system_instruction)
                
                # Count history tokens
                history_tokens = 0
                for msg in recent_history:
                    history_tokens += self.count_tokens(msg['content'])
                
                user_prompt_tokens = self.count_tokens(user_prompt)
                completion_tokens = self.count_tokens(answer)
                
                prompt_tokens = system_tokens + history_tokens + user_prompt_tokens
                total_tokens = prompt_tokens + completion_tokens
                
                usage = {
                    'prompt_tokens': prompt_tokens,
                    'completion_tokens': completion_tokens,
                    'total_tokens': total_tokens,
                    'cached_tokens': 0,
                    'breakdown': {
                        'system': system_tokens,
                        'history': history_tokens,
                        'user_prompt': user_prompt_tokens,
                        'completion': completion_tokens
                    }
                }
                
                logger.info(f"📊 Token breakdown - System: {system_tokens}, History: {history_tokens}, "
                           f"User: {user_prompt_tokens}, Completion: {completion_tokens}")
            
            logger.info(f"✅ Generated: {len(answer)} chars, {len(citations)} citations")
            logger.info(f"📊 Token usage: {usage['total_tokens']} total, {usage['cached_tokens']} cached")
            
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
    
    def _get_context_aware_system_instruction(
        self,
        conversation_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Get system instruction with minimal context additions.
        """
        # Use the base system instruction
        instruction = self.system_instruction
        
        # OPTIMIZATION: Only add context if it's significant
        if conversation_context:
            primary_doc = conversation_context.get('primary_document')
            
            if primary_doc:
                # Add minimal context hint (not full document name)
                instruction += f"\n\nCurrent focus: Document-scoped conversation."
        
        return instruction
    
    def _extract_citations(
        self,
        answer: str,
        sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Extract numbered citation references [1], [2], [3] from the answer text.
        
        Args:
            answer: Generated answer text
            sources: List of source documents
            
        Returns:
            List of citation dictionaries with document and page info
        """
        import re
        
        if not sources:
            return []
        
        # Pattern to match [1], [2,3], [1,2,3] format
        citation_pattern = r'\[(\d+(?:,\s*\d+)*)\]'
        
        matches = re.findall(citation_pattern, answer)
        
        if not matches:
            logger.warning(f"No citations found in answer despite {len(sources)} sources available")
            return []
        
        # Extract all unique citation numbers
        cited_numbers = set()
        for match in matches:
            # Split comma-separated numbers: "1,2,3" -> [1, 2, 3]
            numbers = [int(n.strip()) for n in match.split(',')]
            cited_numbers.update(numbers)
        
        logger.info(f"Found citations for source numbers: {sorted(cited_numbers)}")
        
        # Map citation numbers to actual sources
        citations = []
        for cite_num in sorted(cited_numbers):
            # Sources are 1-indexed in the prompt
            source_idx = cite_num - 1
            
            if 0 <= source_idx < len(sources):
                source = sources[source_idx]
                
                citation = {
                    'document': source.get('document', 'Unknown'),
                    'page': source.get('page'),
                    'chunk_id': source.get('chunk_id'),
                    'section': source.get('section'),
                    'citation_number': cite_num,
                    'text_reference': f"[{cite_num}]"
                }
                
                citations.append(citation)
            else:
                logger.warning(f"Citation [{cite_num}] refers to non-existent source (only {len(sources)} sources)")
        
        logger.info(f"Extracted {len(citations)} valid citations from answer")
        
        return citations

    def _build_contextual_prompt(
        self,
        query: str,
        context: str,
        sources: List[Dict[str, Any]],
        reformulated_query: Optional[str] = None,
        conversation_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Build context-aware prompt for document-based queries with numbered sources.
        
        Args:
            query: Original user query
            context: Retrieved document context
            sources: Source documents
            reformulated_query: Enhanced query with context
            conversation_context: Conversation state
            
        Returns:
            Formatted prompt with numbered sources
        """
        # Format sources with numbers
        sources_text = []
        for idx, src in enumerate(sources, start=1):
            source_line = f"[{idx}] {src['document']}"
            
            if src.get('page'):
                source_line += f", Page {src['page']}"
            
            if src.get('section'):
                source_line += f", Section: {src['section']}"
            
            sources_text.append(source_line)
        
        sources_formatted = "\n".join(sources_text)
        
        prompt_parts = []
        
        # Add conversation context if available
        if conversation_context:
            primary_doc = conversation_context.get('primary_document')
            if primary_doc:
                prompt_parts.append(f"**Context**: We are currently discussing '{primary_doc}'")
        
        # Show both original and reformulated query if different
        if reformulated_query and reformulated_query != query:
            prompt_parts.append(f"**User's Question**: {query}")
            prompt_parts.append(f"**Interpreted as**: {reformulated_query}")
        else:
            prompt_parts.append(f"**Question**: {query}")
        
        prompt_parts.append(f"""
    **Available Context from Documents**:
    {context}

    **Source References** (use these numbers in your citations):
    {sources_formatted}

    **Critical Instructions**:
    1. Answer based ONLY on the context above
    2. **MUST cite sources using [1], [2], [3] format**
    3. Place citations immediately after facts: "The policy is X [1]."
    4. If multiple sources support a fact: "This applies to all branches [1,2]."
    5. If this is a follow-up question, connect it to previous context
    6. If context is insufficient, clearly state what's missing
    7. For financial data, include exact figures with citations
    8. **If the context contains tables, present them in Markdown table format**
    9. Be conversational and empathetic in your response

    **Formatting**:
    - Use **bold** for important points
    - Use bullet points for lists
    - Use clear paragraphs
    - **Use Markdown tables for tabular data**:
    | Column 1 | Column 2 |
    |----------|----------|
    | Value 1  | Value 2  |

    **Answer** (remember: MUST include [1], [2], [3] citations):""")
        
        return "\n\n".join(prompt_parts)
    
    def _build_conversational_prompt(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        conversation_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Build prompt for conversational queries (no document context).
        
        Args:
            query: User query
            conversation_history: Recent messages
            conversation_context: Conversation state
            
        Returns:
            Conversational prompt
        """
        prompt_parts = [f"**User**: {query}"]
        
        # Add context hints
        if conversation_context:
            message_count = conversation_context.get('message_count', 0)
            if message_count > 0:
                prompt_parts.append("\n**Context**: This is part of an ongoing conversation.")
        
        prompt_parts.append("""
**Instructions**:
- Respond naturally and conversationally
- If this is a greeting or small talk, respond warmly
- If the user is asking about documents but no context is available, guide them helpfully
- Use proper markdown formatting
- Be friendly and professional

**Response**:""")
        
        return "\n".join(prompt_parts)
    
    def _assess_confidence(
        self,
        answer: str,
        context: str,
        conversation_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Assess confidence level with context awareness.
        
        Args:
            answer: Generated answer
            context: Document context used
            conversation_context: Conversation state
            
        Returns:
            Confidence level: 'high', 'medium', 'low'
        """
        # High confidence indicators
        high_indicators = [
            'according to', 'states that', 'specified in',
            'the document shows', 'as per', 'clearly mentions'
        ]
        
        # Low confidence indicators
        low_indicators = [
            'not available', 'unclear', 'doesn\'t specify',
            'may', 'might', 'possibly', 'appears to', 'i don\'t have'
        ]
        
        answer_lower = answer.lower()
        
        # Check for uncertainty
        if any(indicator in answer_lower for indicator in low_indicators):
            return 'low'
        
        # Check for strong sourcing
        has_citations = '[document:' in answer_lower
        has_strong_language = any(indicator in answer_lower for indicator in high_indicators)
        
        if has_citations and has_strong_language:
            return 'high'
        
        # Context-based confidence
        if conversation_context:
            # If we're in a scoped document conversation with sources
            if conversation_context.get('primary_document') and has_citations:
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

    async def generate_follow_up_suggestions(
        self,
        prompt: str
    ) -> List[str]:
        """
        Generate intelligent follow-up question suggestions using Gemini Flash.
        Optimized for speed and cost with minimal tokens.
        
        Args:
            prompt: Comprehensive context prompt from suggestion_service
            
        Returns:
            List of 3-4 follow-up question strings
        """
        logger.info("Generating follow-up suggestions with Gemini Flash")
        
        try:
            loop = asyncio.get_event_loop()
            
            # Use Gemini Flash for fast, cheap generation
            response = await loop.run_in_executor(
                None,
                lambda: self.model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.7, 
                        "max_output_tokens": 300, 
                        "top_p": 0.9,
                    }
                )
            )
            
            answer = response.text
            
            # Parse suggestions (one per line)
            suggestions = [
                line.strip() 
                for line in answer.split('\n') 
                if line.strip() and len(line.strip()) > 10
            ]
            
            # Log token usage
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = response.usage_metadata
                total = getattr(usage, 'total_token_count', 0)
                cached = getattr(usage, 'cached_content_token_count', 0)
                
                logger.info(f"📊 Suggestion generation - Tokens: {total} (Cached: {cached})")
                
                # Calculate cost (Gemini Flash pricing)
                regular_tokens = total - cached
                cost = (cached * 0.00000003) + (regular_tokens * 0.0000003)
                logger.info(f"💰 Suggestion cost: ${cost:.6f}")
            
            logger.info(f"✅ Generated {len(suggestions)} suggestions")
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Suggestion generation failed: {str(e)}", exc_info=True)
            
            return []

# Global instance
llm_service = LLMService()

__all__ = ['LLMService', 'llm_service']
