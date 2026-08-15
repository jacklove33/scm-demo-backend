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
    _allowed: dict[CustomerPoStatus, set[CustomerPoStatus]] = {
        CustomerPoStatus.DRAFT: {
            CustomerPoStatus.RECEIVED,
            CustomerPoStatus.CANCELLED,
        },
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

        # Terminal states
        CustomerPoStatus.CONVERTED: set(),
        CustomerPoStatus.REJECTED: set(),
        CustomerPoStatus.CANCELLED: set(),
    }

    @classmethod
    def allowed(
        cls,
        status: CustomerPoStatus,
    ) -> tuple[CustomerPoStatus, ...]:
        """
        Return all valid next statuses.

        This is also used by the API to tell the frontend
        which status options should be displayed.
        """
        return tuple(cls._allowed.get(status, set()))

    @classmethod
    def can_change(
        cls,
        status: CustomerPoStatus,
    ) -> bool:
        """
        True when at least one valid transition exists.
        """
        return bool(cls._allowed.get(status))

    @classmethod
    def require(
        cls,
        before: CustomerPoStatus,
        after: CustomerPoStatus,
    ) -> None:
        """
        Enforce the workflow rule on the server.

        Frontend options are only UI assistance.
        This method remains the real security/business-rule boundary.
        """
        if after not in cls._allowed.get(before, set()):
            raise EntityConflict(
                f"Invalid Customer PO status transition: "
                f"{before.value} -> {after.value}"
            )

    @staticmethod
    def event_type(
        after: CustomerPoStatus,
    ) -> CustomerPoStatusEventType:
        return {
            CustomerPoStatus.VALIDATING:
                CustomerPoStatusEventType.VALIDATION_STARTED,

            CustomerPoStatus.VALIDATED:
                CustomerPoStatusEventType.VALIDATION_PASSED,

            CustomerPoStatus.ON_HOLD:
                CustomerPoStatusEventType.PUT_ON_HOLD,

            CustomerPoStatus.CONVERTED:
                CustomerPoStatusEventType.CONVERTED,

            CustomerPoStatus.REJECTED:
                CustomerPoStatusEventType.REJECTED,

            CustomerPoStatus.CANCELLED:
                CustomerPoStatusEventType.CANCELLED,

        }.get(
            after,
            CustomerPoStatusEventType.STATUS_CHANGED,
        )