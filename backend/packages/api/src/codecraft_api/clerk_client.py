"""The only module that calls Clerk's Backend API.

The browser never sees CLERK_SECRET_KEY. This module exists so the invitation
redirect URL and the owner-only deletion check happen on the server, not in
client code that a signed-in admin can bypass.

Clerk's API uses the US spelling 'organization'; the application's domain term
is 'organisation'.
"""

import logging
import re
import time
from dataclasses import dataclass
from typing import Protocol, cast

import httpx
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

_CLERK_API_BASE_URL = "https://api.clerk.com/v1"
_TIMEOUT_SECONDS = 10.0

_CLERK_ID_PATTERN = re.compile(r"\b(?:user|org|orginv|role|sess)_[A-Za-z0-9]+\b")
_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+")


def _safe_clerk_text(value: object) -> str:
    if not isinstance(value, str):
        return "unknown"
    return _CLERK_ID_PATTERN.sub("[id]", _EMAIL_PATTERN.sub("[email]", value))


def _safe_clerk_path(path: str) -> str:
    return _CLERK_ID_PATTERN.sub("[id]", path)


def _created_at_milliseconds(value: int) -> int:
    """Clerk normally returns milliseconds, but accept seconds for safety."""
    return value if value > 10_000_000_000 else value * 1000


def _clerk_error_fields(response: httpx.Response) -> tuple[str, str]:
    try:
        body = cast("object", response.json())
    except ValueError:
        return "unknown", "unknown"
    if not isinstance(body, dict):
        return "unknown", "unknown"
    body_map = cast("dict[str, object]", body)
    errors = body_map.get("errors")
    if not isinstance(errors, list) or not errors:
        return "unknown", "unknown"
    error = cast("list[object]", errors)[0]
    if not isinstance(error, dict):
        return "unknown", "unknown"
    error_map = cast("dict[str, object]", error)
    return _safe_clerk_text(error_map.get("code")), _safe_clerk_text(error_map.get("message"))


class ClerkApiError(Exception):
    """Clerk refused the request or could not be reached."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ClerkInvitation:
    id: str
    email_address: str


@dataclass(frozen=True)
class ClerkUser:
    name: str
    email_address: str


@dataclass(frozen=True)
class ClerkOrganisation:
    id: str
    name: str
    created_at: int | None = None


class ClerkClientLike(Protocol):
    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def get_user(self, user_id: str) -> ClerkUser: ...

    async def create_invitation(
        self,
        *,
        organisation_id: str,
        email_address: str,
        redirect_url: str,
        inviter_user_id: str,
        inviter_name: str,
        inviter_email: str,
    ) -> ClerkInvitation: ...

    async def delete_organisation(self, organisation_id: str) -> None: ...

    async def create_organisation(
        self,
        *,
        name: str,
        created_by: str,
        idempotency_key: str,
    ) -> ClerkOrganisation: ...

    async def find_organisation_by_idempotency_key(
        self,
        *,
        user_id: str,
        idempotency_key: str,
    ) -> ClerkOrganisation | None: ...

    async def find_recent_organisation_by_name(
        self,
        *,
        user_id: str,
        name: str,
    ) -> ClerkOrganisation | None: ...

    async def update_organisation_membership_role(
        self,
        *,
        organisation_id: str,
        member_user_id: str,
        role: str,
    ) -> None: ...

    async def delete_organisation_membership(
        self,
        *,
        organisation_id: str,
        member_user_id: str,
    ) -> None: ...


class _ClerkEmailAddress(BaseModel):
    id: str
    email_address: str


class _ClerkUserPayload(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    primary_email_address_id: str | None = None
    email_addresses: list[_ClerkEmailAddress] = []


class _ClerkInvitationPayload(BaseModel):
    id: str = Field(min_length=1)
    email_address: str | None = None


class _ClerkOrganisationPayload(BaseModel):
    id: str = Field(min_length=1)
    name: str = ""
    created_by: str | None = None
    created_at: int | None = None
    private_metadata: dict[str, object] = {}


class _ClerkOrganisationListPayload(BaseModel):
    data: list[_ClerkOrganisationPayload] = []
    total_count: int = 0


def _organisation_from_payload(payload: _ClerkOrganisationPayload) -> ClerkOrganisation:
    return ClerkOrganisation(
        id=payload.id,
        name=payload.name,
        created_at=payload.created_at,
    )


def _name_from_user(payload: _ClerkUserPayload) -> str:
    parts = [
        part.strip()
        for part in (payload.first_name, payload.last_name)
        if part is not None and part.strip()
    ]
    if parts:
        return " ".join(parts)
    if payload.username is not None and payload.username.strip():
        return payload.username.strip()
    return ""


def _email_from_user(payload: _ClerkUserPayload) -> str:
    for address in payload.email_addresses:
        if address.id == payload.primary_email_address_id:
            return address.email_address
    if payload.email_addresses:
        return payload.email_addresses[0].email_address
    return ""


class ClerkClient:
    def __init__(self, secret_key: str) -> None:
        self._secret_key = secret_key
        self._client: httpx.AsyncClient | None = None

    async def open(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=_CLERK_API_BASE_URL,
                headers={
                    "Authorization": f"Bearer {self._secret_key}",
                    "Clerk-API-Version": "2026-08-20",
                },
                timeout=_TIMEOUT_SECONDS,
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("the Clerk client has not been opened")
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        json: dict[str, object] | None = None,
        allow_not_found: bool = False,
    ) -> httpx.Response:
        try:
            response = await self._require_client().request(
                method,
                path,
                params=params,
                json=json,
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "Clerk request failed: method=%s path=%s transport=%s",
                method,
                _safe_clerk_path(path),
                type(exc).__name__,
            )
            raise ClerkApiError(502, "the identity service could not be reached") from exc

        if allow_not_found and response.status_code == 404:
            return response
        if response.status_code >= 400:
            code, message = _clerk_error_fields(response)
            logger.warning(
                "Clerk request failed: method=%s path=%s status=%s code=%s message=%s",
                method,
                _safe_clerk_path(path),
                response.status_code,
                code,
                message,
            )
            raise ClerkApiError(response.status_code, "the identity service refused the request")
        return response

    async def get_user(self, user_id: str) -> ClerkUser:
        response = await self._request("GET", f"/users/{user_id}")
        try:
            payload = _ClerkUserPayload.model_validate(response.json())
        except ValidationError as exc:
            raise ClerkApiError(502, "the identity service returned an unexpected user") from exc
        return ClerkUser(
            name=_name_from_user(payload),
            email_address=_email_from_user(payload),
        )

    async def create_invitation(
        self,
        *,
        organisation_id: str,
        email_address: str,
        redirect_url: str,
        inviter_user_id: str,
        inviter_name: str,
        inviter_email: str,
    ) -> ClerkInvitation:
        response = await self._request(
            "POST",
            f"/organizations/{organisation_id}/invitations",
            json={
                "email_address": email_address,
                "role": "org:member",
                "inviter_user_id": inviter_user_id,
                "redirect_url": redirect_url,
                "public_metadata": {
                    "inviter_name": inviter_name,
                    "inviter_email": inviter_email,
                },
            },
        )
        try:
            payload = _ClerkInvitationPayload.model_validate(response.json())
        except ValidationError as exc:
            raise ClerkApiError(
                502, "the identity service returned an unexpected invitation"
            ) from exc
        return ClerkInvitation(
            id=payload.id,
            email_address=payload.email_address or email_address,
        )

    async def delete_organisation(self, organisation_id: str) -> None:
        # Deleting an organisation that is already gone is a successful retry.
        await self._request("DELETE", f"/organizations/{organisation_id}", allow_not_found=True)

    async def create_organisation(
        self,
        *,
        name: str,
        created_by: str,
        idempotency_key: str,
    ) -> ClerkOrganisation:
        response = await self._request(
            "POST",
            "/organizations",
            json={
                "name": name,
                "created_by": created_by,
                "private_metadata": {"codecraft_idempotency_key": idempotency_key},
            },
        )
        try:
            payload = _ClerkOrganisationPayload.model_validate(response.json())
        except ValidationError as exc:
            logger.warning(
                "Clerk response validation failed: method=POST path=/organizations errors=%s",
                exc.errors(include_input=False),
            )
            raise ClerkApiError(
                502, "the identity service returned an unexpected organisation"
            ) from exc
        return _organisation_from_payload(payload)

    async def find_organisation_by_idempotency_key(
        self,
        *,
        user_id: str,
        idempotency_key: str,
    ) -> ClerkOrganisation | None:
        offset = 0
        limit = 100
        while True:
            response = await self._request(
                "GET",
                "/organizations",
                params={
                    "user_id": user_id,
                    "limit": limit,
                    "offset": offset,
                },
            )
            try:
                payload = _ClerkOrganisationListPayload.model_validate(response.json())
            except ValidationError as exc:
                logger.warning(
                    "Clerk response validation failed: method=GET path=/organizations errors=%s",
                    exc.errors(include_input=False),
                )
                raise ClerkApiError(
                    502, "the identity service returned an unexpected organisation list"
                ) from exc

            for organisation in payload.data:
                stored_key = organisation.private_metadata.get("codecraft_idempotency_key")
                if organisation.created_by == user_id and stored_key == idempotency_key:
                    return _organisation_from_payload(organisation)

            offset += limit
            if not payload.data or offset >= payload.total_count:
                return None

    async def find_recent_organisation_by_name(
        self,
        *,
        user_id: str,
        name: str,
    ) -> ClerkOrganisation | None:
        now = int(time.time() * 1000)
        offset = 0
        limit = 100
        while True:
            response = await self._request(
                "GET",
                "/organizations",
                params={
                    "user_id": user_id,
                    "limit": limit,
                    "offset": offset,
                },
            )
            try:
                payload = _ClerkOrganisationListPayload.model_validate(response.json())
            except ValidationError as exc:
                logger.warning(
                    "Clerk response validation failed: method=GET path=/organizations errors=%s",
                    exc.errors(include_input=False),
                )
                raise ClerkApiError(
                    502, "the identity service returned an unexpected organisation list"
                ) from exc

            for organisation in payload.data:
                if (
                    organisation.created_by == user_id
                    and organisation.name == name
                    and organisation.created_at is not None
                    and now - _created_at_milliseconds(organisation.created_at) <= 10_000
                ):
                    return _organisation_from_payload(organisation)

            offset += limit
            if not payload.data or offset >= payload.total_count:
                return None

    async def update_organisation_membership_role(
        self,
        *,
        organisation_id: str,
        member_user_id: str,
        role: str,
    ) -> None:
        await self._request(
            "PATCH",
            f"/organizations/{organisation_id}/memberships/{member_user_id}",
            json={"role": role},
        )

    async def delete_organisation_membership(
        self,
        *,
        organisation_id: str,
        member_user_id: str,
    ) -> None:
        # A membership that is already gone is a successful retry.
        await self._request(
            "DELETE",
            f"/organizations/{organisation_id}/memberships/{member_user_id}",
            allow_not_found=True,
        )
