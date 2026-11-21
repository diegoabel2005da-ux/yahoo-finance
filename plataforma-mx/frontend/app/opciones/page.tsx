"use client";
import { useEffect, useState } from "react";
import Plot from "@/components/Plot";
import { AuditInfo, Card, ErrorBox, Notice, Num, OriginTag, PageHeader, Select, Stat, Table, Text, Upload, useRun } from "@/components/ui";
import { api, Calc } from "@/lib/api";
import { useAsset } from "@/lib/asset";
import { money, num, pct } from "@/lib/format";

export default function Opciones() {
  const { asset } = useAsset();
  const [contracts, setContracts] = useState<any[]>([]);
  const load = () => api.get("/options/contracts", { underlying: asset?.ticker }).then(setContracts).catch(() => setContracts([]));
  useEffect(() => {
    load();
  }, [asset]);
  const [o, setO] = useState<any>({ kind: "call", side: "long", S: NaN, K: NaN, T: 0.25, r: NaN, sigma: NaN, q: 0, style: "europea", steps: 200, tree_steps: 5, sigma_origin: "supuesto_del_usuario", observed_premium: NaN, observed_premium_origin: "", contracts: 1, multiplier: 100, divs: "" });
  const set = (k: string) => (v: any) => setO({ ...o, [k]: v });
  const { data, error, busy, run } = useRun<Calc>();
  const go = () => {
    const divs = o.divs.split(";").map((s: string) => s.split(",").map(Number)).filter((p: number[]) => p.length === 2 && p.every(Number.isFinite));
    run(() => api.post("/options/value", { ...o, discrete_dividends: divs, observed_premium: Number.isFinite(o.observed_premium) ? o.observed_premium : null, observed_premium_origin: o.observed_premium_origin || null }));
  };
  const r = data?.result;
  const g = r?.bsm;
  return (
    <>
      <PageHeader title="Opciones" subtitle="Black-Scholes-Merton con dividendos continuos, Cox-Ross-Rubinstein (europeas y americanas, árbol y convergencia), volatilidad implícita de primas observadas y posiciones básicas." />
      <Card title={`Series de opciones importadas ${asset ? `— ${asset.ticker}` : ""}`}>
        {contracts.length ? (
          <Table rows={contracts.map((x) => ({ símbolo: x.symbol, tipo: x.option_type, strike: x.strike, vencimiento: x.expiry, multiplicador: x.multiplier, estilo: x.style, liquidación: x.settlement, fuente: x.source }))} />
        ) : (
          <Notice tone="warn">Sin series importadas. Se puede valorar una opción teórica, pero no se presentará como contrato listado.</Notice>
        )}
        <div className="mt-3">
          <Upload endpoint="/options/contracts/import" label="Series de opciones (MexDer)" template="option_contracts_template.csv" onDone={load} />
        </div>
      </Card>
      <Card title="Valuación" className="mt-4">
        <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
          <Select label="Contrato listado" value="" onChange={(v) => { const k = contracts.find((x) => x.symbol === v); if (k) setO({ ...o, kind: k.option_type, K: Number(k.strike), style: k.style, multiplier: Number(k.multiplier), T: Math.max((new Date(k.expiry).getTime() - Date.now()) / (365 * 864e5), 0.0001) }); }} options={[["", "—"], ...contracts.map((x) => [x.symbol, x.symbol] as [string, string])]} />
          <Select label="Tipo" value={o.kind} onChange={set("kind")} options={[["call", "Call"], ["put", "Put"]]} />
          <Select label="Posición" value={o.side} onChange={set("side")} options={[["long", "Larga"], ["short", "Corta"]]} />
          <Select label="Estilo" value={o.style} onChange={set("style")} options={[["europea", "Europea"], ["americana", "Americana"]]} />
          <Num label="Spot S" value={o.S} onChange={set("S")} />
          <Num label="Strike K" value={o.K} onChange={set("K")} />
          <Num label="T (años)" value={o.T} onChange={set("T")} />
          <Num label="r (continua)" value={o.r} onChange={set("r")} />
          <Num label="σ" value={o.sigma} onChange={set("sigma")} />
          <Select label="Origen de σ" value={o.sigma_origin} onChange={set("sigma_origin")} options={[["supuesto_del_usuario", "Supuesto del analista"], ["volatilidad_historica", "Histórica (estimación)"], ["volatilidad_implicita_observada", "Implícita de prima observada"]]} />
          <Num label="q (dividendo continuo)" value={o.q} onChange={set("q")} />
          <Text label="Dividendos discretos (t,D; t,D)" value={o.divs} onChange={set("divs")} placeholder="0.1,2.5" />
          <Num label="Pasos CRR" value={o.steps} onChange={set("steps")} step="1" />
          <Num label="Pasos árbol visible (≤12)" value={o.tree_steps} onChange={set("tree_steps")} step="1" />
          <Num label="Contratos" value={o.contracts} onChange={set("contracts")} />
          <Num label="Multiplicador" value={o.multiplier} onChange={set("multiplier")} />
          <Num label="Prima observada (opcional)" value={o.observed_premium} onChange={set("observed_premium")} />
          <Select label="Origen de la prima" value={o.observed_premium_origin} onChange={set("observed_premium_origin")} options={[["", "—"], ["observado_fuente_oficial", "Oficial (MexDer)"], ["observado_proveedor_secundario", "Proveedor secundario"]]} />
        </div>
        <button className="btn mt-3" onClick={go} disabled={busy}>
          Valorar
        </button>
        <ErrorBox error={error} />
      </Card>
      {r && (
        <>
          <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-6">
            <Stat label="Prima teórica" value={num(r.theoretical_premium.value, 4)} sub={<OriginTag origin="resultado_de_modelo" />} />
            {r.observed_premium && <Stat label="Prima observada" value={num(r.observed_premium.value, 4)} sub={<OriginTag origin={r.observed_premium.origin} />} />}
            {r.implied_vol && <Stat label="Volatilidad implícita" value={pct(r.implied_vol.implied_vol)} sub={r.implied_vol.model} />}
            <Stat label={`CRR (${r.crr.steps} pasos, ${r.crr.style})`} value={num(r.crr.price, 4)} sub={`u=${num(r.crr.u, 4)} d=${num(r.crr.d, 4)} p=${num(r.crr.p, 4)}`} />
            <Stat label="Punto de equilibrio" value={num(r.position.breakeven, 4)} />
            <Stat label="Pérdida máxima" value={r.position.unbounded_loss ? "ilimitada" : money(r.position.max_loss)} sub={r.position.requires_margin ? "requiere garantías" : ""} />
          </div>
          {g && (
            <Card title="Griegas (BSM)" className="mt-4">
              <Table rows={[{ delta: num(g.delta, 4), gamma: num(g.gamma, 5), "theta/día": num(g.theta_per_day, 4), "vega / 1 %": num(g.vega_per_pct, 4), "rho / 1 %": num(g.rho_per_pct, 4), d1: num(g.d1, 4), d2: num(g.d2, 4) }]} />
            </Card>
          )}
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <Card title="Resultado: al vencimiento vs revaluación previa">
              <Plot data={[{ x: r.position.payoff_at_expiry.map((p: any) => p.S), y: r.position.payoff_at_expiry.map((p: any) => p.pnl), name: "Al vencimiento (payoff)", line: { color: "#0B1F3A" } }, ...(r.position.value_before_expiry ? [{ x: r.position.value_before_expiry.map((p: any) => p.S), y: r.position.value_before_expiry.map((p: any) => p.pnl), name: "Antes del vencimiento (T/2, BSM)", line: { color: "#14B8A6", dash: "dash" } }] : [])]} height={300} />
              <p className="text-xs text-slate-500">{r.position.note}</p>
            </Card>
            <Card title="Convergencia CRR">
              <Table rows={r.convergence.rows.map((x: any) => ({ pasos: x.steps, precio: num(x.price, 6), "dif. vs BSM": x.diff_vs_bsm === null ? "n/a (americana)" : num(x.diff_vs_bsm, 6) }))} />
            </Card>
          </div>
          {r.tree && (
            <Card title={`Árbol binomial (${r.tree.steps} pasos) — precio / valor`} className="mt-4">
              <div className="overflow-auto">
                <div className="flex gap-3 font-mono text-[10px]">
                  {r.tree.price_tree.map((col: number[], i: number) => (
                    <div key={i} className="flex flex-col justify-center gap-1">
                      {col.map((s: number, j: number) => {
                        const early = r.tree.early_exercise_nodes?.some((e: any) => e.step === i && e.node === j);
                        return (
                          <div key={j} className={`rounded border px-1 ${early ? "border-amber-500 bg-amber-50 dark:bg-amber-950" : "border-slate-200 dark:border-navy-700"}`}>
                            {num(s, 2)}
                            <br />
                            <b>{num(r.tree.value_tree[i][j], 3)}</b>
                          </div>
                        );
                      })}
                    </div>
                  ))}
                </div>
              </div>
              <p className="mt-1 text-xs text-slate-500">Nodos resaltados: ejercicio anticipado óptimo. {r.tree.notes?.join(" ")}</p>
            </Card>
          )}
          <AuditInfo calc={data} />
        </>
      )}
    </>
  );
}
