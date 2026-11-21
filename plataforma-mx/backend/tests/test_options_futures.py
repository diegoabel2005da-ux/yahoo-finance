"""Pruebas de derivados accionarios contra referencias independientes (Hull, Options, Futures
and Other Derivatives) y relaciones de no arbitraje."""
import math

import numpy as np
import pytest

from app.engines import futures as fu
from app.engines import options as op
from app.engines.strategies import build_template, theoretical_premium_fn, validate_strategy, Leg, Strategy


def test_bsm_hull_example():
    # Hull ej. 15.6: S=42, K=40, r=10%, σ=20%, T=0.5 → c=4.76, p=0.81
    assert op.bsm_price("call", 42, 40, 0.5, 0.10, 0.20) == pytest.approx(4.7594, abs=1e-4)
    assert op.bsm_price("put", 42, 40, 0.5, 0.10, 0.20) == pytest.approx(0.8086, abs=1e-4)


@pytest.mark.parametrize("S,K,T,r,s,q", [(100, 95, 1, .05, .3, .02), (50, 60, .25, .11, .45, 0), (20, 20, 2, .08, .15, .04)])
def test_put_call_parity(S, K, T, r, s, q):
    c, p = op.bsm_price("call", S, K, T, r, s, q), op.bsm_price("put", S, K, T, r, s, q)
    assert c - p == pytest.approx(S * math.exp(-q * T) - K * math.exp(-r * T), abs=1e-10)


def test_greeks_against_finite_differences():
    S, K, T, r, s, q = 100, 105, 0.75, 0.09, 0.28, 0.03
    g = op.bsm_greeks("call", S, K, T, r, s, q)
    h = 1e-3
    f = lambda **kw: op.bsm_price("call", kw.get("S", S), K, kw.get("T", T), kw.get("r", r), kw.get("s", s), q)
    assert g["delta"] == pytest.approx((f(S=S + h) - f(S=S - h)) / (2 * h), rel=1e-6)
    assert g["gamma"] == pytest.approx((f(S=S + h) - 2 * f() + f(S=S - h)) / h ** 2, rel=1e-4)
    assert g["vega"] == pytest.approx((f(s=s + h) - f(s=s - h)) / (2 * h), rel=1e-6)
    assert g["rho"] == pytest.approx((f(r=r + h) - f(r=r - h)) / (2 * h), rel=1e-6)
    assert g["theta_per_year"] == pytest.approx(-(f(T=T + h) - f(T=T - h)) / (2 * h), rel=1e-5)
    gp = op.bsm_greeks("put", S, K, T, r, s, q)
    assert g["delta"] - gp["delta"] == pytest.approx(math.exp(-q * T))


def test_crr_converges_to_bsm():
    ref = op.bsm_price("call", 100, 100, 1, 0.05, 0.2, 0.01)
    v = op.crr_price("call", 100, 100, 1, 0.05, 0.2, 0.01, steps=2000)["price"]
    assert v == pytest.approx(ref, abs=5e-3)


def test_crr_american_put_hull():
    # Hull ej. 21.1: S=50, K=50, r=10%, σ=40%, T=5/12, 5 pasos → 4.49 (americana)
    v = op.crr_price("put", 50, 50, 5 / 12, 0.10, 0.40, steps=5, american=True)
    assert v["price"] == pytest.approx(4.49, abs=0.005)
    assert v["early_exercise_nodes"]
    # Con muchos pasos ≈ 4.28 (Hull)
    assert op.crr_price("put", 50, 50, 5 / 12, 0.10, 0.40, steps=1000, american=True)["price"] == pytest.approx(4.28, abs=0.01)


def test_american_call_no_div_equals_european():
    a = op.crr_price("call", 100, 90, 1, 0.07, 0.3, steps=500, american=True)["price"]
    e = op.crr_price("call", 100, 90, 1, 0.07, 0.3, steps=500, american=False)["price"]
    assert a == pytest.approx(e, abs=1e-10)


def test_tree_shapes_and_probability():
    t = op.crr_price("call", 100, 100, 1, 0.05, 0.2, 0.0, steps=4, return_tree=True)
    assert len(t["price_tree"]) == 5 and len(t["price_tree"][4]) == 5
    assert t["price_tree"][0][0] == pytest.approx(100)
    assert 0 < t["p"] < 1 and t["u"] * t["d"] == pytest.approx(1)


def test_discrete_dividend_lowers_call():
    no = op.crr_price("call", 100, 100, 1, 0.05, 0.25, steps=300)["price"]
    yes = op.crr_price("call", 100, 100, 1, 0.05, 0.25, steps=300, discrete_dividends=[(0.5, 3.0)])
    assert yes["price"] < no and yes["notes"]


def test_implied_vol_roundtrip_and_guards():
    obs = op.bsm_price("put", 80, 85, 0.4, 0.1, 0.33, 0.01)
    iv = op.implied_volatility("put", obs, 80, 85, 0.4, 0.1, 0.01, premium_origin="observado_fuente_oficial")
    assert iv["implied_vol"] == pytest.approx(0.33, abs=1e-8)
    with pytest.raises(ValueError, match="modelo"):
        op.implied_volatility("put", obs, 80, 85, 0.4, 0.1, premium_origin="resultado_de_modelo")
    with pytest.raises(ValueError, match="no arbitraje"):
        op.implied_volatility("call", 200, 80, 85, 0.4, 0.1)


def test_basic_positions():
    lc = op.BasicOptionPosition("call", "long", 100, 5, 10, 100)
    assert lc.breakeven() == 105
    assert lc.terminal_pnl(120) == pytest.approx((20 - 5) * 1000)
    assert lc.summary()["max_loss"] == 5000 and lc.summary()["unbounded_gain"]
    sp = op.BasicOptionPosition("put", "short", 100, 4, 1, 100)
    assert sp.terminal_pnl(80) == pytest.approx(-(20 - 4) * 100)
    assert sp.summary()["requires_margin"]


def test_futures_pnl_and_margin():
    assert fu.futures_pnl(10, 100, 50, 55) == 5000
    assert fu.futures_pnl(10, 100, 50, 55, "short") == -5000
    sim = fu.MarginSimulation(10000, maintenance_ratio=0.75, commission_per_contract_side=10)
    r = sim.run([50, 20, 10, 52], n=2, multiplier=100)
    assert r["gross_pnl"] == pytest.approx(2 * 100 * 2)
    assert r["total_margin_calls"] > 0
    # La garantía devuelta + llamadas recuperan: balance final = AIM + llamadas + P&L
    assert r["returned_margin_at_close"] == pytest.approx(r["initial_margin"] + r["total_margin_calls"] + r["gross_pnl"])
    assert r["net_pnl"] == pytest.approx(r["gross_pnl"] - 40)


def test_hedge_ratio_and_stop():
    rng = np.random.default_rng(0)
    f = rng.normal(0, 0.01, 500)
    s = 0.8 * f + rng.normal(0, 0.002, 500)
    h = fu.min_variance_hedge_ratio(s, f)
    assert h["hedge_ratio"] == pytest.approx(0.8, abs=0.02)
    st = fu.stop_loss_simulation([100, 98, 90], entry=100, stop=95, side="long", n=1, multiplier=10,
                                 slippage_ticks=2, tick=0.01)
    assert st["stopped"] and st["fill"] == pytest.approx(89.98) and st["gap_vs_stop"] < 0


def _pf():
    return theoretical_premium_fn(100, 0.1, 0.0, 0.3, "supuesto_del_usuario")


def test_strategy_payoffs_at_expiry():
    T = 0.5
    straddle = build_template("long_straddle", 100, T, 1, 100, _pf())
    prem = -straddle.initial_cash() / 100
    assert straddle.pnl(100, T, .3, .1, 0) == pytest.approx(-prem * 100)
    assert straddle.pnl(130, T, .3, .1, 0) == pytest.approx((30 - prem) * 100)
    be = straddle.breakevens(100, T, .3, .1, 0)
    assert be[0] == pytest.approx(100 - prem, abs=0.05) and be[-1] == pytest.approx(100 + prem, abs=0.05)
    fly = build_template("long_call_butterfly", 100, T, 1, 100, _pf(), {"k1": 90, "k2": 100, "k3": 110})
    cost = -fly.initial_cash()
    assert cost > 0
    assert fly.pnl(100, T, .3, .1, 0) == pytest.approx(10 * 100 - cost)
    assert fly.pnl(80, T, .3, .1, 0) == pytest.approx(-cost)
    assert fly.pnl(130, T, .3, .1, 0) == pytest.approx(-cost)
    sfly = build_template("short_put_butterfly", 100, T, 1, 100, _pf(), {"k1": 90, "k2": 100, "k3": 110})
    assert sfly.pnl(100, T, .3, .1, 0) == pytest.approx(-10 * 100 + sfly.initial_cash())


def test_protective_put_floor_and_covered_call_cap():
    T, n, M = 0.5, 10, 100
    pp = build_template("protective_put", 100, T, n, M, _pf(), {"k_put": 95})
    stock = n * M
    prem = -pp.initial_cash()
    for S in (40, 70, 95):
        assert stock * (S - 100) + pp.pnl(S, T, .3, .1, 0) == pytest.approx(stock * (95 - 100) - prem)
    cc = build_template("covered_call", 100, T, n, M, _pf(), {"k_call": 110})
    inc = cc.initial_cash()
    assert inc > 0 and cc.economic_function == "ingreso_primas"
    for S in (110, 150, 200):
        assert stock * (S - 100) + cc.pnl(S, T, .3, .1, 0) == pytest.approx(stock * 10 + inc)
    # pérdida grande prácticamente no protegida
    assert stock * (50 - 100) + cc.pnl(50, T, .3, .1, 0) == pytest.approx(stock * -50 + inc)


def test_collar_band_and_revaluation_before_expiry():
    T = 0.5
    col = build_template("collar", 100, T, 1, 100, _pf(), {"k_put": 90, "k_call": 110})
    c0 = -col.initial_cash()
    outcomes = [100 * (S - 100) + col.pnl(S, T, .3, .1, 0) for S in (50, 80, 100, 120, 200)]
    assert min(outcomes) == pytest.approx(100 * -10 - c0)
    assert max(outcomes) == pytest.approx(100 * 10 - c0)
    # antes del vencimiento NO es igual al payoff terminal
    early = col.pnl(80, 0.1, .3, .1, 0)
    terminal = col.pnl(80, T, .3, .1, 0)
    assert abs(early - terminal) > 1


def test_validation_flags_naked_calls():
    s = Strategy("x", [Leg("call", -1, 100, 100, 0.5, premium=3)])
    assert any("descubiertas" in w for w in validate_strategy(s))
    s2 = Strategy("y", [Leg("call", 1, 100, None, 0.5, premium=3)])
    assert any("strike" in w for w in validate_strategy(s2))


def test_implied_vol_american_short_maturity():
    # Vencimiento corto con r alta: la cota inferior de σ debe mantener válido el árbol CRR.
    S, K, T, r = 54.42, 55.0, 0.0767, 0.0626
    prem = op.crr_price("call", S, K, T, r, 0.22, 0.0, 300, american=True)["price"]
    iv = op.implied_volatility("call", prem, S, K, T, r, american=True, steps=300)
    assert iv["implied_vol"] == pytest.approx(0.22, abs=1e-6)
