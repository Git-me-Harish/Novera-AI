"""
Chat API endpoints for RAG system.
Provides conversational interface with full RAG pipeline.
"""
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from loguru import logger
import json

from app.db.session import get_db
from app.services.generation.chat_service import chat_service
from app.api.dependencies.auth import get_current_user
from app.models.user import User


router = APIRouter()


# Request/Response Models
class ChatRequest(BaseModel):
    """Chat request model."""
    query: str = Field(..., min_length=1, max_length=1000, description="User's question")
    conversation_id: Optional[str] = Field(None, description="Existing conversation ID")
    doc_type: Optional[str] = Field(None, description="Filter by document type")
    department: Optional[str] = Field(None, description="Filter by department")
    stream: bool = Field(False, description="Enable streaming response")


class SourceInfo(BaseModel):
    """Source citation information."""
    document: str
    page: Optional[int] = None
    section: Optional[str] = None
    chunk_id: str


class ChatResponse(BaseModel):
    """Chat response model."""
    answer: str
    conversation_id: str
    sources: List[SourceInfo]
    citations: List[dict] = []
    confidence: str
    status: str
    metadata: dict


class ConversationMessage(BaseModel):
    """Individual message in conversation."""
    id: str
    role: str
    content: str
    timestamp: str
    metadata: dict = {}


class ConversationDetail(BaseModel):
    """Complete conversation details."""
    id: str
    user_id: str
    created_at: str
    updated_at: str
    messages: List[ConversationMessage]
    metadata: dict = {}
    context: dict = {}


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Chat with the AI assistant using RAG.
    
    This endpoint:
    1. Validates input with guardrails
    2. Retrieves relevant context from documents
    3. Generates answer using Gemini
    4. Validates output for accuracy
    5. Returns answer with sources
    
    Example:
    ```json
    {
      "query": "What is the PF contribution rate?",
      "conversation_id": null,
      "doc_type": "hrms"
    }
    ```
    """
    user_id = str(current_user.id)
    logger.info(f"Chat request from user {user_id}: '{request.query[:50]}...'")
    
    # Check for streaming
    if request.stream:
        # Return streaming response
        return StreamingResponse(
            _stream_chat(request, db, user_id),
            media_type="text/event-stream"
        )
    
    # Regular (non-streaming) chat
    try:
        result = await chat_service.chat(
            query=request.query,
            conversation_id=request.conversation_id,
            user_id=user_id,
            db=db,
            doc_type=request.doc_type,
            department=request.department,
            stream=False
        )
        
        # Check for errors
        if result.get('error'):
            logger.error(f"Chat service returned error: {result['error']}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result['error']
            )
        
        # Format response - handle missing or empty sources
        sources = []
        for src in result.get('sources', []):
            try:
                sources.append(SourceInfo(
                    document=src.get('document', 'Unknown'),
                    page=src.get('page'),
                    section=src.get('section'),
                    chunk_id=src.get('chunk_id', 'unknown')
                ))
            except Exception as e:
                logger.warning(f"Error formatting source: {str(e)}")
                continue
        
        return ChatResponse(
            answer=result['answer'],
            conversation_id=result['conversation_id'],
            sources=sources,
            citations=result.get('citations', []),
            confidence=result.get('confidence', 'medium'),
            status=result.get('status', 'success'),
            metadata=result.get('metadata', {})
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {status.HTTP_400_BAD_REQUEST}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat processing failed: {str(e)}"
        )


async def _stream_chat(request: ChatRequest, db: AsyncSession, user_id: str):
    """
    Internal function to stream chat responses.
    
    Yields Server-Sent Events (SSE) format.
    """
    try:
        result_stream = await chat_service.chat(
            query=request.query,
            conversation_id=request.conversation_id,
            user_id=user_id,
            db=db,
            doc_type=request.doc_type,
            department=request.department,
            stream=True
        )
        
        async for chunk in result_stream:
            # Format as SSE
            yield f"data: {json.dumps(chunk)}\n\n"
        
        # End of stream
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        logger.error(f"Streaming error: {str(e)}")
        error_data = {
            'type': 'error',
            'error': str(e)
        }
        yield f"data: {json.dumps(error_data)}\n\n"


@router.get("/chat/conversations")
async def list_conversations(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user)
):
    """
    List all conversations for the current user.
    
    Returns summaries including:
    - Conversation ID
    - Created/updated timestamps
    - Message counts
    - Topics discussed
    """
    user_id = str(current_user.id)
    
    try:
        conversations = await chat_service.list_conversations(
            user_id=user_id,
            limit=limit
        )
        
        return conversations
        
    except Exception as e:
        logger.error(f"Error listing conversations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/chat/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get complete conversation history.
    
    Returns all messages with metadata including:
    - User queries
    - Assistant responses
    - Sources cited
    - Timestamps
    """
    user_id = str(current_user.id)
    
    try:
        conversation = await chat_service.get_conversation_history(
            conversation_id=conversation_id,
            user_id=user_id
        )
        
        # Check for errors
        if 'error' in conversation:
            error_msg = conversation['error']
            if error_msg == 'Conversation not found':
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=error_msg
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=error_msg
                )
        
        # Format messages
        messages = []
        for msg in conversation.get('messages', []):
            try:
                messages.append(ConversationMessage(
                    id=msg.get('id', ''),
                    role=msg.get('role', 'user'),
                    content=msg.get('content', ''),
                    timestamp=msg.get('timestamp', ''),
                    metadata=msg.get('metadata', {})
                ))
            except Exception as e:
                logger.warning(f"Error formatting message: {str(e)}")
                continue
        
        return ConversationDetail(
            id=conversation['id'],
            user_id=conversation['user_id'],
            created_at=conversation['created_at'],
            updated_at=conversation['updated_at'],
            messages=messages,
            metadata=conversation.get('metadata', {}),
            context=conversation.get('context', {})
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/chat/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Delete a conversation and its history.
    """
    user_id = str(current_user.id)
    
    try:
        deleted = await chat_service.delete_conversation(
            conversation_id=conversation_id,
            user_id=user_id
        )
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found or unauthorized"
            )
        
        return {
            'message': 'Conversation deleted successfully',
            'conversation_id': conversation_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting conversation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/chat/test")
async def test_chat():
    """
    Test endpoint to verify chat API is working.
    """
    return {
        'status': 'operational',
        'message': 'Chat API is ready',
        'features': [
            'RAG-based question answering',
            'Conversation history',
            'Source citations',
            'Input/output guardrails',
            'Streaming responses',
            'Natural conversational responses'
        ]
    }


__all__ = ['router']