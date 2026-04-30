from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from create_prints_server.app.api import router as create_prints_router
from dotenv import load_dotenv
from printing_queue.db import engine
from printing_queue.infra.observability import init_sentry, instrument_fastapi_if_enabled
from printing_queue.models import Base
from print_server.app.api import router as print_server_router

load_dotenv()
init_sentry("api")
Base.metadata.create_all(bind=engine)

app = FastAPI(title="SAVH Print App")

ROOT_DIR = Path(__file__).resolve().parents[3]
STATIC_DIR = ROOT_DIR / "static"
FAVICON_PATH = STATIC_DIR / "images" / "favicon.ico"


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
	"""Entrega el favicon usado por la vista web."""
	return FileResponse(FAVICON_PATH)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(print_server_router)
app.include_router(create_prints_router)

instrument_fastapi_if_enabled(app)
