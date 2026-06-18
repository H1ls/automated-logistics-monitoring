from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from Navigation_Bot.api.routes import router
from Navigation_Bot.core.storage.postgres_connection import initialize_postgres_schema
from Navigation_Bot.core.storage.postgres_pool import create_postgres_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_postgres_schema()
    pool = create_postgres_pool()
    pool.open()
    app.state.postgres_pool = pool
    try:
        yield
    finally:
        pool.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Navigation Bot API",
                  version="0.1.0",
                  docs_url="/docs",
                  redoc_url="/redoc",
                  lifespan=lifespan)

    app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
