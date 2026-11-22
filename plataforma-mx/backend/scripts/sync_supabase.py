"""Sube el contenido de la base local (SQLite) a Supabase mediante la función temporal
public.plataforma_load (sólo service_role), por HTTPS.

La llave secreta NO se lee de ningún archivo: en el entorno de Claude Code la inyecta el proxy como
encabezado `apikey`. Fuera de ese entorno, defina SUPABASE_SECRET_KEY.

Uso: python scripts/sync_supabase.py [ruta_sqlite] [https://<ref>.supabase.co]
"""
import json
import os
import sqlite3
import sys
import time

import httpx2 as httpx
from sqlalchemy import JSON, Boolean

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.db import Base  # noqa: E402

ORDER = ["catalog_revisions", "import_batches", "instruments", "audit_records", "price_records", "discrepancies",
         "rate_observations", "curve_snapshots", "financial_statements", "corporate_actions", "futures_contracts",
         "option_contracts", "contract_quotes", "exposures", "studies"]
MAX_BYTES = 1_500_000


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "plataforma.db"
    url = (sys.argv[2] if len(sys.argv) > 2 else "https://tlwqadsvlnrrhakuxojq.supabase.co").rstrip("/")
    key = os.environ.get("SUPABASE_SECRET_KEY", "proxy-injected")
    tables = {t.name: t for t in Base.metadata.sorted_tables}
    src = sqlite3.connect(db_path)
    src.row_factory = sqlite3.Row
    client = httpx.Client(timeout=120, headers={"apikey": key, "Content-Type": "application/json"})
    summary = {}
    for name in ORDER:
        t = tables[name]
        json_cols = {c.name for c in t.columns if isinstance(c.type, JSON)}
        bool_cols = {c.name for c in t.columns if isinstance(c.type, Boolean)}
        cols = [c.name for c in t.columns]
        total = inserted = 0
        batch, size = [], 0

        def flush():
            nonlocal inserted, batch, size
            if not batch:
                return
            body = json.dumps({"p_table": name, "p_rows": batch}, ensure_ascii=False)
            for attempt in range(4):
                r = client.post(f"{url}/rest/v1/rpc/plataforma_load", content=body.encode())
                if r.status_code == 200:
                    inserted += int(r.json())
                    break
                if attempt == 3 or r.status_code in (400, 401, 403, 404):
                    raise SystemExit(f"{name}: HTTP {r.status_code} {r.text[:300]}")
                time.sleep(2 * (attempt + 1))
            batch, size = [], 0

        for row in src.execute(f'SELECT {", ".join(cols)} FROM "{name}" ORDER BY id'):
            rec = {}
            for c in cols:
                v = row[c]
                if c in json_cols and isinstance(v, str):
                    v = json.loads(v)
                elif c in bool_cols and v is not None:
                    v = bool(v)
                rec[c] = v
            s = len(json.dumps(rec, ensure_ascii=False))
            if size + s > MAX_BYTES:
                flush()
            batch.append(rec)
            size += s
            total += 1
        flush()
        summary[name] = {"locales": total, "insertadas": inserted}
        print(f"{name:22} locales {total:7}  insertadas {inserted:7}", flush=True)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
