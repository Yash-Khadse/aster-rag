from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    # Unknown values fail at startup instead of silently skipping hosted checks.
    environment: Literal["local", "development", "test", "hosted"] = "local"
    database_url: str = "sqlite:///data/app.db"
    jwt_secret: str = ""
    token_minutes: int = 120
    data_dir: str = "data"
    storage_backend: str = "local"
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_bucket: str = "documents"
    cors_origins: str = "http://localhost:3000"
    max_upload_bytes: int = 5 * 1024 * 1024
    monthly_query_limit: int = 1000
    requests_per_minute: int = 30
    demo_enabled: bool = False
    demo_workspace_id: str = ""
    # Open self-registration (anyone may create an org). Set false for invite-only deployments.
    registration_enabled: bool = True
    # Honor the last X-Forwarded-For hop as the client IP. Enable only behind exactly one trusted proxy.
    trust_proxy: bool = False
    max_workspace_documents: int = 500
    max_workspace_bytes: int = 500 * 1024 * 1024
    demo_accounts_per_hour: int = 100
    # shortcut: BM25 needs corpus text in memory, so retrieval loads at most this many chunks per query.
    max_retrieval_chunks: int = 50000
    sse_heartbeat_seconds: float = 15
    vector_backend: str = "qdrant"
    lease_seconds: int = 900
    # None resolves in validate_runtime: required when hosted, off otherwise.
    require_email_verification: bool | None = None
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True
    # Base URL of the web app; verification links are {web_url}/?verify=<token>.
    web_url: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def validate_runtime(self):
        if "*" in self.cors_origin_list:  # cookies are credentialed, so wildcard origins are unsafe
            raise ValueError("CORS_ORIGINS must list explicit origins, not '*'")
        if self.require_email_verification is None:
            self.require_email_verification = self.environment == "hosted"
        if self.environment == "hosted":
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Hosted mode requires PostgreSQL")
            if self.storage_backend != "supabase" or not self.supabase_url or not self.supabase_service_key:
                raise ValueError("Hosted mode requires persistent Supabase storage")
            if self.vector_backend != "pinecone":
                raise ValueError("Hosted mode requires Pinecone")
            if len(self.jwt_secret) < 32:
                raise ValueError("Hosted mode requires a random JWT_SECRET of at least 32 characters")
            if self.require_email_verification and (not self.smtp_host or "localhost" in self.web_url):
                raise ValueError("Hosted email verification requires SMTP_HOST and a public WEB_URL")
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        if not self.jwt_secret:
            import secrets

            secret_path = Path(self.data_dir) / ".jwt-secret"
            if not secret_path.exists():
                try:
                    with secret_path.open("x") as f:
                        f.write(secrets.token_urlsafe(48))
                except FileExistsError:
                    pass
            self.jwt_secret = secret_path.read_text().strip()
