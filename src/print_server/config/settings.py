"""Compat shim.

print_server mantuvo históricamente la configuración DB/printing. Con la
arquitectura de monolito modular, esa configuración vive en `printing_queue`.
"""

from printing_queue.settings import Settings, settings

__all__ = ["Settings", "settings"]
