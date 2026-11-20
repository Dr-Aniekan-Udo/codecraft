from pathlib import Path

import pytest
from codecraft_api.config import Settings
from pydantic import ValidationError
from pydantic_settings import SettingsConfigDict


class SettingsWithoutEnvFile(Settings):
    """Test the validators without reading a developer's real .env file."""

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=None,
        validate_default=True,
        extra="ignore",
    )


_REQUIRED = {
    "DATABASE_URL": "postgresql://api@example/db",
    "MEMBERSHIP_SYNC_DATABASE_URL": "postgresql://sync@example/db",
    "CLERK_JWT_ISSUER": "https://clerk.example",
    "CLERK_WEBHOOK_SIGNING_SECRET": "whsec_c2VjcmV0",
    "CLERK_SECRET_KEY": "sk_test_secret",
    "PARSE_MAX_FILES": "50000",
    "PARSE_MAX_FILE_BYTES": "2000000",
}


@pytest.fixture
def required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in _REQUIRED.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("CODECRAFT_FRONTEND_ORIGIN", "http://localhost:5173")


@pytest.mark.usefixtures("required_env")
@pytest.mark.parametrize("name", sorted(_REQUIRED))
def test_missing_required_value_names_it(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.delenv(name)
    with pytest.raises(ValidationError, match=name):
        SettingsWithoutEnvFile()


@pytest.mark.usefixtures("required_env")
@pytest.mark.parametrize("name", sorted(_REQUIRED))
def test_blank_required_value_names_it(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setenv(name, "   ")
    with pytest.raises(ValidationError, match=name):
        SettingsWithoutEnvFile()


@pytest.mark.usefixtures("required_env")
@pytest.mark.parametrize("name", ["PARSE_MAX_FILES", "PARSE_MAX_FILE_BYTES"])
def test_a_non_integer_parse_limit_names_it(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setenv(name, "not-a-number")
    with pytest.raises(ValidationError, match=name):
        SettingsWithoutEnvFile()


@pytest.mark.usefixtures("required_env")
@pytest.mark.parametrize("name", ["PARSE_MAX_FILES", "PARSE_MAX_FILE_BYTES"])
def test_a_zero_parse_limit_names_it(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setenv(name, "0")
    with pytest.raises(ValidationError, match=name):
        SettingsWithoutEnvFile()


@pytest.mark.usefixtures("required_env")
def test_frontend_origin_has_a_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODECRAFT_FRONTEND_ORIGIN", raising=False)
    settings = SettingsWithoutEnvFile()
    assert settings.CODECRAFT_FRONTEND_ORIGIN == "http://localhost:5173"


def test_the_env_file_path_does_not_depend_on_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / "fake.env"
    env_file.write_text(
        "".join(f"{name}={value}\n" for name, value in _REQUIRED.items())
        + "CODECRAFT_FRONTEND_ORIGIN=http://localhost:5173\n",
        encoding="utf-8",
    )
    for name in (*_REQUIRED, "CODECRAFT_FRONTEND_ORIGIN"):
        monkeypatch.delenv(name, raising=False)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)

    settings = Settings()

    assert settings.PARSE_MAX_FILES == 50_000
    assert settings.PARSE_MAX_FILE_BYTES == 2_000_000
    assert settings.DATABASE_URL == "postgresql://api@example/db"
