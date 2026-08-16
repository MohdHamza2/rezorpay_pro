import json
import logging
import sys
from contextvars import ContextVar
from typing import Any, Dict

# Context variable to store request ID
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Add context variables
        req_id = request_id_ctx.get()
        if req_id:
            log_obj["request_id"] = req_id

        # Include exception traceback if present
        if record.exc_info:
            log_obj["exc_info"] = self.formatException(record.exc_info)

        # Merge extra arguments if provided
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            log_obj.update(record.extra)

        # Add kwargs if they exist and are dict
        for key, value in record.__dict__.items():
            if key not in [
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "message",
                "module",
                "msecs",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
                "taskName",
                "extra",
            ]:
                # Basic check to avoid serialization errors
                try:
                    json.dumps(value)
                    log_obj[key] = value
                except TypeError:
                    log_obj[key] = str(value)

        return json.dumps(log_obj)


_ENV_LOG_LEVELS = {
    "development": logging.DEBUG,
    "staging": logging.INFO,
    "production": logging.INFO,
    "test": logging.WARNING,
}


def setup_logging(environment: str = "development"):
    """Set up structured JSON logging with environment-aware log levels.

    Args:
        environment: One of 'development', 'staging', 'production', 'test'.
    """
    level = _ENV_LOG_LEVELS.get(environment, logging.INFO)
    logger = logging.getLogger()
    logger.setLevel(level)

    # Clear existing handlers
    logger.handlers.clear()

    # Create stdout handler with JSON formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)

    # Configure uvicorn loggers to use the same handler
    for logger_name in ("uvicorn.access", "uvicorn.error", "uvicorn"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers = [handler]
        uvicorn_logger.propagate = False

    return logger
