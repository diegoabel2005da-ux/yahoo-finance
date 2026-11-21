"""Acceso a series validadas. Bloquea cálculos críticos ante discrepancias no resueltas."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import Discrepancy, Instrument, PriceRecord
from ..core.provenance import DataOrigin, PriceType, ValidationStatus
from ..engines.rates.daycount import HolidayCalendar


class DataBlocked(Exception):
    """Discrepancias no resueltas impiden un cálculo crítico."""


def get_instrument(db: Session, ticker: str, series: str | None = None) -> Instrument:
    q = select(Instrument).where(Instrument.ticker == ticker.upper())
    if series:
        q = q.where(Instrument.series == series.upper())
    rows = list(db.scalars(q))
    if not rows:
        raise LookupError(f"{ticker} {series or ''} no está en el catálogo")
    if len(rows) > 1:
        raise LookupError(f"{ticker} tiene varias series {[r.series for r in rows]}; especifique la serie")
    return rows[0]


def open_discrepancies(db: Session, inst: Instrument) -> list[Discrepancy]:
    return list(db.scalars(select(Discrepancy).where(Discrepancy.instrument_id == inst.id,
                                                     Discrepancy.resolved.is_(False))))


def load_ohlcv(db: Session, inst: Instrument, price_type: str = PriceType.OFFICIAL_CLOSE.value,
               start: date | None = None, end: date | None = None, critical: bool = True,
               prefer_official: bool = True) -> tuple[pd.DataFrame, dict]:
    """Carga OHLCV de un tipo de precio. Por fecha/campo usa la versión más reciente de la
    fuente oficial si existe; si no, la de un proveedor secundario no discrepante.
    Devuelve (DataFrame, metadatos de procedencia)."""
    if critical:
        disc = open_discrepancies(db, inst)
        if disc:
            raise DataBlocked(f"{len(disc)} discrepancias sin resolver para {inst.ticker} {inst.series}; "
                              "resuélvalas antes de calcular")
    q = select(PriceRecord).where(PriceRecord.instrument_id == inst.id, PriceRecord.price_type == price_type)
    if start:
        q = q.where(PriceRecord.market_date >= start)
    if end:
        q = q.where(PriceRecord.market_date <= end)
    recs = list(db.scalars(q))
    adj = list(db.scalars(select(PriceRecord).where(PriceRecord.instrument_id == inst.id,
                                                    PriceRecord.price_type == PriceType.ADJUSTED_CLOSE.value)))
    if not recs:
        return pd.DataFrame(), {"available": False, "reason": f"sin observaciones de tipo {price_type}"}
    best: dict[tuple, PriceRecord] = {}
    rank = lambda r: (r.origin == DataOrigin.OBSERVED_OFFICIAL.value if prefer_official else 0, r.data_version)
    for r in recs + adj:
        if r.validation in (ValidationStatus.DISCREPANCY.value, ValidationStatus.REJECTED.value):
            continue
        k = (r.market_date, r.field)
        if k not in best or rank(r) > rank(best[k]):
            best[k] = r
    rows = {}
    sources, statuses = set(), {}
    for (d, f), r in best.items():
        rows.setdefault(d, {})[f] = float(r.value)
        sources.add(r.source)
        statuses[r.validation] = statuses.get(r.validation, 0) + 1
    df = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    df.index = pd.DatetimeIndex(df.index)
    df.index.name = "date"
    last = df.index.max().date()
    meta = {"available": True, "price_type": price_type, "observations": len(df), "first_date": df.index.min().date(),
            "last_date": last, "sources": sorted(sources), "validation_counts": statuses,
            "freshness": freshness_status(last), "adjusted_close_available": "adj_close" in df.columns,
            "currency": inst.currency}
    return df, meta


def freshness_status(last_date: date, today: date | None = None, cal: HolidayCalendar | None = None) -> dict:
    """Estado de actualización respecto del último día hábil cerrado (calendario por reglas)."""
    cal = cal or HolidayCalendar()
    now = datetime.now(timezone(timedelta(hours=-6)))
    today = today or now.date()
    ref = today if (cal.is_business_day(today) and now.hour >= 15) else cal.add_business_days(today, -1) \
        if cal.is_business_day(today) else cal.adjust(today, "preceding")
    lag = len(cal.business_days_between(last_date, ref)) if last_date < ref else 0
    status = "historico_al_dia" if lag == 0 else "desactualizado"
    return {"last_available": last_date, "expected_last_close": ref, "business_days_behind": lag, "status": status,
            "calendar": cal.source}
