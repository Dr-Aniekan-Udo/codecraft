import asyncio
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import cast
from uuid import UUID

import httpx
import pytest
from codecraft_api.app import create_app
from codecraft_api.clerk_client import ClerkClientLike
from codecraft_api.clock_check import check_clock
from codecraft_api.config import Settings
from codecraft_api.token_verifier import InvalidTokenError, VerifiedToken
from codecraft_storage import (
    AnalysisDetail,
    AnalysisSummary,
    DatabaseLike,
    OrganisationSummary,
    ProjectDetail,
    ProjectSummary,
)
from fastapi.testclient import TestClient


class FakeDatabase:
    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def is_member(self, user_id: str, organisation_id: str) -> bool:
        return False

    async def list_organisations(self, user_id: str) -> list[OrganisationSummary]:
        return []

    async def is_owner(self, user_id: str, organisation_id: str) -> bool:
        return False

    async def has_other_owned_organisation(self, user_id: str, organisation_id: str) -> bool:
        return False

    async def has_other_organisation(self, user_id: str, organisation_id: str) -> bool:
        return False

    async def list_analyses(self, user_id: str, organisation_id: str) -> list[AnalysisSummary]:
        return []

    async def list_projects(self, user_id: str, organisation_id: str) -> list[ProjectSummary]:
        return []

    async def get_project(self, user_id: str, project_id: UUID) -> ProjectDetail | None:
        return None

    async def get_analysis(self, user_id: str, analysis_id: UUID) -> AnalysisDetail | None:
        return None

    async def delete_organisation(self, organisation_id: str) -> None: ...

    async def upsert_membership(self, user_id: str, organisation_id: str) -> None: ...

    async def set_owner(self, user_id: str, organisation_id: str) -> None: ...

    async def delete_membership(self, user_id: str, organisation_id: str) -> None: ...


class FakeClerk:
    async def open(self) -> None: ...

    async def close(self) -> None: ...


class FakeVerifier:
    def verify(self, token: str) -> VerifiedToken:
        raise InvalidTokenError("not used")


class UnreachableClient:
    def __init__(self, *_: object, **__: object) -> None: ...

    async def get(self, _: str) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    async def aclose(self) -> None: ...


def _settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql://api@example/db",
        MEMBERSHIP_SYNC_DATABASE_URL="postgresql://sync@example/db",
        CLERK_JWT_ISSUER="https://clerk.example",
        CLERK_WEBHOOK_SIGNING_SECRET="whsec_c2VjcmV0",
        CLERK_SECRET_KEY="sk_test_secret",
    )


def _run_check(
    caplog: pytest.LogCaptureFixture,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await check_clock(client)

    with caplog.at_level(logging.INFO, logger="codecraft_api.clock_check"):
        asyncio.run(run())


def _records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == "codecraft_api.clock_check"]


def test_clock_skew_over_sixty_seconds_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            204,
            headers={
                "date": format_datetime(datetime.now(UTC) + timedelta(seconds=3600), usegmt=True)
            },
        )

    _run_check(caplog, handler)

    records = _records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    message = records[0].getMessage()
    difference = re.search(r"by (\d+) seconds", message)
    assert difference is not None
    assert int(difference.group(1)) > 60
    assert "tokens may be rejected because of the clock" in message


def test_clock_within_sixty_seconds_does_not_warn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            204,
            headers={"date": format_datetime(datetime.now(UTC), usegmt=True)},
        )

    _run_check(caplog, handler)

    assert not [record for record in _records(caplog) if record.levelno >= logging.WARNING]


def test_unreachable_time_source_logs_skip(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    _run_check(caplog, handler)

    records = _records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    assert "Clock check skipped" in records[0].getMessage()


def test_app_starts_when_clock_check_is_unreachable(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("codecraft_api.clock_check.httpx.AsyncClient", UnreachableClient)
    app = create_app(
        _settings(),
        database=cast(DatabaseLike, FakeDatabase()),
        verifier=FakeVerifier(),
        clerk=cast(ClerkClientLike, FakeClerk()),
    )

    test_client = cast("httpx.Client", TestClient(app))
    with (
        caplog.at_level(logging.INFO, logger="codecraft_api.clock_check"),
        test_client as client,
    ):
        response = client.get("/v1/me")

    assert response.status_code == 401
    records = _records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    assert "Clock check skipped" in records[0].getMessage()
