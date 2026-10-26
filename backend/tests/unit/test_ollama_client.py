from __future__ import annotations

import asyncio

import pytest

from app.core.config import Settings
from app.llm.client import OllamaClient, OllamaError


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
