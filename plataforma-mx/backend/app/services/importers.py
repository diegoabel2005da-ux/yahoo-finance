"""Importación validada de archivos CSV/Excel (sección 3).

Cada importador:
- exige columnas obligatorias de procedencia,
- valida renglón por renglón (los renglones inválidos se RECHAZAN, nunca se corrigen ni rellenan),
- registra el lote (hash SHA-256 del archivo, fuente, reporte),
- reconcilia contra referencias oficiales existentes y registra discrepancias.
"""
from __future__ import annotations

import hashlib
import io
from datetime import date, datetime, timezone
from decimal import Decimal

import pandas as pd
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import (CatalogRevision, CurveSnapshot, Discrepancy, FinancialStatement, FuturesContract,
                       ImportBatch, Instrument, OptionContract, PriceRecord, RateObservation)
from ..core.provenance import DataOrigin, Freshness, Observation, PriceType, ValidationStatus

CATALOG_COLUMNS = ["issuer_name", "ticker", "series", "exchange", "currency", "derivatives", "active",
                   "catalog_source", "reviewed_on"]
CATALOG_OPTIONAL = ["isin", "sector", "yahoo_symbol"]
PRICE_COLUMNS = ["ticker", "series", "identifier", "market", "source", "price_type", "market_date",
                 "retrieved_at", "currency", "precision", "freshness", "origin", "close"]
PRICE_OPTIONAL = ["open", "high", "low", "volume", "adj_close", "publication_date", "time", "timezone",
                  "data_version"]
RATE_COLUMNS = ["rate_code", "rate_name", "tenor", "market_date", "value_pct", "convention", "source",
                "retrieved_at", "origin"]
CURVE_COLUMNS = ["days", "value"]
FUT_COLUMNS = ["symbol", "underlying_ticker", "expiry", "multiplier", "tick_size", "tick_value", "currency",
               "settlement", "source", "reviewed_on"]
OPT_COLUMNS = ["symbol", "underlying_ticker", "option_type", "strike", "expiry", "multiplier", "style",
               "settlement", "currency", "source", "reviewed_on"]
FIN_COLUMNS = ["ticker", "statement", "period_type", "period_end", "basis", "currency", "units", "item",
               "value", "source", "retrieved_at"]

RECONCILE_TOLERANCE_UNITS = 0  # coincidencia exacta a la precisión publicada


def read_table(content: bytes, filename: str) -> pd.DataFrame:
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        df = pd.read_excel(io.BytesIO(content), dtype=str)
    elif name.endswith((".csv", ".txt")):
        df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False, na_values=[""])
    else:
        raise ValueError("formato no soportado: use CSV o Excel")
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _missing_cols(df, required):
    return [c for c in required if c not in df.columns]


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and v.strip() == "")


def _date(v) -> date:
    return pd.to_datetime(v, dayfirst=False).date()


def _dt(v) -> datetime:
    d = pd.to_datetime(v)
    if d.tzinfo is None:
        d = d.tz_localize("America/Mexico_City")
    return d.to_pydatetime()


# ----------------------------------------------------------------------- catálogo

def import_catalog(db: Session, content: bytes, filename: str, source: str) -> dict:
    """Importa el universo de subyacentes accionarios con derivados listados en MexDer.

    El archivo debe provenir de la publicación de MexDer (o equivalente autorizado). Cada
    renglón es una emisora+serie. Las emisoras ausentes en la nueva revisión se marcan como
    no vigentes (no se borran: se conserva la trazabilidad)."""
    df = read_table(content, filename)
    miss = _missing_cols(df, CATALOG_COLUMNS)
    if miss:
        raise ValueError(f"columnas obligatorias faltantes: {miss}")
    accepted, rejected = [], []
    seen = set()
    for i, row in df.iterrows():
        errs = [c for c in CATALOG_COLUMNS if _blank(row.get(c))]
        key = (str(row.get("ticker", "")).strip().upper(), str(row.get("series", "")).strip().upper())
        if key in seen:
            errs.append("renglón duplicado (emisora+serie)")
        isin = row.get("isin")
        if not _blank(isin) and (len(str(isin).strip()) != 12 or not str(isin).strip()[:2].isalpha()):
            errs.append("ISIN inválido")
        derivs = [d.strip().lower() for d in str(row.get("derivatives", "")).split("|") if d.strip()]
        if any(d not in ("futuro", "opcion") for d in derivs) or not derivs:
            errs.append("derivatives debe ser 'futuro', 'opcion' o 'futuro|opcion'")
        if str(row.get("exchange", "")).strip().upper() not in ("BMV", "BIVA"):
            errs.append("exchange debe ser BMV o BIVA")
        try:
            reviewed = _date(row.get("reviewed_on"))
        except Exception:
            errs.append("reviewed_on inválida")
            reviewed = None
        if errs:
            rejected.append({"row": int(i) + 2, "errors": errs})
            continue
        seen.add(key)
        accepted.append(dict(issuer_name=str(row["issuer_name"]).strip(), ticker=key[0], series=key[1],
                             isin=None if _blank(isin) else str(isin).strip().upper(),
                             sector=None if _blank(row.get("sector")) else str(row.get("sector")).strip(),
                             yahoo_symbol=None if _blank(row.get("yahoo_symbol")) else str(row.get("yahoo_symbol")).strip(),
                             exchange=str(row["exchange"]).strip().upper(),
                             currency=str(row["currency"]).strip().upper(), derivatives=derivs,
                             active=str(row["active"]).strip().lower() in ("1", "true", "si", "sí", "vigente"),
                             catalog_source=str(row["catalog_source"]).strip(), reviewed_on=reviewed))
    rev = CatalogRevision(source=source, file_sha256=_sha(content), rows_accepted=len(accepted),
                          rows_rejected=len(rejected), report={"rejected": rejected, "filename": filename})
    db.add(rev)
    db.flush()
    existing = {(i.ticker, i.series): i for i in db.scalars(select(Instrument))}
    for rec in accepted:
        k = (rec["ticker"], rec["series"])
        if k in existing:
            inst = existing[k]
            for f, v in rec.items():
                setattr(inst, f, v)
        else:
            inst = Instrument(**rec)
            db.add(inst)
        inst.catalog_revision_id = rev.id
    present = {(r["ticker"], r["series"]) for r in accepted}
    deactivated = []
    for k, inst in existing.items():
        if k not in present and inst.active:
            inst.active = False
            deactivated.append(f"{k[0]} {k[1]}")
    db.commit()
    return {"revision_id": rev.id, "accepted": len(accepted), "rejected": rejected,
            "deactivated_not_in_revision": deactivated}


# ----------------------------------------------------------------------- precios

def import_prices(db: Session, content: bytes, filename: str) -> dict:
    df = read_table(content, filename)
    miss = _missing_cols(df, PRICE_COLUMNS)
    if miss:
        raise ValueError(f"columnas obligatorias faltantes: {miss}")
    batch = ImportBatch(kind="precios", filename=filename, file_sha256=_sha(content),
                        source=";".join(sorted(set(df["source"].dropna().astype(str)))), report={})
    db.add(batch)
    db.flush()
    insts = {(i.ticker, i.series): i for i in db.scalars(select(Instrument))}
    accepted, duplicates, rejected, discrepancies = 0, 0, [], []
    for i, row in df.iterrows():
        rown = int(i) + 2
        key = (str(row["ticker"]).strip().upper(), str(row["series"]).strip().upper())
        inst = insts.get(key)
        if inst is None:
            rejected.append({"row": rown, "errors": [f"{key[0]} {key[1]} no está en el catálogo"]})
            continue
        if str(row["currency"]).strip().upper() != inst.currency:
            rejected.append({"row": rown, "errors": [f"moneda {row['currency']} distinta de la del instrumento ({inst.currency})"]})
            continue
        fields = {"close": row.get("close")}
        for f in ("open", "high", "low", "volume", "adj_close"):
            if f in df.columns and not _blank(row.get(f)):
                fields[f] = row.get(f)
        try:
            ptype = PriceType(str(row["price_type"]).strip())
            if ptype == PriceType.THEORETICAL:
                raise ValueError("no se importan precios teóricos como datos de mercado")
            obs_common = dict(
                instrument=key[0], series=key[1], identifier=str(row["identifier"]).strip(),
                market=str(row["market"]).strip(), source=str(row["source"]).strip(),
                market_date=_date(row["market_date"]),
                publication_date=None if _blank(row.get("publication_date")) else _date(row.get("publication_date")),
                retrieved_at=_dt(row["retrieved_at"]),
                timezone=str(row.get("timezone") or "America/Mexico_City"),
                time=None if _blank(row.get("time")) else str(row.get("time")),
                currency=str(row["currency"]).strip(), published_precision=int(row["precision"]),
                freshness=Freshness(str(row["freshness"]).strip()), origin=DataOrigin(str(row["origin"]).strip()),
                data_version=str(row.get("data_version") or "1"))
            obs = {}
            for f, v in fields.items():
                if _blank(v):
                    continue
                ft = ptype
                if f == "adj_close":
                    ft = PriceType.ADJUSTED_CLOSE
                prec = 0 if f == "volume" else obs_common["published_precision"]
                obs[f] = Observation(**{**obs_common, "price_type": ft, "value_raw": str(v).strip(),
                                        "published_precision": prec})
            if "close" not in obs:
                raise ValueError("close vacío")
            o = {f: float(x.value) for f, x in obs.items()}
            if "high" in o and "low" in o and o["high"] < o["low"]:
                raise ValueError("máximo menor que mínimo")
            for f in ("open", "close"):
                if f in o and "high" in o and "low" in o and not (o["low"] <= o[f] <= o["high"]):
                    raise ValueError(f"{f} fuera del rango [mínimo, máximo]")
            if any(v <= 0 for f, v in o.items() if f != "volume") or o.get("volume", 0) < 0:
                raise ValueError("valores no positivos")
        except (ValidationError, ValueError, KeyError) as e:
            rejected.append({"row": rown, "errors": [str(e).splitlines()[0] if isinstance(e, ValidationError) else str(e)]})
            continue
        new_fields = 0
        for f, ob in obs.items():
            dup = db.scalar(select(PriceRecord).where(
                PriceRecord.instrument_id == inst.id, PriceRecord.market_date == ob.market_date,
                PriceRecord.price_type == ob.price_type.value, PriceRecord.field == f,
                PriceRecord.source == ob.source, PriceRecord.data_version == ob.data_version))
            if dup:
                if dup.value_raw != ob.value_raw:
                    rejected.append({"row": rown, "errors": [
                        f"{f}: ya existe la versión {ob.data_version} con valor {dup.value_raw}; "
                        "use un nuevo data_version para correcciones oficiales"]})
                continue
            status = _reconcile(db, inst, f, ob, discrepancies)
            new_fields += 1
            db.add(PriceRecord(instrument_id=inst.id, field=f, price_type=ob.price_type.value,
                               market_date=ob.market_date, publication_date=ob.publication_date,
                               retrieved_at=ob.retrieved_at, quote_time=ob.time, timezone=ob.timezone,
                               currency=ob.currency, value_raw=ob.value_raw, value=float(ob.value),
                               precision=ob.published_precision, market=ob.market, source=ob.source,
                               origin=ob.origin.value, freshness=ob.freshness.value, validation=status,
                               data_version=ob.data_version, import_batch_id=batch.id))
        if new_fields:
            accepted += 1
        else:
            duplicates += 1
    batch.report = {"accepted_rows": accepted, "duplicates_skipped": duplicates, "rejected": rejected,
                    "discrepancies": discrepancies}
    db.commit()
    return {"batch_id": batch.id, **batch.report}


def _reconcile(db: Session, inst: Instrument, field: str, ob: Observation, discrepancies: list) -> str:
    """Compara contra la referencia oficial del MISMO instrumento, fecha, tipo de precio y campo.
    Las observaciones oficiales se marcan validadas; si una secundaria difiere a la precisión
    publicada, se registra discrepancia (bloqueante)."""
    q = select(PriceRecord).where(PriceRecord.instrument_id == inst.id, PriceRecord.market_date == ob.market_date,
                                  PriceRecord.price_type == ob.price_type.value, PriceRecord.field == field)
    others = list(db.scalars(q))
    if ob.origin == DataOrigin.OBSERVED_OFFICIAL:
        status = ValidationStatus.VALIDATED.value
        for o in others:
            if o.origin != DataOrigin.OBSERVED_OFFICIAL.value:
                if _differs(o.value_raw, ob.value_raw, min(o.precision, ob.published_precision)):
                    o.validation = ValidationStatus.DISCREPANCY.value
                    _log(db, inst, ob, field, ob.source, ob.value_raw, o.source, o.value_raw, discrepancies)
                else:
                    o.validation = ValidationStatus.VALIDATED.value
            elif o.data_version == ob.data_version and _differs(o.value_raw, ob.value_raw, ob.published_precision):
                status = ValidationStatus.DISCREPANCY.value
                _log(db, inst, ob, field, o.source, o.value_raw, ob.source, ob.value_raw, discrepancies)
        return status
    refs = [o for o in others if o.origin == DataOrigin.OBSERVED_OFFICIAL.value]
    if not refs:
        return ValidationStatus.UNVERIFIED.value
    ref = max(refs, key=lambda r: r.data_version)
    if _differs(ref.value_raw, ob.value_raw, min(ref.precision, ob.published_precision)):
        _log(db, inst, ob, field, ref.source, ref.value_raw, ob.source, ob.value_raw, discrepancies)
        return ValidationStatus.DISCREPANCY.value
    return ValidationStatus.VALIDATED.value


def _differs(a: str, b: str, precision: int) -> bool:
    q = Decimal(1).scaleb(-precision)
    return Decimal(a).quantize(q) != Decimal(b).quantize(q)


def _log(db, inst, ob, field, ref_src, ref_val, cand_src, cand_val, out):
    d = Discrepancy(instrument_id=inst.id, market_date=ob.market_date, price_type=ob.price_type.value, field=field,
                    reference_source=ref_src, reference_value=ref_val, candidate_source=cand_src,
                    candidate_value=cand_val)
    db.add(d)
    out.append({"ticker": inst.ticker, "series": inst.series, "date": ob.market_date.isoformat(), "field": field,
                "reference": f"{ref_val} ({ref_src})", "candidate": f"{cand_val} ({cand_src})"})


# ----------------------------------------------------------------------- tasas y curvas

def import_rates(db: Session, content: bytes, filename: str) -> dict:
    df = read_table(content, filename)
    miss = _missing_cols(df, RATE_COLUMNS)
    if miss:
        raise ValueError(f"columnas obligatorias faltantes: {miss}")
    ok, rejected = 0, []
    for i, row in df.iterrows():
        errs = [c for c in RATE_COLUMNS if _blank(row.get(c))]
        try:
            v = Decimal(str(row["value_pct"]).strip())
            if not (Decimal(-5) <= v <= Decimal(100)):
                errs.append("valor fuera de rango plausible (%)")
            origin = DataOrigin(str(row["origin"]).strip())
            if origin in (DataOrigin.MODEL_OUTPUT,):
                errs.append("una tasa de referencia no puede ser resultado de modelo")
            md = _date(row["market_date"])
        except Exception as e:
            errs.append(str(e))
        if errs:
            rejected.append({"row": int(i) + 2, "errors": errs})
            continue
        exists = db.scalar(select(RateObservation).where(RateObservation.rate_code == row["rate_code"].strip(),
                                                         RateObservation.market_date == md,
                                                         RateObservation.source == row["source"].strip()))
        if exists:
            if exists.value_raw != str(v):
                rejected.append({"row": int(i) + 2, "errors": [f"conflicto con valor existente {exists.value_raw}"]})
            continue
        db.add(RateObservation(rate_code=row["rate_code"].strip(), rate_name=row["rate_name"].strip(),
                               tenor=row["tenor"].strip(), market_date=md, value_raw=str(v),
                               convention=row["convention"].strip(), source=row["source"].strip(),
                               retrieved_at=_dt(row["retrieved_at"]), origin=origin.value,
                               validation=(ValidationStatus.VALIDATED if origin == DataOrigin.OBSERVED_OFFICIAL
                                           else ValidationStatus.UNVERIFIED).value))
        ok += 1
    db.commit()
    return {"accepted": ok, "rejected": rejected}


def import_curve(db: Session, content: bytes, filename: str, name: str, curve_date: date, quote_kind: str,
                 compounding: str, day_count: str, interpolation: str, source: str, origin: str) -> dict:
    """Curva: columnas days, value (value en decimal o en %, si quote_kind=zero_rate_pct)."""
    from ..engines.rates.curve import ZeroCurve

    df = read_table(content, filename)
    miss = _missing_cols(df, CURVE_COLUMNS)
    if miss:
        raise ValueError(f"columnas obligatorias faltantes: {miss}")
    DataOrigin(origin)
    if origin == DataOrigin.MODEL_OUTPUT.value:
        raise ValueError("una curva importada no puede declararse resultado de modelo")
    pts = []
    for _, r in df.iterrows():
        d, v = int(r["days"]), float(r["value"])
        if quote_kind == "zero_rate_pct":
            v /= 100
        pts.append({"days": d, "value": v})
    if len(pts) < 2:
        raise ValueError("insuficientes nodos: no se construye una curva con menos de 2 observaciones")
    qk = "discount_factor" if quote_kind == "discount_factor" else "zero_rate"
    curve = ZeroCurve.from_points(curve_date, pts, qk, compounding, day_count, interpolation=interpolation,
                                  name=name, source=source, origin=origin)
    snap = CurveSnapshot(name=name, curve_date=curve_date, quote_kind=qk, compounding=compounding,
                         day_count=day_count, interpolation=interpolation, points=pts, source=source, origin=origin)
    db.add(snap)
    db.commit()
    return {"curve_id": snap.id, "nodes": curve.table()}


# ----------------------------------------------------------------------- contratos

def import_futures_contracts(db: Session, content: bytes, filename: str) -> dict:
    df = read_table(content, filename)
    miss = _missing_cols(df, FUT_COLUMNS)
    if miss:
        raise ValueError(f"columnas obligatorias faltantes: {miss}")
    ok, rejected = 0, []
    for i, r in df.iterrows():
        errs = [c for c in FUT_COLUMNS if _blank(r.get(c))]
        if not errs and str(r["settlement"]).strip().lower() not in ("fisica", "financiera"):
            errs.append("settlement debe ser 'fisica' o 'financiera'")
        if "style" in df.columns and not _blank(r.get("style")):
            errs.append("los futuros no tienen estilo de ejercicio americano/europeo")
        if errs:
            rejected.append({"row": int(i) + 2, "errors": errs})
            continue
        rec = db.scalar(select(FuturesContract).where(FuturesContract.symbol == r["symbol"].strip())) or FuturesContract()
        rec.symbol = r["symbol"].strip()
        rec.underlying_ticker = r["underlying_ticker"].strip().upper()
        rec.expiry = _date(r["expiry"])
        rec.multiplier = float(r["multiplier"])
        rec.tick_size = float(r["tick_size"])
        rec.tick_value = float(r["tick_value"])
        rec.currency = r["currency"].strip().upper()
        rec.settlement = r["settlement"].strip().lower()
        rec.initial_margin = None if _blank(r.get("initial_margin")) else float(r["initial_margin"])
        rec.margin_as_of = None if _blank(r.get("margin_as_of")) else _date(r["margin_as_of"])
        rec.source = r["source"].strip()
        rec.reviewed_on = _date(r["reviewed_on"])
        db.add(rec)
        ok += 1
    db.commit()
    return {"accepted": ok, "rejected": rejected}


def import_option_contracts(db: Session, content: bytes, filename: str) -> dict:
    df = read_table(content, filename)
    miss = _missing_cols(df, OPT_COLUMNS)
    if miss:
        raise ValueError(f"columnas obligatorias faltantes: {miss}")
    ok, rejected = 0, []
    for i, r in df.iterrows():
        errs = [c for c in OPT_COLUMNS if _blank(r.get(c))]
        if not errs:
            if r["option_type"].strip().lower() not in ("call", "put"):
                errs.append("option_type debe ser call o put")
            if r["style"].strip().lower() not in ("europea", "americana"):
                errs.append("style debe ser europea o americana")
        if errs:
            rejected.append({"row": int(i) + 2, "errors": errs})
            continue
        rec = db.scalar(select(OptionContract).where(OptionContract.symbol == r["symbol"].strip())) or OptionContract()
        rec.symbol = r["symbol"].strip()
        rec.underlying_ticker = r["underlying_ticker"].strip().upper()
        rec.option_type = r["option_type"].strip().lower()
        rec.strike = float(r["strike"])
        rec.expiry = _date(r["expiry"])
        rec.multiplier = float(r["multiplier"])
        rec.style = r["style"].strip().lower()
        rec.settlement = r["settlement"].strip().lower()
        rec.currency = r["currency"].strip().upper()
        rec.source = r["source"].strip()
        rec.reviewed_on = _date(r["reviewed_on"])
        db.add(rec)
        ok += 1
    db.commit()
    return {"accepted": ok, "rejected": rejected}


def import_financials(db: Session, content: bytes, filename: str) -> dict:
    """Formato largo: un renglón por partida. Partidas reconocidas: ver ITEM_KEYS."""
    df = read_table(content, filename)
    miss = _missing_cols(df, FIN_COLUMNS)
    if miss:
        raise ValueError(f"columnas obligatorias faltantes: {miss}")
    rejected, groups = [], {}
    for i, r in df.iterrows():
        errs = [c for c in FIN_COLUMNS if _blank(r.get(c))]
        if not errs:
            if r["statement"].strip() not in ("income", "balance", "cashflow"):
                errs.append("statement debe ser income, balance o cashflow")
            if r["period_type"].strip().upper() not in ("Q", "FY"):
                errs.append("period_type debe ser Q o FY")
            if r["basis"].strip().lower() not in ("consolidado", "individual"):
                errs.append("basis debe ser consolidado o individual")
            try:
                float(r["value"])
            except ValueError:
                errs.append("value no numérico")
        if errs:
            rejected.append({"row": int(i) + 2, "errors": errs})
            continue
        k = (r["ticker"].strip().upper(), r["statement"].strip(), r["period_type"].strip().upper(),
             _date(r["period_end"]), r["basis"].strip().lower(), r["source"].strip())
        g = groups.setdefault(k, {"currency": r["currency"].strip().upper(), "units": r["units"].strip(),
                                  "retrieved_at": _dt(r["retrieved_at"]), "items": {}})
        g["items"][r["item"].strip()] = float(r["value"])
    for (t, st, pt, pe, basis, src), g in groups.items():
        rec = db.scalar(select(FinancialStatement).where(
            FinancialStatement.ticker == t, FinancialStatement.statement == st, FinancialStatement.period_type == pt,
            FinancialStatement.period_end == pe, FinancialStatement.basis == basis, FinancialStatement.source == src))
        if rec is None:
            rec = FinancialStatement(ticker=t, statement=st, period_type=pt, period_end=pe, basis=basis, source=src,
                                     currency=g["currency"], units=g["units"], items={}, retrieved_at=g["retrieved_at"])
            db.add(rec)
        rec.items = {**(rec.items or {}), **g["items"]}
    db.commit()
    return {"statements": len(groups), "rejected": rejected}
