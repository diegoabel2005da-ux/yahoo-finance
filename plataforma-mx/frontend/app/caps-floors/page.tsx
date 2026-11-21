"use client";
import { useEffect, useState } from "react";
import Plot from "@/components/Plot";
import { AuditInfo, Card, ErrorBox, Notice, Num, OriginTag, PageHeader, Select, Stat, Table, Text, useRun } from "@/components/ui";
import { api, Calc } from "@/lib/api";
import { money, num, pct } from "@/lib/format";

export default function CapsFloors() {
  const [curves, setCurves] = useState<any[]>([]);
  useEffect(() => {
    api.get("/curves").then(setCurves).catch(() => {});
  }, []);
  const [f, setF] = useState<any>({ curve_id: "", kind: "cap", notional: 100_000_000, strike: NaN, start: "", end: "", frequency: "28D", day_count: "ACT/360", rate_style: "term_fixed_in_advance", model: "black76", vol: NaN, vol_origin: "supuesto_del_usuario", shift: 0, reference_rate: "TIIE_28", fixing_lag_bd: 1, observed_premium: NaN, observed_premium_origin: "", compare_normal_vol: NaN, compare_lognormal_vol: NaN, known_fixings: "", accrued: "" });
  const set = (k: string) => (v: any) => setF({ ...f, [k]: v });
  const { data, error, busy, run } = useRun<Calc>();
  const fin = (v: number) => (Number.isFinite(v) ? v : null);
  const parseMap = (s: string) => Object.fromEntries(s.split(";").map((p) => p.split("=")).filter((p) => p.length === 2).map(([k, v]) => [String(Number(k) - 1), Number(v)]));
  const go = () =>
    run(() =>
      api.post("/capfloor/value", {
        ...f, curve_id: Number(f.curve_id), observed_premium: fin(f.observed_premium), observed_premium_origin: f.observed_premium_origin || null,
        compare_normal_vol: fin(f.compare_normal_vol), compare_lognormal_vol: fin(f.compare_lognormal_vol),
        known_fixings: parseMap(f.known_fixings), accrued_factor: parseMap(f.accrued),
      })
    );
  const v = data?.result.valuation;
  const s = data?.result.sensitivities;
  return (
    <>
      <PageHeader title="Caps y floors" subtitle="Cap = suma de caplets, floor = suma de floorlets. Black-76 (lognormal, con desplazamiento opcional) o Bachelier (normal). Tasas fijadas al inicio o compuestas en atraso (TIIE de Fondeo)." />
      <Notice>
        Los caps/floors se modelan como instrumentos <b>OTC parametrizados</b>. No se afirma que coticen en MexDer. La prima calculada es <b>teórica</b>; sólo una prima observada con fuente permite calibrar volatilidad implícita.
      </Notice>
      <Card title="Definición del instrumento">
        <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
          <Select label="Curva (descuento y forwards)" value={f.curve_id} onChange={set("curve_id")} options={[["", "—"], ...curves.map((c) => [String(c.id), `#${c.id} ${c.name} ${c.curve_date}`] as [string, string])]} />
          <Select label="Tipo" value={f.kind} onChange={set("kind")} options={[["cap", "Cap"], ["floor", "Floor"]]} />
          <Num label="Nocional" value={f.notional} onChange={set("notional")} />
          <Num label="Strike (decimal)" value={f.strike} onChange={set("strike")} hint="p. ej. 0.085 = 8.5 %" />
          <Text label="Inicio" type="date" value={f.start} onChange={set("start")} />
          <Text label="Fin" type="date" value={f.end} onChange={set("end")} />
          <Select label="Periodicidad" value={f.frequency} onChange={set("frequency")} options={["28D", "91D", "182D", "1M", "3M", "6M"].map((x) => [x, x])} />
          <Select label="Base de días" value={f.day_count} onChange={set("day_count")} options={["ACT/360", "ACT/365F", "30/360"].map((x) => [x, x])} />
          <Select label="Tasa de referencia" value={f.rate_style} onChange={set("rate_style")} options={[["term_fixed_in_advance", "Fijada al inicio (p. ej. TIIE 28)"], ["compounded_in_arrears", "Overnight compuesta en atraso (TIIE de Fondeo)"]]} />
          <Text label="Código de referencia" value={f.reference_rate} onChange={set("reference_rate")} />
          <Select label="Modelo" value={f.model} onChange={set("model")} options={[["black76", "Black-76"], ["bachelier", "Bachelier (normal)"]]} />
          <Num label={f.model === "black76" ? "σ lognormal (decimal)" : "σ normal (decimal, 0.01 = 100 pb)"} value={f.vol} onChange={set("vol")} />
          <Select label="Origen de σ" value={f.vol_origin} onChange={set("vol_origin")} options={[["supuesto_del_usuario", "Hipotética del analista"], ["volatilidad_historica_tasas", "Histórica de tasas (estimación)"], ["volatilidad_implicita_observada", "Implícita de cotización real"]]} />
          {f.model === "black76" && <Num label="Desplazamiento (shift)" value={f.shift} onChange={set("shift")} />}
          <Num label="Rezago de fijación (días hábiles)" value={f.fixing_lag_bd} onChange={set("fixing_lag_bd")} step="1" />
          <Text label="Fijaciones conocidas (periodo=tasa;…)" value={f.known_fixings} onChange={set("known_fixings")} placeholder="1=0.0745" />
          <Text label="Factor devengado periodo en curso (periodo=factor)" value={f.accrued} onChange={set("accrued")} placeholder="1=1.0032" />
          <Num label="Prima observada (opcional)" value={f.observed_premium} onChange={set("observed_premium")} />
          <Select label="Origen de la prima" value={f.observed_premium_origin} onChange={set("observed_premium_origin")} options={[["", "—"], ["observado_fuente_oficial", "Cotización con fuente"], ["observado_proveedor_secundario", "Proveedor"]]} />
          <Num label="Comparar: σ normal" value={f.compare_normal_vol} onChange={set("compare_normal_vol")} />
          <Num label="Comparar: σ lognormal" value={f.compare_lognormal_vol} onChange={set("compare_lognormal_vol")} />
        </div>
        <button className="btn mt-3" onClick={go} disabled={busy || !f.curve_id}>
          Valorar
        </button>
        <ErrorBox error={error} />
      </Card>
      {v && (
        <>
          <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-6">
            <Stat label={`Valor teórico ${v.kind}`} value={money(v.value)} sub={<OriginTag origin={v.origin} />} />
            <Stat label="Valor / nocional" value={`${num(v.value_per_notional_bp, 2)} pb`} />
            <Stat label="PV01 paralelo" value={money(s.pv01_parallel)} sub="por +1 pb" />
            <Stat label="Vega" value={money(s.vega)} sub={s.vega_unit} />
            <Stat label="Theta (1 día)" value={money(s.theta_1d)} sub="forwards constantes" />
            <Stat label="Paridad: swap Σ NαP(F−K)" value={money(data.result.parity_swap_value)} sub="cap − floor" />
          </div>
          {v.warnings.map((w: string) => <Notice key={w} tone="warn">{w}</Notice>)}
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <Card title={`${v.kind === "cap" ? "Caplets" : "Floorlets"}: valor y forward por periodo`}>
              <Plot data={[{ type: "bar", x: v.components.map((c: any) => c.period), y: v.components.map((c: any) => c.value), name: "Valor", marker: { color: "#14B8A6" } }, { x: v.components.map((c: any) => c.period), y: v.components.map((c: any) => c.forward), name: "Forward", yaxis: "y2", line: { color: "#0B1F3A" } }]} layout={{ yaxis2: { overlaying: "y", side: "right", tickformat: ".2%" }, shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, yref: "y2", y0: f.strike, y1: f.strike, line: { dash: "dash", color: "#E11D48" } }] }} height={300} />
            </Card>
            <Card title="Sensibilidad por nodo (key-rate PV01)">
              <Plot data={[{ type: "bar", x: s.key_rate_pv01.map((k: any) => `${k.node_days}d`), y: s.key_rate_pv01.map((k: any) => k.pv01), marker: { color: "#0B1F3A" } }]} height={300} />
              <p className="text-xs text-slate-500">Pendiente: {money(s.slope_per_bp)}/pb · Curvatura: {money(s.curvature_per_bp)}/pb · Gamma: {num(s.gamma_per_bp2, 4)}/pb². {s.method}</p>
            </Card>
          </div>
          <Card title="Detalle de componentes" className="mt-4">
            <Table rows={v.components.map((c: any) => ({ periodo: c.period, inicio: c.accrual_start, fin: c.accrual_end, fijación: c.fixing_date, pago: c.payment_date, nocional: num(c.notional, 0), α: num(c.accrual, 6), tasa: pct(c.forward, 4), estado: c.rate_state, τ: num(c.tau, 4), σ: c.vol, DF: num(c.discount_factor, 8), valor: num(c.value) }))} />
            <p className="mt-1 text-xs text-slate-500">τ: tiempo de varianza. Para tasas compuestas en atraso se usa τ = t_s + (t_e − t_s)/3 (Lyashenko–Mercurio, vol constante); para fijadas al inicio, τ = t_fijación.</p>
          </Card>
          {data.result.implied_flat_vol && <Notice>Volatilidad plana implícita de la prima observada: {pct(data.result.implied_flat_vol.implied_flat_vol, 3)} ({data.result.implied_flat_vol.model})</Notice>}
          {data.result.model_comparison && (
            <Card title="Comparación de modelos" className="mt-4">
              <p className="text-sm">Black-76: {money(data.result.model_comparison.black76)} · Bachelier: {money(data.result.model_comparison.bachelier)} · Diferencia: {money(data.result.model_comparison.difference)}</p>
              <p className="mt-1 text-xs text-slate-500">{data.result.model_comparison.explanation}</p>
            </Card>
          )}
          <AuditInfo calc={data} />
        </>
      )}
    </>
  );
}
