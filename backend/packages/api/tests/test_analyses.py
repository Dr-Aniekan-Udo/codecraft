from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import httpx
from codecraft_api.app import create_app
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

_ANALYSIS_ID = UUID("11111111-1111-1111-1111-111111111111")
_CREATED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


class FakeVerifier:
    def verify(self, token: str) -> VerifiedToken:
        if token != "valid-token":
            raise InvalidTokenError("token verification failed")
        # A signed-in person with no active organisation must still be able to read the
        # analyses of an organisation the database says they belong to.
        return VerifiedToken(user_id="user_123", organisation_id=None)


class FakeDatabase:
    def __init__(self, analyses: list[AnalysisSummary] | None = None) -> None:
        self.analyses = [] if analyses is None else analyses
        self.list_analyses_calls: list[tuple[str, str]] = []
        self.is_member_calls: list[tuple[str, str]] = []
        self.organisation_deletes: list[str] = []

    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def is_member(self, user_id: str, organisation_id: str) -> bool:
        self.is_member_calls.append((user_id, organisation_id))
        return False

    async def list_organisations(self, user_id: str) -> list[OrganisationSummary]:
        return []

    async def is_owner(self, user_id: str, organisation_id: str) -> bool:
        return False

    async def has_other_owned_organisation(self, user_id: str, organisation_id: str) -> bool:
        return False

    async def has_other_organisation(self, user_id: str, organisation_id: str) -> bool:
        return True

    async def list_analyses(self, user_id: str, organisation_id: str) -> list[AnalysisSummary]:
        self.list_analyses_calls.append((user_id, organisation_id))
        return self.analyses

    async def list_projects(self, user_id: str, organisation_id: str) -> list[ProjectSummary]:
        return []

    async def get_project(self, user_id: str, project_id: UUID) -> ProjectDetail | None:
        return None

    async def get_analysis(self, user_id: str, analysis_id: UUID) -> AnalysisDetail | None:
        return None

    async def delete_organisation(self, organisation_id: str) -> None:
        self.organisation_deletes.append(organisation_id)

    async def upsert_membership(self, user_id: str, organisation_id: str) -> None: ...

    async def set_owner(self, user_id: str, organisation_id: str) -> None: ...

    async def delete_membership(self, user_id: str, organisation_id: str) -> None: ...


def _settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql://api@example/db",
        MEMBERSHIP_SYNC_DATABASE_URL="postgresql://sync@example/db",
        CLERK_JWT_ISSUER="https://clerk.example",
        CLERK_WEBHOOK_SIGNING_SECRET="whsec_c2VjcmV0",
        CLERK_SECRET_KEY="sk_test_secret",
    )


def _client(database: DatabaseLike) -> httpx.Client:
    # Starlette's TestClient is an httpx.Client at runtime, but its annotations
    # name httpx2, which is not installed. Narrow to the base class it really uses.
    return cast(
        "httpx.Client",
        TestClient(create_app(_settings(), database=database, verifier=FakeVerifier())),
    )


def _authorization() -> dict[str, str]:
    return {"Authorization": "Bearer valid-token"}


def _assert_unauthorized(response: httpx.Response) -> None:
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_missing_token_is_refused() -> None:
    database = FakeDatabase()
    with _client(database) as client:
        response = client.get("/v1/analyses", params={"organisation_id": "org_1"})
    _assert_unauthorized(response)
    assert database.list_analyses_calls == []


def test_invalid_token_is_refused() -> None:
    database = FakeDatabase()
    with _client(database) as client:
        response = client.get(
            "/v1/analyses",
            params={"organisation_id": "org_1"},
            headers={"Authorization": "Bearer not-valid"},
        )
    _assert_unauthorized(response)
    assert database.list_analyses_calls == []


def test_missing_organisation_id_is_rejected() -> None:
    database = FakeDatabase()
    with _client(database) as client:
        response = client.get("/v1/analyses", headers=_authorization())
    assert response.status_code == 422
    assert database.list_analyses_calls == []


def test_empty_organisation_id_is_rejected() -> None:
    database = FakeDatabase()
    with _client(database) as client:
        response = client.get(
            "/v1/analyses", params={"organisation_id": ""}, headers=_authorization()
        )
    assert response.status_code == 422
    assert database.list_analyses_calls == []


def test_lists_analyses() -> None:
    database = FakeDatabase(
        [
            AnalysisSummary(
                id=_ANALYSIS_ID,
                project_name="checkout",
                state="complete",
                created_at=_CREATED_AT,
                is_sample=False,
            )
        ]
    )
    with _client(database) as client:
        response = client.get(
            "/v1/analyses", params={"organisation_id": "org_1"}, headers=_authorization()
        )
    assert response.status_code == 200
    body = response.json()
    assert list(body) == ["analyses"]
    assert len(body["analyses"]) == 1
    item = body["analyses"][0]
    assert set(item) == {"id", "project_name", "state", "created_at", "is_sample"}
    assert item["id"] == str(_ANALYSIS_ID)
    assert item["project_name"] == "checkout"
    assert item["state"] == "complete"
    assert item["is_sample"] is False
    assert datetime.fromisoformat(item["created_at"]) == _CREATED_AT


def test_organisation_id_is_passed_through() -> None:
    database = FakeDatabase()
    with _client(database) as client:
        client.get("/v1/analyses", params={"organisation_id": "org_2"}, headers=_authorization())
    assert database.list_analyses_calls == [("user_123", "org_2")]


def test_token_without_active_organisation_can_read() -> None:
    database = FakeDatabase(
        [
            AnalysisSummary(
                id=_ANALYSIS_ID,
                project_name="checkout",
                state="queued",
                created_at=_CREATED_AT,
                is_sample=True,
            )
        ]
    )
    with _client(database) as client:
        response = client.get(
            "/v1/analyses", params={"organisation_id": "org_1"}, headers=_authorization()
        )
    assert response.status_code == 200
    assert database.list_analyses_calls == [("user_123", "org_1")]


def test_membership_is_not_checked_in_python() -> None:
    database = FakeDatabase()
    with _client(database) as client:
        response = client.get(
            "/v1/analyses", params={"organisation_id": "org_1"}, headers=_authorization()
        )
    assert response.status_code == 200
    assert database.is_member_calls == []
