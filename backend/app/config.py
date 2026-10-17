from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    database_url: str = "sqlite:///./property2claim.db"
    upload_dir: Path = Path("./storage/uploads")
    max_upload_mb: int = 25
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-20b"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_floorplan_model: str = "gemini-3.1-pro-preview"
    jev_api_key: str | None = None
    jev_api_base_url: str = "https://api.typesafe.ai/v1/systemone"
    jev_model: str = "jev-latest"
    nasa_firms_map_key: str | None = None
    nasa_api_key: str | None = None
    noaa_user_agent: str = "Property2Claim/1.0 (contact: demo@example.invalid)"
    allow_live_hazards: bool = False
    demo_mode: bool = True
    cors_origins: str = "http://localhost:3000"

    # Resolve from the repository root so keys work whether uvicorn is started
    # from the repository or from backend/. Values are never returned to clients.
    model_config = SettingsConfigDict(env_file=ROOT_ENV, extra="ignore")

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
