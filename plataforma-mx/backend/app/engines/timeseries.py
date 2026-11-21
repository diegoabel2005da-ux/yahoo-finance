"""Series históricas: remuestreo OHLCV, rendimientos, volatilidad y drawdown (sección 5)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

# Reglas de pandas para cada temporalidad. Se usa el fin de periodo calendario,
# pero la fecha reportada es la ÚLTIMA fecha de negociación real dentro del periodo.
FREQ_RULES = {
    "diaria": None,
    "semanal": "W-FRI",
    "mensual": "ME",
    "bimestral": "2ME",
    "trimestral": "QE",
    "semestral": "6ME",
    "anual": "YE",
}

# Observaciones por año para anualizar, coherentes con cada frecuencia.
PERIODS_PER_YEAR = {
    "diaria": 252, "semanal": 52, "mensual": 12, "bimestral": 6,
    "trimestral": 4, "semestral": 2, "anual": 1,
}


def resample_ohlcv(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Agrega OHLCV: primera apertura, máximo, mínimo, último cierre, volumen total.

    `df` debe tener índice DatetimeIndex ordenado y columnas open, high, low, close, volume
    (volume y open/high/low opcionales). Los periodos sin observaciones se descartan
    (no se rellenan). La fecha del renglón resultante es la última fecha negociada.
    """
    if freq not in FREQ_RULES:
        raise ValueError(f"frecuencia no soportada: {freq}")
    df = df.sort_index()
    if FREQ_RULES[freq] is None:
        return df.copy()
    rule = FREQ_RULES[freq]
    if freq == "bimestral":
        # Bimestres calendario fijos (ene-feb, mar-abr, …) — no dependen del primer dato.
        key = df.index.year * 100 + ((df.index.month - 1) // 2)
        grouper = key
    elif freq == "semestral":
        key = df.index.year * 100 + ((df.index.month - 1) // 6)
        grouper = key
    else:
        grouper = pd.Grouper(freq=rule)
    agg = {}
    if "open" in df:
        agg["open"] = "first"
    if "high" in df:
        agg["high"] = "max"
    if "low" in df:
        agg["low"] = "min"
    agg["close"] = "last"
    if "adj_close" in df:
        agg["adj_close"] = "last"
    if "volume" in df:
        agg["volume"] = lambda s: s.sum(min_count=1)
    tmp = df.copy()
    tmp["_last_date"] = tmp.index
    agg["_last_date"] = "last"
    out = tmp.groupby(grouper).agg(agg).dropna(subset=["close"])
    out.index = pd.DatetimeIndex(out.pop("_last_date"))
    out.index.name = "date"
    return out


def simple_returns(prices: pd.Series) -> pd.Series:
    """R_t = P_t / P_{t-1} − 1"""
    return prices / prices.shift(1) - 1.0


def log_returns(prices: pd.Series) -> pd.Series:
    """r_t = ln(P_t / P_{t-1})"""
    return np.log(prices / prices.shift(1))


def cumulative_returns(prices: pd.Series) -> pd.Series:
    return prices / prices.iloc[0] - 1.0


def annualized_volatility(prices: pd.Series, freq: str = "diaria", log: bool = True) -> float:
    """Desviación estándar muestral (ddof=1) de rendimientos × √(periodos por año)."""
    r = (log_returns(prices) if log else simple_returns(prices)).dropna()
    if len(r) < 2:
        return float("nan")
    return float(r.std(ddof=1) * math.sqrt(PERIODS_PER_YEAR[freq]))


def rolling_volatility(prices: pd.Series, window: int, freq: str = "diaria") -> pd.Series:
    return log_returns(prices).rolling(window).std(ddof=1) * math.sqrt(PERIODS_PER_YEAR[freq])


def drawdown(prices: pd.Series) -> pd.Series:
    """DD_t = P_t / max_{s≤t} P_s − 1"""
    return prices / prices.cummax() - 1.0


def max_drawdown(prices: pd.Series) -> dict:
    dd = drawdown(prices)
    trough = dd.idxmin()
    peak = prices.loc[:trough].idxmax()
    after = prices.loc[trough:]
    rec = after[after >= prices.loc[peak]]
    return {
        "max_drawdown": float(dd.min()),
        "peak_date": peak,
        "trough_date": trough,
        "recovery_date": rec.index[0] if len(rec) else None,
    }


def align_series(a: pd.Series, b: pd.Series) -> pd.DataFrame:
    """Alinea dos series por fechas comunes (inner join) — no interpola."""
    return pd.concat({"a": a, "b": b}, axis=1, join="inner").dropna()
