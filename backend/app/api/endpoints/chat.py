"""Chat API endpoints for RAG system."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_admin_user, get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.document import Chunk as ChunkModel
from app.models.document import Document
from app.models.user import User
from app.services.ai.pricing import estimate_cost
from app.services.generation.chat_service import ConversationAccessError, chat_service
from app.api.endpoints.conversations import load_conversation_dict

router = APIRouter()

# Pricing constants — update here when Gemini pricing changes


# Models:

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[str] = Field(None)
    doc_type: Optional[str] = Field(None)
    department: Optional[str] = Field(None)
    stream: bool = Field(False)


class SourceInfo(BaseModel):
    document: str
    page: Optional[int] = None
    section: Optional[str] = None
    chunk_id: str


class ChatResponse(BaseModel):
    answer: str
    conversation_id: str
    sources: List[SourceInfo]
    citations: List[dict] = []
    confidence: str
    status: str
    suggestions: List[str] = []
    metadata: dict


class ConversationMessage(BaseModel):
    id: str
    role: str
    content: str
    timestamp: str
    metadata: dict = {}


class ConversationDetail(BaseModel):
    id: str
    user_id: str
    created_at: str
    updated_at: str
    messages: List[ConversationMessage]
    metadata: dict = {}
    context: dict = {}


class SelectiveExportRequest(BaseModel):
    message_indices: List[int] = Field(..., description="Indices of messages to export")
    format: str = Field("markdown", pattern="^(markdown|json|pdf)$")


# Helpers:
def _require_debug_mode():
    """Dependency that blocks debug endpoints in production."""
    if settings.environment != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debug endpoints are disabled in production.",
        )


def _calculate_duration(conversation: Dict[str, Any]) -> float:
    """Calculate conversation duration in minutes."""
    try:
        created = datetime.fromisoformat(conversation["created_at"])
        updated = datetime.fromisoformat(conversation["updated_at"])
        # FIX: normalise to UTC if naive so subtraction never raises TypeError
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        return round((updated - created).total_seconds() / 60, 1)
    except Exception:
        return 0.0


def _export_to_markdown(conversation: Dict[str, Any]) -> str:
    lines = [
        "# Conversation Export",
        "",
        f"**Conversation ID:** {conversation['id']}",
        f"**Created:** {conversation['created_at']}",
        f"**Last Updated:** {conversation['updated_at']}",
        "",
        "---",
        "",
    ]
    for msg in conversation["messages"]:
        role = "**User**" if msg["role"] == "user" else "**AI Assistant**"
        lines += [f"### {role} ({msg.get('timestamp', '')})", "", msg["content"], ""]
        if msg["role"] == "assistant":
            sources = msg.get("metadata", {}).get("sources", [])
            if sources:
                lines.append("**Sources:**")
                for src in sources:
                    lines.append(f"- {src.get('document')} (Page {src.get('page', 'N/A')})")
                lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def _export_selected_to_markdown(conversation: Dict[str, Any]) -> str:
    metadata = conversation.get("metadata", {})
    # FIX: timezone-aware
    exported_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# Selective Conversation Export",
        "",
        f"**Conversation ID:** {conversation['id']}",
        f"**Created:** {conversation['created_at']}",
        f"**Exported:** {exported_at}",
        "",
        f"**Selection:** {metadata.get('exported_message_count', 0)} of {metadata.get('total_messages_in_conversation', 0)} messages",
        "",
        "---",
        "",
        "## Selected Messages",
        "",
    ]
    for idx, msg in enumerate(conversation["messages"], 1):
        role = "**User**" if msg["role"] == "user" else "**AI Assistant**"
        ts = msg.get("timestamp", "")
        lines.append(f"### Message {idx}: {role}")
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
                lines.append(f"*{dt.strftime('%I:%M %p')}*")
            except Exception:
                lines.append(f"*{ts}*")
        lines += ["", msg["content"], ""]
        if msg["role"] == "assistant":
            sources = msg.get("metadata", {}).get("sources", [])
            if sources:
                lines.append("**Sources:**")
                for src in sources:
                    lines.append(f"- {src.get('document', 'Unknown')} (Page {src.get('page', 'N/A')})")
                lines.append("")
        lines += ["---", ""]
    return "\n".join(lines)


# Endpoints
@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Chat with the AI assistant using the full RAG pipeline."""
    user_id = str(current_user.id)

    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not assigned to an organization",
        )

    if request.stream:
        return StreamingResponse(
            _stream_chat(request, db, user_id, current_user.organization_id),
            media_type="text/event-stream",
        )

    try:
        result = await chat_service.chat(
            query=request.query,
            conversation_id=request.conversation_id,
            user_id=user_id,
            organization_id=current_user.organization_id,
            db=db,
            doc_type=request.doc_type,
            department=request.department,
            stream=False,
        )

        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])

        sources = []
        for src in result.get("sources", []):
            try:
                sources.append(SourceInfo(
                    document=src.get("document", "Unknown"),
                    page=src.get("page"),
                    section=src.get("section"),
                    chunk_id=src.get("chunk_id", "unknown"),
                ))
            except Exception as e:
                logger.warning(f"Error formatting source: {e}")

        return ChatResponse(
            answer=result["answer"],
            conversation_id=result["conversation_id"],
            sources=sources,
            citations=result.get("citations", []),
            confidence=result.get("confidence", "medium"),
            status=result.get("status", "success"),
            suggestions=result.get("suggestions", []),
            metadata=result.get("metadata", {}),
        )

    except HTTPException:
        raise
    except ConversationAccessError:
        raise HTTPException(status_code=404, detail="Conversation not found")
    except Exception as e:
        # Internal errors (SQL, provider messages) must not reach the client.
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Chat processing failed")


async def _stream_chat(request: ChatRequest, db: AsyncSession, user_id: str, organization_id):
    try:
        result_stream = await chat_service.chat(
            query=request.query,
            conversation_id=request.conversation_id,
            user_id=user_id,
            organization_id=organization_id,
            db=db,
            doc_type=request.doc_type,
            department=request.department,
            stream=True,
        )
        async for chunk in result_stream:
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"
    except ConversationAccessError:
        yield f"data: {json.dumps({'type': 'error', 'error': 'Conversation not found'})}\n\n"
    except Exception as e:
        # Internal errors (SQL, provider messages) must not reach the client.
        logger.error(f"Streaming error: {e}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'error': 'Chat processing failed'})}\n\n"


@router.get("/chat/test", dependencies=[Depends(_require_debug_mode)])
async def test_chat(current_user: User = Depends(get_current_admin_user)):
    """Test endpoint — development only."""
    return {
        "status": "operational",
        "message": "Chat API is ready",
        "features": [
            "RAG-based question answering",
            "Conversation history",
            "Source citations",
            "Input/output guardrails",
            "Streaming responses",
            "Natural conversational responses",
        ],
    }


@router.get("/chat/conversations/{conversation_id}/analytics")
async def get_conversation_analytics(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = str(current_user.id)
    try:
        from app.services.generation.context_manager import context_manager

        conversation = await load_conversation_dict(db, conversation_id, current_user)

        context = await context_manager.get_or_create_context(conversation_id)
        messages = conversation.get("messages", [])
        user_messages = [m for m in messages if m["role"] == "user"]
        assistant_messages = [m for m in messages if m["role"] == "assistant"]

        documents_referenced = set()
        sources_count = 0
        confidences = []

        for msg in assistant_messages:
            meta = msg.get("metadata", {})
            for src in meta.get("sources", []):
                sources_count += 1
                documents_referenced.add(src.get("document", "Unknown"))
            confidences.append(meta.get("confidence", "medium"))

        context_summary = context.get_context_summary() if context else {}

        return {
            "conversation_id": conversation_id,
            "total_messages": len(messages),
            "user_queries": len(user_messages),
            "ai_responses": len(assistant_messages),
            "documents_referenced": list(documents_referenced),
            "total_documents": len(documents_referenced),
            "total_sources_cited": sources_count,
            "confidence_distribution": {
                "high": confidences.count("high"),
                "medium": confidences.count("medium"),
                "low": confidences.count("low"),
            },
            "primary_document": context_summary.get("primary_document"),
            "active_documents": context_summary.get("active_documents", []),
            "topics": context_summary.get("topics", []),
            "time_periods_discussed": context_summary.get("time_periods", []),
            "created_at": conversation["created_at"],
            "duration_minutes": _calculate_duration(conversation),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analytics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/conversations/{conversation_id}/export")
async def export_conversation(
    conversation_id: str,
    format: str = Query("markdown", pattern="^(markdown|json|pdf)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = str(current_user.id)
    try:
        conversation = await load_conversation_dict(db, conversation_id, current_user)

        if format == "json":
            return conversation

        if format == "markdown":
            return Response(
                content=_export_to_markdown(conversation),
                media_type="text/markdown",
                headers={
                    "Content-Disposition": f"attachment; filename=conversation_{conversation_id[:8]}.md"
                },
            )

        if format == "pdf":
            try:
                from app.services.export.pdf_generator import pdf_generator
                buf = pdf_generator.generate_conversation_pdf(conversation)
                return Response(
                    content=buf.read(),
                    media_type="application/pdf",
                    headers={
                        "Content-Disposition": f"attachment; filename=conversation_{conversation_id[:8]}.pdf"
                    },
                )
            except ImportError:
                logger.warning("reportlab not available, falling back to markdown")
                return Response(
                    content=_export_to_markdown(conversation),
                    media_type="text/markdown",
                    headers={
                        "Content-Disposition": f"attachment; filename=conversation_{conversation_id[:8]}.md"
                    },
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting conversation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/conversations/{conversation_id}/export-selected")
async def export_selected_messages(
    conversation_id: str,
    request: SelectiveExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = str(current_user.id)
    try:
        conversation = await load_conversation_dict(db, conversation_id, current_user)

        all_messages = conversation.get("messages", [])
        selected = [all_messages[i] for i in sorted(request.message_indices) if 0 <= i < len(all_messages)]
        if not selected:
            raise HTTPException(status_code=400, detail="No valid messages selected")

        filtered = {
            **conversation,
            "messages": selected,
            "metadata": {
                **conversation.get("metadata", {}),
                "is_selective_export": True,
                "total_messages_in_conversation": len(all_messages),
                "exported_message_count": len(selected),
                "exported_indices": request.message_indices,
            },
        }

        if request.format == "json":
            return filtered

        if request.format == "markdown":
            return Response(
                content=_export_selected_to_markdown(filtered),
                media_type="text/markdown",
                headers={
                    "Content-Disposition": f"attachment; filename=conversation_selective_{conversation_id[:8]}.md"
                },
            )

        if request.format == "pdf":
            try:
                from app.services.export.pdf_generator import pdf_generator
                buf = pdf_generator.generate_conversation_pdf(filtered)
                return Response(
                    content=buf.read(),
                    media_type="application/pdf",
                    headers={
                        "Content-Disposition": f"attachment; filename=conversation_selective_{conversation_id[:8]}.pdf"
                    },
                )
            except Exception as e:
                logger.error(f"PDF generation failed: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in selective export: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/conversations/{conversation_id}/token-stats")
async def get_conversation_token_stats(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = str(current_user.id)
    try:
        conversation = await load_conversation_dict(db, conversation_id, current_user)

        assistant_messages = [m for m in conversation.get("messages", []) if m["role"] == "assistant"]

        total_tokens = total_cached = total_prompt = total_completion = 0
        total_cost = 0.0
        priced_messages = 0
        message_stats = []

        for msg in assistant_messages:
            tokens = msg.get("metadata", {}).get("tokens", {})
            t = tokens.get("total_tokens", 0)
            c = tokens.get("cached_tokens", 0)
            p = tokens.get("prompt_tokens", 0)
            comp = tokens.get("completion_tokens", 0)
            # Priced per message by the model that produced it; None when no
            # price is configured (never a guessed number).
            cost = estimate_cost(msg.get("metadata", {}).get("model"), tokens)

            total_tokens += t
            total_cached += c
            total_prompt += p
            total_completion += comp
            if cost is not None:
                total_cost += cost
                priced_messages += 1

            message_stats.append({
                "message_id": msg.get("id"),
                "timestamp": msg.get("timestamp"),
                "tokens": {"total": t, "cached": c, "prompt": p, "completion": comp},
                "model": msg.get("metadata", {}).get("model"),
                "cost_usd": round(cost, 6) if cost is not None else None,
            })

        cache_efficiency = (total_cached / total_tokens * 100) if total_tokens > 0 else 0

        return {
            "conversation_id": conversation_id,
            "summary": {
                "total_messages": len(assistant_messages),
                "total_tokens": total_tokens,
                "cached_tokens": total_cached,
                "prompt_tokens": total_prompt,
                "completion_tokens": total_completion,
                "cache_efficiency_percent": round(cache_efficiency, 2),
                "total_cost_usd": round(total_cost, 6) if priced_messages else None,
                "priced_messages": priced_messages,
                "avg_tokens_per_message": round(total_tokens / len(assistant_messages)) if assistant_messages else 0,
                "avg_cost_per_message": round(total_cost / priced_messages, 6) if priced_messages else None,
            },
            "messages": message_stats,
            "pricing_info": {
                "source": "LLM_PRICING configuration (USD per million tokens)",
                "currency": "USD",
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting token stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Debug endpoints:
@router.get("/chat/debug/database", dependencies=[Depends(_require_debug_mode)])
async def debug_database(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    if not current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not assigned to an organization")
    doc_counts = {
        row.status: row.count
        for row in (
            await db.execute(
                select(Document.status, func.count(Document.id).label("count"))
                .where(Document.organization_id == current_user.organization_id)
                .group_by(Document.status)
            )
        ).all()
    }
    total_chunks = (
        await db.execute(
            select(func.count(ChunkModel.id))
            .join(Document)
            .where(Document.organization_id == current_user.organization_id)
        )
    ).scalar()
    chunks_with_embeddings = (
        await db.execute(
            text(
                "SELECT COUNT(*) FROM chunks c "
                "JOIN documents d ON d.id = c.document_id "
                "WHERE d.organization_id = :organization_id AND c.embedding IS NOT NULL"
            ),
            {"organization_id": str(current_user.organization_id)},
        )
    ).scalar()
    samples = [
        {
            "filename": row.filename,
            "status": row.status,
            "chunks": row.total_chunks,
            "uploaded": row.upload_date.isoformat() if row.upload_date else None,
        }
        for row in (
            await db.execute(
                select(Document.filename, Document.status, Document.total_chunks, Document.upload_date)
                .where(Document.organization_id == current_user.organization_id)
                .limit(5)
            )
        ).all()
    ]
    return {
        "database_status": "connected",
        "documents_by_status": doc_counts,
        "total_chunks": total_chunks,
        "chunks_with_embeddings": chunks_with_embeddings,
        "sample_documents": samples,
        "diagnosis": {
            "has_documents": sum(doc_counts.values()) > 0,
            "has_chunks": total_chunks > 0,
            "has_embeddings": chunks_with_embeddings > 0,
            "ready_for_search": chunks_with_embeddings > 0,
        },
    }


@router.get("/chat/debug/chunks", dependencies=[Depends(_require_debug_mode)])
async def debug_chunks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    if not current_user.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not assigned to an organization")
    tenant_filter = Document.organization_id == current_user.organization_id
    total_chunks = (
        await db.execute(select(func.count(ChunkModel.id)).join(Document).where(tenant_filter))
    ).scalar()
    chunks_with_embeddings = (
        await db.execute(
            text(
                "SELECT COUNT(*) FROM chunks c "
                "JOIN documents d ON d.id = c.document_id "
                "WHERE d.organization_id = :organization_id AND c.embedding IS NOT NULL"
            ),
            {"organization_id": str(current_user.organization_id)},
        )
    ).scalar()
    dimension_row = (
        await db.execute(
            text(
                "SELECT array_length(c.embedding, 1) as dim FROM chunks c "
                "JOIN documents d ON d.id = c.document_id "
                "WHERE d.organization_id = :organization_id LIMIT 1"
            ),
            {"organization_id": str(current_user.organization_id)},
        )
    ).first()
    actual_dim = dimension_row[0] if dimension_row else None
    sample = (
        await db.execute(
            select(ChunkModel.id, ChunkModel.content, ChunkModel.chunk_type)
            .join(Document)
            .where(tenant_filter)
            .limit(1)
        )
    ).first()

    return {
        "total_chunks": total_chunks,
        "chunks_with_embeddings": chunks_with_embeddings,
        "expected_dimensions": settings.embedding_dimensions,
        "actual_dimensions": actual_dim,
        "dimension_match": actual_dim == settings.embedding_dimensions if actual_dim else False,
        "sample_chunk": {
            "id": str(sample[0]),
            "content": (sample[1][:100] + "...") if sample and sample[1] else None,
            "type": sample[2] if sample else None,
        } if sample else None,
        "status": "ready" if chunks_with_embeddings > 0 else "no_data",
    }


@router.get("/chat/debug/test-embedding", dependencies=[Depends(_require_debug_mode)])
async def test_embedding(current_user: User = Depends(get_current_admin_user)):
    from app.services.embedding.embedding_service import embedding_service
    test_text = "This is a test sentence to verify embeddings are working."
    try:
        start = time.time()
        embedding = await embedding_service.generate_embedding(test_text)
        return {
            "status": "success",
            "provider": embedding_service.provider,
            "model": embedding_service.model_name,
            "dimensions": len(embedding),
            "expected_dimensions": embedding_service.dimensions,
            "dimension_match": len(embedding) == embedding_service.dimensions,
            "elapsed_seconds": round(time.time() - start, 2),
            "sample_values": embedding[:5],
            "using_local_fallback": embedding_service.use_local_fallback,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "error_type": type(e).__name__}


@router.get("/chat/debug/config", dependencies=[Depends(_require_debug_mode)])
async def debug_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    from app.services.ai.registry import chat_chain_for, rerank_client
    from app.services.embedding.embedding_service import embedding_service

    chain = await chat_chain_for(db, current_user.organization_id)
    reranker = rerank_client()
    return {
        "chat_models": chain.labels,
        "chat_model_source": chain.source,
        "embedding_model": f"{embedding_service.provider}:{embedding_service.model_name}",
        "embedding_dimensions": embedding_service.dimensions,
        "rerank_model": reranker.label if reranker else "none",
        "chunk_size": settings.chunk_size,
        "retrieval_top_k": settings.retrieval_top_k,
        "similarity_threshold": settings.similarity_threshold,
    }


__all__ = ["router"]
