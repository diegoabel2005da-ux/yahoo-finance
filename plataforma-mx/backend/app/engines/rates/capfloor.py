"""Caps y floors sobre tasas en pesos (sección 12).

Un cap es una suma de caplets y un floor una suma de floorlets. Flujos terminales:
    caplet_i   = N_i · α_i · max(R_i − K, 0)
    floorlet_i = N_i · α_i · max(K − R_i, 0)
pagados al final del periodo i.

Modelos (por caplet, sobre la tasa forward del periodo bajo la medida T_pago):
    Black-76:  V = N α P(0,T_p) [F N(d1) − K N(d2)],  d1 = [ln(F/K) + ½σ²τ]/(σ√τ)
    Bachelier: V = N α P(0,T_p) [(F − K) N(d) + σ_n √τ φ(d)],  d = (F − K)/(σ_n √τ)
(floorlets por simetría). Con desplazamiento s (Black desplazado) se usa F+s y K+s.

Tiempo de varianza τ:
- Tasa fijada al inicio (p. ej. TIIE a 28 días): τ = t_fijación.
- Tasa overnight compuesta en atraso (p. ej. TIIE de Fondeo compuesta): la tasa se
  conoce hasta el fin del periodo. Se usa la aproximación de Lyashenko–Mercurio (2019)
  con volatilidad constante:  τ = t_s + (t_e − t_s)/3 si t_s ≥ 0;  si el periodo ya inició
  τ = t_e³ / [3 (t_e − t_s)²] y la parte devengada entra como factor conocido.
Esto evita aplicar mecánicamente la fórmula de tasa fijada al inicio a una tasa en atraso.

Toda prima calculada aquí es TEÓRICA (origen 'resultado_de_modelo'). Un cap/floor así
valorado es un instrumento OTC parametrizado; no se afirma que cotice en MexDer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

from ...core.provenance import DataOrigin
from .curve import ZeroCurve
from .daycount import HolidayCalendar, Period, build_schedule


# ---------------------------------------------------------------- fórmulas unitarias

def black76(kind: str, F: float, K: float, tau: float, sigma: float, shift: float = 0.0) -> float:
    """Valor sin descontar ni escalar: E[max(±(R−K),0)] bajo lognormal (desplazada)."""
    Fs, Ks = F + shift, K + shift
    if Fs <= 0 or Ks <= 0:
        raise ValueError("Black-76 requiere F+s>0 y K+s>0; use Bachelier o un desplazamiento")
    if tau <= 0 or sigma <= 0:
        return max(F - K, 0) if kind == "cap" else max(K - F, 0)
    sq = sigma * math.sqrt(tau)
    d1 = (math.log(Fs / Ks) + 0.5 * sq * sq) / sq
    d2 = d1 - sq
    if kind == "cap":
        return Fs * norm.cdf(d1) - Ks * norm.cdf(d2)
    return Ks * norm.cdf(-d2) - Fs * norm.cdf(-d1)


def bachelier(kind: str, F: float, K: float, tau: float, sigma_n: float) -> float:
    if tau <= 0 or sigma_n <= 0:
        return max(F - K, 0) if kind == "cap" else max(K - F, 0)
    sq = sigma_n * math.sqrt(tau)
    d = (F - K) / sq
    if kind == "cap":
        return (F - K) * norm.cdf(d) + sq * norm.pdf(d)
    return (K - F) * norm.cdf(-d) + sq * norm.pdf(d)


def unit_value(model: str, kind: str, F, K, tau, vol, shift=0.0):
    if model == "black76":
        return black76(kind, F, K, tau, vol, shift)
    if model == "bachelier":
        return bachelier(kind, F, K, tau, vol)
    raise ValueError(f"modelo desconocido: {model}")


def terminal_payoff(kind: str, notional: float, accrual: float, R, K: float):
    R = np.asarray(R, float)
    return notional * accrual * (np.maximum(R - K, 0) if kind == "cap" else np.maximum(K - R, 0))


# ---------------------------------------------------------------- especificación

@dataclass
class CapFloorSpec:
    kind: str                         # 'cap' | 'floor'
    notional: float
    strike: float                     # decimal, p. ej. 0.10
    start: date
    end: date
    frequency: str = "28D"
    day_count: str = "ACT/360"
    rate_style: str = "term_fixed_in_advance"   # o 'compounded_in_arrears'
    model: str = "black76"            # o 'bachelier'
    vol: float | list[float] = 0.2    # lognormal (decimal) o normal (decimal de tasa, p. ej. 0.01 = 100pb)
    vol_origin: str = DataOrigin.USER_ASSUMPTION.value
    shift: float = 0.0
    amortization: list[float] | None = None
    fixing_lag_bd: int = 1
    known_fixings: dict[int, float] = field(default_factory=dict)  # periodo → tasa fijada
    accrued_factor: dict[int, float] = field(default_factory=dict)  # periodo en curso (atraso)
    reference_rate: str = "TIIE_28"
    upfront_premium_observed: Optional[float] = None
    premium_origin: Optional[str] = None
    calendar: HolidayCalendar = field(default_factory=HolidayCalendar)

    def schedule(self) -> list[Period]:
        lag = 0 if self.rate_style == "compounded_in_arrears" else self.fixing_lag_bd
        sch = build_schedule(self.start, self.end, self.frequency, self.notional, self.day_count,
                             self.calendar, fixing_lag_bd=lag, amortization=self.amortization)
        if self.rate_style == "compounded_in_arrears":
            for p in sch:
                p.fixing_date = p.accrual_end
        return sch

    def vol_for(self, i: int) -> float:
        return self.vol[i] if isinstance(self.vol, list) else self.vol


def _tau(spec: CapFloorSpec, curve: ZeroCurve, p: Period) -> float:
    ts, te = curve.t_of(p.accrual_start), curve.t_of(p.accrual_end)
    if spec.rate_style == "compounded_in_arrears":
        if ts >= 0:
            return ts + (te - ts) / 3.0
        if te <= 0:
            return 0.0
        return te ** 3 / (3 * (te - ts) ** 2)
    return max(curve.t_of(p.fixing_date), 0.0)


def _forward(spec: CapFloorSpec, fwd: ZeroCurve, p: Period, i: int) -> tuple[float, str]:
    """Tasa forward del periodo o fijación conocida. Devuelve (tasa, estado)."""
    vd = fwd.curve_date
    if spec.rate_style == "term_fixed_in_advance":
        if p.fixing_date <= vd:
            if i not in spec.known_fixings:
                raise ValueError(f"periodo {i + 1}: la tasa ya fijó el {p.fixing_date} y no se proporcionó la fijación")
            return spec.known_fixings[i], "fijada"
        return fwd.forward_simple(p.accrual_start, p.accrual_end, spec.day_count), "forward"
    # Compuesta en atraso
    if p.accrual_end <= vd:
        if i not in spec.known_fixings:
            raise ValueError(f"periodo {i + 1}: periodo concluido sin tasa compuesta observada")
        return spec.known_fixings[i], "fijada"
    if p.accrual_start < vd:
        if i not in spec.accrued_factor:
            raise ValueError(f"periodo {i + 1} en curso: falta el factor devengado Π(1+r_i d_i/360) observado")
        A = spec.accrued_factor[i]
        return (A / fwd.df_date(p.accrual_end) - 1) / p.accrual, "parcialmente_observada"
    return fwd.forward_simple(p.accrual_start, p.accrual_end, spec.day_count), "forward"


def price_capfloor(spec: CapFloorSpec, disc: ZeroCurve, fwd: ZeroCurve | None = None) -> dict:
    """Valor presente de un cap/floor como suma de caplets/floorlets."""
    fwd = fwd or disc
    if spec.kind not in ("cap", "floor"):
        raise ValueError("kind debe ser 'cap' o 'floor'")
    vd = disc.curve_date
    rows, total = [], 0.0
    warnings = []
    for i, p in enumerate(spec.schedule()):
        if p.payment_date <= vd:
            continue  # flujo ya pagado: no forma parte del valor
        F, state = _forward(spec, fwd, p, i)
        tau = _tau(spec, disc, p) if state != "fijada" else 0.0
        dfp = disc.df_date(p.payment_date)
        vol = spec.vol_for(i)
        u = unit_value(spec.model, spec.kind, F, spec.strike, tau, vol, spec.shift)
        v = p.notional * p.accrual * dfp * u
        if disc.is_extrapolated(disc.t_of(p.payment_date)):
            warnings.append(f"periodo {i + 1}: pago fuera del último nodo de la curva (tasa plana extrapolada)")
        total += v
        rows.append({"period": i + 1, "accrual_start": p.accrual_start, "accrual_end": p.accrual_end,
                     "fixing_date": p.fixing_date, "payment_date": p.payment_date, "notional": p.notional,
                     "accrual": p.accrual, "forward": F, "rate_state": state, "tau": tau, "vol": vol,
                     "discount_factor": dfp, "value": v,
                     "intrinsic_on_forward": p.notional * p.accrual * dfp *
                     (max(F - spec.strike, 0) if spec.kind == "cap" else max(spec.strike - F, 0))})
    return {"kind": spec.kind, "model": spec.model, "rate_style": spec.rate_style, "value": total,
            "value_per_notional_bp": total / spec.notional * 1e4 if spec.notional else None,
            "components": rows, "origin": DataOrigin.MODEL_OUTPUT.value, "vol_origin": spec.vol_origin,
            "instrument_status": "OTC parametrizado (teórico); no se afirma cotización en MexDer",
            "observed_premium": spec.upfront_premium_observed, "observed_premium_origin": spec.premium_origin,
            "warnings": warnings}


def swap_value_from_forwards(spec: CapFloorSpec, disc: ZeroCurve, fwd: ZeroCurve | None = None) -> float:
    """Σ N α P (F − K): valor de un swap pagador de fija K. Paridad: Cap − Floor = Swap."""
    fwd = fwd or disc
    tot = 0.0
    for i, p in enumerate(spec.schedule()):
        if p.payment_date <= disc.curve_date:
            continue
        F, _ = _forward(spec, fwd, p, i)
        tot += p.notional * p.accrual * disc.df_date(p.payment_date) * (F - spec.strike)
    return tot


def _clone(spec: CapFloorSpec, **kw) -> CapFloorSpec:
    d = dict(spec.__dict__)
    d.update(kw)
    return CapFloorSpec(**d)


def roll_curve(c: ZeroCurve, days: int = 1) -> ZeroCurve:
    """Avanza la fecha de valuación manteniendo constantes las forwards:
    P_new(T) = P_old(T)/P_old(δ)."""
    dlt = days / 365.0
    keep = c.times > dlt + 1e-9
    t_new = c.times[keep] - dlt
    df_old = np.exp(-c.zero_rates[keep] * c.times[keep])
    z_new = -np.log(df_old / c.df(dlt)) / t_new
    return ZeroCurve(c.curve_date + timedelta(days=days), t_new, z_new, c.interpolation, c.name, c.source, c.origin)


def sensitivities(spec: CapFloorSpec, disc: ZeroCurve, fwd: ZeroCurve | None = None, bp: float = 1.0) -> dict:
    """Sensibilidades por diferencias finitas centrales (se reconstruyen las forwards de la
    curva desplazada):
    - PV01 paralelo (MXN por +1 pb en tasas cero de ambas curvas).
    - Gamma de tasas (MXN por pb²).
    - Key-rate PV01 por nodo.
    - Vega (MXN por +1 punto porcentual de vol lognormal, o +1 pb de vol normal).
    - Theta (MXN por 1 día natural, forwards constantes).
    - Pendiente y curvatura (MXN por 1 pb de choque, ver ZeroCurve.shifted)."""
    fwd = fwd or disc
    same = fwd is disc
    base = price_capfloor(spec, disc, fwd)["value"]

    def pv(dc, fc):
        return price_capfloor(spec, dc, fc)["value"]

    up = pv(disc.shifted(bp), disc.shifted(bp) if same else fwd.shifted(bp))
    dn = pv(disc.shifted(-bp), disc.shifted(-bp) if same else fwd.shifted(-bp))
    pv01 = (up - dn) / (2 * bp)
    gamma = (up - 2 * base + dn) / (bp ** 2)
    krs = []
    for i, t in enumerate(disc.times):
        dcu, dcd = disc.key_rate_bumped(i, bp), disc.key_rate_bumped(i, -bp)
        u = pv(dcu, dcu if same else fwd)
        d = pv(dcd, dcd if same else fwd)
        krs.append({"node_t": float(t), "node_days": int(round(t * 365)), "pv01": (u - d) / (2 * bp)})
    dv = 0.01 if spec.model == "black76" else 0.0001
    vols_up = [v + dv for v in spec.vol] if isinstance(spec.vol, list) else spec.vol + dv
    vols_dn = [max(v - dv, 1e-8) for v in spec.vol] if isinstance(spec.vol, list) else max(spec.vol - dv, 1e-8)
    vega = (price_capfloor(_clone(spec, vol=vols_up), disc, fwd)["value"]
            - price_capfloor(_clone(spec, vol=vols_dn), disc, fwd)["value"]) / 2
    try:
        rd = roll_curve(disc)
        theta = pv(rd, rd if same else roll_curve(fwd)) - base
    except ValueError as e:
        theta = None
        _ = e
    slope = (pv(disc.shifted(slope_bp=bp), disc.shifted(slope_bp=bp) if same else fwd.shifted(slope_bp=bp)) - base) / bp
    curv = (pv(disc.shifted(curvature_bp=bp), disc.shifted(curvature_bp=bp) if same else fwd.shifted(curvature_bp=bp)) - base) / bp
    return {"value": base, "pv01_parallel": pv01, "gamma_per_bp2": gamma, "key_rate_pv01": krs,
            "vega": vega, "vega_unit": "por 1 punto porcentual de vol lognormal" if spec.model == "black76"
            else "por 1 pb de vol normal", "theta_1d": theta, "slope_per_bp": slope, "curvature_per_bp": curv,
            "method": f"Diferencias finitas centrales, choque {bp} pb en tasas cero continuas"}


def implied_flat_vol(spec: CapFloorSpec, observed_premium: float, disc: ZeroCurve, fwd: ZeroCurve | None = None,
                     premium_origin: str = DataOrigin.OBSERVED_OFFICIAL.value) -> dict:
    """Volatilidad plana implícita de una prima OBSERVADA (no de una prima de modelo)."""
    if premium_origin == DataOrigin.MODEL_OUTPUT.value:
        raise ValueError("una prima teórica no puede usarse para calibrar volatilidad implícita de mercado")
    lo, hi = (1e-4, 5.0) if spec.model == "black76" else (1e-6, 0.2)
    f = lambda v: price_capfloor(_clone(spec, vol=v), disc, fwd)["value"] - observed_premium
    if f(lo) > 0 or f(hi) < 0:
        raise ValueError("la prima observada no es alcanzable con volatilidades razonables")
    v = brentq(f, lo, hi, xtol=1e-12)
    return {"implied_flat_vol": v, "model": spec.model, "premium_origin": premium_origin}


def compare_models(spec: CapFloorSpec, disc: ZeroCurve, normal_vol: float, lognormal_vol: float,
                   fwd: ZeroCurve | None = None) -> dict:
    b = price_capfloor(_clone(spec, model="black76", vol=lognormal_vol), disc, fwd)
    n = price_capfloor(_clone(spec, model="bachelier", vol=normal_vol), disc, fwd)
    return {"black76": b["value"], "bachelier": n["value"], "difference": b["value"] - n["value"],
            "explanation": ("Black-76 supone tasas forward lognormales: la vol absoluta crece con el "
                            "nivel de la tasa y el sesgo favorece strikes altos. Bachelier supone cambios "
                            "normales (en pb) independientes del nivel, admite tasas negativas y asigna "
                            "más valor a strikes bajos/floors. Con vols equivalentes ATM (σ_n ≈ σ·F) las "
                            "primas ATM son cercanas y difieren fuera del dinero.")}
