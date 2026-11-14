import asyncio
from datetime import datetime
from typing import Literal
from uuid import UUID

from codecraft_storage import DatabaseLike
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.concurrency import run_in_threadpool

from codecraft_api.clerk_client import ClerkApiError, ClerkClientLike, ClerkOrganisation
from codecraft_api.config import Settings
from codecraft_api.organisation_names import personal_organisation_name
from codecraft_api.token_verifier import (
    InvalidTokenError,
    TokenVerifierLike,
    VerifiedToken,
)
from codecraft_api.webhook import WebhookVerificationError, verify_webhook_signature

_MEMBERSHIP_CREATED = "organizationMembership.created"
_MEMBERSHIP_DELETED = "organizationMembership.deleted"
_ORGANISATION_CREATED = "organization.created"
_ORGANISATION_DELETED = "organization.deleted"

# The role Clerk puts in the session token's `o.rol` claim. Clerk's own API
# uses the `org:admin` / `org:member` form; only the token short form is checked
# here.
ADMIN_ROLE = "admin"


class MeResponse(BaseModel):
    user_id: str
    organisation_id: str
    role: str | None


class AnalysisResponse(BaseModel):
    id: UUID
    project_name: str
    state: str
    created_at: datetime
    is_sample: bool


class AnalysesResponse(BaseModel):
    analyses: list[AnalysisResponse]


class ProjectSummaryResponse(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    is_sample: bool
    latest_analysis_state: str | None
    latest_analysis_created_at: datetime | None


class ProjectsResponse(BaseModel):
    projects: list[ProjectSummaryResponse]


class ProjectRecordResponse(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    is_sample: bool


class ProjectAnalysisResponse(BaseModel):
    id: UUID
    state: str
    created_at: datetime
    is_sample: bool


class ProjectDetailResponse(BaseModel):
    project: ProjectRecordResponse
    analyses: list[ProjectAnalysisResponse]


class AnalysisDetailBody(BaseModel):
    id: UUID
    project_id: UUID
    project_name: str
    state: str
    created_at: datetime
    is_sample: bool


class AnalysisDetailResponse(BaseModel):
    analysis: AnalysisDetailBody


class OrganisationResponse(BaseModel):
    organisation_id: str
    is_owner: bool
    created_at: datetime


class OrganisationsResponse(BaseModel):
    organisations: list[OrganisationResponse]


class _IdempotencyRequest(BaseModel):
    idempotency_key: str

    @field_validator("idempotency_key")
    @classmethod
    def _trim_idempotency_key(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("idempotency_key must not be blank")
        if len(trimmed) > 200:
            raise ValueError("idempotency_key must be at most 200 characters")
        return trimmed


class OrganisationCreationRequest(_IdempotencyRequest):
    name: str

    @field_validator("name")
    @classmethod
    def _trim_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("name must not be blank")
        if len(trimmed) > 256:
            raise ValueError("name must be at most 256 characters")
        return trimmed


class PersonalOrganisationCreationRequest(_IdempotencyRequest):
    model_config = ConfigDict(extra="forbid")


class OrganisationCreationResponse(BaseModel):
    organisation_id: str


class OrganisationMemberRoleRequest(BaseModel):
    role: Literal["org:admin", "org:member"]


class InvitationRequest(BaseModel):
    organisation_id: str = Field(min_length=1)
    email_address: str = Field(min_length=3, max_length=254)


class InvitationResponse(BaseModel):
    id: str
    email_address: str


class _EventEnvelope(BaseModel):
    type: str


class _OrganisationData(BaseModel):
    id: str = Field(min_length=1)


class _OrganisationCreatedData(BaseModel):
    id: str = Field(min_length=1)
    created_by: str | None = None


class _OrganisationCreatedEvent(BaseModel):
    type: str
    data: _OrganisationCreatedData


class _OrganisationDeletedEvent(BaseModel):
    type: str
    data: _OrganisationData


class _Organisation(BaseModel):
    id: str


class _PublicUserData(BaseModel):
    user_id: str


class _MembershipData(BaseModel):
    organization: _Organisation
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


def _not_found() -> HTTPException:
    # A hidden row and a row that does not exist must be indistinguishable, so
    # every missing or malformed identifier returns this exact response.
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _parse_identifier(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise _not_found() from None


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
    clerk: ClerkClientLike,
) -> APIRouter:
    router = APIRouter()
    # One lock per app: a double press or two tabs with the same key must not
    # both reach Clerk's create endpoint, because Clerk cannot enforce our
    # idempotency key atomically for us.
    creation_lock = asyncio.Lock()

    @router.get("/v1/me", response_model=MeResponse)
    async def me(request: Request) -> MeResponse:
        token = await _verified_token(request, verifier)
        if token.organisation_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No active organisation",
            )
        if not await database.is_member(token.user_id, token.organisation_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of the active organisation",
            )
        return MeResponse(
            user_id=token.user_id,
            organisation_id=token.organisation_id,
            role=token.role,
        )

    @router.get("/v1/organisations", response_model=OrganisationsResponse)
    async def list_organisations(request: Request) -> OrganisationsResponse:
        token = await _verified_token(request, verifier)
        summaries = await database.list_organisations(token.user_id)
        return OrganisationsResponse(
            organisations=[
                OrganisationResponse(
                    organisation_id=summary.organisation_id,
                    is_owner=summary.is_owner,
                    created_at=summary.created_at,
                )
                for summary in summaries
            ]
        )

    async def _create_or_reuse_organisation(
        *,
        user_id: str,
        name: str,
        idempotency_key: str,
    ) -> ClerkOrganisation:
        existing = await clerk.find_organisation_by_idempotency_key(
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            # The first attempt may have created the organisation and then failed
            # before writing the local row. The owner write is idempotent, so
            # repair it before returning the same organisation.
            await database.set_owner(user_id, existing.id)
            return existing

        # A second browser can use a different idempotency key for the same
        # attempt. Reuse an organisation with the same name created in the last
        # 10 seconds instead of creating another one.
        recent = await clerk.find_recent_organisation_by_name(user_id=user_id, name=name)
        if recent is not None:
            await database.set_owner(user_id, recent.id)
            return recent

        try:
            organisation = await clerk.create_organisation(
                name=name,
                created_by=user_id,
                idempotency_key=idempotency_key,
            )
        except ClerkApiError as exc:
            # Another API process may have created the organisation between our
            # lookup and this call. The idempotency key is the tie-breaker.
            if exc.status_code == 409:
                raced = await clerk.find_organisation_by_idempotency_key(
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                )
                if raced is not None:
                    await database.set_owner(user_id, raced.id)
                    return raced
            raise

        # The signed webhook will write the same row later. Writing it here too
        # makes the new organisation visible to the next request. Both writes are
        # idempotent.
        await database.set_owner(user_id, organisation.id)
        return organisation

    def _creation_failure(exc: ClerkApiError) -> HTTPException:
        status_code = (
            status.HTTP_422_UNPROCESSABLE_CONTENT
            if exc.status_code in (400, 409, 422)
            else status.HTTP_502_BAD_GATEWAY
        )
        return HTTPException(
            status_code=status_code,
            detail="The organisation could not be created",
        )

    @router.post("/v1/organisations", response_model=OrganisationCreationResponse)
    async def create_organisation(
        request: Request, body: OrganisationCreationRequest
    ) -> OrganisationCreationResponse:
        token = await _verified_token(request, verifier)
        async with creation_lock:
            try:
                organisation = await _create_or_reuse_organisation(
                    user_id=token.user_id,
                    name=body.name,
                    idempotency_key=body.idempotency_key,
                )
            except ClerkApiError as exc:
                raise _creation_failure(exc) from None
        return OrganisationCreationResponse(organisation_id=organisation.id)

    @router.post("/v1/organisations/personal", response_model=OrganisationCreationResponse)
    async def create_personal_organisation(
        request: Request,
        body: PersonalOrganisationCreationRequest,
    ) -> OrganisationCreationResponse:
        token = await _verified_token(request, verifier)
        async with creation_lock:
            try:
                summaries = await database.list_organisations(token.user_id)
                owned = next(
                    (summary for summary in summaries if summary.is_owner),
                    None,
                )
                if owned is not None:
                    return OrganisationCreationResponse(organisation_id=owned.organisation_id)

                organisation = await _create_or_reuse_organisation(
                    user_id=token.user_id,
                    name=personal_organisation_name(),
                    idempotency_key=body.idempotency_key,
                )
            except ClerkApiError as exc:
                raise _creation_failure(exc) from None
        return OrganisationCreationResponse(organisation_id=organisation.id)

    @router.patch(
        "/v1/organisations/{organisation_id}/members/{member_user_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def update_organisation_member_role(
        request: Request,
        organisation_id: str,
        member_user_id: str,
        body: OrganisationMemberRoleRequest,
    ) -> Response:
        token = await _verified_token(request, verifier)
        if token.organisation_id is None or token.organisation_id != organisation_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The role must be changed for the active organisation",
            )
        if token.role != ADMIN_ROLE or not await database.is_owner(token.user_id, organisation_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the organisation owner can change a member's role",
            )
        if await database.is_owner(member_user_id, organisation_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The owner's role cannot be changed",
            )

        try:
            await clerk.update_organisation_membership_role(
                organisation_id=organisation_id,
                member_user_id=member_user_id,
                role=body.role,
            )
        except ClerkApiError as exc:
            status_code = (
                status.HTTP_422_UNPROCESSABLE_CONTENT
                if exc.status_code in (400, 404, 409, 422)
                else status.HTTP_502_BAD_GATEWAY
            )
            raise HTTPException(
                status_code=status_code,
                detail="The member's role could not be changed",
            ) from None
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.delete(
        "/v1/organisations/{organisation_id}/members/{member_user_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def remove_organisation_member(
        request: Request,
        organisation_id: str,
        member_user_id: str,
    ) -> Response:
        token = await _verified_token(request, verifier)
        if token.organisation_id is None or token.organisation_id != organisation_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The member must be removed from the active organisation",
            )
        if not await database.is_member(token.user_id, organisation_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of the active organisation",
            )
        # The owner check is the first authority check and always applies,
        # including when the owner is trying to remove themselves.
        if await database.is_owner(member_user_id, organisation_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The owner cannot be removed from the organisation.",
            )
        if member_user_id != token.user_id and token.role != ADMIN_ROLE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only an organisation admin can remove a member.",
            )
        if not await database.has_other_organisation(member_user_id, organisation_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Removing this member would leave them without an organisation",
            )

        try:
            await clerk.delete_organisation_membership(
                organisation_id=organisation_id,
                member_user_id=member_user_id,
            )
        except ClerkApiError as exc:
            status_code = (
                status.HTTP_422_UNPROCESSABLE_CONTENT
                if exc.status_code in (400, 409, 422)
                else status.HTTP_502_BAD_GATEWAY
            )
            raise HTTPException(
                status_code=status_code,
                detail="The member could not be removed",
            ) from None
        # Remove the local row immediately so the next request is refused;
        # the webhook's delete is idempotent and may arrive later.
        await database.delete_membership(member_user_id, organisation_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/v1/invitations", response_model=InvitationResponse)
    async def invite(request: Request, body: InvitationRequest) -> InvitationResponse:
        token = await _verified_token(request, verifier)
        if token.organisation_id is None or token.organisation_id != body.organisation_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The invitation must be for the active organisation",
            )
        if not await database.is_member(token.user_id, body.organisation_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of the active organisation",
            )
        if token.role != ADMIN_ROLE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only an organisation admin can invite",
            )

        try:
            inviter = await clerk.get_user(token.user_id)
            invitation = await clerk.create_invitation(
                organisation_id=body.organisation_id,
                email_address=body.email_address,
                redirect_url=f"{settings.CODECRAFT_FRONTEND_ORIGIN.rstrip('/')}/invitations",
                inviter_user_id=token.user_id,
                inviter_name=inviter.name,
                inviter_email=inviter.email_address,
            )
        except ClerkApiError as exc:
            status_code = (
                status.HTTP_422_UNPROCESSABLE_CONTENT
                if exc.status_code in (400, 409, 422)
                else status.HTTP_502_BAD_GATEWAY
            )
            raise HTTPException(
                status_code=status_code,
                detail="The invitation could not be sent",
            ) from None

        return InvitationResponse(
            id=invitation.id,
            email_address=invitation.email_address,
        )

    @router.delete("/v1/organisations/{organisation_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_organisation(request: Request, organisation_id: str) -> Response:
        token = await _verified_token(request, verifier)
        if token.organisation_id is None or token.organisation_id != organisation_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the active organisation can be deleted",
            )
        if token.role != ADMIN_ROLE or not await database.is_owner(token.user_id, organisation_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the organisation owner can delete it",
            )
        if not await database.has_other_owned_organisation(token.user_id, organisation_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Deleting this organisation would leave you without an organisation you own",
            )

        try:
            await clerk.delete_organisation(organisation_id)
        except ClerkApiError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The organisation could not be deleted",
            ) from None
        # The endpoint's contract is that the data is gone when it returns. The
        # webhook remains a retry path; its delete is idempotent.
        await database.delete_organisation(organisation_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/v1/analyses", response_model=AnalysesResponse)
    async def list_analyses(
        request: Request,
        organisation_id: str = Query(min_length=1),
    ) -> AnalysesResponse:
        token = await _verified_token(request, verifier)
        # The token's active organisation is not consulted: the person may switch organisations,
        # and the database policy decides which rows the query can return.
        summaries = await database.list_analyses(token.user_id, organisation_id)
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

    @router.get("/v1/projects", response_model=ProjectsResponse)
    async def list_projects(
        request: Request,
        organisation_id: str = Query(min_length=1),
    ) -> ProjectsResponse:
        token = await _verified_token(request, verifier)
        # The database policy decides which projects the person can see; an empty
        # result is a valid organisation with no projects.
        summaries = await database.list_projects(token.user_id, organisation_id)
        return ProjectsResponse(
            projects=[
                ProjectSummaryResponse(
                    id=summary.id,
                    name=summary.name,
                    created_at=summary.created_at,
                    is_sample=summary.is_sample,
                    latest_analysis_state=summary.latest_analysis_state,
                    latest_analysis_created_at=summary.latest_analysis_created_at,
                )
                for summary in summaries
            ]
        )

    @router.get("/v1/projects/{project_id}", response_model=ProjectDetailResponse)
    async def get_project(request: Request, project_id: str) -> ProjectDetailResponse:
        token = await _verified_token(request, verifier)
        detail = await database.get_project(token.user_id, _parse_identifier(project_id))
        if detail is None:
            raise _not_found()
        return ProjectDetailResponse(
            project=ProjectRecordResponse(
                id=detail.project.id,
                name=detail.project.name,
                created_at=detail.project.created_at,
                is_sample=detail.project.is_sample,
            ),
            analyses=[
                ProjectAnalysisResponse(
                    id=analysis.id,
                    state=analysis.state,
                    created_at=analysis.created_at,
                    is_sample=analysis.is_sample,
                )
                for analysis in detail.analyses
            ],
        )

    @router.get("/v1/analyses/{analysis_id}", response_model=AnalysisDetailResponse)
    async def get_analysis(request: Request, analysis_id: str) -> AnalysisDetailResponse:
        token = await _verified_token(request, verifier)
        detail = await database.get_analysis(token.user_id, _parse_identifier(analysis_id))
        if detail is None:
            raise _not_found()
        return AnalysisDetailResponse(
            analysis=AnalysisDetailBody(
                id=detail.id,
                project_id=detail.project_id,
                project_name=detail.project_name,
                state=detail.state,
                created_at=detail.created_at,
                is_sample=detail.is_sample,
            )
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

        if envelope.type == _ORGANISATION_CREATED:
            try:
                created_event = _OrganisationCreatedEvent.model_validate_json(body)
            except ValidationError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid webhook payload",
                ) from None

            owner = created_event.data.created_by
            if owner is not None and owner.strip():
                await database.set_owner(owner.strip(), created_event.data.id)
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        if envelope.type == _ORGANISATION_DELETED:
            try:
                organisation_event = _OrganisationDeletedEvent.model_validate_json(body)
            except ValidationError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid webhook payload",
                ) from None

            await database.delete_organisation(organisation_event.data.id)
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
        organisation_id = event.data.organization.id
        if event.type == _MEMBERSHIP_CREATED:
            await database.upsert_membership(user_id, organisation_id)
        else:
            await database.delete_membership(user_id, organisation_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
