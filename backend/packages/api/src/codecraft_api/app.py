from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from codecraft_storage import Database, DatabaseLike
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from codecraft_api.clerk_client import ClerkClient, ClerkClientLike
from codecraft_api.clock_check import check_clock
from codecraft_api.config import Settings
from codecraft_api.routes import create_router
from codecraft_api.token_verifier import TokenVerifier, TokenVerifierLike


def create_app(
    settings: Settings | None = None,
    database: DatabaseLike | None = None,
    verifier: TokenVerifierLike | None = None,
    clerk: ClerkClientLike | None = None,
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
    resolved_clerk = clerk if clerk is not None else ClerkClient(resolved_settings.CLERK_SECRET_KEY)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        await resolved_database.open()
        await resolved_clerk.open()
        await check_clock()
        try:
            yield
        finally:
            await resolved_clerk.close()
            await resolved_database.close()

    app = FastAPI(
        title="CodeCraft API",
        lifespan=lifespan,
        # The application exposes only the routes the phase defines; FastAPI's
        # documentation routes would be additional routes, so they stay off.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved_settings.CODECRAFT_FRONTEND_ORIGIN],
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(
        create_router(resolved_settings, resolved_database, resolved_verifier, resolved_clerk)
    )
    return app
