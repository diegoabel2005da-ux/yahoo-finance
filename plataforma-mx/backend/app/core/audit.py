"""Auditoría reproducible de cálculos (sección 3.4)."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any

import numpy as np

ENGINE_VERSION = "0.1.0"


def to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return to_jsonable(asdict(obj))
    if hasattr(obj, "model_dump"):
        return to_jsonable(obj.model_dump(mode="json"))
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [to_jsonable(v) for v in obj.tolist()]
    if isinstance(obj, (np.floating,)):
        obj = float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if hasattr(obj, "value") and hasattr(obj, "name") and not isinstance(obj, (str, int)):
        return obj.value  # Enum
    return obj


def digest(payload: Any) -> str:
    raw = json.dumps(to_jsonable(payload), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_audit(calculation: str, inputs: Any, parameters: Any, formulas: list[str], result: Any,
                data_sources: list[dict] | None = None, transformations: list[str] | None = None) -> dict:
    res = to_jsonable(result)
    return {
        "calculation": calculation,
        "engine_version": ENGINE_VERSION,
        "inputs": to_jsonable(inputs),
        "parameters": to_jsonable(parameters),
        "formulas": formulas,
        "data_sources": data_sources or [],
        "transformations": transformations or [],
        "result_digest": digest(res),
        "result": res,
    }


def persist_audit(db, audit: dict) -> int:
    from .db import AuditRecord

    rec = AuditRecord(**audit)
    db.add(rec)
    db.commit()
    return rec.id
