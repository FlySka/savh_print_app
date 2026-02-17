"""Compat shim: import ORM models from `printing_queue.infra.models`."""

from printing_queue.infra.models import Base, PrintJob, PrintJobStatus, PrintJobType

__all__ = ["Base", "PrintJob", "PrintJobStatus", "PrintJobType"]

