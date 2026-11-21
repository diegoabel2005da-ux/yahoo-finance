"use client";
import { useEffect, useMemo, useState } from "react";
import Plot from "@/components/Plot";
import { AuditInfo, Card, ErrorBox, Notice, Num, OriginTag, PageHeader, RiskTag, Select, Table, useRun } from "@/components/ui";
import { api, Calc } from "@/lib/api";
import { money, num } from "@/lib/format";

const LABELS: Record<string, string> = {
  protective_put: "Protective Put", protective_call: "Call protectora", covered_call: "Covered Call", collar: "Collar",
  short_futures: "Venta de futuros", long_futures: "Compra de futuros", long_straddle: "Long Straddle", short_straddle: "Short Straddle",
  long_strangle: "Long Strangle", short_strangle: "Short Strangle", long_call_butterfly: "Long Call Butterfly", short_call_butterfly: "Short Call Butterfly",
  long_put_butterfly: "Long Put Butterfly", short_put_butterfly: "Short Put Butterfly",
};

type Leg = { kind: string; qty: number; multiplier: number; strike: number; expiry_years: number; premium: number; premium_origin: string; entry_price: number; style: string };
const emptyLeg = (): Leg => ({ kind: "call", qty: 1, multiplier: 100, strike: NaN, expiry_years: 0.25, premium: NaN, premium_origin: "supuesto_del_usuario", entry_price: NaN, style: "europea" });

export default function Estrategias() {
  const [tpl, setTpl] = useState<string[]>([]);
  useEffect(() => {
    api.get("/strategies/templates").then((t) => setTpl(t.templates)).catch(() => {});
  }, []);
  const [mode, setMode] = useState<"template" | "manual">("template");
  const [m, setM] = useState<any>({ template: "protective_put", S0: NaN, T: 0.25, r: NaN, q: 0, sigma: NaN, contracts: 1, multiplier: 100, exposure_sign: 1, k_put: NaN, k_call: NaN, k1: NaN, k2: NaN, k3: NaN, include_stock: true });
  const [legs, setLegs] = useState<Leg[]>([emptyLeg()]);
  const set = (k: string) => (v: any) => setM({ ...m, [k]: v });
  const { data, error, busy, run } = useRun<Calc>();
  const go = () => {
    const strikes = Object.fromEntries(["k_put", "k_call", "k1", "k2", "k3"].filter((k) => Number.isFinite(m[k])).map((k) => [k, m[k]]));
    const body: any = { S0: m.S0, T: m.T, r: m.r, q: m.q, sigma: m.sigma, contracts: m.contracts, multiplier: m.multiplier, exposure_sign: m.exposure_sign, eval_times: [0, m.T / 2], strikes };
    if (mode === "template") body.template = m.template;
    else body.legs = legs.map((l) => ({ ...l, strike: Number.isFinite(l.strike) ? l.strike : null, premium: Number.isFinite(l.premium) ? l.premium : null, entry_price: Number.isFinite(l.entry_price) ? l.entry_price : null }));
    run(() => api.post("/strategies/build", body));
  };
  const r = data?.result;
  const overlay = mode === "template" && m.include_stock;
  const curves = useMemo(() => {
    if (!r) return [];
    const shares = m.contracts * m.multiplier * m.exposure_sign;
    const colors = ["#0B1F3A", "#14B8A6", "#A855F7"];
    return Object.entries(r.curves).map(([k, ys]: any, i) => ({
      x: r.grid,
      y: ys.map((y: number, j: number) => y + (overlay ? shares * (r.grid[j] - m.S0) : 0)),
      name: k === "expiry" ? "Al vencimiento" : `Revaluación ${k}`,
      line: { color: colors[i % 3], dash: k === "expiry" ? "solid" : "dash" },
    }));
  }, [r, overlay, m]);
  return (
    <>
      <PageHeader title="Estrategias" subtitle="Straddles, strangles, butterflies, collars, protective put, covered call, futuros y constructor manual por legs, con validación de signos, cantidades, strikes, vencimientos y obligaciones." />
      <Card title="Constructor">
        <div className="mb-3 flex gap-2">
          <button className={mode === "template" ? "btn" : "btn-ghost"} onClick={() => setMode("template")}>Plantillas</button>
          <button className={mode === "manual" ? "btn" : "btn-ghost"} onClick={() => setMode("manual")}>Manual (legs)</button>
        </div>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
          {mode === "template" && <Select label="Estrategia" value={m.template} onChange={set("template")} options={tpl.map((t) => [t, LABELS[t] ?? t])} />}
          <Num label="Spot S0" value={m.S0} onChange={set("S0")} />
          <Num label="Vencimiento T (años)" value={m.T} onChange={set("T")} />
          <Num label="r" value={m.r} onChange={set("r")} />
          <Num label="q" value={m.q} onChange={set("q")} />
          <Num label="σ (supuesto)" value={m.sigma} onChange={set("sigma")} />
          {mode === "template" && (
            <>
              <Num label="Contratos" value={m.contracts} onChange={set("contracts")} />
              <Num label="Multiplicador" value={m.multiplier} onChange={set("multiplier")} />
              <Select label="Exposición" value={String(m.exposure_sign)} onChange={(v) => set("exposure_sign")(Number(v))} options={[["1", "Larga en el subyacente"], ["-1", "Corta en el subyacente"]]} />
              <Num label="Strike put" value={m.k_put} onChange={set("k_put")} />
              <Num label="Strike call" value={m.k_call} onChange={set("k_call")} />
              <Num label="K1 (alas/straddle)" value={m.k1} onChange={set("k1")} />
              <Num label="K2 (centro)" value={m.k2} onChange={set("k2")} />
              <Num label="K3" value={m.k3} onChange={set("k3")} />
              <label className="flex items-end gap-2 text-xs">
                <input type="checkbox" checked={m.include_stock} onChange={(e) => set("include_stock")(e.target.checked)} /> Incluir la exposición en el gráfico
              </label>
            </>
          )}
        </div>
        {mode === "manual" && (
          <div className="mt-3 space-y-2">
            {legs.map((l, i) => (
              <div key={i} className="grid grid-cols-2 gap-2 rounded border border-slate-200 p-2 md:grid-cols-9 dark:border-navy-700">
                <Select label={`Leg ${i + 1}`} value={l.kind} onChange={(v) => setLegs(legs.map((x, j) => (j === i ? { ...x, kind: v } : x)))} options={[["call", "Call"], ["put", "Put"], ["stock", "Acción"], ["future", "Futuro"]]} />
                <Num label="Cantidad (± contratos)" value={l.qty} onChange={(v) => setLegs(legs.map((x, j) => (j === i ? { ...x, qty: v } : x)))} />
                <Num label="Multiplicador" value={l.multiplier} onChange={(v) => setLegs(legs.map((x, j) => (j === i ? { ...x, multiplier: v } : x)))} />
                <Num label="Strike" value={l.strike} onChange={(v) => setLegs(legs.map((x, j) => (j === i ? { ...x, strike: v } : x)))} />
                <Num label="Venc. (años)" value={l.expiry_years} onChange={(v) => setLegs(legs.map((x, j) => (j === i ? { ...x, expiry_years: v } : x)))} />
                <Num label="Prima" value={l.premium} onChange={(v) => setLegs(legs.map((x, j) => (j === i ? { ...x, premium: v } : x)))} />
                <Select label="Origen prima" value={l.premium_origin} onChange={(v) => setLegs(legs.map((x, j) => (j === i ? { ...x, premium_origin: v } : x)))} options={[["supuesto_del_usuario", "Supuesto"], ["observado_fuente_oficial", "Oficial"], ["observado_proveedor_secundario", "Proveedor"], ["resultado_de_modelo", "Teórica"]]} />
                <Num label="Precio entrada (acción/futuro)" value={l.entry_price} onChange={(v) => setLegs(legs.map((x, j) => (j === i ? { ...x, entry_price: v } : x)))} />
                <button className="btn-ghost self-end" onClick={() => setLegs(legs.filter((_, j) => j !== i))}>Quitar</button>
              </div>
            ))}
            <button className="btn-ghost" onClick={() => setLegs([...legs, emptyLeg()])}>+ Agregar leg</button>
          </div>
        )}
        <button className="btn mt-3" onClick={go} disabled={busy}>
          Construir y validar
        </button>
        <ErrorBox error={error} />
      </Card>
      {r && (
        <>
          <Card title={r.strategy.name} className="mt-4" actions={<RiskTag fn={r.strategy.economic_function} label={r.strategy.economic_function_label} />}>
            <p className="text-sm">{r.strategy.description}</p>
            {r.strategy.warnings.map((w: string, i: number) => <Notice key={i} tone="warn">{w}</Notice>)}
            <Plot data={curves} layout={{ shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 0, y1: 0, line: { color: "#94A3B8" } }], xaxis: { title: "Precio del subyacente" }, yaxis: { title: overlay ? "Resultado combinado" : "P&L del overlay" } }} height={360} />
            <p className="text-xs">Costo inicial neto: <b>{money(r.strategy.initial_cost)}</b> · Puntos de equilibrio (overlay): {r.breakevens.map((b: number) => num(b)).join(", ") || "—"}</p>
            <Table rows={r.strategy.legs.map((l: any) => ({ tipo: l.kind, cantidad: l.qty, multiplicador: l.multiplier, strike: l.strike ?? "—", vencimiento: l.expiry_years, prima: l.premium === null ? "—" : num(l.premium, 4), origen: l.premium_origin }))} fmt={{ origen: (v) => <OriginTag origin={v} /> }} />
            <ul className="mt-2 list-disc pl-5 text-xs text-slate-500">{r.notes.map((n: string) => <li key={n}>{n}</li>)}</ul>
            <AuditInfo calc={data} />
          </Card>
        </>
      )}
    </>
  );
}
