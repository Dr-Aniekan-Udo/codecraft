from codecraft_settings import Settings as BaseSettings
from pydantic import ValidationInfo, field_validator


class Settings(BaseSettings):
    """The API's credentials and origin, on top of the base settings."""

    # Empty defaults exist only so the validator can name every missing value.
    # Validation runs on defaults, so a truly missing value still fails startup.
    DATABASE_URL: str = ""
    MEMBERSHIP_SYNC_DATABASE_URL: str = ""
    CLERK_JWT_ISSUER: str = ""
    CLERK_WEBHOOK_SIGNING_SECRET: str = ""
    CLERK_SECRET_KEY: str = ""
    CODECRAFT_FRONTEND_ORIGIN: str = "http://localhost:5173"

    @field_validator(
        "DATABASE_URL",
        "MEMBERSHIP_SYNC_DATABASE_URL",
        "CLERK_JWT_ISSUER",
        "CLERK_WEBHOOK_SIGNING_SECRET",
        "CLERK_SECRET_KEY",
        "CODECRAFT_FRONTEND_ORIGIN",
    )
    @classmethod
    def _must_not_be_blank(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return value
