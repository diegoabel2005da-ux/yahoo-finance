"""Rutas de cálculo. Cada respuesta incluye `audit_id` para reproducir el cálculo."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.audit import ENGINE_VERSION, to_jsonable
from ..core.db import AuditRecord, Exposure, FinancialStatement, FuturesContract, Study, get_session
from ..core.provenance import DataOrigin, PriceType
from ..engines import fundamental as fa
from ..engines import futures as fu
from ..engines import options as op
from ..engines import patterns as pt
from ..engines import risk as rk
from ..engines import scenarios as sc
from ..engines import strategies as stg
from ..engines import technical as ta
from ..engines import timeseries as tsx
from ..engines.rates import capfloor as cf
from ..services import ai_explainer, reports
from ..services.market_data import DataBlocked, get_instrument, load_ohlcv
from .common import df_rows, respond
from .routes_data import load_curve

router = APIRouter(prefix="/api")


def _series(db, ticker, series, start=None, end=None, freq="diaria"):
    try:
        inst = get_instrument(db, ticker, series)
        df, meta = load_ohlcv(db, inst, PriceType.OFFICIAL_CLOSE.value, start, end)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except DataBlocked as e:
        raise HTTPException(409, str(e))
    if df.empty:
        raise HTTPException(422, f"sin cierres oficiales para {ticker} {series}: importe datos verificados")
    return tsx.resample_ohlcv(df, freq), meta


def _src(meta, label):
    return [{"dato": label, "fuente": ", ".join(meta.get("sources", [])), "fecha": str(meta.get("last_date")),
             "origen": "observado", "estado": str(meta.get("validation_counts"))}]


# ================================================================ técnico

class TechnicalReq(BaseModel):
    ticker: str
    series: str
    start: Optional[date] = None
    end: Optional[date] = None
    freq: str = "diaria"
    roc_n: int = 12
    williams_n: int = 14
    stoch_k: int = 14
    stoch_d: int = 3
    stoch_mode: Literal["rapido", "lento"] = "lento"
    stoch_smooth: int = 3
    rsi_periods: list[int] = [9, 14, 25]
    sma: list[int] = [20, 50, 200]
    fib_mode: Literal["auto", "manual"] = "auto"
    fib_high: Optional[float] = None
    fib_low: Optional[float] = None
    fib_trend: Literal["alcista", "bajista"] = "alcista"
    pivot_left: int = 5
    pivot_right: int = 5


@router.post("/technical")
def technical(req: TechnicalReq, db: Session = Depends(get_session)):
    df, meta = _series(db, req.ticker, req.series, req.start, req.end, req.freq)
    c = df["close"]
    out = pd.DataFrame(index=df.index)
    out["close"] = c
    out["roc"] = ta.roc(c, req.roc_n)
    for p in req.rsi_periods:
        out[f"rsi_{p}"] = ta.rsi_wilder(c, p)
    for n in req.sma:
        out[f"sma_{n}"] = ta.sma(c, n)
    hl = "high" in df and "low" in df and df[["high", "low"]].notna().all().all()
    warn = []
    if hl:
        out["williams_r"] = ta.williams_r(df["high"], df["low"], c, req.williams_n)
        st = ta.stochastic(df["high"], df["low"], c, req.stoch_k, req.stoch_d, req.stoch_mode, req.stoch_smooth)
        out["stoch_k"], out["stoch_d"] = st["k"], st["d"]
    else:
        warn.append("Sin máximos/mínimos completos: Williams %R, estocástico y Fibonacci automático no disponibles.")
    if req.fib_mode == "manual":
        if req.fib_high is None or req.fib_low is None:
            raise HTTPException(422, "Fibonacci manual requiere fib_high y fib_low")
        fib = {"levels": ta.fibonacci_levels(req.fib_high, req.fib_low, req.fib_trend), "method": "anclas manuales",
               "anchor_high": {"price": req.fib_high}, "anchor_low": {"price": req.fib_low}, "trend": req.fib_trend}
    else:
        fib = ta.auto_fibonacci(df["high"], df["low"], req.pivot_left, req.pivot_right) if hl else None
    result = {"rows": df_rows(out), "roc_zero_crossings": ta.zero_crossings(out["roc"])[-20:], "fibonacci": fib,
              "warnings": warn, "meta": meta,
              "methodology": {"rsi": "Wilder", "stochastic": f"{req.stoch_mode}, suavizado SMA",
                              "williams": "−100(Máx−C)/(Máx−Mín), NaN si rango cero"}}
    return respond(db, "technical", req.model_dump(), {}, ["ROC", "RSI Wilder", "Williams %R", "Estocástico", "Fibonacci"],
                   result, _src(meta, f"{req.ticker} {req.series} cierres oficiales"))


class PatternsReq(BaseModel):
    ticker: str
    series: str
    start: Optional[date] = None
    end: Optional[date] = None
    freq: str = "diaria"
    pivot_left: int = 5
    pivot_right: int = 5
    tolerance: float = 0.03
    min_depth: float = 0.03
    primary: int = 200
    secondary: int = 50
    short: int = 20


@router.post("/patterns")
def patterns(req: PatternsReq, db: Session = Depends(get_session)):
    df, meta = _series(db, req.ticker, req.series, req.start, req.end, req.freq)
    if not ("high" in df and "low" in df):
        raise HTTPException(422, "el chartismo requiere máximos y mínimos")
    result = {"patterns": pt.detect_patterns(df, req.pivot_left, req.pivot_right, req.tolerance, req.min_depth),
              "trends": pt.classify_trends(df["close"], req.primary, req.secondary, req.short),
              "regression": {k: v for k, v in pt.linear_trend(df["close"]).items() if k != "fitted"},
              "structural_breaks": pt.structural_breaks(df["close"]) if len(df) >= 90 else [],
              "pivots": to_jsonable(ta.pivots(df["high"], df["low"], req.pivot_left, req.pivot_right).to_dict("records")),
              "disclaimer": "Figuras descriptivas detectadas por reglas; no constituyen señales de operación."}
    return respond(db, "patterns", req.model_dump(), {}, ["pivotes fractales", "reglas de figuras"], result,
                   _src(meta, f"{req.ticker} {req.series}"))


# ================================================================ riesgo

class RiskReq(BaseModel):
    ticker: str
    series: str
    benchmark_ticker: Optional[str] = None
    benchmark_series: Optional[str] = None
    start: Optional[date] = None
    end: Optional[date] = None
    freq: str = "diaria"
    confidence: float = 0.95
    general_beta_years: int = 2
    peers: list[dict] = []   # [{"ticker","series"}] para correlaciones


@router.post("/risk")
def risk(req: RiskReq, db: Session = Depends(get_session)):
    df, meta = _series(db, req.ticker, req.series, None, None, req.freq)
    sel = df.loc[str(req.start) if req.start else None: str(req.end) if req.end else None]
    c = sel["close"]
    res = {"summary": rk.risk_summary(c, req.freq, req.confidence),
           "max_drawdown": tsx.max_drawdown(c), "volatility_annual": tsx.annualized_volatility(c, req.freq),
           "period": {"start": sel.index.min(), "end": sel.index.max(), "observations": len(sel)}}
    if "volume" in sel:
        res["liquidity"] = rk.liquidity_metrics(sel["volume"], c)
    if req.benchmark_ticker:
        bdf, bmeta = _series(db, req.benchmark_ticker, req.benchmark_series or "", None, None, req.freq)
        end = df.index.max()
        gen_start = end - pd.DateOffset(years=req.general_beta_years)
        try:
            res["beta_general"] = {**rk.beta(df["close"].loc[gen_start:], bdf["close"].loc[gen_start:]),
                                   "horizon": f"{req.general_beta_years} años hasta {end.date()} ({req.freq})"}
        except ValueError as e:
            res["beta_general"] = {"error": str(e)}
        try:
            res["beta_custom"] = rk.beta(c, bdf["close"].loc[sel.index.min(): sel.index.max()])
        except ValueError as e:
            res["beta_custom"] = {"error": str(e)}
        res["benchmark"] = {"ticker": req.benchmark_ticker, "series": req.benchmark_series, "sources": bmeta.get("sources")}
    if req.peers:
        series = {req.ticker: c}
        for p in req.peers:
            pdf, _ = _series(db, p["ticker"], p["series"], req.start, req.end, req.freq)
            series[p["ticker"]] = pdf["close"]
        res["correlations"] = rk.correlation_matrix(series).round(6).to_dict()
    return respond(db, "risk", req.model_dump(), {}, ["σ anualizada", "VaR/ES", "β = Cov/Var"], res,
                   _src(meta, f"{req.ticker} {req.series}"))


# ================================================================ fundamentales

class RatiosReq(BaseModel):
    ticker: str
    period_end: Optional[date] = None
    period_type: str = "FY"
    basis: str = "consolidado"
    price: Optional[float] = None
    price_source: Optional[str] = None
    shares: Optional[float] = None
    dps_ttm: Optional[float] = None
    tax_rate: Optional[float] = None


@router.post("/ratios")
def ratios(req: RatiosReq, db: Session = Depends(get_session)):
    q = select(FinancialStatement).where(FinancialStatement.ticker == req.ticker.upper(),
                                         FinancialStatement.period_type == req.period_type.upper(),
                                         FinancialStatement.basis == req.basis)
    stmts = list(db.scalars(q))
    if not stmts:
        raise HTTPException(422, "no hay estados financieros importados para ese periodo/base")
    pe = req.period_end or max(s.period_end for s in stmts)
    items, srcs = {}, []
    for s in stmts:
        if s.period_end == pe:
            items.update(s.items)
            srcs.append({"dato": f"{s.statement} {s.period_type} {s.period_end}", "fuente": s.source,
                         "fecha": str(s.retrieved_at), "origen": "observado", "estado": s.basis})
    prev = sorted({s.period_end for s in stmts if s.period_end < pe})
    if prev:
        prev_items = {}
        for s in stmts:
            if s.period_end == prev[-1]:
                prev_items.update(s.items)
        for k, avg in (("total_assets", "avg_total_assets"), ("total_equity", "avg_equity")):
            if k in items and k in prev_items:
                items[avg] = (items[k] + prev_items[k]) / 2
    res = fa.compute_ratios(items, req.price, req.shares, req.dps_ttm, req.tax_rate)
    res["period_end"] = pe
    res["items"] = items
    if req.price is not None:
        srcs.append({"dato": "precio", "fuente": req.price_source or "indicado por el usuario", "fecha": "",
                     "origen": "observado" if req.price_source else "supuesto", "estado": ""})
    return respond(db, "ratios", req.model_dump(), {}, [v[0] for v in fa.RATIO_DEFS.values()], res, srcs)


class DCFReq(BaseModel):
    inputs: dict
    sensitivity_wacc: list[float] = []
    sensitivity_g: list[float] = []
    capm: Optional[dict] = None      # {rf, beta, erp, country_risk, size_premium}
    wacc_build: Optional[dict] = None  # {equity_value, debt_value, kd_pre_tax, tax_rate}


@router.post("/valuation/dcf")
def dcf(req: DCFReq, db: Session = Depends(get_session)):
    inp = dict(req.inputs)
    wacc_detail = None
    try:
        if req.capm and req.wacc_build:
            ke = fa.cost_of_equity_capm(**req.capm)
            w = fa.wacc(req.wacc_build["equity_value"], req.wacc_build["debt_value"], ke,
                        req.wacc_build["kd_pre_tax"], req.wacc_build["tax_rate"])
            inp["wacc"] = w
            wacc_detail = {"ke": ke, "wacc": w, **req.capm, **req.wacc_build}
        p = fa.DCFInputs(**inp)
        res = fa.dcf_fcff(p)
        res["inputs"] = inp
        res["wacc_detail"] = wacc_detail
        if req.sensitivity_wacc and req.sensitivity_g:
            res["sensitivity"] = fa.dcf_sensitivity(p, req.sensitivity_wacc, req.sensitivity_g)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e))
    return respond(db, "dcf", req.model_dump(), {}, ["FCFF = EBIT(1−t)+D&A−CAPEX−ΔCTN", "VT Gordon", "WACC"], res)


class MultiplesReq(BaseModel):
    target: dict
    peers: list[dict]
    multiple: str = "ev_ebitda"


@router.post("/valuation/multiples")
def multiples(req: MultiplesReq, db: Session = Depends(get_session)):
    try:
        res = fa.multiples_valuation(req.target, req.peers, req.multiple)
    except (ValueError, KeyError) as e:
        raise HTTPException(422, str(e))
    return respond(db, "multiples", req.model_dump(), {}, ["mediana de múltiplos de comparables"], res,
                   [{"dato": p.get("name"), "fuente": p.get("source", "no indicada"), "fecha": "", "origen": "",
                     "estado": ""} for p in req.peers])


# ================================================================ futuros

class FuturesReq(BaseModel):
    contracts: float
    multiplier: float
    side: Literal["long", "short"]
    f_initial: float
    price_path: list[float]
    initial_margin_per_contract: Optional[float] = None
    margin_origin: str = DataOrigin.USER_ASSUMPTION.value
    maintenance_ratio: float = 1.0
    commission_per_contract_side: float = 0.0
    underlying_shares: float = 0.0    # posición en acciones combinada
    spot_initial: Optional[float] = None
    spot_final: Optional[float] = None
    contract_symbol: Optional[str] = None
    stop: Optional[float] = None
    slippage_ticks: float = 0.0
    tick: float = 0.01


@router.post("/futures/analyze")
def futures_analyze(req: FuturesReq, db: Session = Depends(get_session)):
    contract = None
    if req.contract_symbol:
        contract = db.scalar(select(FuturesContract).where(FuturesContract.symbol == req.contract_symbol))
        if not contract:
            raise HTTPException(404, "contrato no encontrado en el catálogo de contratos importados")
        if float(contract.multiplier) != req.multiplier:
            raise HTTPException(422, f"multiplicador distinto del contractual ({contract.multiplier})")
    path = [req.f_initial] + req.price_path
    res = {"gross_pnl": fu.futures_pnl(req.contracts, req.multiplier, req.f_initial, path[-1], req.side),
           "contract": to_jsonable({c.name: getattr(contract, c.name) for c in FuturesContract.__table__.columns})
           if contract else {"status": "instrumento teórico de simulación (sin contrato verificado)"},
           "exercise_style": "no aplica (los futuros no son americanos ni europeos)"}
    aim = req.initial_margin_per_contract
    origin = req.margin_origin
    if aim is None and contract is not None:
        side_aim = contract.margin_long if req.side == "long" else contract.margin_short
        if side_aim is None:
            side_aim = contract.initial_margin
        if side_aim is not None:
            aim = float(side_aim)
            origin = f"AIM {'larga' if req.side == 'long' else 'corta'} importada · {contract.margin_source or contract.source}"
    if aim is not None:
        res["margin"] = fu.MarginSimulation(aim, req.maintenance_ratio, req.commission_per_contract_side, origin).run(
            path, req.contracts, req.multiplier, req.side)
    else:
        res["margin"] = {"status": "no_disponible", "reason": "sin AIM verificada ni supuesto indicado"}
    if req.underlying_shares and req.spot_initial is not None and req.spot_final is not None:
        u = req.underlying_shares * (req.spot_final - req.spot_initial)
        res["combined"] = {"underlying_pnl": u, "futures_pnl": res["gross_pnl"], "combined_pnl": u + res["gross_pnl"]}
    if req.stop is not None:
        res["stop_loss"] = fu.stop_loss_simulation(req.price_path, req.f_initial, req.stop, req.side, req.contracts,
                                                   req.multiplier, req.slippage_ticks, req.tick)
    return respond(db, "futures", req.model_dump(), {}, ["P&L = ±n·M·(F_T − F_0)", "liquidación diaria"], res)


class CarryReq(BaseModel):
    spot: float
    r: float
    T: float
    q: float = 0.0
    divs_pv: float = 0.0
    observed_futures: Optional[float] = None


@router.post("/futures/carry")
def futures_carry(req: CarryReq, db: Session = Depends(get_session)):
    res = {"theoretical_price": fu.cost_of_carry_price(req.spot, req.r, req.T, req.q, req.divs_pv),
           "origin": DataOrigin.MODEL_OUTPUT.value}
    if req.observed_futures:
        res["implied_carry"] = fu.implied_carry(req.spot, req.observed_futures, req.T)
        res["basis"] = req.observed_futures - req.spot
    return respond(db, "futures_carry", req.model_dump(), {}, ["F = (S − VP div) e^{(r−q)T}"], res)


# ================================================================ opciones

class OptionReq(BaseModel):
    kind: Literal["call", "put"]
    S: float
    K: float
    T: float
    r: float
    sigma: float
    q: float = 0.0
    sigma_origin: str = DataOrigin.USER_ASSUMPTION.value
    style: Literal["europea", "americana"] = "europea"
    steps: int = 200
    tree_steps: int = 0
    discrete_dividends: list[tuple[float, float]] = []
    observed_premium: Optional[float] = None
    observed_premium_origin: Optional[str] = None
    contracts: float = 1
    multiplier: float = 100
    side: Literal["long", "short"] = "long"


@router.post("/options/value")
def option_value(req: OptionReq, db: Session = Depends(get_session)):
    try:
        res = {"inputs_origin": {"sigma": req.sigma_origin}}
        if req.style == "europea" and not req.discrete_dividends:
            res["bsm"] = op.bsm_greeks(req.kind, req.S, req.K, req.T, req.r, req.sigma, req.q)
        crr = op.crr_price(req.kind, req.S, req.K, req.T, req.r, req.sigma, req.q, req.steps,
                           req.style == "americana", discrete_dividends=req.discrete_dividends or None)
        res["crr"] = crr
        if req.tree_steps:
            res["tree"] = op.crr_price(req.kind, req.S, req.K, req.T, req.r, req.sigma, req.q, min(req.tree_steps, 12),
                                       req.style == "americana", return_tree=True,
                                       discrete_dividends=req.discrete_dividends or None)
        res["convergence"] = op.crr_convergence(req.kind, req.S, req.K, req.T, req.r, req.sigma, req.q,
                                                req.style == "americana", (10, 50, 100, 250, 500))
        theo = res.get("bsm", {}).get("price", crr["price"])
        res["theoretical_premium"] = {"value": theo, "origin": DataOrigin.MODEL_OUTPUT.value}
        if req.observed_premium is not None:
            if not req.observed_premium_origin or req.observed_premium_origin == DataOrigin.MODEL_OUTPUT.value:
                raise ValueError("indique el origen observado de la prima (fuente oficial o proveedor)")
            res["observed_premium"] = {"value": req.observed_premium, "origin": req.observed_premium_origin}
            res["implied_vol"] = op.implied_volatility(req.kind, req.observed_premium, req.S, req.K, req.T, req.r,
                                                       req.q, req.style == "americana",
                                                       premium_origin=req.observed_premium_origin)
            res["theoretical_minus_observed"] = theo - req.observed_premium
        prem = req.observed_premium if req.observed_premium is not None else theo
        pos = op.BasicOptionPosition(req.kind, req.side, req.K, prem, req.contracts, req.multiplier,
                                     req.observed_premium_origin or DataOrigin.MODEL_OUTPUT.value)
        grid = [req.S * x / 100 for x in range(50, 151, 2)]
        res["position"] = {**pos.summary(), "payoff_at_expiry": [{"S": s, "pnl": float(pos.terminal_pnl(s))} for s in grid],
                           "value_before_expiry": [{"S": s, "pnl": pos.sign * (op.bsm_price(req.kind, s, req.K, req.T / 2, req.r, req.sigma, req.q) - prem) * req.contracts * req.multiplier} for s in grid]
                           if req.style == "europea" else None,
                           "note": "Curva previa al vencimiento revaluada con BSM a T/2 (no es el payoff terminal)."}
    except ValueError as e:
        raise HTTPException(422, str(e))
    return respond(db, "option_value", req.model_dump(), {}, ["BSM", "CRR"], res)


# ================================================================ caps / floors

class CapFloorReq(BaseModel):
    curve_id: int
    forward_curve_id: Optional[int] = None
    kind: Literal["cap", "floor"]
    notional: float = Field(gt=0)
    strike: float
    start: date
    end: date
    frequency: str = "28D"
    day_count: str = "ACT/360"
    rate_style: Literal["term_fixed_in_advance", "compounded_in_arrears"] = "term_fixed_in_advance"
    model: Literal["black76", "bachelier"] = "black76"
    vol: float | list[float]
    vol_origin: str = DataOrigin.USER_ASSUMPTION.value
    shift: float = 0.0
    amortization: Optional[list[float]] = None
    fixing_lag_bd: int = 1
    known_fixings: dict[int, float] = {}
    accrued_factor: dict[int, float] = {}
    reference_rate: str = "TIIE_28"
    observed_premium: Optional[float] = None
    observed_premium_origin: Optional[str] = None
    compare_normal_vol: Optional[float] = None
    compare_lognormal_vol: Optional[float] = None


def _spec(req: CapFloorReq) -> cf.CapFloorSpec:
    return cf.CapFloorSpec(req.kind, req.notional, req.strike, req.start, req.end, req.frequency, req.day_count,
                           req.rate_style, req.model, req.vol, req.vol_origin, req.shift, req.amortization,
                           req.fixing_lag_bd, {int(k): v for k, v in req.known_fixings.items()},
                           {int(k): v for k, v in req.accrued_factor.items()}, req.reference_rate,
                           req.observed_premium, req.observed_premium_origin)


@router.post("/capfloor/value")
def capfloor_value(req: CapFloorReq, db: Session = Depends(get_session)):
    disc = load_curve(db, req.curve_id)
    fwd = load_curve(db, req.forward_curve_id) if req.forward_curve_id else None
    try:
        spec = _spec(req)
        res = {"valuation": cf.price_capfloor(spec, disc, fwd), "sensitivities": cf.sensitivities(spec, disc, fwd),
               "parity_swap_value": cf.swap_value_from_forwards(spec, disc, fwd)}
        if req.observed_premium is not None:
            res["implied_flat_vol"] = cf.implied_flat_vol(spec, req.observed_premium, disc, fwd,
                                                          req.observed_premium_origin or "")
        if req.compare_normal_vol and req.compare_lognormal_vol:
            res["model_comparison"] = cf.compare_models(spec, disc, req.compare_normal_vol, req.compare_lognormal_vol, fwd)
    except ValueError as e:
        raise HTTPException(422, str(e))
    src = [{"dato": "curva", "fuente": disc.source, "fecha": str(disc.curve_date), "origen": disc.origin, "estado": ""},
           {"dato": "volatilidad", "fuente": req.vol_origin, "fecha": "", "origen": req.vol_origin, "estado": ""}]
    return respond(db, "capfloor", req.model_dump(), {}, ["caplet = N α P [F N(d1) − K N(d2)]", "Bachelier"], res, src)


# ================================================================ estrategias

class LegIn(BaseModel):
    kind: Literal["stock", "call", "put", "future"]
    qty: float
    multiplier: float = 1
    strike: Optional[float] = None
    expiry_years: Optional[float] = None
    style: str = "europea"
    premium: Optional[float] = None
    premium_origin: str = DataOrigin.USER_ASSUMPTION.value
    entry_price: Optional[float] = None
    underlying: str = ""
    commission: float = 0.0


class StrategyReq(BaseModel):
    template: Optional[str] = None
    legs: list[LegIn] = []
    S0: float
    T: float
    r: float
    q: float = 0.0
    sigma: float
    sigma_origin: str = DataOrigin.USER_ASSUMPTION.value
    contracts: float = 1
    multiplier: float = 100
    strikes: dict = {}
    exposure_sign: int = 1
    eval_times: list[float] = []
    underlying: str = ""


@router.get("/strategies/templates")
def strategy_templates():
    return {"templates": stg.ALL_EQUITY_TEMPLATES, "economic_functions": stg.ECONOMIC_FUNCTIONS,
            "for_long_exposure": stg.EQUITY_TEMPLATES_FOR_LONG, "for_short_exposure": stg.EQUITY_TEMPLATES_FOR_SHORT,
            "rates": ["cap_comprado", "floor_comprado", "collar_tasas"]}


@router.post("/strategies/build")
def strategy_build(req: StrategyReq, db: Session = Depends(get_session)):
    try:
        if req.template:
            pf = stg.theoretical_premium_fn(req.S0, req.r, req.q, req.sigma, req.sigma_origin)
            s = stg.build_template(req.template, req.S0, req.T, req.contracts, req.multiplier, pf, req.strikes,
                                   req.exposure_sign, req.underlying)
        else:
            s = stg.Strategy("Manual", [stg.Leg(**l.model_dump()) for l in req.legs], "no_compatible")
        issues = stg.validate_strategy(s, req.underlying or None)
        errors = [i for i in issues if i.startswith("leg") and "cobertura cruzada" not in i]
        if errors:
            raise ValueError("; ".join(errors))
        grid = [req.S0 * x / 100 for x in range(40, 161, 2)]
        exp = s.option_expiry() or req.T
        curves = {"expiry": s.payoff_curve(grid, exp, req.sigma, req.r, req.q)}
        for t in req.eval_times:
            if 0 <= t < exp:
                curves[f"t={t:.4f}"] = s.payoff_curve(grid, t, req.sigma, req.r, req.q)
        res = {"strategy": {"name": s.name, "economic_function": s.economic_function,
                            "economic_function_label": stg.ECONOMIC_FUNCTIONS[s.economic_function],
                            "description": s.description, "legs": [l.__dict__ for l in s.legs],
                            "initial_cost": -s.initial_cash(), "warnings": s.warnings + issues},
               "grid": grid, "curves": curves, "breakevens": s.breakevens(req.S0, exp, req.sigma, req.r, req.q),
               "notes": ["Curva 'expiry' = resultado al vencimiento; curvas t<vencimiento revaluadas con modelo.",
                         "Primas de plantilla: teóricas BSM (resultado de modelo) salvo legs manuales con prima observada."]}
    except ValueError as e:
        raise HTTPException(422, str(e))
    return respond(db, "strategy", req.model_dump(), {}, ["Σ legs"], res)


# ================================================================ exposiciones y escenarios

class EquityScenarioReq(BaseModel):
    ticker: str
    series: str
    shares: float
    declared: bool = False
    horizon_years: float = 0.25
    sigma: Optional[float] = None
    sigma_origin: Optional[str] = None
    sigma_window: int = 252
    r: float
    r_origin: str
    q: float = 0.0
    spot_override: Optional[float] = None
    spot_override_source: Optional[str] = None
    templates: list[str] = ["protective_put", "collar", "covered_call", "short_futures", "long_straddle"]
    multiplier: float = 100
    option_expiry_years: Optional[float] = None
    futures_symbol: Optional[str] = None
    futures_price: Optional[float] = None
    futures_price_source: Optional[str] = None
    commission_per_contract: float = 0.0
    profiles: dict[str, dict] = {}      # personalización de perfiles (choques, preferencias)
    futures_basis_shock: float = 0.0
    budget: Optional[float] = None
    objective: str = ""


@router.post("/scenarios/equity")
def scenarios_equity(req: EquityScenarioReq, db: Session = Depends(get_session)):
    df, meta = _series(db, req.ticker, req.series)
    last_date = df.index.max().date()
    if req.spot_override is not None:
        if not req.spot_override_source:
            raise HTTPException(422, "un precio spot alternativo requiere fuente")
        spot, spot_prov = req.spot_override, {"value": req.spot_override, "source": req.spot_override_source,
                                              "type": "indicado por el usuario"}
    else:
        spot = float(df["close"].iloc[-1])
        spot_prov = {"value": spot, "type": "cierre_oficial", "date": last_date, "sources": meta["sources"]}
    if req.sigma is None:
        sig = tsx.annualized_volatility(df["close"].tail(req.sigma_window + 1))
        sig_origin = f"volatilidad histórica {req.sigma_window} sesiones al {last_date} (estimación estadística)"
    else:
        sig, sig_origin = req.sigma, req.sigma_origin or DataOrigin.USER_ASSUMPTION.value
    exp = sc.EquityExposure(req.ticker, req.shares, spot, spot_prov, req.horizon_years, sig, sig_origin, req.r,
                            req.r_origin, req.q, req.declared, budget=req.budget, objective=req.objective)
    base = sc.default_profiles()
    profiles = {k: sc.profile_from_dict(req.profiles.get(k, {}), v) for k, v in base.items()}
    for k, v in req.profiles.items():
        if k not in profiles:
            profiles[k] = sc.profile_from_dict(v, base["equilibrado"])
    fut = None
    if req.futures_symbol:
        c = db.scalar(select(FuturesContract).where(FuturesContract.symbol == req.futures_symbol))
        if not c:
            raise HTTPException(404, "contrato de futuro no encontrado")
        price, src = req.futures_price, req.futures_price_source
        if price is None and c.last_settlement is not None:
            price, src = float(c.last_settlement), f"precio de liquidación {c.settlement_date} · {c.source}"
        if price is None or not src:
            raise HTTPException(422, "indique el precio del futuro observado y su fuente (o importe el boletín de MexDer)")
        fut = {"price": price, "status": "listado_verificado", "source": src}
        opt_T = (c.expiry - df.index.max().date()).days / 365.0
        if req.option_expiry_years is None and opt_T > 0:
            req.option_expiry_years = opt_T
    try:
        strats = {k: sc.equity_strategy_set(exp, p, req.multiplier, req.templates, req.option_expiry_years, fut,
                                            commission_per_contract=req.commission_per_contract)
                  for k, p in profiles.items()}
        res = sc.evaluate_equity(exp, strats, profiles, req.futures_basis_shock)
    except ValueError as e:
        raise HTTPException(422, str(e))
    res["profiles"] = {k: p.__dict__ for k, p in profiles.items()}
    res["strategies"] = {k: [{"name": s.name, "economic_function": s.economic_function,
                              "legs": [l.__dict__ for l in s.legs], "initial_cost": -s.initial_cash(),
                              "warnings": s.warnings, "params": s.params} for s in v] for k, v in strats.items()}
    src = _src(meta, f"{req.ticker} {req.series} spot") + [
        {"dato": "volatilidad", "fuente": sig_origin, "fecha": str(last_date), "origen": "estimación/supuesto", "estado": ""},
        {"dato": "tasa libre de riesgo", "fuente": req.r_origin, "fecha": "", "origen": "", "estado": ""}]
    return respond(db, "scenarios_equity", req.model_dump(), {"profiles": res["profiles"]},
                   ["P&L combinado = exposición + overlay"], res, src)


class RateScenarioReq(BaseModel):
    curve_id: int
    kind: Literal["pasivo", "activo"]
    notional: float = Field(gt=0)
    currency: str = "MXN"
    reference_rate: str = "TIIE_28"
    spread: float = 0.0
    start: date
    end: date
    frequency: str = "28D"
    day_count: str = "ACT/360"
    rate_style: Literal["term_fixed_in_advance", "compounded_in_arrears"] = "term_fixed_in_advance"
    amortization: Optional[list[float]] = None
    declared: bool = False
    model: Literal["black76", "bachelier"] = "black76"
    vol: float = 0.2
    vol_origin: str = DataOrigin.USER_ASSUMPTION.value
    strikes: Optional[dict] = None
    known_fixings: dict[int, float] = {}
    accrued_factor: dict[int, float] = {}
    profiles: dict[str, dict] = {}


@router.post("/scenarios/rates")
def scenarios_rates(req: RateScenarioReq, db: Session = Depends(get_session)):
    disc = load_curve(db, req.curve_id)
    exp = sc.RateExposure(req.kind, req.notional, req.currency, req.reference_rate, req.spread, req.start, req.end,
                          req.frequency, req.day_count, req.rate_style, req.amortization, req.declared,
                          known_fixings={int(k): v for k, v in req.known_fixings.items()},
                          accrued_factor={int(k): v for k, v in req.accrued_factor.items()})
    base = sc.default_profiles()
    profiles = {k: sc.profile_from_dict(req.profiles.get(k, {}), v) for k, v in base.items()}
    try:
        res = sc.evaluate_rates(exp, disc, profiles, req.model, req.vol, req.vol_origin, req.strikes)
    except ValueError as e:
        raise HTTPException(422, str(e))
    res["profiles"] = {k: p.__dict__ for k, p in profiles.items()}
    src = [{"dato": "curva", "fuente": disc.source, "fecha": str(disc.curve_date), "origen": disc.origin, "estado": ""},
           {"dato": "volatilidad", "fuente": req.vol_origin, "fecha": "", "origen": req.vol_origin, "estado": ""}]
    return respond(db, "scenarios_rates", req.model_dump(), {"profiles": res["profiles"]}, ["flujos por periodo"], res, src)


@router.get("/profiles/defaults")
def profiles_defaults():
    return {k: p.__dict__ for k, p in sc.default_profiles().items()} | {"_scenarios": sc.SCENARIO_LABELS}


class RankReq(BaseModel):
    audit_id: int
    criterion: str
    profile: Optional[str] = None
    descending: bool = True


@router.post("/scenarios/rank")
def scenarios_rank(req: RankReq, db: Session = Depends(get_session)):
    a = db.get(AuditRecord, req.audit_id)
    if not a or "evaluations" not in a.result:
        raise HTTPException(404, "resultado de escenarios no encontrado")
    try:
        rows = sc.rank(a.result["evaluations"], req.criterion, req.profile, req.descending)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return [{"profile": r["profile"], "strategy": r["strategy"], "economic_function": r["economic_function_label"]}
            for r in rows]


class ExposureReq(BaseModel):
    kind: Literal["equity", "rate_liability", "rate_asset"]
    declared: bool
    payload: dict


@router.post("/exposures")
def exposure_create(req: ExposureReq, db: Session = Depends(get_session)):
    e = Exposure(kind=req.kind, declared=req.declared, payload=to_jsonable(req.payload))
    db.add(e)
    db.commit()
    return {"id": e.id}


@router.get("/exposures")
def exposure_list(db: Session = Depends(get_session)):
    return [to_jsonable({"id": e.id, "kind": e.kind, "declared": e.declared, "payload": e.payload,
                         "created_at": e.created_at}) for e in db.scalars(select(Exposure).order_by(Exposure.id.desc()))]


# ================================================================ IA, reportes, estudios, auditoría

class ExplainReq(BaseModel):
    question: str
    audit_id: Optional[int] = None
    context: Optional[dict] = None


@router.post("/ai/explain")
def ai_explain(req: ExplainReq, db: Session = Depends(get_session)):
    if req.audit_id:
        a = db.get(AuditRecord, req.audit_id)
        if not a:
            raise HTTPException(404, "cálculo no encontrado")
        ctx = {"calculation": a.calculation, "inputs": a.inputs, "result": a.result, "sources": a.data_sources}
        if isinstance(a.result, dict) and "evaluations" in a.result:
            ctx = {**a.result, "calculation": a.calculation}
    elif req.context:
        ctx = req.context
    else:
        raise HTTPException(422, "proporcione audit_id o context")
    return ai_explainer.explain(req.question, ctx)


class StudyReq(BaseModel):
    title: str
    subject: str
    audit_ids: list[int]
    executive_summary: Optional[str] = None
    conclusions: Optional[str] = None
    assumptions: list[str] = []


def compose_study(db: Session, req: StudyReq) -> dict:
    study = {"title": req.title, "subject": req.subject, "generated_at": datetime.now(timezone.utc).isoformat(),
             "engine_version": ENGINE_VERSION, "sources": [], "assumptions": list(req.assumptions),
             "limitations": ["Datos limitados a la cobertura de las fuentes importadas/verificadas.",
                             "Precios teóricos y escenarios son resultados de modelo/hipótesis, no cotizaciones.",
                             "El calendario de días inhábiles por reglas debe contrastarse con el oficial."],
             "executive_summary": req.executive_summary, "conclusions": req.conclusions, "audit_ids": req.audit_ids}
    for aid in req.audit_ids:
        a = db.get(AuditRecord, aid)
        if not a:
            raise HTTPException(404, f"cálculo {aid} no encontrado")
        study["sources"] += a.data_sources or []
        r = a.result
        if a.calculation == "technical":
            study["technical"] = {"rows": r["rows"][-250:]}
            study["historical"] = {"rows": [{"date": x["date"], "close": x["close"]} for x in r["rows"]], "meta": r["meta"]}
            study["technical_summary"] = {"fibonacci_trend": (r.get("fibonacci") or {}).get("trend"),
                                          "ultimo_rsi_14": next((x.get("rsi_14") for x in reversed(r["rows"]) if x.get("rsi_14") is not None), None)}
        elif a.calculation == "risk":
            study["risk"] = {"volatility_annual": r.get("volatility_annual"),
                             "max_drawdown": (r.get("max_drawdown") or {}).get("max_drawdown"),
                             "var_hist": (r["summary"].get("var_hist") or {}).get("var"),
                             "es_hist": (r["summary"].get("var_hist") or {}).get("es"),
                             "beta_general": (r.get("beta_general") or {}).get("beta"),
                             "beta_custom": (r.get("beta_custom") or {}).get("beta"),
                             "r2_custom": (r.get("beta_custom") or {}).get("r_squared")}
        elif a.calculation == "ratios":
            study["ratios"] = r
        elif a.calculation == "dcf":
            study["dcf"] = r
        elif a.calculation == "capfloor":
            study["capfloor"] = r["valuation"]
            study["capfloor_sensitivities"] = {k: v for k, v in r["sensitivities"].items() if k != "key_rate_pv01"}
        elif a.calculation in ("scenarios_equity", "scenarios_rates"):
            study["scenarios"] = r
            study["profiles"] = r.get("profiles")
            study["exposure"] = r.get("exposure")
            if a.calculation == "scenarios_rates":
                study["curve"] = r.get("curve")
            strategies = []
            for pk, lst in (r.get("strategies") or {}).items():
                for s in lst:
                    strategies.append({**s, "name": f"{s['name']} [{pk}]"})
            study["strategies"] = strategies
        elif a.calculation == "futures":
            study["futures"] = {"gross_pnl": r.get("gross_pnl"), **{k: v for k, v in (r.get("margin") or {}).items()
                                                                   if k != "daily"}}
        elif a.calculation == "option_value":
            b = r.get("bsm") or {}
            study["options"] = {"prima_teorica": r["theoretical_premium"]["value"], "delta": b.get("delta"),
                                "gamma": b.get("gamma"), "vega": b.get("vega"), "theta_dia": b.get("theta_per_day"),
                                "crr": r["crr"]["price"], "iv": (r.get("implied_vol") or {}).get("implied_vol")}
    if not study["executive_summary"] and study.get("scenarios"):
        study["executive_summary"] = ai_explainer.rule_based_summary(study["scenarios"])["text"]
    return study


@router.post("/reports/xlsx")
def report_xlsx(req: StudyReq, db: Session = Depends(get_session)):
    data = reports.build_xlsx(compose_study(db, req))
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="informe.xlsx"'})


@router.post("/reports/pdf")
def report_pdf(req: StudyReq, db: Session = Depends(get_session)):
    data = reports.build_pdf(compose_study(db, req))
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="informe.pdf"'})


@router.post("/studies")
def study_save(req: StudyReq, db: Session = Depends(get_session)):
    prev = db.scalar(select(Study).where(Study.title == req.title).order_by(Study.version.desc()))
    s = Study(title=req.title, kind="estudio", version=(prev.version + 1) if prev else 1, inputs=req.model_dump(),
              results=to_jsonable(compose_study(db, req)))
    db.add(s)
    db.commit()
    return {"id": s.id, "version": s.version}


@router.get("/studies")
def study_list(db: Session = Depends(get_session)):
    return [to_jsonable({"id": s.id, "title": s.title, "version": s.version, "created_at": s.created_at,
                         "audit_ids": s.inputs.get("audit_ids")}) for s in db.scalars(select(Study).order_by(Study.id.desc()))]


@router.get("/studies/{sid}")
def study_get(sid: int, db: Session = Depends(get_session)):
    s = db.get(Study, sid)
    if not s:
        raise HTTPException(404, "estudio no encontrado")
    return to_jsonable({"id": s.id, "title": s.title, "version": s.version, "inputs": s.inputs, "results": s.results})


@router.get("/audit/{aid}")
def audit_get(aid: int, db: Session = Depends(get_session)):
    a = db.get(AuditRecord, aid)
    if not a:
        raise HTTPException(404, "registro no encontrado")
    return to_jsonable({c.name: getattr(a, c.name) for c in AuditRecord.__table__.columns})


@router.get("/audit")
def audit_list(limit: int = 50, db: Session = Depends(get_session)):
    return [to_jsonable({"id": a.id, "calculation": a.calculation, "created_at": a.created_at,
                         "digest": a.result_digest})
            for a in db.scalars(select(AuditRecord).order_by(AuditRecord.id.desc()).limit(limit))]
