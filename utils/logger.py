import contextvars
import logging
import uuid
from pathlib import Path

import structlog

from configs import PROJECT_DATA_DIR

LOGS_DIR = PROJECT_DATA_DIR.joinpath("logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Context variable to carry the correlation ID through async/sync call chains
_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)


def get_correlation_id() -> str:
    return _correlation_id.get()


def set_correlation_id(cid: str | None = None) -> str:
    """Set (or generate) a correlation ID for the current context. Returns the ID."""
    cid = cid or str(uuid.uuid4())
    _correlation_id.set(cid)
    return cid


def _add_correlation_id(logger: object, method_name: str, event_dict: dict) -> dict:
    event_dict["correlation_id"] = get_correlation_id() or "n/a"
    return event_dict


# All app loggers live under this namespace so they inherit DEBUG level
# without affecting third-party loggers that sit under the root at INFO.
_APP_LOGGER_NAME = "app"


def configure_logging(
    log_dir: Path | None = None, log_filename: str = "app.log"
) -> None:
    """
    Configure structlog and stdlib logging.

    - Root logger: INFO — covers all third-party libraries with no explicit list.
    - 'app' logger: DEBUG — used by all first-party code via get_logger().
    - If *log_dir* is provided the log file is written there; otherwise only
      the console handler is attached.
    """
    log_dir = log_dir or LOGS_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / log_filename

    # --- stdlib handler: console (human-readable) ---
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    # --- stdlib handler: file (JSON lines) ---
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(message)s"))

    # Root at INFO: third-party libs get INFO and above automatically
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # App logger at DEBUG: propagates up to root handlers
    app_logger = logging.getLogger(_APP_LOGGER_NAME)
    app_logger.setLevel(logging.DEBUG)
    app_logger.propagate = True

    # watchfiles is extremely verbose even at INFO; restrict to ERROR only
    logging.getLogger("watchfiles").propagate = False
    logging.getLogger("watchfiles").handlers.clear()

    # --- structlog pipeline ---
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        _add_correlation_id,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Console: pretty coloured output
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(colors=True),
        foreign_pre_chain=shared_processors,
    )
    console_handler.setFormatter(console_formatter)

    # File: JSON lines
    file_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )
    file_handler.setFormatter(file_formatter)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger scoped under the 'app' namespace.

    All loggers returned here operate at DEBUG level while third-party
    libraries remain at the root INFO level.
    """
    return structlog.get_logger(f"{_APP_LOGGER_NAME}.{name}")
