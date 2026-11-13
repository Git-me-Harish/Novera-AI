"""Wire-level tests for the provider-agnostic AI layer."""
import json

import httpx
import pytest

from app.services.ai import http as ai_http
from app.services.ai import registry
from app.services.ai.chat import AnthropicChat, GeminiChat, OpenAICompatibleChat
from app.services.ai.embeddings import GeminiEmbeddings, OpenAICompatibleEmbeddings
from app.services.ai.rerank import RerankClient
from app.services.ai.types import ChatMessage, ChatResult, ModelSpec, ProviderError


@pytest.fixture
def transport(monkeypatch):
    """Route all provider HTTP through a recorder; tests set ``responder``."""
    calls = []
    state = {"responder": None}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        calls.append({"url": str(request.url), "headers": request.headers, "json": body})
        return state["responder"](request, body)

    monkeypatch.setattr(ai_http, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return calls, state


MESSAGES = [ChatMessage("user", "Q1"), ChatMessage("assistant", "A1"), ChatMessage("user", "Q2")]


async def test_openai_compatible_payload_and_parsing(transport):
    calls, state = transport
    state["responder"] = lambda r, b: httpx.Response(200, json={
        "choices": [{"message": {"content": "Answer [1]"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3,
                  "prompt_tokens_details": {"cached_tokens": 4}},
    })
    client = OpenAICompatibleChat(ModelSpec("ollama", "llama3", None, "http://host:11434/v1"))
    result = await client.complete(MESSAGES, system="SYS", max_tokens=99)
    sent = calls[0]
    assert sent["url"] == "http://host:11434/v1/chat/completions"
    assert sent["json"]["messages"][0] == {"role": "system", "content": "SYS"}
    assert sent["json"]["model"] == "llama3" and sent["json"]["max_tokens"] == 99
    assert "authorization" not in sent["headers"]  # keyless self-hosted endpoint
    assert result.text == "Answer [1]"
    assert result.usage.as_dict() == {"prompt_tokens": 10, "completion_tokens": 3,
                                      "total_tokens": 13, "cached_tokens": 4}


async def test_openai_content_filter_is_blocked_not_error(transport):
    _, state = transport
    state["responder"] = lambda r, b: httpx.Response(200, json={
        "choices": [{"message": {"content": None}, "finish_reason": "content_filter"}],
    })
    result = await OpenAICompatibleChat(ModelSpec("openai", "m", "k")).complete(MESSAGES)
    assert result.text is None and result.finish_reason == "blocked"


async def test_anthropic_moves_system_and_merges_turns(transport):
    calls, state = transport
    state["responder"] = lambda r, b: httpx.Response(200, json={
        "content": [{"type": "text", "text": "Hi"}], "stop_reason": "end_turn",
        "usage": {"input_tokens": 7, "output_tokens": 2},
    })
    msgs = [ChatMessage("system", "EXTRA"), ChatMessage("user", "a"), ChatMessage("user", "b")]
    result = await AnthropicChat(ModelSpec("anthropic", "claude-x", "key")).complete(msgs, system="SYS")
    sent = calls[0]
    assert sent["url"].endswith("/v1/messages")
    assert sent["headers"]["x-api-key"] == "key"
    assert sent["json"]["system"] == "SYS\n\nEXTRA"
    assert sent["json"]["messages"] == [{"role": "user", "content": "a\n\nb"}]
    assert result.text == "Hi" and result.usage.total_tokens == 9


async def test_gemini_maps_roles_and_detects_safety_block(transport):
    calls, state = transport
    state["responder"] = lambda r, b: httpx.Response(200, json={
        "candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}],
    })
    result = await GeminiChat(ModelSpec("gemini", "models/g-x", "key")).complete(MESSAGES, system="SYS")
    sent = calls[0]
    assert sent["url"].endswith("/models/g-x:generateContent")
    assert sent["json"]["systemInstruction"] == {"parts": [{"text": "SYS"}]}
    assert [c["role"] for c in sent["json"]["contents"]] == ["user", "model", "user"]
    assert result.text is None


@pytest.mark.parametrize("status,body,billing,retryable", [
    (429, "Your prepayment credits are depleted", True, False),
    (429, "Too many requests", False, True),
    (402, "payment required", True, False),
    (503, "overloaded", False, True),
    (401, "invalid api key", False, False),
])
def test_provider_errors_are_classified(status, body, billing, retryable):
    error = ai_http.classify("p:m", httpx.Response(status, text=body, headers={"retry-after": "3"}))
    assert (error.billing, error.retryable) == (billing, retryable)
    if retryable:
        assert error.retry_after == 3.0


async def test_embeddings_send_every_batch_and_keep_order(transport):
    # Regression: the old Gemini batch loop only posted the LAST batch.
    calls, state = transport

    def respond(request, body):
        return httpx.Response(200, json={"embeddings": [
            {"values": [float(len(r["content"]["parts"][0]["text"]))] * 4} for r in body["requests"]
        ]})

    state["responder"] = respond
    client = GeminiEmbeddings(ModelSpec("gemini", "e", "k"), dimensions=4, batch_size=2)
    texts = ["a", "bb", "ccc", "dddd", "eeeee"]
    vectors = await client.embed(texts, task="document")
    assert len(calls) == 3
    assert [v[0] for v in vectors] == [1.0, 2.0, 3.0, 4.0, 5.0]


async def test_embedding_count_mismatch_fails(transport):
    _, state = transport
    state["responder"] = lambda r, b: httpx.Response(200, json={"data": [
        {"index": 0, "embedding": [0.0, 0.0]}
    ]})
    client = OpenAICompatibleEmbeddings(ModelSpec("openai", "e", "k"), dimensions=2)
    with pytest.raises(ProviderError, match="1 vectors for 2 inputs"):
        await client.embed(["a", "b"], task="document")


async def test_openai_embeddings_sorted_by_index_with_input_type(transport):
    calls, state = transport
    state["responder"] = lambda r, b: httpx.Response(200, json={"data": [
        {"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]},
    ]})
    spec = ModelSpec("voyage", "v", "k", None, (("input_type_param", "input_type"),))
    vectors = await OpenAICompatibleEmbeddings(spec, dimensions=1).embed(["a", "b"], task="query")
    assert vectors == [[1.0], [2.0]]
    assert calls[0]["json"]["input_type"] == "query"
    # No base_url: must use Voyage's own endpoint, never OpenAI's.
    assert calls[0]["url"] == "https://api.voyageai.com/v1/embeddings"


async def test_openai_protocol_providers_use_their_own_endpoint(transport):
    calls, state = transport
    state["responder"] = lambda r, b: httpx.Response(200, json={
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})
    await OpenAICompatibleChat(ModelSpec("groq", "m", "gsk-key")).complete(MESSAGES)
    assert calls[0]["url"] == "https://api.groq.com/openai/v1/chat/completions"


@pytest.mark.parametrize("key", ["results", "data"])
async def test_rerank_parses_cohere_and_voyage_shapes(transport, key):
    _, state = transport
    state["responder"] = lambda r, b: httpx.Response(200, json={key: [
        {"index": 2, "relevance_score": 0.2}, {"index": 0, "relevance_score": 0.9},
    ]})
    pairs = await RerankClient(ModelSpec("cohere", "r", "k")).rerank("q", ["a", "b", "c"], top_n=2)
    assert pairs == [(0, 0.9), (2, 0.2)]


# ── fallback chain ───────────────────────────────────────────────────────────

class _Client:
    def __init__(self, label, behaviour):
        self.label = label
        self.behaviour = behaviour
        self.calls = 0

    async def complete(self, *args, **kwargs):
        self.calls += 1
        if isinstance(self.behaviour, Exception):
            raise self.behaviour
        return ChatResult(self.behaviour, "m", self.label)


async def test_chain_falls_back_and_billing_opens_circuit(monkeypatch):
    from app.services.generation import llm_service as module

    monkeypatch.setattr(module, "_circuit_open_until", {})
    broke = _Client("a:broke", ProviderError("credits", provider="a", billing=True))
    backup = _Client("b:ok", "fallback answer")
    chain = registry.ChatChain([broke, backup], 0.0, 100, "platform")

    first = await module.llm_service.complete("q", chain=chain, use_cache=False)
    assert first.text == "fallback answer"
    second = await module.llm_service.complete("q2", chain=chain, use_cache=False)
    assert second.text == "fallback answer"
    assert broke.calls == 1, "billing-exhausted model must be skipped while its circuit is open"


async def test_chain_returns_none_when_every_model_fails(monkeypatch):
    from app.services.generation import llm_service as module

    monkeypatch.setattr(module, "_circuit_open_until", {})
    bad = _Client("a:bad", ProviderError("bad model", provider="a", status=404))
    chain = registry.ChatChain([bad], 0.0, 100, "platform")
    assert await module.llm_service.complete("q", chain=chain, use_cache=False) is None


# ── registry ─────────────────────────────────────────────────────────────────

def test_tenant_secret_roundtrip_and_tamper_safety():
    token = registry.encrypt_secret("sk-tenant-123456")
    assert "sk-tenant" not in token
    assert registry.decrypt_secret(token) == "sk-tenant-123456"
    assert registry.decrypt_secret("not-a-valid-token") is None
    assert registry.mask_secret("sk-tenant-123456") == "••••3456"


def test_tenant_model_takes_precedence_then_platform(monkeypatch):
    monkeypatch.setattr(registry, "_platform_clients", lambda: [
        OpenAICompatibleChat(ModelSpec("openai", "platform-model", "k"))
    ])
    tenant = registry.TenantAISettings(
        chat=registry.TenantChatModel(provider="anthropic", model="tenant-model",
                                      api_key_encrypted=registry.encrypt_secret("tk-12345678")),
        temperature=0.4,
    )
    chain = registry.build_chain(tenant)
    assert chain.labels == ["anthropic:tenant-model", "openai:platform-model"]
    assert chain.primary.spec.api_key == "tk-12345678"
    assert chain.temperature == 0.4 and chain.source == "tenant"

    isolated = registry.build_chain(tenant.model_copy(update={"allow_platform_fallback": False}))
    assert isolated.labels == ["anthropic:tenant-model"]


def test_unknown_or_chatless_tenant_provider_is_rejected():
    with pytest.raises(Exception):
        registry.TenantChatModel(provider="voyage", model="x")  # embeddings/rerank only
    with pytest.raises(Exception):
        registry.TenantChatModel(provider="not-a-provider", model="x")


def test_gemini_vectors_keep_their_historical_identity():
    assert registry.embedding_storage_identity(ModelSpec("gemini", "gemini-embedding-001")) == (
        "google", "models/gemini-embedding-001")
    assert registry.embedding_storage_identity(ModelSpec("openai", "text-embedding-3-small")) == (
        "openai", "text-embedding-3-small")
