"""Compat shim: import DB utilities from `printing_queue.infra.db`."""

from printing_queue.infra.db import SessionLocal, engine, get_db

__all__ = ["SessionLocal", "engine", "get_db"]

