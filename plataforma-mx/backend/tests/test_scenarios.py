"""Pruebas del motor de escenarios y de coberturas."""
from datetime import date

import pytest

from app.engines import scenarios as sc
from app.engines.rates.curve import ZeroCurve


def equity_exposure(shares=10_000):
    return sc.EquityExposure("PRUEBA", shares, 100.0, {"source": "sintético de prueba"}, 0.25, 0.30,
                             "supuesto_del_usuario", 0.10, "supuesto_del_usuario")


def test_equity_matrix_dimensions_and_consistency():
    exp = equity_exposure()
    profiles = sc.default_profiles()
    templates = ["protective_put", "collar", "covered_call", "short_futures"]
    strats = {k: sc.equity_strategy_set(exp, p, 100, templates) for k, p in profiles.items()}
    res = sc.evaluate_equity(exp, strats, profiles)
    # 3 perfiles × (4 estrategias + sin cobertura) × 5 escenarios
    assert res["n_evaluations"] == 3 * 5 * 5
    for row in res["evaluations"]:
        assert set(row["scenarios"]) == set(sc.SCENARIO_KEYS)
    # misma condición de mercado para todas las estrategias del perfil
    for pk in profiles:
        rows = [r for r in res["evaluations"] if r["profile"] == pk]
        for sk in sc.SCENARIO_KEYS:
            prices = {r["scenarios"][sk]["S_final"] for r in rows}
            assert len(prices) == 1
            expo = {round(r["scenarios"][sk]["exposure_pnl"], 6) for r in rows}
            assert len(expo) == 1


def test_direction_relative_to_exposure():
    profiles = sc.default_profiles()
    long_res = sc.evaluate_equity(equity_exposure(10_000), {k: [] for k in profiles}, profiles)
    short_res = sc.evaluate_equity(equity_exposure(-10_000), {k: [] for k in profiles}, profiles)
    l = long_res["evaluations"][0]["scenarios"]["estres_adverso_severo"]
    s = short_res["evaluations"][0]["scenarios"]["estres_adverso_severo"]
    assert l["S_final"] < 100 and l["exposure_pnl"] < 0
    assert s["S_final"] > 100 and s["exposure_pnl"] < 0


def test_protective_put_reduces_stress_loss():
    exp = equity_exposure()
    profiles = {"conservador": sc.default_profiles()["conservador"]}
    strats = {"conservador": sc.equity_strategy_set(exp, profiles["conservador"], 100, ["protective_put", "short_futures"])}
    res = sc.evaluate_equity(exp, strats, profiles)
    un, pp, fut = res["evaluations"]
    stress = "estres_adverso_severo"
    assert pp["scenarios"][stress]["combined_pnl"] > un["scenarios"][stress]["combined_pnl"]
    assert pp["scenarios"][stress]["protection_ratio"] > 0.5
    # futuros: resultado combinado casi insensible al precio (sin choque de base)
    spread = fut["scenarios"]["favorable_extremo"]["combined_pnl"] - fut["scenarios"][stress]["combined_pnl"]
    assert abs(spread) < 0.01 * exp.value
    assert fut["warnings"]


def test_edit_shocks_changes_results():
    exp = equity_exposure()
    base = sc.default_profiles()["equilibrado"]
    edited = sc.profile_from_dict({"equity_shocks": {"estres_adverso_severo": 0.5}}, base)
    r1 = sc.evaluate_equity(exp, {"e": []}, {"e": base})
    r2 = sc.evaluate_equity(exp, {"e": []}, {"e": edited})
    assert r2["evaluations"][0]["scenarios"]["estres_adverso_severo"]["S_final"] == pytest.approx(50)
    assert r1["evaluations"][0]["scenarios"]["estres_adverso_severo"]["S_final"] == pytest.approx(75)
    assert base.equity_shocks["estres_adverso_severo"] == 0.25  # el original no se modifica


def curve():
    pts = [{"days": d, "value": 0.072} for d in (28, 91, 182, 364, 728, 1092)]
    return ZeroCurve.from_points(date(2026, 11, 20), pts, "zero_rate", "continua", source="sintética de prueba")


def rate_exposure(kind="pasivo"):
    return sc.RateExposure(kind, 500_000_000, "MXN", "TIIE_28", 0.015, date(2026, 12, 1), date(2028, 11, 28),
                           "28D", "ACT/360")


def test_rate_matrix_and_cap_protection():
    profiles = sc.default_profiles()
    res = sc.evaluate_rates(rate_exposure(), curve(), profiles, "black76", 0.20)
    assert res["n_evaluations"] == 3 * 4 * 5
    for pk in profiles:
        rows = {r["strategy"]: r for r in res["evaluations"] if r["profile"] == pk}
        un, cap = rows["Sin cobertura"], rows["Cap comprado"]
        st = "estres_adverso_severo"
        assert un["scenarios"][st]["parallel_bp"] > 0  # pasivo: adverso = alza
        assert cap["scenarios"][st]["net_pv"] > un["scenarios"][st]["net_pv"]
        assert all(f["derivative_flow"] >= 0 for f in cap["scenarios"][st]["flows"])
        assert rows["Floor comprado"]["economic_function"] == "no_compatible"
        # tasa efectiva acotada por strike + spread
        k = cap["strikes"]["cap"]
        assert cap["scenarios"][st]["max_effective_rate"] <= k + 0.015 + 1e-12


def test_rate_direction_for_asset():
    res = sc.evaluate_rates(rate_exposure("activo"), curve(), {"e": sc.default_profiles()["equilibrado"]})
    rows = {r["strategy"]: r for r in res["evaluations"]}
    assert rows["Sin cobertura"]["scenarios"]["estres_adverso_severo"]["parallel_bp"] < 0
    assert rows["Floor comprado"]["economic_function"] == "cobertura_directa"
    assert rows["Floor comprado"]["scenarios"]["estres_adverso_severo"]["vs_unhedged"] > 0


def test_rank_criteria():
    profiles = sc.default_profiles()
    res = sc.evaluate_rates(rate_exposure(), curve(), profiles)
    ranked = sc.rank(res["evaluations"], "cost", "conservador")
    assert ranked[0]["initial_cost"] <= ranked[-1]["initial_cost"]
    with pytest.raises(ValueError):
        sc.rank(res["evaluations"], "opaco")
