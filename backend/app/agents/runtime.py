from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel

from app.core.config import Settings
from app.llm.client import OpenAICompatibleClient, OllamaClient, build_llm_client


AgentClient = OllamaClient | OpenAICompatibleClient
OutputModel = TypeVar("OutputModel", bound=BaseModel)


@dataclass(frozen=True)
class AgentCallResult:
    """Observable result of one bounded model call.

    The prompt and credentials are deliberately not stored.  The metadata is
    safe to persist in the evidence/audit trail and makes skipped, successful
    and failed model work distinguishable.
    """

    agent: str
    role: str
    status: str
    provider: str
    model: str
    latency_ms: float
    output: BaseModel | None = None
    error: str | None = None

    def metadata(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "role": self.role,
            "status": self.status,
            "provider": self.provider,
            "model": self.model,
            "latency_ms": round(self.latency_ms, 2),
            **({"error": self.error} if self.error else {}),
        }


def _run_async(coroutine: Any) -> Any:
    """Run the async HTTP client from the synchronous coordinator/API path."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    # A sync FastAPI route normally runs in a worker thread, but this keeps the
    # adapter safe if a caller invokes it from an already-running event loop.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result()


class AgentRuntime:
    """One bounded, typed gateway for the configured LLM provider."""

    def __init__(self, settings: Settings, client: AgentClient | Any | None = None):
        self.settings = settings
        self.client = client or build_llm_client(settings)
        self._provider_error: str | None = None

    @property
    def provider(self) -> str:
        return self.settings.llm_provider

    @property
    def model(self) -> str:
        return (
            self.settings.openai_model
            if self.settings.llm_provider == "openai_compatible"
            else self.settings.ollama_model
        )

    def run(
        self,
        *,
        agent: str,
        role: str,
        prompt: str,
        output_model: type[OutputModel],
    ) -> AgentCallResult:
        started = time.perf_counter()
        common = {
            "agent": agent,
            "role": role,
            "provider": self.provider,
            "model": self.model,
        }
        if not self.settings.use_llm:
            return AgentCallResult(
                **common,
                status="skipped",
                latency_ms=0.0,
                error="LLM integration is disabled (AUTOGRADER_USE_LLM=false).",
            )
        if self.settings.llm_provider == "openai_compatible" and not self.settings.openai_api_key:
            return AgentCallResult(
                **common,
                status="skipped",
                latency_ms=0.0,
                error="OpenAI-compatible provider is configured without an API key.",
            )
        if self._provider_error:
            return AgentCallResult(
                **common,
                status="unavailable",
                latency_ms=0.0,
                error=self._provider_error,
            )

        field_names = ", ".join(output_model.model_fields)
        # The provider already receives JSON mode and the caller validates the
        # full Pydantic contract.  Repeating a large JSON schema in every prompt
        # wastes context/token quota and can cause Groq TPM failures.
        bounded_prompt = (
            f"{prompt}\n\nReturn only a JSON object with these top-level fields: {field_names}."
        )
        try:
            raw = _run_async(
                self.client.generate_json(bounded_prompt, output_model.model_json_schema())
            )
        except Exception as exc:  # provider failures are reviewable, not fatal grading errors
            error = str(exc)
            if self.settings.openai_api_key:
                error = error.replace(self.settings.openai_api_key, "[redacted]")
            # A rate limit is specific to this request window; do not suppress
            # the later independent agents because Agent 2 happened to hit it.
            if getattr(exc, "status_code", None) != 429:
                self._provider_error = error[:1_000]
            return AgentCallResult(
                **common,
                status="failed",
                latency_ms=(time.perf_counter() - started) * 1_000,
                error=error[:1_000],
            )
        try:
            parsed = output_model.model_validate(raw)
        except Exception as exc:  # malformed model JSON must not suppress later independent agents
            return AgentCallResult(
                **common,
                status="invalid_output",
                latency_ms=(time.perf_counter() - started) * 1_000,
                error=f"model output failed schema validation: {exc}"[:1_000],
            )
        return AgentCallResult(
            **common,
            status="completed",
            latency_ms=(time.perf_counter() - started) * 1_000,
            output=parsed,
        )


def bounded_json(value: Any, limit: int = 30_000) -> str:
    """Serialize untrusted assignment/source context without huge prompts."""

    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return encoded[:limit]
