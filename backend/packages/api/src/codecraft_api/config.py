from pathlib import Path

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchored to this file, not the working directory: the API reads backend/.env
# whether it is started from the backend root or anywhere else.
_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    """Required configuration is required: no silent fallback for missing values."""

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        validate_default=True,
        extra="ignore",
    )

    # Empty defaults exist only so the validator can name every missing value.
    # Validation runs on defaults, so a truly missing value still fails startup.
    DATABASE_URL: str = ""
    MEMBERSHIP_SYNC_DATABASE_URL: str = ""
    CLERK_JWT_ISSUER: str = ""
    CLERK_WEBHOOK_SIGNING_SECRET: str = ""
    CLERK_SECRET_KEY: str = ""
    CODECRAFT_FRONTEND_ORIGIN: str = "http://localhost:5173"

    # Zero is the sentinel for a missing integer limit: it can never be valid,
    # and validation runs on defaults, so the error names the field.
    PARSE_MAX_FILES: int = Field(default=0, ge=1)
    PARSE_MAX_FILE_BYTES: int = Field(default=0, ge=1)

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
