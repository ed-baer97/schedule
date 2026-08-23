"""Domain errors raised by services (mapped to HTTP in routers)."""


class ServiceError(Exception):
    """Base for service-layer errors."""


class NotFoundError(ServiceError):
    def __init__(self, message: str = "Not found"):
        self.message = message
        super().__init__(message)


class ValidationConflict(ServiceError):
    """Business validation failed (maps to HTTP 422)."""

    def __init__(self, errors: list[str] | str):
        if isinstance(errors, str):
            errors = [errors]
        self.errors = errors
        super().__init__("; ".join(errors))


class BadRequestError(ServiceError):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ConflictError(ServiceError):
    """Resource conflict (maps to HTTP 409)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
