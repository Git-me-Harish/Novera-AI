""" Conversational RAG chat service """

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.retrieval.pipeline import retrieval_pipeline
from app.services.generation.llm_service import llm_service
from app.services.generation.guardrails import guardrails_service
from app.services.generation.conversation_manager import (
    ConversationStoreProtocol,
    conversation_store,
)
from app.services.generation.conversation_titles import schedule_title
from app.services.generation.context_manager import ConversationContext, context_manager
from app.services.retrieval.query_processor import query_processor
from app.services.generation.suggestion_service import suggestion_service
from app.services.generation.semantic_cache import semantic_cache
from app.services.embedding.embedding_service import embedding_service
from app.core.rag_trace import get_current_trace, hash_value
from app.services.generation.llm_service import INSUFFICIENT_CONTEXT_ANSWER
from app.services.ai.registry import ChatChain, chat_chain_for
from app.services.ai.pricing import estimate_cost
from app.services.ai.types import ProviderNotConfigured


class ConversationAccessError(LookupError):
    """The conversation exists but belongs to a different user."""


async def _single_event_stream(result: dict[str, Any]) -> AsyncGenerator[dict, None]:
    """Adapt a complete (e.g. rejected-input) response to the stream protocol."""
    yield {"type": "metadata", "conversation_id": result["conversation_id"], "sources": []}
    yield {"type": "content", "content": result["answer"]}
    yield {"type": "done", "conversation_id": result["conversation_id"]}


class ChatService:
    """
    Complete RAG chat service with natural conversation flow.
    All conversation and context state is persisted to Redis so
    multiple workers handle the same session seamlessly.
    """

    async def _should_search_documents(
        self,
        query: str,
        conversation_history: Optional[list[dict]] = None,
    ) -> bool:
        from app.services.generation.query_classifier import query_classifier

        classification = await query_classifier.classify_query(
            query, conversation_history
        )
        should_search = classification["type"] == "document"
        label = "📄 DOCUMENT SEARCH" if should_search else "🗣️ CONVERSATIONAL"
        logger.info(
            f"{label} | query_hash={hash_value(query)} | chars={len(query)} | "
            f"reason={classification['reasoning']} | "
            f"confidence={classification['confidence']} | "
            f"cached={classification.get('cached', False)}"
        )
        return should_search

    # Main chat entrypoint:

    async def chat(
        self,
        query: str,
        conversation_id: Optional[str],
        user_id: str,
        organization_id,
        db: AsyncSession,
        doc_type: Optional[str] = None,
        department: Optional[str] = None,
        stream: bool = False,
        use_semantic_cache: bool = True,
        return_evidence: bool = False,
        store: Optional[ConversationStoreProtocol] = None,
    ) -> dict[str, Any]:
        """Answer one chat turn.

        ``return_evidence`` adds the retrieved chunks and stage timings under
        ``evidence`` so offline evaluation scores this exact code path.
        ``store`` defaults to the durable PostgreSQL store; evaluation passes an
        in-memory one so golden-set runs never write into a tenant's history.
        """
        from app.core.config import settings
        import time

        query = guardrails_service.normalize_input(query)

        store = store or conversation_store

        # A caller-supplied conversation id is untrusted: its history is fed
        # into the prompt, so another user's id would leak their messages.
        # Lookups are scoped to tenant AND owner. An id that exists but is not
        # visible (another user, another tenant, or deleted) is a 404; an id
        # that does not exist at all starts a fresh conversation.
        conversation = None
        if conversation_id:
            conversation = await store.get_owned(
                db, conversation_id, organization_id=organization_id, user_id=user_id
            )
            if conversation is None and await store.exists_for_other_owner(db, conversation_id):
                logger.warning("Rejected access to a conversation not visible to this user")
                raise ConversationAccessError(conversation_id)

        # Resolve the tenant's model chain once; every generation in this
        # request (answer, rejection message, cache key) uses the same one.
        try:
            chain = await chat_chain_for(db, organization_id)
        except ProviderNotConfigured as exc:
            logger.error(str(exc))
            chain = None
        model_label = chain.primary.label if chain else "unconfigured"
        trace = get_current_trace()
        if trace:
            trace.set_principal(tenant_id=organization_id, user_id=user_id)
            trace.set_query(query)
            trace.event("input_normalized", status="ok")
        logger.info(f"📨 Chat request received (user={user_id}, chars={len(query)})")

        # Input guardrails:
        is_valid, error_msg = guardrails_service.validate_input(query)
        if trace:
            trace.event("input_validated", valid=is_valid, status="ok" if is_valid else "rejected")
        if not is_valid:
            logger.warning(f"Input validation failed: {error_msg}")
            rejected = await self._generate_conversational_response(
                query, conversation, user_id, organization_id, db, error_msg,
                is_error=True, chain=chain, store=store,
            )
            # The stream endpoint iterates the result; a bare dict crashed it.
            return _single_event_stream(rejected) if stream else rejected

        # Conversation setup. Prior turns are read BEFORE the new question is
        # stored: reading after made the current question appear twice in the
        # prompt (once as bare history, once with its evidence).
        if conversation is None:
            conversation = await store.create(
                db,
                organization_id=organization_id,
                user_id=user_id,
                first_question=query,
                metadata={"doc_type": doc_type, "department": department},
            )
            prior_history: list[dict] = []
        else:
            prior_history = await store.recent_history(
                db, conversation, settings.conversation_prompt_turns
            )
        is_first_turn = not prior_history
        conversation_id = str(conversation.id)
        await store.append_message(db, conversation, "user", query)

        # Query processing + context management:
        processed_query = query_processor.process_query(query)
        conv_context = await context_manager.get_or_create_context(conversation_id)
        if not conv_context.message_count and conversation.context:
            # Redis working memory expired: rehydrate from the durable snapshot.
            conv_context = ConversationContext(conversation_id, dict(conversation.context))
        conv_context.update_from_query(query, processed_query)

        reformulated_query = query_processor.reformulate_with_context(
            query, conv_context
        )
        if reformulated_query != query:
            logger.info(
                f"🔄 Reformulated: query_hash={hash_value(query)}, "
                f"output_chars={len(reformulated_query)}"
            )

        # Classify intent: document search vs conversational — this will guide retrieval and generation
        history = prior_history
        try:
            should_search = await self._should_search_documents(reformulated_query, history)
        except Exception as e:
            logger.warning(f"Query classification error, defaulting to document search: {e}")
            should_search = True

        semantic_cached_response: Optional[dict[str, Any]] = None
        semantic_cache_embedding: list[float] | None = None
        semantic_cache_fingerprint: str | None = None
        semantic_cache_scope: str | None = None
        # Semantic answers are only reusable for a fresh, non-streaming
        # document query. Conversation history can legitimately change the
        # answer even when the current question is similar.
        if use_semantic_cache and should_search and not stream and not any(
            message.get("role") == "assistant" for message in history
        ):
            try:
                semantic_cache_embedding = await embedding_service.embed_query(
                    reformulated_query
                )
                semantic_cache_scope = semantic_cache.scope_key(doc_type, department)
                semantic_cache_fingerprint = await semantic_cache.corpus_fingerprint(
                    db, organization_id
                )
                semantic_cached_response = await semantic_cache.lookup(
                    db,
                    organization_id=organization_id,
                    query=reformulated_query,
                    query_embedding=semantic_cache_embedding,
                    scope_key=semantic_cache_scope,
                    corpus_fingerprint=semantic_cache_fingerprint,
                    generation_model=model_label,
                )
                if semantic_cached_response and trace:
                    trace.event(
                        "semantic_cache_hit",
                        similarity=semantic_cached_response["similarity"],
                        cache_entry_id=semantic_cached_response["cache_entry_id"],
                    )
            except Exception as e:
                # A cache outage must never make the answer path unavailable.
                logger.warning(f"Semantic cache lookup skipped: {type(e).__name__}")
                semantic_cached_response = None

        context = ""
        sources: list = []
        chunks_used = 0
        retrieval_metadata: dict = {}
        retrieved_chunks: list = []
        retrieval_ms = 0.0

        # Document retrieval:
        if should_search and semantic_cached_response is None:
            retrieval_started = trace.stage_start("retrieval") if trace else None
            retrieval_clock = time.perf_counter()
            try:
                use_scoped = conv_context.should_use_document_scope()
                logger.info(
                    f"🔍 Retrieval: {'scoped' if use_scoped else 'global'} search"
                )

                retrieval_result = await retrieval_pipeline.retrieve(
                    query=reformulated_query,
                    db=db,
                    organization_id=organization_id,
                    top_k=settings.global_search_top_k,
                    doc_type=doc_type,
                    department=department,
                    include_context=True,
                    conversation_context=conv_context,
                    force_global=False,
                    query_embedding=semantic_cache_embedding,
                )

                context = retrieval_result["context_text"]
                sources = retrieval_result["sources"]
                retrieved_chunks = retrieval_result["chunks"]
                chunks_used = len(retrieved_chunks)
                retrieval_metadata = retrieval_result.get("retrieval_metadata", {})
                conv_context.update_from_retrieval(sources)

                logger.info(
                    f"✅ Retrieved {chunks_used} chunks "
                    f"({retrieval_metadata.get('search_type', '?')} search)"
                )
                if trace:
                    trace.stage_end(
                        "retrieval",
                        retrieval_started,
                        strategy=retrieval_metadata.get("search_strategy"),
                        candidate_k=retrieval_metadata.get("total_retrieved", 0),
                        final_k=chunks_used,
                        retrieved=retrieval_metadata.get("total_retrieved", 0),
                        reranked=retrieval_metadata.get("after_reranking", 0),
                        sources=len(sources),
                        expanded_to_global=retrieval_metadata.get("expanded_to_global", False),
                        embedding_model=f"{embedding_service.provider}:{embedding_service.model_name}",
                        embedding_dimensions=embedding_service.dimensions,
                        min_score=(retrieval_metadata.get("score_summary") or {}).get("min", 0.0),
                        max_score=(retrieval_metadata.get("score_summary") or {}).get("max", 0.0),
                        avg_score=(retrieval_metadata.get("score_summary") or {}).get("avg", 0.0),
                    )
            except Exception as e:
                logger.error(f"Retrieval failed: {e}", exc_info=True)
                context = ""
                sources = []
                if trace:
                    trace.stage_end(
                        "retrieval", retrieval_started, status="error", error_type=type(e).__name__
                    )

        retrieval_ms = (
            (time.perf_counter() - retrieval_clock) * 1000
            if should_search and semantic_cached_response is None else 0.0
        )

        # Save updated context before generation:
        await context_manager.save_context(conv_context)

        # Stream path: same generation + output policy as the JSON path.
        if stream:
            return self._chat_stream(
                db=db,
                store=store,
                conversation=conversation,
                organization_id=organization_id,
                is_first_turn=is_first_turn,
                should_search=should_search,
                chunks_used=chunks_used,
                query=query,
                reformulated_query=reformulated_query,
                context=context,
                sources=sources,
                history=prior_history,
                conversation_id=conversation_id,
                retrieval_metadata=retrieval_metadata,
                conv_context=conv_context,
                is_conversational=not should_search,
                chain=chain,
            )

        # Generate answer and persist assistant message in DB:
        generation_result: Optional[dict] = None
        answer = ""
        citations: list = []
        generation_ms = 0.0

        generation_started = trace.stage_start("generation") if trace else None
        if semantic_cached_response is not None:
            answer = semantic_cached_response["answer"]
            sources = semantic_cached_response.get("sources", [])
            citations = semantic_cached_response.get("citations", [])
            generation_result = {
                "answer": answer,
                "citations": citations,
                "confidence": "high",
                "cache_hit": True,
                "finish_reason": "semantic_cache",
                "usage": {
                    "total_tokens": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cached_tokens": 0,
                },
            }
            if trace:
                trace.stage_end(
                    "generation",
                    generation_started,
                    cache_hit=True,
                    finish_reason="semantic_cache",
                    citation_count=len(citations),
                )
        else:
            generation_clock = time.perf_counter()
            try:
                full_history = prior_history
                generation_result = await self._generate_validated(
                    chain=chain,
                    query=query,
                    reformulated_query=reformulated_query,
                    context=context,
                    sources=sources,
                    history=full_history,
                    context_summary=conv_context.get_context_summary(),
                    is_conversational=not should_search,
                )
                answer = generation_result["answer"]
                citations = generation_result["citations"]
                if trace:
                    usage = generation_result.get("usage", {}) or {}
                    trace.stage_end(
                        "generation",
                        generation_started,
                        model=generation_result.get("model", model_label),
                        model_source=chain.source if chain else "none",
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        total_tokens=usage.get("total_tokens", 0),
                        cache_hit=generation_result.get("cache_hit", False),
                        citation_count=len(citations),
                        finish_reason=generation_result.get("finish_reason"),
                    )

                usage = generation_result.get("usage", {})
                total_tokens = usage.get("total_tokens", 0)
                cached_tokens = usage.get("cached_tokens", 0)
                cost = estimate_cost(generation_result.get("model"), usage)
                logger.info(
                    f"💬 Response: {len(answer)} chars | {len(citations)} citations | "
                    f"{total_tokens} tokens | est. "
                    + (f"${cost:.6f}" if cost is not None else "cost unknown")
                )

            except Exception as e:
                logger.error(f"Generation failed: {e}", exc_info=True)
                answer = (
                    "I encountered an issue generating a response. "
                    "Could you try rephrasing your question?"
                )
                generation_result = {
                    "answer": answer,
                    "citations": [],
                    "confidence": "low",
                    "finish_reason": "error",
                    "usage": {"total_tokens": 0},
                }
                if trace:
                    trace.stage_end("generation", generation_started, status="error", error_type=type(e).__name__)
            generation_ms = (time.perf_counter() - generation_clock) * 1000

        if (
            semantic_cached_response is None
            and semantic_cache_embedding is not None
            and semantic_cache_scope is not None
            and semantic_cache_fingerprint is not None
            and should_search
            and generation_result
            and not generation_result.get("cache_hit", False)
            and generation_result.get("finish_reason") == "stop"
            and citations
        ):
            try:
                await semantic_cache.store(
                    db,
                    organization_id=organization_id,
                    query=reformulated_query,
                    query_embedding=semantic_cache_embedding,
                    scope_key=semantic_cache_scope,
                    corpus_fingerprint=semantic_cache_fingerprint,
                    generation_model=model_label,
                    answer=answer,
                    sources=sources,
                    citations=citations,
                )
            except Exception as e:
                logger.warning(f"Semantic cache write skipped: {type(e).__name__}")

        await self._finish_turn(
            db, store, conversation,
            organization_id=organization_id,
            query=query,
            reformulated_query=reformulated_query,
            answer=answer,
            citations=citations,
            sources=sources,
            generation_result=generation_result or {},
            should_search=should_search,
            chunks_used=chunks_used,
            conv_context=conv_context,
            is_first_turn=is_first_turn,
        )

        # Suggestions — fire in background, never block response:
        suggestions: list[str] = []
        try:
            suggestions = suggestion_service._get_fallback_suggestions(
                conv_context.get_context_summary(), answer
            )
        except Exception:
            suggestions = []

        try:
            asyncio.get_running_loop().create_task(
                suggestion_service.generate_suggestions(
                    last_query=query,
                    last_response=answer,
                    context_summary=conv_context.get_context_summary(),
                    sources=sources,
                )
            )
        except Exception:
            pass

        # Build response payload:
        if sources:
            logger.info(
                f"✅ RESPONSE FROM DOCUMENTS | "
                f"primary={conv_context.primary_document} | "
                f"chunks={chunks_used} | citations={len(citations)}"
            )
        else:
            logger.info("🤖 RESPONSE: CONVERSATIONAL")

        response = {
            "answer": answer,
            "conversation_id": conversation_id,
            "sources": sources,
            "citations": citations,
            "confidence": (
                (generation_result or {}).get("confidence", "low")
            ),
            "status": "success",
            "suggestions": suggestions,
            "metadata": {
                "chunks_used": chunks_used,
                "tokens": (generation_result or {}).get("usage", {}),
                "model": (generation_result or {}).get("model"),
                "cache_hit": (generation_result or {}).get("cache_hit", False),
                "searched_documents": should_search,
                "retrieval_metadata": retrieval_metadata,
                "context_summary": conv_context.get_context_summary(),
                "query_reformulated": reformulated_query != query,
            },
        }
        if return_evidence:
            response["evidence"] = {
                "chunks": retrieved_chunks,
                "context": context,
                "should_search": should_search,
                "reformulated_query": reformulated_query,
                "finish_reason": (generation_result or {}).get("finish_reason"),
                "validation": (generation_result or {}).get("validation", {}),
                "retrieval_latency_ms": round(retrieval_ms, 3),
                "generation_latency_ms": round(generation_ms, 3),
            }
        return response

    async def _generate_validated(
        self,
        *,
        query: str,
        reformulated_query: str,
        context: str,
        sources: list,
        history: list,
        context_summary: Optional[dict],
        is_conversational: bool,
        chain: Optional[ChatChain] = None,
    ) -> dict[str, Any]:
        """Generate an answer and apply the output policy.

        Shared by the JSON and streaming paths so both enforce identical
        grounding rules. Only model-produced answers are validated; fixed
        system messages (abstention, provider unavailable) pass through.
        """
        result = await llm_service.generate_answer(
            query=query,
            reformulated_query=reformulated_query,
            context=context,
            sources=sources,
            conversation_history=history,
            conversation_context=context_summary,
            is_conversational=is_conversational,
            chain=chain,
        )
        result["answer"] = guardrails_service.sanitize_output(result["answer"])
        result.setdefault("citations", [])
        if result.get("finish_reason") == "stop":
            output_ok, output_warning, validation = guardrails_service.validate_output(
                query=query,
                answer=result["answer"],
                context=context,
                sources=sources,
            )
            result["validation"] = validation
            if not output_ok:
                logger.warning(f"Output rejected by guardrails: {output_warning}")
                result.update(
                    answer=INSUFFICIENT_CONTEXT_ANSWER,
                    citations=[],
                    confidence="low",
                    finish_reason="output_guardrail_rejected",
                )
        return result

    # Conversational fallback:

    async def _generate_conversational_response(
        self,
        query: str,
        conversation,
        user_id: str,
        organization_id,
        db: AsyncSession,
        context_message: str,
        is_error: bool = False,
        chain: Optional[ChatChain] = None,
        store: Optional[ConversationStoreProtocol] = None,
    ) -> dict[str, Any]:
        store = store or conversation_store
        if conversation is None:
            conversation = await store.create(
                db, organization_id=organization_id, user_id=user_id, first_question=query
            )
            history: list[dict] = []
        else:
            history = await store.recent_history(db, conversation, 2)
        await store.append_message(db, conversation, "user", query)

        try:
            result = await llm_service.generate_conversational_response(
                query=query,
                context_message=context_message,
                history=history,
                is_error=is_error,
                chain=chain,
            )
            answer = result["answer"]
        except Exception:
            answer = context_message

        metadata = {"type": "conversational", "rejected": is_error}
        await store.append_message(db, conversation, "assistant", answer, metadata)

        return {
            "answer": answer,
            "conversation_id": str(conversation.id),
            "sources": [],
            "citations": [],
            "confidence": "high",
            "status": "success" if not is_error else "rejected",
            "suggestions": [],
            "metadata": metadata,
        }

    async def _finish_turn(
        self,
        db: AsyncSession,
        store: ConversationStoreProtocol,
        conversation,
        *,
        organization_id,
        query: str,
        reformulated_query: str,
        answer: str,
        citations: list,
        sources: list,
        generation_result: dict,
        should_search: bool,
        chunks_used: int,
        conv_context,
        is_first_turn: bool,
    ) -> None:
        """Persist the answer and context identically for JSON and stream paths."""
        await store.append_message(
            db, conversation, "assistant", answer,
            {
                "citations": citations,
                "sources": sources,
                "tokens": generation_result.get("usage", {}),
                "model": generation_result.get("model"),
                "confidence": generation_result.get("confidence"),
                "finish_reason": generation_result.get("finish_reason"),
                "cache_hit": generation_result.get("cache_hit", False),
                "searched_documents": should_search,
                "chunks_used": chunks_used,
                "reformulated_query": (
                    reformulated_query if reformulated_query != query else None
                ),
            },
        )
        await store.save_context(db, conversation, conv_context.to_dict())
        # Title only from a real answer: an outage message is a poor title source.
        if is_first_turn and store is conversation_store and generation_result.get(
            "finish_reason"
        ) in {"stop", "semantic_cache", "length", "insufficient_context"}:
            schedule_title(organization_id, conversation.id, query)

    # Streaming response generator:

    async def _chat_stream(
        self,
        *,
        db: AsyncSession,
        store: ConversationStoreProtocol,
        conversation,
        organization_id,
        is_first_turn: bool,
        should_search: bool,
        chunks_used: int,
        query: str,
        reformulated_query: str,
        context: str,
        sources: list,
        history: list,
        conversation_id: str,
        retrieval_metadata: dict,
        conv_context,       # ConversationContext
        is_conversational: bool,
        chain: Optional[ChatChain] = None,
    ) -> AsyncGenerator[dict, None]:
        yield {
            "type": "metadata",
            "conversation_id": conversation_id,
            "sources": sources,
            "retrieval_metadata": retrieval_metadata,
        }

        # Buffer the answer before emitting it so the same output policy is
        # applied to streaming and non-streaming requests. A safe response is
        # more important than partial unvalidated token delivery. The old
        # stream call omitted is_conversational, so "hello" was answered with
        # the insufficient-information abstention.
        generation_result = await self._generate_validated(
            chain=chain,
            query=query,
            reformulated_query=reformulated_query,
            context=context,
            sources=sources,
            history=history,
            context_summary=conv_context.get_context_summary(),
            is_conversational=is_conversational,
        )
        full_answer = generation_result["answer"]
        yield {
            "type": "content",
            "content": full_answer,
            "citations": generation_result["citations"],
        }

        await self._finish_turn(
            db, store, conversation,
            organization_id=organization_id,
            query=query,
            reformulated_query=reformulated_query,
            answer=full_answer,
            citations=generation_result["citations"],
            sources=sources,
            generation_result=generation_result,
            should_search=should_search,
            chunks_used=chunks_used,
            conv_context=conv_context,
            is_first_turn=is_first_turn,
        )

        yield {"type": "done", "conversation_id": conversation_id}

# Singleton
chat_service = ChatService()

__all__ = ["ChatService", "chat_service"]
