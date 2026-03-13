class CommandRouterError(Exception):
    """Base command router error."""


class ValidationError(CommandRouterError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class CorrelationConflictError(CommandRouterError):
    def __init__(self, correlation_id: str, existing_command_id: str) -> None:
        super().__init__(f"correlation_id conflict: {correlation_id}")
        self.correlation_id = correlation_id
        self.existing_command_id = existing_command_id


class QueueOverflowError(CommandRouterError):
    def __init__(self, queue_depth: int, retry_after_seconds: int) -> None:
        super().__init__("queue overflow")
        self.queue_depth = queue_depth
        self.retry_after_seconds = retry_after_seconds


class NotFoundError(CommandRouterError):
    pass


class CancelNotAllowedError(CommandRouterError):
    pass


class OverrideNotAllowedError(CommandRouterError):
    pass


class DispatchNotAllowedError(CommandRouterError):
    pass


class ReconciliationNotAllowedError(CommandRouterError):
    pass
