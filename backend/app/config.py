from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openrouter_api_key: str = ""
    gemini_api_key: str = ""
    semantic_scholar_api_key: str = ""

    # NeonDB connection string — format: postgresql://user:pass@host/dbname?sslmode=require
    database_url: str = ""

    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    allowed_origins: list[str] = ["http://localhost:8501", "http://127.0.0.1:8501"]


settings = Settings()
