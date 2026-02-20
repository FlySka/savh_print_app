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

**Configurar SumatraPDF (impresión)**

1) Instala SumatraPDF (versión clásica/installer) y deja la ruta, por ejemplo:
   `C:\Program Files\SumatraPDF\SumatraPDF.exe`
2) Define en `.env`:
   - `SUMATRA_PATH=C:\\Program Files\\SumatraPDF\\SumatraPDF.exe`
   - `PRINTER_NAME=Nombre de tu impresora` (tal como aparece en Panel de Control > Impresoras).
3) (Opcional) Prueba manual desde PowerShell para validar:
   ```powershell
   & "C:\Program Files\SumatraPDF\SumatraPDF.exe" -print-to "Nombre de tu impresora" -print-settings duplexdefault test.pdf
   ```
   Si imprime, el `print_worker` podrá hacerlo. Si falla, revisa ruta, nombre exacto de la impresora o drivers.

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
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\savh.ps1 start -Reload
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\savh.ps1 status
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\savh.ps1 logs
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\savh.ps1 stop
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

### Logs y monitoreo

**Ver logs**

- `scripts\savh.ps1 logs` taila simultáneamente los 3 servicios. Si no ves líneas, espera a que se emitan; corta con `Ctrl+C` antes de borrar archivos.
- Cada servicio escribe stdout+stderr al mismo archivo con timestamp:
  - API: `data/logs/app_YYYYMMDD_HHMMSS.log`
  - generate_worker: `data/logs/worker_generate_YYYYMMDD_HHMMSS.log`
  - print_worker: `data/logs/worker_print_YYYYMMDD_HHMMSS.log`
- `scripts\savh.ps1 stop` usa `taskkill /T` para matar árbol (incluye `uvicorn --reload` y watchfiles) y limpia pidfiles. Si un log no se deja borrar, cierra cualquier `savh.ps1 logs`, corre `stop` y reintenta.
- Mejor UX: abrir `data/logs/*.log` con tu viewer favorito (por ej. `lnav` o Notepad++).

**Monitoreo “simple”**

- Healthcheck: `GET /health`
- DB: mirar `printing.print_jobs` (jobs `ERROR` + `error_msg`)

**Monitoreo “serio” (Windows)**

**A) Correr como servicios (NSSM)**

Objetivo: que API + workers queden “siempre arriba”, con restart automático y logs persistentes.

1) Instala NSSM (manual):
   - Descarga: `https://nssm.cc/download`
   - Extrae `win64\nssm.exe` y cópialo a, por ejemplo, `C:\Tools\nssm\nssm.exe`
   - Agrega `C:\Tools\nssm` al `PATH` (o usa `set NSSM_EXE=C:\Tools\nssm\nssm.exe` antes de ejecutar el script).

2) Recomendado (para que el servicio no dependa de `poetry` en PATH): crear venv in-project:

```powershell
poetry config virtualenvs.in-project true
poetry install
```

Esto deja el runtime en `.\.venv\Scripts\python.exe` (más estable para servicios).
Sin `.venv`, el servicio suele fallar (especialmente si corre como `LocalSystem`) porque Poetry crea un venv vacío en `systemprofile`.

3) Crea 3 servicios apuntando al repo (el *Startup directory / AppDirectory* debe ser la carpeta del proyecto para que encuentre `.env`).

4) Servicio API (ejemplo en GUI de NSSM):

- *Application*: `C:\path\to\savh_print_app\.venv\Scripts\python.exe`
- *Arguments*: `-m uvicorn print_server.app.main:app --host 127.0.0.1 --port 8000`
- *Startup directory*: ruta del repo (donde está `.env`)

5) Servicio worker generación:

- *Application*: `C:\path\to\savh_print_app\.venv\Scripts\python.exe`
- *Arguments*: `-u -m create_prints_server.worker.generate_worker`
- *Startup directory*: ruta del repo

6) Servicio worker impresión:

- *Application*: `C:\path\to\savh_print_app\.venv\Scripts\python.exe`
- *Arguments*: `-u -m print_server.worker.print_worker`
- *Startup directory*: ruta del repo

7) Configura logs con rotación (ejemplo, repite por servicio):

```bat
nssm set savh-api AppStdout C:\path\to\savh_print_app\data\logs\service_api.out.log
nssm set savh-api AppStderr C:\path\to\savh_print_app\data\logs\service_api.err.log
nssm set savh-api AppRotateFiles 1
nssm set savh-api AppRotateBytes 10485760
```

Script listo:

- `scripts/nssm_install.bat install` (ejecuta como Admin; detecta el repo por la ubicación del script y usa `.venv` si existe)
- `scripts/nssm_install.bat uninstall` (remueve los 3 servicios)

Nota importante (credenciales/impresora):
- Si tu `.env` referencia paths dentro de tu perfil de usuario (por ejemplo `GOOGLE_APPLICATION_CREDENTIALS=C:\Users\...`), configura los servicios para “Log on as” tu usuario (en `services.msc` o `nssm edit <servicio>`). Si quedan como `LocalSystem`, normalmente no tienen acceso a esos archivos ni a recursos del usuario.

**B) Métricas Prometheus + Grafana**

El hook ya está en `printing_queue.infra.observability.instrument_fastapi_if_enabled` y la dependencia está en `pyproject.toml`. Solo actívalo:

1) Habilita en `.env`:

```env
ENABLE_METRICS=true
METRICS_PATH=/metrics
```

2) Levanta Prometheus + Grafana (Docker Desktop):

```bash
docker compose -f monitoring/docker-compose.yml up -d
```

3) URLs:

- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (admin/admin)

4) Prometheus ya scrapea `host.docker.internal:8000` (ver `monitoring/prometheus.yml`). Ajusta el puerto si cambias `PORT` en `.env`.
5) En Grafana, crea un datasource Prometheus apuntando a `http://prometheus:9090` (dentro del compose) y agrega dashboards para las métricas de FastAPI/Instrumentator expuestas en `/metrics`.

> Nota: además de las métricas del instrumentator, la app expone `http_requests_by_status_total` (labels `handler`, `method`, `status`) para poder graficar tasa de errores (4xx/5xx).

**C) Exponer por Tailscale (opcional)**

Objetivo: acceder a la API (`PORT=8000`) y Grafana (`3000`) desde tu tailnet sin abrir puertos públicos. Requiere Tailscale 1.38+ en Windows.

Pasos rápidos (PowerShell, en el host Windows):

```powershell
# 1) Asegura que la app escuche en la red del host
#    (en .env ya dejamos HOST=0.0.0.0)

# 2) Inicia los servicios de la app
scripts\savh.ps1 start

# 3) Publica los puertos internos con Serve (solo tailnet, TLS automático)
tailscale serve --bg --https=443  http://127.0.0.1:8000   # API
tailscale serve --bg --https=8443 http://127.0.0.1:3000   # Grafana

# 4) Verifica
tailscale serve status

# 5) (Opcional) Detener la exposición cuando no la uses
tailscale serve reset
```

Acceso desde otro dispositivo del tailnet (MagicDNS):
- API: `https://<tu-host>.ts.net/`
- Grafana: `https://<tu-host>.ts.net:8443/`

Notas:
- Serve y Funnel comparten puerto; si luego necesitas público, usa `tailscale funnel --bg 443` y/o `tailscale funnel --bg 8443` (requiere políticas con atributo `funnel`).
- Si cambias el puerto de la API, ajusta el backend en los comandos Serve y en `monitoring/prometheus.yml`.

**D) Sentry para errores (API + workers)**

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
