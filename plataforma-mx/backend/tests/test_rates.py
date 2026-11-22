"""Pruebas de derivados de tasas: convenciones, curvas, Black-76, Bachelier, caps y floors."""
import math
from datetime import date, timedelta

import numpy as np
import pytest
from scipy.stats import norm

from app.engines.rates import capfloor as cf
from app.engines.rates.curve import ZeroCurve, to_continuous
from app.engines.rates.daycount import (HolidayCalendar, build_schedule, compounded_in_arrears, easter,
                                        mexican_market_holidays, year_fraction)

VD = date(2026, 11, 20)


def flat_curve(rate=0.07, comp="continua"):
    pts = [{"days": d, "value": rate} for d in (28, 91, 182, 364, 728, 1092, 1820)]
    return ZeroCurve.from_points(VD, pts, "zero_rate", comp, name="prueba", source="sintética de prueba")


def test_year_fractions():
    assert year_fraction(date(2026, 1, 1), date(2026, 1, 29), "ACT/360") == pytest.approx(28 / 360)
    assert year_fraction(date(2026, 1, 1), date(2027, 1, 1), "ACT/365F") == pytest.approx(1.0)
    assert year_fraction(date(2026, 1, 31), date(2026, 3, 31), "30/360") == pytest.approx(60 / 360)
    with pytest.raises(ValueError):
        year_fraction(VD, VD, "BUS/252x")


def test_calendar_rules():
    assert easter(2026) == date(2026, 4, 5)
    assert easter(2025) == date(2025, 4, 20)
    h = mexican_market_holidays(2026)
    assert date(2026, 2, 2) in h and date(2026, 3, 16) in h and date(2026, 11, 16) in h
    assert date(2026, 4, 2) in h and date(2026, 4, 3) in h
    cal = HolidayCalendar()
    assert cal.adjust(date(2026, 9, 16)) == date(2026, 9, 17)
    assert cal.adjust(date(2026, 1, 31), "modified_following") == date(2026, 1, 30)
    off = HolidayCalendar.from_dates([date(2026, 6, 1)], "oficial", "archivo")
    assert not off.is_business_day(date(2026, 6, 1)) and off.is_business_day(date(2026, 9, 16))


def test_schedule_28d():
    sch = build_schedule(date(2026, 11, 23), date(2027, 11, 22), "28D", 1e6)
    assert len(sch) == 13
    assert all(p.accrual_end > p.accrual_start for p in sch)
    assert sum(p.accrual for p in sch) == pytest.approx((sch[-1].accrual_end - sch[0].accrual_start).days / 360)
    with pytest.raises(ValueError):
        build_schedule(date(2026, 11, 23), date(2027, 11, 22), "28D", 1e6, amortization=[1, 2])


def test_compounded_in_arrears():
    cal = HolidayCalendar()
    s, e = date(2026, 11, 23), date(2026, 12, 21)
    days = cal.business_days_between(s, e)
    fx = {d: 0.07 for d in days}
    r = compounded_in_arrears(fx, s, e, cal)
    # compuesta diaria con tasa constante: ligeramente superior a la simple
    assert r["rate"] > 0.07 and r["rate"] < 0.0703
    fx.pop(days[3])
    assert compounded_in_arrears(fx, s, e, cal)["rate"] is None


def test_curve_basics_and_conversion():
    c = flat_curve(0.07)
    assert c.df(1.0) == pytest.approx(math.exp(-0.07))
    assert c.zero(0.5) == pytest.approx(0.07)
    assert to_continuous(0.07, 1.0, "anual") == pytest.approx(math.log(1.07))
    with pytest.raises(ValueError):
        ZeroCurve(VD, np.array([1.0]), np.array([0.07]))
    df_curve = ZeroCurve.from_points(VD, [{"days": 365, "value": 0.93}, {"days": 730, "value": 0.86}],
                                     "discount_factor")
    assert df_curve.df(1.0) == pytest.approx(0.93)
    # log-lineal en DF: forward constante entre nodos
    f1 = df_curve.forward_simple(VD + timedelta(days=400), VD + timedelta(days=428), "ACT/365F")
    f2 = df_curve.forward_simple(VD + timedelta(days=600), VD + timedelta(days=628), "ACT/365F")
    assert f1 == pytest.approx(f2, rel=1e-10)
    sh = c.shifted(parallel_bp=100)
    assert sh.zero(1.0) == pytest.approx(0.08)


def test_black76_against_numerical_integration():
    # Referencia independiente: E[max(R−K,0)] con R lognormal, integrada numéricamente.
    from scipy.integrate import quad
    F, K, s, tf = 0.07, 0.08, 0.20, 1.0
    m, v = math.log(F) - 0.5 * s * s * tf, s * math.sqrt(tf)
    dens = lambda x: math.exp(-(math.log(x) - m) ** 2 / (2 * v * v)) / (x * v * math.sqrt(2 * math.pi))
    ref = quad(lambda x: (x - K) * dens(x), K, 1.0, limit=200)[0]
    assert cf.black76("cap", F, K, tf, s) == pytest.approx(ref, rel=1e-7)
    ref_f = quad(lambda x: (K - x) * dens(x), 1e-9, K, limit=200)[0]
    assert cf.black76("floor", F, K, tf, s) == pytest.approx(ref_f, rel=1e-7)
    # Caplet escalado (estructura de Hull ej. de caplet: L=10,000, α=0.25, cero 6.5 % a 1.25 años)
    v_caplet = 10000 * 0.25 * math.exp(-0.065 * 1.25) * cf.black76("cap", F, K, tf, s)
    assert v_caplet == pytest.approx(10000 * 0.25 * math.exp(-0.065 * 1.25) * ref, rel=1e-7)


def test_bachelier_against_numerical_integration():
    from scipy.integrate import quad
    F, K, t, sn = 0.072, 0.075, 0.8, 0.012
    sd = sn * math.sqrt(t)
    ref = quad(lambda x: (x - K) * norm.pdf(x, F, sd), K, F + 12 * sd)[0]
    assert cf.bachelier("cap", F, K, t, sn) == pytest.approx(ref, rel=1e-8)


def test_bachelier_formula_and_parity():
    F, K, t, sn = 0.072, 0.075, 0.8, 0.012
    d = (F - K) / (sn * math.sqrt(t))
    assert cf.bachelier("cap", F, K, t, sn) == pytest.approx((F - K) * norm.cdf(d) + sn * math.sqrt(t) * norm.pdf(d))
    for model, vol in (("black76", 0.25), ("bachelier", 0.01)):
        c = cf.unit_value(model, "cap", F, K, t, vol)
        f = cf.unit_value(model, "floor", F, K, t, vol)
        assert c - f == pytest.approx(F - K, abs=1e-14)


def _spec(**kw):
    base = dict(kind="cap", notional=100_000_000, strike=0.075, start=date(2026, 12, 1), end=date(2028, 11, 28),
                frequency="28D", day_count="ACT/360", model="black76", vol=0.22)
    base.update(kw)
    return cf.CapFloorSpec(**base)


def test_cap_floor_parity_and_monotonicity():
    c = flat_curve(0.072)
    cap = cf.price_capfloor(_spec(), c)
    floor = cf.price_capfloor(_spec(kind="floor"), c)
    swap = cf.swap_value_from_forwards(_spec(), c)
    assert cap["value"] - floor["value"] == pytest.approx(swap, rel=1e-9, abs=1e-6)
    assert cap["value"] > 0 and cap["origin"] == "resultado_de_modelo"
    vals_cap = [cf.price_capfloor(_spec(strike=k), c)["value"] for k in (0.06, 0.07, 0.08, 0.09)]
    vals_floor = [cf.price_capfloor(_spec(kind="floor", strike=k), c)["value"] for k in (0.06, 0.07, 0.08, 0.09)]
    assert all(np.diff(vals_cap) <= 0) and all(np.diff(vals_floor) >= 0)
    # escala lineal con el nocional
    assert cf.price_capfloor(_spec(notional=2e8), c)["value"] == pytest.approx(2 * cap["value"])
    # la suma de caplets es el cap
    assert sum(r["value"] for r in cap["components"]) == pytest.approx(cap["value"])


def test_bachelier_cap_parity():
    c = flat_curve(0.072)
    cap = cf.price_capfloor(_spec(model="bachelier", vol=0.012), c)["value"]
    floor = cf.price_capfloor(_spec(model="bachelier", vol=0.012, kind="floor"), c)["value"]
    assert cap - floor == pytest.approx(cf.swap_value_from_forwards(_spec(), c), rel=1e-9)


def test_terminal_flows_nonnegative():
    R = np.linspace(-0.01, 0.2, 50)
    assert (cf.terminal_payoff("cap", 1e6, 28 / 360, R, 0.08) >= 0).all()
    assert (cf.terminal_payoff("floor", 1e6, 28 / 360, R, 0.08) >= 0).all()


def test_in_arrears_has_lower_variance_time_than_in_advance_equivalent():
    c = flat_curve(0.072)
    adv = cf.price_capfloor(_spec(fixing_lag_bd=0), c)
    arr = cf.price_capfloor(_spec(rate_style="compounded_in_arrears"), c)
    # en atraso τ = t_s + (t_e − t_s)/3 > t_s: más incertidumbre → mayor valor por periodo ATM-ish
    for a, b in zip(adv["components"], arr["components"]):
        assert b["tau"] > a["tau"]
    assert arr["value"] > adv["value"]


def test_fixed_and_partial_periods():
    c = flat_curve(0.072)
    spec = _spec(start=date(2026, 11, 2), rate_style="compounded_in_arrears")
    with pytest.raises(ValueError, match="factor devengado"):
        cf.price_capfloor(spec, c)
    spec.accrued_factor = {0: 1 + 0.0705 * 18 / 360}
    out = cf.price_capfloor(spec, c)
    assert out["components"][0]["rate_state"] == "parcialmente_observada"
    spec2 = _spec(start=date(2026, 11, 2))
    with pytest.raises(ValueError, match="fijación"):
        cf.price_capfloor(spec2, c)
    spec2.known_fixings = {0: 0.09}
    first = cf.price_capfloor(spec2, c)["components"][0]
    assert first["rate_state"] == "fijada" and first["tau"] == 0
    assert first["value"] == pytest.approx(first["notional"] * first["accrual"] * first["discount_factor"] * 0.015)


def test_sensitivities_signs_and_pv01_check():
    c = flat_curve(0.072)
    s = cf.sensitivities(_spec(), c)
    assert s["pv01_parallel"] > 0 and s["vega"] > 0
    sf = cf.sensitivities(_spec(kind="floor"), c)
    assert sf["pv01_parallel"] < 0 and sf["vega"] > 0
    assert sum(k["pv01"] for k in s["key_rate_pv01"]) == pytest.approx(s["pv01_parallel"], rel=0.02)
    assert s["theta_1d"] < 0


def test_implied_flat_vol_guard():
    c = flat_curve(0.072)
    v = cf.price_capfloor(_spec(vol=0.3), c)["value"]
    assert cf.implied_flat_vol(_spec(), v, c)["implied_flat_vol"] == pytest.approx(0.3, abs=1e-8)
    with pytest.raises(ValueError):
        cf.implied_flat_vol(_spec(), v, c, premium_origin="resultado_de_modelo")


def test_black_requires_positive_rates():
    with pytest.raises(ValueError):
        cf.black76("cap", -0.001, 0.01, 1, 0.2)
    assert cf.black76("cap", -0.001, 0.01, 1, 0.2, shift=0.02) > 0


def test_bootstrap_government_curve_reprices_par_bonds():
    from app.engines.rates.curve import bootstrap_government_curve
    cetes = [(28, 0.0619), (91, 0.0649), (182, 0.0667), (364, 0.0695)]
    bonds = [(3, 0.080), (5, 0.0878), (10, 0.0928)]
    nodes = bootstrap_government_curve(cetes, bonds)
    df = {n["days"]: n["value"] for n in nodes}
    assert df[28] == pytest.approx(1 / (1 + 0.0619 * 28 / 360))
    # un bono par a 5 años (10 cupones) debe valer 1 con los DF obtenidos
    c = 0.0878 * 182 / 360
    pv = c * sum(df[182 * k] for k in range(1, 11)) + df[1820]
    assert pv == pytest.approx(1.0, abs=1e-12)
    ds = [df[d] for d in sorted(df)]
    assert all(b < a for a, b in zip(ds, ds[1:]))  # DF decrecientes
    with pytest.raises(ValueError):
        bootstrap_government_curve([(28, 0.06)], bonds)


def test_forward_diagnostics_flags_unstable_long_end():
    from app.engines.rates.curve import bootstrap_government_curve, forward_diagnostics
    cetes = [(28, 0.0619), (91, 0.0649), (182, 0.0667), (364, 0.0695)]
    ok = forward_diagnostics(bootstrap_government_curve(cetes, [(3, .08), (5, .0878), (10, .0928), (20, .0979)]))
    assert not ok["flagged"]
    bad = forward_diagnostics(bootstrap_government_curve(cetes, [(3, .08), (5, .0878), (10, .0928), (20, .0979), (30, .1015)]))
    assert bad["flagged"] and bad["max_forward"] > 0.15
