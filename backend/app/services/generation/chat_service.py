"""
Seamless conversational RAG chat service.
Provides natural, AI-driven conversations with smart document retrieval.
"""
from typing import List, Dict, Any, Optional, AsyncGenerator
from datetime import datetime
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.retrieval.pipeline import retrieval_pipeline
from app.services.generation.llm_service import llm_service
from app.services.generation.guardrails import guardrails_service
from app.services.generation.conversation_manager import conversation_manager


class ChatService:
    """
    Complete RAG chat service with natural conversation flow.
    No templated responses - everything is AI-generated.
    """
    
    def _should_search_documents(self, query: str) -> bool:
        """
        Intelligently detect if query requires document search.
        
        Returns True if:
        - Query asks about specific information (what, how, when, explain)
        - Query mentions domain keywords (policy, salary, expense, etc.)
        - Query is asking for details or data
        
        Returns False if:
        - Simple greetings
        - General conversation
        - Acknowledgments
        """
        query_lower = query.lower().strip()
        words = query_lower.split()
        
        # Very short queries (1-3 words) are likely conversational
        if len(words) <= 3:
            conversational_words = [
                'hi', 'hello', 'hey', 'thanks', 'thank', 'ok', 'okay',
                'yes', 'no', 'sure', 'great', 'good', 'nice', 'bye'
            ]
            if any(word in query_lower for word in conversational_words):
                return False
        
        # Check for information-seeking keywords
        info_seeking = [
            'what', 'how', 'when', 'where', 'why', 'who', 'which',
            'explain', 'describe', 'tell me', 'show me', 'find',
            'about', 'regarding', 'concerning', 'details', 'information'
        ]
        
        if any(keyword in query_lower for keyword in info_seeking):
            return True
        
        # Check for domain keywords (finance/HR)
        domain_keywords = [
            'document', 'policy', 'salary', 'leave', 'expense', 'revenue',
            'employee', 'benefit', 'payment', 'report', 'finance', 'hr',
            'budget', 'cost', 'profit', 'loss', 'quarter', 'annual',
            'reimbursement', 'allowance', 'deduction', 'compliance'
        ]
        
        if any(keyword in query_lower for keyword in domain_keywords):
            return True
        
        # Default: search if query is substantial (5+ words)
        return len(words) >= 5
    
    async def chat(
        self,
        query: str,
        conversation_id: Optional[str],
        user_id: str,
        db: AsyncSession,
        doc_type: Optional[str] = None,
        department: Optional[str] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Process chat query with intelligent document search detection.
        """
        logger.info(f"📨 Chat: '{query[:50]}...' (user: {user_id})")
        
        # Step 1: Input validation (permissive)
        is_valid, error_msg = guardrails_service.validate_input(query)
        
        if not is_valid:
            logger.warning(f"Input validation failed: {error_msg}")
            # Return validation error as conversational response
            return await self._generate_conversational_response(
                query, conversation_id, user_id, db, error_msg, is_error=True
            )
        
        # Step 2: Get or create conversation
        if not conversation_id:
            conversation_id = conversation_manager.create_conversation(
                user_id=user_id,
                metadata={'doc_type': doc_type, 'department': department}
            )
            logger.info(f"Created conversation: {conversation_id}")
        
        # Add user message
        conversation_manager.add_message(
            conversation_id=conversation_id,
            role='user',
            content=query
        )
        
        # Step 3: Determine if we need to search documents
        should_search = self._should_search_documents(query)
        logger.info(f"Document search: {'YES' if should_search else 'NO'}")
        
        context = ""
        sources = []
        chunks_used = 0
        retrieval_metadata = {}
        
        if should_search:
            # Step 4: Retrieve from documents
            try:
                logger.info("🔍 Searching documents...")
                retrieval_result = await retrieval_pipeline.retrieve(
                    query=query,
                    db=db,
                    top_k=8,
                    doc_type=doc_type,
                    department=department,
                    include_context=True
                )
                
                context = retrieval_result['context_text']
                sources = retrieval_result['sources']
                chunks_used = len(retrieval_result['chunks'])
                retrieval_metadata = retrieval_result.get('retrieval_metadata', {})
                
                logger.info(f"Retrieved {chunks_used} chunks")
                
            except Exception as e:
                logger.error(f"Retrieval failed: {str(e)}", exc_info=True)
                # Don't fail - continue with conversational response
                context = ""
                sources = []
         # Step 5: Generate AI response
        generation_result = None
        answer = ""
        citations = []
        
        try:
            history = conversation_manager.get_history(conversation_id, limit=3)
            
            if stream:
                return await self._chat_stream(
                    query, context, sources, history,
                    conversation_id, retrieval_metadata
                )
            
            # Generate answer (AI decides how to respond based on context)
            generation_result = await llm_service.generate_answer(
                query=query,
                context=context if context else "No specific document context available.",
                sources=sources,
                conversation_history=history,
                is_conversational=not should_search
            )
            
            answer = generation_result['answer']
            citations = generation_result.get('citations', [])
            
            logger.info(f"✅ Generated: {len(answer)} chars, {len(citations)} citations")
            
        except Exception as e:
            logger.error(f"Generation failed: {str(e)}", exc_info=True)
            answer = "I encountered an issue generating a response. Could you try rephrasing your question?"
            citations = []
            generation_result = {
                'answer': answer,
                'citations': citations,
                'confidence': 'low',
                'usage': {'total_tokens': 0}
            }
        
        # Step 6: Save assistant message
        conversation_manager.add_message(
            conversation_id=conversation_id,
            role='assistant',
            content=answer,
            metadata={
                'citations': citations,
                'sources': sources,
                'tokens': generation_result.get('usage', {}) if generation_result else {},
                'searched_documents': should_search,
                'chunks_used': chunks_used
            }
        )
        
        # Step 7: Return response
        logger.info("=" * 60)
        if sources and len(sources) > 0:
            logger.info("✅ RESPONSE SOURCE: DOCUMENTS")
            logger.info(f"   📄 Documents used: {len(set(s['document'] for s in sources))}")
            logger.info(f"   📑 Total chunks: {chunks_used}")
            logger.info(f"   📌 Citations: {len(citations)}")
            for src in sources[:3]:
                logger.info(f"      - {src['document']} (Page {src.get('page', 'N/A')})")
        else:
            logger.info("🤖 RESPONSE SOURCE: API/LLM (Fallback)")
            logger.info(f"   ⚠️  Reason: {'No documents found' if should_search else 'Conversational query'}")
        logger.info("=" * 60)
        return {
            'answer': answer,
            'conversation_id': conversation_id,
            'sources': sources,
            'citations': citations,
            'confidence': generation_result.get('confidence', 'medium') if generation_result else 'low',
            'status': 'success',
            'metadata': {
                'chunks_used': chunks_used,
                'tokens': generation_result.get('usage', {}) if generation_result else {},
                'searched_documents': should_search,
                'retrieval_metadata': retrieval_metadata
            }
        }
    
    async def _generate_conversational_response(
        self,
        query: str,
        conversation_id: Optional[str],
        user_id: str,
        db: AsyncSession,
        context_message: str,
        is_error: bool = False
    ) -> Dict[str, Any]:
        """Generate a conversational response without document search."""
        if not conversation_id:
            conversation_id = conversation_manager.create_conversation(user_id=user_id)
        
        conversation_manager.add_message(conversation_id, 'user', query)
        
        # Let AI generate response
        history = conversation_manager.get_history(conversation_id, limit=3)
        
        try:
            result = await llm_service.generate_conversational_response(
                query=query,
                context_message=context_message,
                history=history,
                is_error=is_error
            )
            
            answer = result['answer']
        except:
            answer = context_message
        
        conversation_manager.add_message(
            conversation_id, 'assistant', answer,
            metadata={'type': 'conversational'}
        )
        
        return {
            'answer': answer,
            'conversation_id': conversation_id,
            'sources': [],
            'citations': [],
            'confidence': 'high',
            'status': 'success' if not is_error else 'rejected',
            'metadata': {'type': 'conversational'}
        }
    
    async def _chat_stream(
        self,
        query: str,
        context: str,
        sources: list,
        history: list,
        conversation_id: str,
        retrieval_metadata: dict
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream chat response."""
        yield {
            'type': 'metadata',
            'conversation_id': conversation_id,
            'sources': sources,
            'retrieval_metadata': retrieval_metadata
        }
        
        full_answer = ""
        
        async for chunk in llm_service.generate_answer_stream(
            query=query,
            context=context,
            sources=sources,
            conversation_history=history
        ):
            full_answer += chunk
            yield {'type': 'content', 'content': chunk}
        
        conversation_manager.add_message(
            conversation_id, 'assistant', full_answer,
            metadata={'sources': sources}
        )
        
        yield {'type': 'done', 'conversation_id': conversation_id}
    
    async def get_conversation_history(
        self,
        conversation_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """Get conversation history."""
        conversation = conversation_manager.get_conversation(conversation_id)
        
        if not conversation:
            return {'error': 'Conversation not found'}
        
        if conversation['user_id'] != user_id:
            return {'error': 'Unauthorized'}
        
        return conversation
    
    async def list_conversations(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """List user conversations."""
        conversations = conversation_manager.list_user_conversations(user_id, limit)
        
        return [
            {**conv, 'summary': conversation_manager.summarize_conversation(conv['id'])}
            for conv in conversations
        ]
    
    async def delete_conversation(
        self,
        conversation_id: str,
        user_id: str
    ) -> bool:
        """Delete conversation."""
        conversation = conversation_manager.get_conversation(conversation_id)
        
        if not conversation or conversation['user_id'] != user_id:
            return False
        
        return conversation_manager.delete_conversation(conversation_id)


# Global instance
chat_service = ChatService()

__all__ = ['ChatService', 'chat_service']