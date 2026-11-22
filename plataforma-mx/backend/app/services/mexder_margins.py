"""Aportaciones Iniciales Mínimas (AIM) unitarias de MexDer/Asigna (archivo Excel «AIMS_Unitarias_<Mes><Año>»).

Hojas esperadas: «Futuros» (CLASE, SERIE, Larga/Corta, AIM Unitaria), «Opciones» (CLASE, SERIE,
CALL(C)/PUT(P), EJERCICIO, Larga/Corta, AIM Unitaria) y «Swaps» (informativa, no se carga).

- La AIM es una GARANTÍA por contrato, no un costo. Se guarda por separado para la posición larga y la corta.
- Las AIM sólo se asignan a contratos que ya existen (importados de un boletín de MexDer). Si una serie del
  archivo no existe como contrato, se reporta y no se crea: no se inventan contratos.
- El periodo se toma del nombre del archivo (p. ej. «Octubre26» → octubre de 2026). Si no se reconoce,
  la importación se rechaza para no asignar una fecha falsa.
"""
from __future__ import annotations

import calendar
import io
import re
from collections import defaultdict
from datetime import date

MONTHS = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8,
          "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12}
SERIES_MONTH = {"EN": 1, "FB": 2, "MR": 3, "AB": 4, "MY": 5, "JN": 6, "JL": 7, "AG": 8, "SP": 9, "OC": 10, "NV": 11, "DC": 12}
BOND_CLASSES = {"JN27": "M270603", "MY29": "M290531", "MY31": "M310529", "NV36": "M361120", "NV42": "M421113",
                "NV47": "M471107"}


def period_from_filename(filename: str) -> tuple[date, str]:
    m = re.search(r"(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)[_\s-]?(\d{2,4})",
                  filename.upper())
    if not m:
        raise ValueError("no se reconoce el periodo en el nombre del archivo (se espera, p. ej., «AIMS_Unitarias_Octubre26»)")
    y = int(m.group(2))
    y = y + 2000 if y < 100 else y
    mo = MONTHS[m.group(1)]
    return date(y, mo, calendar.monthrange(y, mo)[1]), f"{m.group(1).capitalize()} {y}"


def _series_ym(code: str) -> tuple[int, int]:
    return 2000 + int(code[2:4]), SERIES_MONTH[code[:2]]


def class_maps(db) -> tuple[dict, dict]:
    """Claves de pizarra → ticker, a partir del catálogo (campo catalog_source) y alias conocidos."""
    from sqlalchemy import select

    from ..core.db import Instrument

    fut, opt = {}, {}
    for i in db.scalars(select(Instrument)):
        src = i.catalog_source or ""
        m = re.search(r"clave de pizarra ([A-Z0-9/&]+)", src)
        if m:
            for k in m.group(1).split("/"):
                fut[k] = i.ticker
        m = re.search(r"clave de opciones ([A-Z]{2})", src)
        if m:
            opt[m.group(1)] = i.ticker
    fut.update({"IPC": "IPC", "MIP": "IPC"})
    opt.update({"IP": "IPC", "DA": "USD"})
    return fut, opt


def import_aims(db, content: bytes, filename: str) -> dict:
    import hashlib

    import xlrd
    from sqlalchemy import select

    from ..core.db import FuturesContract, OptionContract

    as_of, period = period_from_filename(filename)
    sha = hashlib.sha256(content).hexdigest()
    book = xlrd.open_workbook(file_contents=content)
    names = {s.name.strip().lower(): s for s in book.sheets()}
    if "futuros" not in names and "opciones" not in names:
        raise ValueError("el archivo no tiene hojas «Futuros» ni «Opciones»")
    source = f"AIM unitarias MexDer/Asigna · periodo {period} · {filename} (sha256 {sha[:12]})"
    fut_map, opt_map = class_maps(db)
    report = {"period": period, "as_of": as_of.isoformat(), "source": source}

    # ----------------------------------------------------------- futuros
    if "futuros" in names:
        sh = names["futuros"]
        aims = defaultdict(dict)
        for r in range(1, sh.nrows):
            cl, ser, side, val = [sh.cell_value(r, c) for c in range(4)]
            aims[(str(cl).strip(), str(ser).strip())][str(side).strip().lower()] = float(val)
        contracts = {c.symbol: c for c in db.scalars(select(FuturesContract))}
        matched, unmatched = 0, []
        for (cl, ser), v in aims.items():
            if re.fullmatch(r"(DA|MD)\d{2}", cl):
                sym = f"{cl[:2]} {cl[2:]}{ser}"
            elif cl in BOND_CLASSES:
                sym = f"{BOND_CLASSES[cl]} {ser}"
            elif cl in ("EURO", "TIEF", "CE91"):
                sym = f"{cl} {ser}"
            elif cl in fut_map:
                sym = f"{fut_map[cl]} {ser}" if cl != "MIP" else f"MIP {ser}"
            else:
                unmatched.append(f"{cl} {ser} (clave no reconocida)")
                continue
            c = contracts.get(sym)
            if c is None:
                unmatched.append(f"{cl} {ser} → {sym} (no existe en los contratos importados del boletín)")
                continue
            c.margin_long, c.margin_short = v.get("larga"), v.get("corta")
            c.initial_margin = max(x for x in (c.margin_long, c.margin_short) if x is not None)
            c.margin_as_of, c.margin_source = as_of, source
            matched += 1
        by_class = defaultdict(int)
        for u in unmatched:
            by_class[re.sub(r"\d{2}$", "", u.split()[0])] += 1
        report["futures"] = {"series_in_file": len(aims), "assigned": matched, "not_assigned_count": len(unmatched),
                             "not_assigned_by_class": dict(by_class), "not_assigned_sample": unmatched[:25]}

    # ----------------------------------------------------------- opciones
    if "opciones" in names:
        sh = names["opciones"]
        aims = defaultdict(dict)
        for r in range(1, sh.nrows):
            cl, ser, cp, k, side, val = [sh.cell_value(r, c) for c in range(6)]
            aims[(str(cl).strip(), str(ser).strip(), str(cp).strip().upper(), float(k))][str(side).strip().lower()] = float(val)
        report["strike_scales_from_aims"] = resolve_unverified_scales(db, aims, opt_map, filename)
        index = defaultdict(list)
        for c in db.scalars(select(OptionContract)):
            index[(c.underlying_ticker, c.expiry.year, c.expiry.month, c.option_type)].append(c)
        matched, unmatched, strike_checks = 0, [], defaultdict(lambda: [0, 0])
        for (cl, ser, cp, k), v in aims.items():
            tk = opt_map.get(cl)
            if tk is None:
                unmatched.append(f"{cl} {ser} {cp} {k:g} (clave no reconocida)")
                continue
            y, mo = _series_ym(ser)
            cands = index.get((tk, y, mo, "call" if cp == "C" else "put"), [])
            c = next((x for x in cands if abs(float(x.strike) - k) <= 1e-6 * max(1.0, abs(k))), None)
            strike_checks[tk][1] += 1
            if c is None:
                unmatched.append(f"{cl} {ser} {cp} {k:g} → {tk} (serie no existe en el boletín importado)")
                continue
            strike_checks[tk][0] += 1
            c.margin_long, c.margin_short = v.get("larga"), v.get("corta")
            c.margin_as_of, c.margin_source = as_of, source
            matched += 1
        report["options"] = {"series_in_file": len(aims), "assigned": matched, "not_assigned_count": len(unmatched),
                             "not_assigned_sample": unmatched[:25],
                             "match_rate_by_underlying": {t: f"{a}/{n}" for t, (a, n) in sorted(strike_checks.items())}}
    if "swaps" in names:
        report["swaps"] = {"rows": names["swaps"].nrows - 1,
                           "status": "no cargado: la plataforma aún no modela swaps de TIIE listados"}
    db.commit()
    return report


def resolve_unverified_scales(db, aims: dict, opt_map: dict, filename: str) -> dict:
    """Para series de opciones cuya escala de strike no pudo verificarse por paridad (p. ej. sin precios del
    subyacente), usa como segunda fuente independiente el archivo de AIM, que publica los strikes en su escala
    real: se elige ×1 o ×100 según cuál produzca coincidencia con al menos el 50 % de los strikes del archivo."""
    from sqlalchemy import select

    from ..core.db import OptionContract

    aim_strikes = defaultdict(set)
    for (cl, ser, cp, k) in aims:
        tk = opt_map.get(cl)
        if tk:
            y, mo = _series_ym(ser)
            aim_strikes[(tk, y, mo)].add(round(k, 6))
    pending = defaultdict(list)
    for c in db.scalars(select(OptionContract).where(OptionContract.strike_scale.is_(None))):
        pending[c.underlying_ticker].append(c)
    out = {}
    for tk, contracts in pending.items():
        score = {}
        for scale in (1.0, 100.0):
            hits = total = 0
            for c in contracts:
                ref = aim_strikes.get((tk, c.expiry.year, c.expiry.month))
                if not ref:
                    continue
                total += 1
                hits += round(float(c.strike_published) * scale, 6) in ref
            score[scale] = (hits, total)
        # Decisión: ≥ 50 % de coincidencia, o ≥ 25 % cuando la escala alternativa no coincide en ninguna serie
        # (los strikes listados se recorren entre meses, así que la coincidencia parcial es normal).
        best = None
        for scale, other in ((1.0, 100.0), (100.0, 1.0)):
            hits, total = score[scale]
            if total and (hits / total >= 0.5 or (hits / total >= 0.25 and score[other][0] == 0)):
                if best is None or hits > best[1]:
                    best = (scale, hits, total)
        if best is None:
            out[tk] = "sin coincidencias suficientes: la escala sigue sin verificar"
            continue
        scale, hits, total = best
        ev = f"Strike = publicado × {scale:g}. Coincidencia con strikes del archivo de AIM {filename}: {hits}/{total} series"
        for c in contracts:
            c.strike_scale, c.strike = scale, round(float(c.strike_published) * scale, 6)
            c.notes = " · ".join(n for n in (c.notes or "").split(" · ") if not n.startswith("ESCALA NO VERIFICADA")) \
                + (" · " if c.notes else "") + ev
        out[tk] = ev
    db.flush()
    return out
