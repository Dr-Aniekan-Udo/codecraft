"""The base configuration every backend process shares."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchored to this file, not the working directory: the command reads
# backend/.env whether it is started from the backend folder or anywhere else.
_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    """The parse limits and the one environment file location."""

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        validate_default=True,
        extra="ignore",
    )

    # Zero is the sentinel for a missing integer limit: it can never be valid,
    # and validation runs on defaults, so the error names the field.
    PARSE_MAX_FILES: int = Field(default=0, ge=1)
    PARSE_MAX_FILE_BYTES: int = Field(default=0, ge=1)
