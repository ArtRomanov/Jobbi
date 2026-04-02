import logging
import os

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import v1_router
from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    log_level = settings.LOG_LEVEL.upper()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level, logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def init_sentry() -> None:
    settings = get_settings()
    dsn = settings.SENTRY_DSN
    if not dsn:
        return

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration

    sentry_sdk.init(
        dsn=dsn,
        integrations=[FastApiIntegration()],
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
    )


def create_app() -> FastAPI:
    configure_logging()
    init_sentry()

    settings = get_settings()
    app = FastAPI(title="Jobbi", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS.split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(v1_router)

    return app


app = create_app()