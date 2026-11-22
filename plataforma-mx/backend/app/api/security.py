"""Protección de operaciones que modifican datos en despliegues públicos.

Si la variable ADMIN_TOKEN está definida (p. ej. en Render), las rutas que importan, reemplazan o
actualizan datos exigen el encabezado `X-Admin-Token` con ese valor. Consultas y cálculos siguen
abiertos. Sin ADMIN_TOKEN (uso local), no se exige nada.
"""
from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException


def require_admin(x_admin_token: str | None = Header(default=None)):
    expected = os.environ.get("ADMIN_TOKEN")
    if not expected:
        return
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(403, "Operación que modifica datos: requiere el token de administrador "
                                 "(Inicio → «Token de administrador»).")
