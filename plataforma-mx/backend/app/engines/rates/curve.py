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
