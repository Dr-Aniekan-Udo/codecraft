from datetime import datetime
from uuid import UUID

from codecraft_storage import DatabaseLike
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from codecraft_api.config import Settings
from codecraft_api.token_verifier import (
    InvalidTokenError,
    TokenVerifierLike,
    VerifiedToken,
)
from codecraft_api.webhook import WebhookVerificationError, verify_webhook_signature

_MEMBERSHIP_CREATED = "organizationMembership.created"
_MEMBERSHIP_DELETED = "organizationMembership.deleted"
_TEAM_DELETED = "organization.deleted"


class MeResponse(BaseModel):
    user_id: str
    team_id: str


class AnalysisResponse(BaseModel):
    id: UUID
    project_name: str
    state: str
    created_at: datetime
    is_sample: bool


class AnalysesResponse(BaseModel):
    analyses: list[AnalysisResponse]


class _EventEnvelope(BaseModel):
    type: str


class _TeamData(BaseModel):
    id: str = Field(min_length=1)


class _TeamDeletedEvent(BaseModel):
    type: str
    data: _TeamData


class _Organization(BaseModel):
    id: str


class _PublicUserData(BaseModel):
    user_id: str


class _MembershipData(BaseModel):
    organization: _Organization
    public_user_data: _PublicUserData


class _MembershipEvent(BaseModel):
    type: str
    data: _MembershipData


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization")
    if authorization is None:
        raise _unauthorized()
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise _unauthorized()
    return token.strip()


async def _verified_token(request: Request, verifier: TokenVerifierLike) -> VerifiedToken:
    token = _bearer_token(request)
    try:
        # PyJWKClient may fetch the JWKS synchronously on a cache miss. Keep that
        # work off the event loop so one token check cannot stall other requests.
        return await run_in_threadpool(verifier.verify, token)
    except InvalidTokenError:
        raise _unauthorized() from None


def create_router(
    settings: Settings,
    database: DatabaseLike,
    verifier: TokenVerifierLike,
) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/me", response_model=MeResponse)
    async def me(request: Request) -> MeResponse:
        token = await _verified_token(request, verifier)
        if token.team_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No active team",
            )
        if not await database.is_member(token.user_id, token.team_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of the active team",
            )
        return MeResponse(user_id=token.user_id, team_id=token.team_id)

    @router.get("/v1/analyses", response_model=AnalysesResponse)
    async def list_analyses(
        request: Request,
        team_id: str = Query(min_length=1),
    ) -> AnalysesResponse:
        token = await _verified_token(request, verifier)
        # The token's active team is not consulted: the person may switch teams,
        # and the database policy decides which rows the query can return.
        summaries = await database.list_analyses(token.user_id, team_id)
        return AnalysesResponse(
            analyses=[
                AnalysisResponse(
                    id=summary.id,
                    project_name=summary.project_name,
                    state=summary.state,
                    created_at=summary.created_at,
                    is_sample=summary.is_sample,
                )
                for summary in summaries
            ]
        )

    @router.post(
        "/webhooks/clerk",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def clerk_webhook(request: Request) -> Response:
        svix_id = request.headers.get("svix-id")
        svix_timestamp = request.headers.get("svix-timestamp")
        svix_signature = request.headers.get("svix-signature")
        if svix_id is None or svix_timestamp is None or svix_signature is None:
            raise _unauthorized()

        body = await request.body()
        try:
            verify_webhook_signature(
                settings.CLERK_WEBHOOK_SIGNING_SECRET,
                svix_id,
                svix_timestamp,
                svix_signature,
                body,
            )
        except WebhookVerificationError:
            raise _unauthorized() from None

        # Parsing happens only after the signature proved the body came from Clerk.
        try:
            envelope = _EventEnvelope.model_validate_json(body)
        except ValidationError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook payload",
            ) from None

        if envelope.type == _TEAM_DELETED:
            try:
                team_event = _TeamDeletedEvent.model_validate_json(body)
            except ValidationError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid webhook payload",
                ) from None

            await database.delete_team(team_event.data.id)
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        if envelope.type not in (_MEMBERSHIP_CREATED, _MEMBERSHIP_DELETED):
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        try:
            event = _MembershipEvent.model_validate_json(body)
        except ValidationError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook payload",
            ) from None

        user_id = event.data.public_user_data.user_id
        team_id = event.data.organization.id
        if event.type == _MEMBERSHIP_CREATED:
            await database.upsert_membership(user_id, team_id)
        else:
            await database.delete_membership(user_id, team_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
