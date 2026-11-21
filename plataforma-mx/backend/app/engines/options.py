"""Opciones sobre acciones (sección 11).

- Black-Scholes-Merton con dividendo continuo q (opciones europeas).
- Cox-Ross-Rubinstein (europeas y americanas), con árbol de precios y valores.
- Volatilidad implícita a partir de primas OBSERVADAS (Brent con cotas de no arbitraje).

Convenciones de griegas: theta por año (y por día natural /365), vega y rho por
1.00 de cambio (y por 1 punto porcentual /100).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

from ..core.provenance import DataOrigin


def _check(S, K, T, sigma):
    if S <= 0 or K <= 0:
        raise ValueError("S y K deben ser positivos")
    if T < 0:
        raise ValueError("T no puede ser negativo")
    if sigma < 0:
        raise ValueError("σ no puede ser negativa")


def intrinsic(kind: str, S: float, K: float) -> float:
    return max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)


def bsm_price(kind: str, S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    """C = S e^{−qT} N(d1) − K e^{−rT} N(d2);  P = K e^{−rT} N(−d2) − S e^{−qT} N(−d1)."""
    _check(S, K, T, sigma)
    if T == 0 or sigma == 0:
        fwd_intr = (S * math.exp(-q * T) - K * math.exp(-r * T))
        return max(fwd_intr, 0.0) if kind == "call" else max(-fwd_intr, 0.0)
    sq = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / sq
    d2 = d1 - sq
    if kind == "call":
        return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    if kind == "put":
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)
    raise ValueError("kind debe ser 'call' o 'put'")


def bsm_greeks(kind: str, S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> dict:
    _check(S, K, T, sigma)
    if T == 0 or sigma == 0:
        raise ValueError("griegas analíticas no definidas para T=0 o σ=0")
    sq = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / sq
    d2 = d1 - sq
    eq, er = math.exp(-q * T), math.exp(-r * T)
    pdf = norm.pdf(d1)
    gamma = eq * pdf / (S * sq)
    vega = S * eq * pdf * math.sqrt(T)
    if kind == "call":
        delta = eq * norm.cdf(d1)
        theta = -S * eq * pdf * sigma / (2 * math.sqrt(T)) - r * K * er * norm.cdf(d2) + q * S * eq * norm.cdf(d1)
        rho = K * T * er * norm.cdf(d2)
    else:
        delta = -eq * norm.cdf(-d1)
        theta = -S * eq * pdf * sigma / (2 * math.sqrt(T)) + r * K * er * norm.cdf(-d2) - q * S * eq * norm.cdf(-d1)
        rho = -K * T * er * norm.cdf(-d2)
    return {"price": bsm_price(kind, S, K, T, r, sigma, q), "delta": delta, "gamma": gamma,
            "theta_per_year": theta, "theta_per_day": theta / 365.0, "vega": vega,
            "vega_per_pct": vega / 100.0, "rho": rho, "rho_per_pct": rho / 100.0, "d1": d1, "d2": d2,
            "origin": DataOrigin.MODEL_OUTPUT.value, "model": "Black-Scholes-Merton"}


def no_arbitrage_bounds(kind: str, S, K, T, r, q=0.0, american=False):
    """Cotas de un precio de opción. Europea: call ∈ [max(Se^{−qT}−Ke^{−rT},0), Se^{−qT}];
    put ∈ [max(Ke^{−rT}−Se^{−qT},0), Ke^{−rT}]. Americana: el ejercicio inmediato añade
    la cota inferior intrínseca y la put americana está acotada por K."""
    fs, fk = S * math.exp(-q * T), K * math.exp(-r * T)
    if kind == "call":
        lo, hi = max(fs - fk, 0.0), (S if american else fs)
        if american:
            lo = max(lo, S - K)
    else:
        lo, hi = max(fk - fs, 0.0), (K if american else fk)
        if american:
            lo = max(lo, K - S)
    return lo, hi


def implied_volatility(kind: str, observed_premium: float, S, K, T, r, q=0.0, american=False,
                       steps: int = 300, premium_origin: str = DataOrigin.OBSERVED_OFFICIAL.value,
                       lo_vol=1e-4, hi_vol=5.0) -> dict:
    """Volatilidad implícita de una prima observada.

    Se rechaza si la prima proviene de un modelo (no existe IV "de mercado" de un precio teórico),
    o si viola las cotas de no arbitraje. Método: Brent sobre σ ∈ [1e-4, 5].
    """
    if premium_origin == DataOrigin.MODEL_OUTPUT.value:
        raise ValueError("la prima proviene de un modelo: no puede calibrarse una volatilidad implícita de mercado")
    if T <= 0:
        raise ValueError("la opción está vencida")
    lo, hi = no_arbitrage_bounds(kind, S, K, T, r, q, american)
    if not (lo - 1e-12 <= observed_premium <= hi + 1e-12):
        raise ValueError(f"prima {observed_premium} fuera de cotas de no arbitraje [{lo:.6f}, {hi:.6f}]")

    if american:
        # El árbol CRR exige σ√Δt > |r − q|Δt para que p ∈ (0,1): la búsqueda empieza en ese mínimo.
        lo_vol = max(lo_vol, 1.05 * abs(r - q) * math.sqrt(T / steps))

    def f(sig):
        if american:
            return crr_price(kind, S, K, T, r, sig, q, steps, american=True)["price"] - observed_premium
        return bsm_price(kind, S, K, T, r, sig, q) - observed_premium

    flo, fhi = f(lo_vol), f(hi_vol)
    if flo > 0:
        raise ValueError("la prima es inferior al valor con volatilidad mínima: sin solución")
    if fhi < 0:
        raise ValueError("la prima excede el valor con volatilidad máxima (500 %): sin solución")
    iv = brentq(f, lo_vol, hi_vol, xtol=1e-10, rtol=1e-12, maxiter=200)
    return {"implied_vol": iv, "model": "CRR americana" if american else "BSM",
            "premium_origin": premium_origin, "residual": f(iv)}


def crr_price(kind: str, S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0,
              steps: int = 200, american: bool = False, return_tree: bool = False,
              discrete_dividends: list[tuple[float, float]] | None = None) -> dict:
    """Árbol binomial Cox-Ross-Rubinstein.

    u = e^{σ√Δt}, d = 1/u, p = (e^{(r−q)Δt} − d)/(u − d).

    Dividendos discretos [(t_i, D_i)]: modelo de "precio libre de dividendos"
    (S* = S − VP(dividendos dentro de T)); el árbol se construye sobre S* y en cada nodo
    se suma el VP de los dividendos pendientes. Es una aproximación estándar
    (Hull, cap. 21) y se informa en `notes`.
    """
    _check(S, K, T, sigma)
    if steps < 1:
        raise ValueError("steps ≥ 1")
    notes = []
    dt = T / steps
    u = math.exp(sigma * math.sqrt(dt))
    d = 1 / u
    growth = math.exp((r - q) * dt)
    p = (growth - d) / (u - d)
    if not (0 < p < 1):
        raise ValueError(f"probabilidad neutral al riesgo fuera de (0,1): p={p:.4f}; aumente steps")
    disc = math.exp(-r * dt)
    divs = [(t, D) for (t, D) in (discrete_dividends or []) if 0 < t <= T]
    pv_div = lambda t0: sum(D * math.exp(-r * (t - t0)) for t, D in divs if t > t0 + 1e-12)
    S_star = S - pv_div(0.0)
    if divs:
        notes.append("Dividendos discretos tratados con el modelo de precio libre de dividendos (aproximación).")
        if S_star <= 0:
            raise ValueError("el VP de los dividendos excede el precio spot")
    j = np.arange(steps + 1)
    ST = S_star * u ** (steps - j) * d ** j + pv_div(T)
    vals = np.maximum(ST - K, 0) if kind == "call" else np.maximum(K - ST, 0)
    price_tree = [ST.tolist()] if return_tree else None
    value_tree = [vals.tolist()] if return_tree else None
    early = []
    for i in range(steps - 1, -1, -1):
        vals = disc * (p * vals[:-1] + (1 - p) * vals[1:])
        if american or return_tree:
            jj = np.arange(i + 1)
            Si = S_star * u ** (i - jj) * d ** jj + pv_div(i * dt)
            if american:
                ex = np.maximum(Si - K, 0) if kind == "call" else np.maximum(K - Si, 0)
                mask = ex > vals + 1e-12
                if mask.any() and steps <= 50:
                    early += [{"step": i, "node": int(n)} for n in np.where(mask)[0]]
                vals = np.where(mask, ex, vals)
            if return_tree:
                price_tree.append(Si.tolist())
                value_tree.append(vals.tolist())
    out = {"price": float(vals[0]), "u": u, "d": d, "p": p, "dt": dt, "steps": steps,
           "style": "americana" if american else "europea", "model": "Cox-Ross-Rubinstein",
           "origin": DataOrigin.MODEL_OUTPUT.value, "notes": notes}
    if american:
        out["early_exercise_nodes"] = early
    if return_tree:
        out["price_tree"] = price_tree[::-1]
        out["value_tree"] = value_tree[::-1]
    return out


def crr_convergence(kind, S, K, T, r, sigma, q=0.0, american=False, steps_list=(10, 25, 50, 100, 200, 500, 1000)):
    ref = bsm_price(kind, S, K, T, r, sigma, q) if not american else None
    rows = []
    for n in steps_list:
        v = crr_price(kind, S, K, T, r, sigma, q, n, american)["price"]
        rows.append({"steps": n, "price": v, "diff_vs_bsm": (v - ref) if ref is not None else None})
    return {"bsm_reference": ref, "rows": rows}


def option_payoff(kind: str, ST, K: float):
    ST = np.asarray(ST, float)
    return np.maximum(ST - K, 0) if kind == "call" else np.maximum(K - ST, 0)


@dataclass
class BasicOptionPosition:
    kind: str          # call / put
    side: str          # long / short
    K: float
    premium: float     # por unidad de subyacente
    contracts: float
    multiplier: float
    premium_origin: str = DataOrigin.USER_ASSUMPTION.value

    @property
    def sign(self):
        return 1 if self.side == "long" else -1

    def terminal_pnl(self, ST):
        return self.sign * (option_payoff(self.kind, ST, self.K) - self.premium) * self.contracts * self.multiplier

    def breakeven(self):
        return self.K + self.premium if self.kind == "call" else self.K - self.premium

    def summary(self):
        q = self.contracts * self.multiplier
        if self.side == "long":
            max_loss = self.premium * q
            max_gain = None if self.kind == "call" else (self.K - self.premium) * q
        else:
            max_gain = self.premium * q
            max_loss = None if self.kind == "call" else (self.K - self.premium) * q
        return {"breakeven": self.breakeven(), "max_gain": max_gain, "max_loss": max_loss,
                "unbounded_gain": max_gain is None, "unbounded_loss": max_loss is None,
                "premium_total": self.premium * q, "premium_origin": self.premium_origin,
                "requires_margin": self.side == "short"}
