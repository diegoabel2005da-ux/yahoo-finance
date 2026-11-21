"""Medidas de riesgo (sección 8). Son estimaciones estadísticas históricas, no predicciones."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats

from .timeseries import PERIODS_PER_YEAR, align_series, log_returns, simple_returns


def beta(asset_prices: pd.Series, market_prices: pd.Series, use_log: bool = False) -> dict:
    """β = Cov(R_a, R_m) / Var(R_m), con rendimientos en fechas comunes.

    Devuelve también alfa, R² de la regresión MCO R_a = α + β R_m, error estándar de β
    y número de observaciones.
    """
    df = align_series(asset_prices, market_prices)
    f = log_returns if use_log else simple_returns
    ra = f(df["a"]).dropna()
    rm = f(df["b"]).dropna()
    idx = ra.index.intersection(rm.index)
    ra, rm = ra.loc[idx].to_numpy(), rm.loc[idx].to_numpy()
    n = len(ra)
    if n < 3:
        raise ValueError("se requieren al menos 3 rendimientos comunes para estimar beta")
    var_m = np.var(rm, ddof=1)
    if var_m == 0:
        raise ValueError("la varianza del índice es cero")
    cov = np.cov(ra, rm, ddof=1)[0, 1]
    b = cov / var_m
    a = ra.mean() - b * rm.mean()
    resid = ra - (a + b * rm)
    ss_res = float((resid ** 2).sum())
    ss_tot = float(((ra - ra.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    se_b = math.sqrt(ss_res / (n - 2) / ((rm - rm.mean()) ** 2).sum()) if n > 2 else float("nan")
    return {
        "beta": float(b), "alpha": float(a), "r_squared": float(r2), "std_error_beta": se_b,
        "observations": n, "start": idx[0], "end": idx[-1],
        "returns": "logarítmicos" if use_log else "simples",
        "methodology": "β = Cov(Ra,Rm)/Var(Rm), covarianza muestral (ddof=1), fechas comunes",
    }


def historical_var_es(returns: np.ndarray, confidence: float = 0.95) -> dict:
    """VaR y ES históricos sobre rendimientos (las pérdidas son positivas).

    VaR_c = −cuantil_{1−c}(R) (interpolación lineal).
    ES_c  = −media(R | R ≤ −VaR_c).
    """
    r = np.asarray(returns, float)
    r = r[~np.isnan(r)]
    if len(r) < 20:
        raise ValueError("se requieren al menos 20 observaciones para VaR histórico")
    q = np.quantile(r, 1 - confidence)
    tail = r[r <= q]
    return {"var": float(-q), "es": float(-tail.mean()), "observations": len(r),
            "confidence": confidence, "method": "histórico"}


def parametric_var_es(returns: np.ndarray, confidence: float = 0.95) -> dict:
    """VaR y ES normales: VaR = −(μ + σ z_{1−c}); ES = −μ + σ φ(z_c)/(1−c)."""
    r = np.asarray(returns, float)
    r = r[~np.isnan(r)]
    if len(r) < 2:
        raise ValueError("observaciones insuficientes")
    mu, sd = r.mean(), r.std(ddof=1)
    z = stats.norm.ppf(1 - confidence)
    var = -(mu + sd * z)
    es = -mu + sd * stats.norm.pdf(stats.norm.ppf(confidence)) / (1 - confidence)
    return {"var": float(var), "es": float(es), "observations": len(r), "confidence": confidence,
            "method": "paramétrico normal", "mean": float(mu), "std": float(sd)}


def scale_var(var_1: float, horizon: int) -> float:
    """Escalamiento por raíz del tiempo (supone rendimientos i.i.d.)."""
    return var_1 * math.sqrt(horizon)


def correlation_matrix(prices: dict[str, pd.Series]) -> pd.DataFrame:
    df = pd.concat(prices, axis=1, join="inner").dropna()
    return np.log(df / df.shift(1)).dropna().corr()


def liquidity_metrics(volume: pd.Series, close: pd.Series, window: int = 20) -> dict:
    """Métricas descriptivas de liquidez: volumen e importe operado promedio, días sin operación
    y medida de iliquidez de Amihud = media(|R_t| / Importe_t)."""
    turnover = volume * close
    r = simple_returns(close).abs()
    valid = turnover > 0
    amihud = (r[valid] / turnover[valid]).dropna()
    return {
        "avg_volume": float(volume.tail(window).mean()),
        "avg_turnover": float(turnover.tail(window).mean()),
        "zero_volume_days": int((volume.tail(window) == 0).sum()),
        "amihud_illiquidity": float(amihud.mean()) if len(amihud) else None,
        "window": window,
    }


def risk_summary(close: pd.Series, freq: str = "diaria", confidence: float = 0.95) -> dict:
    r = log_returns(close).dropna().to_numpy()
    ppy = PERIODS_PER_YEAR[freq]
    out = {
        "observations": len(r),
        "volatility_annual": float(r.std(ddof=1) * math.sqrt(ppy)) if len(r) > 1 else None,
        "skew": float(stats.skew(r)) if len(r) > 2 else None,
        "excess_kurtosis": float(stats.kurtosis(r)) if len(r) > 3 else None,
    }
    try:
        out["var_hist"] = historical_var_es(simple_returns(close).dropna().to_numpy(), confidence)
    except ValueError as e:
        out["var_hist"] = {"error": str(e)}
    try:
        out["var_param"] = parametric_var_es(simple_returns(close).dropna().to_numpy(), confidence)
    except ValueError as e:
        out["var_param"] = {"error": str(e)}
    out["disclaimer"] = ("Medidas estimadas con datos históricos; no constituyen una predicción "
                         "ni garantizan pérdidas máximas futuras.")
    return out
