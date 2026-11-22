"""Lectura de los boletines diarios de MexDer (futuros y opciones, versión «básica» en PDF).

Se extraen SÓLO las secciones «Precios de Liquidación e Interés Abierto»: serie por serie, el
vencimiento real, el precio de liquidación anterior, el actual y el interés abierto. Las
especificaciones contractuales (multiplicador, puja, liquidación) provienen de las páginas de
contratos de MexDer que el usuario proporcionó; los campos no publicados ahí quedan vacíos.

El precio de liquidación de opciones es el precio oficial que publica MexDer para cada serie.
Cuando una serie no operó en el día, MexDer lo determina con su propia metodología, así que no
equivale a una prima negociada. Se etiqueta como `precio_liquidacion` (observado, fuente oficial).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from datetime import date
from typing import Optional

MONTHS = {"ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SEP": 9,
          "OCT": 10, "NOV": 11, "DIC": 12}
MONTH_CODE = {1: "EN", 2: "FB", 3: "MR", 4: "AB", 5: "MY", 6: "JN", 7: "JL", 8: "AG", 9: "SP", 10: "OC", 11: "NV", 12: "DC"}
SPANISH_DATE = re.compile(r"(\d{1,2}) DE ([A-ZÁÉÍÓÚ]+) DE (\d{4})")
LONG_MONTHS = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8,
               "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12}
NUM = r"-?[\d,]+(?:\.\d+)?"
FUT_ROW = re.compile(rf"^\s*(\d{{4}})/([A-Z]{{3}})/(\d{{1,2}})\s+({NUM})\s+({NUM})\s+({NUM}|-----)\s*$")
OPT_ROW = re.compile(rf"^\s*(\d{{4}})/([A-Z]{{3}})/(\d{{1,2}})\s+([CP])\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM}|-----)\s*$")

# Alias de los boletines → (ticker, serie) del catálogo.
EQUITY_ALIASES = {
    "ALFA A": ("SIGMAF", "A", "alias confirmado por el usuario (ALFA A = SIGMAF A)"),
    "AMERICA MOVIL B": ("AMX", "B", "alias del boletín"),
    "AMX B": ("AMX", "B", None),
    "KOF L": ("KOF", "UBL", "alias del boletín (única serie de KOF en el catálogo)"),
    "WALMEX V": ("WALMEX", "*", "alias del boletín (única serie de WALMEX en el catálogo)"),
    "GMEXICO B": ("GMEXICO", "B", None),
}
GLOBALS = {"AAPL", "META", "NFLX", "NVDA", "TSLA"}

# Especificaciones tomadas de las páginas de contratos de MexDer (copiadas por el usuario el 2026-11-21).
FUTURE_SPECS = {
    "DA": dict(underlying="USD", multiplier=10_000, tick_size=0.0001, tick_value=1.00, settlement="no indicada", currency="MXN"),
    "MD": dict(underlying="USD", multiplier=1_000, tick_size=0.0001, tick_value=0.10, settlement="no indicada", currency="MXN"),
    "EURO": dict(underlying="EUR", multiplier=10_000, tick_size=0.0001, tick_value=1.00, settlement="no indicada", currency="MXN"),
    "IPC": dict(underlying="IPC", multiplier=10, tick_size=5, tick_value=50.00, settlement="no indicada", currency="MXN"),
    "MIP": dict(underlying="IPC", multiplier=2, tick_size=10, tick_value=20.00, settlement="no indicada", currency="MXN"),
    "TIEF": dict(underlying="TIIE_FONDEO", multiplier=100_000, tick_size=0.01, tick_value=None, settlement="no indicada", currency="MXN"),
    "CE91": dict(underlying="CETES_91", multiplier=10_000, tick_size=None, tick_value=None, settlement="no indicada", currency="MXN"),
    "BONO": dict(multiplier=1_000, tick_size=0.025, tick_value=None, settlement="fisica", currency="MXN"),
    "EQ_MX": dict(multiplier=100, tick_size=0.01, tick_value=1.00, settlement="fisica", currency="MXN"),
    "EQ_GLOBAL": dict(multiplier=1, tick_size=0.01, tick_value=0.01, settlement="financiera", currency="MXN"),
}


def pdf_to_text(path: str) -> str:
    """Extrae texto con disposición. Usa `pdftotext -layout` (poppler) o, si no existe, pdfplumber."""
    if shutil.which("pdftotext"):
        return subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, check=True).stdout
    import pdfplumber  # pragma: no cover
    with pdfplumber.open(path) as pdf:
        return "\f".join((p.extract_text(layout=True) or "") for p in pdf.pages)


def _num(s: str) -> Optional[float]:
    if s == "-----":
        return None
    return float(s.replace(",", ""))


def bulletin_date(text: str) -> date:
    m = SPANISH_DATE.search(text)
    if not m:
        raise ValueError("no se encontró la fecha del boletín")
    return date(int(m.group(3)), LONG_MONTHS[m.group(2)], int(m.group(1)))


def _expiry(y, mon, d) -> date:
    return date(int(y), MONTHS[mon], int(d))


def _settlement_section(text: str, marker: str) -> list[str]:
    i = text.find(marker)
    if i < 0:
        raise ValueError(f"no se encontró la sección «{marker}»")
    return text[i:].splitlines()


def classify_future(header: str) -> tuple[str, dict, dict]:
    """Devuelve (prefijo de clave, especificación, metadatos del subyacente) para un encabezado de sección."""
    h = header.upper()
    if "MINI CONTRATO DE FUTURO DEL DOLAR" in h:
        return "MD", FUTURE_SPECS["MD"], {"kind": "divisa"}
    if "DOLAR" in h:
        return "DA", FUTURE_SPECS["DA"], {"kind": "divisa"}
    if "EURO" in h:
        return "EURO", FUTURE_SPECS["EURO"], {"kind": "divisa"}
    if "MINI CONTRATO DE FUTUROS SOBRE EL S&P/BMV IPC" in h:
        return "MIP", FUTURE_SPECS["MIP"], {"kind": "indice", "ticker": "IPC", "series": "*"}
    if "S&P/BMV IPC" in h:
        return "IPC", FUTURE_SPECS["IPC"], {"kind": "indice", "ticker": "IPC", "series": "*"}
    if "TASA DE FONDEO" in h:
        return "TIEF", FUTURE_SPECS["TIEF"], {"kind": "tasa"}
    if "CETE 91" in h:
        return "CE91", FUTURE_SPECS["CE91"], {"kind": "tasa"}
    m = re.search(r"\b(M\d{6})\b", h)
    if m:
        return m.group(1), {**FUTURE_SPECS["BONO"], "underlying": m.group(1)}, {"kind": "bono"}
    if "INDIVIDUAL EQUITY FUTURES" in h:
        name = header.split("/")[0].strip()
        return _equity(name, futures=True)
    raise ValueError(f"sección de futuros no reconocida: {header.strip()}")


def _equity(name: str, futures: bool):
    name = re.sub(r"\s+", " ", name.strip().upper())
    if name in EQUITY_ALIASES:
        t, s, note = EQUITY_ALIASES[name]
    else:
        parts = name.rsplit(" ", 1)
        t, s, note = (parts[0], parts[1], None) if len(parts) == 2 else (parts[0], "*", None)
    is_global = t in GLOBALS
    spec = FUTURE_SPECS["EQ_GLOBAL" if is_global else "EQ_MX"]
    return (t, {**spec, "underlying": t},
            {"kind": "accion_global" if is_global else "accion", "ticker": t, "series": s, "bulletin_name": name,
             "alias_note": note})


def parse_futures(text: str) -> dict:
    bdate = bulletin_date(text)
    lines = _settlement_section(text, "Precios de Liquidación e Interés Abierto")
    out, current, unknown = [], None, []
    for ln in lines:
        if " / " in ln and re.search(r"\bFUTURES?\b", ln) and "Bulletin" not in ln and not FUT_ROW.match(ln):
            try:
                current = classify_future(ln.strip())
            except ValueError as e:
                current = None
                unknown.append(str(e))
            continue
        m = FUT_ROW.match(ln)
        if m and current:
            prefix, spec, meta = current
            exp = _expiry(*m.group(1, 2, 3))
            if prefix in ("DA", "MD"):
                sym = f"{prefix} {exp.day:02d}{MONTH_CODE[exp.month]}{exp.year % 100:02d}"
            elif prefix == "TIEF":
                # Vence el primer día hábil del mes SIGUIENTE al mes de la serie (CGC del contrato TIEF).
                sy, sm = (exp.year, exp.month - 1) if exp.month > 1 else (exp.year - 1, 12)
                sym = f"TIEF {MONTH_CODE[sm]}{sy % 100:02d}"
            else:
                sym = f"{prefix} {MONTH_CODE[exp.month]}{exp.year % 100:02d}"
            out.append({"prefix": prefix, "spec": spec, "meta": meta, "expiry": exp, "symbol": sym,
                        "previous_settlement": _num(m.group(4)), "settlement": _num(m.group(5)),
                        "open_interest": _num(m.group(6))})
    return {"date": bdate, "rows": out, "unrecognized_sections": unknown}


def parse_options(text: str) -> dict:
    bdate = bulletin_date(text)
    lines = _settlement_section(text, "Precios de Liquidación e Interés Abierto")
    out, current, unknown = [], None, []
    for ln in lines:
        u = ln.upper()
        if "OPCIONES SOBRE" in u and not OPT_ROW.match(ln):
            if "FUTUROS DE S&P/BMV IPC" in u:
                current = ("IPC", {"kind": "indice_futuro", "ticker": "IPC", "series": "*"}, 1, "europea", "no indicada")
            elif "DOLAR" in u:
                current = ("USD", {"kind": "divisa"}, 10_000, "europea", "no indicada")
            elif "OPCIONES SOBRE ACCIONES" in u:
                name = re.split(r"OPTIONS\s+", ln.strip(), flags=re.I)[-1]
                t, _, meta = _equity(name, futures=False)
                mult = 1 if t in GLOBALS else 100
                current = (t, meta, mult, "americana", "financiera" if t in GLOBALS else "fisica")
            else:
                current = None
                unknown.append(ln.strip())
            continue
        m = OPT_ROW.match(ln)
        if m and current:
            under, meta, mult, style, settle = current
            exp = _expiry(*m.group(1, 2, 3))
            kind = "call" if m.group(4) == "C" else "put"
            k = _num(m.group(5))
            out.append({"underlying": under, "meta": meta, "multiplier": mult, "style": style, "settlement_type": settle,
                        "expiry": exp, "option_type": kind, "strike": k,
                        "symbol": f"{under}{meta.get('series', '') if meta.get('series') not in (None, '*') else ''} "
                                  f"{kind.upper()} {exp.isoformat()} K{k:g}(publicado)",
                        "previous_settlement": _num(m.group(6)), "settlement": _num(m.group(7)),
                        "open_interest": _num(m.group(8))})
    return {"date": bdate, "rows": out, "unrecognized_sections": unknown}


def detect_kind(text: str) -> str:
    head = text[:3000].upper()
    if "BOLETÍN DE OPCIONES" in head or "OPTIONS BULLETIN" in head:
        return "opciones"
    if "BOLETÍN DE FUTUROS" in head or "FUTURES BULLETIN" in head:
        return "futuros"
    raise ValueError("el documento no parece un boletín de futuros u opciones de MexDer")


# ============================================================ escala de strikes

def infer_strike_scales(rows: list[dict], spots: dict[str, float]) -> dict[str, dict]:
    """El boletín publica, para algunos subyacentes, el strike dividido entre 100 (p. ej. «4.90» = $490).
    La escala se INFIERE por paridad put-call, sin modelo: para cada strike con call y put,
    K_implícito ≈ S − (C − P), y la razón K_implícito / K_publicado da el factor.
    Se acepta ×1 si la mediana está en [0.8, 1.25] y ×100 si está en [80, 125]; en otro caso no se decide."""
    import statistics

    pairs: dict[str, dict] = {}
    for r in rows:
        if r["underlying"] in ("IPC", "USD") or not r["settlement"]:
            continue
        pairs.setdefault(r["underlying"], {}).setdefault((r["expiry"], r["strike"]), {})[r["option_type"]] = r["settlement"]
    out = {}
    for und, ks in pairs.items():
        S = spots.get(und)
        near = min((e for e, _ in ks), default=None)  # sólo el vencimiento más cercano: el descuento por tasa es despreciable
        ratios = [(S - (cp["call"] - cp["put"])) / K for (e, K), cp in ks.items()
                  if S and e == near and K > 0 and "call" in cp and "put" in cp] if S else []
        if not ratios:
            out[und] = {"scale": None, "evidence": "sin precio del subyacente o sin pares call/put para verificar"}
            continue
        med = statistics.median(ratios)
        scale = 1.0 if 0.8 <= med <= 1.25 else 100.0 if 80 <= med <= 125 else None
        ev = f"paridad put-call: mediana K_implícito/K_publicado = {med:.3f} ({len(ratios)} pares, spot {S})"
        if scale and abs(med / scale - 1) > 0.03:
            ev += (f". ADVERTENCIA: desviación de {abs(med / scale - 1):.1%} tras la escala; el precio del subyacente "
                   "disponible difiere del de referencia de MexDer, así que la volatilidad implícita con ese precio no es confiable")
        out[und] = {"scale": scale, "median_ratio": med, "pairs": len(ratios), "evidence": ev}
    return out


# ============================================================ importación a la base de datos

def import_bulletin(db, content: bytes, filename: str) -> dict:
    """Importa un boletín (PDF o texto extraído) de futuros u opciones de MexDer.
    Crea/actualiza los contratos listados y guarda el historial de precios de liquidación."""
    import hashlib
    import os
    import tempfile

    from sqlalchemy import select

    from ..core.db import ContractQuote, FuturesContract, Instrument, OptionContract, PriceRecord

    sha = hashlib.sha256(content).hexdigest()
    if filename.lower().endswith(".pdf"):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
            fh.write(content)
            tmp = fh.name
        try:
            text = pdf_to_text(tmp)
        finally:
            os.unlink(tmp)
    else:
        text = content.decode("utf-8", errors="replace")
    kind = detect_kind(text)
    parsed = parse_futures(text) if kind == "futuros" else parse_options(text)
    bdate = parsed["date"]
    source = f"MexDer · Boletín de {kind} (precios de liquidación e interés abierto) del {bdate.isoformat()} · {filename}"
    catalog = {(i.ticker, i.series) for i in db.scalars(select(Instrument))}
    scales = {}
    if kind == "opciones":
        spots = {}
        for inst in db.scalars(select(Instrument)):
            pr = db.scalar(select(PriceRecord).where(PriceRecord.instrument_id == inst.id, PriceRecord.field == "close",
                                                     PriceRecord.price_type == "cierre_oficial",
                                                     PriceRecord.market_date == bdate))
            if pr is not None:
                spots[inst.ticker] = float(pr.value)
        scales = infer_strike_scales(parsed["rows"], spots)
    created = updated = quotes = 0
    not_in_catalog, aliases = set(), set()
    for r in parsed["rows"]:
        meta = r["meta"]
        if meta.get("alias_note"):
            aliases.add(f"{meta.get('bulletin_name')} → {meta['ticker']} {meta['series']}: {meta['alias_note']}")
        if meta.get("ticker") and (meta["ticker"], meta["series"]) not in catalog:
            not_in_catalog.add(f"{meta['ticker']} {meta['series']}")
        if kind == "futuros":
            spec = r["spec"]
            rec = db.scalar(select(FuturesContract).where(FuturesContract.symbol == r["symbol"]))
            if rec is None:
                rec = FuturesContract(symbol=r["symbol"])
                db.add(rec)
                created += 1
            else:
                updated += 1
            rec.underlying_ticker = meta.get("ticker") or spec.get("underlying")
            rec.expiry = r["expiry"]
            rec.multiplier = spec["multiplier"]
            rec.tick_size, rec.tick_value = spec.get("tick_size"), spec.get("tick_value")
            rec.currency, rec.settlement = spec["currency"], spec["settlement"]
            rec.notes = meta.get("alias_note")
        else:
            rec = db.scalar(select(OptionContract).where(OptionContract.symbol == r["symbol"]))
            if rec is None:
                rec = OptionContract(symbol=r["symbol"])
                db.add(rec)
                created += 1
            else:
                updated += 1
            rec.underlying_ticker = r["underlying"]
            rec.underlying_series = meta.get("series")
            sc = scales.get(r["underlying"], {"scale": 1.0, "evidence": "índice/divisa: strike en unidades del subyacente"})
            rec.strike_published, rec.strike_scale = r["strike"], sc["scale"]
            rec.option_type, rec.strike, rec.expiry = r["option_type"], round(r["strike"] * (sc["scale"] or 1.0), 6), r["expiry"]
            rec.multiplier, rec.style, rec.settlement, rec.currency = r["multiplier"], r["style"], r["settlement_type"], "MXN"
            notes = [n for n in (meta.get("alias_note"), "Opción sobre el futuro del IPC: ampara un futuro de $10 por punto"
                                 if r["underlying"] == "IPC" else None) if n]
            if r["underlying"] not in ("IPC", "USD"):
                notes.append(("ESCALA NO VERIFICADA: strike tal como se publica. " if sc["scale"] is None else
                              f"Strike = publicado × {sc['scale']:g}. ") + sc["evidence"])
            rec.notes = " · ".join(notes) or None
        if rec.settlement_date is None or bdate >= rec.settlement_date:
            rec.last_settlement, rec.previous_settlement = r["settlement"], r["previous_settlement"]
            rec.open_interest, rec.settlement_date = r["open_interest"], bdate
        rec.source = source
        rec.reviewed_on = bdate
        q = db.scalar(select(ContractQuote).where(ContractQuote.contract_kind == ("futuro" if kind == "futuros" else "opcion"),
                                                  ContractQuote.symbol == r["symbol"], ContractQuote.market_date == bdate,
                                                  ContractQuote.source == source))
        if q is None:
            db.add(ContractQuote(contract_kind="futuro" if kind == "futuros" else "opcion", symbol=r["symbol"],
                                 market_date=bdate, previous_settlement=r["previous_settlement"],
                                 settlement=r["settlement"], open_interest=r["open_interest"], source=source,
                                 file_sha256=sha))
            quotes += 1
    db.commit()
    return {"kind": kind, "bulletin_date": bdate.isoformat(), "series_read": len(parsed["rows"]),
            "strike_scales": {u: {"escala": v["scale"], "evidencia": v["evidence"]} for u, v in sorted(scales.items())},
            "contracts_created": created, "contracts_updated": updated, "quotes_added": quotes,
            "aliases_applied": sorted(aliases), "underlyings_not_in_catalog": sorted(not_in_catalog),
            "unrecognized_sections": parsed["unrecognized_sections"], "source": source}
