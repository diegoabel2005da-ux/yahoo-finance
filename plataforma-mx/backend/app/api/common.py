from __future__ import annotations

from fastapi import HTTPException

from ..core.audit import build_audit, persist_audit, to_jsonable


def respond(db, calculation: str, inputs, params, formulas: list[str], result, sources: list[dict] | None = None,
            transformations: list[str] | None = None) -> dict:
    audit = build_audit(calculation, inputs, params, formulas, result, sources, transformations)
    aid = persist_audit(db, audit)
    return {"result": audit["result"], "audit_id": aid, "result_digest": audit["result_digest"],
            "engine_version": audit["engine_version"]}


def bad_request(e: Exception):
    raise HTTPException(status_code=422, detail=str(e))


def df_rows(df, max_rows: int | None = None):
    d = df.reset_index()
    c0 = d.columns[0]
    d[c0] = d[c0].astype(str).str[:10]
    if max_rows:
        d = d.tail(max_rows)
    return to_jsonable(d.to_dict(orient="records"))
