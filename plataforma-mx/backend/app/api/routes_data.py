"""Rutas de datos: catálogo, precios, reconciliación, tasas, curvas, contratos, estados financieros."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.audit import to_jsonable
from ..core.db import (CatalogRevision, CurveSnapshot, Discrepancy, FinancialStatement, FuturesContract,
                       ImportBatch, Instrument, OptionContract, PriceRecord, RateObservation, get_session)
from ..core.provenance import PriceType
from ..engines import timeseries as tsx
from ..services import connectors, importers
from ..services.market_data import DataBlocked, get_instrument, load_ohlcv
from .common import df_rows
from .security import require_admin

router = APIRouter(prefix="/api")
TEMPLATES = Path(__file__).resolve().parents[2] / "data" / "templates"


@router.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@router.get("/sources/status")
def sources_status():
    return [connectors.check_source(n, timeout=5) for n in connectors.SOURCES]


@router.get("/templates")
def list_templates():
    return sorted(p.name for p in TEMPLATES.glob("*.csv"))


@router.get("/templates/{name}")
def get_template(name: str):
    p = TEMPLATES / name
    if not p.exists() or p.parent != TEMPLATES:
        raise HTTPException(404, "plantilla no encontrada")
    return FileResponse(p, filename=name, media_type="text/csv")


async def _read(file: UploadFile) -> bytes:
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(413, "archivo mayor a 50 MB")
    return content


def _wrap(fn):
    try:
        return fn()
    except ValueError as e:
        raise HTTPException(422, str(e))


# ------------------------------------------------------------------ catálogo

@router.post("/catalog/import", dependencies=[Depends(require_admin)])
async def catalog_import(file: UploadFile = File(...), source: str = Form(...), db: Session = Depends(get_session)):
    content = await _read(file)
    return _wrap(lambda: importers.import_catalog(db, content, file.filename, source))


@router.get("/catalog/connector")
def catalog_connector():
    return connectors.fetch_mexder_catalog()


@router.get("/catalog")
def catalog(active_only: bool = False, db: Session = Depends(get_session)):
    q = select(Instrument)
    if active_only:
        q = q.where(Instrument.active.is_(True))
    insts = list(db.scalars(q.order_by(Instrument.ticker, Instrument.series)))
    counts = dict(db.execute(select(PriceRecord.instrument_id, func.count()).group_by(PriceRecord.instrument_id)).all())
    fins = {t for (t,) in db.execute(select(FinancialStatement.ticker).distinct())}
    futs = {t for (t,) in db.execute(select(FuturesContract.underlying_ticker).distinct())}
    opts = {t for (t,) in db.execute(select(OptionContract.underlying_ticker).distinct())}
    open_d = dict(db.execute(select(Discrepancy.instrument_id, func.count()).where(Discrepancy.resolved.is_(False))
                             .group_by(Discrepancy.instrument_id)).all())
    rev = db.scalar(select(CatalogRevision).order_by(CatalogRevision.id.desc()))
    return {"revision": to_jsonable({"id": rev.id, "source": rev.source, "imported_at": rev.imported_at,
                                     "sha256": rev.file_sha256}) if rev else None,
            "instruments": [to_jsonable({
                "id": i.id, "issuer_name": i.issuer_name, "ticker": i.ticker, "series": i.series, "isin": i.isin,
                "yahoo_symbol": i.yahoo_symbol,
                "sector": i.sector, "exchange": i.exchange, "currency": i.currency, "derivatives": i.derivatives,
                "active": i.active, "catalog_source": i.catalog_source, "reviewed_on": i.reviewed_on,
                "availability": {"prices": counts.get(i.id, 0) > 0, "financials": i.ticker in fins,
                                 "futures_contracts": i.ticker in futs, "option_contracts": i.ticker in opts,
                                 "open_discrepancies": open_d.get(i.id, 0)}}) for i in insts]}


@router.get("/catalog/{ticker}/{series}/analyses")
def available_analyses(ticker: str, series: str, db: Session = Depends(get_session)):
    """Qué análisis pueden realizarse con los datos existentes y cuáles están pendientes."""
    inst = get_instrument(db, ticker, series)
    n_px = db.scalar(select(func.count()).select_from(PriceRecord).where(PriceRecord.instrument_id == inst.id,
                                                                         PriceRecord.field == "close")) or 0
    has_hl = db.scalar(select(func.count()).select_from(PriceRecord).where(PriceRecord.instrument_id == inst.id,
                                                                           PriceRecord.field == "high")) or 0
    fin = db.scalar(select(func.count()).select_from(FinancialStatement).where(FinancialStatement.ticker == inst.ticker)) or 0
    fut = db.scalar(select(func.count()).select_from(FuturesContract).where(FuturesContract.underlying_ticker == inst.ticker)) or 0
    opt = db.scalar(select(func.count()).select_from(OptionContract).where(OptionContract.underlying_ticker == inst.ticker)) or 0
    disc = db.scalar(select(func.count()).select_from(Discrepancy).where(Discrepancy.instrument_id == inst.id,
                                                                         Discrepancy.resolved.is_(False))) or 0

    def item(name, ok, need):
        return {"analysis": name, "available": bool(ok) and not disc, "requires": need,
                "blocked_by_discrepancies": bool(disc)}
    return [item("Históricos y rendimientos", n_px >= 2, "≥2 cierres"),
            item("Volatilidad, drawdown, VaR/ES", n_px >= 21, "≥21 cierres"),
            item("RSI / ROC", n_px >= 26, "≥26 cierres"),
            item("Williams %R / Estocástico / Chartismo", has_hl >= 20, "máximos y mínimos ≥20 sesiones"),
            item("Beta", n_px >= 30, "≥30 cierres del activo y del índice de referencia"),
            item("Estados financieros y ratios", fin > 0, "estados financieros importados"),
            item("DCF", True, "supuestos editables del usuario (estados financieros recomendados)"),
            item("Futuros listados", fut > 0, "especificaciones de contratos MexDer importadas"),
            item("Opciones listadas", opt > 0, "especificaciones de contratos MexDer importadas"),
            item("Opciones teóricas / escenarios", n_px >= 1, "precio spot verificado + supuestos de volatilidad")]


# ------------------------------------------------------------------ precios

@router.post("/prices/import", dependencies=[Depends(require_admin)])
async def prices_import(file: UploadFile = File(...), db: Session = Depends(get_session)):
    content = await _read(file)
    return _wrap(lambda: importers.import_prices(db, content, file.filename))


@router.get("/prices/{ticker}/{series}")
def prices(ticker: str, series: str, freq: str = "diaria", price_type: str = PriceType.OFFICIAL_CLOSE.value,
           start: date | None = None, end: date | None = None, db: Session = Depends(get_session)):
    try:
        inst = get_instrument(db, ticker, series)
        df, meta = load_ohlcv(db, inst, price_type, start, end)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except DataBlocked as e:
        raise HTTPException(409, str(e))
    if df.empty:
        return {"meta": to_jsonable(meta), "rows": []}
    out = tsx.resample_ohlcv(df, freq)
    out["ret_simple"] = tsx.simple_returns(out["close"])
    out["ret_log"] = tsx.log_returns(out["close"])
    out["ret_cum"] = tsx.cumulative_returns(out["close"])
    out["drawdown"] = tsx.drawdown(out["close"])
    meta.update({"frequency": freq, "volatility_annual": tsx.annualized_volatility(out["close"], freq)
                 if len(out) > 2 else None,
                 "max_drawdown": tsx.max_drawdown(out["close"]) if len(out) > 1 else None,
                 "all_time_high": float(df["high" if "high" in df else "close"].max()),
                 "all_time_low": float(df["low" if "low" in df else "close"].min()),
                 "aggregation": "apertura=primera, máximo=máx, mínimo=mín, cierre=último, volumen=suma; fecha=última sesión"})
    return {"meta": to_jsonable(meta), "rows": df_rows(out)}


@router.get("/discrepancies")
def discrepancies(only_open: bool = True, db: Session = Depends(get_session)):
    q = select(Discrepancy, Instrument).join(Instrument, Instrument.id == Discrepancy.instrument_id)
    if only_open:
        q = q.where(Discrepancy.resolved.is_(False))
    return [to_jsonable({"id": d.id, "ticker": i.ticker, "series": i.series, "date": d.market_date, "field": d.field,
                         "price_type": d.price_type, "reference": d.reference_value, "reference_source": d.reference_source,
                         "candidate": d.candidate_value, "candidate_source": d.candidate_source,
                         "resolved": d.resolved, "note": d.resolution_note}) for d, i in db.execute(q)]


@router.post("/discrepancies/{did}/resolve", dependencies=[Depends(require_admin)])
def resolve_discrepancy(did: int, note: str = Form(...), db: Session = Depends(get_session)):
    """Resolver = se documenta la decisión. El registro secundario discrepante queda excluido
    de los cálculos (estado 'discrepancia'); nunca se sobrescribe la cifra oficial."""
    d = db.get(Discrepancy, did)
    if not d:
        raise HTTPException(404, "no existe")
    if len(note.strip()) < 10:
        raise HTTPException(422, "documente la resolución (mín. 10 caracteres)")
    d.resolved, d.resolution_note = True, note.strip()
    db.commit()
    return {"resolved": did}


@router.get("/imports")
def imports(db: Session = Depends(get_session)):
    return [to_jsonable({"id": b.id, "kind": b.kind, "filename": b.filename, "sha256": b.file_sha256,
                         "imported_at": b.imported_at, "report": b.report})
            for b in db.scalars(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(100))]


# ------------------------------------------------------------------ tasas y curvas

@router.post("/rates/import", dependencies=[Depends(require_admin)])
async def rates_import(file: UploadFile = File(...), db: Session = Depends(get_session)):
    content = await _read(file)
    return _wrap(lambda: importers.import_rates(db, content, file.filename))


@router.post("/rates/banxico", dependencies=[Depends(require_admin)])
def rates_banxico(rate_code: str = Form(...), start: date = Form(...), end: date = Form(...),
                  db: Session = Depends(get_session)):
    res = connectors.fetch_banxico(rate_code, start, end)
    if res["status"] != "ok":
        return res
    import io
    import pandas as pd
    buf = io.BytesIO()
    pd.DataFrame(res["rows"]).to_csv(buf, index=False)
    return {"status": "ok", "series": res["series"], **importers.import_rates(db, buf.getvalue(), "banxico.csv")}


@router.get("/rates")
def rates_list(db: Session = Depends(get_session)):
    rows = db.execute(select(RateObservation.rate_code, RateObservation.rate_name, func.min(RateObservation.market_date),
                             func.max(RateObservation.market_date), func.count())
                      .group_by(RateObservation.rate_code, RateObservation.rate_name)).all()
    return [to_jsonable({"rate_code": r[0], "rate_name": r[1], "first": r[2], "last": r[3], "observations": r[4]})
            for r in rows]


@router.get("/rates/{code}")
def rate_series(code: str, start: date | None = None, end: date | None = None, db: Session = Depends(get_session)):
    q = select(RateObservation).where(RateObservation.rate_code == code)
    if start:
        q = q.where(RateObservation.market_date >= start)
    if end:
        q = q.where(RateObservation.market_date <= end)
    rows = list(db.scalars(q.order_by(RateObservation.market_date)))
    return [to_jsonable({"date": r.market_date, "value_pct": r.value_raw, "tenor": r.tenor, "convention": r.convention,
                         "source": r.source, "retrieved_at": r.retrieved_at, "origin": r.origin,
                         "validation": r.validation}) for r in rows]


@router.post("/curves/import", dependencies=[Depends(require_admin)])
async def curves_import(file: UploadFile = File(...), name: str = Form(...), curve_date: date = Form(...),
                        quote_kind: str = Form("zero_rate_pct"), compounding: str = Form("continua"),
                        day_count: str = Form("ACT/360"), interpolation: str = Form("log_linear_df"),
                        source: str = Form(...), origin: str = Form(...), db: Session = Depends(get_session)):
    content = await _read(file)
    return _wrap(lambda: importers.import_curve(db, content, file.filename, name, curve_date, quote_kind, compounding,
                                                day_count, interpolation, source, origin))


@router.get("/curves")
def curves(db: Session = Depends(get_session)):
    return [to_jsonable({"id": c.id, "name": c.name, "curve_date": c.curve_date, "source": c.source, "origin": c.origin,
                         "nodes": len(c.points), "compounding": c.compounding, "interpolation": c.interpolation})
            for c in db.scalars(select(CurveSnapshot).order_by(CurveSnapshot.id.desc()))]


def load_curve(db: Session, curve_id: int):
    from ..engines.rates.curve import ZeroCurve
    c = db.get(CurveSnapshot, curve_id)
    if not c:
        raise HTTPException(404, "curva no encontrada")
    return ZeroCurve.from_points(c.curve_date, c.points, c.quote_kind, c.compounding, c.day_count,
                                 interpolation=c.interpolation, name=c.name, source=c.source, origin=c.origin)


@router.get("/curves/{curve_id}")
def curve_detail(curve_id: int, db: Session = Depends(get_session)):
    from datetime import timedelta
    curve = load_curve(db, curve_id)
    fwd = []
    d0 = curve.curve_date
    for k in range(int(curve.times[-1] * 365 / 28)):
        a, b = d0 + timedelta(days=28 * k), d0 + timedelta(days=28 * (k + 1))
        fwd.append({"start": a, "end": b, "forward_simple_act360": curve.forward_simple(a, b)})
    return to_jsonable({"name": curve.name, "date": curve.curve_date, "source": curve.source, "origin": curve.origin,
                        "interpolation": curve.interpolation, "nodes": curve.table(), "forwards_28d": fwd,
                        "note": "Forwards derivadas de los nodos importados con la interpolación indicada; "
                                "fuera del último nodo no se extrapola."})


# ------------------------------------------------------------------ contratos y estados financieros

@router.post("/futures/contracts/import", dependencies=[Depends(require_admin)])
async def fut_import(file: UploadFile = File(...), db: Session = Depends(get_session)):
    content = await _read(file)
    return _wrap(lambda: importers.import_futures_contracts(db, content, file.filename))


@router.get("/futures/contracts")
def fut_list(underlying: str | None = None, db: Session = Depends(get_session)):
    q = select(FuturesContract)
    if underlying:
        q = q.where(FuturesContract.underlying_ticker == underlying.upper())
    return [to_jsonable({c.name: getattr(f, c.name) for c in FuturesContract.__table__.columns})
            for f in db.scalars(q.order_by(FuturesContract.expiry))]


@router.post("/options/contracts/import", dependencies=[Depends(require_admin)])
async def opt_import(file: UploadFile = File(...), db: Session = Depends(get_session)):
    content = await _read(file)
    return _wrap(lambda: importers.import_option_contracts(db, content, file.filename))


@router.get("/options/contracts")
def opt_list(underlying: str | None = None, db: Session = Depends(get_session)):
    q = select(OptionContract)
    if underlying:
        q = q.where(OptionContract.underlying_ticker == underlying.upper())
    return [to_jsonable({c.name: getattr(f, c.name) for c in OptionContract.__table__.columns})
            for f in db.scalars(q.order_by(OptionContract.expiry, OptionContract.strike))]


@router.post("/financials/import", dependencies=[Depends(require_admin)])
async def fin_import(file: UploadFile = File(...), db: Session = Depends(get_session)):
    content = await _read(file)
    return _wrap(lambda: importers.import_financials(db, content, file.filename))


@router.get("/financials/{ticker}")
def fin_get(ticker: str, period_type: str | None = None, db: Session = Depends(get_session)):
    q = select(FinancialStatement).where(FinancialStatement.ticker == ticker.upper())
    if period_type:
        q = q.where(FinancialStatement.period_type == period_type.upper())
    return [to_jsonable({"statement": f.statement, "period_type": f.period_type, "period_end": f.period_end,
                         "basis": f.basis, "currency": f.currency, "units": f.units, "items": f.items,
                         "source": f.source, "retrieved_at": f.retrieved_at})
            for f in db.scalars(q.order_by(FinancialStatement.period_end))]


# ------------------------------------------------------------------ Yahoo Finance (fuente de referencia designada)

from pydantic import BaseModel  # noqa: E402

from ..services import yahoo  # noqa: E402


class YahooReq(BaseModel):
    ticker: str
    series: str
    start: date | None = None
    end: date | None = None
    period: str | None = None
    yahoo_symbol: str | None = None
    quarterly: bool = False


def _yahoo_symbol(db, req) -> str | None:
    if req.yahoo_symbol:
        return req.yahoo_symbol
    inst = db.scalar(select(Instrument).where(Instrument.ticker == req.ticker.upper(),
                                              Instrument.series == req.series.upper()))
    if inst is None:
        raise HTTPException(404, f"{req.ticker} {req.series} no está en el catálogo")
    return inst.yahoo_symbol


@router.get("/yahoo/status")
def yahoo_status():
    return connectors.check_yahoo()


@router.post("/yahoo/prices", dependencies=[Depends(require_admin)])
def yahoo_prices(req: YahooReq, db: Session = Depends(get_session)):
    res = yahoo.fetch_prices(req.ticker.upper(), req.series.upper(), req.start, req.end, _yahoo_symbol(db, req), req.period)
    if res["status"] != "ok":
        return res
    if not res["rows"]:
        return {"status": "ok", "symbol": res["symbol"], "accepted_rows": 0, "rejected": res["pre_rejected"]}
    imp = _wrap(lambda: importers.import_prices(db, yahoo.rows_to_csv(res["rows"]), f"yahoo_{res['symbol']}.csv"))
    imp["rejected"] = res["pre_rejected"] + imp["rejected"]
    return {"status": "ok", "symbol": res["symbol"], "currency": res["currency"], **imp}


@router.post("/yahoo/financials", dependencies=[Depends(require_admin)])
def yahoo_financials(req: YahooReq, db: Session = Depends(get_session)):
    res = yahoo.fetch_financials(req.ticker.upper(), req.series.upper(), req.quarterly, _yahoo_symbol(db, req))
    if res["status"] != "ok":
        return res
    imp = _wrap(lambda: importers.import_financials(db, yahoo.rows_to_csv(res["rows"]), f"yahoo_fin_{res['symbol']}.csv"))
    return {"status": "ok", "symbol": res["symbol"], "currency": res["currency"],
            "missing_items": res["missing_items"], "notes": res["notes"], **imp}


@router.get("/yahoo/dividends/{ticker}/{series}")
def yahoo_dividends(ticker: str, series: str, yahoo_symbol: str | None = None, db: Session = Depends(get_session)):
    sym = yahoo_symbol or _yahoo_symbol(db, YahooReq(ticker=ticker, series=series))
    return yahoo.fetch_dividends(ticker.upper(), series.upper(), sym)


@router.post("/yahoo/refresh", dependencies=[Depends(require_admin)])
def yahoo_refresh(db: Session = Depends(get_session)):
    """Actualiza precios de todas las emisoras vigentes desde su último dato almacenado."""
    from datetime import timedelta
    out = []
    for inst in db.scalars(select(Instrument).where(Instrument.active.is_(True))):
        last = db.scalar(select(func.max(PriceRecord.market_date)).where(PriceRecord.instrument_id == inst.id))
        start = (last + timedelta(days=1)) if last else None
        res = yahoo.fetch_prices(inst.ticker, inst.series, start, None, inst.yahoo_symbol, None if start else "5y")
        if res["status"] != "ok":
            if last is not None and "no devolvió observaciones" in res.get("reason", ""):
                out.append({"ticker": inst.ticker, "series": inst.series, "symbol": res["symbol"], "status": "al_dia",
                            "accepted_rows": 0, "last_date": last.isoformat()})
            else:
                out.append({"ticker": inst.ticker, "series": inst.series, **res})
            continue
        imp = importers.import_prices(db, yahoo.rows_to_csv(res["rows"]), f"yahoo_{res['symbol']}.csv") if res["rows"] \
            else {"accepted_rows": 0, "rejected": []}
        out.append({"ticker": inst.ticker, "series": inst.series, "symbol": res["symbol"],
                    "accepted_rows": imp["accepted_rows"], "rejected": len(res["pre_rejected"]) + len(imp["rejected"]),
                    "discrepancies": len(imp.get("discrepancies", []))})
    return out


# ------------------------------------------------------------------ Curva CETES (Banxico)

class CetesCurveReq(BaseModel):
    curve_date: date | None = None
    max_age_days: int = 10
    interpolation: str = "log_linear_df"


@router.post("/curves/banxico-cetes", dependencies=[Depends(require_admin)])
def curve_cetes(req: CetesCurveReq, db: Session = Depends(get_session)):
    """Curva cero desde los rendimientos de la subasta semanal de CETES (Banxico SIE).

    Nodos: 28, 91, 182 y 364 días; tasa de rendimiento simple ACT/360 publicada por Banxico.
    Para cada plazo se toma la última subasta con fecha ≤ fecha de la curva; si alguna es más
    antigua que `max_age_days`, la curva NO se construye. Cobertura máxima: 364 días."""
    from datetime import timedelta
    import io
    import pandas as pd

    cd = req.curve_date or date.today()
    nodes, used = [], []
    for code, days in connectors.CETES_TENORS.items():
        res = connectors.fetch_banxico(code, cd - timedelta(days=40), cd)
        if res["status"] != "ok" or not res["rows"]:
            raise HTTPException(422, f"{code}: {res.get('reason', 'sin observaciones en las últimas semanas')}")
        last = max(res["rows"], key=lambda r: r["market_date"])
        obs_date = date.fromisoformat(last["market_date"])
        if (cd - obs_date).days > req.max_age_days:
            raise HTTPException(422, f"{code}: última subasta {obs_date} con más de {req.max_age_days} días de antigüedad")
        nodes.append({"days": days, "value": float(last["value_pct"]) / 100})
        used.append({"tenor": code, "series": res["series"], "auction_date": obs_date.isoformat(), "yield_pct": last["value_pct"]})
    buf = io.BytesIO()
    pd.DataFrame(nodes).to_csv(buf, index=False)
    source = "Banxico SIE · subasta semanal de CETES · " + "; ".join(f"{u['tenor']} {u['yield_pct']}% ({u['auction_date']})" for u in used)
    res = _wrap(lambda: importers.import_curve(db, buf.getvalue(), "cetes.csv", f"CETES Banxico {cd}", cd, "zero_rate",
                                               "simple", "ACT/360", req.interpolation, source, "observado_fuente_oficial"))
    return {**res, "auctions": used,
            "notes": ["Rendimientos de subasta primaria (no curva de mercado secundario).",
                      "Las fechas de subasta pueden diferir entre plazos; se reporta cada una.",
                      "Cobertura hasta 364 días: los pagos posteriores quedarían fuera de la curva y se advierten."]}


# ------------------------------------------------------------------ Boletines diarios de MexDer

@router.post("/mexder/bulletin", dependencies=[Depends(require_admin)])
async def mexder_bulletin(file: UploadFile = File(...), db: Session = Depends(get_session)):
    from ..services import mexder_bulletins
    content = await _read(file)
    return _wrap(lambda: mexder_bulletins.import_bulletin(db, content, file.filename))


@router.post("/mexder/aims", dependencies=[Depends(require_admin)])
async def mexder_aims(file: UploadFile = File(...), db: Session = Depends(get_session)):
    from ..services import mexder_margins
    content = await _read(file)
    return _wrap(lambda: mexder_margins.import_aims(db, content, file.filename))


# ------------------------------------------------------------------ Fundamentales en lote (Yahoo)

def _store_actions(db, inst, res) -> int:
    from ..core.db import CorporateAction
    n = 0
    for r in res["rows"]:
        exists = db.scalar(select(CorporateAction).where(
            CorporateAction.ticker == inst.ticker, CorporateAction.series == inst.series, CorporateAction.kind == r["kind"],
            CorporateAction.ex_date == r["ex_date"], CorporateAction.source_key == "yahoo"))
        if exists:
            continue
        db.add(CorporateAction(ticker=inst.ticker, series=inst.series, kind=r["kind"], ex_date=r["ex_date"],
                               value=r["value"], currency=r["currency"], source=res["source"], source_key="yahoo"))
        n += 1
    db.commit()
    return n


@router.post("/yahoo/actions", dependencies=[Depends(require_admin)])
def yahoo_actions(req: YahooReq, db: Session = Depends(get_session)):
    inst = get_instrument(db, req.ticker, req.series)
    res = yahoo.fetch_actions(inst.ticker, inst.series, req.yahoo_symbol or inst.yahoo_symbol)
    if res["status"] != "ok":
        return res
    return {"status": "ok", "symbol": res["symbol"], "added": _store_actions(db, inst, res), "total": len(res["rows"])}


@router.get("/actions/{ticker}/{series}")
def actions_list(ticker: str, series: str, db: Session = Depends(get_session)):
    from ..core.db import CorporateAction
    rows = db.scalars(select(CorporateAction).where(CorporateAction.ticker == ticker.upper(),
                                                    CorporateAction.series == series.upper())
                      .order_by(CorporateAction.ex_date.desc()))
    return [to_jsonable({"kind": r.kind, "ex_date": r.ex_date, "value": r.value, "currency": r.currency,
                         "source": r.source}) for r in rows]


@router.post("/yahoo/fundamentals-all", dependencies=[Depends(require_admin)])
def yahoo_fundamentals_all(db: Session = Depends(get_session)):
    """Estados financieros (anuales y trimestrales), dividendos y splits de todas las emisoras vigentes.
    Los índices no tienen estados financieros y se omiten."""
    out = []
    for inst in db.scalars(select(Instrument).where(Instrument.active.is_(True)).order_by(Instrument.ticker)):
        row = {"ticker": inst.ticker, "series": inst.series}
        if (inst.sector or "").startswith("Índice"):
            row["skipped"] = "índice: sin estados financieros"
            out.append(row)
            continue
        for q in (False, True):
            res = yahoo.fetch_financials(inst.ticker, inst.series, q, inst.yahoo_symbol)
            key = "trimestral" if q else "anual"
            if res["status"] != "ok":
                row[key] = f"no disponible: {res['reason']}"
                continue
            imp = importers.import_financials(db, yahoo.rows_to_csv(res["rows"]), f"yahoo_fin_{res['symbol']}.csv")
            row[key] = {"estados": imp["statements"], "moneda": res["currency"], "rechazados": len(imp["rejected"]),
                        "partidas_no_publicadas": res["missing_items"]}
        act = yahoo.fetch_actions(inst.ticker, inst.series, inst.yahoo_symbol)
        if act["status"] == "ok":
            row["eventos"] = {"nuevos": _store_actions(db, inst, act),
                              "dividendos": sum(r["kind"] == "dividendo" for r in act["rows"]),
                              "splits": sum(r["kind"] == "split" for r in act["rows"])}
        else:
            row["eventos"] = f"no disponible: {act['reason']}"
        out.append(row)
    return out


class GovCurveReq(BaseModel):
    curve_date: date | None = None
    include_30y: bool = False
    cetes_max_age_days: int = 10
    bonds_max_age_days: int = 60
    interpolation: str = "log_linear_df"


@router.post("/curves/banxico-gov", dependencies=[Depends(require_admin)])
def curve_gov(req: GovCurveReq, db: Session = Depends(get_session)):
    """Curva cero gubernamental hasta 30 años: CETES 28-364 días + Bonos M 3-30 años (subastas de Banxico),
    con bootstrapping de tasas par. Rechaza la construcción si alguna subasta excede la antigüedad máxima."""
    import io
    from datetime import timedelta

    import pandas as pd

    from ..engines.rates.curve import bootstrap_government_curve, forward_diagnostics

    cd = req.curve_date or date.today()
    used, cetes, bonds = [], [], []
    for code, days in connectors.CETES_TENORS.items():
        res = connectors.fetch_banxico(code, cd - timedelta(days=40), cd)
        if res["status"] != "ok" or not res["rows"]:
            raise HTTPException(422, f"{code}: {res.get('reason', 'sin observaciones recientes')}")
        last = max(res["rows"], key=lambda r: r["market_date"])
        od = date.fromisoformat(last["market_date"])
        if (cd - od).days > req.cetes_max_age_days:
            raise HTTPException(422, f"{code}: última subasta {od} excede {req.cetes_max_age_days} días")
        cetes.append((days, float(last["value_pct"]) / 100))
        used.append({"tenor": code, "series": res["series"], "auction_date": od.isoformat(), "yield_pct": last["value_pct"]})
    for code, years in connectors.BONO_M_TENORS.items():
        if years == 30 and not req.include_30y:
            continue
        res = connectors.fetch_banxico(code, cd - timedelta(days=req.bonds_max_age_days + 10), cd)
        if res["status"] != "ok" or not res["rows"]:
            raise HTTPException(422, f"{code}: {res.get('reason', 'sin subasta en la ventana permitida')}")
        last = max(res["rows"], key=lambda r: r["market_date"])
        od = date.fromisoformat(last["market_date"])
        if (cd - od).days > req.bonds_max_age_days:
            raise HTTPException(422, f"{code}: última subasta {od} excede {req.bonds_max_age_days} días")
        bonds.append((years, float(last["value_pct"]) / 100))
        used.append({"tenor": code, "series": res["series"], "auction_date": od.isoformat(), "yield_pct": last["value_pct"]})
    try:
        nodes = bootstrap_government_curve(cetes, bonds)
    except ValueError as e:
        raise HTTPException(422, str(e))
    buf = io.BytesIO()
    pd.DataFrame(nodes).to_csv(buf, index=False)
    source = ("Banxico SIE · subastas de CETES y Bonos M · bootstrapping de tasas par (plataforma) · "
              + "; ".join(f"{u['tenor']} {u['yield_pct']}% ({u['auction_date']})" for u in used))
    res = _wrap(lambda: importers.import_curve(db, buf.getvalue(), "gov.csv", f"Gubernamental Banxico {cd}", cd,
                                               "discount_factor", "continua", "ACT/365F", req.interpolation, source,
                                               "observado_fuente_oficial"))
    diag = forward_diagnostics(nodes)
    warnings = []
    if diag["flagged"]:
        f0 = diag["flagged"][0]
        warnings.append(f"Forwards inestables desde {f0['from_days'] // 365} años (máx. {diag['max_forward']:.2%}): el tramo "
                        "largo del bootstrapping con tasas par no es confiable; úselo con cautela.")
    return {**res, "auctions": used, "warnings": warnings,
            "forward_check": {"max_forward": diag["max_forward"], "flagged_segments": len(diag["flagged"])},
            "notes": ["Insumos oficiales (subastas primarias de Banxico); la curva cero es un cálculo de la plataforma.",
                      "Por omisión la curva llega a 20 años; el nodo de 30 años es opcional (include_30y) porque, con tasas "
                      "par cercanas al 10 %, amplifica las forwards del tramo largo.",
                      "Rendimientos de Bonos M tratados como tasas par con cupón semestral de 182 días; plazo nominal de cada subasta.",
                      "Las fechas de subasta difieren entre plazos; se reporta cada una."]}
