from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    postgres_user: str = "vimonitor"
    postgres_password: str = "change_me"
    postgres_db: str = "vimonitor"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # API / auth
    bootstrap_api_key: str = "change_me_api_key"
    bootstrap_tenant_name: str = "default"

    # Monitoring domain
    target_city: str = "Москва"
    target_city_id: str = ""

    # Scheduling
    default_check_interval_seconds: int = 21600
    scheduler_tick_seconds: int = 60
    schedule_jitter_seconds: int = 300

    # Fetcher
    fetcher_backend: str = "httpx"
    fetch_timeout_seconds: float = 20.0
    fetch_max_retries: int = 3
    fetch_min_delay_seconds: float = 1.0
    fetch_max_delay_seconds: float = 3.0
    global_rate_limit_rps: float = 2.0

    proxy_url: str = ""
    scraping_service_url: str = ""
    scraping_service_key: str = ""

    # Cookie-harvest: reuse ServicePipe cookies obtained from a real browser.
    # session_cookie: raw Cookie header value. cookie_file: path re-read each fetch
    # (lets an external refresher update cookies without restarting workers).
    # harvest_user_agent: fixed UA that MUST match the browser the cookie came from
    # (ServicePipe binds the cookie to UA + IP).
    session_cookie: str = ""
    cookie_file: str = ""
    harvest_user_agent: str = ""

    # Playwright/patchright backend. ServicePipe passes a HEADED real browser with a
    # persistent profile and flags headless — keep headless False (use xvfb on servers).
    playwright_headless: bool = False
    playwright_channel: str = "chromium"
    playwright_user_data_dir: str = "/data/vi_profile"
    playwright_nav_timeout_ms: int = 60000
    playwright_settle_ms: int = 2000
    playwright_settle_tries: int = 20
    playwright_max_concurrency: int = 2

    log_level: str = "INFO"

    @property
    def async_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
