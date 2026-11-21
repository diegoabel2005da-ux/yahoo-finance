"use client";
import { useMemo, useState } from "react";
import Plot from "@/components/Plot";
import RequireAsset from "@/components/RequireAsset";
import { AuditInfo, Card, ErrorBox, Notice, Num, PageHeader, Select, Table, useRun } from "@/components/ui";
import { api, Calc } from "@/lib/api";
import { num, pct } from "@/lib/format";

function Technical({ ticker, series }: { ticker: string; series: string }) {
  const [p, setP] = useState({ roc_n: 12, williams_n: 14, stoch_k: 14, stoch_d: 3, stoch_mode: "lento", stoch_smooth: 3, fib_mode: "auto", fib_high: NaN, fib_low: NaN, fib_trend: "alcista", pivot_left: 5, pivot_right: 5, freq: "diaria" });
  const set = (k: string) => (v: any) => setP({ ...p, [k]: v });
  const { data, error, busy, run } = useRun<Calc>();
  const go = () =>
    run(() =>
      api.post("/technical", {
        ticker, series, ...p, rsi_periods: [9, 14, 25], sma: [20, 50, 200],
        fib_high: Number.isFinite(p.fib_high) ? p.fib_high : null, fib_low: Number.isFinite(p.fib_low) ? p.fib_low : null,
      })
    );
  const r = data?.result;
  const x = r?.rows.map((d: any) => d.date) ?? [];
  const col = (k: string) => r?.rows.map((d: any) => d[k]);
  const fibShapes = useMemo(
    () => (r?.fibonacci?.levels ?? []).filter((l: any) => l.kind === "retroceso").map((l: any) => ({ type: "line", xref: "paper", x0: 0, x1: 1, y0: l.price, y1: l.price, line: { dash: "dot", width: 1, color: "#14B8A6" } })),
    [r]
  );
  return (
    <>
      <Card title="Parámetros de indicadores">
        <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
          <Select label="Temporalidad" value={p.freq} onChange={set("freq")} options={["diaria", "semanal", "mensual"].map((f) => [f, f])} />
          <Num label="ROC n" value={p.roc_n} onChange={set("roc_n")} step="1" />
          <Num label="Williams n" value={p.williams_n} onChange={set("williams_n")} step="1" />
          <Num label="Estocástico %K" value={p.stoch_k} onChange={set("stoch_k")} step="1" />
          <Num label="Estocástico %D" value={p.stoch_d} onChange={set("stoch_d")} step="1" />
          <Select label="Modalidad" value={p.stoch_mode} onChange={set("stoch_mode")} options={[["lento", "Lento"], ["rapido", "Rápido"]]} />
          <Num label="Suavizado %K (lento)" value={p.stoch_smooth} onChange={set("stoch_smooth")} step="1" />
          <Select label="Fibonacci" value={p.fib_mode} onChange={set("fib_mode")} options={[["auto", "Automático (pivotes)"], ["manual", "Anclas manuales"]]} />
          {p.fib_mode === "manual" ? (
            <>
              <Num label="Ancla máxima" value={p.fib_high} onChange={set("fib_high")} />
              <Num label="Ancla mínima" value={p.fib_low} onChange={set("fib_low")} />
              <Select label="Tendencia" value={p.fib_trend} onChange={set("fib_trend")} options={[["alcista", "Alcista"], ["bajista", "Bajista"]]} />
            </>
          ) : (
            <>
              <Num label="Pivote: barras izq." value={p.pivot_left} onChange={set("pivot_left")} step="1" />
              <Num label="Pivote: barras der." value={p.pivot_right} onChange={set("pivot_right")} step="1" />
            </>
          )}
        </div>
        <button className="btn mt-3" onClick={go} disabled={busy}>
          {busy ? "Calculando…" : "Calcular indicadores"}
        </button>
        <ErrorBox error={error} />
      </Card>
      {r && (
        <>
          {r.warnings.map((w: string) => <Notice key={w} tone="warn">{w}</Notice>)}
          <Card title="Precio, medias móviles y Fibonacci" className="mt-4">
            <Plot data={[{ x, y: col("close"), name: "Cierre", line: { color: "#0B1F3A" } }, ...[20, 50, 200].map((n, i) => ({ x, y: col(`sma_${n}`), name: `SMA ${n}`, line: { width: 1, color: ["#14B8A6", "#F59E0B", "#A855F7"][i] } }))]} layout={{ shapes: fibShapes }} height={340} />
            {r.fibonacci && (
              <p className="text-xs text-slate-500">
                Fibonacci ({r.fibonacci.method}): {r.fibonacci.trend}; anclas {num(r.fibonacci.anchor_high.price)} / {num(r.fibonacci.anchor_low.price)} — niveles: {r.fibonacci.levels.map((l: any) => `${(l.ratio * 100).toFixed(1)}%=${num(l.price)}`).join(" · ")}
              </p>
            )}
          </Card>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <Card title="RSI 9 · 14 · 25 (Wilder)">
              <Plot data={[9, 14, 25].map((n, i) => ({ x, y: col(`rsi_${n}`), name: `RSI ${n}`, line: { width: 1.2, color: ["#E11D48", "#0B1F3A", "#14B8A6"][i] } }))} layout={{ yaxis: { range: [0, 100] }, shapes: [70, 30].map((y) => ({ type: "line", xref: "paper", x0: 0, x1: 1, y0: y, y1: y, line: { dash: "dash", width: 1, color: "#94A3B8" } })) }} height={260} />
            </Card>
            <Card title={`ROC(${p.roc_n})`}>
              <Plot data={[{ x, y: col("roc"), name: "ROC %", line: { color: "#0B1F3A" } }]} layout={{ shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 0, y1: 0, line: { color: "#94A3B8" } }] }} height={260} />
              <p className="text-xs text-slate-500">Cruces de cero recientes: {r.roc_zero_crossings.map((c: any) => `${c.date.slice(0, 10)} (${c.direction})`).join(", ") || "—"}</p>
            </Card>
            {r.rows[0]?.williams_r !== undefined && (
              <>
                <Card title={`Williams %R(${p.williams_n})`}>
                  <Plot data={[{ x, y: col("williams_r"), name: "%R", line: { color: "#0B1F3A" } }]} layout={{ yaxis: { range: [-100, 0] }, shapes: [-20, -80].map((y) => ({ type: "line", xref: "paper", x0: 0, x1: 1, y0: y, y1: y, line: { dash: "dash", width: 1, color: "#94A3B8" } })) }} height={240} />
                </Card>
                <Card title={`Estocástico ${p.stoch_mode} (${p.stoch_k},${p.stoch_d})`}>
                  <Plot data={[{ x, y: col("stoch_k"), name: "%K", line: { color: "#0B1F3A" } }, { x, y: col("stoch_d"), name: "%D", line: { color: "#14B8A6" } }]} layout={{ yaxis: { range: [0, 100] } }} height={240} />
                </Card>
              </>
            )}
          </div>
          <p className="mt-2 text-xs text-slate-500">Metodología: {JSON.stringify(r.methodology)}. Zonas de referencia (70/30, −20/−80) son convenciones descriptivas, no señales.</p>
          <AuditInfo calc={data} />
        </>
      )}
    </>
  );
}

function DCF() {
  const [n, setN] = useState(5);
  const [base, setBase] = useState<any>({ base_revenue: NaN, tax_rate: 0.3, net_debt: NaN, shares_outstanding: NaN, minority_interest: 0, non_operating_assets: 0, terminal_growth: 0.035 });
  const [yr, setYr] = useState<any>({ revenue_growth: 0.05, ebit_margin: 0.18, da_pct_revenue: 0.05, capex_pct_revenue: 0.06, nwc_pct_revenue_change: 0.1 });
  const [capm, setCapm] = useState<any>({ rf: NaN, beta: NaN, erp: NaN, country_risk: 0, size_premium: 0 });
  const [wb, setWb] = useState<any>({ equity_value: NaN, debt_value: NaN, kd_pre_tax: NaN, tax_rate: 0.3 });
  const [wacc, setWacc] = useState<number>(NaN);
  const { data, error, busy, run } = useRun<Calc>();
  const go = () => {
    const arr = (v: number) => Array(n).fill(v);
    const inputs: any = { ...base, wacc: Number.isFinite(wacc) ? wacc : 0.1 };
    Object.keys(yr).forEach((k) => (inputs[k] = arr(yr[k])));
    const useCapm = Object.values(capm).every((v: any) => Number.isFinite(v)) && Object.values(wb).every((v: any) => Number.isFinite(v));
    if (!useCapm && !Number.isFinite(wacc)) return run(async () => { throw Object.assign(new Error("indique WACC o los insumos completos de CAPM/WACC"), { status: 422 }); });
    const w0 = Number.isFinite(wacc) ? wacc : 0.12;
    return run(() => api.post("/valuation/dcf", { inputs, capm: useCapm ? capm : null, wacc_build: useCapm ? wb : null, sensitivity_wacc: [w0 - 0.02, w0 - 0.01, w0, w0 + 0.01, w0 + 0.02], sensitivity_g: [base.terminal_growth - 0.01, base.terminal_growth, base.terminal_growth + 0.01] }));
  };
  const r = data?.result;
  return (
    <Card title="Valuación DCF (FCFF) — supuestos editables" className="mt-4">
      <Notice>Los insumos son supuestos del analista (o cifras de estados financieros verificados que usted capture). El valor resultante es teórico y no implica que el precio de mercado lo alcanzará.</Notice>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
        <Num label="Años de proyección" value={n} onChange={(v) => setN(Math.max(1, Math.min(15, v || 1)))} step="1" />
        <Num label="Ingresos base" value={base.base_revenue} onChange={(v) => setBase({ ...base, base_revenue: v })} />
        <Num label="Tasa impuestos" value={base.tax_rate} onChange={(v) => setBase({ ...base, tax_rate: v })} />
        <Num label="Deuda neta" value={base.net_debt} onChange={(v) => setBase({ ...base, net_debt: v })} />
        <Num label="Acciones en circulación" value={base.shares_outstanding} onChange={(v) => setBase({ ...base, shares_outstanding: v })} />
        <Num label="g terminal" value={base.terminal_growth} onChange={(v) => setBase({ ...base, terminal_growth: v })} />
        <Num label="Crecimiento ingresos (anual)" value={yr.revenue_growth} onChange={(v) => setYr({ ...yr, revenue_growth: v })} />
        <Num label="Margen EBIT" value={yr.ebit_margin} onChange={(v) => setYr({ ...yr, ebit_margin: v })} />
        <Num label="D&A / ingresos" value={yr.da_pct_revenue} onChange={(v) => setYr({ ...yr, da_pct_revenue: v })} />
        <Num label="CAPEX / ingresos" value={yr.capex_pct_revenue} onChange={(v) => setYr({ ...yr, capex_pct_revenue: v })} />
        <Num label="ΔCTN / Δingresos" value={yr.nwc_pct_revenue_change} onChange={(v) => setYr({ ...yr, nwc_pct_revenue_change: v })} />
        <Num label="Interés minoritario" value={base.minority_interest} onChange={(v) => setBase({ ...base, minority_interest: v })} />
      </div>
      <h3 className="mt-3 text-xs font-semibold uppercase text-slate-500">WACC: directo o por CAPM</h3>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
        <Num label="WACC directo" value={wacc} onChange={setWacc} />
        <Num label="rf" value={capm.rf} onChange={(v) => setCapm({ ...capm, rf: v })} />
        <Num label="β" value={capm.beta} onChange={(v) => setCapm({ ...capm, beta: v })} />
        <Num label="Prima de mercado" value={capm.erp} onChange={(v) => setCapm({ ...capm, erp: v })} />
        <Num label="Prima país" value={capm.country_risk} onChange={(v) => setCapm({ ...capm, country_risk: v })} />
        <Num label="Prima tamaño" value={capm.size_premium} onChange={(v) => setCapm({ ...capm, size_premium: v })} />
        <Num label="Valor capital (E)" value={wb.equity_value} onChange={(v) => setWb({ ...wb, equity_value: v })} />
        <Num label="Valor deuda (D)" value={wb.debt_value} onChange={(v) => setWb({ ...wb, debt_value: v })} />
        <Num label="Kd antes de impuestos" value={wb.kd_pre_tax} onChange={(v) => setWb({ ...wb, kd_pre_tax: v })} />
      </div>
      <button className="btn mt-3" onClick={go} disabled={busy}>
        Valuar
      </button>
      <ErrorBox error={error} />
      {r && (
        <div className="mt-3 space-y-3">
          {r.wacc_detail && <p className="text-xs">Ke = {pct(r.wacc_detail.ke)} · WACC = {pct(r.wacc_detail.wacc)}</p>}
          <Table rows={r.projection} />
          <p className="text-sm">
            VP explícito {num(r.pv_explicit)} · VP terminal {num(r.pv_terminal)} ({pct(r.terminal_weight)} del VE) · VE <b>{num(r.enterprise_value)}</b> · Capital <b>{num(r.equity_value)}</b> · Valor teórico por acción <b>{num(r.value_per_share)}</b>
          </p>
          {r.sensitivity && (
            <div>
              <h4 className="text-xs font-semibold uppercase text-slate-500">Sensibilidad valor por acción (WACC × g)</h4>
              <Table rows={r.sensitivity.wacc.map((w: number, i: number) => Object.fromEntries([["WACC", pct(w)], ...r.sensitivity.g.map((g: number, j: number) => [`g=${pct(g)}`, num(r.sensitivity.value_per_share[i][j])])]))} />
            </div>
          )}
          <p className="text-xs text-slate-500">{r.disclaimer}</p>
          <AuditInfo calc={data} />
        </div>
      )}
    </Card>
  );
}

export default function Analisis() {
  return (
    <>
      <PageHeader title="Análisis y valuación" subtitle="ROC, Williams %R, estocástico, RSI 9/14/25 (Wilder), Fibonacci y valuación fundamental DCF con WACC/CAPM y sensibilidades." />
      <RequireAsset>{(a) => <Technical {...a} />}</RequireAsset>
      <DCF />
    </>
  );
}
