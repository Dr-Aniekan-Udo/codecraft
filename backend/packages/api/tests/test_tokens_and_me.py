import logging
import time
from typing import cast
from uuid import UUID

import httpx
import jwt
import pytest
from codecraft_api.app import create_app
from codecraft_api.config import Settings
from codecraft_api.token_verifier import TokenVerifier
from codecraft_storage import (
    AnalysisDetail,
    AnalysisSummary,
    DatabaseLike,
    OrganisationSummary,
    ProjectDetail,
    ProjectSummary,
)
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

_ISSUER = "https://clerk.example"
_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_JWK = jwt.PyJWK.from_json(RSAAlgorithm.to_jwk(_PRIVATE_KEY.public_key()), algorithm="RS256")


class StaticJWKClient(jwt.PyJWKClient):
    """A JWKS client whose key is fixed, so tests never touch the network."""

    def __init__(self, key: jwt.PyJWK) -> None:
        super().__init__("https://unused.invalid/.well-known/jwks.json")
        self._static_key = key

    def get_signing_key_from_jwt(self, token: str | bytes) -> jwt.PyJWK:
        return self._static_key


class FakeDatabase:
    def __init__(self) -> None:
        self.memberships: set[tuple[str, str]] = set()
        self.is_member_calls: list[tuple[str, str]] = []
        self.list_analyses_calls: list[tuple[str, str]] = []
        self.analyses: list[AnalysisSummary] = []
        self.organisation_deletes: list[str] = []
        self.upserts: list[tuple[str, str]] = []
        self.deletes: list[tuple[str, str]] = []

    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def is_member(self, user_id: str, organisation_id: str) -> bool:
        self.is_member_calls.append((user_id, organisation_id))
        return (user_id, organisation_id) in self.memberships

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

    async def upsert_membership(self, user_id: str, organisation_id: str) -> None:
        self.upserts.append((user_id, organisation_id))

    async def set_owner(self, user_id: str, organisation_id: str) -> None:
        pass

    async def delete_membership(self, user_id: str, organisation_id: str) -> None:
        self.deletes.append((user_id, organisation_id))


def _database() -> DatabaseLike:
    return FakeDatabase()


def _settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql://api@example/db",
        MEMBERSHIP_SYNC_DATABASE_URL="postgresql://sync@example/db",
        CLERK_JWT_ISSUER=_ISSUER,
        CLERK_WEBHOOK_SIGNING_SECRET="whsec_c2VjcmV0",
        CLERK_SECRET_KEY="sk_test_secret",
    )


def _verifier() -> TokenVerifier:
    return TokenVerifier(_ISSUER, jwks_client=StaticJWKClient(_PUBLIC_JWK))


def _claims() -> dict[str, object]:
    return {
        "sub": "user_123",
        "o": {"id": "org_123", "rol": "admin"},
        "iss": _ISSUER,
        "exp": int(time.time()) + 300,
    }


def _member_claims() -> dict[str, object]:
    claims = _claims()
    claims["o"] = {"id": "org_123", "rol": "member"}
    return claims


def _token(claims: dict[str, object]) -> str:
    return jwt.encode(claims, _PRIVATE_KEY, algorithm="RS256", headers={"kid": "test"})


def _client(database: DatabaseLike) -> httpx.Client:
    # Starlette's TestClient is an httpx.Client at runtime, but its annotations
    # name httpx2, which is not installed. Narrow to the base class it really uses.
    return cast(
        "httpx.Client", TestClient(create_app(_settings(), database=database, verifier=_verifier()))
    )


def _assert_unauthorized(response: httpx.Response) -> None:
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_missing_token_is_refused() -> None:
    with _client(_database()) as client:
        response = client.get("/v1/me")
    _assert_unauthorized(response)


def test_expired_token_is_refused() -> None:
    claims = _claims()
    claims["exp"] = int(time.time()) - 10
    with _client(_database()) as client:
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {_token(claims)}"})
    _assert_unauthorized(response)


def test_expired_token_logs_reason_without_token_data(
    caplog: pytest.LogCaptureFixture,
) -> None:
    claims = _claims()
    claims["exp"] = int(time.time()) - 10
    token = _token(claims)

    with (
        caplog.at_level(logging.WARNING, logger="codecraft_api.token_verifier"),
        _client(_database()) as client,
    ):
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})

    _assert_unauthorized(response)
    records = [record for record in caplog.records if record.name == "codecraft_api.token_verifier"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "ExpiredSignatureError" in message
    assert "signature has expired" in message
    for forbidden in (token, "user_123", "org_123", _ISSUER, str(claims["exp"])):
        assert forbidden not in message


def test_altered_token_is_refused() -> None:
    header, payload, signature = _token(_claims()).split(".")
    first = "A" if signature[0] != "A" else "B"
    altered = f"{header}.{payload}.{first}{signature[1:]}"
    with _client(_database()) as client:
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {altered}"})
    _assert_unauthorized(response)


def test_wrong_issuer_is_refused() -> None:
    claims = _claims()
    claims["iss"] = "https://not-clerk.example"
    with _client(_database()) as client:
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {_token(claims)}"})
    _assert_unauthorized(response)


def test_token_without_expiry_is_refused() -> None:
    claims = _claims()
    del claims["exp"]
    with _client(_database()) as client:
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {_token(claims)}"})
    _assert_unauthorized(response)


def test_token_with_o_id_returns_organisation() -> None:
    database = FakeDatabase()
    database.memberships.add(("user_123", "org_123"))
    with _client(database) as client:
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {_token(_claims())}"})
    assert response.status_code == 200
    assert response.json() == {
        "user_id": "user_123",
        "organisation_id": "org_123",
        "role": "admin",
    }


def test_admin_token_returns_admin_role() -> None:
    database = FakeDatabase()
    database.memberships.add(("user_123", "org_123"))
    with _client(database) as client:
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {_token(_claims())}"})
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_member_token_returns_member_role() -> None:
    database = FakeDatabase()
    database.memberships.add(("user_123", "org_123"))
    with _client(database) as client:
        response = client.get(
            "/v1/me",
            headers={"Authorization": f"Bearer {_token(_member_claims())}"},
        )
    assert response.status_code == 200
    assert response.json()["role"] == "member"


def test_token_with_no_o_has_no_active_organisation() -> None:
    database = FakeDatabase()
    claims = _claims()
    del claims["o"]
    with _client(database) as client:
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {_token(claims)}"})
    assert response.status_code == 403
    assert response.json()["detail"] == "No active organisation"
    assert database.is_member_calls == []


def test_token_with_only_org_id_has_no_active_organisation() -> None:
    database = FakeDatabase()
    claims = _claims()
    del claims["o"]
    claims["org_id"] = "org_123"
    with _client(database) as client:
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {_token(claims)}"})
    assert response.status_code == 403
    assert response.json()["detail"] == "No active organisation"
    assert database.is_member_calls == []


def test_token_with_o_without_id_has_no_active_organisation() -> None:
    database = FakeDatabase()
    claims = _claims()
    claims["o"] = {}
    with _client(database) as client:
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {_token(claims)}"})
    assert response.status_code == 403
    assert response.json()["detail"] == "No active organisation"
    assert database.is_member_calls == []


def test_non_member_is_forbidden() -> None:
    database = FakeDatabase()
    with _client(database) as client:
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {_token(_claims())}"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Not a member of the active organisation"
    assert database.is_member_calls == [("user_123", "org_123")]
