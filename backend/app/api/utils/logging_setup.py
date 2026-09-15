"""
Structured JSON logging + correlation ID context var.

The `logger` defined here is imported across the whole application.
"""

import json
import logging
import contextvars
from datetime import datetime


# ---------- LOGGING ----------
_correlation_id_var = contextvars.ContextVar("correlation_id", default="unknown")


def get_correlation_id() -> str:
    return _correlation_id_var.get()


def set_correlation_id(cid: str):
    return _correlation_id_var.set(cid)


def reset_correlation_id(token) -> None:
    _correlation_id_var.reset(token)


class CorrelationFilter(logging.Filter):
    def filter(self, record):
        record.correlation_id = _correlation_id_var.get()
        return True


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
        }
        if hasattr(record, "correlation_id"):
            log_obj["correlation_id"] = record.correlation_id
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())

logger = logging.getLogger("hot_portion")
logger.setLevel(logging.INFO)
if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
    logger.addHandler(handler)
logger.addFilter(CorrelationFilter())

uvicorn_logger = logging.getLogger("uvicorn.access")
uvicorn_logger.handlers = [handler]
uvicorn_logger.addFilter(CorrelationFilter())
