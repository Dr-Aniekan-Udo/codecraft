from dataclasses import dataclass
from typing import Protocol

import jwt
from jwt.exceptions import PyJWTError
from pydantic import BaseModel, Field, ValidationError


class InvalidTokenError(Exception):
    """The token could not be trusted."""


class _OrganizationClaims(BaseModel):
    id: str | None = None


class _TokenClaims(BaseModel):
    sub: str = Field(min_length=1)
    o: _OrganizationClaims | None = None


@dataclass(frozen=True)
class VerifiedToken:
    user_id: str
    team_id: str | None


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
            raise InvalidTokenError("token verification failed") from exc

        # Clerk v2 puts the active organization in the standard `o` object.
        # A missing `o` or `o.id` means no active team, not a fallback to the
        # legacy v1 `org_id` claim.
        team_id = parsed.o.id if parsed.o is not None and parsed.o.id else None
        return VerifiedToken(user_id=parsed.sub, team_id=team_id)
