import logging
import logging.config
import time


class UtcFormatter(logging.Formatter):
    """Human-readable formatter with deterministic UTC timestamps."""

    default_msec_format = "%s.%03d"

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        timestamp = time.strftime(
            datefmt or "%Y-%m-%d %H:%M:%S",
            time.gmtime(record.created),
        )
        return f"{timestamp}.{int(record.msecs):03d}"

    def format(self, record: logging.LogRecord) -> str:
        correlation_id = getattr(record, "correlation_id", None)
        if not correlation_id:
            return super().format(record)

        original_message, original_args = record.msg, record.args
        try:
            record.msg = f"correlation_id={correlation_id} {record.getMessage()}"
            record.args = ()
            return super().format(record)
        finally:
            record.msg, record.args = original_message, original_args


LOGGING_CONFIG: dict[str, object] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "utc": {
            "()": "app.core.logging.UtcFormatter",
            "format": "%(asctime)s UTC %(levelname)s %(name)s %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "utc",
            "stream": "ext://sys.stderr",
        }
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "uvicorn": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}


def configure_logging() -> None:
    logging.config.dictConfig(LOGGING_CONFIG)
