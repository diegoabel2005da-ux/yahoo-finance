"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ComparisonMatrix, RateFlows, ScenarioCharts } from "@/components/ScenarioMatrix";
import { AuditInfo, Card, ErrorBox, Notice, PageHeader, Text, useRun } from "@/components/ui";
import { api, Calc } from "@/lib/api";
import { ExposureForm, loadExposure, scenarioRequest } from "@/lib/exposure";
import { SCENARIOS, SCEN_LABEL } from "@/lib/format";

const PREFS: [string, string][] = [
  ["max_loss_tolerance", "Pérdida máx. tolerada (fracción)"], ["hedge_budget", "Presupuesto de cobertura (fracción)"],
  ["put_moneyness", "Strike put / S0"], ["call_moneyness", "Strike call / S0"], ["hedge_ratio", "Razón de cobertura"],
  ["cap_strike_offset_bp", "Strike cap: forward + pb"], ["floor_strike_offset_bp", "Strike floor: forward + pb"],
];

export default function Escenarios() {
  const [exp, setExp] = useState<ExposureForm | null>(null);
  const [profiles, setProfiles] = useState<Record<string, any> | null>(null);
  const [versions, setVersions] = useState<Record<string, any>>({});
  const [vname, setVname] = useState("");
  const [q, setQ] = useState("¿Cómo se comparan las alternativas dentro del mismo escenario y qué riesgos persisten después de la cobertura?");
  const { data, error, busy, run } = useRun<Calc>();
  const ai = useRun<any>();
  useEffect(() => {
    setExp(loadExposure());
    api.get("/profiles/defaults").then((d) => {
      const { _scenarios, ...p } = d;
      setProfiles(p);
    });
    try {
      setVersions(JSON.parse(localStorage.getItem("profileVersions") || "{}"));
    } catch {}
  }, []);
  const isEq = exp?.kind === "equity";
  const shockKeys: [string, string, number][] = isEq
    ? [["equity_shocks", "Movimiento del precio (magnitud, %)", 100], ["equity_vol_shift", "Cambio de volatilidad (pts %)", 100]]
    : [["rate_shocks_bp", "Paralelo (pb, magnitud)", 1], ["rate_slope_bp", "Pendiente (pb)", 1], ["rate_curvature_bp", "Curvatura (pb)", 1]];
  const setShock = (p: string, k: string, s: string, v: number, scale: number) => setProfiles({ ...profiles!, [p]: { ...profiles![p], [k]: { ...profiles![p][k], [s]: v / scale } } });
  const setPref = (p: string, k: string, v: number) => setProfiles({ ...profiles!, [p]: { ...profiles![p], [k]: v } });
  const go = () => {
    if (!exp || !profiles) return;
    const { path, body } = scenarioRequest(exp, profiles);
    run(() => api.post(path, body));
  };
  const saveVersion = () => {
    if (!vname || !profiles) return;
    const v = { ...versions, [vname]: { profiles, exposure: exp, audit_id: data?.audit_id ?? null, saved: new Date().toISOString() } };
    setVersions(v);
    try {
      localStorage.setItem("profileVersions", JSON.stringify(v));
    } catch {}
  };
  return (
    <>
      <PageHeader title="Perfiles y escenarios" subtitle="Cinco escenarios prospectivos por cada combinación perfil × estrategia. Los perfiles son preferencias analíticas del simulador, no evaluaciones regulatorias de idoneidad. Los choques son hipótesis editables, sin probabilidades." />
      {!exp ? (
        <Notice tone="warn">
          Defina primero una exposición en <Link className="underline" href="/coberturas">Coberturas</Link>.
        </Notice>
      ) : (
        <Notice>
          Exposición: {exp.kind === "equity" ? `${exp.ticker} ${exp.series}, ${exp.shares} acciones (${exp.declared ? "real declarada" : "hipotética"})` : `${exp.side} a tasa variable ${exp.reference_rate} + ${exp.spread}, nocional ${exp.notional.toLocaleString("es-MX")}`}. Adverso/favorable se define respecto de esta exposición: {exp.kind === "equity" ? (exp.shares > 0 ? "adverso = caída del precio" : "adverso = alza del precio") : exp.side === "pasivo" ? "adverso = alza de tasas" : "adverso = baja de tasas"}.
        </Notice>
      )}
      {profiles && exp && (
        <Card title="Editor de perfiles y choques">
          <div className="overflow-auto">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Perfil</th>
                  <th>Variable</th>
                  {SCENARIOS.map((s) => <th key={s}>{SCEN_LABEL[s]}</th>)}
                </tr>
              </thead>
              <tbody>
                {Object.entries(profiles).map(([pk, p]: any) =>
                  shockKeys.map(([k, label, scale], i) => (
                    <tr key={pk + k}>
                      {i === 0 && <td rowSpan={shockKeys.length} className="align-top font-semibold" title={p.description}>{p.name}</td>}
                      <td>{label}</td>
                      {SCENARIOS.map((s) => (
                        <td key={s}>
                          <input className="input w-20" type="number" step="any" value={+(p[k][s] * scale).toFixed(4)} onChange={(e) => setShock(pk, k, s, Number(e.target.value), scale)} disabled={s === "base" && k !== "equity_vol_shift"} />
                        </td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <h3 className="mt-3 text-xs font-semibold uppercase text-slate-500">Preferencias y restricciones cuantificables</h3>
          <div className="overflow-auto">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Perfil</th>
                  {PREFS.map(([, l]) => <th key={l}>{l}</th>)}
                </tr>
              </thead>
              <tbody>
                {Object.entries(profiles).map(([pk, p]: any) => (
                  <tr key={pk}>
                    <td className="font-semibold">{p.name}</td>
                    {PREFS.map(([k]) => (
                      <td key={k}>
                        <input className="input w-24" type="number" step="any" value={p[k]} onChange={(e) => setPref(pk, k, Number(e.target.value))} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-1 text-[11px] text-slate-500">Dentro de cada perfil la misma condición de mercado se aplica a todas las estrategias. El perfil cambia su conjunto de choques y sus preferencias (strikes, razón de cobertura, límites), siempre de forma visible.</p>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <button className="btn" onClick={go} disabled={busy}>{busy ? "Simulando…" : "Simular matriz completa"}</button>
            <div className="w-56"><Text label="Nombre de versión" value={vname} onChange={setVname} /></div>
            <button className="btn-ghost" onClick={saveVersion} disabled={!vname}>Guardar versión</button>
            {Object.keys(versions).length > 0 && (
              <select className="input w-56" onChange={(e) => { const v = versions[e.target.value]; if (v) { setProfiles(v.profiles); if (v.exposure) setExp(v.exposure); } }} defaultValue="">
                <option value="">Cargar versión…</option>
                {Object.entries(versions).map(([k, v]: any) => <option key={k} value={k}>{k} ({String(v.saved).slice(0, 16)}{v.audit_id ? `, auditoría #${v.audit_id}` : ""})</option>)}
              </select>
            )}
          </div>
          <ErrorBox error={error} />
        </Card>
      )}
      {data && (
        <>
          <Card title={`Matriz perfil × estrategia × escenario (${data.result.n_evaluations} evaluaciones)`} className="mt-4">
            <ComparisonMatrix result={data.result} />
          </Card>
          <Card title="Gráficos y comparador" className="mt-4">
            <ScenarioCharts result={data.result} />
          </Card>
          {!isEq && (
            <Card title="Tablas de flujos por periodo" className="mt-4">
              <RateFlows result={data.result} />
            </Card>
          )}
          <Card title="Interpretación (IA explicativa)" className="mt-4">
            <Notice>El asistente recibe sólo los resultados estructurados de esta simulación (auditoría #{data.audit_id}). No genera primas, tasas, volatilidades ni probabilidades; las cifras de la respuesta se verifican contra el contexto.</Notice>
            <textarea className="input h-20" value={q} onChange={(e) => setQ(e.target.value)} />
            <button className="btn mt-2" onClick={() => ai.run(() => api.post("/ai/explain", { question: q, audit_id: data.audit_id }))} disabled={ai.busy}>
              {ai.busy ? "Interpretando…" : "Explicar"}
            </button>
            <ErrorBox error={ai.error} />
            {ai.data && (
              <div className="mt-2">
                <p className="mb-1 text-[11px] text-slate-500">Modo: {ai.data.mode}{ai.data.model ? ` (${ai.data.model})` : ""} · {ai.data.verified ? "cifras verificadas contra el contexto" : "contiene cifras no rastreables"} {ai.data.notice ? `· ${ai.data.notice}` : ""} {ai.data.llm_error ? `· error LLM: ${ai.data.llm_error}` : ""}</p>
                {ai.data.untraceable_numbers?.length > 0 && <Notice tone="warn">Cifras no rastreables: {ai.data.untraceable_numbers.join(", ")}</Notice>}
                <div className="whitespace-pre-wrap rounded border border-slate-200 p-3 text-sm dark:border-navy-700">{ai.data.text ?? "El modelo declinó responder."}</div>
              </div>
            )}
          </Card>
          <AuditInfo calc={data} />
        </>
      )}
    </>
  );
}
