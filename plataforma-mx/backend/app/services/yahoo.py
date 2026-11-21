"""Conector Yahoo Finance (librería yfinance).

El usuario designó Yahoo Finance como FUENTE DE REFERENCIA de la plataforma para uso personal
y de investigación (términos de Yahoo revisados y aceptados por el usuario). Por eso sus
observaciones se registran con origen `observado_fuente_oficial`. La fuente se identifica
siempre de forma explícita, por ejemplo:

    "Yahoo Finance (yfinance) · fuente de referencia designada por el usuario · WALMEX.MX"

Reglas de veracidad que se mantienen:
- Los datos pasan por los mismos importadores validados que los archivos CSV/Excel.
- Una barra sin cierre (NaN), o la barra de la sesión en curso antes del cierre, se RECHAZA.
  No se rellena ni se interpola.
- Precios con la precisión de puja de la BMV (2 decimales). El texto publicado se redondea desde
  el flotante de Yahoo, cuyos artefactos binarios se eliminan; esta transformación se documenta.
- `Close` de Yahoo está ajustado por splits, no por dividendos. `Adj Close` se guarda como
  cierre ajustado. Ninguno se presenta como el precio de cierre de la subasta de la BMV.
"""
from __future__ import annotations

import io
import math
from datetime import date, datetime, timedelta, timezone

import pandas as pd

SOURCE_TAG = "Yahoo Finance (yfinance) · fuente de referencia designada por el usuario"
MX_TZ = timezone(timedelta(hours=-6))
SESSION_CLOSE_HOUR = 16  # margen sobre el cierre de la BMV (15:00 CDMX) para considerar el día cerrado

FIN_MAP = {
    "income": {
        "revenue": ["Total Revenue", "Operating Revenue"],
        "gross_profit": ["Gross Profit"],
        "ebitda": ["EBITDA"],
        "ebit": ["EBIT"],
        "net_income": ["Net Income Common Stockholders", "Net Income"],
        "interest_expense": ["Interest Expense"],
        "depreciation_amortization": ["Reconciled Depreciation"],
    },
    "balance": {
        "total_assets": ["Total Assets"],
        "current_assets": ["Current Assets"],
        "inventories": ["Inventory"],
        "cash": ["Cash And Cash Equivalents"],
        "total_liabilities": ["Total Liabilities Net Minority Interest"],
        "current_liabilities": ["Current Liabilities"],
        "total_debt": ["Total Debt"],
        "total_equity": ["Stockholders Equity"],
        "minority_interest": ["Minority Interest"],
        "shares_outstanding": ["Ordinary Shares Number", "Share Issued"],
    },
    "cashflow": {
        "cfo": ["Operating Cash Flow"],
        "cfi": ["Investing Cash Flow"],
        "cff": ["Financing Cash Flow"],
        "capex": ["Capital Expenditure"],
        "dividends_paid": ["Cash Dividends Paid"],
    },
}
_FIN_ATTR = {"income": ("income_stmt", "quarterly_income_stmt"), "balance": ("balance_sheet", "quarterly_balance_sheet"),
             "cashflow": ("cashflow", "quarterly_cashflow")}


def yahoo_symbol(ticker: str, series: str, override: str | None = None) -> str:
    """Convención de Yahoo para la BMV: emisora + serie + '.MX' (serie '*' se omite).
    Ejemplos: WALMEX * → WALMEX.MX · GFNORTE O → GFNORTEO.MX · CEMEX CPO → CEMEXCPO.MX.
    Índices y casos especiales: use `override` (p. ej. ^MXX para el S&P/BMV IPC)."""
    if override:
        return override.strip()
    s = series.strip().upper()
    return f"{ticker.strip().upper()}{'' if s in ('*', '') else s}.MX"


def _yf():
    import yfinance as yf
    return yf


def _fmt(v: float, dec: int = 2) -> str | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return f"{round(float(v), dec):.{dec}f}"


def history_to_rows(df: pd.DataFrame, ticker: str, series: str, symbol: str, currency: str,
                    now: datetime | None = None) -> tuple[list[dict], list[dict]]:
    """Convierte el DataFrame de yfinance (auto_adjust=False) en renglones de la plantilla de precios.
    Devuelve (renglones, rechazados_previos)."""
    now = now or datetime.now(MX_TZ)
    today = now.date()
    retrieved = now.isoformat()
    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs(symbol, axis=1, level=1) if symbol in df.columns.get_level_values(1) else df.droplevel(1, axis=1)
    rows, rejected = [], []
    for ts, r in df.iterrows():
        d = pd.Timestamp(ts).date()
        close = r.get("Close")
        if close is None or pd.isna(close):
            rejected.append({"date": d.isoformat(), "errors": ["barra sin cierre publicado (NaN): no se rellena"]})
            continue
        if d > today:
            rejected.append({"date": d.isoformat(), "errors": ["fecha futura"]})
            continue
        if d == today and now.hour < SESSION_CLOSE_HOUR:
            rejected.append({"date": d.isoformat(), "errors": ["sesión en curso: el último precio aún no es un cierre"]})
            continue
        freshness = "preliminar" if d == today else "historico"
        vol = r.get("Volume")
        rows.append({
            "ticker": ticker, "series": series, "identifier": symbol, "market": "BMV",
            "source": f"{SOURCE_TAG} · {symbol}", "price_type": "cierre_oficial",
            "market_date": d.isoformat(), "publication_date": d.isoformat(), "retrieved_at": retrieved,
            "time": "", "timezone": "America/Mexico_City", "currency": currency, "precision": 2,
            "freshness": freshness, "origin": "observado_fuente_oficial", "data_version": "1",
            "open": _fmt(r.get("Open")), "high": _fmt(r.get("High")), "low": _fmt(r.get("Low")),
            "close": _fmt(close), "adj_close": _fmt(r.get("Adj Close")),
            "volume": "" if vol is None or pd.isna(vol) else str(int(vol)),
        })
    return rows, rejected


def fetch_prices(ticker: str, series: str, start: date | None, end: date | None, override: str | None = None,
                 period: str | None = None) -> dict:
    symbol = yahoo_symbol(ticker, series, override)
    yf = _yf()
    try:
        kw = dict(auto_adjust=False, actions=False, progress=False, interval="1d", threads=False)
        if start:
            kw["start"] = start.isoformat()
            kw["end"] = (end + timedelta(days=1)).isoformat() if end else None
        else:
            kw["period"] = period or "5y"
        df = yf.download(symbol, **kw)
    except Exception as e:  # red, bloqueo, símbolo inválido
        return {"status": "no_disponible", "symbol": symbol, "reason": f"{type(e).__name__}: {str(e)[:200]}"}
    if df is None or df.empty:
        return {"status": "no_disponible", "symbol": symbol, "reason": "Yahoo no devolvió observaciones para el símbolo"}
    currency = "MXN"
    try:
        currency = (yf.Ticker(symbol).fast_info.get("currency") or "MXN").upper()
    except Exception:
        pass
    rows, rejected = history_to_rows(df, ticker, series, symbol, currency)
    return {"status": "ok", "symbol": symbol, "currency": currency, "rows": rows, "pre_rejected": rejected}


def rows_to_csv(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    pd.DataFrame(rows).to_csv(buf, index=False)
    return buf.getvalue().encode()


def fetch_financials(ticker: str, series: str, quarterly: bool = False, override: str | None = None) -> dict:
    """Estados financieros de Yahoo mapeados a las partidas de la plataforma. Las partidas que Yahoo
    no publica se omiten: no se calculan ni se rellenan."""
    symbol = yahoo_symbol(ticker, series, override)
    yf = _yf()
    try:
        t = yf.Ticker(symbol)
        fin_ccy = None
        try:
            fin_ccy = (t.get_info() or {}).get("financialCurrency")
        except Exception:
            pass
        currency = (fin_ccy or t.fast_info.get("currency") or "MXN").upper()
        frames = {k: getattr(t, attrs[1] if quarterly else attrs[0]) for k, attrs in _FIN_ATTR.items()}
    except Exception as e:
        return {"status": "no_disponible", "symbol": symbol, "reason": f"{type(e).__name__}: {str(e)[:200]}"}
    retrieved = datetime.now(MX_TZ).isoformat()
    rows, found = [], set()
    for stmt, df in frames.items():
        if df is None or df.empty:
            continue
        for col in df.columns:
            pe = pd.Timestamp(col).date()
            for key, labels in FIN_MAP[stmt].items():
                label = next((l for l in labels if l in df.index and not pd.isna(df.at[l, col])), None)
                if label is None:
                    continue
                found.add((stmt, key))
                val = float(df.at[label, col])
                if key in ("dividends_paid", "capex"):
                    val = abs(val)  # Yahoo los reporta como salidas negativas; la plataforma usa montos positivos
                rows.append({"ticker": ticker, "statement": stmt, "period_type": "Q" if quarterly else "FY",
                             "period_end": pe.isoformat(), "basis": "consolidado", "currency": currency, "units": "unidades",
                             "item": key, "value": repr(val),
                             "source": f"{SOURCE_TAG} · {symbol} · {label}", "retrieved_at": retrieved})
    if not rows:
        return {"status": "no_disponible", "symbol": symbol, "reason": "Yahoo no publicó estados financieros para el símbolo"}
    return {"status": "ok", "symbol": symbol, "currency": currency, "rows": rows,
            "missing_items": {st: [k for k in keys if (st, k) not in found] for st, keys in FIN_MAP.items()
                              if any((st, k) not in found for k in keys)},
            "notes": ["Base consolidada según Yahoo; capex y dividendos pagados se guardan como montos positivos.",
                      "La partida 'net_income' usa la utilidad atribuible a accionistas comunes cuando existe."]}


def fetch_dividends(ticker: str, series: str, override: str | None = None) -> dict:
    symbol = yahoo_symbol(ticker, series, override)
    try:
        s = _yf().Ticker(symbol).dividends
    except Exception as e:
        return {"status": "no_disponible", "symbol": symbol, "reason": f"{type(e).__name__}: {str(e)[:200]}"}
    rows = [{"ex_date": pd.Timestamp(i).date().isoformat(), "amount": float(v)} for i, v in s.items()]
    today = datetime.now(MX_TZ).date()
    ttm = sum(r["amount"] for r in rows if date.fromisoformat(r["ex_date"]) > today - timedelta(days=365))
    return {"status": "ok", "symbol": symbol, "source": f"{SOURCE_TAG} · {symbol}", "dividends": rows,
            "dps_ttm": ttm if rows else None, "retrieved_at": datetime.now(MX_TZ).isoformat(),
            "note": "Fecha = fecha ex-dividendo según Yahoo; montos por acción en la moneda de cotización."}
