# DEV

Guía de verificación local para validar la app antes de instalar o reiniciar servicios con NSSM.

## Alcance

- Este proyecto está pensado para Windows 10/11 nativo.
- WSL/Linux queda fuera del flujo soportado para pruebas locales de runtime.
- El objetivo de esta guía es probar la app como proceso normal, no como servicio.

Advertencia importante:

- Si ejecutas la app desde WSL con `DATABASE_URL=...@localhost:5432/...`, `localhost` apunta al loopback de WSL, no al PostgreSQL de Windows.
- Si tu PostgreSQL está corriendo en Windows y sólo escucha en `localhost`, el API y los workers fallarán con `connection refused` aunque pgAdmin en Windows funcione bien.
- Con la configuración por defecto de este repo, la forma correcta de probar es levantar la app desde PowerShell/CMD en Windows.
- Si insistes en ejecutar desde WSL, primero tendrías que reconfigurar PostgreSQL en Windows para aceptar conexiones externas y usar la IP/nombre del host Windows en `DATABASE_URL` y `BUSINESS_DATABASE_URL`, no `localhost`.

## Qué tiene que quedar OK antes de NSSM

Antes de pasar a `scripts/nssm_install.bat`, conviene validar estos puntos:

1. Dependencias Python instaladas y tests verdes.
2. La base de cola (`DATABASE_URL`) existe y tiene el schema `printing` y los enums requeridos.
3. El API responde `GET /health`.
4. `GET /api/egresos` responde correctamente con la fuente configurada.
5. `POST /api/jobs/generate` crea jobs y el `generate_worker` los mueve a `READY` o `DONE` según corresponda.
6. Los PDFs se generan físicamente en `data/shipping_list/` y `data/guides/`.
7. Si vas a validar impresión, el `print_worker` mueve jobs `READY` a `DONE` y SumatraPDF puede hablar con la impresora configurada.

## Pre-requisitos

- Windows con PowerShell.
- Python 3.10+.
- Poetry instalado.
- PostgreSQL accesible desde Windows.
- Si vas a probar impresión real:
  - SumatraPDF instalado.
  - `SUMATRA_PATH` correcto.
  - `PRINTER_NAME` idéntico al nombre real de la impresora en Windows.

## Setup inicial

Si todavía no lo hiciste, parte con esto:

```powershell
poetry config virtualenvs.in-project true
poetry install
Copy-Item .env.example.windows .env
```

Luego completa `.env`.

Notas:

- Para `DOCUMENTS_DATA_SOURCE=sheets`, revisa `GOOGLE_APPLICATION_CREDENTIALS`, `SHEETS_ID` y los nombres/rangos de hojas.
- Para `DOCUMENTS_DATA_SOURCE=postgres`, define también:

```env
DOCUMENTS_DATA_SOURCE=postgres
BUSINESS_DATABASE_URL=postgresql+psycopg://usuario:password@host:5432/bd_comercial
BUSINESS_DB_SCHEMA=core
DOCUMENTS_DISPATCH_SALE_TYPE=DESPACHO
DOCUMENTS_EGRESO_SALE_TYPE=EGRESO
```

## Inicialización de la base de cola

Esto es obligatorio al menos una vez por host/base.

Los modelos ORM usan `create_type=False`, así que la app no crea sola el schema `printing` ni los enums `print_job_type` / `print_job_status`. Eso viene en `scripts/init_db.sql`.

### Paso 1: crear la base si no existe

La base apuntada por `DATABASE_URL` debe existir antes de arrancar el API.

Ejemplo esperado:

```env
DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/savh_jobs_print
```

Si `savh_jobs_print` no existe, créala desde tu cliente SQL preferido.

### Paso 2: correr `scripts/init_db.sql`

Con `psql`:

```powershell
psql "postgresql://postgres:password@localhost:5432/savh_jobs_print" -f scripts/init_db.sql
```

Si no tienes `psql`, ejecuta el contenido de `scripts/init_db.sql` desde pgAdmin, DBeaver o el cliente SQL que uses.

### Paso 3: qué crea la app sola

Al arrancar, `Base.metadata.create_all(...)` crea la tabla `printing.print_jobs` y tablas auxiliares nuevas si faltan. Pero si no corriste antes `scripts/init_db.sql`, el arranque puede fallar por falta de schema/enums.

## Pruebas automáticas

El repo hoy trae tests de la parte de generación en `tests/create_prints_server/`.

Corre esto antes del smoke test manual:

```powershell
poetry run pytest tests/create_prints_server -q
```

Esto cubre principalmente:

- selección del provider (`sheets` vs `postgres`)
- integración del provider en generator/API
- transformación de datos necesaria para generar PDFs

No cubre impresión real ni el arranque de PowerShell/NSSM.

## Smoke test local sin NSSM

La forma más útil de probar antes de NSSM es levantar procesos normales y validar el flujo en vivo.

### Opción A: probar solo API + generación

Esta opción evita imprimir papel y sirve para validar fuente de datos, cola y generación de PDFs.

Abre dos terminales PowerShell en la raíz del repo.

Terminal 1, API:

```powershell
poetry run uvicorn print_server.app.main:app --host 127.0.0.1 --port 8000 --access-log --log-level info
```

Terminal 2, generate worker:

```powershell
poetry run python -u -m create_prints_server.worker.generate_worker
```

#### Check 1: healthcheck

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get
```

Esperado:

```json
{"status":"ok"}
```

#### Check 2: fuente de datos

Si la fuente es `sheets`:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/egresos?day=YYYY-MM-DD" -Method Get
```

Si la fuente es `postgres`, usa un día con ventas reales.

Consultas útiles para elegir día y validar aliases:

```sql
select tipo from core.dim_sale_types order by tipo;
select cast(fecha as date) as day, count(*) from core.sales group by 1 order by 1 desc limit 10;
```

Qué debería pasar:

- el endpoint responde `200`
- si hay egresos ese día, devuelve una lista con `venta_id`, `label`, `cliente`, `total`
- si no hay egresos, devuelve `[]`

#### Check 3: generación de PDFs

Encola un job de generación:

```powershell
$body = @{ what = "both"; day = "YYYY-MM-DD" } | ConvertTo-Json -Compress
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/jobs/generate" -Method Post -ContentType "application/json" -Body $body
```

Luego consulta el estado:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/jobs/ID" -Method Get
```

Esperado en esta opción:

- el job parte como `pending`
- el `generate_worker` lo toma
- el job termina en `ready`
- `payload.files` contiene rutas PDF

También valida que los archivos existan:

```powershell
Get-Item data\shipping_list\*.pdf
Get-Item data\guides\*.pdf
```

#### Check 4: egreso puntual

Si tienes un `venta_id` de egreso real, prueba además el camino puntual:

```powershell
$body = @{ what = "egreso"; day = "YYYY-MM-DD"; venta_id = "123" } | ConvertTo-Json -Compress
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/jobs/generate" -Method Post -ContentType "application/json" -Body $body
```

Esperado:

- el job termina en `ready`
- `payload.files` apunta a un PDF tipo `guides_egreso_YYYYMMDD.pdf`

### Opción B: flujo completo con impresión

Haz esto cuando ya validaste la opción A y quieras confirmar que la impresión real también funciona.

Abre una tercera terminal PowerShell:

```powershell
poetry run python -u -m print_server.worker.print_worker
```

Qué deberías ver:

- jobs `READY` pasan a `printing`
- luego quedan en `done`
- si falla Sumatra o la impresora, el job termina en `error` con `error_msg`

Puedes reutilizar los jobs generados en la opción A o encolar uno nuevo.

También puedes probar el endpoint de subida de PDF con un archivo descartable de una sola página:

```powershell
curl.exe -sS -X POST "http://127.0.0.1:8000/api/print-upload" -F "file=@C:\ruta\test.pdf;type=application/pdf"
```

Luego revisa el job con `GET /api/jobs/{id}`.

## Smoke test usando el script local del repo

Si quieres una prueba más parecida al uso diario, pero todavía sin NSSM, usa `scripts/savh.ps1`.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\savh.ps1 start -Reload
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\savh.ps1 status
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\savh.ps1 logs
```

Este script levanta:

- API
- `generate_worker`
- `print_worker`

Importante:

- esta opción ya incluye impresión real si llegan jobs `READY`
- úsala cuando realmente quieras validar el flujo completo
- para detener todo:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\savh.ps1 stop
```

## Logs y observabilidad mínima

Mientras haces pruebas, revisa:

- `data/logs/app_*.log`
- `data/logs/worker_generate_*.log`
- `data/logs/worker_print_*.log`
- `GET /api/jobs/{id}`
- tabla `printing.print_jobs`

Estados normales:

- `pending` -> `generating` -> `ready` -> `printing` -> `done`

También puede aparecer:

- `done` directamente desde `generate_worker` cuando no hay ventas para la fecha y se registra `orders_count = 0`
- `error` si falla conexión a fuente, render PDF, Sumatra, impresora o falta algún archivo

## Checklist de aprobación antes de NSSM

No pases a NSSM hasta que puedas marcar todo esto:

- `poetry run pytest tests/create_prints_server -q` pasa.
- `GET /health` responde `ok`.
- `GET /api/egresos` responde correctamente para la fuente configurada.
- un job `what=both` genera PDFs reales.
- un job `what=egreso` genera su guía puntual.
- la guía de despacho y la guía de egreso mantienen `3 por hoja` y el talón recortable inferior se ve legible al 100%.
- el talón recortable tiene espacio útil para escritura manual en `RECIBE CONFORME`, checkboxes de pago y línea de `MONTO`.
- si vas a imprimir en producción, al menos un job llega a `done` con `print_worker` real.
- no quedan errores en logs de arranque.
- `.env` final está validado en el mismo host Windows donde luego se instalará NSSM.

## Problemas frecuentes

### El API no arranca y falla con Postgres enums o schema

Probablemente faltó correr `scripts/init_db.sql` sobre la base de `DATABASE_URL`.

### El API no arranca con `connection refused` a `127.0.0.1:5432`

Si estás ejecutando `poetry run uvicorn ...` desde WSL, ese `127.0.0.1` es WSL, no Windows.

Qué significa:

- pgAdmin puede mostrar `savh_erp` y `savh_jobs_print` correctamente en Windows
- pero la app en WSL igual falla porque no está hablando con el mismo loopback

Solución recomendada:

- ejecuta API y workers desde PowerShell o CMD en Windows usando el mismo `.env`

Alternativa avanzada:

- reconfigura PostgreSQL en Windows para escuchar fuera de `localhost`
- abre el acceso en `pg_hba.conf`
- cambia `DATABASE_URL` y `BUSINESS_DATABASE_URL` para apuntar a la IP o hostname del host Windows

### `GET /api/egresos` devuelve vacío en `postgres`

Revisa:

- `BUSINESS_DATABASE_URL`
- `BUSINESS_DB_SCHEMA`
- `DOCUMENTS_DISPATCH_SALE_TYPE`
- `DOCUMENTS_EGRESO_SALE_TYPE`
- que el día consultado realmente tenga ventas

### Los jobs quedan en `ERROR` al imprimir

Revisa:

- `SUMATRA_PATH`
- `PRINTER_NAME`
- que el PDF exista físicamente
- stdout/stderr del `print_worker`

### Funciona manualmente, pero no debería asumirse que NSSM también funcionará

Manual y servicio no son el mismo runtime. Antes de NSSM, además de validar la app, conviene dejar lista la venv in-project con:

```powershell
poetry config virtualenvs.in-project true
poetry install
```

Eso deja el runtime esperado para `scripts/nssm_install.bat` en `.venv\Scripts\python.exe`.