from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from codecraft_storage import Database, DatabaseLike
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from codecraft_api.config import Settings
from codecraft_api.routes import create_router
from codecraft_api.token_verifier import TokenVerifier, TokenVerifierLike


def create_app(
    settings: Settings | None = None,
    database: DatabaseLike | None = None,
    verifier: TokenVerifierLike | None = None,
) -> FastAPI:
    """Build the API. Tests inject fakes instead of a live database or Clerk."""
    resolved_settings = settings if settings is not None else Settings()
    resolved_database = (
        database
        if database is not None
        else Database(
            resolved_settings.DATABASE_URL,
            resolved_settings.MEMBERSHIP_SYNC_DATABASE_URL,
        )
    )
    resolved_verifier = (
        verifier if verifier is not None else TokenVerifier(resolved_settings.CLERK_JWT_ISSUER)
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        await resolved_database.open()
        try:
            yield
        finally:
            await resolved_database.close()

    app = FastAPI(
        title="CodeCraft API",
        lifespan=lifespan,
        # The phase defines exactly two routes; FastAPI's documentation routes
        # would be additional routes, so they stay off.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved_settings.CODECRAFT_FRONTEND_ORIGIN],
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(create_router(resolved_settings, resolved_database, resolved_verifier))
    return app
