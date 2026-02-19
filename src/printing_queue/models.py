"""Compat shim: import ORM models from `printing_queue.infra.models`."""

from printing_queue.infra.models import Base, PrintJob, PrintJobStatus, PrintJobStatusEvent, PrintJobType

__all__ = ["Base", "PrintJob", "PrintJobStatus", "PrintJobStatusEvent", "PrintJobType"]
