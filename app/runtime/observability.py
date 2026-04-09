from __future__ import annotations

import os
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.runtime.config import settings


def configure_langsmith() -> None:
    if not settings.langsmith_tracing:
        return

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    if settings.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key


def is_langsmith_configured() -> bool:
    return settings.langsmith_tracing


def langsmith_config(
    run_name: str,
    *,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> RunnableConfig:
    config: RunnableConfig = {
        "run_name": run_name,
    }
    if tags:
        config["tags"] = tags
    if metadata:
        config["metadata"] = metadata
    return config
