## SAVH Print App (dev notes)

Monolito modular en Python que:

- expone una **web** (FastAPI) para solicitar generación/impresión
- usa una **BD PostgreSQL** como cola (`printing.print_jobs`)
- corre 2 **workers**:
  - `generate_worker`: lee Google Sheets y genera PDFs
  - `print_worker`: imprime PDFs en Windows usando SumatraPDF

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

Este repo **requiere** un `.env` para funcionar. Hay un ejemplo en `.env.example`.

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

- Si corres en Windows “nativo”, puedes usar un `.env` con paths Windows (ver `.env_windows` como referencia local).
- Si corres en Linux/WSL, usa paths Linux (ej. `/mnt/c/...`), porque `Path("C:\\...")` no existe en Linux.

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

### Instalación

```bash
poetry install
cp .env.example .env
```

Completa `.env` con tus valores.

---

### Correr (API + workers) con logs

Script recomendado (crea logs en `data/logs/` y pids en `data/pids/`):

```bash
scripts/savh.sh start --reload
```

En Windows (PowerShell / CMD):

```bat
scripts\windows\savh.cmd start -Reload
scripts\windows\savh.cmd status
scripts\windows\savh.cmd logs
scripts\windows\savh.cmd stop
```

Otros comandos:

```bash
scripts/savh.sh status
scripts/savh.sh logs
scripts/savh.sh stop
```

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

- `scripts/savh.sh logs` (tail de los últimos logs generados)
- Mejor UX: instalar `lnav` y abrir `data/logs/*.log`

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

### Probar primero en WSL (simil “serio”)

La forma más rápida de probar en WSL es correr todo “a mano” y ver logs con `lnav`/`tail`. Luego, si quieres “servicios”, usa systemd.

**A) Run manual (rápido)**

1) Instala deps:

```bash
poetry install
```

2) Ten Postgres corriendo y ejecuta el init (si aplica):

```bash
psql "${DATABASE_URL/+psycopg/}" -f scripts/init_db.sql
```

3) Levanta API + workers con el script (logs en `data/logs/`):

```bash
scripts/savh.sh start --reload
scripts/savh.sh logs
```

**B) Systemd en WSL (servicios)**

1) Copia units y ajusta paths:

- `scripts/wsl/systemd/savh-api.service`
- `scripts/wsl/systemd/savh-worker-generate.service`
- `scripts/wsl/systemd/savh-worker-print.service`

En cada archivo cambia:

- `WorkingDirectory=/path/to/savh_print_app`
- `EnvironmentFile=/path/to/savh_print_app/.env`

2) Instala units:

```bash
sudo cp scripts/wsl/systemd/savh-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now savh-api savh-worker-generate savh-worker-print
```

3) Ver estado/logs:

```bash
systemctl status savh-api
journalctl -u savh-api -f
```

Notas:

- Para que systemd funcione en WSL, debes tenerlo habilitado (según tu versión/configuración de WSL).
- `print_worker` en WSL solo sirve si tu `.env` apunta a un `SUMATRA_PATH` que exista desde WSL (por ejemplo `/mnt/c/Program Files/SumatraPDF/SumatraPDF.exe`) y una impresora válida.

---

### Estructura de carpetas

- `src/print_server/` → UI + endpoints (upload/consulta jobs) + impresión
- `src/create_prints_server/` → endpoints de generación + lógica de Google Sheets + render PDF
- `src/printing_queue/` → settings + db + modelos ORM de la cola
- `data/uploads/` → PDFs subidos
- `data/shipping_list/` y `data/guides/` → PDFs generados
- `data/logs/` → logs (script)
