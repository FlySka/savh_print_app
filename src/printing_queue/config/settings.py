from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración del módulo printing_queue desde variables de entorno.

    Nota:
        Se permite `extra="ignore"` porque en el mismo entorno pueden existir
        variables para otros servicios/módulos (por ejemplo create_prints_server).

    Args:
        DATABASE_URL: URL de conexión a PostgreSQL.
        UPLOAD_DIR: Carpeta para archivos subidos.
        PRINTER_NAME: Nombre exacto de la impresora en Windows.
        SUMATRA_PATH: Ruta a SumatraPDF.exe.
        POLL_SECONDS: Intervalo de polling del worker.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str
    UPLOAD_DIR: str = "data/uploads"
    PRINTER_NAME: str = ""
    SUMATRA_PATH: str = ""
    POLL_SECONDS: int = 2


settings = Settings()

