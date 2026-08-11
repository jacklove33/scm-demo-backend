from enum import StrEnum

from app.core.exceptions import EntityConflict


class CustomerPoSource(StrEnum):
    MANUAL = "MANUAL"
    IMPORT = "IMPORT"
    API = "API"
    EDI = "EDI"


class CustomerPoStatus(StrEnum):
    DRAFT = "DRAFT"
    RECEIVED = "RECEIVED"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"
    PROCESSING = "PROCESSING"
    ON_HOLD = "ON_HOLD"
    CONVERTED = "CONVERTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class CustomerPoStatusEventType(StrEnum):
    CREATED = "CREATED"
    STATUS_CHANGED = "STATUS_CHANGED"
    VALIDATION_STARTED = "VALIDATION_STARTED"
    VALIDATION_PASSED = "VALIDATION_PASSED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PUT_ON_HOLD = "PUT_ON_HOLD"
    RELEASED = "RELEASED"
    CONVERTED = "CONVERTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class CustomerPoStatusTransitions:
    _allowed = {
        CustomerPoStatus.DRAFT: {CustomerPoStatus.RECEIVED, CustomerPoStatus.CANCELLED},
        CustomerPoStatus.RECEIVED: {
            CustomerPoStatus.VALIDATING,
            CustomerPoStatus.ON_HOLD,
            CustomerPoStatus.CANCELLED,
        },
        CustomerPoStatus.VALIDATING: {
            CustomerPoStatus.VALIDATED,
            CustomerPoStatus.REJECTED,
            CustomerPoStatus.ON_HOLD,
        },
        CustomerPoStatus.VALIDATED: {
            CustomerPoStatus.PROCESSING,
            CustomerPoStatus.ON_HOLD,
            CustomerPoStatus.CANCELLED,
        },
        CustomerPoStatus.PROCESSING: {
            CustomerPoStatus.CONVERTED,
            CustomerPoStatus.ON_HOLD,
            CustomerPoStatus.REJECTED,
        },
        CustomerPoStatus.ON_HOLD: {
            CustomerPoStatus.VALIDATING,
            CustomerPoStatus.VALIDATED,
            CustomerPoStatus.PROCESSING,
            CustomerPoStatus.CANCELLED,
        },
        CustomerPoStatus.CONVERTED: set(),
        CustomerPoStatus.REJECTED: set(),
        CustomerPoStatus.CANCELLED: set(),
    }

    @classmethod
    def require(cls, before: CustomerPoStatus, after: CustomerPoStatus) -> None:
        if after not in cls._allowed[before]:
            raise EntityConflict(f"Invalid Customer PO status transition: {before} -> {after}")

    @staticmethod
    def event_type(after: CustomerPoStatus) -> CustomerPoStatusEventType:
        return {
            CustomerPoStatus.VALIDATING: CustomerPoStatusEventType.VALIDATION_STARTED,
            CustomerPoStatus.VALIDATED: CustomerPoStatusEventType.VALIDATION_PASSED,
            CustomerPoStatus.ON_HOLD: CustomerPoStatusEventType.PUT_ON_HOLD,
            CustomerPoStatus.CONVERTED: CustomerPoStatusEventType.CONVERTED,
            CustomerPoStatus.REJECTED: CustomerPoStatusEventType.REJECTED,
            CustomerPoStatus.CANCELLED: CustomerPoStatusEventType.CANCELLED,
        }.get(after, CustomerPoStatusEventType.STATUS_CHANGED)
