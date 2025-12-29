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
from app.services.generation.context_manager import context_manager
from app.services.retrieval.query_processor import query_processor
from app.services.generation.suggestion_service import suggestion_service 


class ChatService:
    """
    Complete RAG chat service with natural conversation flow.
    No templated responses - everything is AI-generated.
    """
    
    async def _should_search_documents(
        self, 
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> bool:
        """
        Use pure LLM understanding to determine if document search is needed.
        No hardcoded rules - only semantic understanding.
        
        Args:
            query: User's query
            conversation_history: Recent conversation for context
            
        Returns:
            True if document search needed, False for conversational response
        """
        from app.services.generation.query_classifier import query_classifier
        
        # Use LLM to classify with full understanding
        classification = await query_classifier.classify_query(query, conversation_history)
        
        classification_type = classification['type']
        reasoning = classification['reasoning']
        confidence = classification['confidence']
        
        should_search = (classification_type == 'document')
        
        # Log the decision with reasoning
        if should_search:
            logger.info(f"📄 DOCUMENT SEARCH NEEDED")
            logger.info(f"   Query: '{query}'")
            logger.info(f"   Reason: {reasoning}")
            logger.info(f"   Confidence: {confidence}")
        else:
            logger.info(f"🗣️ CONVERSATIONAL RESPONSE")
            logger.info(f"   Query: '{query}'")
            logger.info(f"   Reason: {reasoning}")
            logger.info(f"   Confidence: {confidence}")
        
        return should_search
    
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
        Process chat query with intelligent context awareness.
        Now includes document-scoped context and conversational continuity.
        """
        # IMPORT at top of file
        from app.services.generation.context_manager import context_manager
        
        logger.info(f"📨 Chat: '{query[:50]}...' (user: {user_id})")
        
        # Step 1: Input validation (permissive)
        is_valid, error_msg = guardrails_service.validate_input(query)
        
        if not is_valid:
            logger.warning(f"Input validation failed: {error_msg}")
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
        
        # Step 3: Process query with context awareness
        processed_query = query_processor.process_query(query)
        
        # Step 4: Get/update conversation context
        conv_context = context_manager.get_or_create_context(conversation_id)
        
        # Update context with query
        conv_context.update_from_query(query, processed_query)
        
        # Step 5: Reformulate query using context (for follow-ups)
        reformulated_query = query_processor.reformulate_with_context(
            query, conv_context
        )
        
        logger.info(f"🔄 Query reformulation: '{query}' -> '{reformulated_query}'")
        
        # Step 6: Use intelligent LLM classification to determine search need
        history = conversation_manager.get_history(conversation_id, limit=2) if conversation_id else []
        should_search = await self._should_search_documents(reformulated_query, history)
        
        context = ""
        sources = []
        chunks_used = 0
        retrieval_metadata = {}
        
        if should_search:
            # Step 7: Intelligent document retrieval with dynamic scoping
            try:
                logger.info("🔍 Searching documents with dynamic scoping...")
                
                from app.core.config import settings
                
                # Determine initial search mode
                use_scoped_initially = conv_context.should_use_document_scope() if conv_context else False
                
                if use_scoped_initially:
                    logger.info("📄 Starting with scoped search (will expand if needed)")
                else:
                    logger.info("🌐 Starting with global search")
                
                retrieval_result = await retrieval_pipeline.retrieve(
                    query=reformulated_query,
                    db=db,
                    top_k=settings.global_search_top_k, 
                    doc_type=doc_type,
                    department=department,
                    include_context=True,
                    conversation_context=conv_context,
                    force_global=False 
                )
                
                context = retrieval_result['context_text']
                sources = retrieval_result['sources']
                chunks_used = len(retrieval_result['chunks'])
                retrieval_metadata = retrieval_result.get('retrieval_metadata', {})
                
                # Update context with retrieval results
                if conv_context:
                    conv_context.update_from_retrieval(sources)
                
                # Log search outcome
                search_type = retrieval_metadata.get('search_type', 'unknown')
                expanded = retrieval_metadata.get('expanded_to_global', False)
                
                if expanded:
                    logger.info(f"✅ Retrieved {chunks_used} chunks (expanded from scoped to global search)")
                else:
                    logger.info(f"✅ Retrieved {chunks_used} chunks ({search_type} search)")

            except Exception as e:
                logger.error(f"Retrieval failed: {str(e)}", exc_info=True)
                context = ""
                sources = []
        
        # Step 8: Generate AI response with context awareness
        generation_result = None
        answer = ""
        citations = []
        
        try:
            history = conversation_manager.get_history(conversation_id, limit=5)  # More history for context
            
            if stream:
                return await self._chat_stream(
                    query, context, sources, history,
                    conversation_id, retrieval_metadata, conv_context
                )
            
            # Add context summary to generation
            context_summary = conv_context.get_context_summary()
            
            # Generate answer with context
            generation_result = await llm_service.generate_answer(
                query=query,  # Original query for natural response
                reformulated_query=reformulated_query,  # For context
                context=context if context else "No specific document context available.",
                sources=sources,
                conversation_history=history,
                conversation_context=context_summary,
                is_conversational=not should_search
            )
            
            answer = generation_result['answer']
            citations = generation_result.get('citations', [])
            
            logger.info(f"✅ Generated: {len(answer)} chars, {len(citations)} citations")

            if generation_result:
                usage = generation_result.get('usage', {})
                logger.info(f"TOKEN USAGE - Total: {usage.get('total_tokens', 0)}, "
                            f"Cached: {usage.get('cached_tokens', 0)}, "
                            f"Prompt: {usage.get('prompt_tokens', 0)}, "
                            f"Completion: {usage.get('completion_tokens', 0)}")
                
                # Calculate estimated cost
                total_tokens = usage.get('total_tokens', 0)
                cached_tokens = usage.get('cached_tokens', 0)
                regular_tokens = total_tokens - cached_tokens
                
                # Gemini 1.5 Flash pricing
                cost = (cached_tokens * 0.00000003) + (regular_tokens * 0.0000003)
                logger.info(f"ESTIMATED COST: ${cost:.6f}")
            
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
        
        # Step 9: Save assistant message with context
        conversation_manager.add_message(
            conversation_id=conversation_id,
            role='assistant',
            content=answer,
            metadata={
                'citations': citations,
                'sources': sources,
                'tokens': generation_result.get('usage', {}) if generation_result else {},
                'searched_documents': should_search,
                'chunks_used': chunks_used,
                'context_used': conv_context.to_dict(),
                'reformulated_query': reformulated_query if reformulated_query != query else None
            }
        )
        
        # Step 10: Return response with context info
        logger.info("=" * 60)
        if sources and len(sources) > 0:
            logger.info("✅ RESPONSE SOURCE: DOCUMENTS")
            logger.info(f"   📄 Primary document: {conv_context.primary_document}")
            logger.info(f"   📑 Total chunks: {chunks_used}")
            logger.info(f"   📌 Citations: {len(citations)}")
        else:
            logger.info("🤖 RESPONSE SOURCE: CONVERSATIONAL")
        logger.info("=" * 60)
        
        # Generate smart suggestions with full context
        suggestions = []
        try:
            # Pass conversation history for better context
            history_for_suggestions = conversation_manager.get_history(conversation_id, limit=2) if conversation_id else []
            
            suggestions = await suggestion_service.generate_suggestions(
                last_query=query,
                last_response=answer,
                context_summary=conv_context.get_context_summary(),
                sources=sources,
                conversation_history=history_for_suggestions  # ← NEW: Added conversation history
            )
            
            # Filter by confidence if needed
            if generation_result and generation_result.get('confidence') == 'low':
                suggestions = suggestion_service.filter_suggestions_by_confidence(
                    suggestions,
                    'low'
                )
            
            logger.info(f"✅ Generated {len(suggestions)} LLM-powered suggestions: {suggestions}")
            
        except Exception as e:
            logger.error(f"Suggestion generation failed: {str(e)}", exc_info=True)
            suggestions = []
            
            # Filter by confidence if needed
            if generation_result and generation_result.get('confidence') == 'low':
                suggestions = suggestion_service.filter_suggestions_by_confidence(
                    suggestions,
                    'low'
                )
            
            logger.info(f"Generated {len(suggestions)} smart suggestions: {suggestions}")
        except Exception as e:
            logger.error(f"Suggestion generation failed: {str(e)}", exc_info=True)
            suggestions = []
        
        # ✅ MUST be at top level, NOT in metadata
        response_data = {
            'answer': answer,
            'conversation_id': conversation_id,
            'sources': sources,
            'citations': citations,
            'confidence': generation_result.get('confidence', 'medium') if generation_result else 'low',
            'status': 'success',
            'suggestions': suggestions, 
            'metadata': {
                'chunks_used': chunks_used,
                'tokens': generation_result.get('usage', {}) if generation_result else {},
                'searched_documents': should_search,
                'retrieval_metadata': retrieval_metadata,
                'context_summary': conv_context.get_context_summary(),
                'query_reformulated': reformulated_query != query
            }
        }
        
        logger.debug(f"Returning response with suggestions: {response_data.get('suggestions')}")
        
        return response_data

        """return {
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
                'retrieval_metadata': retrieval_metadata,
                'context_summary': conv_context.get_context_summary(),  # Include context in response
                'query_reformulated': reformulated_query != query
            }
        }"""
        
    
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