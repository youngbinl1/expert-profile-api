"""Runtime settings, read from environment variables on every call (easy to override in tests)."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_api_key: str          # shared secret clients must send in the X-API-Key header
    anthropic_api_key: str    # optional: without it the service falls back to a template/mock mode
    llm_model: str
    ddb_table: str            # optional: without it, history is kept in memory only
    region: str
    history_ttl_days: int
    auth_disabled: bool


def get_settings() -> Settings:
    return Settings(
        app_api_key=os.getenv("APP_API_KEY", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "claude-haiku-4-5"),
        ddb_table=os.getenv("DDB_TABLE", ""),
        region=os.getenv("APP_REGION", "ap-northeast-1"),
        history_ttl_days=int(os.getenv("HISTORY_TTL_DAYS", "30")),
        auth_disabled=os.getenv("AUTH_DISABLED", "").lower() == "true",
    )
