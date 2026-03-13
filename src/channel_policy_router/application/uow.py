from abc import ABC, abstractmethod

from channel_policy_router.domain.repositories import (
    BatchLockRepository,
    CommandRepository,
    IncidentHookRepository,
)


class UnitOfWork(ABC):
    commands: CommandRepository
    incidents: IncidentHookRepository
    locks: BatchLockRepository

    @abstractmethod
    def __enter__(self) -> "UnitOfWork":
        raise NotImplementedError

    @abstractmethod
    def __exit__(self, exc_type, exc, tb) -> None:
        raise NotImplementedError

    @abstractmethod
    def commit(self) -> None:
        raise NotImplementedError

    def rollback(self) -> None:
        raise NotImplementedError
