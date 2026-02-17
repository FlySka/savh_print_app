from __future__ import annotations

import os
import sys

from loguru import logger as _base_logger

_CONFIGURED = False
_FORMAT = "<green>{time:YYYY-MM-DDTHH:mm:ss.SSSZ}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"


def configure_logging() -> None:
    """Configura Loguru para print_server.

    Se deja local al paquete para evitar dependencias cruzadas entre apps.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_config = {
        "handlers": [
            {
                "sink": sys.stdout,
                "format": _FORMAT,
                "diagnose": False,
                "level": log_level,
            },
        ],
    }
    _base_logger.configure(**log_config)
    _CONFIGURED = True


def get_logger(name: str):
    """Retorna un logger que muestra `name` en el formato ({name})."""
    configure_logging()
    return _base_logger.patch(lambda record: record.update(name=name))

