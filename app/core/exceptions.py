class AppError(Exception):
    code = "APP_ERROR"
    status_code = 400

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AuthenticationRequired(AppError):
    code = "AUTHENTICATION_REQUIRED"
    status_code = 401


class PermissionDenied(AppError):
    code = "PERMISSION_DENIED"
    status_code = 403


class EntityNotFound(AppError):
    code = "NOT_FOUND"
    status_code = 404


class VersionConflict(AppError):
    code = "VERSION_CONFLICT"
    status_code = 409


class EntityConflict(AppError):
    code = "CONFLICT"
    status_code = 409


class ValidationFailure(AppError):
    code = "VALIDATION_ERROR"
    status_code = 422


class ImportValidationFailure(ValidationFailure):
    code = "IMPORT_VALIDATION_FAILED"


class ExternalServiceFailure(AppError):
    code = "EXTERNAL_SERVICE_ERROR"
    status_code = 502
