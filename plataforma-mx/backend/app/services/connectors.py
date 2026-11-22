"""Conectores a fuentes oficiales.

Ningún conector devuelve datos inventados: si la fuente no responde, requiere licencia o
credenciales, el conector devuelve un estado explícito ('no_disponible') con el motivo, y la
interfaz ofrece la importación validada de archivos como alternativa.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone

import httpx2 as httpx

SOURCES = {
    "BMV": {"url": "https://www.bmv.com.mx/", "access": "Sitio público; datos de mercado sujetos a licencia (Infosel/BMV Market Data)."},
    "BIVA": {"url": "https://www.biva.mx/", "access": "Sitio público; reutilización sujeta a términos de uso."},
    "MexDer": {"url": "https://www.mexder.com.mx/", "access": "Boletines y especificaciones de contratos públicos; "
               "precios de liquidación y AIMs publicados por MexDer/Asigna."},
    "CNBV": {"url": "https://stivconsultasexternas.cnbv.gob.mx/", "access": "Consulta pública de información de emisoras (STIV)."},
    "Banxico": {"url": "https://www.banxico.org.mx/SieAPIRest/service/v1/", "access": "API SIE: requiere token gratuito (BANXICO_TOKEN)."},
    "Yahoo Finance": {"url": "https://query1.finance.yahoo.com/v8/finance/chart/%5EMXX?range=1d",
                      "access": "Fuente de referencia designada por el usuario (uso personal y de investigación, "
                                "términos de Yahoo aceptados). Datos vía yfinance."},
    "INEGI": {"url": "https://www.inegi.org.mx/servicios/api_indicadores.html", "access": "API de indicadores: requiere token (INEGI_TOKEN)."},
}

# Series SIE verificadas contra el título oficial devuelto por la API de Banxico (21-nov-2026).
# Se pueden añadir o sobrescribir con BANXICO_SERIES="CODIGO=SFxxxx,CODIGO2=SFyyyy".
DEFAULT_BANXICO_SERIES = {
    "TIIE_28": "SF43783",        # TIIE a 28 días, % anual
    "TIIE_91": "SF43878",        # TIIE a 91 días
    "TIIE_182": "SF111916",      # TIIE a 182 días
    "TIIE_FONDEO": "SF331451",   # TIIE de Fondeo a un día hábil bancario (mediana ponderada por volumen)
    "TASA_OBJETIVO": "SF61745",  # Tasa objetivo de Banxico
    "CETES_28": "SF43936",       # Cetes 28 días, tasa de rendimiento de la subasta semanal
    "CETES_91": "SF43939",
    "CETES_182": "SF43942",
    "CETES_364": "SF43945",
    "FIX": "SF43718",            # Tipo de cambio FIX (pesos por dólar), fecha de determinación
    "BONO_M_3A": "SF43883",      # Bonos a tasa fija 3 años, tasa de rendimiento de la subasta
    "BONO_M_5A": "SF43886",
    "BONO_M_10A": "SF44071",
    "BONO_M_20A": "SF45384",
    "BONO_M_30A": "SF60696",
}
BONO_M_TENORS = {"BONO_M_3A": 3, "BONO_M_5A": 5, "BONO_M_10A": 10, "BONO_M_20A": 20, "BONO_M_30A": 30}
CETES_TENORS = {"CETES_28": 28, "CETES_91": 91, "CETES_182": 182, "CETES_364": 364}


def banxico_series_map() -> dict[str, str]:
    m = dict(DEFAULT_BANXICO_SERIES)
    raw = os.environ.get("BANXICO_SERIES", "")
    for part in raw.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            m[k.strip()] = v.strip()
    return m


def check_source(name: str, timeout: float = 8.0) -> dict:
    info = SOURCES[name]
    try:
        r = httpx.get(info["url"], timeout=timeout, follow_redirects=True)
        ok = r.status_code < 400
        return {"source": name, "url": info["url"], "reachable": ok, "status_code": r.status_code,
                "access": info["access"], "checked_at": datetime.now(timezone.utc).isoformat()}
    except Exception as e:  # red bloqueada, DNS, TLS…
        return {"source": name, "url": info["url"], "reachable": False, "error": type(e).__name__,
                "detail": str(e)[:200], "access": info["access"],
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "fallback": "Importación validada de CSV/Excel"}


def fetch_banxico(rate_code: str, start: date, end: date, timeout: float = 15.0) -> dict:
    """Descarga observaciones de la API SIE de Banxico. Devuelve renglones con procedencia
    completa listos para `import_rates`, o un estado 'no_disponible' con motivo."""
    # Si no hay variable, se envía un marcador: en entornos con la credencial guardada, el proxy de red
    # sustituye el encabezado Bmx-Token por el token real. Sin credencial, Banxico responde 401 y se reporta.
    token = os.environ.get("BANXICO_TOKEN") or "proxy-injected"
    series = banxico_series_map().get(rate_code)
    if not series:
        return {"status": "no_disponible", "reason": f"sin identificador SIE configurado para {rate_code}"}
    url = f"{SOURCES['Banxico']['url']}series/{series}/datos/{start.isoformat()}/{end.isoformat()}"
    try:
        r = httpx.get(url, headers={"Bmx-Token": token, "Accept": "application/json"}, timeout=timeout)
        if r.status_code in (401, 403):
            return {"status": "no_disponible", "reason": f"Banxico rechazó el token (HTTP {r.status_code}): configure "
                                                         "BANXICO_TOKEN o guarde la credencial del entorno"}
        r.raise_for_status()
        data = r.json()["bmx"]["series"][0]
    except Exception as e:
        return {"status": "no_disponible", "reason": f"{type(e).__name__}: {str(e)[:200]}"}
    retrieved = datetime.now(timezone.utc).isoformat()
    rows = []
    for d in data.get("datos", []):
        if d.get("dato") in (None, "N/E", ""):
            continue  # el SIE marca 'N/E' cuando no existe dato: no se rellena
        dd, mm, yy = d["fecha"].split("/")
        rows.append({"rate_code": rate_code, "rate_name": data.get("titulo", rate_code), "tenor": rate_code,
                     "market_date": f"{yy}-{mm}-{dd}", "value_pct": d["dato"].replace(",", ""),
                     "convention": ("Pesos por dólar (FIX)" if rate_code == "FIX" else
                                    "Rendimiento anual de subasta, cupón semestral (182 días)" if rate_code.startswith("BONO_M") else
                                    "Tasa anual, base ACT/360 (verificar metodología vigente)"),
                     "source": f"Banxico SIE {series}", "retrieved_at": retrieved,
                     "origin": "observado_fuente_oficial"})
    return {"status": "ok", "series": series, "rows": rows}


def fetch_mexder_catalog() -> dict:
    """MexDer no ofrece (en lo verificado) una API pública documentada del universo de
    subyacentes. El catálogo se actualiza importando la publicación vigente de contratos."""
    chk = check_source("MexDer")
    return {"status": "requiere_importacion", "connectivity": chk,
            "instructions": "Descargue de MexDer la relación vigente de contratos de futuros y opciones sobre "
                            "acciones y cárguela con la plantilla catalog_template.csv."}


def check_yahoo() -> dict:
    return check_source("Yahoo Finance")
