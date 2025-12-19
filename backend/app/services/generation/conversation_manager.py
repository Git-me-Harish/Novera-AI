"""
Conversation management service.
Handles chat history, context tracking, and session management.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import UUID, uuid4
import json
from loguru import logger


class ConversationManager:
    """
    Manages conversation state and history for chat sessions.
    Provides context-aware conversation handling.
    """
    
    def __init__(self):
        # In-memory storage
        self.conversations: Dict[str, Dict[str, Any]] = {}
        self.max_history_length = 3
        self.session_timeout = 3600
    
    def create_conversation(
        self,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new conversation session.
        
        Args:
            user_id: ID of the user
            metadata: Optional conversation metadata
            
        Returns:
            Conversation ID
        """
        conversation_id = str(uuid4())
        
        self.conversations[conversation_id] = {
            'id': conversation_id,
            'user_id': user_id,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'messages': [],
            'metadata': metadata or {},
            'context': {}  # Store conversation context
        }
        
        logger.info(f"Created conversation: {conversation_id} for user: {user_id}")
        
        return conversation_id
    
    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Add a message to conversation history."""
        if conversation_id not in self.conversations:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        message = {
            'id': str(uuid4()),
            'role': role,
            'content': content,
            'timestamp': datetime.utcnow().isoformat(),
            'metadata': metadata or {}
        }
        
        conversation = self.conversations[conversation_id]
        conversation['messages'].append(message)
        conversation['updated_at'] = datetime.utcnow().isoformat()
        
        if metadata and 'context_used' in metadata:
            context_data = metadata['context_used']
            if 'primary_document' in context_data:
                conversation['context']['primary_document'] = context_data['primary_document']
            if 'active_documents' in context_data:
                conversation['context']['active_documents'] = context_data['active_documents']
        
        if len(conversation['messages']) > 10:
            conversation['messages'] = (
                conversation['messages'][:1] + 
                conversation['messages'][-9:] 
            )
        
        logger.debug(f"Added {role} message to conversation {conversation_id}")
        
        return message
    
    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve conversation by ID.
        
        Returns:
            Conversation object or None
        """
        return self.conversations.get(conversation_id)
    
    def get_history(
        self,
        conversation_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        Get conversation history in OpenAI format.
        
        Args:
            conversation_id: Conversation ID
            limit: Number of recent exchanges to return
            
        Returns:
            List of messages in {role, content} format
        """
        conversation = self.get_conversation(conversation_id)
        
        if not conversation:
            return []
        
        messages = conversation['messages']
        
        # Apply limit if specified
        if limit:
            messages = messages[-(limit * 2):]  # Each exchange = 2 messages
        
        # Format for OpenAI API
        return [
            {'role': msg['role'], 'content': msg['content']}
            for msg in messages
        ]
    
    def update_context(
        self,
        conversation_id: str,
        context_updates: Dict[str, Any]
    ) -> None:
        """
        Update conversation context (topics, entities, preferences).
        
        Args:
            conversation_id: Conversation ID
            context_updates: Dictionary of context updates
        """
        if conversation_id not in self.conversations:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        conversation = self.conversations[conversation_id]
        
        # FIXED: Properly merge dictionaries instead of using .update()
        current_context = conversation.get('context', {})
        new_context = {**current_context, **context_updates}
        conversation['context'] = new_context
        conversation['updated_at'] = datetime.utcnow().isoformat()
        
        logger.debug(f"Updated context for conversation {conversation_id}")
    
    def get_context(self, conversation_id: str) -> Dict[str, Any]:
        """
        Get conversation context.
        
        Returns:
            Context dictionary
        """
        conversation = self.get_conversation(conversation_id)
        return conversation.get('context', {}) if conversation else {}
    
    def summarize_conversation(
        self,
        conversation_id: str
    ) -> Dict[str, Any]:
        """
        Generate summary of conversation.
        
        Returns:
            Summary with key metrics
        """
        conversation = self.get_conversation(conversation_id)
        
        if not conversation:
            return {}
        
        messages = conversation['messages']
        
        # Count messages by role
        user_messages = [m for m in messages if m['role'] == 'user']
        assistant_messages = [m for m in messages if m['role'] == 'assistant']
        
        # Extract topics from context
        topics = conversation.get('context', {}).get('topics', [])
        
        return {
            'conversation_id': conversation_id,
            'total_messages': len(messages),
            'user_messages': len(user_messages),
            'assistant_messages': len(assistant_messages),
            'duration': self._calculate_duration(conversation),
            'topics_discussed': topics,
            'created_at': conversation['created_at'],
            'last_activity': conversation['updated_at']
        }
    
    def delete_conversation(self, conversation_id: str) -> bool:
        """
        Delete a conversation.
        
        Returns:
            True if deleted, False if not found
        """
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
            logger.info(f"Deleted conversation: {conversation_id}")
            return True
        
        return False
    
    def list_user_conversations(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        List all conversations for a user.
        
        Args:
            user_id: User ID
            limit: Maximum conversations to return
            
        Returns:
            List of conversation summaries
        """
        user_convos = [
            conv for conv in self.conversations.values()
            if conv['user_id'] == user_id
        ]
        
        # Sort by updated_at (most recent first)
        user_convos.sort(
            key=lambda x: x['updated_at'],
            reverse=True
        )
        
        return user_convos[:limit]
    
    def cleanup_old_conversations(self) -> int:
        """
        Remove conversations older than session timeout.
        
        Returns:
            Number of conversations deleted
        """
        now = datetime.utcnow()
        to_delete = []
        
        for conv_id, conv in self.conversations.items():
            updated_at = datetime.fromisoformat(conv['updated_at'])
            age_seconds = (now - updated_at).total_seconds()
            
            if age_seconds > self.session_timeout:
                to_delete.append(conv_id)
        
        for conv_id in to_delete:
            del self.conversations[conv_id]
        
        if to_delete:
            logger.info(f"Cleaned up {len(to_delete)} old conversations")
        
        return len(to_delete)
    
    def _calculate_duration(self, conversation: Dict[str, Any]) -> str:
        """Calculate conversation duration in human-readable format."""
        created = datetime.fromisoformat(conversation['created_at'])
        updated = datetime.fromisoformat(conversation['updated_at'])
        
        duration = updated - created
        
        hours = duration.seconds // 3600
        minutes = (duration.seconds % 3600) // 60
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    
    def export_conversation(
        self,
        conversation_id: str,
        format: str = 'json'
    ) -> str:
        """
        Export conversation in specified format.
        
        Args:
            conversation_id: Conversation ID
            format: Export format (json, markdown)
            
        Returns:
            Exported conversation string
        """
        conversation = self.get_conversation(conversation_id)
        
        if not conversation:
            return ""
        
        if format == 'json':
            return json.dumps(conversation, indent=2)
        
        elif format == 'markdown':
            md_lines = [
                f"# Conversation {conversation_id}",
                f"Created: {conversation['created_at']}",
                f"Updated: {conversation['updated_at']}",
                "",
                "## Messages",
                ""
            ]
            
            for msg in conversation['messages']:
                role = "**User**" if msg['role'] == 'user' else "**Assistant**"
                md_lines.append(f"{role}: {msg['content']}")
                md_lines.append("")
            
            return "\n".join(md_lines)
        
        return ""


# Global instance
conversation_manager = ConversationManager()

__all__ = ['ConversationManager', 'conversation_manager']