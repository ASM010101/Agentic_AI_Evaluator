from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application settings.

    Defaults are intentionally conservative. In particular, the Docker runner
    is the production default and the application never falls back to running
    student code on the host.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "backend/.env"),
        env_prefix="AUTOGRADER_",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "AutoGrader"
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./data/autograder.db"
    artifact_dir: Path = Path("./data/artifacts")

    runner: Literal["bubblewrap", "docker", "fake"] = "bubblewrap"
    docker_image: str = "autograder-sandbox:latest"
    docker_timeout_s: float = Field(default=12.0, gt=0, le=300)
    bubblewrap_path: str = "bwrap"
    bubblewrap_uid: int = Field(default=65534, ge=1, le=65534)
    bubblewrap_gid: int = Field(default=65534, ge=1, le=65534)
    max_source_bytes: int = Field(default=200_000, gt=0, le=5_000_000)
    max_batch_files: int = Field(default=100, gt=0, le=500)
    max_test_input_bytes: int = Field(default=100_000, gt=0, le=2_000_000)
    max_output_bytes: int = Field(default=100_000, gt=0, le=2_000_000)
    max_concurrent_runs: int = Field(default=2, gt=0, le=32)
    fake_delay_ms: int = Field(default=0, ge=0, le=10_000)

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.1:latest"
    ollama_connect_timeout_s: float = Field(default=2.0, gt=0, le=30)
    ollama_read_timeout_s: float = Field(default=120.0, gt=0, le=600)
    ollama_max_retries: int = Field(default=1, ge=0, le=3)
    ollama_max_concurrency: int = Field(default=1, gt=0, le=8)
    openai_connect_timeout_s: float = Field(default=2.0, gt=0, le=30)
    openai_read_timeout_s: float = Field(default=90.0, gt=0, le=600)
    openai_max_retries: int = Field(default=2, ge=0, le=5)
    llm_max_output_tokens: int = Field(default=900, ge=128, le=8_000)
    use_llm: bool = False

    # OpenAI-compatible provider (Groq, OpenRouter, NVIDIA NIM, etc.)
    llm_provider: Literal["ollama", "openai_compatible"] = "ollama"
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "AUTOGRADER_OPENAI_API_KEY",
            "OPENROUTER_API_KEY",
            "OpenRouter_API_KEY",
            "NVIDIA_API_KEY",
            "GROQ_API_KEY",
            "OPENAI_API_KEY",
        ),
    )
    # An OpenAI-compatible endpoint must be explicitly selected. Do not silently
    # route a key for one provider to a different provider's default endpoint.
    openai_base_url: str = ""
    openai_model: str = "openai/gpt-oss-20b"

    compiler_standard: str = "c11"
    compiler_flags: tuple[str, ...] = ("-std=c11", "-O2", "-Wall", "-Wextra", "-lm")

    @model_validator(mode="after")
    def _resolve_llm_defaults(self) -> Settings:
        if not self.openai_api_key:
            env_key = (
                os.getenv("AUTOGRADER_OPENAI_API_KEY")
                or os.getenv("OPENROUTER_API_KEY")
                or os.getenv("OpenRouter_API_KEY")
                or os.getenv("NVIDIA_API_KEY")
                or os.getenv("GROQ_API_KEY")
                or os.getenv("Groq_API_Key")
                or os.getenv("OPENAI_API_KEY")
                or ""
            )
            if env_key:
                self.openai_api_key = env_key
        # Provider selection is explicit. Merely having a key in the process
        # environment must not silently switch a local Ollama deployment to a
        # remote provider.
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
