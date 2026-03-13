from fastapi import FastAPI

from channel_policy_router.adapters.inbound.http.router import create_router
from channel_policy_router.adapters.outbound.in_memory import InMemoryUnitOfWork
from channel_policy_router.adapters.outbound.postgres import PostgresUnitOfWork
from channel_policy_router.application.uow import UnitOfWork
from channel_policy_router.application.use_cases import CommandRouterUseCases
from channel_policy_router.settings import Settings


def create_use_cases(settings: Settings) -> CommandRouterUseCases:
    uow: UnitOfWork
    if settings.persistence_backend == "postgres":
        uow = PostgresUnitOfWork(
            settings.postgres_dsn,
            auto_init_schema=settings.postgres_auto_init,
        )
    else:
        uow = InMemoryUnitOfWork()

    return CommandRouterUseCases(
        uow=uow,
        queue_max_depth_per_point=settings.queue_max_depth_per_point,
        queue_retry_after_seconds=settings.queue_retry_after_seconds,
        idempotency_window_seconds=settings.idempotency_window_seconds,
        correlation_window_seconds=settings.correlation_window_seconds,
        sla_deadline_offset_seconds=settings.sla_deadline_offset_seconds,
        sla_batch_lock_ttl_seconds=settings.sla_batch_lock_ttl_seconds,
        incident_delivery_lock_ttl_seconds=settings.incident_delivery_lock_ttl_seconds,
        incident_delivery_backoff_base_seconds=settings.incident_delivery_backoff_base_seconds,
        incident_delivery_backoff_max_seconds=settings.incident_delivery_backoff_max_seconds,
    )


def create_app() -> FastAPI:
    settings = Settings()
    use_cases = create_use_cases(settings)

    app = FastAPI(
        title="Channel Policy Router",
        version="1.0.0",
        description="Wave 4 baseline for command channel policy, queueing, and safety constraints.",
    )
    app.include_router(create_router(use_cases))
    return app


app = create_app()
