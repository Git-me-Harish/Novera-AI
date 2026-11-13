"""Tenant AI settings API: secrecy, tenancy, SSRF policy and effect on routing."""
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.api.dependencies.auth import get_current_org_admin
from app.db.session import get_db
from app.main import app
from app.services.ai import registry
from app.services.ai.chat import OpenAICompatibleChat
from app.services.ai.types import ModelSpec

ORG_ID = uuid4()


class FakeSession:
    """Just enough AsyncSession for the endpoints: one organization row."""

    def __init__(self, org):
        self.org = org
        self.commits = 0

    async def execute(self, statement):
        # select(Organization) -> the row; select(Organization.settings) -> the column.
        selected = statement.column_descriptions[0]["name"]
        value = self.org.settings if selected == "settings" else self.org
        return SimpleNamespace(scalar_one_or_none=lambda: value)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        pass


@pytest.fixture
def api(monkeypatch):
    org = SimpleNamespace(id=ORG_ID, settings={})
    session = FakeSession(org)
    admin = SimpleNamespace(id=uuid4(), organization_id=ORG_ID,
                            is_super_admin=lambda: False, is_org_admin=lambda: True)

    async def fake_db():
        yield session

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_org_admin] = lambda: admin
    monkeypatch.setattr(registry, "_platform_clients", lambda: [
        OpenAICompatibleChat(ModelSpec("openai", "platform-model", "k"))
    ])
    registry.reset_clients()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    yield client, org, session
    app.dependency_overrides.clear()
    registry.reset_clients()


URL = "/api/v1/organization/ai-settings"


async def test_key_is_encrypted_and_never_returned(api):
    client, org, _ = api
    response = await client.put(URL, json={
        "chat": {"provider": "anthropic", "model": "claude-x", "api_key": "sk-ant-secret-9876"},
        "temperature": 0.2,
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert "sk-ant-secret-9876" not in response.text
    assert body["chat"]["api_key_set"] and body["chat"]["api_key_hint"] == "••••9876"
    assert body["effective_chat_models"] == ["anthropic:claude-x", "openai:platform-model"]
    stored = org.settings["ai"]["chat"]["api_key_encrypted"]
    assert "sk-ant" not in stored and registry.decrypt_secret(stored) == "sk-ant-secret-9876"


async def test_omitted_key_is_kept_and_empty_key_clears(api):
    client, org, _ = api
    await client.put(URL, json={"chat": {"provider": "openai", "model": "a", "api_key": "sk-keep-1234"}})
    await client.put(URL, json={"chat": {"provider": "openai", "model": "b"}})
    assert registry.decrypt_secret(org.settings["ai"]["chat"]["api_key_encrypted"]) == "sk-keep-1234"
    # Switching provider must not carry another provider's key across.
    response = await client.put(URL, json={"chat": {"provider": "mistral", "model": "m"}})
    assert response.status_code == 422  # mistral needs a key and none is stored for it


async def test_new_tenant_model_is_used_on_the_next_request(api):
    client, org, session = api
    before = await registry.chat_chain_for(session, ORG_ID)
    assert before.labels == ["openai:platform-model"]
    await client.put(URL, json={"chat": {"provider": "openai", "model": "tenant-model",
                                         "api_key": "sk-tenant-1234"},
                                "allow_platform_fallback": False})
    after = await registry.chat_chain_for(session, ORG_ID)
    assert after.labels == ["openai:tenant-model"], "cache must be invalidated on update"
    await client.delete(URL)
    assert (await registry.chat_chain_for(session, ORG_ID)).labels == ["openai:platform-model"]


async def test_org_admin_cannot_manage_another_org(api):
    client, _, _ = api
    response = await client.get(URL, params={"organization_id": str(uuid4())})
    assert response.status_code == 403


@pytest.mark.parametrize("chat", [
    {"provider": "openai_compatible", "model": "m", "base_url": "http://169.254.169.254/v1", "api_key": "k" * 12},
    {"provider": "openai_compatible", "model": "m", "base_url": "https://127.0.0.1/v1", "api_key": "k" * 12},
    {"provider": "openai_compatible", "model": "m", "base_url": "http://user:pw@example.com/v1"},
    # No base_url: the default would be the PLATFORM's localhost.
    {"provider": "ollama", "model": "llama3"},
    # Requires an explicit base URL.
    {"provider": "vllm", "model": "m"},
])
async def test_internal_endpoints_are_rejected(api, chat):
    client, org, _ = api
    response = await client.put(URL, json={"chat": chat})
    assert response.status_code == 422, response.text
    assert "ai" not in org.settings


async def test_embedding_only_provider_cannot_be_a_chat_model(api):
    client, _, _ = api
    response = await client.put(URL, json={"chat": {"provider": "voyage", "model": "v", "api_key": "k" * 12}})
    assert response.status_code == 422


async def test_provider_catalog_lists_no_model_names(api):
    client, _, _ = api
    providers = (await client.get("/api/v1/ai/providers")).json()["providers"]
    ids = {p["id"] for p in providers}
    assert {"openai", "anthropic", "gemini", "ollama", "openai_compatible"} <= ids
    assert all("model" not in p for p in providers)
