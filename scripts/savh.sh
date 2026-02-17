#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LOG_DIR="${LOG_DIR:-data/logs}"
PID_DIR="${PID_DIR:-data/pids}"

APP_PID_FILE="$PID_DIR/app.pid"
GEN_PID_FILE="$PID_DIR/generate_worker.pid"
PRINT_PID_FILE="$PID_DIR/print_worker.pid"

HOST_DEFAULT="127.0.0.1"
PORT_DEFAULT="8000"

usage() {
  cat <<'USAGE'
Uso:
  scripts/savh.sh start [--reload]
  scripts/savh.sh stop
  scripts/savh.sh status
  scripts/savh.sh logs

Notas:
  - Guarda logs en data/logs con timestamp de inicio.
  - Guarda PIDs en data/pids para poder detenerlos.
USAGE
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: falta comando requerido: $1" >&2
    exit 1
  fi
}

is_running_pidfile() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] || return 1
  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" >/dev/null 2>&1
}

start_one() {
  local name="$1"
  local pid_file="$2"
  local log_file="$3"
  shift 3

  if is_running_pidfile "$pid_file"; then
    echo "OK: $name ya está corriendo (pid=$(cat "$pid_file"))"
    return 0
  fi

  mkdir -p "$LOG_DIR" "$PID_DIR"

  # shellcheck disable=SC2091
  ( "$@" ) >>"$log_file" 2>&1 &
  local pid="$!"
  echo "$pid" >"$pid_file"
  echo "OK: $name iniciado pid=$pid log=$log_file"
}

stop_one() {
  local name="$1"
  local pid_file="$2"

  if ! [[ -f "$pid_file" ]]; then
    echo "OK: $name no tiene pidfile ($pid_file)"
    return 0
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [[ -z "$pid" ]]; then
    rm -f "$pid_file"
    echo "OK: $name pidfile vacío eliminado"
    return 0
  fi

  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
    for _ in {1..30}; do
      if kill -0 "$pid" >/dev/null 2>&1; then
        sleep 0.2
      else
        break
      fi
    done
    if kill -0 "$pid" >/dev/null 2>&1; then
      echo "WARN: $name sigue vivo; forzando kill -9 pid=$pid" >&2
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
    echo "OK: $name detenido pid=$pid"
  else
    echo "OK: $name no estaba corriendo (pid=$pid)"
  fi

  rm -f "$pid_file"
}

status_one() {
  local name="$1"
  local pid_file="$2"
  if is_running_pidfile "$pid_file"; then
    echo "RUNNING: $name pid=$(cat "$pid_file")"
  else
    echo "STOPPED: $name"
  fi
}

main() {
  local cmd="${1:-}"
  shift || true

  case "$cmd" in
    start)
      need_cmd poetry

      local reload_flag=""
      if [[ "${1:-}" == "--reload" ]]; then
        reload_flag="--reload"
        shift
      elif [[ -n "${1:-}" ]]; then
        echo "ERROR: flag no reconocida: $1" >&2
        usage
        exit 2
      fi

      local stamp
      stamp="$(date +"%Y%m%d_%H%M%S")"
      local host="${HOST:-$HOST_DEFAULT}"
      local port="${PORT:-$PORT_DEFAULT}"

      local app_log="$LOG_DIR/app_${stamp}.log"
      local gen_log="$LOG_DIR/worker_generate_${stamp}.log"
      local print_log="$LOG_DIR/worker_print_${stamp}.log"

      echo "Iniciando servicios (HOST=$host PORT=$port)..."
      start_one "api" "$APP_PID_FILE" "$app_log" poetry run uvicorn print_server.app.main:app --host "$host" --port "$port" $reload_flag
      start_one "generate_worker" "$GEN_PID_FILE" "$gen_log" poetry run python -m create_prints_server.worker.generate_worker
      start_one "print_worker" "$PRINT_PID_FILE" "$print_log" poetry run python -m print_server.worker.print_worker

      cat <<EOF

Logs:
  $app_log
  $gen_log
  $print_log

Tip:
  scripts/savh.sh logs
EOF
      ;;

    stop)
      stop_one "print_worker" "$PRINT_PID_FILE"
      stop_one "generate_worker" "$GEN_PID_FILE"
      stop_one "api" "$APP_PID_FILE"
      ;;

    status)
      status_one "api" "$APP_PID_FILE"
      status_one "generate_worker" "$GEN_PID_FILE"
      status_one "print_worker" "$PRINT_PID_FILE"
      ;;

    logs)
      mkdir -p "$LOG_DIR"
      local files
      files="$(ls -1t "$LOG_DIR"/*.log 2>/dev/null | head -n 6 || true)"
      if [[ -z "$files" ]]; then
        echo "No hay logs en $LOG_DIR"
        exit 0
      fi
      # tail soporta múltiples archivos y prefija con el nombre.
      # shellcheck disable=SC2086
      tail -n 200 -F $files
      ;;

    ""|-h|--help|help)
      usage
      ;;

    *)
      echo "ERROR: comando no reconocido: $cmd" >&2
      usage
      exit 2
      ;;
  esac
}

main "$@"

