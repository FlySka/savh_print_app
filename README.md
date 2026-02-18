## SAVH Print App (dev notes)

Monolito modular en Python que:

- expone una **web** (FastAPI) para solicitar generación/impresión
- usa una **BD PostgreSQL** como cola (`printing.print_jobs`)
- corre 2 **workers**:
  - `generate_worker`: lee Google Sheets y genera PDFs
  - `print_worker`: imprime PDFs en Windows usando SumatraPDF

Estado de soporte: la app se mantiene **solo para Windows 10/11** (nativo). Las instrucciones Linux/WSL quedan como referencia histórica y ya no se prueban.

---

### Componentes

**Web / API (FastAPI)**

- Entrypoint: `src/print_server/app/main.py` (incluye routers de `print_server` y `create_prints_server`)
- UI: `GET /` (template `templates/index.html`, assets en `static/`)
- Health: `GET /health`

**Workers**

- Generación: `python -m create_prints_server.worker.generate_worker`
  - toma jobs `PENDING` tipo `shipping_docs`
  - genera PDFs y deja el job en `READY` con `payload.files`
- Impresión: `python -m print_server.worker.print_worker`
  - toma jobs `READY` (upload o generados)
  - imprime `payload.files` y marca `DONE` o `ERROR`

**BD**

- PostgreSQL (SQLAlchemy + psycopg)
- Tabla: `printing.print_jobs`
- Enums PostgreSQL requeridos:
  - `printing.print_job_type` (`shipping_docs`, `upload`)
  - `printing.print_job_status` (`pending`, `generating`, `ready`, `printing`, `done`, `error`)

---

### Requisitos

- Python `>=3.10`
- Poetry
- PostgreSQL
- Para imprimir en Windows: SumatraPDF instalado y una impresora configurada
- Credenciales de Google (Service Account) con acceso de lectura al Google Sheet

---

### Variables de entorno (`.env`)

Este repo **requiere** un `.env` para funcionar. Usa `.env.example.windows` como base; el ejemplo Linux queda solo como referencia legacy.

Variables principales:

- `DATABASE_URL`: conexión a Postgres (ej: `postgresql+psycopg://user:pass@localhost:5432/db`)
- `GOOGLE_APPLICATION_CREDENTIALS`: path al JSON del service account
- `SHEETS_ID`, `*_SHEET`, `*_RANGE`: configuración de lectura de Google Sheets
- `PDF_ORDERS_PATH`, `PDF_GUIDES_PATH`: paths de salida de PDFs
- `UPLOAD_DIR`: dónde se guardan PDFs subidos
- `PRINTER_NAME`, `SUMATRA_PATH`: impresión por SumatraPDF (Windows)
- `POLL_SECONDS`: polling de workers
- `HOST`, `PORT`: host/puerto para levantar la API

Notas:

- Paths deben ser Windows (ej. `C:\\Users\\...\\data\\uploads`). El uso con WSL no está soportado.

---

### Inicialización de BD (1 vez)

Este proyecto asume que existen el schema y los enum types de Postgres (porque los modelos usan `create_type=False`).

1) Crea schema + enums:

```bash
# psql NO entiende el "+psycopg" del SQLAlchemy URL, usa una URL "postgresql://"
psql "${DATABASE_URL/+psycopg/}" -f scripts/init_db.sql
```

2) La tabla `printing.print_jobs` la crea la app al iniciar (`Base.metadata.create_all(...)`).

---

### Instalación (Windows)

PowerShell:

```powershell
poetry install
Copy-Item .env.example.windows .env
```

CMD:

```bat
poetry install
copy .env.example.windows .env
```

Completa `.env` con tus valores.

---

### Correr (API + workers) con logs

Script recomendado (crea logs en `data/logs/` y pids en `data/pids/`):

PowerShell:

```powershell
scripts\savh.ps1 start -Reload
scripts\savh.ps1 status
scripts\savh.ps1 logs
scripts\savh.ps1 stop
```

CMD:

```bat
scripts\savh.cmd start -Reload
scripts\savh.cmd status
scripts\savh.cmd logs
scripts\savh.cmd stop
```

Nota: `scripts/savh.sh` queda como legacy para entornos Linux/WSL (no soportado).

Web:

- `http://$HOST:$PORT/`

---

### API (útil para debug)

- `GET /` → UI
- `GET /health` → healthcheck
- `POST /api/jobs/generate` → encola generación (shipping list / guides / both)
  - body:
    - `{"what":"guides"}` o `{"what":"shipping_list"}` o `{"what":"both"}`
    - opcional: `day` (`YYYY-MM-DD`)
- `POST /api/print-upload` → sube PDF, lo deja `READY` para imprimir
- `GET /api/jobs/{id}` → inspecciona estado/payload/error del job

Ejemplo:

```bash
curl -sS -X POST "http://$HOST:$PORT/api/jobs/generate" \
  -H 'content-type: application/json' \
  -d '{"what":"both","day":"2026-02-17"}' | jq
```

---

### Flujo completo (end-to-end)

1) Web/UI encola job en `printing.print_jobs`
2) `generate_worker` reclama `PENDING shipping_docs` → genera PDFs → job `READY` con `payload.files`
3) `print_worker` reclama `READY` → imprime cada PDF → job `DONE` (o `ERROR`)

Para “Subir PDF”, el endpoint deja el job directamente en `READY` y el `print_worker` lo imprime.

---

### Logs y monitoreo (sugerencias)

**Ver logs**

- `scripts\savh.ps1 logs` o `scripts\savh.cmd logs` (últimos logs)
- Mejor UX: abrir `data/logs/*.log` con tu viewer favorito (por ej. `lnav` o Notepad++)

**Monitoreo “simple”**

- Healthcheck: `GET /health`
- DB: mirar `printing.print_jobs` (jobs `ERROR` + `error_msg`)

**Monitoreo “serio” (Windows)**

**A) Correr como servicios (NSSM)**

Objetivo: que API + workers queden “siempre arriba”, con restart automático y logs persistentes.

1) Instala NSSM y crea 3 servicios apuntando al repo (el *Startup directory* debe ser la carpeta del proyecto para que encuentre `.env`).

2) Servicio API:

- *Application*: `poetry` (o ruta completa a `poetry.exe` si NSSM no hereda tu PATH)
- *Arguments*: `run uvicorn print_server.app.main:app --host 127.0.0.1 --port 8000`
- *Startup directory*: ruta del repo (donde está `.env`)

3) Servicio worker generación:

- *Application*: `poetry` (o ruta completa a `poetry.exe`)
- *Arguments*: `run python -m create_prints_server.worker.generate_worker`
- *Startup directory*: ruta del repo

4) Servicio worker impresión:

- *Application*: `poetry` (o ruta completa a `poetry.exe`)
- *Arguments*: `run python -m print_server.worker.print_worker`
- *Startup directory*: ruta del repo

5) Configura logs con rotación (ejemplo, repite por servicio):

```bat
nssm set savh-api AppStdout C:\path\to\savh_print_app\data\logs\service_api.out.log
nssm set savh-api AppStderr C:\path\to\savh_print_app\data\logs\service_api.err.log
nssm set savh-api AppRotateFiles 1
nssm set savh-api AppRotateBytes 10485760
```

Script listo:

- `scripts/windows/nssm_install.bat` (edita `REPO_DIR` y `POETRY_EXE`, luego ejecútalo como Admin)

**B) Métricas Prometheus + Grafana**

Ya está implementado el hook, pero es opcional:

1) Instala la dependencia:

```bash
poetry add prometheus-fastapi-instrumentator
```

2) Habilita en `.env`:

```env
ENABLE_METRICS=true
METRICS_PATH=/metrics
```

3) Levanta Prometheus + Grafana (Docker Desktop):

```bash
docker compose -f monitoring/docker-compose.yml up -d
```

4) URLs:

- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (admin/admin)

Prometheus hace scrape a `host.docker.internal:8000` por defecto (ver `monitoring/prometheus.yml`).

**C) Sentry para errores (API + workers)**

Ya está implementado el hook, pero es opcional:

1) Instala la dependencia:

```bash
poetry add sentry-sdk
```

2) Configura en `.env` (mínimo):

```env
SENTRY_DSN=TU_DSN
SENTRY_ENVIRONMENT=prod
```

3) (Opcional) Tracing/performance:

```env
SENTRY_TRACES_SAMPLE_RATE=0.05
SENTRY_PROFILES_SAMPLE_RATE=0
```

---

### Estructura de carpetas

- `src/print_server/` → UI + endpoints (upload/consulta jobs) + impresión
- `src/create_prints_server/` → endpoints de generación + lógica de Google Sheets + render PDF
- `src/printing_queue/` → settings + db + modelos ORM de la cola
- `data/uploads/` → PDFs subidos
- `data/shipping_list/` y `data/guides/` → PDFs generados
- `data/logs/` → logs (script)
