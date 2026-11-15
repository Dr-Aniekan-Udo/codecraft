import logging
from dataclasses import dataclass
from typing import Protocol

import jwt
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    ImmatureSignatureError,
    InvalidAlgorithmError,
    InvalidAudienceError,
    InvalidIssuedAtError,
    InvalidIssuerError,
    InvalidKeyError,
    InvalidSignatureError,
    InvalidSubjectError,
    MissingRequiredClaimError,
    PyJWKClientError,
    PyJWTError,
)
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# Fixed descriptions only. The raw exception text can carry claim values, so it
# is never logged.
_REJECTION_REASONS: tuple[tuple[type[Exception], str], ...] = (
    (ExpiredSignatureError, "signature has expired"),
    (ImmatureSignatureError, "the token is not yet valid"),
    (InvalidSignatureError, "signature verification failed"),
    (InvalidIssuerError, "issuer does not match"),
    (InvalidAudienceError, "audience does not match"),
    (InvalidSubjectError, "subject is invalid"),
    (InvalidAlgorithmError, "the signing algorithm is not allowed"),
    (InvalidIssuedAtError, "the issued-at claim is invalid"),
    (InvalidKeyError, "the signing key is invalid"),
    (MissingRequiredClaimError, "a required claim is missing"),
    (DecodeError, "the token could not be decoded"),
    (PyJWKClientError, "the signing keys could not be loaded"),
    (PyJWTError, "the token failed verification"),
)


def _rejection_reason(error: Exception) -> str:
    for exception_type, reason in _REJECTION_REASONS:
        if isinstance(error, exception_type):
            return reason
    return "the token claims have an unexpected shape"


class InvalidTokenError(Exception):
    """The token could not be trusted."""


class _OrganisationClaims(BaseModel):
    id: str | None = None
    rol: str | None = None


class _TokenClaims(BaseModel):
    sub: str = Field(min_length=1)
    o: _OrganisationClaims | None = None


@dataclass(frozen=True)
class VerifiedToken:
    user_id: str
    organisation_id: str | None
    role: str | None = None


class TokenVerifierLike(Protocol):
    def verify(self, token: str) -> VerifiedToken: ...


class TokenVerifier:
    """Verify Clerk session tokens against Clerk's published signing keys."""

    def __init__(self, issuer: str, *, jwks_client: jwt.PyJWKClient | None = None) -> None:
        # Clerk issues its issuer without a trailing slash. Normalising keeps the
        # JWKS URL and the claimed issuer identical.
        self._issuer = issuer.rstrip("/")
        self._jwks_client = jwks_client or jwt.PyJWKClient(f"{self._issuer}/.well-known/jwks.json")

    def verify(self, token: str) -> VerifiedToken:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                options={
                    "require": ["exp", "iss", "sub"],
                    # Clerk tokens can carry an audience that this API does not
                    # use; membership is decided by the database, not the token.
                    "verify_aud": False,
                },
            )
            parsed = _TokenClaims.model_validate(claims)
        except (PyJWTError, ValidationError) as exc:
            logger.warning(
                "Token rejected: %s: %s",
                type(exc).__name__,
                _rejection_reason(exc),
            )
            raise InvalidTokenError("token verification failed") from exc

        # Clerk v2 puts the active organisation in the standard `o` object.
        # A missing `o` or `o.id` means no active organisation, not a fallback to the
        # legacy v1 `org_id` claim.
        organisation_id = parsed.o.id if parsed.o is not None and parsed.o.id else None
        role = parsed.o.rol if parsed.o is not None and parsed.o.rol else None
        return VerifiedToken(user_id=parsed.sub, organisation_id=organisation_id, role=role)
