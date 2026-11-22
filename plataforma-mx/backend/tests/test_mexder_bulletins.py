"""Pruebas del lector de boletines de MexDer con fragmentos de texto en el formato publicado.
Las cifras son SINTÉTICAS (sólo reproducen la disposición del boletín)."""
from datetime import date

import pytest

from app.services import mexder_bulletins as mb

FUT = """                  BOLETÍN DE FUTUROS / FUTURES BULLETIN
                                                   20 DE NOVIEMBRE DE 2026
  Boletín de Futuros - Precios de Liquidación e Interés Abierto
  Vencimiento   Precio de Liquidación Anterior    Precio de Liquidación   Interés Abierto
                       FUTUROS SOBRE EL S&P/BMV IPC / S&P/BMV IPC FUTURES
       2026/DIC/18            68,850                    68,676                 25,936
            MINI CONTRATO DE FUTURO DEL DOLAR / MINI U.S. DOLLAR CONTRACT FUTURE
       2026/DIC/14          19.145600                 19.206600                     1
                         WALMEX V / INDIVIDUAL EQUITY FUTURES
       2027/MAR/19          55.000000                 55.030000                     0
  Futures Bulletin - Settlement Prices and Open Interest
       2027/JUN/18          55.900000                 55.940000                 -----
"""

OPT = """   BOLETÍN DE OPCIONES / OPTIONS BULLETIN
                                     20 DE NOVIEMBRE DE 2026
  Boletín de Opciones - Precios de Liquidación e Interés Abierto
          OPCIONES SOBRE ACCIONES / INDIVIDUAL EQUITY OPTIONS ASUR B
      2026/DIC/18    C    4.9     35.00     33.00     0
  Options Bulletin - Settlement Prices & Open Interest
      2026/DIC/18    P    4.9      1.00      1.00     10
          OPCIONES SOBRE ACCIONES / INDIVIDUAL EQUITY OPTIONS WALMEX *
      2026/DIC/18    C    55       1.20      1.19     0
      2026/DIC/18    P    55       1.40      1.45     0
"""


def test_parse_futures_sections_aliases_and_page_breaks():
    f = mb.parse_futures(FUT)
    assert f["date"] == date(2026, 11, 20)
    syms = {r["symbol"]: r for r in f["rows"]}
    assert set(syms) == {"IPC DC26", "MD 14DC26", "WALMEX MR27", "WALMEX JN27"}
    assert syms["IPC DC26"]["settlement"] == 68676 and syms["IPC DC26"]["open_interest"] == 25936
    assert syms["MD 14DC26"]["spec"]["multiplier"] == 1000          # el mini dólar no se confunde con la sección previa
    assert syms["WALMEX JN27"]["meta"]["series"] == "*"             # alias WALMEX V, a través del salto de página
    assert syms["WALMEX JN27"]["open_interest"] is None             # «-----» = no publicado, no se rellena


def test_parse_options_and_infer_scale():
    o = mb.parse_options(OPT)
    assert len(o["rows"]) == 4 and {r["underlying"] for r in o["rows"]} == {"ASUR", "WALMEX"}
    sc = mb.infer_strike_scales(o["rows"], {"ASUR": 522.0, "WALMEX": 54.42})
    assert sc["ASUR"]["scale"] == 100.0       # (522 − (33 − 1)) / 4.9 ≈ 100
    assert sc["WALMEX"]["scale"] == 1.0       # (54.42 − (1.19 − 1.45)) / 55 ≈ 1
    assert mb.infer_strike_scales(o["rows"], {})["ASUR"]["scale"] is None   # sin precio: no se decide


def test_detect_kind():
    assert mb.detect_kind(FUT) == "futuros" and mb.detect_kind(OPT) == "opciones"
    with pytest.raises(ValueError):
        mb.detect_kind("otro documento")


def test_single_digit_day_and_tief_series_month():
    txt = FUT.replace("                         WALMEX V", "                TASA DE FONDEO / BANK FUNDING RATE FUTURES\n"
                      "       2026/DIC/1           6.330000                  6.330000                     0\n"
                      "                         WALMEX V")
    rows = {r["symbol"]: r for r in mb.parse_futures(txt)["rows"]}
    assert "TIEF NV26" in rows                      # vence 1-dic-2026 → serie de noviembre
    assert rows["TIEF NV26"]["expiry"] == date(2026, 12, 1) and rows["TIEF NV26"]["settlement"] == 6.33
