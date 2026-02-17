from __future__ import annotations

import os
from typing import Any

_SENTRY_CONFIGURED = False
_METRICS_CONFIGURED = False


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def init_sentry(service_name: str) -> None:
    """Inicializa Sentry si `SENTRY_DSN` está configurado.

    Es *opcional* y no debe romper si no está instalado `sentry-sdk`.
    """
    global _SENTRY_CONFIGURED
    if _SENTRY_CONFIGURED:
        return

    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return

    try:
        import sentry_sdk
    except Exception:
        # sin dependency o falla de import: no romper
        return

    integrations: list[Any] = []
    try:
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        integrations.append(FastApiIntegration())
    except Exception:
        pass

    def _float_env(name: str, default: float = 0.0) -> float:
        raw = os.getenv(name, "")
        if raw is None or raw.strip() == "":
            return default
        try:
            return float(raw)
        except Exception:
            return default

    sentry_sdk.init(
        dsn=dsn,
        environment=(os.getenv("SENTRY_ENVIRONMENT") or None),
        release=(os.getenv("SENTRY_RELEASE") or None),
        server_name=(os.getenv("SENTRY_SERVER_NAME") or None),
        traces_sample_rate=_float_env("SENTRY_TRACES_SAMPLE_RATE", 0.0),
        profiles_sample_rate=_float_env("SENTRY_PROFILES_SAMPLE_RATE", 0.0),
        send_default_pii=_truthy(os.getenv("SENTRY_SEND_DEFAULT_PII", "false")),
        integrations=integrations,
    )

    try:
        sentry_sdk.set_tag("service", service_name)
    except Exception:
        pass

    _SENTRY_CONFIGURED = True


def capture_exception(exc: BaseException) -> None:
    """Captura una excepción en Sentry (si está habilitado)."""
    if not _SENTRY_CONFIGURED:
        return
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except Exception:
        return


def instrument_fastapi_if_enabled(app: Any) -> None:
    """Expone métricas Prometheus en FastAPI si `ENABLE_METRICS=true`.

    Es *opcional* y no debe romper si no está instalado el instrumentator.
    """
    global _METRICS_CONFIGURED
    if _METRICS_CONFIGURED:
        return

    if not _truthy(os.getenv("ENABLE_METRICS", "false")):
        return

    try:
        from prometheus_fastapi_instrumentator import Instrumentator
    except Exception:
        return

    endpoint = os.getenv("METRICS_PATH", "/metrics").strip() or "/metrics"
    try:
        Instrumentator().instrument(app).expose(
            app,
            endpoint=endpoint,
            include_in_schema=False,
        )
        _METRICS_CONFIGURED = True
    except Exception:
        # no romper el arranque si algo falla en métricas
        return

