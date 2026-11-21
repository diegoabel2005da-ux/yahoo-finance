"""Pruebas del conector Yahoo con un yfinance SIMULADO (sin red). Las cifras son sintéticas."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import yahoo

MX = timezone(timedelta(hours=-6))


def fake_history(dates, nan_last=False):
    n = len(dates)
    close = np.linspace(50, 52, n) + 0.000001  # artefacto binario típico de Yahoo
    df = pd.DataFrame({"Open": close - 0.1, "High": close + 0.3, "Low": close - 0.3, "Close": close,
                       "Adj Close": close - 0.5, "Volume": np.arange(n) * 1000 + 1000}, index=pd.DatetimeIndex(dates))
    if nan_last:
        df.iloc[-1, df.columns.get_loc("Close")] = np.nan
    return df


def test_symbol_convention():
    assert yahoo.yahoo_symbol("WALMEX", "*") == "WALMEX.MX"
    assert yahoo.yahoo_symbol("GFNORTE", "O") == "GFNORTEO.MX"
    assert yahoo.yahoo_symbol("CEMEX", "CPO") == "CEMEXCPO.MX"
    assert yahoo.yahoo_symbol("IPC", "*", "^MXX") == "^MXX"


def test_rows_reject_incomplete_and_session_in_progress():
    dates = pd.bdate_range("2026-11-16", "2026-11-20")
    now = datetime(2026, 11, 20, 11, 0, tzinfo=MX)
    rows, rej = yahoo.history_to_rows(fake_history(dates, nan_last=True), "X", "*", "X.MX", "MXN", now)
    assert len(rows) == 4 and rej[0]["errors"][0].startswith("barra sin cierre")
    rows, rej = yahoo.history_to_rows(fake_history(dates), "X", "*", "X.MX", "MXN", now)
    assert len(rows) == 4 and "sesión en curso" in rej[0]["errors"][0]
    rows, _ = yahoo.history_to_rows(fake_history(dates), "X", "*", "X.MX", "MXN", datetime(2026, 11, 20, 18, tzinfo=MX))
    assert len(rows) == 5 and rows[-1]["freshness"] == "preliminar" and rows[0]["freshness"] == "historico"
    r = rows[0]
    assert r["close"] == "50.00" and r["origin"] == "observado_fuente_oficial"
    assert "fuente de referencia designada por el usuario" in r["source"] and r["identifier"] == "X.MX"


def test_endpoint_imports_with_provenance(monkeypatch):
    dates = pd.bdate_range("2025-01-01", periods=60)

    class FakeTicker:
        def __init__(self, s):
            self.fast_info = {"currency": "MXN"}

    class FakeYF:
        Ticker = FakeTicker

        @staticmethod
        def download(symbol, **kw):
            assert symbol == "FICT.MX"
            return fake_history(dates)

    monkeypatch.setattr(yahoo, "_yf", lambda: FakeYF)
    c = TestClient(create_app("sqlite://"))
    cat = (b"issuer_name,ticker,series,isin,sector,exchange,currency,derivatives,active,catalog_source,reviewed_on,yahoo_symbol\n"
           b"Ficticia,FICT,*,,Prueba,BMV,MXN,opcion,true,PRUEBA,2026-11-21,\n")
    c.post("/api/catalog/import", files={"file": ("c.csv", cat)}, data={"source": "PRUEBA"})
    r = c.post("/api/yahoo/prices", json={"ticker": "FICT", "series": "*"}).json()
    assert r["status"] == "ok" and r["accepted_rows"] == 60
    again = c.post("/api/yahoo/prices", json={"ticker": "FICT", "series": "*"}).json()
    assert again["accepted_rows"] == 0 and again["duplicates_skipped"] == 60
    px = c.get("/api/prices/FICT/*").json()
    assert px["meta"]["validation_counts"] == {"validado": 60 * 6}
    assert px["meta"]["adjusted_close_available"]


def test_unreachable_is_reported_not_invented(monkeypatch):
    class Boom:
        @staticmethod
        def download(*a, **k):
            raise ConnectionError("bloqueado")

    monkeypatch.setattr(yahoo, "_yf", lambda: Boom)
    r = yahoo.fetch_prices("X", "*", None, None)
    assert r["status"] == "no_disponible" and "bloqueado" in r["reason"]
