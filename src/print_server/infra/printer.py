from __future__ import annotations

import subprocess
from pathlib import Path
from print_server.infra.logging import get_logger

from print_server.config.settings import settings

logger = get_logger(__name__)


def print_pdf_windows_sumatra(pdf_path: str) -> None:
    """Imprime un PDF en Windows usando SumatraPDF por línea de comandos.

    Args:
        pdf_path (str): Ruta al archivo PDF.

    Raises:
        RuntimeError: Si el proceso de impresión falla.
    """
    exe = Path(settings.SUMATRA_PATH)
    if not exe.exists():
        raise RuntimeError(f"SumatraPDF no encontrado en: {exe}")

    pdf = Path(pdf_path)
    if not pdf.exists():
        raise RuntimeError(f"PDF no encontrado: {pdf}")

    logger.info(f"Lanzando SumatraPDF para imprimir {pdf} en {settings.PRINTER_NAME}")
    cmd = [
        str(exe),
        "-print-to",
        settings.PRINTER_NAME,
        "-silent",
        str(pdf),
    ]

    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "Falló la impresión con SumatraPDF. "
            f"stdout={completed.stdout} stderr={completed.stderr}"
        )
    logger.info(f"Impresión completada {pdf}")
