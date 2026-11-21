"""Constructor de estrategias sobre acciones (sección 13).

Una estrategia es un conjunto de legs (acciones, calls, puts, futuros). En el contexto de
cobertura, la estrategia es el OVERLAY de derivados que se añade a la exposición; la
exposición se modela aparte para mostrar siempre el resultado combinado.

Valuación:
- Al vencimiento de una opción: valor intrínseco (payoff).
- Antes del vencimiento: revaluación con modelo (BSM europea / CRR americana) con el
  tiempo remanente. Nunca se usa el payoff terminal para valorar antes del vencimiento.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from ..core.provenance import DataOrigin
from .options import bsm_price, crr_price

ECONOMIC_FUNCTIONS = {
    "cobertura_directa": "Cobertura directa",
    "cobertura_parcial": "Cobertura parcial",
    "cobertura_cruzada": "Cobertura cruzada",
    "volatilidad": "Estrategia de volatilidad",
    "ingreso_primas": "Estrategia de ingreso por primas",
    "no_compatible": "Estrategia de riesgo no compatible con la exposición declarada",
    "sin_cobertura": "Posición sin cobertura (referencia)",
}


@dataclass
class Leg:
    kind: str                     # stock | call | put | future
    qty: float                    # contratos (o acciones si stock); signo: + largo, − corto
    multiplier: float = 1.0
    strike: Optional[float] = None
    expiry_years: Optional[float] = None
    style: str = "europea"        # sólo opciones
    premium: Optional[float] = None   # por unidad de subyacente
    premium_origin: str = DataOrigin.USER_ASSUMPTION.value
    entry_price: Optional[float] = None  # acciones / futuros
    underlying: str = ""
    contract_symbol: Optional[str] = None
    contract_status: str = "teorico_simulacion"  # o 'listado_verificado'
    commission: float = 0.0

    def units(self) -> float:
        return self.qty * self.multiplier

    def initial_cash(self) -> float:
        """Flujo inicial (negativo = desembolso). Futuros: 0 (la AIM es garantía, no costo)."""
        if self.kind in ("call", "put"):
            return -self.units() * self.premium - abs(self.commission)
        if self.kind == "stock":
            return -self.units() * self.entry_price - abs(self.commission)
        return -abs(self.commission)

    def value(self, S: float, t: float, sigma: float, r: float, q: float,
              futures_basis: float = 0.0) -> float:
        """Valor de mercado (o P&L acumulado para futuros) en el tiempo t."""
        if self.kind == "stock":
            return self.units() * S
        if self.kind == "future":
            tau = max(self.expiry_years - t, 0.0)
            F = S * math.exp((r - q) * tau) * (1 + futures_basis)
            return self.units() * (F - self.entry_price)
        tau = self.expiry_years - t
        if tau <= 1e-12:
            intr = max(S - self.strike, 0) if self.kind == "call" else max(self.strike - S, 0)
            return self.units() * intr
        if self.style == "americana":
            v = crr_price(self.kind, S, self.strike, tau, r, sigma, q, 200, american=True)["price"]
        else:
            v = bsm_price(self.kind, S, self.strike, tau, r, sigma, q)
        return self.units() * v


@dataclass
class Strategy:
    name: str
    legs: list[Leg]
    economic_function: str = "no_compatible"
    description: str = ""
    warnings: list[str] = field(default_factory=list)
    params: dict = field(default_factory=dict)

    def initial_cash(self) -> float:
        return sum(l.initial_cash() for l in self.legs)

    def pnl(self, S: float, t: float, sigma: float, r: float, q: float, futures_basis: float = 0.0,
            financing: bool = False) -> float:
        """P&L económico del overlay = valor en t + flujo inicial (± costo de financiamiento)."""
        init = self.initial_cash()
        fin = init * (math.exp(r * t) - 1) if financing else 0.0
        return sum(l.value(S, t, sigma, r, q, futures_basis) for l in self.legs) + init + fin

    def option_expiry(self) -> Optional[float]:
        ex = [l.expiry_years for l in self.legs if l.kind in ("call", "put", "future")]
        return min(ex) if ex else None

    def payoff_curve(self, S_grid, t: float, sigma: float, r: float, q: float) -> list[float]:
        return [self.pnl(float(s), t, sigma, r, q) for s in S_grid]

    def breakevens(self, S0: float, t: float, sigma: float, r: float, q: float) -> list[float]:
        grid = np.linspace(S0 * 0.3, S0 * 2.0, 1401)
        pn = np.array(self.payoff_curve(grid, t, sigma, r, q))
        out = []
        for i in range(1, len(grid)):
            if pn[i - 1] == 0:
                out.append(float(grid[i - 1]))
            elif pn[i - 1] * pn[i] < 0:
                out.append(float(grid[i - 1] - pn[i - 1] * (grid[i] - grid[i - 1]) / (pn[i] - pn[i - 1])))
        return out

    def net_option_units(self) -> dict:
        calls = sum(l.units() for l in self.legs if l.kind == "call")
        puts = sum(l.units() for l in self.legs if l.kind == "put")
        return {"calls": calls, "puts": puts}


def validate_strategy(s: Strategy, underlying: str | None = None) -> list[str]:
    """Reglas de validación del constructor manual (sección 13.9)."""
    issues = []
    for i, l in enumerate(s.legs, 1):
        if l.kind not in ("stock", "call", "put", "future"):
            issues.append(f"leg {i}: tipo inválido {l.kind}")
            continue
        if l.qty == 0:
            issues.append(f"leg {i}: cantidad cero")
        if l.multiplier <= 0:
            issues.append(f"leg {i}: multiplicador debe ser positivo")
        if l.kind in ("call", "put"):
            if l.strike is None or l.strike <= 0:
                issues.append(f"leg {i}: strike inválido")
            if l.expiry_years is None or l.expiry_years <= 0:
                issues.append(f"leg {i}: vencimiento inválido")
            if l.premium is None or l.premium < 0:
                issues.append(f"leg {i}: prima faltante o negativa")
        if l.kind == "future":
            if l.expiry_years is None or l.expiry_years <= 0 or l.entry_price is None:
                issues.append(f"leg {i}: futuro sin vencimiento o precio de entrada")
        if l.kind == "stock" and l.entry_price is None:
            issues.append(f"leg {i}: acción sin precio de entrada")
        if underlying and l.underlying and l.underlying != underlying:
            issues.append(f"leg {i}: subyacente {l.underlying} distinto de {underlying} (cobertura cruzada / riesgo de base)")
    # Obligaciones y riesgos elevados
    short_calls = -sum(l.units() for l in s.legs if l.kind == "call" and l.qty < 0)
    long_calls = sum(l.units() for l in s.legs if l.kind == "call" and l.qty > 0)
    stock_units = sum(l.units() for l in s.legs if l.kind == "stock")
    if short_calls > long_calls + max(stock_units, 0) + 1e-9:
        issues.append("ADVERTENCIA: calls vendidas descubiertas — pérdida potencial ilimitada y requerimiento de garantías")
    if any(l.kind == "put" and l.qty < 0 for l in s.legs):
        issues.append("ADVERTENCIA: puts vendidas — obligación de compra al strike y requerimiento de garantías")
    if any(l.kind == "future" for l in s.legs):
        issues.append("Futuros: liquidación diaria de pérdidas/ganancias; requiere AIM y posibles aportaciones adicionales")
    return issues


PremiumFn = Callable[[str, float, float], tuple[float, str]]


def theoretical_premium_fn(S0: float, r: float, q: float, sigma: float, sigma_origin: str) -> PremiumFn:
    """Proveedor de primas TEÓRICAS (BSM). Se etiqueta como resultado de modelo."""
    def f(kind, K, T):
        return bsm_price(kind, S0, K, T, r, sigma, q), DataOrigin.MODEL_OUTPUT.value
    f.description = f"Prima teórica BSM con σ={sigma:.4f} ({sigma_origin}), r={r:.4f}, q={q:.4f}"
    return f


def observed_chain_premium_fn(chain: list[dict], fallback: PremiumFn | None = None) -> PremiumFn:
    """Primas observadas: chain = [{kind, strike, expiry_years, premium, origin}].
    Sin coincidencia exacta se usa el fallback teórico (etiquetado) o se falla."""
    def f(kind, K, T):
        for c in chain:
            if c["kind"] == kind and abs(c["strike"] - K) < 1e-9 and abs(c["expiry_years"] - T) < 1e-6:
                return c["premium"], c.get("origin", DataOrigin.OBSERVED_SECONDARY.value)
        if fallback:
            return fallback(kind, K, T)
        raise ValueError(f"no existe prima observada para {kind} K={K} T={T:.4f}")
    return f


def build_template(name: str, S0: float, T: float, contracts: float, multiplier: float, premium: PremiumFn,
                   strikes: dict | None = None, exposure_sign: int = 1, underlying: str = "",
                   futures_price: float | None = None, futures_status: str = "teorico_simulacion",
                   commission_per_contract: float = 0.0, hedge_ratio: float = 1.0) -> Strategy:
    """Plantillas. `strikes` admite claves k_put, k_call, k1, k2, k3 (valores absolutos).
    `exposure_sign`: +1 exposición larga en el subyacente, −1 corta."""
    k = strikes or {}
    n = contracts

    def opt(kind, K, qty):
        p, origin = premium(kind, K, T)
        return Leg(kind, qty, multiplier, K, T, premium=p, premium_origin=origin, underlying=underlying,
                   commission=commission_per_contract * abs(qty))

    def fut(qty):
        return Leg("future", qty, multiplier, expiry_years=T, entry_price=futures_price, underlying=underlying,
                   contract_status=futures_status, commission=commission_per_contract * abs(qty))

    es = exposure_sign
    partial = hedge_ratio < 0.999
    hedge_fn = "cobertura_parcial" if partial else "cobertura_directa"
    nh = n * hedge_ratio
    T_ = {
        "protective_put": lambda: Strategy(
            "Protective Put", [opt("put", k.get("k_put", S0), nh)], hedge_fn,
            "Put comprada sobre acciones largas: piso de pérdida a cambio de la prima."),
        "protective_call": lambda: Strategy(
            "Call protectora", [opt("call", k.get("k_call", S0), nh)], hedge_fn,
            "Call comprada sobre exposición corta: techo al costo de recompra."),
        "covered_call": lambda: Strategy(
            "Covered Call", [opt("call", k.get("k_call", S0 * 1.05), -nh)], "ingreso_primas",
            "Call vendida sobre acciones largas: la prima amortigua caídas sólo en su monto y limita "
            "la ganancia por encima del strike. No protege contra pérdidas grandes."),
        "collar": lambda: Strategy(
            "Collar", [opt("put", k.get("k_put", S0 * 0.95), nh), opt("call", k.get("k_call", S0 * 1.05), -nh)]
            if es > 0 else [opt("call", k.get("k_call", S0 * 1.05), nh), opt("put", k.get("k_put", S0 * 0.95), -nh)],
            hedge_fn, "Put comprada financiada con call vendida: banda de resultados entre ambos strikes."),
        "short_futures": lambda: Strategy(
            "Venta de futuros", [fut(-nh)], hedge_fn if es > 0 else "no_compatible",
            "Fija el precio de venta futuro; elimina pérdidas y ganancias (salvo base)."),
        "long_futures": lambda: Strategy(
            "Compra de futuros", [fut(nh)], hedge_fn if es < 0 else "no_compatible",
            "Fija el precio de compra futuro."),
        "long_straddle": lambda: Strategy(
            "Long Straddle", [opt("call", k.get("k1", S0), n), opt("put", k.get("k1", S0), n)], "volatilidad",
            "Gana con movimientos grandes en cualquier dirección; pierde las primas si el precio no se mueve."),
        "short_straddle": lambda: Strategy(
            "Short Straddle", [opt("call", k.get("k1", S0), -n), opt("put", k.get("k1", S0), -n)], "volatilidad",
            "Cobra primas; pérdidas potencialmente ilimitadas ante movimientos grandes."),
        "long_strangle": lambda: Strategy(
            "Long Strangle", [opt("put", k.get("k_put", S0 * 0.95), n), opt("call", k.get("k_call", S0 * 1.05), n)],
            "volatilidad", "Como el straddle con strikes fuera del dinero: más barato, requiere mayor movimiento."),
        "short_strangle": lambda: Strategy(
            "Short Strangle", [opt("put", k.get("k_put", S0 * 0.95), -n), opt("call", k.get("k_call", S0 * 1.05), -n)],
            "volatilidad", "Cobra primas; pérdidas grandes si el precio sale de la banda."),
        "long_call_butterfly": lambda: _fly("call", +1, "Long Call Butterfly"),
        "short_call_butterfly": lambda: _fly("call", -1, "Short Call Butterfly"),
        "long_put_butterfly": lambda: _fly("put", +1, "Long Put Butterfly"),
        "short_put_butterfly": lambda: _fly("put", -1, "Short Put Butterfly"),
    }

    def _fly(kind, sgn, label):
        k1, k2, k3 = k.get("k1", S0 * 0.95), k.get("k2", S0), k.get("k3", S0 * 1.05)
        if not (k1 < k2 < k3):
            raise ValueError("butterfly requiere k1 < k2 < k3")
        if abs((k2 - k1) - (k3 - k2)) > 1e-9:
            # mariposa no simétrica: se ajustan cantidades para mantener riesgo acotado
            w1, w3 = (k3 - k2) / (k3 - k1), (k2 - k1) / (k3 - k1)
        else:
            w1 = w3 = 0.5
        legs = [opt(kind, k1, sgn * 2 * w1 * n), opt(kind, k2, -sgn * 2 * n), opt(kind, k3, sgn * 2 * w3 * n)]
        return Strategy(label, legs, "volatilidad",
                        "Apuesta a que el precio termine cerca del strike central (larga) o se aleje (corta).")

    if name not in T_:
        raise ValueError(f"plantilla desconocida: {name}")
    s = T_[name]()
    # Sobre exposición corta, las coberturas con opciones se reflejan
    if es < 0 and name == "protective_put":
        s.economic_function = "no_compatible"
        s.warnings.append("Una put no protege una exposición corta (riesgo de alza).")
    if es > 0 and name == "protective_call":
        s.economic_function = "no_compatible"
    if es < 0 and name == "covered_call":
        s.economic_function = "no_compatible"
        s.warnings.append("Vender calls sobre una exposición corta aumenta el riesgo de alza.")
    if futures_status != "listado_verificado" and name in ("short_futures", "long_futures"):
        s.warnings.append("Contrato de futuro no verificado como listado: instrumento teórico de simulación.")
    s.warnings += [w for w in validate_strategy(s, underlying) if w.startswith("ADVERTENCIA") or "Futuros" in w]
    s.params = {"S0": S0, "T": T, "contracts": n, "multiplier": multiplier, "strikes": k,
                "hedge_ratio": hedge_ratio, "premium_source": getattr(premium, "description", "observada")}
    return s


EQUITY_TEMPLATES_FOR_LONG = ["protective_put", "collar", "covered_call", "short_futures",
                             "long_straddle", "long_strangle"]
EQUITY_TEMPLATES_FOR_SHORT = ["protective_call", "collar", "long_futures", "long_straddle"]
ALL_EQUITY_TEMPLATES = ["protective_put", "protective_call", "covered_call", "collar", "short_futures",
                        "long_futures", "long_straddle", "short_straddle", "long_strangle", "short_strangle",
                        "long_call_butterfly", "short_call_butterfly", "long_put_butterfly", "short_put_butterfly"]
