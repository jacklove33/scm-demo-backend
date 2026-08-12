from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from app.core.exceptions import ValidationFailure


class InvalidDateRange(ValidationFailure):
    code = "INVALID_DATE_RANGE"


class DateRangeTooLarge(ValidationFailure):
    code = "DATE_RANGE_TOO_LARGE"


@dataclass(frozen=True, slots=True)
class DateTimeBounds:
    from_inclusive: datetime | None
    to_exclusive: datetime | None


def validate_date_range(
    date_from: date | None,
    date_to: date | None,
    *,
    max_days: int,
    field_name: str,
) -> DateTimeBounds:
    """Validate an inclusive calendar-date range and produce UTC half-open boundaries."""
    if date_from and date_to:
        if date_from > date_to:
            raise InvalidDateRange(
                f"{field_name}_date_from cannot be later than {field_name}_date_to."
            )
        if (date_to - date_from).days + 1 > max_days:
            raise DateRangeTooLarge(
                f"{field_name.capitalize()} date range cannot exceed {max_days} days."
            )
    return DateTimeBounds(
        datetime.combine(date_from, datetime.min.time(), UTC) if date_from else None,
        datetime.combine(date_to + timedelta(days=1), datetime.min.time(), UTC)
        if date_to
        else None,
    )
