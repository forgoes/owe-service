from __future__ import annotations

from app.runtime.observability import configure_langsmith, is_langsmith_configured
from app.runtime.openai import chat_model_registry
from app.runtime.session import initialize_database, is_database_initialized


def initialize_runtime_dependencies() -> None:
    configure_langsmith()
    chat_model_registry.initialize()
    initialize_database()


def runtime_status() -> dict[str, bool]:
    return {
        "langsmith_configured": is_langsmith_configured(),
        "models_initialized": chat_model_registry.is_initialized(),
        "database_initialized": is_database_initialized(),
    }
