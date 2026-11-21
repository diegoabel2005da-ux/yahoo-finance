"""Análisis financiero y valuación fundamental (secciones 6.7 y 7).

Las razones se calculan sólo si todos los insumos existen; si falta alguno, el
resultado es None con la lista de insumos faltantes (nunca se rellena).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

RATIO_DEFS = {
    # nombre: (fórmula, numerador, denominador, explicación)
    "liquidez_corriente": ("Activo circulante / Pasivo circulante", "current_assets", "current_liabilities",
                           "Capacidad de cubrir obligaciones de corto plazo con activos de corto plazo."),
    "prueba_acida": ("(Activo circulante − Inventarios) / Pasivo circulante", None, "current_liabilities",
                     "Liquidez inmediata excluyendo inventarios."),
    "roa": ("Utilidad neta / Activo total promedio", "net_income", "avg_total_assets",
            "Rentabilidad sobre los activos."),
    "roe": ("Utilidad neta controladora / Capital contable promedio", "net_income", "avg_equity",
            "Rentabilidad sobre el capital de los accionistas."),
    "roic": ("EBIT·(1−t) / (Deuda financiera + Capital − Efectivo)", None, None,
             "Rentabilidad sobre el capital invertido."),
    "margen_bruto": ("Utilidad bruta / Ingresos", "gross_profit", "revenue", ""),
    "margen_operativo": ("EBIT / Ingresos", "ebit", "revenue", ""),
    "margen_neto": ("Utilidad neta / Ingresos", "net_income", "revenue", ""),
    "margen_ebitda": ("EBITDA / Ingresos", "ebitda", "revenue", ""),
    "deuda_capital": ("Deuda financiera / Capital contable", "total_debt", "total_equity",
                      "Apalancamiento financiero."),
    "deuda_neta_ebitda": ("(Deuda financiera − Efectivo) / EBITDA", None, "ebitda",
                          "Años de EBITDA necesarios para pagar la deuda neta."),
    "cobertura_intereses": ("EBIT / Gasto por intereses", "ebit", "interest_expense",
                            "Veces que la utilidad operativa cubre los intereses."),
    "pe": ("Precio / UPA", None, None, "Múltiplo precio-utilidad."),
    "pb": ("Capitalización / Capital contable", None, "total_equity", "Múltiplo precio-valor en libros."),
    "ev_ebitda": ("VE / EBITDA", None, "ebitda", ""),
    "ev_ventas": ("VE / Ingresos", None, "revenue", ""),
    "dividend_yield": ("Dividendos por acción (12m) / Precio", None, None, ""),
    "payout": ("Dividendos pagados / Utilidad neta", "dividends_paid", "net_income", ""),
}


def _div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def compute_ratios(f: dict, price: Optional[float] = None, shares: Optional[float] = None,
                   dps_ttm: Optional[float] = None, tax_rate: Optional[float] = None) -> dict:
    """`f`: diccionario de partidas de un periodo (mismas unidades). Devuelve
    {ratio: {"value", "formula", "missing", "explanation"}}."""
    g = f.get
    derived = dict(f)
    if g("avg_total_assets") is None and g("total_assets") is not None:
        derived["avg_total_assets"] = g("total_assets")
    if g("avg_equity") is None and g("total_equity") is not None:
        derived["avg_equity"] = g("total_equity")
    if g("ebitda") is None and g("ebit") is not None and g("depreciation_amortization") is not None:
        derived["ebitda"] = g("ebit") + g("depreciation_amortization")
    d = derived.get
    mcap = price * shares if price is not None and shares is not None else None
    net_debt = (d("total_debt") - d("cash")) if d("total_debt") is not None and d("cash") is not None else None
    ev = mcap + net_debt + (d("minority_interest") or 0) if mcap is not None and net_debt is not None else None
    out = {}

    def put(name, value, needs):
        missing = [k for k in needs if d(k) is None and k not in ("price", "shares", "dps_ttm", "tax_rate")]
        if "price" in needs and price is None:
            missing.append("price")
        if "shares" in needs and shares is None:
            missing.append("shares")
        if "dps_ttm" in needs and dps_ttm is None:
            missing.append("dps_ttm")
        if "tax_rate" in needs and tax_rate is None:
            missing.append("tax_rate")
        formula, *_, expl = RATIO_DEFS[name]
        out[name] = {"value": value if not missing else None, "formula": formula,
                     "missing": missing, "explanation": expl}

    for name, (_, num, den, _) in RATIO_DEFS.items():
        if num and den:
            put(name, _div(d(num), d(den)), [num, den])
    qa = (d("current_assets") - d("inventories")) if d("current_assets") is not None and d("inventories") is not None else None
    put("prueba_acida", _div(qa, d("current_liabilities")), ["current_assets", "inventories", "current_liabilities"])
    invested = (d("total_debt") + d("total_equity") - d("cash")) if None not in (d("total_debt"), d("total_equity"), d("cash")) else None
    nopat = d("ebit") * (1 - tax_rate) if d("ebit") is not None and tax_rate is not None else None
    put("roic", _div(nopat, invested), ["ebit", "tax_rate", "total_debt", "total_equity", "cash"])
    put("deuda_neta_ebitda", _div(net_debt, d("ebitda")), ["total_debt", "cash", "ebitda"])
    eps = _div(d("net_income"), shares)
    put("pe", _div(price, eps) if eps and eps > 0 else None, ["price", "shares", "net_income"])
    put("pb", _div(mcap, d("total_equity")), ["price", "shares", "total_equity"])
    put("ev_ebitda", _div(ev, d("ebitda")), ["price", "shares", "total_debt", "cash", "ebitda"])
    put("ev_ventas", _div(ev, d("revenue")), ["price", "shares", "total_debt", "cash", "revenue"])
    put("dividend_yield", _div(dps_ttm, price), ["dps_ttm", "price"])
    return {"ratios": out, "market_cap": mcap, "enterprise_value": ev, "net_debt": net_debt}


def horizontal_analysis(periods: list[dict], items: list[str]) -> list[dict]:
    """Variación % de cada partida contra el periodo previo (lista ordenada cronológicamente)."""
    out = []
    for i in range(1, len(periods)):
        row = {}
        for k in items:
            a, b = periods[i - 1].get(k), periods[i].get(k)
            row[k] = (b / a - 1) if a not in (None, 0) and b is not None else None
        out.append(row)
    return out


def vertical_analysis(period: dict, base_key: str) -> dict:
    base = period.get(base_key)
    return {k: (v / base if base and v is not None and isinstance(v, (int, float)) else None)
            for k, v in period.items()}


# ---------------- Costo de capital ----------------

def cost_of_equity_capm(rf: float, beta: float, erp: float, country_risk: float = 0.0,
                        size_premium: float = 0.0) -> float:
    """Ke = rf + β·PRM + prima país + prima tamaño"""
    return rf + beta * erp + country_risk + size_premium


def wacc(equity_value: float, debt_value: float, ke: float, kd_pre_tax: float, tax_rate: float) -> float:
    """WACC = E/(D+E)·Ke + D/(D+E)·Kd·(1−t)"""
    v = equity_value + debt_value
    if v <= 0:
        raise ValueError("D + E debe ser positivo")
    return equity_value / v * ke + debt_value / v * kd_pre_tax * (1 - tax_rate)


@dataclass
class DCFInputs:
    base_revenue: float
    revenue_growth: list[float]          # una tasa por año proyectado
    ebit_margin: list[float]
    tax_rate: float
    da_pct_revenue: list[float]          # D&A / ingresos
    capex_pct_revenue: list[float]
    nwc_pct_revenue_change: list[float]  # ΔCTN / ΔIngresos
    wacc: float
    terminal_growth: float | None = None
    terminal_multiple: float | None = None  # múltiplo VE/EBITDA de salida
    net_debt: float = 0.0
    minority_interest: float = 0.0
    non_operating_assets: float = 0.0
    shares_outstanding: float = 1.0
    mid_year: bool = False
    notes: list[str] = field(default_factory=list)


def dcf_fcff(p: DCFInputs) -> dict:
    """DCF por FCFF.

    FCFF_t = EBIT_t(1−t) + D&A_t − CAPEX_t − ΔCTN_t
    VT (Gordon) = FCFF_{N}(1+g)/(WACC−g);  VT (múltiplo) = EBITDA_N × múltiplo
    VE = Σ FCFF_t/(1+WACC)^t + VT/(1+WACC)^N
    Capital = VE − deuda neta − minoritario + activos no operativos
    """
    n = len(p.revenue_growth)
    for name in ("ebit_margin", "da_pct_revenue", "capex_pct_revenue", "nwc_pct_revenue_change"):
        if len(getattr(p, name)) != n:
            raise ValueError(f"{name} debe tener {n} elementos")
    if (p.terminal_growth is None) == (p.terminal_multiple is None):
        raise ValueError("especifique exactamente uno: terminal_growth o terminal_multiple")
    if p.terminal_growth is not None and p.terminal_growth >= p.wacc:
        raise ValueError("g terminal debe ser menor que el WACC")
    rows = []
    rev_prev = p.base_revenue
    pv_sum = 0.0
    for t in range(n):
        rev = rev_prev * (1 + p.revenue_growth[t])
        ebit = rev * p.ebit_margin[t]
        nopat = ebit * (1 - p.tax_rate)
        da = rev * p.da_pct_revenue[t]
        capex = rev * p.capex_pct_revenue[t]
        dnwc = (rev - rev_prev) * p.nwc_pct_revenue_change[t]
        fcff = nopat + da - capex - dnwc
        expo = t + 0.5 if p.mid_year else t + 1
        dfac = (1 + p.wacc) ** -expo
        pv_sum += fcff * dfac
        rows.append({"year": t + 1, "revenue": rev, "ebit": ebit, "nopat": nopat, "da": da, "capex": capex,
                     "delta_nwc": dnwc, "fcff": fcff, "discount_factor": dfac, "pv_fcff": fcff * dfac,
                     "ebitda": ebit + da})
        rev_prev = rev
    last = rows[-1]
    if p.terminal_growth is not None:
        tv = last["fcff"] * (1 + p.terminal_growth) / (p.wacc - p.terminal_growth)
        tv_method = "Gordon"
    else:
        tv = last["ebitda"] * p.terminal_multiple
        tv_method = "múltiplo VE/EBITDA"
    tv_expo = n - 0.5 if (p.mid_year and p.terminal_growth is not None) else n
    pv_tv = tv * (1 + p.wacc) ** -tv_expo
    ev = pv_sum + pv_tv
    equity = ev - p.net_debt - p.minority_interest + p.non_operating_assets
    return {"projection": rows, "pv_explicit": pv_sum, "terminal_value": tv, "pv_terminal": pv_tv,
            "terminal_method": tv_method, "enterprise_value": ev, "equity_value": equity,
            "value_per_share": equity / p.shares_outstanding,
            "terminal_weight": pv_tv / ev if ev else None,
            "disclaimer": "Valor teórico bajo los supuestos indicados; no implica que el precio de "
                          "mercado lo alcanzará."}


def dcf_sensitivity(p: DCFInputs, wacc_grid: list[float], g_grid: list[float]) -> dict:
    table = []
    for w in wacc_grid:
        row = []
        for g in g_grid:
            q = DCFInputs(**{**p.__dict__, "wacc": w, "terminal_growth": g, "terminal_multiple": None})
            try:
                row.append(dcf_fcff(q)["value_per_share"])
            except ValueError:
                row.append(None)
        table.append(row)
    return {"wacc": wacc_grid, "g": g_grid, "value_per_share": table}


def multiples_valuation(target: dict, peers: list[dict], multiple: str = "ev_ebitda") -> dict:
    """Valuación por comparables: mediana del múltiplo de pares × métrica de la emisora.
    `peers`: [{"name", "multiple_value", "source"}]; `target`: {"metric", "net_debt", "shares"}."""
    vals = np.array([pp["multiple_value"] for pp in peers if pp.get("multiple_value") is not None], float)
    if len(vals) == 0:
        raise ValueError("no hay múltiplos de comparables con datos")
    med, q1, q3 = float(np.median(vals)), float(np.quantile(vals, .25)), float(np.quantile(vals, .75))

    def per_share(m):
        if multiple in ("ev_ebitda", "ev_ventas"):
            return (m * target["metric"] - target.get("net_debt", 0)) / target["shares"]
        return m * target["metric"] / target["shares"]  # P/E, P/B: métrica total

    return {"multiple": multiple, "median": med, "q1": q1, "q3": q3, "n_peers": len(vals),
            "value_per_share_median": per_share(med), "range": [per_share(q1), per_share(q3)]}
