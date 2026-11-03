from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from app.core.config import Settings


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    """Original Ollama-native client (talks to /api/generate)."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._semaphore = asyncio.Semaphore(settings.ollama_max_concurrency)

    async def health(self) -> tuple[bool, str, str | None]:
        timeout = httpx.Timeout(
            connect=self.settings.ollama_connect_timeout_s,
            read=self.settings.ollama_read_timeout_s,
            write=5,
            pool=5,
        )
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(self.settings.ollama_base_url.rstrip("/") + "/api/tags")
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return False, f"Ollama unavailable: {exc}", None
        models = {item.get("name") for item in data.get("models", []) if isinstance(item, dict)}
        if self.settings.ollama_model not in models:
            return False, f"model {self.settings.ollama_model!r} is not installed", None
        return True, "configured Ollama model is available", self.settings.ollama_model

    async def generate_json(self, prompt: str, schema_hint: dict[str, Any]) -> dict[str, Any]:
        timeout = httpx.Timeout(
            connect=self.settings.ollama_connect_timeout_s,
            read=self.settings.ollama_read_timeout_s,
            write=5,
            pool=5,
        )
        body = {
            "model": self.settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "seed": 42},
        }
        last_error: Exception | None = None
        async with self._semaphore:
            for _attempt in range(self.settings.ollama_max_retries + 1):
                try:
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        response = await client.post(
                            self.settings.ollama_base_url.rstrip("/") + "/api/generate", json=body
                        )
                        response.raise_for_status()
                        envelope = response.json()
                        raw = envelope.get("response")
                        if not isinstance(raw, str):
                            raise OllamaError("Ollama response did not contain a JSON string")
                        parsed = json.loads(raw)
                        if not isinstance(parsed, dict):
                            raise OllamaError("Ollama JSON response must be an object")
                        # A schema hint is deliberately informational here; the
                        # caller validates the typed Pydantic result.
                        _ = schema_hint
                        return parsed
                except (httpx.HTTPError, ValueError, OllamaError) as exc:
                    last_error = exc
        raise OllamaError(str(last_error or "Ollama request failed"))

    def health_sync(self) -> tuple[bool, str, str | None]:
        return asyncio.run(self.health())


class OpenAICompatibleClient:
    """Client for OpenAI-compatible APIs (Groq, OpenRouter, NVIDIA NIM, etc.).

    These providers expose the standard /v1/chat/completions endpoint and
    accept a Bearer token. The model name is provider-specific.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._semaphore = asyncio.Semaphore(settings.ollama_max_concurrency)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }

    async def health(self) -> tuple[bool, str, str | None]:
        if not self.settings.openai_api_key:
            return False, "AUTOGRADER_OPENAI_API_KEY is not set", None
        timeout = httpx.Timeout(
            connect=self.settings.ollama_connect_timeout_s,
            read=self.settings.ollama_read_timeout_s,
            write=5,
            pool=5,
        )
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    self.settings.openai_base_url.rstrip("/") + "/models",
                    headers=self._headers(),
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return False, f"LLM provider unavailable: {exc}", None

        # Check if the configured model is listed (some providers list all,
        # others return a subset).
        models = set()
        for item in data.get("data", []):
            if isinstance(item, dict):
                models.add(item.get("id", ""))
        if models and self.settings.openai_model not in models:
            return (
                False,
                f"model {self.settings.openai_model!r} not found at {self.settings.openai_base_url}",
                None,
            )
        return (
            True,
            f"LLM model {self.settings.openai_model!r} is available",
            self.settings.openai_model,
        )

    async def generate_json(self, prompt: str, schema_hint: dict[str, Any]) -> dict[str, Any]:
        timeout = httpx.Timeout(
            connect=self.settings.ollama_connect_timeout_s,
            read=self.settings.ollama_read_timeout_s,
            write=5,
            pool=5,
        )
        system_msg = (
            "You are AutoGrader, a deterministic C programming submission evaluator. "
            "Respond ONLY with a valid JSON object. Do not include any other text."
        )
        body = {
            "model": self.settings.openai_model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        last_error: Exception | None = None
        async with self._semaphore:
            for _attempt in range(self.settings.ollama_max_retries + 1):
                try:
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        response = await client.post(
                            self.settings.openai_base_url.rstrip("/") + "/chat/completions",
                            headers=self._headers(),
                            json=body,
                        )
                        response.raise_for_status()
                        envelope = response.json()
                        choices = envelope.get("choices", [])
                        if not choices:
                            raise OllamaError("LLM returned no choices")
                        raw = choices[0].get("message", {}).get("content", "")
                        if not isinstance(raw, str) or not raw.strip():
                            raise OllamaError("LLM response did not contain content")
                        parsed = json.loads(raw)
                        if not isinstance(parsed, dict):
                            raise OllamaError("LLM JSON response must be an object")
                        _ = schema_hint
                        return parsed
                except (httpx.HTTPError, ValueError, OllamaError) as exc:
                    last_error = exc
        raise OllamaError(str(last_error or "LLM request failed"))

    def health_sync(self) -> tuple[bool, str, str | None]:
        return asyncio.run(self.health())


def build_llm_client(settings: Settings) -> OllamaClient | OpenAICompatibleClient:
    """Factory: pick the right LLM client based on configuration."""
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleClient(settings)
    return OllamaClient(settings)
