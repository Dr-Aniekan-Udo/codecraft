import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import httpx
import pytest
from codecraft_api.app import create_app
from codecraft_api.clerk_client import (
    ClerkApiError,
    ClerkInvitation,
    ClerkOrganisation,
    ClerkUser,
)
from codecraft_api.config import Settings
from codecraft_api.routes import ADMIN_ROLE
from codecraft_api.token_verifier import InvalidTokenError, VerifiedToken
from codecraft_storage import (
    AnalysisDetail,
    AnalysisSummary,
    CreationAttemptRow,
    CreationAttemptStore,
    DatabaseLike,
    OrganisationSummary,
    ProjectDetail,
    ProjectSummary,
)
from fastapi.testclient import TestClient

_CREATED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


class FakeVerifier:
    def __init__(
        self, *, organisation_id: str | None = "org_1", role: str | None = ADMIN_ROLE
    ) -> None:
        self._organisation_id = organisation_id
        self._role = role

    def verify(self, token: str) -> VerifiedToken:
        if token != "valid-token":
            raise InvalidTokenError("token verification failed")
        return VerifiedToken(
            user_id="user_123", organisation_id=self._organisation_id, role=self._role
        )


class FakeDatabase:
    def __init__(
        self,
        *,
        organisations: list[OrganisationSummary] | None = None,
        owner: bool = True,
        other_owned_organisation: bool = True,
        another_organisation: bool = True,
        owned_organisations: dict[str, set[str]] | None = None,
    ) -> None:
        self.organisations = [] if organisations is None else organisations
        self.owner = owner
        self.other_owned_organisation = other_owned_organisation
        self.another_organisation = another_organisation
        self.owned_organisations = owned_organisations
        self.memberships: set[tuple[str, str]] = set()
        self.list_organisations_calls: list[str] = []
        self.is_member_calls: list[tuple[str, str]] = []
        self.owner_calls: list[tuple[str, str]] = []
        self.other_owned_calls: list[tuple[str, str]] = []
        self.another_organisation_calls: list[tuple[str, str]] = []
        self.deleted_memberships: list[tuple[str, str]] = []
        self.organisation_deletes: list[str] = []
        self.owners: list[tuple[str, str]] = []
        self.attempts: dict[tuple[str, str], CreationAttemptRow] = {}
        # Stands in for the database's advisory lock: two processes sharing a
        # key must not both reach the identity provider.
        self.creation_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self.creation_attempt_calls: list[tuple[str, str]] = []
        self.mark_created_failures = 0
        self.owner_write_failures = 0

    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def is_member(self, user_id: str, organisation_id: str) -> bool:
        self.is_member_calls.append((user_id, organisation_id))
        return (user_id, organisation_id) in self.memberships

    async def list_organisations(self, user_id: str) -> list[OrganisationSummary]:
        self.list_organisations_calls.append(user_id)
        return self.organisations

    async def is_owner(self, user_id: str, organisation_id: str) -> bool:
        self.owner_calls.append((user_id, organisation_id))
        if self.owned_organisations is not None:
            return organisation_id in self.owned_organisations.get(user_id, set())
        return self.owner

    async def has_other_owned_organisation(self, user_id: str, organisation_id: str) -> bool:
        self.other_owned_calls.append((user_id, organisation_id))
        return self.other_owned_organisation

    async def has_other_organisation(self, user_id: str, organisation_id: str) -> bool:
        self.another_organisation_calls.append((user_id, organisation_id))
        return self.another_organisation

    async def list_analyses(self, user_id: str, organisation_id: str) -> list[AnalysisSummary]:
        return []

    async def list_projects(self, user_id: str, organisation_id: str) -> list[ProjectSummary]:
        return []

    async def get_project(self, user_id: str, project_id: UUID) -> ProjectDetail | None:
        return None

    async def get_analysis(self, user_id: str, analysis_id: UUID) -> AnalysisDetail | None:
        return None

    async def delete_organisation(self, organisation_id: str) -> None:
        self.organisation_deletes.append(organisation_id)

    async def upsert_membership(self, user_id: str, organisation_id: str) -> None: ...

    async def set_owner(self, user_id: str, organisation_id: str) -> None:
        if self.owner_write_failures > 0:
            self.owner_write_failures -= 1
            raise RuntimeError("the owner row could not be written")
        self.owners.append((user_id, organisation_id))
        if not any(item.organisation_id == organisation_id for item in self.organisations):
            self.organisations.append(OrganisationSummary(organisation_id, True, _CREATED_AT))

    async def delete_membership(self, user_id: str, organisation_id: str) -> None:
        self.deleted_memberships.append((user_id, organisation_id))

    def delete_organisation_attempts(self, organisation_id: str) -> None:
        for key in list(self.attempts):
            if self.attempts[key].organisation_id == organisation_id:
                del self.attempts[key]

    @asynccontextmanager
    async def creation_attempt(
        self, user_id: str, idempotency_key: str
    ) -> AsyncGenerator[CreationAttemptStore]:
        key = (user_id, idempotency_key)
        lock = self.creation_locks.setdefault(key, asyncio.Lock())
        async with lock:
            self.creation_attempt_calls.append(key)
            previous = self.attempts.get(key)
            try:
                yield FakeCreationAttemptStore(self, key)
            except BaseException:
                # The real creation transaction rolls back every attempt write.
                if previous is None:
                    self.attempts.pop(key, None)
                else:
                    self.attempts[key] = previous
                raise


class FakeCreationAttemptStore:
    def __init__(self, database: FakeDatabase, key: tuple[str, str]) -> None:
        self._database = database
        self._key = key

    def _write(self, status: str, organisation_id: str | None) -> None:
        # The real table's check constraint pairs a created status with an
        # organisation id; the fake rejects any row that breaks the pairing.
        if (status == "created") != (organisation_id is not None):
            raise ValueError("a created attempt must name an organisation")
        self._database.attempts[self._key] = CreationAttemptRow(status, organisation_id)

    async def read(self) -> CreationAttemptRow | None:
        return self._database.attempts.get(self._key)

    async def mark_claimed(self) -> None:
        self._write("claimed", None)

    async def mark_created(self, organisation_id: str) -> None:
        if self._database.mark_created_failures > 0:
            self._database.mark_created_failures -= 1
            raise RuntimeError("the creation attempt row could not be written")
        self._write("created", organisation_id)

    async def mark_failed(self) -> None:
        self._write("failed", None)


class FakeClerk:
    def __init__(
        self,
        *,
        error: ClerkApiError | None = None,
        error_methods: set[str] | None = None,
        email_address: str = "ada@example.com",
        race_organisation: ClerkOrganisation | None = None,
        recent_organisation: ClerkOrganisation | None = None,
    ) -> None:
        self.error = error
        self.error_methods = error_methods
        self.email_address = email_address
        self.race_organisation = race_organisation
        self.recent_organisation = recent_organisation
        self.created: list[dict[str, str]] = []
        self.deleted: list[str] = []
        self.created_organisations: list[dict[str, str]] = []
        self.recorded_idempotency_keys: list[tuple[str, str]] = []
        self.created_at_offset_ms = 0
        self.role_changes: list[dict[str, str]] = []
        self.removed_memberships: list[dict[str, str]] = []
        self.get_user_calls: list[str] = []
        self.find_by_key_calls = 0
        self._organisations_by_idempotency_key: dict[tuple[str, str], ClerkOrganisation] = {}
        self._created_organisations: list[tuple[str, ClerkOrganisation]] = []
        self._organisation_count = 0
        self.opened = False
        self.closed = False
        self.create_started = asyncio.Event()
        self.release_create = asyncio.Event()
        self.release_create.set()

    def _raise_injected_error(self, method: str) -> None:
        if self.error is not None and (self.error_methods is None or method in self.error_methods):
            raise self.error

    async def open(self) -> None:
        self.opened = True

    async def close(self) -> None:
        self.closed = True

    async def get_user(self, user_id: str) -> ClerkUser:
        self.get_user_calls.append(user_id)
        return ClerkUser(name="Ada Lovelace", email_address=self.email_address)

    async def create_invitation(self, **kwargs: str) -> ClerkInvitation:
        self._raise_injected_error("create_invitation")
        self.created.append(dict(kwargs))
        return ClerkInvitation(id="orginv_1", email_address=str(kwargs["email_address"]))

    async def delete_organisation(self, organisation_id: str) -> None:
        self._raise_injected_error("delete_organisation")
        self.deleted.append(organisation_id)

    async def create_organisation(
        self,
        *,
        name: str,
        created_by: str,
        idempotency_key: str,
    ) -> ClerkOrganisation:
        self._raise_injected_error("create_organisation")
        self.create_started.set()
        await self.release_create.wait()
        self._organisation_count += 1
        organisation = ClerkOrganisation(
            id=f"org_created_{self._organisation_count}",
            name=name,
            created_at=int(time.time() * 1000) - self.created_at_offset_ms,
        )
        self.created_organisations.append(
            {
                "name": name,
                "created_by": created_by,
                "idempotency_key": idempotency_key,
            }
        )
        self._organisations_by_idempotency_key[(created_by, idempotency_key)] = organisation
        self._created_organisations.append((created_by, organisation))
        return organisation

    async def find_organisation_by_idempotency_key(
        self,
        *,
        user_id: str,
        idempotency_key: str,
    ) -> ClerkOrganisation | None:
        self._raise_injected_error("find_organisation_by_idempotency_key")
        self.find_by_key_calls += 1
        if self.race_organisation is not None and self.find_by_key_calls > 1:
            return self.race_organisation
        return self._organisations_by_idempotency_key.get((user_id, idempotency_key))

    async def find_recent_organisation_by_name(
        self,
        *,
        user_id: str,
        name: str,
    ) -> ClerkOrganisation | None:
        self._raise_injected_error("find_recent_organisation_by_name")
        now = int(time.time() * 1000)
        candidates = [
            organisation
            for created_by, organisation in self._created_organisations
            if created_by == user_id
        ]
        if self.recent_organisation is not None:
            candidates.append(self.recent_organisation)
        for organisation in candidates:
            if (
                organisation.name == name
                and organisation.created_at is not None
                and now - organisation.created_at <= 10_000
            ):
                return organisation
        return None

    async def record_organisation_idempotency_key(
        self,
        *,
        organisation: ClerkOrganisation,
        idempotency_key: str,
    ) -> None:
        self._raise_injected_error("record_organisation_idempotency_key")
        self.recorded_idempotency_keys.append((organisation.id, idempotency_key))
        for created_by, created in self._created_organisations:
            if created.id == organisation.id:
                self._organisations_by_idempotency_key[(created_by, idempotency_key)] = organisation
                break

    async def update_organisation_membership_role(
        self,
        *,
        organisation_id: str,
        member_user_id: str,
        role: str,
    ) -> None:
        self._raise_injected_error("update_organisation_membership_role")
        self.role_changes.append(
            {
                "organisation_id": organisation_id,
                "member_user_id": member_user_id,
                "role": role,
            }
        )

    async def delete_organisation_membership(
        self,
        *,
        organisation_id: str,
        member_user_id: str,
    ) -> None:
        self._raise_injected_error("delete_organisation_membership")
        self.removed_memberships.append(
            {
                "organisation_id": organisation_id,
                "member_user_id": member_user_id,
            }
        )


def _settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql://api@example/db",
        MEMBERSHIP_SYNC_DATABASE_URL="postgresql://sync@example/db",
        CLERK_JWT_ISSUER="https://clerk.example",
        CLERK_WEBHOOK_SIGNING_SECRET="whsec_c2VjcmV0",
        CLERK_SECRET_KEY="sk_test_secret",
        PARSE_MAX_FILES=50_000,
        PARSE_MAX_FILE_BYTES=2_000_000,
    )


def _client(
    database: DatabaseLike,
    clerk: FakeClerk,
    *,
    organisation_id: str | None = "org_1",
    role: str | None = ADMIN_ROLE,
    raise_server_exceptions: bool = True,
) -> httpx.Client:
    return cast(
        "httpx.Client",
        TestClient(
            create_app(
                _settings(),
                database=database,
                verifier=FakeVerifier(organisation_id=organisation_id, role=role),
                clerk=clerk,
            ),
            raise_server_exceptions=raise_server_exceptions,
        ),
    )


def _authorization() -> dict[str, str]:
    return {"Authorization": "Bearer valid-token"}


def _database_with_member() -> FakeDatabase:
    database = FakeDatabase()
    database.memberships.add(("user_123", "org_1"))
    return database


def test_list_organisations_returns_owner_flags_without_active_organisation() -> None:
    database = FakeDatabase(organisations=[OrganisationSummary("org_1", True, _CREATED_AT)])
    clerk = FakeClerk()
    with _client(database, clerk, organisation_id=None) as client:
        response = client.get("/v1/organisations", headers=_authorization())
    assert response.status_code == 200
    assert response.json() == {
        "organisations": [
            {
                "organisation_id": "org_1",
                "is_owner": True,
                "created_at": _CREATED_AT.isoformat().replace("+00:00", "Z"),
            }
        ]
    }
    assert database.list_organisations_calls == ["user_123"]


def test_create_organisation_same_key_creates_once_and_returns_same_organisation() -> None:
    database = FakeDatabase()
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        first = client.post(
            "/v1/organisations",
            json={"name": "Design", "idempotency_key": "key-1"},
            headers=_authorization(),
        )
        second = client.post(
            "/v1/organisations",
            json={"name": "Design", "idempotency_key": "key-1"},
            headers=_authorization(),
        )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == {"organisation_id": "org_created_1"}
    assert second.json() == {"organisation_id": "org_created_1"}
    assert len(clerk.created_organisations) == 1
    assert "slug" not in clerk.created_organisations[0]
    assert database.owners
    assert all(owner == ("user_123", "org_created_1") for owner in database.owners)


def test_create_organisation_different_keys_create_different_organisations() -> None:
    database = FakeDatabase()
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        first = client.post(
            "/v1/organisations",
            json={"name": "Design", "idempotency_key": "key-1"},
            headers=_authorization(),
        )
        second = client.post(
            "/v1/organisations",
            json={"name": "Research", "idempotency_key": "key-2"},
            headers=_authorization(),
        )
    assert first.json() == {"organisation_id": "org_created_1"}
    assert second.json() == {"organisation_id": "org_created_2"}
    assert len(clerk.created_organisations) == 2
    assert all("slug" not in entry for entry in clerk.created_organisations)
    assert [entry["idempotency_key"] for entry in clerk.created_organisations] == [
        "key-1",
        "key-2",
    ]


def test_create_organisation_same_name_within_ten_seconds_reuses_the_first() -> None:
    database = FakeDatabase()
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        first = client.post(
            "/v1/organisations",
            json={"name": "Design", "idempotency_key": "key-1"},
            headers=_authorization(),
        )
        second = client.post(
            "/v1/organisations",
            json={"name": "Design", "idempotency_key": "key-2"},
            headers=_authorization(),
        )
    assert first.json() == {"organisation_id": "org_created_1"}
    assert second.json() == {"organisation_id": "org_created_1"}
    assert len(clerk.created_organisations) == 1


def test_create_organisation_same_name_after_ten_seconds_creates_again() -> None:
    database = FakeDatabase()
    clerk = FakeClerk(
        recent_organisation=ClerkOrganisation(
            id="org_old",
            name="Design",
            created_at=int(time.time() * 1000) - 11_000,
        )
    )
    with _client(database, clerk) as client:
        response = client.post(
            "/v1/organisations",
            json={"name": "Design", "idempotency_key": "key-1"},
            headers=_authorization(),
        )
    assert response.status_code == 200
    assert response.json() == {"organisation_id": "org_created_1"}
    assert len(clerk.created_organisations) == 1


def test_reused_recent_organisation_records_the_new_key_for_a_later_retry() -> None:
    database = FakeDatabase()
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        first = client.post(
            "/v1/organisations",
            json={"name": "Design", "idempotency_key": "key-1"},
            headers=_authorization(),
        )
        second = client.post(
            "/v1/organisations",
            json={"name": "Design", "idempotency_key": "key-2"},
            headers=_authorization(),
        )
        assert clerk.recorded_idempotency_keys == [("org_created_1", "key-2")]
        # Leave the ten-second name window, so only the stored key can match.
        clerk.created_at_offset_ms = 11_000
        retried = client.post(
            "/v1/organisations",
            json={"name": "Design", "idempotency_key": "key-2"},
            headers=_authorization(),
        )
        earlier = client.post(
            "/v1/organisations",
            json={"name": "Design", "idempotency_key": "key-1"},
            headers=_authorization(),
        )
    assert first.status_code == 200
    assert second.status_code == 200
    assert retried.status_code == 200
    assert earlier.status_code == 200
    assert first.json() == {"organisation_id": "org_created_1"}
    assert second.json() == {"organisation_id": "org_created_1"}
    assert retried.json() == {"organisation_id": "org_created_1"}
    assert earlier.json() == {"organisation_id": "org_created_1"}
    assert len(clerk.created_organisations) == 1


def test_create_organisation_retries_by_idempotency_key_after_conflict() -> None:
    database = FakeDatabase()
    raced = ClerkOrganisation(id="org_raced", name="Design")
    clerk = FakeClerk(
        error=ClerkApiError(409, "conflict"),
        error_methods={"create_organisation"},
        race_organisation=raced,
    )

    with _client(database, clerk) as client:
        response = client.post(
            "/v1/organisations",
            json={"name": "Design", "idempotency_key": "key-1"},
            headers=_authorization(),
        )

    assert response.status_code == 200
    assert response.json() == {"organisation_id": "org_raced"}
    assert clerk.find_by_key_calls == 2
    assert clerk.created_organisations == []
    assert database.owners == [("user_123", "org_raced")]


def test_two_concurrent_requests_for_one_key_create_one_organisation() -> None:
    database = FakeDatabase()
    clerk = FakeClerk()
    clerk.release_create.clear()
    # Separate apps mean separate in-process locks, so only the database's
    # per-key lock can stop both requests from reaching Clerk.
    first_app = create_app(_settings(), database=database, verifier=FakeVerifier(), clerk=clerk)
    second_app = create_app(_settings(), database=database, verifier=FakeVerifier(), clerk=clerk)

    async def send_both() -> tuple[httpx.Response, httpx.Response]:
        payload = {"name": "Design", "idempotency_key": "key-1"}
        tasks: list[asyncio.Task[httpx.Response]] = []
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=first_app), base_url="http://test"
            ) as first,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=second_app), base_url="http://test"
            ) as second,
        ):
            try:
                first_request = asyncio.create_task(
                    first.post("/v1/organisations", json=payload, headers=_authorization())
                )
                tasks.append(first_request)
                await asyncio.wait_for(clerk.create_started.wait(), timeout=5)
                second_request = asyncio.create_task(
                    second.post("/v1/organisations", json=payload, headers=_authorization())
                )
                tasks.append(second_request)
                await asyncio.sleep(0.05)
                assert database.creation_attempt_calls == [("user_123", "key-1")]
                assert not second_request.done()
                clerk.release_create.set()
                return await asyncio.wait_for(
                    asyncio.gather(first_request, second_request), timeout=5
                )
            finally:
                clerk.release_create.set()
                for task in tasks:
                    if not task.done():
                        task.cancel()
                        with suppress(asyncio.CancelledError):
                            await task

    first_response, second_response = asyncio.run(send_both())

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json() == {"organisation_id": "org_created_1"}
    assert second_response.json() == {"organisation_id": "org_created_1"}
    assert len(clerk.created_organisations) == 1
    assert database.creation_attempt_calls == [
        ("user_123", "key-1"),
        ("user_123", "key-1"),
    ]


def test_retry_after_the_attempt_row_failed_returns_the_created_organisation() -> None:
    database = FakeDatabase()
    database.mark_created_failures = 1
    clerk = FakeClerk()
    with _client(database, clerk, raise_server_exceptions=False) as client:
        first = client.post(
            "/v1/organisations",
            json={"name": "Design", "idempotency_key": "key-1"},
            headers=_authorization(),
        )
        retried = client.post(
            "/v1/organisations",
            json={"name": "Design", "idempotency_key": "key-1"},
            headers=_authorization(),
        )
    assert first.status_code == 500
    assert retried.status_code == 200
    assert retried.json() == {"organisation_id": "org_created_1"}
    assert len(clerk.created_organisations) == 1
    assert clerk.find_by_key_calls == 2


def test_retry_after_the_owner_write_failed_returns_the_created_organisation() -> None:
    database = FakeDatabase()
    database.owner_write_failures = 1
    clerk = FakeClerk()
    with _client(database, clerk, raise_server_exceptions=False) as client:
        first = client.post(
            "/v1/organisations",
            json={"name": "Design", "idempotency_key": "key-1"},
            headers=_authorization(),
        )
        assert ("user_123", "key-1") not in database.attempts
        retried = client.post(
            "/v1/organisations",
            json={"name": "Design", "idempotency_key": "key-1"},
            headers=_authorization(),
        )
    assert first.status_code == 500
    assert retried.status_code == 200
    assert retried.json() == {"organisation_id": "org_created_1"}
    assert len(clerk.created_organisations) == 1
    assert clerk.find_by_key_calls == 2


def test_retry_after_the_organisation_is_deleted_does_not_return_it() -> None:
    database = FakeDatabase()
    deleted_organisation = "org_deleted"
    database.attempts[("user_123", "key-1")] = CreationAttemptRow("created", deleted_organisation)
    # The delete routine removes the attempt row with the organisation.
    database.delete_organisation_attempts(deleted_organisation)
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        response = client.post(
            "/v1/organisations",
            json={"name": "Design", "idempotency_key": "key-1"},
            headers=_authorization(),
        )
    assert response.status_code == 200
    assert response.json() != {"organisation_id": deleted_organisation}
    assert ("user_123", deleted_organisation) not in database.owners
    assert len(clerk.created_organisations) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Design"},
        {"name": "Design", "idempotency_key": ""},
        {"name": "Design", "idempotency_key": "   "},
    ],
)
def test_create_organisation_requires_an_idempotency_key(payload: dict[str, str]) -> None:
    database = FakeDatabase()
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        response = client.post("/v1/organisations", json=payload, headers=_authorization())
    assert response.status_code == 422
    assert clerk.created_organisations == []


@pytest.mark.parametrize(
    "payload",
    [
        {"idempotency_key": "key-1"},
        {"name": None, "idempotency_key": "key-1"},
        {"name": "", "idempotency_key": "key-1"},
        {"name": "   ", "idempotency_key": "key-1"},
    ],
)
def test_create_organisation_requires_a_name(payload: dict[str, object]) -> None:
    database = FakeDatabase()
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        response = client.post("/v1/organisations", json=payload, headers=_authorization())
    assert response.status_code == 422
    assert clerk.created_organisations == []


def test_create_organisation_uses_the_entered_name_without_the_personal_rule() -> None:
    database = FakeDatabase()
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        response = client.post(
            "/v1/organisations",
            json={"name": "Design Organisation", "idempotency_key": "key-1"},
            headers=_authorization(),
        )
    assert response.status_code == 200
    assert clerk.created_organisations == [
        {
            "name": "Design Organisation",
            "created_by": "user_123",
            "idempotency_key": "key-1",
        }
    ]
    assert clerk.get_user_calls == []


def test_create_personal_organisation_uses_the_default_name() -> None:
    database = FakeDatabase()
    clerk = FakeClerk(email_address="ada@example.com")
    with _client(database, clerk) as client:
        response = client.post(
            "/v1/organisations/personal",
            json={"idempotency_key": "personal-1"},
            headers=_authorization(),
        )
    assert response.status_code == 200
    assert clerk.created_organisations == [
        {
            "name": "My organisation",
            "created_by": "user_123",
            "idempotency_key": "personal-1",
        }
    ]
    assert clerk.get_user_calls == []


def test_create_personal_organisation_returns_the_existing_owned_organisation() -> None:
    database = FakeDatabase(
        organisations=[
            OrganisationSummary("org_existing", True, _CREATED_AT),
            OrganisationSummary("org_other", False, _CREATED_AT),
        ]
    )
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        response = client.post(
            "/v1/organisations/personal",
            json={"idempotency_key": "personal-1"},
            headers=_authorization(),
        )
    assert response.status_code == 200
    assert response.json() == {"organisation_id": "org_existing"}
    assert clerk.created_organisations == []
    assert clerk.get_user_calls == []


def test_personal_organisation_is_reused_across_apps_and_keys() -> None:
    database = FakeDatabase()
    clerk = FakeClerk()
    with _client(database, clerk) as first, _client(database, clerk) as second:
        first_response = first.post(
            "/v1/organisations/personal",
            json={"idempotency_key": "browser-1"},
            headers=_authorization(),
        )
        second_response = second.post(
            "/v1/organisations/personal",
            json={"idempotency_key": "browser-2"},
            headers=_authorization(),
        )
    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json() == {"organisation_id": "org_created_1"}
    assert second_response.json() == {"organisation_id": "org_created_1"}
    assert len(clerk.created_organisations) == 1
    assert "slug" not in clerk.created_organisations[0]


def test_create_personal_organisation_rejects_a_name() -> None:
    database = FakeDatabase()
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        response = client.post(
            "/v1/organisations/personal",
            json={"name": "Design", "idempotency_key": "personal-1"},
            headers=_authorization(),
        )
    assert response.status_code == 422
    assert clerk.created_organisations == []


@pytest.mark.parametrize("clerk_status", [400, 409, 422, 502])
def test_create_organisation_maps_clerk_errors(clerk_status: int) -> None:
    database = FakeDatabase()
    clerk = FakeClerk(error=ClerkApiError(clerk_status, "refused"))
    with _client(database, clerk) as client:
        response = client.post(
            "/v1/organisations",
            json={"name": "Design", "idempotency_key": "key-1"},
            headers=_authorization(),
        )
    expected = 422 if clerk_status in (400, 409, 422) else 502
    assert response.status_code == expected
    assert response.json()["detail"] == "The organisation could not be created"
    assert database.attempts[("user_123", "key-1")].status == "failed"


def test_invitation_requires_admin_and_active_organisation() -> None:
    database = _database_with_member()
    clerk = FakeClerk()
    with _client(database, clerk, role="member") as client:
        response = client.post(
            "/v1/invitations",
            json={"organisation_id": "org_1", "email_address": "new@example.com"},
            headers=_authorization(),
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "Only an organisation admin can invite"
    assert clerk.created == []

    with _client(database, clerk, organisation_id="org_2") as client:
        response = client.post(
            "/v1/invitations",
            json={"organisation_id": "org_1", "email_address": "new@example.com"},
            headers=_authorization(),
        )
    assert response.status_code == 403
    assert clerk.created == []


def test_removed_admin_cannot_invite() -> None:
    database = FakeDatabase()
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        response = client.post(
            "/v1/invitations",
            json={"organisation_id": "org_1", "email_address": "new@example.com"},
            headers=_authorization(),
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not a member of the active organisation"
    assert clerk.created == []


def test_invitation_uses_backend_redirect_and_inviter_metadata() -> None:
    database = _database_with_member()
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        response = client.post(
            "/v1/invitations",
            json={"organisation_id": "org_1", "email_address": "new@example.com"},
            headers=_authorization(),
        )
    assert response.status_code == 200
    assert response.json() == {"id": "orginv_1", "email_address": "new@example.com"}
    assert clerk.created == [
        {
            "organisation_id": "org_1",
            "email_address": "new@example.com",
            "redirect_url": "http://localhost:5173/invitations",
            "inviter_user_id": "user_123",
            "inviter_name": "Ada Lovelace",
            "inviter_email": "ada@example.com",
        }
    ]


@pytest.mark.parametrize("clerk_status", [400, 422, 502])
def test_invitation_maps_clerk_errors(clerk_status: int) -> None:
    database = _database_with_member()
    clerk = FakeClerk(
        error=ClerkApiError(clerk_status, "refused"),
        error_methods={"create_invitation"},
    )
    with _client(database, clerk) as client:
        response = client.post(
            "/v1/invitations",
            json={"organisation_id": "org_1", "email_address": "new@example.com"},
            headers=_authorization(),
        )
    expected = 422 if clerk_status in (400, 422) else 502
    assert response.status_code == expected


def test_delete_requires_owner_and_another_owned_organisation() -> None:
    database = FakeDatabase(owner=False)
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        response = client.delete("/v1/organisations/org_1", headers=_authorization())
    assert response.status_code == 403
    assert database.owner_calls == [("user_123", "org_1")]
    assert clerk.deleted == []

    database = FakeDatabase(other_owned_organisation=False)
    with _client(database, clerk) as client:
        response = client.delete("/v1/organisations/org_1", headers=_authorization())
    assert response.status_code == 403
    assert database.other_owned_calls == [("user_123", "org_1")]
    assert clerk.deleted == []


def test_delete_calls_clerk_and_database_for_owner_with_another_owned_organisation() -> None:
    database = FakeDatabase()
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        response = client.delete("/v1/organisations/org_1", headers=_authorization())
    assert response.status_code == 204
    assert clerk.deleted == ["org_1"]
    assert database.organisation_deletes == ["org_1"]


def test_admin_cannot_remove_the_owner() -> None:
    database = _database_with_member()
    database.owned_organisations = {"user_owner": {"org_1"}}
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        response = client.delete(
            "/v1/organisations/org_1/members/user_owner",
            headers=_authorization(),
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "The owner cannot be removed from the organisation."
    assert clerk.removed_memberships == []
    assert database.deleted_memberships == []


def test_owner_cannot_leave_the_organisation() -> None:
    database = _database_with_member()
    database.owned_organisations = {"user_123": {"org_1"}}
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        response = client.delete(
            "/v1/organisations/org_1/members/user_123",
            headers=_authorization(),
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "The owner cannot be removed from the organisation."
    assert clerk.removed_memberships == []
    assert database.deleted_memberships == []


def test_removed_admin_cannot_remove_another_member() -> None:
    database = FakeDatabase()
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        response = client.delete(
            "/v1/organisations/org_1/members/user_456",
            headers=_authorization(),
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not a member of the active organisation"
    assert clerk.removed_memberships == []
    assert database.deleted_memberships == []


def test_admin_can_remove_another_member() -> None:
    database = _database_with_member()
    database.owned_organisations = {}
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        response = client.delete(
            "/v1/organisations/org_1/members/user_456",
            headers=_authorization(),
        )
    assert response.status_code == 204
    assert clerk.removed_memberships == [{"organisation_id": "org_1", "member_user_id": "user_456"}]
    assert database.deleted_memberships == [("user_456", "org_1")]


def test_member_cannot_remove_another_member() -> None:
    database = _database_with_member()
    database.owned_organisations = {}
    clerk = FakeClerk()
    with _client(database, clerk, role="member") as client:
        response = client.delete(
            "/v1/organisations/org_1/members/user_456",
            headers=_authorization(),
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "Only an organisation admin can remove a member."
    assert clerk.removed_memberships == []
    assert database.deleted_memberships == []


def test_member_can_leave_the_organisation() -> None:
    database = _database_with_member()
    database.owned_organisations = {}
    clerk = FakeClerk()
    with _client(database, clerk, role="member") as client:
        response = client.delete(
            "/v1/organisations/org_1/members/user_123",
            headers=_authorization(),
        )
    assert response.status_code == 204
    assert clerk.removed_memberships == [{"organisation_id": "org_1", "member_user_id": "user_123"}]
    assert database.deleted_memberships == [("user_123", "org_1")]


def test_member_cannot_leave_their_only_organisation() -> None:
    database = FakeDatabase(another_organisation=False)
    database.owned_organisations = {}
    database.memberships.add(("user_123", "org_1"))
    clerk = FakeClerk()
    with _client(database, clerk, role="member") as client:
        response = client.delete(
            "/v1/organisations/org_1/members/user_123",
            headers=_authorization(),
        )
    assert response.status_code == 403
    assert (
        response.json()["detail"] == "Removing this member would leave them without an organisation"
    )
    assert database.another_organisation_calls == [("user_123", "org_1")]
    assert clerk.removed_memberships == []
    assert database.deleted_memberships == []


def test_admin_cannot_remove_a_member_with_no_other_organisation() -> None:
    database = FakeDatabase(another_organisation=False)
    database.owned_organisations = {}
    database.memberships.add(("user_123", "org_1"))
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        response = client.delete(
            "/v1/organisations/org_1/members/user_456",
            headers=_authorization(),
        )
    assert response.status_code == 403
    assert (
        response.json()["detail"] == "Removing this member would leave them without an organisation"
    )
    assert database.another_organisation_calls == [("user_456", "org_1")]
    assert clerk.removed_memberships == []
    assert database.deleted_memberships == []


def test_non_owner_admin_cannot_change_another_admin_role() -> None:
    database = FakeDatabase(owned_organisations={})
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        response = client.patch(
            "/v1/organisations/org_1/members/user_456",
            json={"role": "org:admin"},
            headers=_authorization(),
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "Only the organisation owner can change a member's role"
    assert clerk.role_changes == []


def test_owner_cannot_change_the_owner_role() -> None:
    database = FakeDatabase(owned_organisations={"user_123": {"org_1"}})
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        response = client.patch(
            "/v1/organisations/org_1/members/user_123",
            json={"role": "org:member"},
            headers=_authorization(),
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "The owner's role cannot be changed"
    assert clerk.role_changes == []


def test_owner_promotes_and_demotes_a_member() -> None:
    database = FakeDatabase(owned_organisations={"user_123": {"org_1"}})
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        promote = client.patch(
            "/v1/organisations/org_1/members/user_456",
            json={"role": "org:admin"},
            headers=_authorization(),
        )
        demote = client.patch(
            "/v1/organisations/org_1/members/user_456",
            json={"role": "org:member"},
            headers=_authorization(),
        )
    assert promote.status_code == 204
    assert demote.status_code == 204
    assert clerk.role_changes == [
        {"organisation_id": "org_1", "member_user_id": "user_456", "role": "org:admin"},
        {"organisation_id": "org_1", "member_user_id": "user_456", "role": "org:member"},
    ]


def test_role_change_rejects_an_unknown_role() -> None:
    database = FakeDatabase(owned_organisations={"user_123": {"org_1"}})
    clerk = FakeClerk()
    with _client(database, clerk) as client:
        response = client.patch(
            "/v1/organisations/org_1/members/user_456",
            json={"role": "org:owner"},
            headers=_authorization(),
        )
    assert response.status_code == 422
    assert clerk.role_changes == []


def test_admin_token_can_invite() -> None:
    database = _database_with_member()
    clerk = FakeClerk()
    with _client(database, clerk, role=ADMIN_ROLE) as client:
        response = client.post(
            "/v1/invitations",
            json={"organisation_id": "org_1", "email_address": "new@example.com"},
            headers=_authorization(),
        )
    assert response.status_code == 200
    assert len(clerk.created) == 1


def test_admin_token_can_promote_and_demote_a_member() -> None:
    database = FakeDatabase(owned_organisations={"user_123": {"org_1"}})
    clerk = FakeClerk()
    with _client(database, clerk, role=ADMIN_ROLE) as client:
        promote = client.patch(
            "/v1/organisations/org_1/members/user_456",
            json={"role": "org:admin"},
            headers=_authorization(),
        )
        demote = client.patch(
            "/v1/organisations/org_1/members/user_456",
            json={"role": "org:member"},
            headers=_authorization(),
        )
    assert promote.status_code == 204
    assert demote.status_code == 204
    assert [change["role"] for change in clerk.role_changes] == ["org:admin", "org:member"]


def test_admin_token_can_remove_another_member() -> None:
    database = _database_with_member()
    database.owned_organisations = {}
    clerk = FakeClerk()
    with _client(database, clerk, role=ADMIN_ROLE) as client:
        response = client.delete(
            "/v1/organisations/org_1/members/user_456",
            headers=_authorization(),
        )
    assert response.status_code == 204
    assert clerk.removed_memberships == [{"organisation_id": "org_1", "member_user_id": "user_456"}]


def test_admin_token_can_delete_organisation_with_another_owned_organisation() -> None:
    database = FakeDatabase(other_owned_organisation=True)
    clerk = FakeClerk()
    with _client(database, clerk, role=ADMIN_ROLE) as client:
        response = client.delete("/v1/organisations/org_1", headers=_authorization())
    assert response.status_code == 204
    assert clerk.deleted == ["org_1"]


def test_member_token_cannot_invite() -> None:
    database = _database_with_member()
    clerk = FakeClerk()
    with _client(database, clerk, role="member") as client:
        response = client.post(
            "/v1/invitations",
            json={"organisation_id": "org_1", "email_address": "new@example.com"},
            headers=_authorization(),
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "Only an organisation admin can invite"
    assert clerk.created == []


def test_member_token_cannot_change_another_member_role() -> None:
    database = FakeDatabase(owned_organisations={"user_123": {"org_1"}})
    clerk = FakeClerk()
    with _client(database, clerk, role="member") as client:
        response = client.patch(
            "/v1/organisations/org_1/members/user_456",
            json={"role": "org:admin"},
            headers=_authorization(),
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "Only the organisation owner can change a member's role"
    assert clerk.role_changes == []


def test_member_token_cannot_remove_another_member() -> None:
    database = _database_with_member()
    database.owned_organisations = {}
    clerk = FakeClerk()
    with _client(database, clerk, role="member") as client:
        response = client.delete(
            "/v1/organisations/org_1/members/user_456",
            headers=_authorization(),
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "Only an organisation admin can remove a member."
    assert clerk.removed_memberships == []


def test_member_token_cannot_delete_organisation() -> None:
    database = FakeDatabase()
    clerk = FakeClerk()
    with _client(database, clerk, role="member") as client:
        response = client.delete("/v1/organisations/org_1", headers=_authorization())
    assert response.status_code == 403
    assert response.json()["detail"] == "Only the organisation owner can delete it"
    assert clerk.deleted == []
