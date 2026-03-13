from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "channel-policy-router"
    app_env: str = "dev"

    persistence_backend: str = Field(default="in_memory", pattern="^(in_memory|postgres)$")
    postgres_dsn: str = "postgresql://postgres:postgres@localhost:5432/channel_policy_router"
    postgres_auto_init: bool = True

    queue_max_depth_per_point: int = Field(default=5, ge=1)
    queue_retry_after_seconds: int = Field(default=30, ge=1)
    idempotency_window_seconds: int = Field(default=3600, ge=60)
    correlation_window_seconds: int = Field(default=86400, ge=60)
    sla_deadline_offset_seconds: int = 0

    sla_batch_lock_ttl_seconds: int = Field(default=30, ge=1)
    incident_delivery_lock_ttl_seconds: int = Field(default=30, ge=1)
    incident_delivery_backoff_base_seconds: int = Field(default=10, ge=1)
    incident_delivery_backoff_max_seconds: int = Field(default=300, ge=1)

    model_config = SettingsConfigDict(
        env_prefix="CHANNEL_POLICY_ROUTER_",
        env_file=".env",
        extra="ignore",
    )
