"use client";
import { useMemo, useState } from "react";
import Plot from "./Plot";
import { RiskTag, Select, Table } from "./ui";
import { money, pct, SCENARIOS, SCEN_LABEL } from "@/lib/format";

/** Valor principal de un escenario: P&L combinado (acciones) o VP neto (tasas). */
export const mainValue = (s: any) => s.combined_pnl ?? s.net_pv;

const CRITERIA: [string, string][] = [
  ["stress_pnl", "Mejor resultado en estrés severo"],
  ["cost", "Menor costo inicial"],
  ["base_pnl", "Mejor resultado base"],
  ["upside", "Mejor resultado favorable extremo"],
  ["protection_stress", "Mayor protección en estrés"],
];

function keyFor(r: any, c: string) {
  const s = r.scenarios;
  if (c === "stress_pnl") return mainValue(s.estres_adverso_severo);
  if (c === "cost") return -r.initial_cost;
  if (c === "base_pnl") return mainValue(s.base);
  if (c === "upside") return mainValue(s.favorable_extremo);
  return s.estres_adverso_severo.protection_ratio ?? -1e18;
}

export function ComparisonMatrix({ result }: { result: any }) {
  const profiles = Array.from(new Set(result.evaluations.map((r: any) => r.profile))) as string[];
  const [profile, setProfile] = useState(profiles[0]);
  const [crit, setCrit] = useState("stress_pnl");
  const rows = useMemo(() => result.evaluations.filter((r: any) => r.profile === profile).sort((a: any, b: any) => keyFor(b, crit) - keyFor(a, crit)), [result, profile, crit]);
  const isEq = "combined_pnl" in result.evaluations[0].scenarios.base;
  return (
    <>
      <div className="mb-2 flex flex-wrap gap-2">
        <div className="w-48"><Select label="Perfil" value={profile} onChange={setProfile} options={profiles.map((p) => [p, p])} /></div>
        <div className="w-72"><Select label="Ordenar por (criterio explícito)" value={crit} onChange={setCrit} options={CRITERIA} /></div>
      </div>
      <div className="overflow-auto">
        <table className="tbl">
          <thead>
            <tr>
              {["Alternativa", "Función económica", "Costo neto", "Costo %", ...SCENARIOS.map((k) => SCEN_LABEL[k]), "Protección (estrés)", isEq ? "Participación alza" : "Mejora vs sin cob. (estrés)", "Restricciones del perfil", "Riesgos no cubiertos (estrés)"].map((h) => <th key={h}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((r: any) => (
              <tr key={r.strategy}>
                <td className="font-medium">{r.strategy}</td>
                <td><RiskTag fn={r.economic_function} label={r.economic_function_label} /></td>
                <td>{money(r.initial_cost)}</td>
                <td>{pct(r.initial_cost_pct)}</td>
                {SCENARIOS.map((k) => {
                  const v = mainValue(r.scenarios[k]);
                  return <td key={k} className={v < 0 ? "text-red-700 dark:text-red-400" : ""}>{money(v)}</td>;
                })}
                <td>{pct(r.scenarios.estres_adverso_severo.protection_ratio)}</td>
                <td>{isEq ? pct(r.upside_participation) : money(r.scenarios.estres_adverso_severo.vs_unhedged)}</td>
                <td className="text-[10px]">{Object.entries(r.constraints ?? {}).filter(([, v]) => v !== null).map(([k, v]) => `${k}: ${v ? "✓" : "✗"}`).join(" · ")}</td>
                <td className="max-w-xs text-[10px]">{(r.scenarios.estres_adverso_severo.unhedged_risks ?? []).join("; ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-[11px] text-slate-500">{isEq ? "Valores: P&L combinado (exposición + derivados) al horizonte." : "Valores: VP neto de flujos de intereses y del derivado menos prima, en la curva de cada escenario."} Orden por criterio cuantitativo visible; no se usan puntuaciones opacas.</p>
    </>
  );
}

export function ScenarioCharts({ result }: { result: any }) {
  const profiles = Array.from(new Set(result.evaluations.map((r: any) => r.profile))) as string[];
  const strategies = Array.from(new Set(result.evaluations.map((r: any) => r.strategy))) as string[];
  const [profile, setProfile] = useState(profiles[0]);
  const [pick, setPick] = useState<string[]>(strategies.slice(0, 3));
  const rows = result.evaluations.filter((r: any) => r.profile === profile && pick.includes(r.strategy));
  const palette = ["#94A3B8", "#0B1F3A", "#14B8A6", "#2563EB", "#A855F7", "#F59E0B", "#E11D48"];
  const isEq = "combined_pnl" in result.evaluations[0].scenarios.base;
  return (
    <>
      <div className="mb-2 flex flex-wrap items-end gap-3">
        <div className="w-48"><Select label="Perfil" value={profile} onChange={setProfile} options={profiles.map((p) => [p, p])} /></div>
        <div className="flex flex-wrap gap-2 text-xs">
          {strategies.map((s) => (
            <label key={s} className="flex items-center gap-1">
              <input type="checkbox" checked={pick.includes(s)} onChange={(e) => setPick(e.target.checked ? [...pick, s] : pick.filter((x) => x !== s))} /> {s}
            </label>
          ))}
        </div>
      </div>
      <Plot data={rows.map((r: any, i: number) => ({ type: "bar", name: r.strategy, x: SCENARIOS.map((k) => SCEN_LABEL[k]), y: SCENARIOS.map((k) => mainValue(r.scenarios[k])), marker: { color: palette[strategies.indexOf(r.strategy) % palette.length] } }))} layout={{ barmode: "group", yaxis: { title: isEq ? "P&L combinado" : "VP neto" } }} height={340} />
      <h3 className="mt-3 text-xs font-semibold uppercase text-slate-500">Comparación lado a lado</h3>
      <div className="grid grid-cols-1 gap-3 2xl:grid-cols-3">
        {rows.map((r: any) => (
          <div key={r.strategy} className="rounded border border-slate-200 p-2 text-xs dark:border-navy-700">
            <div className="mb-1 font-semibold">{r.strategy}</div>
            <RiskTag fn={r.economic_function} label={r.economic_function_label} />
            <Table
              rows={SCENARIOS.map((k) => {
                const s = r.scenarios[k];
                return isEq
                  ? { escenario: SCEN_LABEL[k], precio: s.S_final?.toFixed(2), exposición: money(s.exposure_pnl), derivado: money(s.derivative_pnl), combinado: money(s.combined_pnl), "vs base": money(s.vs_base), "delta rem.": Math.round(s.residual_delta_shares), valuación: s.valuation }
                  : { escenario: SCEN_LABEL[k], "paralelo pb": s.parallel_bp, "VP exposición": money(s.pv_exposure), "VP derivado": money(s.pv_derivative_flows), "VP neto": money(s.net_pv), "MTM tras choque": money(s.derivative_mtm_after_shock), "tasa efectiva máx": pct(s.max_effective_rate) };
              })}
            />
          </div>
        ))}
      </div>
    </>
  );
}

export function RateFlows({ result }: { result: any }) {
  const profiles = Array.from(new Set(result.evaluations.map((r: any) => r.profile))) as string[];
  const strategies = Array.from(new Set(result.evaluations.map((r: any) => r.strategy))) as string[];
  const [profile, setProfile] = useState(profiles[0]);
  const [strategy, setStrategy] = useState(strategies[1] ?? strategies[0]);
  const [scen, setScen] = useState("estres_adverso_severo");
  const row = result.evaluations.find((r: any) => r.profile === profile && r.strategy === strategy);
  const flows = row?.scenarios[scen].flows ?? [];
  return (
    <>
      <div className="mb-2 grid grid-cols-3 gap-2">
        <Select label="Perfil" value={profile} onChange={setProfile} options={profiles.map((p) => [p, p])} />
        <Select label="Alternativa" value={strategy} onChange={setStrategy} options={strategies.map((s) => [s, s])} />
        <Select label="Escenario" value={scen} onChange={setScen} options={SCENARIOS.map((k) => [k, SCEN_LABEL[k]])} />
      </div>
      <Plot data={[{ type: "bar", name: "Flujo exposición", x: flows.map((f: any) => f.payment_date), y: flows.map((f: any) => f.exposure_flow), marker: { color: "#94A3B8" } }, { type: "bar", name: "Flujo derivado", x: flows.map((f: any) => f.payment_date), y: flows.map((f: any) => f.derivative_flow), marker: { color: "#14B8A6" } }, { name: "Neto", x: flows.map((f: any) => f.payment_date), y: flows.map((f: any) => f.net_flow), line: { color: "#0B1F3A" } }]} layout={{ barmode: "relative" }} height={300} />
      <Table rows={flows.map((f: any) => ({ periodo: f.period, pago: f.payment_date, tasa: pct(f.rate, 4), estado: f.rate_state, exposición: money(f.exposure_flow), derivado: money(f.derivative_flow), neto: money(f.net_flow), "tasa efectiva": pct(f.effective_rate, 4) }))} />
      <p className="mt-1 text-[11px] text-slate-500">Flujos efectivamente pagaderos (no descontados) bajo la hipótesis de que las tasas realizadas igualan las forwards de la curva desplazada. La prima se paga al inicio y no se incluye en estos flujos.</p>
    </>
  );
}
