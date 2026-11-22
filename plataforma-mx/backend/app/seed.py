"""Carga de datos semilla del repositorio y actualización en línea.

Uso:
    python -m app.seed            # carga local: catálogo, boletines y AIM del repositorio (sin red)
    python -m app.seed --online   # además: precios y fundamentales (Yahoo), series de Banxico y curva gubernamental

Los archivos semilla viven en `backend/data/`:
    catalogs/mexder_catalogo_*.csv       (se usa el más reciente por nombre)
    seed/mexder/*Boletin_de_Futuros*.pdf (en orden cronológico por nombre)
    seed/mexder/*Boletin_de_Opciones*.pdf
    seed/mexder/AIMS_Unitarias_*.xls

Mientras no exista un archivo de AIM más reciente, las AIM de octubre de 2026 son la referencia vigente; se
muestran siempre con su periodo («Octubre 2026»), nunca como AIM de otro mes.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import func, select

DATA = Path(__file__).resolve().parents[1] / "data"
BANXICO_SERIES_TO_LOAD = ["FIX", "TIIE_28", "TIIE_91", "TIIE_182", "TIIE_FONDEO", "TASA_OBJETIVO", "CETES_28",
                          "CETES_91", "CETES_182", "CETES_364", "BONO_M_3A", "BONO_M_5A", "BONO_M_10A", "BONO_M_20A",
                          "BONO_M_30A"]


def seed_local(db, log=print) -> dict:
    """Catálogo, boletines y AIM del repositorio. Idempotente: reimportar no duplica datos."""
    from .core.db import Instrument
    from .services import importers, mexder_bulletins, mexder_margins

    out = {}
    cats = sorted((DATA / "catalogs").glob("mexder_catalogo_*.csv"))
    if cats and not db.scalar(select(func.count()).select_from(Instrument)):
        r = importers.import_catalog(db, cats[-1].read_bytes(), cats[-1].name,
                                     f"Catálogo semilla del repositorio · {cats[-1].name}")
        out["catalog"] = {"file": cats[-1].name, "accepted": r["accepted"]}
        log(f"catálogo: {r['accepted']} instrumentos ({cats[-1].name})")
    seed = DATA / "seed" / "mexder"
    bulletins = sorted(list(seed.glob("*Boletin_de_Futuros*.pdf")) + list(seed.glob("*Boletin_de_Opciones*.pdf")))
    out["bulletins"] = []
    for f in bulletins:
        r = mexder_bulletins.import_bulletin(db, f.read_bytes(), f.name)
        out["bulletins"].append({"file": f.name, "series": r["series_read"], "new_quotes": r["quotes_added"]})
        log(f"boletín {f.name}: {r['series_read']} series, {r['quotes_added']} cotizaciones nuevas")
    aims = sorted(seed.glob("AIMS_Unitarias_*.xls"))
    if aims:
        # el más reciente por periodo
        latest = max(aims, key=lambda p: mexder_margins.period_from_filename(p.name)[0])
        r = mexder_margins.import_aims(db, latest.read_bytes(), latest.name)
        out["aims"] = {"file": latest.name, "period": r["period"],
                       "futures_assigned": r.get("futures", {}).get("assigned"),
                       "options_assigned": r.get("options", {}).get("assigned")}
        log(f"AIM {latest.name} ({r['period']}): futuros {out['aims']['futures_assigned']}, "
            f"opciones {out['aims']['options_assigned']}")
    return out


def refresh_online(db, log=print) -> dict:
    """Actualización con red: Yahoo (precios, estados financieros, dividendos, splits), Banxico y curva."""
    from fastapi.testclient import TestClient  # reutiliza exactamente la lógica de los endpoints

    from .api import routes_calc, routes_data  # noqa: F401
    from .main import build_app

    app = build_app()
    c = TestClient(app)
    out = {}
    px = c.post("/api/yahoo/refresh").json()
    out["prices"] = {"new_sessions": sum(x.get("accepted_rows", 0) for x in px),
                     "unavailable": [x["ticker"] for x in px if x.get("status") == "no_disponible"]}
    log(f"precios: {out['prices']['new_sessions']} sesiones nuevas")
    fund = c.post("/api/yahoo/fundamentals-all").json()
    out["fundamentals"] = {"issuers": len(fund)}
    log(f"fundamentales: {len(fund)} emisoras")
    start = (date.today() - timedelta(days=730)).isoformat()
    out["banxico"] = {}
    for code in BANXICO_SERIES_TO_LOAD:
        r = c.post("/api/rates/banxico", data={"rate_code": code, "start": start, "end": date.today().isoformat()}).json()
        out["banxico"][code] = r.get("accepted", r.get("reason"))
    log(f"Banxico: {out['banxico']}")
    cv = c.post("/api/curves/banxico-gov", json={})
    out["gov_curve"] = cv.json().get("curve_id") if cv.status_code == 200 else cv.json().get("detail")
    log(f"curva gubernamental: {out['gov_curve']}")
    # Con precios ya cargados, se reimportan los boletines para verificar la escala de strikes por paridad.
    seed = DATA / "seed" / "mexder"
    from .services import mexder_bulletins
    for f in sorted(seed.glob("*Boletin_de_Opciones*.pdf")):
        mexder_bulletins.import_bulletin(db, f.read_bytes(), f.name)
    return out


def main(argv: list[str]) -> None:
    from .core.db import SessionLocal, init_db

    init_db()
    from .core import db as dbm

    with dbm.SessionLocal() as db:
        seed_local(db)
        if "--online" in argv:
            refresh_online(db)


if __name__ == "__main__":
    main(sys.argv[1:])
