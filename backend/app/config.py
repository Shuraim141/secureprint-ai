"""Central configuration. Values come from environment variables or the repo-root .env."""
import base64
import binascii
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "SecurePrint AI"
    environment: str = "development"
    log_level: str = "INFO"

    # Production: PostgreSQL URL; SQLAlchemy code stays unchanged.
    database_url: str = f"sqlite:///{REPO_ROOT / 'data' / 'secureprint.db'}"
    # Production: object storage (S3) behind a StorageBackend adapter (Phase 4).
    storage_dir: Path = REPO_ROOT / "data" / "storage"
    model_dir: Path = REPO_ROOT / "ml" / "models"  # trained .joblib artifacts (see ml/README.md)
    max_upload_mb: int = Field(default=50, ge=1, le=500)

    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = Field(default=30, ge=1, le=1440)
    max_failed_logins: int = Field(default=5, ge=1, le=100)
    lockout_minutes: int = Field(default=15, ge=1, le=1440)

    # Production: KMS/HSM behind a KeyProvider adapter. MVP: local master key from .env.
    master_key: str = ""
    seed_password: str = ""
    cors_origins: str = "http://localhost:5173"
    hardware_profile: str = "auto"

    @field_validator("jwt_secret")
    @classmethod
    def _reject_placeholder_secret(cls, value: str) -> str:
        if value.lower().startswith("change-me"):
            raise ValueError("JWT_SECRET is still a placeholder; run scripts/init_env.py")
        return value

    @field_validator("master_key")
    @classmethod
    def _validate_master_key(cls, value: str) -> str:
        if not value:
            return value
        try:
            raw = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("MASTER_KEY must be valid base64") from exc
        if len(raw) != 32:
            raise ValueError("MASTER_KEY must decode to exactly 32 bytes (AES-256)")
        return value

    @field_validator("environment")
    @classmethod
    def _validate_environment(cls, value: str) -> str:
        if value not in {"development", "test", "production"}:
            raise ValueError("ENVIRONMENT must be development, test or production")
        return value

    @field_validator("hardware_profile")
    @classmethod
    def _validate_hardware_profile(cls, value: str) -> str:
        if value not in {"auto", "low", "standard", "high"}:
            raise ValueError("HARDWARE_PROFILE must be auto, low, standard or high")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()  # jwt_secret is read from the environment
