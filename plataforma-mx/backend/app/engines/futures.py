"""Futuros (sección 10). Los futuros NO tienen estilo de ejercicio americano/europeo.

La aportación inicial mínima (AIM) es una garantía depositada y recuperable, no un costo.
El costo económico se compone de pérdidas/ganancias liquidadas diariamente y comisiones.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


def futures_pnl(n: float, multiplier: float, f_initial: float, f_final: float, side: str = "long") -> float:
    """P&L bruto: largo = n·M·(F_final − F_inicial); corto = −n·M·(F_final − F_inicial)."""
    sign = 1 if side == "long" else -1
    return sign * n * multiplier * (f_final - f_initial)


def round_to_tick(price: float, tick: float) -> float:
    return round(round(price / tick) * tick, 10)


def cost_of_carry_price(S: float, r: float, T: float, q: float = 0.0, discrete_divs_pv: float = 0.0) -> float:
    """Precio teórico (no cotizado): F = (S − VP(div)) e^{(r−q)T}."""
    return (S - discrete_divs_pv) * math.exp((r - q) * T)


def implied_carry(S: float, F: float, T: float) -> float:
    """Tasa de acarreo implícita en un precio de futuro observado: ln(F/S)/T."""
    return math.log(F / S) / T


def min_variance_hedge_ratio(spot_returns, fut_returns) -> dict:
    """h* = ρ σ_S/σ_F = Cov(ΔS,ΔF)/Var(ΔF); efectividad = ρ²."""
    s, f = np.asarray(spot_returns, float), np.asarray(fut_returns, float)
    c = np.cov(s, f, ddof=1)
    h = c[0, 1] / c[1, 1]
    rho = c[0, 1] / math.sqrt(c[0, 0] * c[1, 1])
    return {"hedge_ratio": h, "correlation": rho, "effectiveness_r2": rho ** 2, "observations": len(s)}


def contracts_for_hedge(exposure_value: float, futures_price: float, multiplier: float,
                        hedge_ratio: float = 1.0, beta: float | None = None) -> dict:
    """N* = h·V_A / (F·M) ; para índices: N* = β·V_A/(F·M). Se reporta el entero y el residuo."""
    h = beta if beta is not None else hedge_ratio
    raw = h * exposure_value / (futures_price * multiplier)
    n = round(raw)
    return {"contracts_exact": raw, "contracts_rounded": n,
            "residual_unhedged_notional": (raw - n) * futures_price * multiplier}


@dataclass
class MarginSimulation:
    initial_margin_per_contract: float           # AIM verificada (o supuesto etiquetado)
    maintenance_ratio: float = 1.0               # mantenimiento como fracción de la AIM (supuesto)
    commission_per_contract_side: float = 0.0
    margin_origin: str = "supuesto_del_usuario"
    notes: list[str] = field(default_factory=list)

    def run(self, prices: list[float], n: float, multiplier: float, side: str = "long") -> dict:
        """Liquidación diaria: variación = signo·n·M·(F_t − F_{t−1}). Si el saldo cae bajo
        mantenimiento, se exige aportación adicional hasta la AIM. Las garantías se devuelven
        al cierre; el P&L económico = Σ variaciones − comisiones."""
        sign = 1 if side == "long" else -1
        aim = self.initial_margin_per_contract * abs(n)
        maint = aim * self.maintenance_ratio
        bal = aim
        rows, total_calls, peak_funding = [], 0.0, aim
        for t in range(1, len(prices)):
            vm = sign * n * multiplier * (prices[t] - prices[t - 1])
            bal += vm
            call = 0.0
            if bal < maint - 1e-9:
                call = aim - bal
                bal += call
                total_calls += call
            peak_funding = max(peak_funding, aim + total_calls)
            rows.append({"t": t, "price": prices[t], "variation_margin": vm, "margin_call": call, "balance": bal})
        comm = self.commission_per_contract_side * abs(n) * 2
        pnl = futures_pnl(n, multiplier, prices[0], prices[-1], side)
        return {"daily": rows, "initial_margin": aim, "total_margin_calls": total_calls,
                "returned_margin_at_close": bal, "gross_pnl": pnl, "commissions": comm, "net_pnl": pnl - comm,
                "max_cash_committed": peak_funding, "margin_origin": self.margin_origin,
                "note": "La AIM es una garantía recuperable; el resultado económico es el P&L neto."}


def stop_loss_simulation(path: list[float], entry: float, stop: float, side: str, n: float, multiplier: float,
                         slippage_ticks: float = 0.0, tick: float = 0.01, gap_fill: str = "open") -> dict:
    """Stop-loss hipotético sobre una trayectoria de precios (no es una orden real).

    Si un precio atraviesa el stop, la ejecución se supone en ese precio (no en el stop
    si hubo brecha) más el deslizamiento; esto refleja riesgo de gap y de ejecución."""
    sign = 1 if side == "long" else -1
    for t, px in enumerate(path):
        hit = px <= stop if side == "long" else px >= stop
        if hit:
            fill = px if gap_fill == "open" else stop
            fill -= sign * slippage_ticks * tick
            return {"stopped": True, "step": t, "fill": fill, "stop": stop,
                    "gap_vs_stop": fill - stop, "pnl": futures_pnl(n, multiplier, entry, fill, side),
                    "warning": "Ejecución supuesta; en mercado real puede no haber contraparte al precio objetivo."}
    return {"stopped": False, "pnl": futures_pnl(n, multiplier, entry, path[-1], side), "fill": path[-1]}
