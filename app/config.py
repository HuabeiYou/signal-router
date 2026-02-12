import os
from dataclasses import dataclass


@dataclass
class Settings:
    app_env: str = os.getenv("APP_ENV", "dev")
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
    inbound_token: str = os.getenv("INBOUND_TOKEN", "change-me-token")
    admin_username: str = os.getenv("ADMIN_USERNAME", "admin")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "change-me-password")
    fernet_key: str = os.getenv("FERNET_KEY", "")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    session_secret: str = os.getenv("SESSION_SECRET", "change-me-session-secret")


settings = Settings()
