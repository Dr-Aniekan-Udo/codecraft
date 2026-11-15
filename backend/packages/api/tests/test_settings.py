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
def test_frontend_origin_has_a_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODECRAFT_FRONTEND_ORIGIN", raising=False)
    settings = SettingsWithoutEnvFile()
    assert settings.CODECRAFT_FRONTEND_ORIGIN == "http://localhost:5173"
