from dotenv import load_dotenv

# Load .env into os.environ before anything else so google-genai picks up GOOGLE_API_KEY
load_dotenv()

import secrets
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings

# Generated once at process startup — rotates on every container restart.
# Never written to disk or env; all active sessions are invalidated on redeploy.
_RUNTIME_JWT_SECRET = secrets.token_hex(32)


class Settings(BaseSettings):
    google_api_key: str
    google_oauth_client_id: str
    google_oauth_client_secret: str
    allowed_emails: str           # comma-separated list of authorized Google accounts
    app_base_url: str = "http://localhost:8080"

    # JWT secret is runtime-generated, not read from .env
    jwt_secret: str = _RUNTIME_JWT_SECRET

    @property
    def allowed_email_list(self) -> List[str]:
        return [e.strip().lower() for e in self.allowed_emails.split(",") if e.strip()]

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()