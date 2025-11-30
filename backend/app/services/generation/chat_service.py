"""
Complete chat service orchestrator.
Coordinates retrieval, generation, guardrails, and conversation management.
"""
from typing import Dict, Any, Optional, AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.services.retrieval.pipeline import retrieval_pipeline
from app.services.generation.llm_service import llm_service
from app.services.generation.guardrails import guardrails_service
from app.services.generation.conversation_manager import conversation_manager


class ChatService:
    """
    Complete RAG chat service.
    Orchestrates the entire query → answer pipeline with safety checks.
    """
    
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
        Process a chat query through the complete RAG pipeline.
        
        Args:
            query: User's question
            conversation_id: Existing conversation ID (or None for new)
            user_id: User identifier
            db: Database session
            doc_type: Filter by document type
            department: Filter by department
            stream: Whether to stream response
            
        Returns:
            Complete chat response with answer and metadata
        """
        logger.info(f"📨 Chat request: '{query[:50]}...' (user: {user_id})")
        
        # Step 1: Input Guardrails
        is_valid, error_msg = guardrails_service.validate_input(query)
        
        if not is_valid:
            logger.warning(f"❌ Input validation failed: {error_msg}")
            return {
                'answer': f"I cannot process this query: {error_msg}",
                'error': error_msg,
                'status': 'rejected',
                'conversation_id': conversation_id
            }
        
        # Step 2: Get or create conversation
        if not conversation_id:
            conversation_id = conversation_manager.create_conversation(
                user_id=user_id,
                metadata={'doc_type': doc_type, 'department': department}
            )
            logger.info(f"Created new conversation: {conversation_id}")
        
        # Add user message to history
        conversation_manager.add_message(
            conversation_id=conversation_id,
            role='user',
            content=query
        )
        
        # Step 3: Retrieve relevant context
        logger.info("🔍 Retrieving context...")
        
        try:
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
            
            logger.info(f"✅ Retrieved {chunks_used} chunks ({retrieval_result['total_tokens']} tokens)")
            
        except Exception as e:
            logger.error(f"❌ Retrieval failed: {str(e)}")
            return {
                'answer': "I encountered an error while searching for information. Please try again.",
                'error': str(e),
                'status': 'retrieval_error',
                'conversation_id': conversation_id
            }
        
        # Check if we have relevant context
        if not context or len(context.strip()) < 50:
            logger.warning("⚠️  No relevant context found")
            
            no_info_response = """I couldn't find relevant information in the knowledge base to answer your question. 

This could be because:
1. The information is not in the uploaded documents
2. The question requires information from documents not yet processed
3. The query might be outside the scope of available documentation

Please try:
- Rephrasing your question
- Being more specific
- Asking about topics covered in the available documents"""
            
            conversation_manager.add_message(
                conversation_id=conversation_id,
                role='assistant',
                content=no_info_response,
                metadata={'status': 'no_context'}
            )
            
            return {
                'answer': no_info_response,
                'sources': [],
                'status': 'no_context',
                'conversation_id': conversation_id,
                'retrieval_metadata': retrieval_result.get('retrieval_metadata', {})
            }
        
        # Step 4: Generate answer
        logger.info("💬 Generating answer...")
        
        try:
            # Get conversation history
            history = conversation_manager.get_history(
                conversation_id=conversation_id,
                limit=3  # Last 3 exchanges
            )
            
            if stream:
                # Return streaming generator
                return await self._chat_stream(
                    query=query,
                    context=context,
                    sources=sources,
                    history=history,
                    conversation_id=conversation_id,
                    retrieval_result=retrieval_result
                )
            else:
                # Generate complete answer
                generation_result = await llm_service.generate_answer(
                    query=query,
                    context=context,
                    sources=sources,
                    conversation_history=history
                )
                
                answer = generation_result['answer']
                citations = generation_result['citations']
                
                logger.info(f"✅ Generated answer: {len(answer)} chars, {len(citations)} citations")
            
        except Exception as e:
            logger.error(f"❌ Generation failed: {str(e)}")
            return {
                'answer': "I encountered an error while generating the answer. Please try again.",
                'error': str(e),
                'status': 'generation_error',
                'conversation_id': conversation_id
            }
        
        # Step 5: Output Guardrails
        is_valid_output, warning, validation_details = guardrails_service.validate_output(
            query=query,
            answer=answer,
            context=context,
            sources=sources
        )
        
        if not is_valid_output:
            logger.warning(f"❌ Output validation failed: {warning}")
            
            # Return a safe fallback response
            fallback = """I found relevant information but need to verify it before providing an answer. 

Here are the source documents that may help:
""" + "\n".join([f"- {src['document']}, Page {src['page']}" for src in sources[:3]])
            
            answer = fallback
            validation_details['fallback_used'] = True
        
        # Sanitize output
        answer = guardrails_service.sanitize_output(answer)
        
        # Step 6: Save assistant message
        conversation_manager.add_message(
            conversation_id=conversation_id,
            role='assistant',
            content=answer,
            metadata={
                'citations': citations,
                'sources': sources,
                'tokens': generation_result['usage'],
                'validation': validation_details,
                'retrieval': retrieval_result.get('retrieval_metadata', {})
            }
        )
        
        # Update conversation context
        conversation_manager.update_context(
            conversation_id=conversation_id,
            context_updates={
                'last_intent': retrieval_result['processed_query']['intent'],
                'last_doc_type': doc_type,
                'topics': conversation_manager.get_context(conversation_id).get('topics', [])
            }
        )
        
        # Step 7: Return complete response
        return {
            'answer': answer,
            'conversation_id': conversation_id,
            'sources': sources,
            'citations': citations,
            'confidence': generation_result['confidence'],
            'status': 'success',
            'metadata': {
                'chunks_used': chunks_used,
                'tokens': generation_result['usage'],
                'retrieval_strategy': retrieval_result['retrieval_metadata']['search_strategy'],
                'intent': retrieval_result['processed_query']['intent'],
                'validation': validation_details
            }
        }
    
    async def _chat_stream(
        self,
        query: str,
        context: str,
        sources: list,
        history: list,
        conversation_id: str,
        retrieval_result: dict
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream chat response for real-time display.
        
        Yields:
            Response chunks with metadata
        """
        # First, yield metadata
        yield {
            'type': 'metadata',
            'conversation_id': conversation_id,
            'sources': sources,
            'retrieval_metadata': retrieval_result.get('retrieval_metadata', {})
        }
        
        # Stream answer chunks
        full_answer = ""
        
        async for chunk in llm_service.generate_answer_stream(
            query=query,
            context=context,
            sources=sources,
            conversation_history=history
        ):
            full_answer += chunk
            
            yield {
                'type': 'content',
                'content': chunk
            }
        
        # Save complete answer to conversation
        conversation_manager.add_message(
            conversation_id=conversation_id,
            role='assistant',
            content=full_answer,
            metadata={
                'sources': sources,
                'retrieval': retrieval_result.get('retrieval_metadata', {})
            }
        )
        
        # Final metadata
        yield {
            'type': 'done',
            'conversation_id': conversation_id
        }
    
    async def get_conversation_history(
        self,
        conversation_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get complete conversation history.
        
        Returns:
            Conversation object with all messages
        """
        conversation = conversation_manager.get_conversation(conversation_id)
        
        if not conversation:
            return {'error': 'Conversation not found'}
        
        # Verify ownership
        if conversation['user_id'] != user_id:
            return {'error': 'Unauthorized'}
        
        return conversation
    
    async def list_conversations(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        List user's conversations.
        
        Returns:
            List of conversation summaries
        """
        conversations = conversation_manager.list_user_conversations(
            user_id=user_id,
            limit=limit
        )
        
        # Add summaries
        return [
            {
                **conv,
                'summary': conversation_manager.summarize_conversation(conv['id'])
            }
            for conv in conversations
        ]
    
    async def delete_conversation(
        self,
        conversation_id: str,
        user_id: str
    ) -> bool:
        """ 
        Delete a conversation.
        
        Returns:
            True if deleted successfully
        """
        # Verify ownership
        conversation = conversation_manager.get_conversation(conversation_id)
        
        if not conversation or conversation['user_id'] != user_id:
            return False
        
        return conversation_manager.delete_conversation(conversation_id)


# Global instance
chat_service = ChatService()

__all__ = ['ChatService', 'chat_service']