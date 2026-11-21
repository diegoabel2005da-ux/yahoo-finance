"""Pruebas de integración de la API con datos SINTÉTICOS de prueba (fuente 'PRUEBA-SINTETICA').

Ningún dato de este archivo representa información de mercado real; los tickers son ficticios.
"""
import io
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.main import create_app

SRC = "PRUEBA-SINTETICA"


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app("sqlite://"))


def csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode()


def catalog_csv():
    return csv(pd.DataFrame([
        dict(issuer_name="Emisora Ficticia A", ticker="FICTA", series="A", isin="MX0000000001", sector="Prueba",
             exchange="BMV", currency="MXN", derivatives="futuro|opcion", active="true", catalog_source=SRC,
             reviewed_on="2026-11-20"),
        dict(issuer_name="Emisora Ficticia A", ticker="FICTA", series="B", isin="", sector="Prueba", exchange="BMV",
             currency="MXN", derivatives="opcion", active="true", catalog_source=SRC, reviewed_on="2026-11-20"),
        dict(issuer_name="Indice Ficticio", ticker="IDXF", series="*", isin="", sector="Índice", exchange="BMV",
             currency="MXN", derivatives="futuro", active="true", catalog_source=SRC, reviewed_on="2026-11-20"),
        dict(issuer_name="Mala", ticker="MALA", series="X", isin="XX", sector="", exchange="NYSE", currency="MXN",
             derivatives="swap", active="true", catalog_source=SRC, reviewed_on="2026-11-20"),
    ]))


def prices_csv(ticker, series, origin, seed, n=320, bump=None, version="1"):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2025-08-01", periods=n)
    c = 50 * np.exp(np.cumsum(rng.normal(0.0002, 0.012, n)))
    rows = []
    for i, d in enumerate(days):
        close = round(c[i], 2)
        if bump and i == bump:
            close = round(close + 0.05, 2)
        hi, lo = round(max(close, c[i]) * 1.006, 2), round(min(close, c[i]) * 0.994, 2)
        rows.append(dict(ticker=ticker, series=series, identifier=f"{ticker}{series}", market="BMV", source=f"{SRC}-{origin}",
                         price_type="cierre_oficial", market_date=d.date().isoformat(), publication_date=d.date().isoformat(),
                         retrieved_at="2026-11-20T18:00:00-06:00", currency="MXN", precision=2, freshness="historico",
                         origin=origin, data_version=version, open=close, high=hi, low=lo, close=close,
                         volume=int(rng.integers(1e5, 1e6))))
    return csv(pd.DataFrame(rows))


def test_full_flow(client):
    r = client.post("/api/catalog/import", files={"file": ("cat.csv", catalog_csv())}, data={"source": SRC})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] == 3 and len(body["rejected"]) == 1
    cat = client.get("/api/catalog").json()["instruments"]
    assert {(i["ticker"], i["series"]) for i in cat} == {("FICTA", "A"), ("FICTA", "B"), ("IDXF", "*")}
    assert not cat[0]["availability"]["prices"]

    # Emisora con varias series: hay que especificar la serie
    r = client.post("/api/technical", json={"ticker": "FICTA", "series": "A"})
    assert r.status_code == 422  # sin precios aún: no se inventan

    r = client.post("/api/prices/import", files={"file": ("p.csv", prices_csv("FICTA", "A", "observado_fuente_oficial", 1))})
    assert r.status_code == 200 and r.json()["accepted_rows"] == 320
    client.post("/api/prices/import", files={"file": ("i.csv", prices_csv("IDXF", "*", "observado_fuente_oficial", 2))})

    # Renglón inválido: high < low → rechazado, no corregido
    bad = pd.read_csv(io.BytesIO(prices_csv("FICTA", "B", "observado_fuente_oficial", 3, n=3)))
    bad.loc[1, "high"] = 1.0
    bad.loc[2, "currency"] = "USD"
    r = client.post("/api/prices/import", files={"file": ("b.csv", csv(bad))}).json()
    assert r["accepted_rows"] == 1 and len(r["rejected"]) == 2

    px = client.get("/api/prices/FICTA/A", params={"freq": "semanal"}).json()
    assert px["meta"]["observations"] == 320 and px["meta"]["validation_counts"]
    assert px["rows"][0]["volume"] > 0

    an = client.get("/api/catalog/FICTA/A/analyses").json()
    assert all(a["available"] for a in an if a["analysis"].startswith(("Históricos", "RSI")))
    assert not next(a for a in an if a["analysis"] == "Futuros listados")["available"]

    t = client.post("/api/technical", json={"ticker": "FICTA", "series": "A", "rsi_periods": [9, 14, 25], "roc_n": 10})
    assert t.status_code == 200, t.text
    tech = t.json()
    assert {"rsi_9", "rsi_14", "rsi_25", "williams_r", "stoch_k"} <= set(tech["result"]["rows"][-1])
    assert client.get(f"/api/audit/{tech['audit_id']}").json()["result_digest"] == tech["result_digest"]

    rk = client.post("/api/risk", json={"ticker": "FICTA", "series": "A", "benchmark_ticker": "IDXF",
                                        "benchmark_series": "*", "start": "2026-01-01"}).json()["result"]
    assert rk["beta_general"]["observations"] > rk["beta_custom"]["observations"] > 100
    assert rk["summary"]["var_hist"]["var"] > 0

    pat = client.post("/api/patterns", json={"ticker": "FICTA", "series": "A"})
    assert pat.status_code == 200

    # Escenarios accionarios: 3 perfiles × (5 estrategias + sin cobertura) × 5 escenarios
    sc = client.post("/api/scenarios/equity", json={"ticker": "FICTA", "series": "A", "shares": 20000, "r": 0.07,
                                                    "r_origin": "supuesto de prueba"})
    assert sc.status_code == 200, sc.text
    scj = sc.json()
    assert scj["result"]["n_evaluations"] == 3 * 6 * 5
    spot = scj["result"]["exposure"]["spot"]
    assert spot == px["rows"][-1]["close"]  # spot = último cierre oficial importado
    # personalizar choques recalcula
    sc2 = client.post("/api/scenarios/equity", json={"ticker": "FICTA", "series": "A", "shares": 20000, "r": 0.07,
                                                     "r_origin": "supuesto de prueba",
                                                     "profiles": {"conservador": {"equity_shocks": {"estres_adverso_severo": 0.5}}}}).json()
    e1 = next(r for r in scj["result"]["evaluations"] if r["profile"] == "conservador")
    e2 = next(r for r in sc2["result"]["evaluations"] if r["profile"] == "conservador")
    assert e2["scenarios"]["estres_adverso_severo"]["S_final"] == pytest.approx(spot * 0.5)
    assert e1["scenarios"]["estres_adverso_severo"]["S_final"] != e2["scenarios"]["estres_adverso_severo"]["S_final"]

    # Curva + cap + escenarios de tasas
    curve = csv(pd.DataFrame({"days": [28, 91, 182, 364, 728, 1092], "value": [7.2, 7.15, 7.1, 7.0, 6.95, 7.0]}))
    cr = client.post("/api/curves/import", files={"file": ("c.csv", curve)},
                     data={"name": "Curva de prueba", "curve_date": "2026-11-20", "quote_kind": "zero_rate_pct",
                           "compounding": "continua", "day_count": "ACT/360", "interpolation": "log_linear_df",
                           "source": SRC, "origin": "observado_proveedor_secundario"})
    assert cr.status_code == 200, cr.text
    cid = cr.json()["curve_id"]
    cap = client.post("/api/capfloor/value", json={"curve_id": cid, "kind": "cap", "notional": 1e8, "strike": 0.075,
                                                   "start": "2026-12-01", "end": "2028-11-28", "vol": 0.2,
                                                   "compare_normal_vol": 0.014, "compare_lognormal_vol": 0.2})
    assert cap.status_code == 200, cap.text
    capj = cap.json()
    assert capj["result"]["valuation"]["origin"] == "resultado_de_modelo"
    assert "OTC" in capj["result"]["valuation"]["instrument_status"]
    rs = client.post("/api/scenarios/rates", json={"curve_id": cid, "kind": "pasivo", "notional": 5e8, "spread": 0.012,
                                                   "start": "2026-12-01", "end": "2028-11-28"})
    assert rs.status_code == 200, rs.text
    assert rs.json()["result"]["n_evaluations"] == 3 * 4 * 5

    # Reportes: valores idénticos a los del backend
    req = {"title": "Estudio de prueba", "subject": "FICTA A", "audit_ids": [tech["audit_id"], scj["audit_id"],
                                                                             capj["audit_id"]]}
    x = client.post("/api/reports/xlsx", json=req)
    assert x.status_code == 200
    wb = load_workbook(io.BytesIO(x.content))
    assert len(wb.sheetnames) == 17
    ws = wb["Escenarios"]
    first = scj["result"]["evaluations"][0]["scenarios"]["estres_adverso_severo"]
    assert ws["G4"].value == pytest.approx(first["combined_pnl"])
    assert ws["H4"].value == "=E4+F4"
    p = client.post("/api/reports/pdf", json=req)
    assert p.status_code == 200 and p.content[:4] == b"%PDF"
    st = client.post("/api/studies", json=req).json()
    assert client.post("/api/studies", json=req).json()["version"] == st["version"] + 1

    ai = client.post("/api/ai/explain", json={"question": "Compara las alternativas", "audit_id": scj["audit_id"]}).json()
    assert ai["mode"] in ("reglas", "llm") and ai["text"]


def test_reconciliation_blocks(client):
    # Proveedor secundario con una cifra distinta a la oficial → discrepancia → cálculos bloqueados
    r = client.post("/api/prices/import", files={"file": ("s.csv", prices_csv("FICTA", "A", "observado_proveedor_secundario", 1,
                                                                             bump=10))}).json()
    # en la fecha alterada difieren open, high y close (el fixture deriva open/high del cierre)
    assert len(r["discrepancies"]) == 3 and len({d["date"] for d in r["discrepancies"]}) == 1
    assert client.post("/api/technical", json={"ticker": "FICTA", "series": "A"}).status_code == 409
    ds = client.get("/api/discrepancies").json()
    assert client.post(f"/api/discrepancies/{ds[0]['id']}/resolve", data={"note": "corto"}).status_code == 422
    for d in ds:
        assert client.post(f"/api/discrepancies/{d['id']}/resolve",
                           data={"note": "Se conserva el cierre oficial; proveedor secundario excluido."}).status_code == 200
    t = client.post("/api/technical", json={"ticker": "FICTA", "series": "A"})
    assert t.status_code == 200
    # el valor discrepante no entra al cálculo: se usa el oficial
    px = client.get("/api/prices/FICTA/A").json()
    assert all("PRUEBA-SINTETICA-observado_fuente_oficial" in s for s in px["meta"]["sources"])


def test_theoretical_prices_cannot_be_imported(client):
    df = pd.read_csv(io.BytesIO(prices_csv("FICTA", "A", "observado_fuente_oficial", 9, n=1)))
    df["price_type"] = "precio_teorico_calculado"
    r = client.post("/api/prices/import", files={"file": ("t.csv", csv(df))}).json()
    assert r["accepted_rows"] == 0


def test_option_endpoint_guards(client):
    r = client.post("/api/options/value", json={"kind": "call", "S": 100, "K": 100, "T": 0.5, "r": 0.1, "sigma": 0.3,
                                                "observed_premium": 9.0, "observed_premium_origin": "resultado_de_modelo"})
    assert r.status_code == 422
    r = client.post("/api/options/value", json={"kind": "put", "S": 100, "K": 100, "T": 0.5, "r": 0.1, "sigma": 0.3,
                                                "style": "americana", "tree_steps": 4})
    assert r.status_code == 200 and len(r.json()["result"]["tree"]["price_tree"]) == 5


def test_untraceable_numbers():
    from app.services.ai_explainer import untraceable_numbers
    ctx = {"value": 1234567.891, "rate": 0.0725}
    assert untraceable_numbers("El valor es 1,234,567.89 y la tasa 7.25%", ctx) == []
    assert untraceable_numbers("La prima es 98765.4", ctx) == ["98765.4"]
