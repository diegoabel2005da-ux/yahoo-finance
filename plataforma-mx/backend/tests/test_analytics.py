"""Pruebas de series, indicadores técnicos, riesgo, fundamentales y patrones.

Los datos usados aquí son SINTÉTICOS y deterministas, generados sólo para verificar
fórmulas; nunca se presentan como datos de mercado.
"""
import math

import numpy as np
import pandas as pd
import pytest

from app.engines import fundamental as fa
from app.engines import patterns as pt
from app.engines import risk as rk
from app.engines import technical as ta
from app.engines import timeseries as ts


@pytest.fixture
def ohlc():
    idx = pd.bdate_range("2024-01-01", periods=300)
    rng = np.random.default_rng(42)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, 300))), idx)
    high = close * (1 + rng.uniform(0, 0.01, 300))
    low = close * (1 - rng.uniform(0, 0.01, 300))
    opn = close.shift(1).fillna(100)
    vol = pd.Series(rng.integers(1000, 5000, 300), idx).astype(float)
    return pd.DataFrame({"open": opn, "high": high, "low": low, "close": close, "volume": vol})


def test_returns_formulas():
    p = pd.Series([100.0, 110.0, 99.0])
    assert ts.simple_returns(p).iloc[1] == pytest.approx(0.10)
    assert ts.log_returns(p).iloc[2] == pytest.approx(math.log(99 / 110))
    assert ts.cumulative_returns(p).iloc[-1] == pytest.approx(-0.01)


def test_resample_weekly_ohlcv(ohlc):
    w = ts.resample_ohlcv(ohlc, "semanal")
    first_week = ohlc.loc[: w.index[0]]
    assert w.iloc[0]["open"] == first_week["open"].iloc[0]
    assert w.iloc[0]["high"] == first_week["high"].max()
    assert w.iloc[0]["low"] == first_week["low"].min()
    assert w.iloc[0]["close"] == first_week["close"].iloc[-1]
    assert w.iloc[0]["volume"] == first_week["volume"].sum()
    assert w.index[0] == first_week.index[-1]  # fecha = última negociada
    m = ts.resample_ohlcv(ohlc, "mensual")
    assert m["volume"].sum() == ohlc["volume"].sum()
    b = ts.resample_ohlcv(ohlc, "bimestral")
    assert b.index[0].month in (2,)  # ene-feb termina en febrero
    for f in ("trimestral", "semestral", "anual"):
        assert ts.resample_ohlcv(ohlc, f)["volume"].sum() == ohlc["volume"].sum()


def test_volatility_annualization():
    p = pd.Series(np.exp(np.cumsum([0.01, -0.01] * 50)))
    r = np.log(p / p.shift(1)).dropna()
    assert ts.annualized_volatility(p, "diaria") == pytest.approx(r.std(ddof=1) * math.sqrt(252))
    assert ts.annualized_volatility(p, "semanal") == pytest.approx(r.std(ddof=1) * math.sqrt(52))


def test_drawdown():
    p = pd.Series([100, 120, 90, 130, 65.0], pd.bdate_range("2024-01-01", periods=5))
    md = ts.max_drawdown(p)
    assert md["max_drawdown"] == pytest.approx(65 / 130 - 1)
    assert md["recovery_date"] is None


def test_roc_and_crossings():
    p = pd.Series([10, 11, 12, 11, 10, 9, 10, 12.0])
    r = ta.roc(p, 2)
    assert r.iloc[2] == pytest.approx((12 / 10 - 1) * 100)
    assert np.isnan(r.iloc[1])
    assert len(ta.zero_crossings(r)) >= 1


def test_williams_and_stochastic_zero_range():
    h = pd.Series([10, 12, 11, 13, 13, 13, 13.0])
    l = pd.Series([9, 10, 10, 11, 13, 13, 13.0])
    c = pd.Series([9.5, 11, 10.5, 12, 13, 13, 13.0])
    w = ta.williams_r(h, l, c, 3)
    assert w.iloc[3] == pytest.approx(-100 * (13 - 12) / (13 - 10))
    h2 = pd.Series([5.0] * 6)
    w2 = ta.williams_r(h2, h2, h2, 3)
    assert w2.dropna().empty  # denominador cero → NaN, no se inventa
    st = ta.stochastic(h, l, c, k=3, d=2, mode="rapido")
    assert st["k"].iloc[3] == pytest.approx(100 * (12 - 10) / (13 - 10))
    assert st["d"].iloc[3] == pytest.approx((st["k"].iloc[2] + st["k"].iloc[3]) / 2)
    slow = ta.stochastic(h, l, c, k=3, d=2, mode="lento", smooth_k=2)
    assert slow["k"].iloc[3] == pytest.approx((st["k"].iloc[2] + st["k"].iloc[3]) / 2)


def _rsi_reference(close, n):
    # Implementación independiente (bucle con listas, versión de Wilder 1978)
    ch = [close[i] - close[i - 1] for i in range(1, len(close))]
    g = sum(max(x, 0) for x in ch[:n]) / n
    l = sum(max(-x, 0) for x in ch[:n]) / n
    out = [100 - 100 / (1 + g / l)]
    for x in ch[n:]:
        g = (g * (n - 1) + max(x, 0)) / n
        l = (l * (n - 1) + max(-x, 0)) / n
        out.append(100 - 100 / (1 + g / l))
    return out


@pytest.mark.parametrize("n", [9, 14, 25])
def test_rsi_wilder(ohlc, n):
    c = ohlc["close"]
    mine = ta.rsi_wilder(c, n).dropna().to_numpy()
    ref = _rsi_reference(c.tolist(), n)
    assert np.allclose(mine, ref)
    assert ta.rsi_wilder(c, n).iloc[: n].isna().all()


def test_rsi_classic_dataset():
    # Serie del ejemplo clásico de RSI (14) de StockCharts: primer RSI ≈ 70.53
    closes = [44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955, 45.4245, 45.8433, 46.0826,
              45.8931, 46.0328, 45.6140, 46.2820, 46.2820, 46.0028, 46.0328, 46.4116, 46.2222, 45.6439]
    r = ta.rsi_wilder(pd.Series(closes), 14)
    assert r.iloc[14] == pytest.approx(70.53, abs=0.01)
    assert r.iloc[15] == pytest.approx(66.32, abs=0.01)


def test_fibonacci():
    lv = ta.fibonacci_levels(200, 100, "alcista")
    d = {(x["kind"], x["ratio"]): x["price"] for x in lv}
    assert d[("retroceso", 0.618)] == pytest.approx(138.2)
    assert d[("retroceso", 0.0)] == 200 and d[("retroceso", 1.0)] == 100
    assert d[("extension", 1.618)] == pytest.approx(261.8)
    dn = {(x["kind"], x["ratio"]): x["price"] for x in ta.fibonacci_levels(200, 100, "bajista")}
    assert dn[("retroceso", 0.382)] == pytest.approx(138.2)


def test_pivots_do_not_use_future(ohlc):
    pv = ta.pivots(ohlc["high"], ohlc["low"], 5, 5)
    assert pv["idx"].max() <= len(ohlc) - 6


def test_beta_known_relation():
    idx = pd.bdate_range("2023-01-01", periods=400)
    rng = np.random.default_rng(1)
    rm = rng.normal(0, 0.01, 400)
    ra = 1.3 * rm + rng.normal(0, 0.002, 400)
    m = pd.Series(100 * np.cumprod(1 + rm), idx)
    a = pd.Series(50 * np.cumprod(1 + ra), idx)
    b = rk.beta(a, m)
    assert b["beta"] == pytest.approx(1.3, abs=0.03)
    assert 0.9 < b["r_squared"] <= 1
    # definición Cov/Var exacta
    r_a, r_m = a.pct_change().dropna(), m.pct_change().dropna()
    assert b["beta"] == pytest.approx(np.cov(r_a, r_m)[0, 1] / np.var(r_m, ddof=1))


def test_var_es():
    r = np.linspace(-0.05, 0.05, 101)
    h = rk.historical_var_es(r, 0.95)
    assert h["var"] == pytest.approx(-np.quantile(r, 0.05))
    assert h["es"] >= h["var"]
    p = rk.parametric_var_es(np.random.default_rng(3).normal(0, 0.01, 5000), 0.99)
    assert p["var"] == pytest.approx(0.01 * 2.326, rel=0.06)
    assert p["es"] > p["var"]
    with pytest.raises(ValueError):
        rk.historical_var_es(r[:5])


def test_ratios_and_missing():
    f = {"revenue": 1000, "gross_profit": 400, "ebit": 200, "net_income": 120, "total_assets": 2000,
         "total_equity": 800, "total_debt": 600, "cash": 100, "current_assets": 500, "current_liabilities": 250,
         "inventories": 100, "interest_expense": 40, "depreciation_amortization": 50}
    r = fa.compute_ratios(f, price=20, shares=100, tax_rate=0.30)
    R = r["ratios"]
    assert R["liquidez_corriente"]["value"] == 2.0
    assert R["prueba_acida"]["value"] == pytest.approx(1.6)
    assert R["margen_neto"]["value"] == pytest.approx(0.12)
    assert R["deuda_neta_ebitda"]["value"] == pytest.approx(500 / 250)
    assert R["cobertura_intereses"]["value"] == 5.0
    assert R["roic"]["value"] == pytest.approx(200 * 0.7 / (600 + 800 - 100))
    assert R["pe"]["value"] == pytest.approx(20 / 1.2)
    assert R["ev_ebitda"]["value"] == pytest.approx((2000 + 500) / 250)
    assert R["dividend_yield"]["value"] is None and "dps_ttm" in R["dividend_yield"]["missing"]
    r2 = fa.compute_ratios({"revenue": 100})
    assert r2["ratios"]["margen_neto"]["value"] is None and "net_income" in r2["ratios"]["margen_neto"]["missing"]


def test_wacc_capm():
    ke = fa.cost_of_equity_capm(0.09, 1.1, 0.06, 0.01)
    assert ke == pytest.approx(0.166)
    assert fa.wacc(600, 400, ke, 0.10, 0.30) == pytest.approx(0.6 * 0.166 + 0.4 * 0.07)


def test_dcf_against_manual():
    p = fa.DCFInputs(base_revenue=1000, revenue_growth=[0.1, 0.1], ebit_margin=[0.2, 0.2], tax_rate=0.3,
                     da_pct_revenue=[0.05, 0.05], capex_pct_revenue=[0.06, 0.06], nwc_pct_revenue_change=[0.1, 0.1],
                     wacc=0.1, terminal_growth=0.03, net_debt=200, shares_outstanding=10)
    out = fa.dcf_fcff(p)
    r1, r2 = 1100, 1210
    f1 = r1 * 0.2 * 0.7 + r1 * 0.05 - r1 * 0.06 - 100 * 0.1
    f2 = r2 * 0.2 * 0.7 + r2 * 0.05 - r2 * 0.06 - 110 * 0.1
    tv = f2 * 1.03 / 0.07
    ev = f1 / 1.1 + f2 / 1.21 + tv / 1.21
    assert out["enterprise_value"] == pytest.approx(ev)
    assert out["value_per_share"] == pytest.approx((ev - 200) / 10)
    with pytest.raises(ValueError):
        fa.dcf_fcff(fa.DCFInputs(**{**p.__dict__, "terminal_growth": 0.12}))
    sens = fa.dcf_sensitivity(p, [0.09, 0.10, 0.11], [0.02, 0.03])
    col = [row[1] for row in sens["value_per_share"]]
    assert col[0] > col[1] > col[2]


def test_patterns_double_top_detection():
    # Serie sintética con doble techo explícito
    seg = np.concatenate([np.linspace(100, 130, 20), np.linspace(130, 110, 15)[1:], np.linspace(110, 129.5, 15)[1:],
                          np.linspace(129.5, 100, 20)[1:]])
    idx = pd.bdate_range("2024-01-01", periods=len(seg))
    c = pd.Series(seg, idx)
    df = pd.DataFrame({"high": c * 1.001, "low": c * 0.999, "close": c})
    found = pt.detect_patterns(df, left=5, right=5)
    dt = [f for f in found if f["pattern"] == "doble_techo"]
    assert dt and dt[0]["status"] == "confirmada"
    assert dt[0]["confirmation_level"] == pytest.approx(110 * 0.999, rel=1e-3)


def test_trend_rules(ohlc):
    tr = pt.classify_trends(ohlc["close"], primary=200, secondary=50, short=20)
    assert tr["primaria"]["state"] in ("alcista", "bajista", "lateral/mixta")
    assert "rules" in tr
