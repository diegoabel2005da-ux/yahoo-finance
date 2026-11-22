"""Curvas de tasas (sección 12.6).

La curva se construye EXCLUSIVAMENTE a partir de puntos importados/verificados
(tasas cero o factores de descuento por plazo). No se extrapola en silencio: fuera del
último nodo se aplica tasa cero plana y se marca `extrapolated=True`.

Tiempo interno: t = días/365 desde la fecha de la curva (ACT/365F).
Tasa cero interna: compuesta continuamente.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from .daycount import year_fraction


def to_continuous(rate: float, t: float, compounding: str, day_count_fraction: float | None = None) -> float:
    """Convierte una tasa cotizada a cero continua. compounding: 'continua', 'simple',
    'anual', 'semestral', 'trimestral', 'mensual', 'periodo_28d'.
    Para 'simple' se usa la fracción de la convención del dato (p.ej. ACT/360)."""
    if t <= 0:
        return rate
    if compounding == "continua":
        return rate
    if compounding == "simple":
        a = day_count_fraction if day_count_fraction is not None else t
        return math.log(1 + rate * a) / t
    m = {"anual": 1, "semestral": 2, "trimestral": 4, "mensual": 12, "periodo_28d": 360 / 28}[compounding]
    return m * math.log(1 + rate / m)


@dataclass
class ZeroCurve:
    curve_date: date
    times: np.ndarray            # años ACT/365F, crecientes, > 0
    zero_rates: np.ndarray       # continuas
    interpolation: str = "log_linear_df"  # o 'linear_zero'
    name: str = "curva"
    source: str = ""
    origin: str = "observado_proveedor_secundario"
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        self.times = np.asarray(self.times, float)
        self.zero_rates = np.asarray(self.zero_rates, float)
        if len(self.times) < 2:
            raise ValueError("una curva requiere al menos 2 nodos; con menos no se construye curva")
        if np.any(np.diff(self.times) <= 0) or self.times[0] <= 0:
            raise ValueError("los plazos deben ser positivos y estrictamente crecientes")
        if self.interpolation not in ("log_linear_df", "linear_zero"):
            raise ValueError("interpolación no soportada")

    # ---- constructores ----
    @classmethod
    def from_points(cls, curve_date: date, points: list[dict], quote_kind: str = "zero_rate",
                    compounding: str = "continua", day_count: str = "ACT/360", **kw) -> "ZeroCurve":
        """points: [{"date": date | "days": int, "value": float}] con value en decimal
        (tasa) o factor de descuento."""
        ts, zs = [], []
        for p in sorted(points, key=lambda p: p.get("days") or (p["date"] - curve_date).days):
            days = p.get("days") if p.get("days") is not None else (p["date"] - curve_date).days
            d_end = curve_date + timedelta(days=days)
            t = days / 365.0
            if quote_kind == "discount_factor":
                if not (0 < p["value"] <= 1.5):
                    raise ValueError(f"factor de descuento inválido: {p['value']}")
                z = -math.log(p["value"]) / t
            else:
                z = to_continuous(p["value"], t, compounding, year_fraction(curve_date, d_end, day_count))
            ts.append(t)
            zs.append(z)
        return cls(curve_date, np.array(ts), np.array(zs), **kw)

    def with_rates(self, zero_rates) -> "ZeroCurve":
        return ZeroCurve(self.curve_date, self.times.copy(), np.asarray(zero_rates, float), self.interpolation,
                         self.name, self.source, self.origin, dict(self.meta))

    # ---- consultas ----
    def zero(self, t: float) -> float:
        if t <= self.times[0]:
            return float(self.zero_rates[0])
        if t >= self.times[-1]:
            return float(self.zero_rates[-1])
        if self.interpolation == "linear_zero":
            return float(np.interp(t, self.times, self.zero_rates))
        # log-lineal en DF ⇔ lineal en z·t (forward instantánea constante a tramos)
        zt = np.interp(t, self.times, self.zero_rates * self.times)
        return float(zt / t)

    def df(self, t: float) -> float:
        if t <= 0:
            return 1.0
        return math.exp(-self.zero(t) * t)

    def t_of(self, d: date) -> float:
        return (d - self.curve_date).days / 365.0

    def df_date(self, d: date) -> float:
        return self.df(self.t_of(d))

    def is_extrapolated(self, t: float) -> bool:
        return t > self.times[-1] + 1e-12 or t < 0

    def forward_simple(self, d1: date, d2: date, day_count: str = "ACT/360") -> float:
        """F(d1,d2) = (P(d1)/P(d2) − 1)/α(d1,d2)"""
        a = year_fraction(d1, d2, day_count)
        return (self.df_date(d1) / self.df_date(d2) - 1) / a

    # ---- desplazamientos ----
    def shifted(self, parallel_bp: float = 0.0, slope_bp: float = 0.0, curvature_bp: float = 0.0,
                pivot: float | None = None) -> "ZeroCurve":
        """Choques en tasa cero (pb):
        paralelo: +p; pendiente: +s·(t − pivote)/(t_max − t_min) (gira en el pivote);
        curvatura: +c·(1 − |2(t−t_min)/(t_max−t_min) − 1|) (máximo en la mitad del tramo)."""
        t0, t1 = self.times[0], self.times[-1]
        pv = pivot if pivot is not None else (t0 + t1) / 2
        span = t1 - t0
        x = (self.times - t0) / span
        shock = parallel_bp + slope_bp * (self.times - pv) / span + curvature_bp * (1 - np.abs(2 * x - 1))
        return self.with_rates(self.zero_rates + shock / 1e4)

    def key_rate_bumped(self, i: int, bp: float = 1.0) -> "ZeroCurve":
        z = self.zero_rates.copy()
        z[i] += bp / 1e4
        return self.with_rates(z)

    def table(self) -> list[dict]:
        return [{"t": float(t), "days": int(round(t * 365)), "zero_cont": float(z), "df": math.exp(-z * t)}
                for t, z in zip(self.times, self.zero_rates)]


def bootstrap_government_curve(cetes: list[tuple[int, float]], bonds: list[tuple[float, float]],
                               coupon_days: int = 182) -> list[dict]:
    """Curva cero gubernamental: CETES (cupón cero) + Bonos M (rendimientos tratados como tasas PAR).

    - CETES: DF(d) = 1 / (1 + y·d/360), con y = rendimiento simple publicado (decimal).
    - Bonos M: cupón semestral c_k = y_par(t_k)·182/360 pagado cada 182 días; la tasa par en cada fecha
      de cupón se interpola linealmente entre nodos (la tasa par a 364 días se deriva de los CETES).
      Condición par: 1 = c·Σ_{j≤k} DF_j + DF_k  ⇒  DF_k = (1 − c·Σ_{j<k} DF_j) / (1 + c).
    Supuestos documentados: plazo nominal de cada subasta (3, 5, 10, 20, 30 años = 182·2·años días) y
    rendimiento de subasta ≈ tasa par. Devuelve nodos [{"days", "value"(DF)}].
    """
    if len(cetes) < 2:
        raise ValueError("se requieren al menos 2 nodos de CETES")
    cetes = sorted(cetes)
    dfs = {d: 1.0 / (1.0 + y * d / 360.0) for d, y in cetes}
    nodes = [{"days": d, "value": v} for d, v in dfs.items()]
    if not bonds:
        return nodes
    # DF en fechas de cupón dentro del primer año, interpolando log-linealmente los CETES
    cdays, cdfs = zip(*sorted(dfs.items()))

    def df_cetes(d):
        if d <= cdays[0]:
            return dfs[cdays[0]] ** (d / cdays[0])
        for i in range(1, len(cdays)):
            if d <= cdays[i]:
                w = (d - cdays[i - 1]) / (cdays[i] - cdays[i - 1])
                return math.exp((1 - w) * math.log(cdfs[i - 1]) + w * math.log(cdfs[i]))
        raise ValueError("fecha de cupón fuera de los CETES")

    a = coupon_days / 360.0
    df_cpn = [df_cetes(coupon_days * k) for k in (1, 2) if coupon_days * k <= cdays[-1]]
    if len(df_cpn) < 2:
        raise ValueError("los CETES deben cubrir al menos 364 días para enlazar con los Bonos M")
    par_1y = (1 - df_cpn[1]) / (a * (df_cpn[0] + df_cpn[1]))
    par_pts = [(2 * coupon_days, par_1y)] + sorted((round(y * 2) * coupon_days, r) for y, r in bonds)
    last_k = par_pts[-1][0] // coupon_days
    for k in range(3, last_k + 1):
        d = k * coupon_days
        for (d0, r0), (d1, r1) in zip(par_pts, par_pts[1:]):
            if d0 <= d <= d1:
                par = r0 + (r1 - r0) * (d - d0) / (d1 - d0)
                break
        c = par * a
        df_k = (1 - c * sum(df_cpn)) / (1 + c)
        if not (0 < df_k < df_cpn[-1]):
            raise ValueError(f"bootstrapping inconsistente en {d} días (DF={df_k:.6f}); revise los rendimientos")
        df_cpn.append(df_k)
        nodes.append({"days": d, "value": df_k})
    return sorted(nodes, key=lambda n: n["days"])


def forward_diagnostics(nodes: list[dict], step_days: int = 364, threshold: float = 0.03) -> dict:
    """Forwards continuas a ~1 año entre nodos de la curva (DF). Marca tramos cuya forward excede en más
    de `threshold` la tasa cero máxima de la curva hasta ese punto: señal de inestabilidad del bootstrapping."""
    df = {n["days"]: n["value"] for n in nodes}
    days = sorted(df)
    out, flagged = [], []
    max_zero = 0.0
    for d0 in days:
        d1 = next((d for d in days if d >= d0 + step_days), None)
        if d1 is None:
            break
        fwd = math.log(df[d0] / df[d1]) / ((d1 - d0) / 365)
        max_zero = max(max_zero, -math.log(df[d0]) / (d0 / 365))
        out.append({"from_days": d0, "to_days": d1, "forward_cont": fwd})
        if fwd > max_zero + threshold:
            flagged.append({"from_days": d0, "to_days": d1, "forward_cont": fwd})
    return {"forwards": out, "flagged": flagged,
            "max_forward": max((f["forward_cont"] for f in out), default=None)}
