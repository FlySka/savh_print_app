from __future__ import annotations

from fastapi import FastAPI
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

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(print_server_router)
app.include_router(create_prints_router)

instrument_fastapi_if_enabled(app)
