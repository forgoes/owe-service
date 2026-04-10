from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.4"
    model_startup_probe: bool = True
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "postgres"
    db_password: str = "postgres"
    db_name: str = "owe"
    db_schema: str = "owe"
    db_echo: bool = False
    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str = "owe-service"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    estimated_mwh_per_sqft_commercial: float = 0.0016
    estimated_mwh_per_sqft_industrial: float = 0.0032
    auth0_domain: str = ""
    auth0_api_audience: str = ""

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg2",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )

    @property
    def auth0_enabled(self) -> bool:
        return bool(self.auth0_domain and self.auth0_api_audience)

    @property
    def auth0_issuer(self) -> str:
        domain = self.auth0_domain.strip()
        if not domain:
            return ""
        if not domain.startswith("http://") and not domain.startswith("https://"):
            domain = f"https://{domain}"
        return f"{domain.rstrip('/')}/"


settings = Settings()
