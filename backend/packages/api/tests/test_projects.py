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
    ProjectAnalysisSummary,
    ProjectDetail,
    ProjectRecord,
    ProjectSummary,
)
from fastapi.testclient import TestClient

_PROJECT_ID = UUID("22222222-2222-2222-2222-222222222222")
_OTHER_PROJECT_ID = UUID("33333333-3333-3333-3333-333333333333")
_THIRD_PROJECT_ID = UUID("55555555-5555-5555-5555-555555555555")
_ANALYSIS_ID = UUID("11111111-1111-1111-1111-111111111111")
_OTHER_ANALYSIS_ID = UUID("44444444-4444-4444-4444-444444444444")
_CREATED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
_EARLIER = datetime(2026, 1, 1, 3, 4, 5, tzinfo=UTC)


class FakeVerifier:
    def verify(self, token: str) -> VerifiedToken:
        if token != "valid-token":
            raise InvalidTokenError("token verification failed")
        return VerifiedToken(user_id="user_123", organisation_id=None)


class FakeDatabase:
    def __init__(
        self,
        *,
        projects: list[ProjectSummary] | None = None,
        project_details: dict[UUID, ProjectDetail] | None = None,
        analysis_details: dict[UUID, AnalysisDetail] | None = None,
    ) -> None:
        self.projects = [] if projects is None else projects
        self.project_details = {} if project_details is None else project_details
        self.analysis_details = {} if analysis_details is None else analysis_details
        self.list_projects_calls: list[tuple[str, str]] = []
        self.get_project_calls: list[tuple[str, UUID]] = []
        self.get_analysis_calls: list[tuple[str, UUID]] = []
        self.is_member_calls: list[tuple[str, str]] = []

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
        return []

    async def list_projects(self, user_id: str, organisation_id: str) -> list[ProjectSummary]:
        self.list_projects_calls.append((user_id, organisation_id))
        return self.projects

    async def get_project(self, user_id: str, project_id: UUID) -> ProjectDetail | None:
        self.get_project_calls.append((user_id, project_id))
        return self.project_details.get(project_id)

    async def get_analysis(self, user_id: str, analysis_id: UUID) -> AnalysisDetail | None:
        self.get_analysis_calls.append((user_id, analysis_id))
        return self.analysis_details.get(analysis_id)

    async def delete_organisation(self, organisation_id: str) -> None: ...

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


def _project_detail() -> ProjectDetail:
    return ProjectDetail(
        project=ProjectRecord(
            id=_PROJECT_ID,
            name="checkout",
            created_at=_CREATED_AT,
            is_sample=False,
        ),
        analyses=[
            ProjectAnalysisSummary(
                id=_ANALYSIS_ID,
                state="complete",
                created_at=_CREATED_AT,
                is_sample=False,
            ),
            ProjectAnalysisSummary(
                id=_OTHER_ANALYSIS_ID,
                state="queued",
                created_at=_EARLIER,
                is_sample=True,
            ),
        ],
    )


def _analysis_detail() -> AnalysisDetail:
    return AnalysisDetail(
        id=_ANALYSIS_ID,
        project_id=_PROJECT_ID,
        project_name="checkout",
        state="complete",
        created_at=_CREATED_AT,
        is_sample=False,
    )


def test_lists_projects_with_latest_analysis() -> None:
    database = FakeDatabase(
        projects=[
            ProjectSummary(
                id=_PROJECT_ID,
                name="checkout",
                created_at=_CREATED_AT,
                is_sample=False,
                latest_analysis_state="complete",
                latest_analysis_created_at=_CREATED_AT,
            ),
            ProjectSummary(
                id=_OTHER_PROJECT_ID,
                name="catalog",
                created_at=_EARLIER,
                is_sample=True,
                latest_analysis_state=None,
                latest_analysis_created_at=None,
            ),
        ]
    )
    with _client(database) as client:
        response = client.get(
            "/v1/projects", params={"organisation_id": "org_1"}, headers=_authorization()
        )
    assert response.status_code == 200
    body = response.json()
    assert list(body) == ["projects"]
    assert len(body["projects"]) == 2

    first = body["projects"][0]
    assert set(first) == {
        "id",
        "name",
        "created_at",
        "is_sample",
        "latest_analysis_state",
        "latest_analysis_created_at",
    }
    assert first["id"] == str(_PROJECT_ID)
    assert first["name"] == "checkout"
    assert first["is_sample"] is False
    assert first["latest_analysis_state"] == "complete"
    assert datetime.fromisoformat(first["created_at"]) == _CREATED_AT
    assert datetime.fromisoformat(first["latest_analysis_created_at"]) == _CREATED_AT

    second = body["projects"][1]
    assert second["id"] == str(_OTHER_PROJECT_ID)
    assert second["name"] == "catalog"
    assert second["is_sample"] is True
    assert second["latest_analysis_state"] is None
    assert second["latest_analysis_created_at"] is None


def test_projects_keep_database_order() -> None:
    database = FakeDatabase(
        projects=[
            ProjectSummary(
                id=_PROJECT_ID,
                name="newest",
                created_at=_CREATED_AT,
                is_sample=False,
                latest_analysis_state=None,
                latest_analysis_created_at=None,
            ),
            ProjectSummary(
                id=_OTHER_PROJECT_ID,
                name="middle",
                created_at=_EARLIER,
                is_sample=False,
                latest_analysis_state=None,
                latest_analysis_created_at=None,
            ),
            ProjectSummary(
                id=_THIRD_PROJECT_ID,
                name="oldest",
                created_at=_EARLIER,
                is_sample=False,
                latest_analysis_state=None,
                latest_analysis_created_at=None,
            ),
        ]
    )
    with _client(database) as client:
        response = client.get(
            "/v1/projects", params={"organisation_id": "org_1"}, headers=_authorization()
        )
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["projects"]] == [
        str(_PROJECT_ID),
        str(_OTHER_PROJECT_ID),
        str(_THIRD_PROJECT_ID),
    ]
    assert database.list_projects_calls == [("user_123", "org_1")]


def test_get_project_returns_project_and_analyses() -> None:
    database = FakeDatabase(project_details={_PROJECT_ID: _project_detail()})
    with _client(database) as client:
        response = client.get(f"/v1/projects/{_PROJECT_ID}", headers=_authorization())
    assert response.status_code == 200
    body = response.json()
    assert list(body) == ["project", "analyses"]

    project = body["project"]
    assert set(project) == {"id", "name", "created_at", "is_sample"}
    assert project["id"] == str(_PROJECT_ID)
    assert project["name"] == "checkout"
    assert project["is_sample"] is False
    assert datetime.fromisoformat(project["created_at"]) == _CREATED_AT

    analyses = body["analyses"]
    assert [item["id"] for item in analyses] == [str(_ANALYSIS_ID), str(_OTHER_ANALYSIS_ID)]
    assert set(analyses[0]) == {"id", "state", "created_at", "is_sample"}
    assert analyses[0]["state"] == "complete"
    assert analyses[1]["state"] == "queued"
    assert analyses[1]["is_sample"] is True
    assert database.get_project_calls == [("user_123", _PROJECT_ID)]


def test_get_analysis_returns_fields() -> None:
    database = FakeDatabase(analysis_details={_ANALYSIS_ID: _analysis_detail()})
    with _client(database) as client:
        response = client.get(f"/v1/analyses/{_ANALYSIS_ID}", headers=_authorization())
    assert response.status_code == 200
    body = response.json()
    assert list(body) == ["analysis"]
    analysis = body["analysis"]
    assert set(analysis) == {
        "id",
        "project_id",
        "project_name",
        "state",
        "created_at",
        "is_sample",
    }
    assert analysis["id"] == str(_ANALYSIS_ID)
    assert analysis["project_id"] == str(_PROJECT_ID)
    assert analysis["project_name"] == "checkout"
    assert analysis["state"] == "complete"
    assert analysis["is_sample"] is False
    assert datetime.fromisoformat(analysis["created_at"]) == _CREATED_AT
    assert database.get_analysis_calls == [("user_123", _ANALYSIS_ID)]


def test_hidden_and_unknown_project_are_indistinguishable() -> None:
    database = FakeDatabase()
    with _client(database) as client:
        hidden = client.get(f"/v1/projects/{_PROJECT_ID}", headers=_authorization())
        unknown = client.get(f"/v1/projects/{_OTHER_PROJECT_ID}", headers=_authorization())
    assert hidden.status_code == 404
    assert hidden.status_code == unknown.status_code
    assert hidden.json() == unknown.json() == {"detail": "Not found"}


def test_hidden_and_unknown_analysis_are_indistinguishable() -> None:
    database = FakeDatabase()
    with _client(database) as client:
        hidden = client.get(f"/v1/analyses/{_ANALYSIS_ID}", headers=_authorization())
        unknown = client.get(f"/v1/analyses/{_OTHER_ANALYSIS_ID}", headers=_authorization())
    assert hidden.status_code == 404
    assert hidden.status_code == unknown.status_code
    assert hidden.json() == unknown.json() == {"detail": "Not found"}


def test_malformed_identifiers_return_the_not_found_body() -> None:
    database = FakeDatabase()
    with _client(database) as client:
        project = client.get("/v1/projects/not-a-uuid", headers=_authorization())
        analysis = client.get("/v1/analyses/not-a-uuid", headers=_authorization())
    assert project.status_code == 404
    assert analysis.status_code == 404
    assert project.json() == analysis.json() == {"detail": "Not found"}
    assert database.get_project_calls == []
    assert database.get_analysis_calls == []


def test_missing_token_is_refused() -> None:
    database = FakeDatabase()
    with _client(database) as client:
        responses = [
            client.get("/v1/projects", params={"organisation_id": "org_1"}),
            client.get(f"/v1/projects/{_PROJECT_ID}"),
            client.get(f"/v1/analyses/{_ANALYSIS_ID}"),
        ]
    for response in responses:
        _assert_unauthorized(response)
    assert database.list_projects_calls == []
    assert database.get_project_calls == []
    assert database.get_analysis_calls == []


def test_invalid_token_is_refused() -> None:
    database = FakeDatabase()
    headers = {"Authorization": "Bearer not-valid"}
    with _client(database) as client:
        responses = [
            client.get("/v1/projects", params={"organisation_id": "org_1"}, headers=headers),
            client.get(f"/v1/projects/{_PROJECT_ID}", headers=headers),
            client.get(f"/v1/analyses/{_ANALYSIS_ID}", headers=headers),
        ]
    for response in responses:
        _assert_unauthorized(response)
    assert database.list_projects_calls == []
    assert database.get_project_calls == []
    assert database.get_analysis_calls == []


def test_project_routes_do_not_check_membership() -> None:
    database = FakeDatabase(
        projects=[],
        project_details={_PROJECT_ID: _project_detail()},
        analysis_details={_ANALYSIS_ID: _analysis_detail()},
    )
    with _client(database) as client:
        list_response = client.get(
            "/v1/projects", params={"organisation_id": "org_1"}, headers=_authorization()
        )
        project_response = client.get(f"/v1/projects/{_PROJECT_ID}", headers=_authorization())
        analysis_response = client.get(f"/v1/analyses/{_ANALYSIS_ID}", headers=_authorization())
    assert list_response.status_code == 200
    assert project_response.status_code == 200
    assert analysis_response.status_code == 200
    assert database.is_member_calls == []
