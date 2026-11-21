"""Motor central de escenarios combinados y evaluación de coberturas (secciones 14 y 15).

Reglas del motor:
1. Cada combinación perfil × estrategia se evalúa en (al menos) cinco escenarios:
   estrés adverso severo, adverso moderado, base, favorable moderado, favorable extremo.
2. "Adverso/favorable" se define respecto de la exposición: para acciones largas, adverso =
   caída; para exposición corta, adverso = alza; para un pasivo a tasa variable, adverso =
   alza de tasas; para un activo a tasa variable, adverso = baja de tasas.
3. Dentro de un perfil, la MISMA condición de mercado se aplica a todas las estrategias.
   El perfil sólo define su conjunto de choques (visible y editable) y sus preferencias.
4. Los choques son hipótesis de simulación. No se asignan probabilidades.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from ..core.provenance import DataOrigin
from .rates.capfloor import CapFloorSpec, price_capfloor, terminal_payoff
from .rates.curve import ZeroCurve
from .strategies import ECONOMIC_FUNCTIONS, Strategy, build_template, theoretical_premium_fn

SCENARIO_KEYS = ["estres_adverso_severo", "adverso_moderado", "base", "favorable_moderado", "favorable_extremo"]
SCENARIO_LABELS = {
    "estres_adverso_severo": "Estrés adverso severo",
    "adverso_moderado": "Movimiento adverso moderado",
    "base": "Escenario base / estabilidad",
    "favorable_moderado": "Movimiento favorable moderado",
    "favorable_extremo": "Movimiento favorable extremo",
}


@dataclass
class Profile:
    key: str
    name: str
    description: str
    # magnitudes de choque en la dirección ADVERSA/FAVORABLE (positivas). Acciones: % de precio.
    equity_shocks: dict[str, float]
    equity_vol_shift: dict[str, float]          # puntos de vol (decimal) añadidos a σ
    rate_shocks_bp: dict[str, float]            # paralelo, magnitud en pb
    rate_slope_bp: dict[str, float] = field(default_factory=lambda: {k: 0.0 for k in SCENARIO_KEYS})
    rate_curvature_bp: dict[str, float] = field(default_factory=lambda: {k: 0.0 for k in SCENARIO_KEYS})
    max_loss_tolerance: float = 0.10            # pérdida máxima aceptable (% de exposición) en estrés severo
    hedge_budget: float = 0.03                  # costo inicial máximo aceptable (% de exposición)
    put_moneyness: float = 1.0                  # strike de puts protectoras / S0
    call_moneyness: float = 1.05                # strike de calls vendidas / S0
    hedge_ratio: float = 1.0
    cap_strike_offset_bp: float = 0.0           # strike cap = forward promedio + offset
    floor_strike_offset_bp: float = 0.0


def default_profiles() -> dict[str, Profile]:
    return {
        "conservador": Profile(
            "conservador", "Conservador",
            "Prioriza reducir pérdidas y la protección, aunque existan costos o límites a resultados favorables.",
            equity_shocks={"estres_adverso_severo": 0.35, "adverso_moderado": 0.15, "base": 0.0,
                           "favorable_moderado": 0.10, "favorable_extremo": 0.25},
            equity_vol_shift={"estres_adverso_severo": 0.15, "adverso_moderado": 0.05, "base": 0.0,
                              "favorable_moderado": -0.02, "favorable_extremo": 0.03},
            rate_shocks_bp={"estres_adverso_severo": 300, "adverso_moderado": 125, "base": 0,
                            "favorable_moderado": 75, "favorable_extremo": 200},
            max_loss_tolerance=0.08, hedge_budget=0.05, put_moneyness=1.00, call_moneyness=1.08,
            hedge_ratio=1.0, cap_strike_offset_bp=0, floor_strike_offset_bp=0),
        "equilibrado": Profile(
            "equilibrado", "Equilibrado",
            "Busca balance entre costo, protección y participación en movimientos favorables.",
            equity_shocks={"estres_adverso_severo": 0.25, "adverso_moderado": 0.10, "base": 0.0,
                           "favorable_moderado": 0.10, "favorable_extremo": 0.25},
            equity_vol_shift={"estres_adverso_severo": 0.10, "adverso_moderado": 0.03, "base": 0.0,
                              "favorable_moderado": -0.02, "favorable_extremo": 0.03},
            rate_shocks_bp={"estres_adverso_severo": 200, "adverso_moderado": 100, "base": 0,
                            "favorable_moderado": 100, "favorable_extremo": 200},
            max_loss_tolerance=0.15, hedge_budget=0.03, put_moneyness=0.95, call_moneyness=1.05,
            hedge_ratio=1.0, cap_strike_offset_bp=50, floor_strike_offset_bp=-50),
        "agresivo": Profile(
            "agresivo", "Agresivo",
            "Tolera mayor exposición residual y estudia estrategias de mayor riesgo, sin confundirlas con "
            "coberturas garantizadas.",
            equity_shocks={"estres_adverso_severo": 0.20, "adverso_moderado": 0.08, "base": 0.0,
                           "favorable_moderado": 0.12, "favorable_extremo": 0.35},
            equity_vol_shift={"estres_adverso_severo": 0.08, "adverso_moderado": 0.02, "base": 0.0,
                              "favorable_moderado": -0.02, "favorable_extremo": 0.05},
            rate_shocks_bp={"estres_adverso_severo": 150, "adverso_moderado": 75, "base": 0,
                            "favorable_moderado": 100, "favorable_extremo": 250},
            max_loss_tolerance=0.25, hedge_budget=0.015, put_moneyness=0.90, call_moneyness=1.10,
            hedge_ratio=0.5, cap_strike_offset_bp=100, floor_strike_offset_bp=-100),
    }


def profile_from_dict(d: dict, base: Profile | None = None) -> Profile:
    p = copy.deepcopy(base) if base else None
    if p is None:
        return Profile(**d)
    for k, v in d.items():
        if isinstance(getattr(p, k, None), dict) and isinstance(v, dict):
            getattr(p, k).update(v)
        else:
            setattr(p, k, v)
    return p


def _signed_move(key: str, magnitude: float, adverse_sign: int) -> float:
    """adverse_sign: dirección del movimiento adverso (+1 alza, −1 baja)."""
    if key == "base":
        return 0.0
    adverse = key in ("estres_adverso_severo", "adverso_moderado")
    return adverse_sign * magnitude if adverse else -adverse_sign * magnitude


# ======================================================================== ACCIONES

@dataclass
class EquityExposure:
    ticker: str
    shares: float                  # + largo, − corto
    spot: float
    spot_provenance: dict          # fuente, fecha, tipo de precio
    horizon_years: float
    sigma: float
    sigma_origin: str
    r: float
    r_origin: str
    q: float = 0.0
    declared: bool = False
    currency: str = "MXN"
    budget: Optional[float] = None
    objective: str = ""
    restrictions: list[str] = field(default_factory=list)

    @property
    def sign(self) -> int:
        return 1 if self.shares > 0 else -1

    @property
    def value(self) -> float:
        return self.shares * self.spot


def equity_strategy_set(exp: EquityExposure, profile: Profile, multiplier: float, templates: list[str],
                        option_expiry: float | None = None, futures: dict | None = None,
                        premium_fn=None, commission_per_contract: float = 0.0) -> list[Strategy]:
    """Construye las estrategias para el perfil. Los strikes dependen del perfil (preferencia
    documentada); las condiciones de mercado no."""
    T = option_expiry or exp.horizon_years
    contracts = abs(exp.shares) / multiplier
    pf = premium_fn or theoretical_premium_fn(exp.spot, exp.r, exp.q, exp.sigma, exp.sigma_origin)
    S0 = exp.spot
    strikes = {"k_put": round(S0 * profile.put_moneyness, 2), "k_call": round(S0 * profile.call_moneyness, 2),
               "k1": round(S0 * 0.95, 2), "k2": round(S0, 2), "k3": round(S0 * 1.05, 2)}
    if exp.sign < 0:
        strikes["k_call"] = round(S0 * (2 - profile.put_moneyness), 2)
        strikes["k_put"] = round(S0 * (2 - profile.call_moneyness), 2)
    fut_price = None
    fut_status = "teorico_simulacion"
    if futures:
        fut_price = futures["price"]
        fut_status = futures.get("status", "teorico_simulacion")
    else:
        fut_price = S0 * math.exp((exp.r - exp.q) * T)
    out = []
    for name in templates:
        hr = profile.hedge_ratio if name in ("protective_put", "protective_call", "collar", "short_futures",
                                             "long_futures") else 1.0
        s = build_template(name, S0, T, contracts, multiplier, pf, strikes, exp.sign, exp.ticker,
                           futures_price=fut_price, futures_status=fut_status,
                           commission_per_contract=commission_per_contract, hedge_ratio=hr)
        if name in ("short_futures", "long_futures") and not futures:
            s.warnings.append("Precio de futuro teórico por costo de acarreo (no es una cotización).")
        out.append(s)
    return out


def evaluate_equity(exp: EquityExposure, strategies_by_profile: dict[str, list[Strategy]],
                    profiles: dict[str, Profile], futures_basis_shock: float = 0.0) -> dict:
    """Matriz perfil × estrategia × escenario para una exposición accionaria."""
    adverse_sign = -1 if exp.sign > 0 else +1
    h = exp.horizon_years
    results = []
    scen_defs = {}
    for pk, prof in profiles.items():
        scen_defs[pk] = {}
        for sk in SCENARIO_KEYS:
            move = _signed_move(sk, prof.equity_shocks[sk], adverse_sign)
            scen_defs[pk][sk] = {"price_change": move, "S_final": exp.spot * (1 + move),
                                 "sigma_final": max(exp.sigma + prof.equity_vol_shift[sk], 0.01),
                                 "horizon_years": h, "futures_basis": futures_basis_shock if sk != "base" else 0.0,
                                 "label": SCENARIO_LABELS[sk]}
        strategies = [Strategy("Sin cobertura", [], "sin_cobertura", "Exposición original")] + \
            strategies_by_profile[pk]
        for s in strategies:
            cost = -s.initial_cash()
            row = {"profile": pk, "strategy": s.name, "economic_function": s.economic_function,
                   "economic_function_label": ECONOMIC_FUNCTIONS[s.economic_function],
                   "initial_cost": cost, "initial_cost_pct": cost / abs(exp.value),
                   "premium_origins": sorted({l.premium_origin for l in s.legs if l.kind in ("call", "put")}),
                   "warnings": s.warnings, "scenarios": {}}
            base_combined = None
            for sk in SCENARIO_KEYS:
                sc = scen_defs[pk][sk]
                S1, sig1 = sc["S_final"], sc["sigma_final"]
                expo_pnl = exp.shares * (S1 - exp.spot)
                deriv = s.pnl(S1, h, sig1, exp.r, exp.q, sc["futures_basis"]) if s.legs else 0.0
                combined = expo_pnl + deriv
                # delta residual por diferencia finita (exposición remanente en acciones-equivalentes)
                dS = exp.spot * 0.001
                d_up = s.pnl(S1 + dS, h, sig1, exp.r, exp.q) if s.legs else 0.0
                d_dn = s.pnl(S1 - dS, h, sig1, exp.r, exp.q) if s.legs else 0.0
                residual_delta = exp.shares + (d_up - d_dn) / (2 * dS)
                protection = None
                if expo_pnl < 0:
                    protection = (combined - expo_pnl) / (-expo_pnl)
                row["scenarios"][sk] = {
                    "S_final": S1, "price_change": sc["price_change"], "sigma_final": sig1,
                    "exposure_pnl": expo_pnl, "derivative_pnl": deriv, "combined_pnl": combined,
                    "combined_pct": combined / abs(exp.value), "protection_ratio": protection,
                    "residual_delta_shares": residual_delta,
                    "unhedged_risks": _equity_unhedged(s, residual_delta, exp),
                    "valuation": ("payoff al vencimiento" if s.option_expiry() and s.option_expiry() <= h + 1e-9
                                  else "revaluación con modelo antes del vencimiento" if s.legs else "precio final"),
                }
                if sk == "base":
                    base_combined = combined
            for sk in SCENARIO_KEYS:
                row["scenarios"][sk]["vs_base"] = row["scenarios"][sk]["combined_pnl"] - base_combined
            worst = row["scenarios"]["estres_adverso_severo"]["combined_pct"]
            row["constraints"] = {
                "max_loss_ok": worst >= -prof.max_loss_tolerance,
                "budget_ok": row["initial_cost_pct"] <= prof.hedge_budget + 1e-12,
                "compatible": s.economic_function not in ("no_compatible",),
            }
            row["upside_participation"] = _participation(row, exp)
            results.append(row)
    return {"exposure": _expo_dict(exp), "scenario_definitions": scen_defs, "evaluations": results,
            "n_evaluations": len(results) * len(SCENARIO_KEYS),
            "method_notes": [
                "Mismos choques de mercado para todas las estrategias dentro de cada perfil.",
                "Opciones con vencimiento posterior al horizonte se revalúan con BSM (europeas) o CRR (americanas).",
                "Los choques son hipótesis de simulación, sin probabilidades asignadas.",
                "La AIM de futuros no se considera costo; el P&L de futuros se liquida diariamente.",
            ]}


def _participation(row, exp):
    fav = row["scenarios"]["favorable_extremo"]
    if fav["exposure_pnl"] <= 0:
        return None
    return fav["combined_pnl"] / fav["exposure_pnl"]


def _equity_unhedged(s: Strategy, residual_delta: float, exp: EquityExposure) -> list[str]:
    risks = []
    if abs(residual_delta) > 0.05 * abs(exp.shares):
        risks.append(f"Exposición direccional remanente ≈ {residual_delta:,.0f} acciones equivalentes")
    if any(l.kind == "future" for l in s.legs):
        risks.append("Riesgo de base entre futuro y contado; necesidades de liquidez por liquidación diaria")
    if any(l.kind in ("call", "put") for l in s.legs):
        risks.append("Riesgo de volatilidad y de liquidez de las opciones; riesgo de vencimiento/renovación")
    if any(l.qty < 0 and l.kind in ("call", "put") for l in s.legs):
        risks.append("Obligaciones por opciones vendidas (garantías)")
    return risks


def _expo_dict(exp):
    return {"ticker": exp.ticker, "shares": exp.shares, "spot": exp.spot, "value": exp.value,
            "spot_provenance": exp.spot_provenance, "horizon_years": exp.horizon_years,
            "sigma": exp.sigma, "sigma_origin": exp.sigma_origin, "r": exp.r, "r_origin": exp.r_origin,
            "q": exp.q, "declared": exp.declared, "main_risk": "baja del precio" if exp.sign > 0 else "alza del precio"}


# ======================================================================== TASAS

@dataclass
class RateExposure:
    kind: str                       # 'pasivo' | 'activo'
    notional: float
    currency: str
    reference_rate: str
    spread: float                   # margen contractual (decimal)
    start: date
    end: date
    frequency: str
    day_count: str
    rate_style: str = "term_fixed_in_advance"
    amortization: list[float] | None = None
    declared: bool = False
    budget: Optional[float] = None
    known_fixings: dict[int, float] = field(default_factory=dict)
    accrued_factor: dict[int, float] = field(default_factory=dict)

    @property
    def adverse_sign(self) -> int:
        return +1 if self.kind == "pasivo" else -1


def _rate_overlays(exp: RateExposure, prof: Profile, disc: ZeroCurve, model: str, vol: float, vol_origin: str,
                   strikes: dict | None = None) -> list[dict]:
    base = CapFloorSpec("cap", exp.notional, 0.0, exp.start, exp.end, exp.frequency, exp.day_count,
                        exp.rate_style, model, vol, vol_origin, amortization=exp.amortization,
                        known_fixings=exp.known_fixings, accrued_factor=exp.accrued_factor,
                        reference_rate=exp.reference_rate)
    # strike de referencia: forward promedio ponderado por nocional·α (visible al usuario)
    from .rates.capfloor import _forward
    sch = base.schedule()
    w = [(p.notional * p.accrual) for p in sch]
    fw = [_forward(base, disc, p, i)[0] for i, p in enumerate(sch)]
    avg_fwd = sum(a * b for a, b in zip(w, fw)) / sum(w)
    k_cap = (strikes or {}).get("cap", round(avg_fwd + prof.cap_strike_offset_bp / 1e4, 6))
    k_floor = (strikes or {}).get("floor", round(avg_fwd + prof.floor_strike_offset_bp / 1e4, 6))
    cap = CapFloorSpec(**{**base.__dict__, "kind": "cap", "strike": k_cap})
    floor = CapFloorSpec(**{**base.__dict__, "kind": "floor", "strike": k_floor})
    if exp.kind == "pasivo":
        return [
            {"name": "Cap comprado", "legs": [(+1, cap)], "economic_function": "cobertura_directa"},
            {"name": "Collar de tasas (cap comprado + floor vendido)", "legs": [(+1, cap), (-1, floor)],
             "economic_function": "cobertura_directa"},
            {"name": "Floor comprado", "legs": [(+1, floor)], "economic_function": "no_compatible"},
        ], avg_fwd
    return [
        {"name": "Floor comprado", "legs": [(+1, floor)], "economic_function": "cobertura_directa"},
        {"name": "Collar de tasas (floor comprado + cap vendido)", "legs": [(+1, floor), (-1, cap)],
         "economic_function": "cobertura_directa"},
        {"name": "Cap comprado", "legs": [(+1, cap)], "economic_function": "no_compatible"},
    ], avg_fwd


def evaluate_rates(exp: RateExposure, disc: ZeroCurve, profiles: dict[str, Profile], model: str = "black76",
                   vol: float = 0.2, vol_origin: str = DataOrigin.USER_ASSUMPTION.value,
                   strikes: dict | None = None) -> dict:
    """Matriz perfil × estrategia × escenario para una exposición a tasa variable.

    Hipótesis de trayectoria: en cada escenario la curva se desplaza al inicio (paralelo +
    pendiente + curvatura) y las tasas realizadas de cada periodo igualan las forwards de la
    curva desplazada. Se reportan por separado:
    - flujos efectivamente pagaderos (no descontados) por periodo,
    - valor presente de los flujos en la curva del escenario,
    - valor de mercado inmediato (MTM) del derivado tras el choque,
    - P&L económico del derivado = VP(pagos del derivado) − prima.
    """
    results, scen_defs = [], {}
    from .rates.capfloor import _forward
    sgn_expo = -1 if exp.kind == "pasivo" else +1   # pasivo paga intereses (flujo negativo)
    for pk, prof in profiles.items():
        overlays, avg_fwd = _rate_overlays(exp, prof, disc, model, vol, vol_origin, strikes)
        premiums = {}
        for ov in overlays:
            prem = 0.0
            for sign, spec in ov["legs"]:
                prem += sign * price_capfloor(spec, disc)["value"]
            premiums[ov["name"]] = prem
        scen_defs[pk] = {}
        for sk in SCENARIO_KEYS:
            par = _signed_move(sk, prof.rate_shocks_bp[sk], exp.adverse_sign)
            slope = _signed_move(sk, prof.rate_slope_bp[sk], exp.adverse_sign)
            curv = _signed_move(sk, prof.rate_curvature_bp[sk], exp.adverse_sign)
            scen_defs[pk][sk] = {"parallel_bp": par, "slope_bp": slope, "curvature_bp": curv,
                                 "label": SCENARIO_LABELS[sk]}
        candidates = [{"name": "Sin cobertura", "legs": [], "economic_function": "sin_cobertura"}] + overlays
        for ov in candidates:
            prem = premiums.get(ov["name"], 0.0)
            row = {"profile": pk, "strategy": ov["name"], "economic_function": ov["economic_function"],
                   "economic_function_label": ECONOMIC_FUNCTIONS[ov["economic_function"]],
                   "initial_cost": prem, "initial_cost_pct": prem / exp.notional,
                   "premium_origin": DataOrigin.MODEL_OUTPUT.value if ov["legs"] else None,
                   "strikes": {("cap" if sp.kind == "cap" else "floor"): sp.strike for _, sp in ov["legs"]},
                   "reference_avg_forward": avg_fwd, "scenarios": {}}
            base_net = None
            for sk in SCENARIO_KEYS:
                sd = scen_defs[pk][sk]
                c = disc.shifted(sd["parallel_bp"], sd["slope_bp"], sd["curvature_bp"])
                ref = CapFloorSpec("cap", exp.notional, 0.0, exp.start, exp.end, exp.frequency, exp.day_count,
                                   exp.rate_style, model, vol, amortization=exp.amortization,
                                   known_fixings=exp.known_fixings, accrued_factor=exp.accrued_factor)
                flows = []
                pv_expo = pv_deriv = 0.0
                for i, p in enumerate(ref.schedule()):
                    if p.payment_date <= disc.curve_date:
                        continue
                    R, state = _forward(ref, c, p, i)
                    interest = sgn_expo * p.notional * p.accrual * (R + exp.spread)
                    d_pay = 0.0
                    for sign, spec in ov["legs"]:
                        d_pay += sign * float(terminal_payoff(spec.kind, p.notional, p.accrual, R, spec.strike))
                    dfp = c.df_date(p.payment_date)
                    pv_expo += interest * dfp
                    pv_deriv += d_pay * dfp
                    flows.append({"period": i + 1, "payment_date": p.payment_date, "rate": R, "rate_state": state,
                                  "exposure_flow": interest, "derivative_flow": d_pay, "net_flow": interest + d_pay,
                                  "effective_rate": (interest + d_pay) / (p.notional * p.accrual) * sgn_expo})
                mtm = sum(sign * price_capfloor(spec, c)["value"] for sign, spec in ov["legs"])
                net_pv = pv_expo + pv_deriv - prem
                row["scenarios"][sk] = {
                    **sd, "flows": flows,
                    "exposure_flows_total": sum(f["exposure_flow"] for f in flows),
                    "derivative_flows_total": sum(f["derivative_flow"] for f in flows),
                    "pv_exposure": pv_expo, "pv_derivative_flows": pv_deriv, "premium": prem,
                    "derivative_economic_pnl": pv_deriv - prem, "net_pv": net_pv,
                    "derivative_mtm_after_shock": mtm,
                    "max_effective_rate": max((f["effective_rate"] for f in flows), default=None),
                    "min_effective_rate": min((f["effective_rate"] for f in flows), default=None),
                    "unhedged_risks": _rate_unhedged(ov, exp),
                }
                if sk == "base":
                    base_net = net_pv
            unhedged_base = None
            for sk in SCENARIO_KEYS:
                row["scenarios"][sk]["vs_base"] = row["scenarios"][sk]["net_pv"] - base_net
            results.append(row)
        # Protección relativa a "Sin cobertura" en cada escenario (misma condición de mercado)
        rows_p = [r for r in results if r["profile"] == pk]
        un = next(r for r in rows_p if r["strategy"] == "Sin cobertura")
        for r in rows_p:
            for sk in SCENARIO_KEYS:
                loss_un = un["scenarios"][sk]["net_pv"] - un["scenarios"]["base"]["net_pv"]
                gain = r["scenarios"][sk]["net_pv"] - un["scenarios"][sk]["net_pv"]
                r["scenarios"][sk]["vs_unhedged"] = gain
                r["scenarios"][sk]["protection_ratio"] = (gain / -loss_un) if loss_un < 0 else None
            worst = r["scenarios"]["estres_adverso_severo"]["vs_unhedged"]
            r["constraints"] = {"budget_ok": r["initial_cost_pct"] <= prof.hedge_budget + 1e-12,
                                "compatible": r["economic_function"] != "no_compatible",
                                "improves_stress": worst > 0 if r["strategy"] != "Sin cobertura" else None}
    return {"exposure": {**exp.__dict__, "start": exp.start, "end": exp.end,
                         "main_risk": "alza de tasas" if exp.kind == "pasivo" else "baja de tasas"},
            "curve": {"name": disc.name, "date": disc.curve_date, "source": disc.source, "origin": disc.origin,
                      "nodes": disc.table()},
            "model": model, "vol": vol, "vol_origin": vol_origin,
            "scenario_definitions": scen_defs, "evaluations": results,
            "n_evaluations": len(results) * len(SCENARIO_KEYS),
            "method_notes": [
                "Tasas realizadas = forwards de la curva desplazada (hipótesis de escenario, no pronóstico).",
                "Primas teóricas calculadas con la curva base y la volatilidad indicada; no son cotizaciones.",
                "Caps/floors modelados como instrumentos OTC parametrizados.",
                "Mismo choque de curva para todas las alternativas dentro de cada perfil.",
            ]}


def _rate_unhedged(ov, exp):
    risks = []
    if not ov["legs"]:
        risks.append("Exposición total a movimientos de la tasa de referencia")
    else:
        risks.append("Riesgo de contraparte del derivado OTC")
        risks.append("Margen contractual (spread) no cubierto por el derivado")
        if any(sign < 0 for sign, _ in ov["legs"]):
            risks.append("Se renuncia a beneficios por movimientos favorables más allá del strike vendido")
        if exp.rate_style == "compounded_in_arrears":
            risks.append("La tasa compuesta se conoce al final del periodo: incertidumbre de flujo hasta el pago")
    return risks


# ======================================================================== comparación

def rank(evaluations: list[dict], criterion: str, profile: str | None = None, descending: bool = True) -> list[dict]:
    """Ordena por un criterio explícito: 'stress_pnl', 'cost', 'base_pnl', 'upside',
    'protection_stress'. Sin puntuaciones opacas."""
    rows = [r for r in evaluations if profile is None or r["profile"] == profile]

    def key(r):
        s = r["scenarios"]
        if criterion == "stress_pnl":
            return s["estres_adverso_severo"].get("combined_pnl", s["estres_adverso_severo"].get("net_pv"))
        if criterion == "cost":
            return -r["initial_cost"]
        if criterion == "base_pnl":
            return s["base"].get("combined_pnl", s["base"].get("net_pv"))
        if criterion == "upside":
            return s["favorable_extremo"].get("combined_pnl", s["favorable_extremo"].get("net_pv"))
        if criterion == "protection_stress":
            v = s["estres_adverso_severo"].get("protection_ratio")
            return -1e9 if v is None else v
        raise ValueError(f"criterio desconocido: {criterion}")
    return sorted(rows, key=key, reverse=descending)
