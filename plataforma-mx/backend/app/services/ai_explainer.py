"""IA explicativa (sección 16).

La IA recibe SOLAMENTE resultados estructurados del motor matemático y redacta
interpretaciones. Salvaguardas:
1. El prompt de sistema prohíbe generar cifras nuevas, primas, tasas o probabilidades.
2. Verificación posterior: todo número del texto debe poder rastrearse a una cifra del
   contexto (con tolerancia de redondeo). Si aparecen números no rastreables, la respuesta
   se marca y se devuelve la lista para revisión.
3. Sin credenciales configuradas, se usa un explicador determinista por reglas que sólo
   describe las cifras del contexto (nunca se simula una respuesta de IA).
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from ..core.audit import to_jsonable

MODEL = os.environ.get("AI_MODEL", "claude-opus-5-5")

SYSTEM_PROMPT = """Eres el asistente explicativo de una plataforma profesional de análisis financiero del \
mercado mexicano. Respondes en español, con precisión técnica y en tono profesional.

Reglas obligatorias:
- Sólo puedes usar las cifras incluidas en el CONTEXTO (JSON producido por el motor de cálculo verificado). \
No calcules cifras nuevas, no estimes primas, tasas, volatilidades, cotizaciones ni probabilidades.
- Si para responder hace falta una cifra que no está en el contexto, dilo explícitamente e indica qué cálculo \
del motor habría que ejecutar.
- Distingue siempre: datos observados (con su fuente), supuestos del usuario y resultados de modelo/teóricos. \
Nunca presentes un supuesto o un precio teórico como cotización observada.
- Los escenarios son hipótesis de simulación, no pronósticos; no les asignes probabilidades.
- No recomiendes operar ni prometas resultados; explica ventajas, costos, riesgos residuales y limitaciones.
- Una estrategia de volatilidad no es una cobertura; un cap/floor valorado aquí es OTC teórico salvo que el \
contexto indique lo contrario.
- Cuando cites una cifra, cópiala del contexto (puedes redondearla) y menciona a qué se refiere."""

_NUM = re.compile(r"(?<![\w.,])[-−]?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\d,])|(?<![\w.,])[-−]?\d+(?:\.\d+)?")


def _numbers_in(obj: Any, out: list[float]):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers_in(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _numbers_in(v, out)
    elif isinstance(obj, str):
        for m in _NUM.findall(obj):
            try:
                out.append(float(m.replace(",", "").replace(" ", "").replace("−", "-")))
            except ValueError:
                pass


def untraceable_numbers(text: str, context: Any, rel_tol: float = 0.006) -> list[str]:
    """Números del texto que no corresponden (± redondeo, ± escala %, miles o millones) a una cifra del contexto."""
    nums: list[float] = []
    _numbers_in(to_jsonable(context), nums)
    candidates = set()
    for n in nums:
        for scale in (1, 100, 0.01, 1e-3, 1e-6, 1e4):
            candidates.add(n * scale)
    allowed_small = {0, 1, 2, 3, 4, 5, 9, 14, 25, 50, 100}
    bad = []
    for m in _NUM.findall(text):
        s = m.replace(",", "").replace(" ", "").replace("−", "-")
        try:
            v = float(s)
        except ValueError:
            continue
        if abs(v) in allowed_small or 1900 <= abs(v) <= 2100:
            continue
        if not any(abs(v - c) <= max(rel_tol * abs(c), 0.051 if abs(c) < 10 else 0.51) for c in candidates):
            bad.append(m)
    return bad


def explain(question: str, context: dict, max_tokens: int = 4000) -> dict:
    ctx = to_jsonable(context)
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        try:
            return _explain_llm(question, ctx, max_tokens)
        except Exception as e:  # se informa: no se fabrica una respuesta
            fallback = rule_based_summary(ctx)
            fallback["llm_error"] = f"{type(e).__name__}: {str(e)[:300]}"
            return fallback
    return rule_based_summary(ctx)


def _explain_llm(question: str, ctx: dict, max_tokens: int) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    user = f"CONTEXTO (resultados verificados del motor):\n```json\n{json.dumps(ctx, ensure_ascii=False)[:150000]}\n```\n\nPREGUNTA:\n{question}"
    resp = client.beta.messages.create(
        model=MODEL, max_tokens=max_tokens, system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"}, output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        messages=[{"role": "user", "content": user}],
    )
    if resp.stop_reason == "refusal":
        return {"mode": "llm", "text": None, "refused": True, "model": resp.model}
    text = "".join(b.text for b in resp.content if b.type == "text")
    bad = untraceable_numbers(text, ctx)
    return {"mode": "llm", "model": resp.model, "text": text, "untraceable_numbers": bad,
            "verified": not bad,
            "notice": None if not bad else "La respuesta contiene cifras no rastreables al contexto; revísela."}


def rule_based_summary(ctx: dict) -> dict:
    """Resumen determinista: describe las cifras del contexto sin generar nuevas."""
    lines = []
    if "evaluations" in ctx:
        by_profile: dict[str, list] = {}
        for r in ctx["evaluations"]:
            by_profile.setdefault(r["profile"], []).append(r)
        for pk, rows in by_profile.items():
            lines.append(f"Perfil {pk}:")
            un = next((r for r in rows if r["strategy"] == "Sin cobertura"), None)
            for r in rows:
                s = r["scenarios"]["estres_adverso_severo"]
                val = s.get("combined_pnl", s.get("net_pv"))
                fav = r["scenarios"]["favorable_extremo"]
                favv = fav.get("combined_pnl", fav.get("net_pv"))
                lines.append(f"  • {r['strategy']} ({r['economic_function_label']}): costo inicial "
                             f"{r['initial_cost']:,.2f}; resultado en estrés severo {val:,.2f}; "
                             f"en favorable extremo {favv:,.2f}.")
            if un:
                lines.append("  La comparación usa la misma condición de mercado para todas las alternativas.")
        lines.append("Los escenarios son hipótesis de simulación; no tienen probabilidades asignadas.")
    elif "ratios" in ctx:
        for k, v in ctx["ratios"].items():
            if v.get("value") is None:
                lines.append(f"• {k}: no calculable (faltan {', '.join(v.get('missing', []))}).")
            else:
                lines.append(f"• {k} = {v['value']:.4f} ({v['formula']}).")
    else:
        lines.append("No hay un resumen por reglas para este tipo de resultado; consulte las tablas del motor.")
    return {"mode": "reglas", "text": "\n".join(lines), "verified": True,
            "notice": "Explicador determinista (sin modelo de lenguaje configurado)."}
