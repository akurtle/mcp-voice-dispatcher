from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

_CONFIGURED = False


def _configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    _configure_logging()
    return logging.getLogger(name)


def _coerce(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _coerce(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_coerce(item) for item in value]
    return str(value)


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    payload = {"event": event, **{key: _coerce(value) for key, value in fields.items()}}
    logger.info(json.dumps(payload, sort_keys=True))


def new_request_id() -> str:
    return uuid.uuid4().hex
