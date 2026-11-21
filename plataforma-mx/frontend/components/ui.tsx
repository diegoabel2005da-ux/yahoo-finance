"use client";
import { useState } from "react";
import { ORIGIN_LABEL } from "@/lib/format";

export function Card({ title, children, actions, className = "" }: { title?: string; children: React.ReactNode; actions?: React.ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="card-title mb-0">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-4">
      <h1 className="text-xl font-semibold text-navy-900 dark:text-white">{title}</h1>
      {subtitle && <p className="mt-1 max-w-4xl text-sm text-slate-600 dark:text-slate-400">{subtitle}</p>}
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="block" title={hint}>
      <span className="label">{label}</span>
      {children}
    </label>
  );
}

export function Num({ label, value, onChange, step = "any", hint }: { label: string; value: number | string | undefined; onChange: (v: number) => void; step?: string; hint?: string }) {
  return (
    <Field label={label} hint={hint}>
      <input className="input" type="number" step={step} value={value === undefined || (typeof value === "number" && Number.isNaN(value)) ? "" : value} onChange={(e) => onChange(e.target.value === "" ? NaN : Number(e.target.value))} />
    </Field>
  );
}

export function Text({ label, value, onChange, placeholder, type = "text" }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; type?: string }) {
  return (
    <Field label={label}>
      <input className="input" type={type} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

export function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <Field label={label}>
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </Field>
  );
}

export function ErrorBox({ error }: { error: any }) {
  if (!error) return null;
  return (
    <div role="alert" className="my-2 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
      <strong>{error.status === 409 ? "Cálculo bloqueado: " : error.status === 422 ? "Datos insuficientes o inválidos: " : "Error: "}</strong>
      {String(error.message ?? error)}
    </div>
  );
}

export function Notice({ children, tone = "info" }: { children: React.ReactNode; tone?: "info" | "warn" }) {
  const c = tone === "warn" ? "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100" : "border-turq/40 bg-teal-50 text-teal-900 dark:border-turq-700 dark:bg-navy-800 dark:text-teal-100";
  return <div className={`my-2 rounded border px-3 py-2 text-xs ${c}`}>{children}</div>;
}

export function OriginTag({ origin }: { origin?: string | null }) {
  if (!origin) return null;
  const theo = origin === "resultado_de_modelo";
  const off = origin === "observado_fuente_oficial";
  const cls = theo ? "bg-violet-100 text-violet-800 dark:bg-violet-900 dark:text-violet-100" : off ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-100" : "bg-slate-200 text-slate-700 dark:bg-navy-700 dark:text-slate-200";
  return <span className={`tag ${cls}`}>{ORIGIN_LABEL[origin] ?? origin}</span>;
}

export function RiskTag({ fn, label }: { fn: string; label?: string }) {
  const map: Record<string, string> = {
    cobertura_directa: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-100",
    cobertura_parcial: "bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-100",
    cobertura_cruzada: "bg-sky-100 text-sky-800 dark:bg-sky-900 dark:text-sky-100",
    volatilidad: "bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100",
    ingreso_primas: "bg-orange-100 text-orange-900 dark:bg-orange-900 dark:text-orange-100",
    no_compatible: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-100",
    sin_cobertura: "bg-slate-200 text-slate-700 dark:bg-navy-700 dark:text-slate-200",
  };
  return <span className={`tag ${map[fn] ?? map.sin_cobertura}`}>{label ?? fn.replace(/_/g, " ")}</span>;
}

export function AuditInfo({ calc }: { calc?: { audit_id: number; result_digest: string; engine_version: string } | null }) {
  if (!calc) return null;
  return (
    <p className="mt-2 font-mono text-[10px] text-slate-500">
      Auditoría #{calc.audit_id} · sha256 {calc.result_digest.slice(0, 16)}… · motor {calc.engine_version} ·{" "}
      <a className="underline" href={`/api/audit/${calc.audit_id}`} target="_blank" rel="noreferrer">
        ver registro
      </a>
    </p>
  );
}

export function Table({ rows, cols, max = 500, fmt }: { rows: any[]; cols?: string[]; max?: number; fmt?: Record<string, (v: any) => React.ReactNode> }) {
  if (!rows?.length) return <p className="text-sm text-slate-500">Sin registros.</p>;
  const c = cols ?? Object.keys(rows[0]);
  const shown = rows.slice(-max);
  return (
    <div className="max-h-96 overflow-auto rounded border border-slate-200 dark:border-navy-700">
      <table className="tbl">
        <thead>
          <tr>{c.map((k) => <th key={k}>{k}</th>)}</tr>
        </thead>
        <tbody>
          {shown.map((r, i) => (
            <tr key={i}>
              {c.map((k) => (
                <td key={k}>{fmt?.[k] ? fmt[k](r[k]) : typeof r[k] === "number" ? Number(r[k]).toLocaleString("es-MX", { maximumFractionDigits: 6 }) : typeof r[k] === "object" && r[k] !== null ? JSON.stringify(r[k]) : String(r[k] ?? "—")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > max && <p className="p-1 text-[10px] text-slate-500">Mostrando los últimos {max} de {rows.length}.</p>}
    </div>
  );
}

export function Upload({ endpoint, label, extra, onDone, template }: { endpoint: string; label: string; extra?: Record<string, string>; onDone?: (r: any) => void; template?: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<any>(null);
  const send = async () => {
    if (!file) return;
    setBusy(true);
    setErr(null);
    const fd = new FormData();
    fd.append("file", file);
    Object.entries(extra ?? {}).forEach(([k, v]) => fd.append(k, v));
    try {
      const r = await fetch(`/api${endpoint}`, { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok) throw Object.assign(new Error(typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail)), { status: r.status });
      setRes(j);
      onDone?.(j);
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  };
  const rejected = res?.rejected ?? [];
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-end gap-2">
        <Field label={label}>
          <input type="file" accept=".csv,.xlsx,.xls" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-xs" />
        </Field>
        <button className="btn" disabled={!file || busy} onClick={send}>
          {busy ? "Validando…" : "Importar y validar"}
        </button>
        {template && (
          <a className="btn-ghost" href={`/api/templates/${template}`}>
            Plantilla
          </a>
        )}
      </div>
      <ErrorBox error={err} />
      {res && (
        <div className="text-xs">
          <p>
            Aceptados: <b>{res.accepted ?? res.accepted_rows ?? res.statements ?? "—"}</b> · Rechazados: <b>{rejected.length}</b>
            {res.discrepancies?.length ? (
              <>
                {" "}
                · <span className="font-semibold text-red-700">Discrepancias: {res.discrepancies.length}</span>
              </>
            ) : null}
          </p>
          {rejected.length > 0 && (
            <ul className="mt-1 max-h-32 list-disc overflow-auto pl-5 text-red-700 dark:text-red-300">
              {rejected.slice(0, 50).map((r: any, i: number) => (
                <li key={i}>
                  Renglón {r.row}: {r.errors.join("; ")}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="rounded border border-slate-200 p-2 dark:border-navy-700">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
      {sub && <div className="text-[10px] text-slate-500">{sub}</div>}
    </div>
  );
}

export function useRun<T>() {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<T>) => {
    setBusy(true);
    setError(null);
    try {
      const d = await fn();
      setData(d);
      return d;
    } catch (e) {
      setError(e);
      setData(null);
    } finally {
      setBusy(false);
    }
  };
  return { data, error, busy, run, setData };
}
