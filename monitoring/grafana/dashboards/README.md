# Dashboards (Grafana)

Guarda aquí los dashboards exportados en formato JSON para poder transportarlos a otro PC.

## Exportar desde Grafana

1) Abre el dashboard en Grafana.
2) **Share** → **Export** → **Save to file** (o copia el JSON).
3) Guarda el archivo `.json` en esta carpeta (por ejemplo: `savh-dashboard.json`).

## Cargar automáticamente (provisioning)

El `docker-compose` monta esta carpeta en el contenedor y Grafana carga automáticamente los JSON al iniciar.

## Datasources (Prometheus + PostgreSQL)

Se provisionan automáticamente:

- `prometheus` (default) → `http://prometheus:9090`
- `grafana-postgresql-datasource` → usa variables de entorno (ver `monitoring/docker-compose.yml`)

Levantar:

```bash
docker compose -f monitoring/docker-compose.yml up -d
```

Abrir:

- `http://localhost:3000` (admin/admin)
