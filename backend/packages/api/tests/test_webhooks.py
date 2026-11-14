import base64
import hashlib
import hmac
import json
import time
from typing import cast
from uuid import UUID

import httpx
import pytest
from codecraft_api.app import create_app
from codecraft_api.config import Settings
from codecraft_api.token_verifier import VerifiedToken
from codecraft_storage import (
    AnalysisDetail,
    AnalysisSummary,
    DatabaseLike,
    OrganisationSummary,
    ProjectDetail,
    ProjectSummary,
)
from fastapi.testclient import TestClient

_SECRET = "whsec_" + base64.b64encode(b"test-signing-secret").decode()


class FakeDatabase:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, str]] = []
        self.owners: list[tuple[str, str]] = []
        self.deletes: list[tuple[str, str]] = []
        self.organisation_deletes: list[str] = []
        self.is_member_calls: list[tuple[str, str]] = []
        self.list_analyses_calls: list[tuple[str, str]] = []

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
        return []

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
        self.owners.append((user_id, organisation_id))

    async def delete_membership(self, user_id: str, organisation_id: str) -> None:
        self.deletes.append((user_id, organisation_id))


class FakeVerifier:
    def verify(self, token: str) -> VerifiedToken:
        return VerifiedToken(user_id="unused", organisation_id=None)


def _settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql://api@example/db",
        MEMBERSHIP_SYNC_DATABASE_URL="postgresql://sync@example/db",
        CLERK_JWT_ISSUER="https://clerk.example",
        CLERK_WEBHOOK_SIGNING_SECRET=_SECRET,
        CLERK_SECRET_KEY="sk_test_secret",
    )


def _client(database: DatabaseLike) -> httpx.Client:
    # Starlette's TestClient is an httpx.Client at runtime, but its annotations
    # name httpx2, which is not installed. Narrow to the base class it really uses.
    return cast(
        "httpx.Client",
        TestClient(create_app(_settings(), database=database, verifier=FakeVerifier())),
    )


def _signature(body: bytes, svix_id: str, timestamp: int) -> str:
    secret = base64.b64decode(_SECRET.removeprefix("whsec_"))
    signed = f"{svix_id}.{timestamp}.".encode() + body
    digest = hmac.new(secret, signed, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode()


def _headers(body: bytes, timestamp: int | None = None) -> dict[str, str]:
    moment = int(time.time()) if timestamp is None else timestamp
    return {
        "svix-id": "msg_123",
        "svix-timestamp": str(moment),
        "svix-signature": _signature(body, "msg_123", moment),
        "content-type": "application/json",
    }


def _payload(event_type: str, user_id: str = "user_1", organisation_id: str = "org_1") -> bytes:
    document = {
        "type": event_type,
        "data": {
            "organization": {"id": organisation_id},
            "public_user_data": {"user_id": user_id},
        },
    }
    return json.dumps(document).encode()


def _organisation_deleted_payload(data: dict[str, object]) -> bytes:
    return json.dumps({"type": "organization.deleted", "data": data}).encode()


def test_created_event_upserts_membership() -> None:
    database = FakeDatabase()
    body = _payload("organizationMembership.created")
    with _client(database) as client:
        response = client.post("/webhooks/clerk", content=body, headers=_headers(body))
    assert response.status_code == 204
    assert database.upserts == [("user_1", "org_1")]
    assert database.deletes == []


def test_organisation_created_records_owner() -> None:
    database = FakeDatabase()
    body = json.dumps(
        {
            "type": "organization.created",
            "data": {"id": "org_1", "created_by": "user_1"},
        }
    ).encode()
    with _client(database) as client:
        response = client.post("/webhooks/clerk", content=body, headers=_headers(body))
    assert response.status_code == 204
    assert database.owners == [("user_1", "org_1")]
    assert database.upserts == []


def test_organisation_created_without_creator_is_ignored() -> None:
    database = FakeDatabase()
    body = json.dumps({"type": "organization.created", "data": {"id": "org_1"}}).encode()
    with _client(database) as client:
        response = client.post("/webhooks/clerk", content=body, headers=_headers(body))
    assert response.status_code == 204
    assert database.owners == []


def test_deleted_event_removes_membership() -> None:
    database = FakeDatabase()
    body = _payload("organizationMembership.deleted")
    with _client(database) as client:
        response = client.post("/webhooks/clerk", content=body, headers=_headers(body))
    assert response.status_code == 204
    assert database.deletes == [("user_1", "org_1")]
    assert database.upserts == []


def test_invalid_signature_writes_nothing() -> None:
    database = FakeDatabase()
    signed_body = _payload("organizationMembership.created")
    headers = _headers(signed_body)
    with _client(database) as client:
        response = client.post("/webhooks/clerk", content=signed_body + b" ", headers=headers)
    assert response.status_code == 401
    assert database.upserts == []
    assert database.deletes == []


def test_stale_timestamp_writes_nothing() -> None:
    database = FakeDatabase()
    body = _payload("organizationMembership.created")
    stale = int(time.time()) - 301
    with _client(database) as client:
        response = client.post("/webhooks/clerk", content=body, headers=_headers(body, stale))
    assert response.status_code == 401
    assert database.upserts == []
    assert database.deletes == []


def test_other_event_type_is_ignored() -> None:
    database = FakeDatabase()
    body = _payload("organization.updated")
    with _client(database) as client:
        response = client.post("/webhooks/clerk", content=body, headers=_headers(body))
    assert response.status_code == 204
    assert database.upserts == []
    assert database.deletes == []
    assert database.organisation_deletes == []


def test_organisation_deleted_event_deletes_organisation() -> None:
    database = FakeDatabase()
    body = _organisation_deleted_payload({"id": "org_1"})
    with _client(database) as client:
        response = client.post("/webhooks/clerk", content=body, headers=_headers(body))
    assert response.status_code == 204
    assert database.organisation_deletes == ["org_1"]
    assert database.upserts == []
    assert database.deletes == []


def test_organisation_deleted_event_with_no_rows_still_succeeds() -> None:
    # The fake reports success without removing anything, which is what the
    # routine does for an organisation identifier that matches no rows.
    database = FakeDatabase()
    body = _organisation_deleted_payload({"id": "org_without_rows"})
    with _client(database) as client:
        response = client.post("/webhooks/clerk", content=body, headers=_headers(body))
    assert response.status_code == 204
    assert database.organisation_deletes == ["org_without_rows"]


def test_organisation_deleted_event_with_invalid_signature_writes_nothing() -> None:
    database = FakeDatabase()
    signed_body = _organisation_deleted_payload({"id": "org_1"})
    headers = _headers(signed_body)
    with _client(database) as client:
        response = client.post("/webhooks/clerk", content=signed_body + b" ", headers=headers)
    assert response.status_code == 401
    assert database.organisation_deletes == []


@pytest.mark.parametrize("data", [{}, {"id": ""}])
def test_organisation_deleted_event_without_identifier_is_rejected(data: dict[str, object]) -> None:
    database = FakeDatabase()
    body = _organisation_deleted_payload(data)
    with _client(database) as client:
        response = client.post("/webhooks/clerk", content=body, headers=_headers(body))
    assert response.status_code == 400
    assert database.organisation_deletes == []


def test_missing_signature_headers_are_refused() -> None:
    database = FakeDatabase()
    body = _payload("organizationMembership.created")
    with _client(database) as client:
        response = client.post("/webhooks/clerk", content=body)
    assert response.status_code == 401
    assert database.upserts == []


def test_signed_but_malformed_payload_is_rejected() -> None:
    database = FakeDatabase()
    body = b"{ not json"
    with _client(database) as client:
        response = client.post("/webhooks/clerk", content=body, headers=_headers(body))
    assert response.status_code == 400
    assert database.upserts == []
    assert database.deletes == []
