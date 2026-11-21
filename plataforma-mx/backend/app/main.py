"""Aplicación FastAPI — Plataforma de análisis financiero y coberturas, mercado mexicano."""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import routes_calc, routes_data
from .core.db import init_db


def create_app(db_url: str | None = None) -> FastAPI:
    init_db(db_url)
    app = FastAPI(title="Plataforma MX — Análisis, valuación y coberturas", version="0.1.0",
                  description="Herramienta profesional de análisis e investigación. No ejecuta órdenes reales.")
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])
    app.include_router(routes_data.router)
    app.include_router(routes_calc.router)
    return app


app = create_app()
