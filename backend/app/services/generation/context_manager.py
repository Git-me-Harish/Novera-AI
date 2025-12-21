"""
Enhanced context management for conversational RAG.
Tracks document scope, entities, and conversation flow.
"""
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
from collections import defaultdict
from loguru import logger
import re


class ConversationContext:
    """
    Manages conversation context for a single conversation.
    Tracks documents, entities, and conversation state.
    """
    
    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        
        # Document context
        self.active_documents: Set[str] = set()  # Document IDs being discussed
        self.document_references: List[Dict[str, Any]] = []  # History of doc references
        self.primary_document: Optional[str] = None  # Main document in focus
        
        # Entity tracking
        self.entities: Dict[str, List[str]] = defaultdict(list)  # Type -> values
        self.financial_context: Dict[str, Any] = {}  # Financial-specific context
        
        # Time-based context
        self.time_periods: List[str] = []  # Q1 2024, FY2023, etc.
        self.last_time_reference: Optional[str] = None
        
        # Topic tracking
        self.topics: List[str] = []  # Main topics discussed
        self.current_topic: Optional[str] = None
        
        # Conversation state
        self.message_count = 0
        self.last_intent: Optional[str] = None
        self.expecting_clarification = False
        
        logger.info(f"Context initialized for conversation {conversation_id}")
    
    def update_from_query(self, query: str, processed_query: Dict[str, Any]):
        """
        Update context based on user query analysis.
        
        Args:
            query: Raw user query
            processed_query: Processed query from query_processor
        """
        self.updated_at = datetime.utcnow()
        self.message_count += 1
        
        # Update intent
        self.last_intent = processed_query.get('intent')
        
        # Update entities
        for entity_type, values in processed_query.get('entities', {}).items():
            self.entities[entity_type].extend(values)
            # Keep only last 10 of each type
            self.entities[entity_type] = self.entities[entity_type][-10:]
        
        # Extract time periods
        time_periods = self._extract_time_periods(query)
        if time_periods:
            self.time_periods.extend(time_periods)
            self.last_time_reference = time_periods[-1]
        
        logger.debug(f"Context updated: entities={len(self.entities)}, time_refs={len(self.time_periods)}")
    
    def update_from_retrieval(self, sources: List[Dict[str, Any]]):
        """
        Update context based on retrieval results.
        
        Args:
            sources: List of source documents/chunks used
        """
        if not sources:
            return
        
        # Extract unique document names/IDs
        for source in sources:
            doc_name = source.get('document')
            if doc_name:
                self.active_documents.add(doc_name)
                
                # Track reference
                self.document_references.append({
                    'document': doc_name,
                    'page': source.get('page'),
                    'timestamp': datetime.utcnow().isoformat(),
                    'message_index': self.message_count
                })
        
        # Set primary document (most frequently referenced)
        if self.active_documents:
            doc_counts = defaultdict(int)
            for ref in self.document_references[-10:]:  # Last 10 references
                doc_counts[ref['document']] += 1
            
            self.primary_document = max(doc_counts.items(), key=lambda x: x[1])[0]
        
        logger.debug(f"Active documents: {len(self.active_documents)}, primary: {self.primary_document}")
    
    def should_use_document_scope(self) -> bool:
        """
        Determine if we should scope retrieval to active documents.
        
        NEW LOGIC: Only scope if we have STRONG contextual evidence
        
        Returns:
            True if document scope should be applied
        """
        if not self.primary_document:
            return False
        
        if not self.document_references:
            return False
        
        last_ref = self.document_references[-1]
        messages_since = self.message_count - last_ref['message_index']
        
        # CRITICAL FIX: More lenient scoping
        # Only scope if:
        # 1. Very recent (within 3 messages) OR
        # 2. Multiple references to same document (within 8 messages)
        if messages_since <= 3:
            return True
        
        if messages_since <= 8:
            # Check if multiple recent references to same document
            recent_refs = [ref for ref in self.document_references[-5:] 
                        if ref['document'] == self.primary_document]
            return len(recent_refs) >= 2
        
        return False
        
        # Check recency
        last_ref = self.document_references[-1]
        messages_since = self.message_count - last_ref['message_index']
        
        return messages_since <= 5
    
    def get_document_filter(self) -> Optional[List[str]]:
        """
        Get list of documents to BOOST (not restrict) in retrieval.
        
        CHANGED: Now returns documents for boosting, not hard filtering
        
        Returns:
            List of document names to prioritize, or None for no boosting
        """
        if not self.should_use_document_scope():
            return None
        
        # Return primary + recently referenced docs for BOOSTING
        # NOT for hard filtering
        boost_docs = set()
        
        if self.primary_document:
            boost_docs.add(self.primary_document)
        
        # Add docs referenced in last 3 messages
        for ref in self.document_references[-3:]:
            boost_docs.add(ref['document'])
        
        result = list(boost_docs) if boost_docs else None
        
        if result:
            logger.info(f"Documents to BOOST (not filter): {result}")
        
        return result
    
    def should_expand_search(self, initial_results: List[Dict[str, Any]]) -> bool:
        """
        Determine if we should expand search beyond scoped documents.
        
        Args:
            initial_results: Results from scoped search
            
        Returns:
            True if we should do a global search
        """
        if not initial_results:
            logger.info("No scoped results - should expand search")
            return True
        
        # Check if results are actually relevant
        avg_score = sum(
            r.get('rerank_score', r.get('fused_score', r.get('similarity_score', 0)))
            for r in initial_results
        ) / len(initial_results)
        
        # If average relevance is low, expand search
        from app.core.config import settings
        threshold = settings.min_relevance_for_scoped_search
        
        if avg_score < threshold:
            logger.info(f"Low scoped relevance ({avg_score:.3f} < {threshold}) - expanding search")
            return True
        
        return False
    
    def detect_context_switch(self, query: str, processed_query: Dict[str, Any]) -> bool:
        """
        Detect if user is switching context/topic.
        
        Args:
            query: User query
            processed_query: Processed query data
            
        Returns:
            True if context switch detected
        """
        query_lower = query.lower()
        
        # Explicit switch indicators
        switch_phrases = [
            'different document',
            'another document',
            'other document',
            'switch to',
            'change topic',
            'new question',
            'instead',
            'let\'s talk about',
            'tell me about',
            'show me',
        ]
        
        for phrase in switch_phrases:
            if phrase in query_lower:
                logger.info(f"Context switch detected: '{phrase}'")
                return True
        
        # Intent change (e.g., from financial to procedural)
        new_intent = processed_query.get('intent')
        if self.last_intent and new_intent and new_intent != self.last_intent:
            # Allow some intent flexibility
            flexible_intents = ['general', 'factual']
            if new_intent not in flexible_intents and self.last_intent not in flexible_intents:
                logger.info(f"Intent switch: {self.last_intent} -> {new_intent}")
                return True
        
        return False
    
    def reset_document_scope(self):
        """Reset document-specific context (on context switch)."""
        logger.info("Resetting document scope")
        self.active_documents.clear()
        self.document_references.clear()
        self.primary_document = None
    
    def get_context_summary(self) -> Dict[str, Any]:
        """
        Get summary of current context state.
        
        Returns:
            Dictionary with context information
        """
        return {
            'conversation_id': self.conversation_id,
            'message_count': self.message_count,
            'primary_document': self.primary_document,
            'active_documents': list(self.active_documents),
            'recent_time_period': self.last_time_reference,
            'entities': {k: v[-3:] for k, v in self.entities.items()},  # Last 3 of each
            'last_intent': self.last_intent,
            'age_minutes': (datetime.utcnow() - self.created_at).seconds / 60
        }
    
    def enhance_query_with_context(self, query: str) -> str:
        """
        Enhance query with contextual information.
        
        Args:
            query: Original user query
            
        Returns:
            Enhanced query string
        """
        enhancements = []
        
        # Add document context if relevant
        if self.primary_document and self.should_use_document_scope():
            enhancements.append(f"in document '{self.primary_document}'")
        
        # Add time period context if available
        if self.last_time_reference:
            # Check if query already mentions time
            if not re.search(r'\b(q[1-4]|fy|20\d{2}|quarter|year)\b', query.lower()):
                enhancements.append(f"for {self.last_time_reference}")
        
        if enhancements:
            enhanced = f"{query} ({' '.join(enhancements)})"
            logger.debug(f"Enhanced query: '{query}' -> '{enhanced}'")
            return enhanced
        
        return query
    
    def _extract_time_periods(self, text: str) -> List[str]:
        """Extract time period references from text."""
        patterns = [
            r'\bQ[1-4]\s*20\d{2}\b',  # Q1 2024
            r'\bFY\s*20\d{2}\b',       # FY2024
            r'\b20\d{2}\b',            # 2024
            r'\b(first|second|third|fourth)\s+quarter\b',
        ]
        
        periods = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            periods.extend(matches)
        
        return periods
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'conversation_id': self.conversation_id,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'active_documents': list(self.active_documents),
            'document_references': self.document_references,
            'primary_document': self.primary_document,
            'entities': dict(self.entities),
            'financial_context': self.financial_context,
            'time_periods': self.time_periods,
            'last_time_reference': self.last_time_reference,
            'topics': self.topics,
            'current_topic': self.current_topic,
            'message_count': self.message_count,
            'last_intent': self.last_intent,
        }


class ContextManager:
    """
    Manages conversation contexts across all conversations.
    """
    
    def __init__(self):
        self.contexts: Dict[str, ConversationContext] = {}
        self.context_timeout = timedelta(hours=1)  # Clear old contexts
        logger.info("ContextManager initialized")
    
    def get_or_create_context(self, conversation_id: str) -> ConversationContext:
        """Get existing context or create new one."""
        if conversation_id not in self.contexts:
            self.contexts[conversation_id] = ConversationContext(conversation_id)
        return self.contexts[conversation_id]
    
    def update_context(
        self,
        conversation_id: str,
        query: str,
        processed_query: Dict[str, Any],
        sources: Optional[List[Dict[str, Any]]] = None
    ) -> ConversationContext:
        """
        Update context with new query and results.
        
        Args:
            conversation_id: Conversation ID
            query: User query
            processed_query: Processed query data
            sources: Retrieval sources (if available)
            
        Returns:
            Updated context
        """
        context = self.get_or_create_context(conversation_id)
        
        # Check for context switch
        if context.detect_context_switch(query, processed_query):
            context.reset_document_scope()
        
        # Update from query
        context.update_from_query(query, processed_query)
        
        # Update from sources if provided
        if sources:
            context.update_from_retrieval(sources)
        
        return context
    
    def get_context(self, conversation_id: str) -> Optional[ConversationContext]:
        """Get context for conversation."""
        return self.contexts.get(conversation_id)
    
    def cleanup_old_contexts(self):
        """Remove expired contexts."""
        now = datetime.utcnow()
        to_remove = []
        
        for conv_id, context in self.contexts.items():
            age = now - context.updated_at
            if age > self.context_timeout:
                to_remove.append(conv_id)
        
        for conv_id in to_remove:
            del self.contexts[conv_id]
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} expired contexts")


# Global instance
context_manager = ContextManager()

__all__ = ['ContextManager', 'ConversationContext', 'context_manager']