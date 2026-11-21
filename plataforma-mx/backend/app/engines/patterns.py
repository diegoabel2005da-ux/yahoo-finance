"""Tendencias y chartismo algorítmico (secciones 8 y 9).

Las figuras son descripciones de la geometría del precio. No generan órdenes ni
implican rentabilidad. Cada detección expone criterios, puntos, estado y nivel de
invalidación para que el usuario pueda revisarla o ajustarla.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .technical import pivots, sma


def linear_trend(close: pd.Series) -> dict:
    """Regresión MCO del log-precio contra el tiempo (en barras)."""
    y = np.log(close.to_numpy(float))
    x = np.arange(len(y), dtype=float)
    if len(y) < 3:
        return {"error": "observaciones insuficientes"}
    b, a = np.polyfit(x, y, 1)
    fit = a + b * x
    ss_res = ((y - fit) ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    return {"slope_log_per_bar": float(b), "r_squared": float(1 - ss_res / ss_tot) if ss_tot else None,
            "direction": "alcista" if b > 0 else "bajista" if b < 0 else "lateral",
            "fitted": np.exp(fit).tolist()}


def classify_trends(close: pd.Series, primary: int = 200, secondary: int = 50, short: int = 20) -> dict:
    """Reglas documentadas:
    - Primaria: precio vs SMA(primary) y pendiente de SMA(primary) en 20 barras.
    - Secundaria: SMA(secondary) vs SMA(primary).
    - Corto plazo: precio vs SMA(short) y ROC de SMA(short) en 5 barras.
    """
    res = {}
    for name, n in (("primaria", primary), ("secundaria", secondary), ("corto_plazo", short)):
        if len(close) < n + 20:
            res[name] = {"state": "datos_insuficientes", "window": n}
            continue
        m = sma(close, n)
        slope = m.iloc[-1] / m.iloc[-21] - 1
        above = close.iloc[-1] > m.iloc[-1]
        state = "alcista" if above and slope > 0 else "bajista" if (not above and slope < 0) else "lateral/mixta"
        res[name] = {"state": state, "window": n, "sma": float(m.iloc[-1]),
                     "sma_slope_20": float(slope), "price_above_sma": bool(above)}
    res["rules"] = ("Alcista si precio>SMA y pendiente SMA(20 barras)>0; bajista si precio<SMA y "
                    "pendiente<0; en otro caso lateral/mixta.")
    return res


def structural_breaks(close: pd.Series, min_size: int = 30, max_breaks: int = 3) -> list[dict]:
    """Segmentación binaria por mínimos cuadrados sobre el log-precio (cambio de media/tendencia).
    Se acepta un corte si reduce la suma de cuadrados en > 20 %."""
    y = np.log(close.to_numpy(float))

    def sse(seg):
        if len(seg) < 3:
            return 0.0
        x = np.arange(len(seg))
        b, a = np.polyfit(x, seg, 1)
        return float(((seg - (a + b * x)) ** 2).sum())

    breaks = []
    segments = [(0, len(y))]
    for _ in range(max_breaks):
        best = None
        for (s, e) in segments:
            base = sse(y[s:e])
            for k in range(s + min_size, e - min_size):
                tot = sse(y[s:k]) + sse(y[k:e])
                gain = (base - tot) / base if base > 0 else 0
                if gain > 0.2 and (best is None or gain > best[0]):
                    best = (gain, k, s, e)
        if not best:
            break
        gain, k, s, e = best
        segments.remove((s, e))
        segments += [(s, k), (k, e)]
        breaks.append({"idx": k, "date": close.index[k], "sse_reduction": gain})
    return sorted(breaks, key=lambda d: d["idx"])


def _near(a: float, b: float, tol: float) -> bool:
    return abs(a - b) / ((a + b) / 2) <= tol


def detect_patterns(df: pd.DataFrame, left: int = 5, right: int = 5, tol: float = 0.03,
                    min_depth: float = 0.03) -> list[dict]:
    """Detecta figuras sobre pivotes fractales confirmados. `df` con high, low, close."""
    pv = pivots(df["high"], df["low"], left, right).sort_values("idx").reset_index(drop=True)
    close = df["close"]
    last_close = float(close.iloc[-1])
    out: list[dict] = []
    highs = pv[pv.kind == "maximo"].reset_index(drop=True)
    lows = pv[pv.kind == "minimo"].reset_index(drop=True)

    def lows_between(i0, i1):
        return lows[(lows.idx > i0) & (lows.idx < i1)]

    def highs_between(i0, i1):
        return highs[(highs.idx > i0) & (highs.idx < i1)]

    def after(idx):
        return close.iloc[idx + 1:]

    # --- Doble techo / doble suelo ---
    for i in range(len(highs) - 1):
        h1, h2 = highs.iloc[i], highs.iloc[i + 1]
        mid = lows_between(h1.idx, h2.idx)
        if mid.empty or not _near(h1.price, h2.price, tol):
            continue
        neck = float(mid.price.min())
        if (min(h1.price, h2.price) - neck) / neck < min_depth:
            continue
        post = after(int(h2.idx))
        status = "confirmada" if (post < neck).any() else "en_formacion"
        if (post > max(h1.price, h2.price)).any():
            status = "invalidada"
        out.append({"pattern": "doble_techo", "status": status,
                    "points": [_pt(h1), _pt(mid.loc[mid.price.idxmin()]), _pt(h2)],
                    "confirmation_level": neck, "invalidation_level": float(max(h1.price, h2.price)),
                    "criteria": f"Dos máximos pivote a ±{tol:.0%}, valle intermedio ≥{min_depth:.0%}; "
                                "confirma cierre bajo la línea de cuello"})
    for i in range(len(lows) - 1):
        l1, l2 = lows.iloc[i], lows.iloc[i + 1]
        mid = highs_between(l1.idx, l2.idx)
        if mid.empty or not _near(l1.price, l2.price, tol):
            continue
        neck = float(mid.price.max())
        if (neck - max(l1.price, l2.price)) / neck < min_depth:
            continue
        post = after(int(l2.idx))
        status = "confirmada" if (post > neck).any() else "en_formacion"
        if (post < min(l1.price, l2.price)).any():
            status = "invalidada"
        out.append({"pattern": "doble_suelo", "status": status,
                    "points": [_pt(l1), _pt(mid.loc[mid.price.idxmax()]), _pt(l2)],
                    "confirmation_level": neck, "invalidation_level": float(min(l1.price, l2.price)),
                    "criteria": f"Dos mínimos pivote a ±{tol:.0%}; confirma cierre sobre el cuello"})

    # --- Hombro-cabeza-hombro (y su inversión) ---
    for i in range(len(highs) - 2):
        ls, hd, rs = highs.iloc[i], highs.iloc[i + 1], highs.iloc[i + 2]
        if hd.price > ls.price and hd.price > rs.price and _near(ls.price, rs.price, tol * 1.5):
            t1 = lows_between(ls.idx, hd.idx)
            t2 = lows_between(hd.idx, rs.idx)
            if t1.empty or t2.empty:
                continue
            p1, p2 = t1.loc[t1.price.idxmin()], t2.loc[t2.price.idxmin()]
            slope = (p2.price - p1.price) / (p2.idx - p1.idx)
            neck_now = p2.price + slope * (len(close) - 1 - p2.idx)
            post = after(int(rs.idx))
            status = "confirmada" if (post < neck_now).any() else "en_formacion"
            if (post > hd.price).any():
                status = "invalidada"
            out.append({"pattern": "hombro_cabeza_hombro", "status": status,
                        "points": [_pt(ls), _pt(p1), _pt(hd), _pt(p2), _pt(rs)],
                        "confirmation_level": float(neck_now), "invalidation_level": float(hd.price),
                        "criteria": "Cabeza > hombros, hombros similares; cuello por los dos valles"})
    for i in range(len(lows) - 2):
        ls, hd, rs = lows.iloc[i], lows.iloc[i + 1], lows.iloc[i + 2]
        if hd.price < ls.price and hd.price < rs.price and _near(ls.price, rs.price, tol * 1.5):
            t1 = highs_between(ls.idx, hd.idx)
            t2 = highs_between(hd.idx, rs.idx)
            if t1.empty or t2.empty:
                continue
            p1, p2 = t1.loc[t1.price.idxmax()], t2.loc[t2.price.idxmax()]
            slope = (p2.price - p1.price) / (p2.idx - p1.idx)
            neck_now = p2.price + slope * (len(close) - 1 - p2.idx)
            post = after(int(rs.idx))
            status = "confirmada" if (post > neck_now).any() else "en_formacion"
            if (post < hd.price).any():
                status = "invalidada"
            out.append({"pattern": "hombro_cabeza_hombro_invertido", "status": status,
                        "points": [_pt(ls), _pt(p1), _pt(hd), _pt(p2), _pt(rs)],
                        "confirmation_level": float(neck_now), "invalidation_level": float(hd.price),
                        "criteria": "Cabeza < hombros, hombros similares; cuello por los dos picos"})

    # --- Triángulos, canales y cuñas: rectas por los últimos 3 pivotes de cada lado ---
    if len(highs) >= 3 and len(lows) >= 3:
        hh, ll = highs.tail(3), lows.tail(3)
        bh, ah = np.polyfit(hh.idx, hh.price, 1)
        bl, al = np.polyfit(ll.idx, ll.price, 1)
        n = len(close) - 1
        upper, lower = ah + bh * n, al + bl * n
        ref = float(close.iloc[-60:].mean())
        flat = 0.0005 * ref  # pendiente "plana" por barra
        kind = None
        if abs(bh) <= flat and bl > flat:
            kind = "triangulo_ascendente"
        elif bh < -flat and abs(bl) <= flat:
            kind = "triangulo_descendente"
        elif bh < -flat and bl > flat:
            kind = "triangulo_simetrico"
        elif abs(bh - bl) <= flat and abs(bh) > flat:
            kind = "canal_alcista" if bh > 0 else "canal_bajista"
        elif abs(bh) <= flat and abs(bl) <= flat:
            kind = "canal_lateral"
        elif bh > 0 and bl > 0 and bl > bh:
            kind = "cuna_ascendente"
        elif bh < 0 and bl < 0 and bh < bl:
            kind = "cuna_descendente"
        if kind:
            status = "ruptura_alcista" if last_close > upper else "ruptura_bajista" if last_close < lower else "vigente"
            out.append({"pattern": kind, "status": status,
                        "points": [_pt(r) for _, r in pd.concat([hh, ll]).sort_values("idx").iterrows()],
                        "upper_line": {"slope": float(bh), "intercept": float(ah), "value_now": float(upper)},
                        "lower_line": {"slope": float(bl), "intercept": float(al), "value_now": float(lower)},
                        "criteria": "Rectas MCO por los 3 últimos pivotes máximos y mínimos; "
                                    "clasificación por signo/convergencia de pendientes"})

    # --- Banderas y banderines: impulso fuerte seguido de consolidación corta ---
    out += _flags(close)
    out += support_resistance(pv, last_close, tol)
    return out


def _flags(close: pd.Series, pole: int = 10, cons: int = 15, min_move: float = 0.10) -> list[dict]:
    if len(close) < pole + cons + 1:
        return []
    c = close.to_numpy(float)
    start, top, end = len(c) - cons - pole - 1, len(c) - cons - 1, len(c) - 1
    move = c[top] / c[start] - 1
    if abs(move) < min_move:
        return []
    seg = c[top:end + 1]
    x = np.arange(len(seg))
    slope = np.polyfit(x, seg, 1)[0]
    rng = (seg.max() - seg.min()) / seg.mean()
    if rng > abs(move) * 0.5:
        return []
    width_early = np.ptp(seg[: len(seg) // 2])
    width_late = np.ptp(seg[len(seg) // 2:])
    kind = "banderin" if width_late < 0.6 * width_early else "bandera"
    bull = move > 0
    if (bull and slope > 0) or (not bull and slope < 0):
        return []  # una bandera consolida en contra del impulso
    return [{"pattern": f"{kind}_{'alcista' if bull else 'bajista'}", "status": "en_formacion",
             "points": [{"date": close.index[start], "price": c[start]},
                        {"date": close.index[top], "price": c[top]},
                        {"date": close.index[end], "price": c[end]}],
             "pole_move": float(move),
             "criteria": f"Impulso ≥{min_move:.0%} en {pole} barras y consolidación de {cons} barras "
                         "contra el impulso con rango < 50 % del impulso"}]


def support_resistance(pv: pd.DataFrame, last_close: float, tol: float = 0.02, min_touches: int = 2) -> list[dict]:
    """Agrupa pivotes con precios a ±tol; cada grupo con ≥ min_touches toques es un nivel."""
    if pv.empty:
        return []
    prices = sorted(pv.price.tolist())
    clusters: list[list[float]] = []
    for p in prices:
        if clusters and _near(np.mean(clusters[-1]), p, tol):
            clusters[-1].append(p)
        else:
            clusters.append([p])
    out = []
    for cl in clusters:
        if len(cl) >= min_touches:
            lvl = float(np.mean(cl))
            out.append({"pattern": "soporte" if lvl < last_close else "resistencia", "status": "vigente",
                        "level": lvl, "touches": len(cl),
                        "criteria": f"≥{min_touches} pivotes a ±{tol:.0%} del nivel"})
    return out


def _pt(row) -> dict:
    return {"date": row["date"], "price": float(row["price"]), "kind": row.get("kind")}
