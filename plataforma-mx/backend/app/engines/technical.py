"""Indicadores técnicos (sección 6). Todas las ventanas son parametrizables.

Convenciones:
- Los primeros n−1 valores son NaN (no se inventan valores con ventanas incompletas).
- Si el denominador Máximo_n − Mínimo_n es cero, el oscilador es NaN y se marca.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FIB_LEVELS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
FIB_EXTENSIONS = [1.272, 1.618, 2.0, 2.618]


def roc(close: pd.Series, n: int) -> pd.Series:
    """ROC(n) = [(P_t / P_{t−n}) − 1] × 100"""
    if n < 1:
        raise ValueError("n debe ser ≥ 1")
    return (close / close.shift(n) - 1.0) * 100.0


def zero_crossings(series: pd.Series) -> list[dict]:
    s = series.dropna()
    sign = np.sign(s)
    out = []
    prev = None
    for ts, v in sign.items():
        if prev is not None and v != 0 and prev != 0 and v != prev:
            out.append({"date": ts, "direction": "alcista" if v > 0 else "bajista"})
        if v != 0:
            prev = v
    return out


def _hl_range(high: pd.Series, low: pd.Series, n: int):
    hh = high.rolling(n, min_periods=n).max()
    ll = low.rolling(n, min_periods=n).min()
    return hh, ll


def williams_r(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    """%R = −100 × (Máx_n − Cierre) / (Máx_n − Mín_n); NaN si Máx_n = Mín_n."""
    hh, ll = _hl_range(high, low, n)
    den = (hh - ll).replace(0.0, np.nan)
    return -100.0 * (hh - close) / den


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k: int = 14, d: int = 3,
               mode: str = "lento", smooth_k: int = 3) -> pd.DataFrame:
    """Oscilador estocástico.

    Rápido: %K = 100 (C − Mín_k)/(Máx_k − Mín_k); %D = SMA_d(%K).
    Lento:  %K_lento = SMA_smooth_k(%K_rápido); %D_lento = SMA_d(%K_lento).
    Suavizado: medias móviles simples (documentado).
    """
    hh, ll = _hl_range(high, low, k)
    den = (hh - ll).replace(0.0, np.nan)
    fast_k = 100.0 * (close - ll) / den
    if mode == "rapido":
        kk = fast_k
    elif mode == "lento":
        kk = fast_k.rolling(smooth_k, min_periods=smooth_k).mean()
    else:
        raise ValueError("mode debe ser 'rapido' o 'lento'")
    dd = kk.rolling(d, min_periods=d).mean()
    return pd.DataFrame({"k": kk, "d": dd})


def rsi_wilder(close: pd.Series, n: int = 14) -> pd.Series:
    """RSI con suavizado de Wilder.

    Ganancia/pérdida promedio inicial = media simple de los primeros n cambios;
    después: avg_t = (avg_{t−1}·(n−1) + x_t) / n.  RSI = 100 − 100/(1+RS).
    Si la pérdida promedio es 0 → RSI = 100 (y si ambas son 0 → 50).
    """
    c = close.to_numpy(dtype=float)
    out = np.full(len(c), np.nan)
    if len(c) <= n:
        return pd.Series(out, index=close.index)
    delta = np.diff(c)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    ag = gains[:n].mean()
    al = losses[:n].mean()

    def _rsi(g, l):
        if l == 0:
            return 50.0 if g == 0 else 100.0
        return 100.0 - 100.0 / (1.0 + g / l)

    out[n] = _rsi(ag, al)
    for i in range(n, len(delta)):
        ag = (ag * (n - 1) + gains[i]) / n
        al = (al * (n - 1) + losses[i]) / n
        out[i + 1] = _rsi(ag, al)
    return pd.Series(out, index=close.index)


def rsi_multi(close: pd.Series, periods=(9, 14, 25)) -> pd.DataFrame:
    return pd.DataFrame({f"rsi_{p}": rsi_wilder(close, p) for p in periods})


def sma(close: pd.Series, n: int) -> pd.Series:
    return close.rolling(n, min_periods=n).mean()


def ema(close: pd.Series, n: int) -> pd.Series:
    """EMA con α = 2/(n+1), sembrada con la SMA de los primeros n datos."""
    c = close.to_numpy(dtype=float)
    out = np.full(len(c), np.nan)
    if len(c) < n:
        return pd.Series(out, index=close.index)
    a = 2.0 / (n + 1)
    out[n - 1] = c[:n].mean()
    for i in range(n, len(c)):
        out[i] = a * c[i] + (1 - a) * out[i - 1]
    return pd.Series(out, index=close.index)


def fibonacci_levels(anchor_high: float, anchor_low: float, trend: str = "alcista",
                     extensions: bool = True) -> list[dict]:
    """Retrocesos de Fibonacci entre dos anclas.

    Tendencia alcista (de mínimo a máximo): nivel = Máx − f·(Máx − Mín).
    Tendencia bajista (de máximo a mínimo): nivel = Mín + f·(Máx − Mín).
    Extensiones: proyectadas más allá del ancla final con el mismo rango.
    """
    if anchor_high <= anchor_low:
        raise ValueError("el ancla máxima debe ser mayor que la mínima")
    rng = anchor_high - anchor_low
    out = []
    for f in FIB_LEVELS:
        price = anchor_high - f * rng if trend == "alcista" else anchor_low + f * rng
        out.append({"ratio": f, "kind": "retroceso", "price": price})
    if extensions:
        for f in FIB_EXTENSIONS:
            price = anchor_low + f * rng if trend == "alcista" else anchor_high - f * rng
            out.append({"ratio": f, "kind": "extension", "price": price})
    return out


def pivots(high: pd.Series, low: pd.Series, left: int = 5, right: int = 5) -> pd.DataFrame:
    """Pivotes fractales: un máximo (mínimo) es pivote si es estrictamente el mayor
    (menor) dentro de `left` barras previas y `right` posteriores. Los últimos
    `right` datos no pueden confirmarse (no se usan datos futuros inexistentes)."""
    h = high.to_numpy(float)
    l = low.to_numpy(float)
    rows = []
    for i in range(left, len(h) - right):
        wh = h[i - left:i + right + 1]
        wl = l[i - left:i + right + 1]
        if h[i] == wh.max() and (wh == h[i]).sum() == 1:
            rows.append({"idx": i, "date": high.index[i], "kind": "maximo", "price": h[i]})
        if l[i] == wl.min() and (wl == l[i]).sum() == 1:
            rows.append({"idx": i, "date": low.index[i], "kind": "minimo", "price": l[i]})
    return pd.DataFrame(rows, columns=["idx", "date", "kind", "price"])


def auto_fibonacci(high: pd.Series, low: pd.Series, left: int = 5, right: int = 5) -> dict | None:
    """Ancla automática: último pivote máximo y último pivote mínimo confirmados.
    Si el mínimo es anterior al máximo → tendencia alcista; si no → bajista."""
    pv = pivots(high, low, left, right)
    if pv.empty or (pv.kind == "maximo").sum() == 0 or (pv.kind == "minimo").sum() == 0:
        return None
    ph = pv[pv.kind == "maximo"].iloc[-1]
    pl = pv[pv.kind == "minimo"].iloc[-1]
    trend = "alcista" if pl.idx < ph.idx else "bajista"
    return {
        "anchor_high": {"date": ph.date, "price": float(ph.price)},
        "anchor_low": {"date": pl.date, "price": float(pl.price)},
        "trend": trend,
        "levels": fibonacci_levels(float(ph.price), float(pl.price), trend),
        "method": f"Último pivote fractal confirmado (left={left}, right={right})",
    }
