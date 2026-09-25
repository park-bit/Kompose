from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore")

    # LLM
    llm_api_key: str = ""
    llm_model: str = "gemini-2.0-flash"

    # Database (defaults to local SQLite for zero-docker setup)
    database_url: str = "sqlite+aiosqlite:///./travel_planner.db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_ttl_api: int = 3600        # 1 hour for API responses
    redis_ttl_scrape: int = 1800     # 30 min for scrape results

    # Google Maps
    google_maps_api_key: str = ""

    # Amadeus
    amadeus_client_id: str = ""
    amadeus_client_secret: str = ""
    amadeus_hostname: str = "test"   # "test" or "production"

    # Apify
    apify_api_token: str = ""

    # OpenWeatherMap
    openweather_api_key: str = ""

    # Exchange Rates
    exchangerate_api_key: str = ""

    # TF model path (exported from Kaggle)
    price_model_path: str = "models/price_trend_model"

    # App
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
