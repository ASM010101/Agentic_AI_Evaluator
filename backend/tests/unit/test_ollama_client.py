from __future__ import annotations

import asyncio

import pytest

from app.core.config import Settings
from app.llm.client import OpenAICompatibleClient, OllamaClient, OllamaError


class FakeResponse:
    def __init__(self, payload: dict, error: Exception | None = None):
        self.payload = payload
        self.error = error

    def raise_for_status(self) -> None:
        if self.error:
            raise self.error

    def json(self) -> dict:
        return self.payload


class FakeAsyncClient:
    def __init__(self, *, tags: FakeResponse, generated: FakeResponse):
        self.tags = tags
        self.generated = generated

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def get(self, _url: str) -> FakeResponse:
        return self.tags

    async def post(self, _url: str, json: dict) -> FakeResponse:
        return self.generated


class FakeOpenAIAsyncClient:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.body: dict = {}

    async def __aenter__(self) -> "FakeOpenAIAsyncClient":
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def get(self, _url: str, **_kwargs) -> FakeResponse:
        return FakeResponse({"data": [{"id": "openai/gpt-oss-20b"}]})

    async def post(self, _url: str, *, json: dict, **_kwargs) -> FakeResponse:
        self.body = json
        return self.response


def test_ollama_health_and_typed_json_generation(monkeypatch):
    settings = Settings(ollama_model="demo", ollama_max_retries=0)
    fake = FakeAsyncClient(
        tags=FakeResponse({"models": [{"name": "demo"}]}),
        generated=FakeResponse({"response": '{"score": 1}'}),
    )
    monkeypatch.setattr("app.llm.client.httpx.AsyncClient", lambda **_kwargs: fake)
    client = OllamaClient(settings)
    assert client.health_sync() == (True, "configured Ollama model is available", "demo")
    assert asyncio.run(client.generate_json("return JSON", {"score": "number"})) == {"score": 1}


def test_ollama_reports_missing_model_and_malformed_output(monkeypatch):
    settings = Settings(ollama_model="missing", ollama_max_retries=0)
    missing = FakeAsyncClient(
        tags=FakeResponse({"models": [{"name": "other"}]}),
        generated=FakeResponse({"response": "{}"}),
    )
    monkeypatch.setattr("app.llm.client.httpx.AsyncClient", lambda **_kwargs: missing)
    client_health = OllamaClient(settings).health_sync()
    assert client_health[0] is False

    malformed = FakeAsyncClient(
        tags=FakeResponse({"models": [{"name": "missing"}]}),
        generated=FakeResponse({"response": "not JSON"}),
    )
    monkeypatch.setattr("app.llm.client.httpx.AsyncClient", lambda **_kwargs: malformed)
    with pytest.raises(OllamaError):
        asyncio.run(OllamaClient(settings).generate_json("return JSON", {}))


def test_nvidia_gpt_oss_request_uses_low_reasoning_effort(monkeypatch):
    settings = Settings(
        _env_file=None,
        llm_provider="openai_compatible",
        openai_api_key="test-key",
        openai_base_url="https://integrate.api.nvidia.com/v1",
        openai_model="openai/gpt-oss-20b",
        openai_max_retries=0,
        llm_max_output_tokens=128,
    )
    fake = FakeOpenAIAsyncClient(
        FakeResponse({"choices": [{"message": {"content": '{"ok": true}'}}]})
    )
    monkeypatch.setattr("app.llm.client.httpx.AsyncClient", lambda **_kwargs: fake)

    result = asyncio.run(OpenAICompatibleClient(settings).generate_json("return JSON", {}))

    assert result == {"ok": True}
    assert fake.body["reasoning_effort"] == "low"
    assert fake.body["max_tokens"] == 128


def test_openai_compatible_client_does_not_assume_groq_endpoint():
    settings = Settings(
        _env_file=None,
        llm_provider="openai_compatible",
        openai_api_key="test-key",
        openai_base_url="",
    )

    available, detail, model = OpenAICompatibleClient(settings).health_sync()

    assert available is False
    assert detail == "OpenAI-compatible LLM endpoint is not configured"
    assert model is None
