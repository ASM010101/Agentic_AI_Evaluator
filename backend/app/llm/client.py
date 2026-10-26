from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from app.core.config import Settings


class OllamaError(RuntimeError):
    pass


class OllamaClient:
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
