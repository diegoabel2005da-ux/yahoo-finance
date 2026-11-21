"""Reportes Excel (sección 17) y PDF (sección 18).

Ambos se generan del MISMO objeto de estudio producido por el backend, de modo que los
valores de la interfaz, el Excel y el PDF coinciden. En Excel se incluyen fórmulas
auditables donde es posible (DCF, caplets, escenarios); los valores calculados por el
motor se conservan en columnas adyacentes para verificación cruzada.
"""
from __future__ import annotations

import io
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4, landscape  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import (Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,  # noqa: E402
                                TableStyle)

from ..core.audit import to_jsonable  # noqa: E402
from ..engines.scenarios import SCENARIO_KEYS, SCENARIO_LABELS  # noqa: E402

NAVY, TURQ, GREY = "0B1F3A", "14B8A6", "E5E7EB"
SHEETS = ["Portada", "Fuentes y fechas", "Datos históricos", "Estados financieros", "Ratios", "DCF",
          "Análisis técnico", "Riesgo", "Futuros", "Opciones", "Curvas de tasas", "Caps y floors",
          "Estrategias", "Perfiles de riesgo", "Escenarios", "Comparativas", "Fórmulas y supuestos"]

FORMULAS = [
    ("Rendimiento simple", "R_t = P_t / P_{t-1} − 1"),
    ("Rendimiento logarítmico", "r_t = ln(P_t / P_{t-1})"),
    ("Volatilidad anualizada", "σ = desv. est. muestral(r) × √(periodos por año)"),
    ("Beta", "β = Cov(R_a, R_m) / Var(R_m)"),
    ("VaR histórico", "VaR_c = −cuantil_{1−c}(R)"),
    ("Expected Shortfall", "ES_c = −E[R | R ≤ −VaR_c]"),
    ("ROC", "ROC(n) = (P_t / P_{t−n} − 1) × 100"),
    ("Williams %R", "%R = −100 (Máx_n − C)/(Máx_n − Mín_n)"),
    ("Estocástico", "%K = 100 (C − Mín_n)/(Máx_n − Mín_n); %D = SMA(%K)"),
    ("RSI (Wilder)", "RSI = 100 − 100/(1 + RS); promedios suavizados de Wilder"),
    ("FCFF", "EBIT(1−t) + D&A − CAPEX − ΔCTN"),
    ("WACC", "E/V·Ke + D/V·Kd(1−t)"),
    ("Valor terminal (Gordon)", "FCFF_N (1+g)/(WACC − g)"),
    ("BSM call", "S e^{−qT} N(d1) − K e^{−rT} N(d2)"),
    ("CRR", "u = e^{σ√Δt}, d = 1/u, p = (e^{(r−q)Δt} − d)/(u − d)"),
    ("Futuro largo", "P&L = n·M·(F_final − F_inicial)"),
    ("Caplet", "N·α·max(R − K, 0)"),
    ("Floorlet", "N·α·max(K − R, 0)"),
    ("Black-76 caplet", "N α P(0,T_p)[F N(d1) − K N(d2)]"),
    ("Bachelier caplet", "N α P(0,T_p)[(F − K)N(d) + σ_n√τ φ(d)]"),
    ("TIIE de Fondeo compuesta", "[Π(1 + r_i d_i/360) − 1]·360/D"),
]


def _hdr(ws, row, cols):
    for j, c in enumerate(cols, 1):
        cell = ws.cell(row=row, column=j, value=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.alignment = Alignment(wrap_text=True, vertical="center")


def _autowidth(ws):
    for col in ws.columns:
        width = max((len(str(c.value)) if c.value is not None else 0) for c in col)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(10, width + 2), 60)


def _na(ws, reason):
    ws["A3"] = "Sección sin datos"
    ws["A3"].font = Font(bold=True, color="B91C1C")
    ws["A4"] = reason


def _title(ws, text):
    ws["A1"] = text
    ws["A1"].font = Font(bold=True, size=14, color=NAVY)


def build_xlsx(study: dict) -> bytes:
    st = to_jsonable(study)
    wb = Workbook()
    wb.remove(wb.active)
    ws = {name: wb.create_sheet(name[:31]) for name in SHEETS}
    for name, sh in ws.items():
        _title(sh, name)
        sh.page_setup.orientation = "landscape"
        sh.page_setup.fitToWidth = 1
        sh.sheet_properties.pageSetUpPr.fitToPage = True
        sh.print_title_rows = "1:2"

    # Portada
    p = ws["Portada"]
    rows = [("Título", st.get("title")), ("Generado", st.get("generated_at")),
            ("Activo / exposición", st.get("subject")), ("Versión del motor", st.get("engine_version")),
            ("Advertencia", "Herramienta de análisis e investigación. No ejecuta órdenes ni constituye "
                            "recomendación. Los resultados teóricos o simulados se identifican como tales.")]
    for i, (k, v) in enumerate(rows, 3):
        p.cell(i, 1, k).font = Font(bold=True)
        p.cell(i, 2, str(v) if v is not None else "")

    # Fuentes
    s = ws["Fuentes y fechas"]
    src = st.get("sources") or []
    if src:
        cols = ["dato", "fuente", "fecha", "origen", "estado"]
        _hdr(s, 3, cols)
        for i, r in enumerate(src, 4):
            for j, c in enumerate(cols, 1):
                s.cell(i, j, str(r.get(c, "")))
    else:
        _na(s, "No se registraron fuentes en este estudio.")

    # Históricos
    h = ws["Datos históricos"]
    hist = (st.get("historical") or {}).get("rows")
    if hist:
        cols = list(hist[0].keys())
        _hdr(h, 3, cols)
        for i, r in enumerate(hist, 4):
            for j, c in enumerate(cols, 1):
                h.cell(i, j, r.get(c))
        # rendimiento simple como fórmula auditable
        if "close" in cols:
            cc = get_column_letter(cols.index("close") + 1)
            rc = len(cols) + 1
            h.cell(3, rc, "rend_simple (fórmula)").font = Font(bold=True)
            for i in range(5, 4 + len(hist)):
                h.cell(i, rc, f"={cc}{i}/{cc}{i-1}-1").number_format = "0.00%"
    else:
        _na(h, (st.get("historical") or {}).get("reason", "Sin series históricas cargadas."))

    # Estados financieros
    f = ws["Estados financieros"]
    fin = st.get("financials") or []
    if fin:
        r0 = 3
        for stmt in fin:
            f.cell(r0, 1, f"{stmt['statement']} {stmt['period_type']} {stmt['period_end']} ({stmt['basis']}, "
                          f"{stmt['currency']} {stmt['units']}) — {stmt['source']}").font = Font(bold=True)
            r0 += 1
            for k, v in stmt["items"].items():
                f.cell(r0, 1, k)
                f.cell(r0, 2, v).number_format = "#,##0.00"
                r0 += 1
            r0 += 1
    else:
        _na(f, "No se han importado estados financieros verificables para la emisora.")

    # Ratios
    r = ws["Ratios"]
    ratios = (st.get("ratios") or {}).get("ratios")
    if ratios:
        _hdr(r, 3, ["razón", "valor", "fórmula", "insumos faltantes", "explicación"])
        for i, (k, v) in enumerate(ratios.items(), 4):
            r.cell(i, 1, k)
            r.cell(i, 2, v.get("value")).number_format = "0.0000"
            r.cell(i, 3, v.get("formula"))
            r.cell(i, 4, ", ".join(v.get("missing") or []))
            r.cell(i, 5, v.get("explanation"))
    else:
        _na(r, "Sin razones financieras (faltan estados financieros).")

    # DCF con fórmulas
    d = ws["DCF"]
    dcf = st.get("dcf")
    if dcf and dcf.get("projection"):
        inp = dcf.get("inputs", {})
        d["A3"], d["B3"] = "WACC", inp.get("wacc")
        d["A4"], d["B4"] = "Tasa de impuestos", inp.get("tax_rate")
        d["A5"], d["B5"] = "g terminal", inp.get("terminal_growth")
        cols = ["year", "revenue", "ebit", "nopat", "da", "capex", "delta_nwc", "fcff", "discount_factor", "pv_fcff",
                "fcff (fórmula)", "pv (fórmula)"]
        _hdr(d, 7, cols)
        for i, row in enumerate(dcf["projection"], 8):
            for j, c in enumerate(cols[:10], 1):
                d.cell(i, j, row[c]).number_format = "#,##0.00" if j > 1 else "0"
            d.cell(i, 11, f"=D{i}+E{i}-F{i}-G{i}").number_format = "#,##0.00"
            d.cell(i, 12, f"=K{i}*(1+$B$3)^-A{i}" if not inp.get("mid_year") else f"=K{i}*(1+$B$3)^-(A{i}-0.5)")
            d.cell(i, 12).number_format = "#,##0.00"
        e = 8 + len(dcf["projection"])
        for k, lab in enumerate(["pv_explicit", "terminal_value", "pv_terminal", "enterprise_value", "equity_value",
                                 "value_per_share"]):
            d.cell(e + 1 + k, 1, lab).font = Font(bold=True)
            d.cell(e + 1 + k, 2, dcf.get(lab)).number_format = "#,##0.00"
        d.cell(e + 8, 1, dcf.get("disclaimer"))
    else:
        _na(d, "DCF no ejecutado en este estudio.")

    # Técnico
    t = ws["Análisis técnico"]
    tech = (st.get("technical") or {}).get("rows")
    if tech:
        cols = list(tech[0].keys())
        _hdr(t, 3, cols)
        for i, rr in enumerate(tech, 4):
            for j, c in enumerate(cols, 1):
                t.cell(i, j, rr.get(c))
    else:
        _na(t, "Sin indicadores técnicos.")

    _kv_sheet(ws["Riesgo"], st.get("risk"), "Sin métricas de riesgo.")
    _kv_sheet(ws["Futuros"], st.get("futures"), "Sin contratos de futuros analizados.")
    _kv_sheet(ws["Opciones"], st.get("options"), "Sin opciones analizadas.")

    c = ws["Curvas de tasas"]
    cur = st.get("curve")
    if cur and cur.get("nodes"):
        c["A3"] = f"{cur.get('name')} — {cur.get('date')} — fuente: {cur.get('source')} ({cur.get('origin')})"
        _hdr(c, 4, ["t (años)", "días", "cero continua", "factor de descuento", "DF (fórmula)"])
        for i, n in enumerate(cur["nodes"], 5):
            c.cell(i, 1, n["t"])
            c.cell(i, 2, n["days"])
            c.cell(i, 3, n["zero_cont"]).number_format = "0.000000%"
            c.cell(i, 4, n["df"]).number_format = "0.00000000"
            c.cell(i, 5, f"=EXP(-C{i}*A{i})").number_format = "0.00000000"
    else:
        _na(c, "Sin curva de tasas importada.")

    cf = ws["Caps y floors"]
    capf = st.get("capfloor")
    if capf and capf.get("components"):
        cf["A3"] = (f"{capf['kind'].upper()} — modelo {capf['model']} — estilo de tasa {capf['rate_style']} — "
                    f"{capf.get('instrument_status')}")
        cols = ["period", "accrual_start", "accrual_end", "payment_date", "notional", "accrual", "forward", "tau",
                "vol", "discount_factor", "value"]
        _hdr(cf, 4, cols + ["unidad (=valor/(N·α·DF))", "valor (fórmula)"])
        for i, comp in enumerate(capf["components"], 5):
            for j, k in enumerate(cols, 1):
                cf.cell(i, j, comp.get(k))
            cf.cell(i, 12, comp["value"] / (comp["notional"] * comp["accrual"] * comp["discount_factor"]))
            cf.cell(i, 13, f"=E{i}*F{i}*J{i}*L{i}").number_format = "#,##0.00"
        e = 5 + len(capf["components"])
        cf.cell(e, 10, "Total").font = Font(bold=True)
        cf.cell(e, 11, f"=SUM(K5:K{e-1})").number_format = "#,##0.00"
        cf.cell(e, 13, f"=SUM(M5:M{e-1})").number_format = "#,##0.00"
        if st.get("capfloor_sensitivities"):
            _kv_block(cf, e + 2, st["capfloor_sensitivities"])
    else:
        _na(cf, "Sin cap/floor valorado.")

    es = ws["Estrategias"]
    strategies = st.get("strategies") or []
    if strategies:
        _hdr(es, 3, ["estrategia", "función económica", "legs", "costo inicial", "advertencias"])
        for i, s_ in enumerate(strategies, 4):
            es.cell(i, 1, s_.get("name"))
            es.cell(i, 2, s_.get("economic_function"))
            es.cell(i, 3, "; ".join(f"{l['kind']} q={l['qty']} K={l.get('strike')} prima={l.get('premium')} "
                                    f"({l.get('premium_origin')})" for l in s_.get("legs", [])))
            es.cell(i, 4, s_.get("initial_cost"))
            es.cell(i, 5, " | ".join(s_.get("warnings", [])))
    else:
        _na(es, "Sin estrategias.")

    pr = ws["Perfiles de riesgo"]
    profs = st.get("profiles") or {}
    if profs:
        r0 = 3
        for k, prof in profs.items():
            pr.cell(r0, 1, prof.get("name", k)).font = Font(bold=True)
            pr.cell(r0, 2, prof.get("description"))
            r0 += 1
            for kk, vv in prof.items():
                if kk in ("name", "description", "key"):
                    continue
                pr.cell(r0, 1, kk)
                pr.cell(r0, 2, str(vv))
                r0 += 1
            r0 += 1
        pr.cell(r0, 1, "Los perfiles representan preferencias analíticas del simulador, no evaluaciones "
                       "regulatorias de idoneidad.")
    else:
        _na(pr, "Sin perfiles.")

    sc = ws["Escenarios"]
    scen = st.get("scenarios")
    if scen and scen.get("evaluations"):
        equity = "combined_pnl" in scen["evaluations"][0]["scenarios"]["base"]
        cols = (["perfil", "estrategia", "escenario", "precio final", "P&L exposición", "P&L derivado",
                 "P&L combinado (motor)", "P&L combinado (fórmula)", "vs base", "protección"] if equity else
                ["perfil", "estrategia", "escenario", "paralelo pb", "VP exposición", "VP flujos derivado", "prima",
                 "VP neto (motor)", "VP neto (fórmula)", "vs sin cobertura", "MTM derivado tras choque"])
        _hdr(sc, 3, cols)
        i = 4
        for row in scen["evaluations"]:
            for sk in SCENARIO_KEYS:
                x = row["scenarios"][sk]
                sc.cell(i, 1, row["profile"])
                sc.cell(i, 2, row["strategy"])
                sc.cell(i, 3, SCENARIO_LABELS[sk])
                if equity:
                    vals = [x["S_final"], x["exposure_pnl"], x["derivative_pnl"], x["combined_pnl"]]
                    for j, v in enumerate(vals, 4):
                        sc.cell(i, j, v).number_format = "#,##0.00"
                    sc.cell(i, 8, f"=E{i}+F{i}").number_format = "#,##0.00"
                    sc.cell(i, 9, x["vs_base"]).number_format = "#,##0.00"
                    sc.cell(i, 10, x.get("protection_ratio")).number_format = "0.0%"
                else:
                    vals = [x["parallel_bp"], x["pv_exposure"], x["pv_derivative_flows"], x["premium"], x["net_pv"]]
                    for j, v in enumerate(vals, 4):
                        sc.cell(i, j, v).number_format = "#,##0.00"
                    sc.cell(i, 9, f"=E{i}+F{i}-G{i}").number_format = "#,##0.00"
                    sc.cell(i, 10, x.get("vs_unhedged")).number_format = "#,##0.00"
                    sc.cell(i, 11, x.get("derivative_mtm_after_shock")).number_format = "#,##0.00"
                i += 1
        sc.auto_filter.ref = f"A3:{get_column_letter(len(cols))}{i-1}"
        sc.freeze_panes = "D4"
        sc.cell(i + 1, 1, "Escenarios = hipótesis de simulación; sin probabilidades de ocurrencia.")
    else:
        _na(sc, "Sin escenarios simulados.")

    cm_ = ws["Comparativas"]
    if scen and scen.get("evaluations"):
        _hdr(cm_, 3, ["perfil", "estrategia", "función económica", "costo inicial", "costo % exposición",
                      "estrés severo", "base", "favorable extremo", "restricciones"])
        for i, row in enumerate(scen["evaluations"], 4):
            g = lambda k: row["scenarios"][k].get("combined_pnl", row["scenarios"][k].get("net_pv"))
            vals = [row["profile"], row["strategy"], row["economic_function_label"], row["initial_cost"],
                    row["initial_cost_pct"], g("estres_adverso_severo"), g("base"), g("favorable_extremo"),
                    ", ".join(f"{k}={v}" for k, v in (row.get("constraints") or {}).items())]
            for j, v in enumerate(vals, 1):
                cell = cm_.cell(i, j, v)
                if j in (4, 6, 7, 8):
                    cell.number_format = "#,##0.00"
                if j == 5:
                    cell.number_format = "0.00%"
    else:
        _na(cm_, "Sin comparativas.")

    fo = ws["Fórmulas y supuestos"]
    _hdr(fo, 3, ["concepto", "fórmula / supuesto"])
    i = 4
    for k, v in FORMULAS:
        fo.cell(i, 1, k)
        fo.cell(i, 2, v)
        i += 1
    for a in (st.get("assumptions") or []) + (st.get("limitations") or []):
        fo.cell(i, 1, "Supuesto/limitación")
        fo.cell(i, 2, a)
        i += 1
    for sh in ws.values():
        _autowidth(sh)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _kv_block(ws, r0, data):
    for k, v in (data or {}).items():
        if isinstance(v, (dict, list)):
            ws.cell(r0, 1, k).font = Font(bold=True)
            ws.cell(r0, 2, str(v)[:30000])
        else:
            ws.cell(r0, 1, k)
            ws.cell(r0, 2, v)
        r0 += 1
    return r0


def _kv_sheet(ws, data, reason):
    if not data:
        _na(ws, reason)
    else:
        _kv_block(ws, 3, data)


# ============================================================================ PDF

def _chart_scenarios(scen: dict, profile: str) -> bytes | None:
    rows = [r for r in scen["evaluations"] if r["profile"] == profile]
    if not rows:
        return None
    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=150)
    width = 0.8 / len(rows)
    palette = ["#94a3b8", "#0b1f3a", "#14b8a6", "#2563eb", "#a855f7", "#f59e0b", "#e11d48"]
    for i, r in enumerate(rows):
        vals = [r["scenarios"][k].get("combined_pnl", r["scenarios"][k].get("net_pv")) for k in SCENARIO_KEYS]
        ax.bar([x + i * width for x in range(5)], vals, width, label=r["strategy"], color=palette[i % len(palette)])
    ax.set_xticks([x + 0.4 - width / 2 for x in range(5)])
    ax.set_xticklabels([SCENARIO_LABELS[k].replace(" ", "\n", 1) for k in SCENARIO_KEYS], fontsize=7)
    ax.axhline(0, color="#334155", lw=0.8)
    ax.set_title(f"Resultado combinado por escenario — perfil {profile}", fontsize=9)
    ax.tick_params(axis="y", labelsize=7)
    ax.legend(fontsize=6, ncol=3, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def _chart_series(hist: list[dict]) -> bytes | None:
    if not hist or "close" not in hist[0]:
        return None
    fig, ax = plt.subplots(figsize=(9, 3), dpi=150)
    ax.plot([h["date"] for h in hist], [h["close"] for h in hist], color="#0b1f3a", lw=1)
    ax.set_title("Precio de cierre (dato observado)", fontsize=9)
    ax.tick_params(labelsize=7)
    step = max(1, len(hist) // 8)
    ax.set_xticks(range(0, len(hist), step))
    ax.set_xticklabels([hist[i]["date"][:10] for i in range(0, len(hist), step)], rotation=0)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def build_pdf(study: dict) -> bytes:
    st = to_jsonable(study)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm, title=st.get("title", "Informe"))
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("H1", parent=ss["Heading1"], textColor=colors.HexColor("#0B1F3A"))
    H2 = ParagraphStyle("H2", parent=ss["Heading2"], textColor=colors.HexColor("#0B1F3A"))
    B = ParagraphStyle("B", parent=ss["BodyText"], fontSize=9, leading=12)
    TAG = ParagraphStyle("T", parent=B, textColor=colors.HexColor("#0F766E"))
    el = []

    def table(rows, widths=None):
        t = Table(rows, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B1F3A")),
                               ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 7),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")])]))
        return t

    def na(reason):
        el.append(Paragraph(f"<i>Sin datos: {reason}</i>", B))

    fmt = lambda v: "—" if v is None else (f"{v:,.2f}" if isinstance(v, (int, float)) else str(v))

    # Portada
    el += [Spacer(1, 3 * cm), Paragraph(st.get("title", "Informe de análisis"), H1),
           Paragraph(f"Sujeto de análisis: {st.get('subject', '—')}", B),
           Paragraph(f"Generado: {st.get('generated_at', datetime.now().isoformat())} · Motor {st.get('engine_version', '')}", B),
           Spacer(1, 1 * cm),
           Paragraph("Herramienta de análisis e investigación. No ejecuta órdenes, no constituye recomendación y "
                     "no garantiza resultados. Los valores teóricos y simulados se identifican como tales y no son "
                     "cotizaciones oficiales.", TAG), PageBreak()]

    el.append(Paragraph("Resumen ejecutivo", H2))
    el.append(Paragraph((st.get("executive_summary") or "—").replace("\n", "<br/>"), B))
    el.append(Paragraph("Identificación del activo o exposición", H2))
    el.append(Paragraph(str(st.get("exposure") or st.get("subject") or "—"), B))
    el.append(Paragraph("Metodología", H2))
    for n in (st.get("scenarios") or {}).get("method_notes", []) + (st.get("methodology") or []):
        el.append(Paragraph(f"• {n}", B))

    el.append(Paragraph("Fuentes y fechas", H2))
    src = st.get("sources") or []
    if src:
        el.append(table([["Dato", "Fuente", "Fecha", "Origen", "Estado"]] +
                        [[str(s.get(k, ""))[:60] for k in ("dato", "fuente", "fecha", "origen", "estado")] for s in src]))
    else:
        na("no se registraron fuentes")

    el.append(Paragraph("Datos históricos", H2))
    hist = (st.get("historical") or {}).get("rows")
    img = _chart_series(hist) if hist else None
    if img:
        el.append(Image(io.BytesIO(img), width=24 * cm, height=8 * cm))
        meta = (st.get("historical") or {}).get("meta", {})
        el.append(Paragraph(f"Observaciones: {meta.get('observations')} · Último dato disponible: "
                            f"{meta.get('last_date')} · Fuentes: {', '.join(meta.get('sources', []))}", B))
    else:
        na((st.get("historical") or {}).get("reason", "sin series históricas"))

    el.append(Paragraph("Análisis fundamental y valuación", H2))
    ratios = (st.get("ratios") or {}).get("ratios")
    if ratios:
        el.append(table([["Razón", "Valor", "Fórmula", "Faltantes"]] +
                        [[k, fmt(v.get("value")), v.get("formula"), ", ".join(v.get("missing") or [])]
                         for k, v in ratios.items()]))
    else:
        na("sin estados financieros importados")
    dcf = st.get("dcf")
    if dcf and dcf.get("projection"):
        el.append(Spacer(1, 0.3 * cm))
        el.append(table([["Año", "Ingresos", "EBIT", "FCFF", "VP FCFF"]] +
                        [[r["year"], fmt(r["revenue"]), fmt(r["ebit"]), fmt(r["fcff"]), fmt(r["pv_fcff"])]
                         for r in dcf["projection"]]))
        el.append(Paragraph(f"Valor empresa: {fmt(dcf['enterprise_value'])} · Capital: {fmt(dcf['equity_value'])} · "
                            f"Valor teórico por acción: {fmt(dcf['value_per_share'])}. {dcf.get('disclaimer', '')}", B))

    for sec, key in (("Análisis técnico y patrones", "technical_summary"), ("Riesgos", "risk"),
                     ("Futuros", "futures"), ("Opciones", "options")):
        el.append(Paragraph(sec, H2))
        data = st.get(key)
        if data:
            el.append(table([["Concepto", "Valor"]] + [[k, str(fmt(v))[:110]] for k, v in data.items()
                                                       if not isinstance(v, (list, dict))]))
        else:
            na("no incluido en este estudio")

    el.append(Paragraph("Caps y floors", H2))
    capf = st.get("capfloor")
    if capf and capf.get("components"):
        el.append(Paragraph(f"{capf['kind'].upper()} · modelo {capf['model']} · {capf['instrument_status']} · "
                            f"volatilidad: {capf.get('vol_origin')}", TAG))
        el.append(table([["Periodo", "Inicio", "Fin", "Forward", "τ", "DF", "Valor"]] +
                        [[c["period"], c["accrual_start"], c["accrual_end"], f"{c['forward']:.4%}", f"{c['tau']:.4f}",
                          f"{c['discount_factor']:.6f}", fmt(c["value"])] for c in capf["components"]]))
        el.append(Paragraph(f"Valor teórico total: {fmt(capf['value'])}", B))
    else:
        na("no corresponde o no se valoró")

    el.append(PageBreak())
    el.append(Paragraph("Estrategias de cobertura y comparativas", H2))
    scen = st.get("scenarios")
    if scen and scen.get("evaluations"):
        profiles = sorted({r["profile"] for r in scen["evaluations"]})
        for pk in profiles:
            img = _chart_scenarios(scen, pk)
            if img:
                el.append(Image(io.BytesIO(img), width=24 * cm, height=9.6 * cm))
            rows = [r for r in scen["evaluations"] if r["profile"] == pk]
            g = lambda r, k: r["scenarios"][k].get("combined_pnl", r["scenarios"][k].get("net_pv"))
            el.append(table([["Estrategia", "Función", "Costo"] + [SCENARIO_LABELS[k] for k in SCENARIO_KEYS]] +
                            [[r["strategy"], r["economic_function_label"][:40], fmt(r["initial_cost"])] +
                             [fmt(g(r, k)) for k in SCENARIO_KEYS] for r in rows]))
            el.append(Spacer(1, 0.4 * cm))
        el.append(Paragraph("Cinco escenarios por combinación perfil/estrategia. Choques visibles y editables; "
                            "sin probabilidades asignadas.", B))
    else:
        na("no se ejecutó la simulación de escenarios")

    el.append(Paragraph("Conclusiones", H2))
    el.append(Paragraph((st.get("conclusions") or "Ver resumen ejecutivo.").replace("\n", "<br/>"), B))
    el.append(Paragraph("Limitaciones", H2))
    for l in st.get("limitations") or ["—"]:
        el.append(Paragraph(f"• {l}", B))
    el.append(PageBreak())
    el.append(Paragraph("Anexo de fórmulas", H2))
    el.append(table([["Concepto", "Fórmula"]] + [list(f) for f in FORMULAS]))
    doc.build(el)
    return buf.getvalue()
