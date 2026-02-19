from __future__ import annotations

import os
from typing import Any

_SENTRY_CONFIGURED = False
_METRICS_CONFIGURED = False
_HTTP_STATUS_METRICS_CONFIGURED = False

_HTTP_REQUESTS_BY_STATUS_TOTAL: Any | None = None


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
    global _HTTP_REQUESTS_BY_STATUS_TOTAL
    global _HTTP_STATUS_METRICS_CONFIGURED
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

    # Métrica adicional con `status` para poder graficar tasa de errores (4xx/5xx).
    # El instrumentator expone histogramas/contadores de latencia, pero dependiendo
    # de la config puede no incluir status codes como label.
    if _HTTP_STATUS_METRICS_CONFIGURED:
        return

    try:
        from prometheus_client import Counter
    except Exception:
        return

    if _HTTP_REQUESTS_BY_STATUS_TOTAL is None:
        try:
            # Nombre específico para evitar colisiones con otras instrumentaciones.
            _HTTP_REQUESTS_BY_STATUS_TOTAL = Counter(
                "http_requests_by_status_total",
                "Total HTTP requests by handler/method/status.",
                labelnames=("handler", "method", "status"),
            )
        except Exception:
            _HTTP_REQUESTS_BY_STATUS_TOTAL = None

    if _HTTP_REQUESTS_BY_STATUS_TOTAL is None:
        return

    def _extract_handler(request: Any) -> str:
        scope = getattr(request, "scope", None) or {}
        route = scope.get("route")
        handler = getattr(route, "path", None) or scope.get("path") or ""
        if isinstance(handler, str) and handler.startswith("/static"):
            return "/static"
        return handler if isinstance(handler, str) and handler else ""

    @app.middleware("http")
    async def _prometheus_http_status_middleware(request: Any, call_next: Any) -> Any:
        try:
            response = await call_next(request)
        except Exception:
            # Si falla antes de responder, igual intenta contar como 500.
            handler = _extract_handler(request) or getattr(getattr(request, "url", None), "path", "") or ""
            if handler and handler != endpoint:
                try:
                    _HTTP_REQUESTS_BY_STATUS_TOTAL.labels(
                        handler=handler,
                        method=getattr(request, "method", ""),
                        status="500",
                    ).inc()
                except Exception:
                    pass
            raise

        handler = _extract_handler(request) or getattr(getattr(request, "url", None), "path", "") or ""
        if handler and handler != endpoint:
            try:
                _HTTP_REQUESTS_BY_STATUS_TOTAL.labels(
                    handler=handler,
                    method=getattr(request, "method", ""),
                    status=str(getattr(response, "status_code", "")),
                ).inc()
            except Exception:
                pass
        return response

    _HTTP_STATUS_METRICS_CONFIGURED = True
