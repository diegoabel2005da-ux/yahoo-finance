"""Aplicación FastAPI — Plataforma de análisis financiero y coberturas, mercado mexicano."""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import routes_calc, routes_data
from .core.db import init_db

SEED_STATE = {"local": "pendiente", "online": "no ejecutada", "log": [], "started_at": None, "finished_at": None}


def _log(msg: str) -> None:
    SEED_STATE["log"] = (SEED_STATE["log"] + [f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"])[-200:]


def _run_seed(online: bool) -> None:
    from .core import db as dbm
    from .seed import refresh_online, seed_local

    key = "online" if online else "local"
    SEED_STATE[key], SEED_STATE["started_at"] = "en curso", datetime.now(timezone.utc).isoformat()
    try:
        with dbm.SessionLocal() as db:
            seed_local(db, _log)
            if online:
                refresh_online(db, _log)
        SEED_STATE[key] = "completa"
    except Exception as e:  # se informa; no se ocultan fallas
        SEED_STATE[key] = f"error: {type(e).__name__}: {e}"
        _log(SEED_STATE[key])
    SEED_STATE["finished_at"] = datetime.now(timezone.utc).isoformat()


def build_app() -> FastAPI:
    app = FastAPI(title="Plataforma MX — Análisis, valuación y coberturas", version="0.1.0",
                  description="Herramienta profesional de análisis e investigación. No ejecuta órdenes reales.")
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])
    app.include_router(routes_data.router)
    app.include_router(routes_calc.router)

    @app.get("/api/seed/status")
    def seed_status():
        return SEED_STATE

    @app.post("/api/seed/refresh")
    def seed_refresh():
        if "en curso" in (SEED_STATE["local"], SEED_STATE["online"]):
            return {"status": "ya en curso", **SEED_STATE}
        threading.Thread(target=_run_seed, args=(True,), daemon=True).start()
        return {"status": "iniciada"}

    return app


def create_app(db_url: str | None = None) -> FastAPI:
    init_db(db_url)
    app = build_app()
    if db_url is None and os.environ.get("AUTO_SEED", "1") == "1":
        @app.on_event("startup")
        def _auto_seed():
            # Carga local (sin red) de los datos semilla del repositorio, en segundo plano.
            threading.Thread(target=_run_seed, args=(False,), daemon=True).start()
    return app


app = create_app()
