import re
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Configuration from env vars or a local .env file."""

    model_config = SettingsConfigDict(env_file=str(_BASE_DIR / ".env"), env_file_encoding="utf-8")

    APP_ENV: str = "dev"
    DATABASE_URL: str = f"sqlite:///{(_BASE_DIR / 'app.db').as_posix()}"
    SECRET_KEY: str = "dev-secret-change-me"
    ACCESS_TOKEN_MINUTES: int = 30

    AUTO_SEED_EXAMPLE_USER: bool | None = None
    EXAMPLE_USER_EMAIL: str = "example@demo.local"
    EXAMPLE_USER_PASSWORD: str = "DemoPass123!"
    EXAMPLE_USER_ROLE: str = "admin"

    @model_validator(mode="after")
    def _normalize_database_url(self):
        url = self.DATABASE_URL
        if not url.startswith("sqlite:///"):
            return self

        path = url.removeprefix("sqlite:///")
        if path == ":memory:" or path.startswith("file:"):
            return self

        if path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\\\/]", path):
            return self

        abs_path = (_BASE_DIR / Path(path)).resolve()
        self.DATABASE_URL = f"sqlite:///{abs_path.as_posix()}"
        return self


settings = Settings()
