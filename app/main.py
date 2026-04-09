import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.runtime.bootstrap import initialize_runtime_dependencies
from app.runtime.config import settings
from app.runtime.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("Initializing runtime dependencies.")
    initialize_runtime_dependencies()
    logger.info("Runtime dependencies initialized successfully.")
    yield


def create_app() -> FastAPI:
    configure_logging()
    application = FastAPI(
        title="OWE Service",
        version="0.1.0",
        description="Lead qualification backend for the technical challenge.",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health_router)
    application.include_router(chat_router, prefix="/api/v1")

    return application


app = create_app()
