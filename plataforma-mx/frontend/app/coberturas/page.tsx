"use client";
import { useEffect, useState } from "react";
import { ComparisonMatrix } from "@/components/ScenarioMatrix";
import { AuditInfo, Card, ErrorBox, Notice, Num, PageHeader, Select, Table, Text, useRun } from "@/components/ui";
import { api, Calc } from "@/lib/api";
import { useAsset } from "@/lib/asset";
import { EquityExposureForm, ExposureForm, RateExposureForm, saveExposure, scenarioRequest } from "@/lib/exposure";
import { money } from "@/lib/format";

const TEMPLATES: [string, string][] = [
  ["protective_put", "Protective Put"], ["collar", "Collar"], ["covered_call", "Covered Call"], ["short_futures", "Venta de futuros"],
  ["long_futures", "Compra de futuros"], ["protective_call", "Call protectora"], ["long_straddle", "Long Straddle"], ["long_strangle", "Long Strangle"],
  ["short_straddle", "Short Straddle"], ["short_strangle", "Short Strangle"],
];

export default function Coberturas() {
  const { asset } = useAsset();
  const [kind, setKind] = useState<"equity" | "rate">("equity");
  const [curves, setCurves] = useState<any[]>([]);
  const [futs, setFuts] = useState<any[]>([]);
  const [saved, setSaved] = useState<any[]>([]);
  const [eq, setEq] = useState<EquityExposureForm>({ kind: "equity", ticker: "", series: "", shares: 10000, declared: false, horizon_years: 0.25, r: NaN, r_origin: "", q: 0, sigma: null, sigma_origin: null, multiplier: 100, option_expiry_years: null, templates: ["protective_put", "collar", "covered_call", "short_futures", "long_straddle"], commission_per_contract: 0, futures_symbol: null, futures_price: null, futures_price_source: null, budget: null, objective: "Limitar pérdidas ante caídas del precio" });
  const [rt, setRt] = useState<RateExposureForm>({ kind: "rate", curve_id: 0, side: "pasivo", notional: 500_000_000, currency: "MXN", reference_rate: "TIIE_28", spread: 0.015, start: "", end: "", frequency: "28D", day_count: "ACT/360", rate_style: "term_fixed_in_advance", declared: false, model: "black76", vol: NaN, vol_origin: "supuesto_del_usuario", cap_strike: null, floor_strike: null });
  const { data, error, busy, run } = useRun<Calc>();
  useEffect(() => {
    api.get("/curves").then(setCurves).catch(() => {});
    api.get("/exposures").then(setSaved).catch(() => {});
  }, []);
  useEffect(() => {
    if (asset) {
      setEq((e) => ({ ...e, ticker: asset.ticker, series: asset.series }));
      api.get("/futures/contracts", { underlying: asset.ticker }).then(setFuts).catch(() => setFuts([]));
    }
  }, [asset]);
  const e: ExposureForm = kind === "equity" ? eq : rt;
  const go = async () => {
    saveExposure(e);
    await api.post("/exposures", { kind: kind === "equity" ? "equity" : rt.side === "pasivo" ? "rate_liability" : "rate_asset", declared: e.declared, payload: e }).catch(() => {});
    const { path, body } = scenarioRequest(e);
    run(() => api.post(path, body));
    api.get("/exposures").then(setSaved).catch(() => {});
  };
  const num0 = (v: any) => (v === null || v === undefined ? NaN : v);
  return (
    <>
      <PageHeader title="Coberturas" subtitle="Motor de evaluación: identifique la exposición (magnitud, moneda, horizonte, riesgo principal, presupuesto y objetivo), determine las estrategias compatibles y compárelas contra la posición sin cobertura bajo las mismas condiciones de mercado." />
      <Card title="1. Exposición">
        <div className="mb-3 flex gap-2">
          <button className={kind === "equity" ? "btn" : "btn-ghost"} onClick={() => setKind("equity")}>Accionaria</button>
          <button className={kind === "rate" ? "btn" : "btn-ghost"} onClick={() => setKind("rate")}>Tasa variable</button>
        </div>
        {kind === "equity" ? (
          <>
            {!asset && <Notice tone="warn">Seleccione el activo en el selector superior.</Notice>}
            <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
              <Text label="Activo" value={`${eq.ticker} ${eq.series}`} onChange={() => {}} />
              <Num label="Acciones (+ larga / − corta)" value={eq.shares} onChange={(v) => setEq({ ...eq, shares: v })} />
              <Select label="Naturaleza" value={eq.declared ? "1" : "0"} onChange={(v) => setEq({ ...eq, declared: v === "1" })} options={[["0", "Hipotética"], ["1", "Real declarada"]]} />
              <Num label="Horizonte (años)" value={eq.horizon_years} onChange={(v) => setEq({ ...eq, horizon_years: v })} />
              <Num label="Tasa libre de riesgo r" value={eq.r} onChange={(v) => setEq({ ...eq, r: v })} />
              <Text label="Fuente/origen de r" value={eq.r_origin} onChange={(v) => setEq({ ...eq, r_origin: v })} />
              <Num label="Dividendo continuo q" value={eq.q} onChange={(v) => setEq({ ...eq, q: v })} />
              <Num label="σ (vacío = histórica 252 sesiones)" value={num0(eq.sigma)} onChange={(v) => setEq({ ...eq, sigma: Number.isFinite(v) ? v : null, sigma_origin: Number.isFinite(v) ? "supuesto_del_usuario" : null })} />
              <Num label="Multiplicador contratos" value={eq.multiplier} onChange={(v) => setEq({ ...eq, multiplier: v })} />
              <Num label="Vencimiento opciones (años; vacío = horizonte)" value={num0(eq.option_expiry_years)} onChange={(v) => setEq({ ...eq, option_expiry_years: Number.isFinite(v) ? v : null })} />
              <Num label="Comisión por contrato" value={eq.commission_per_contract} onChange={(v) => setEq({ ...eq, commission_per_contract: v })} />
              <Num label="Presupuesto de cobertura (MXN)" value={num0(eq.budget)} onChange={(v) => setEq({ ...eq, budget: Number.isFinite(v) ? v : null })} />
              <Select label="Futuro listado (opcional)" value={eq.futures_symbol ?? ""} onChange={(v) => setEq({ ...eq, futures_symbol: v || null })} options={[["", "Teórico por acarreo"], ...futs.map((f) => [f.symbol, `${f.symbol} ${f.expiry}`] as [string, string])]} />
              {eq.futures_symbol && (
                <>
                  <Num label="Precio del futuro observado" value={num0(eq.futures_price)} onChange={(v) => setEq({ ...eq, futures_price: Number.isFinite(v) ? v : null })} />
                  <Text label="Fuente del precio" value={eq.futures_price_source ?? ""} onChange={(v) => setEq({ ...eq, futures_price_source: v })} />
                </>
              )}
              <Text label="Objetivo de protección" value={eq.objective} onChange={(v) => setEq({ ...eq, objective: v })} />
            </div>
            <div className="mt-2 flex flex-wrap gap-3 text-xs">
              {TEMPLATES.map(([k, l]) => (
                <label key={k} className="flex items-center gap-1">
                  <input type="checkbox" checked={eq.templates.includes(k)} onChange={(ev) => setEq({ ...eq, templates: ev.target.checked ? [...eq.templates, k] : eq.templates.filter((x) => x !== k) })} /> {l}
                </label>
              ))}
            </div>
          </>
        ) : (
          <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
            <Select label="Curva" value={String(rt.curve_id || "")} onChange={(v) => setRt({ ...rt, curve_id: Number(v) })} options={[["", "—"], ...curves.map((c) => [String(c.id), `#${c.id} ${c.name} ${c.curve_date}`] as [string, string])]} />
            <Select label="Tipo" value={rt.side} onChange={(v) => setRt({ ...rt, side: v as any })} options={[["pasivo", "Pasivo a tasa variable"], ["activo", "Activo a tasa variable"]]} />
            <Select label="Naturaleza" value={rt.declared ? "1" : "0"} onChange={(v) => setRt({ ...rt, declared: v === "1" })} options={[["0", "Hipotética"], ["1", "Real declarada"]]} />
            <Num label="Nocional" value={rt.notional} onChange={(v) => setRt({ ...rt, notional: v })} />
            <Text label="Tasa de referencia" value={rt.reference_rate} onChange={(v) => setRt({ ...rt, reference_rate: v })} />
            <Num label="Margen contractual (decimal)" value={rt.spread} onChange={(v) => setRt({ ...rt, spread: v })} />
            <Text label="Inicio" type="date" value={rt.start} onChange={(v) => setRt({ ...rt, start: v })} />
            <Text label="Fin" type="date" value={rt.end} onChange={(v) => setRt({ ...rt, end: v })} />
            <Select label="Periodicidad" value={rt.frequency} onChange={(v) => setRt({ ...rt, frequency: v })} options={["28D", "91D", "182D", "1M", "3M", "6M"].map((x) => [x, x])} />
            <Select label="Base de días" value={rt.day_count} onChange={(v) => setRt({ ...rt, day_count: v })} options={["ACT/360", "ACT/365F", "30/360"].map((x) => [x, x])} />
            <Select label="Estilo de tasa" value={rt.rate_style} onChange={(v) => setRt({ ...rt, rate_style: v })} options={[["term_fixed_in_advance", "Fijada al inicio"], ["compounded_in_arrears", "Compuesta en atraso"]]} />
            <Select label="Modelo" value={rt.model} onChange={(v) => setRt({ ...rt, model: v })} options={[["black76", "Black-76"], ["bachelier", "Bachelier"]]} />
            <Num label="σ (supuesto)" value={rt.vol} onChange={(v) => setRt({ ...rt, vol: v })} />
            <Num label="Strike cap (vacío = por perfil)" value={num0(rt.cap_strike)} onChange={(v) => setRt({ ...rt, cap_strike: Number.isFinite(v) ? v : null })} />
            <Num label="Strike floor (vacío = por perfil)" value={num0(rt.floor_strike)} onChange={(v) => setRt({ ...rt, floor_strike: Number.isFinite(v) ? v : null })} />
          </div>
        )}
        <button className="btn mt-3" onClick={go} disabled={busy}>
          {busy ? "Evaluando…" : "2. Evaluar alternativas compatibles"}
        </button>
        <ErrorBox error={error} />
      </Card>
      {data && (
        <Card title="3. Matriz comparativa" className="mt-4">
          <p className="mb-2 text-xs">
            Riesgo principal: <b>{data.result.exposure.main_risk}</b> · {data.result.n_evaluations} evaluaciones (perfiles × alternativas × 5 escenarios)
            {data.result.exposure.value !== undefined && <> · Valor de la exposición: {money(data.result.exposure.value)} · Spot: {data.result.exposure.spot} ({data.result.exposure.spot_provenance?.type} {String(data.result.exposure.spot_provenance?.date ?? "")})</>}
          </p>
          <ComparisonMatrix result={data.result} />
          <ul className="mt-2 list-disc pl-5 text-[11px] text-slate-500">{data.result.method_notes.map((n: string) => <li key={n}>{n}</li>)}</ul>
          <Notice>Para editar choques y preferencias por perfil, ver gráficos y pedir interpretaciones, abra «Perfiles y escenarios»: utiliza esta misma exposición.</Notice>
          <AuditInfo calc={data} />
        </Card>
      )}
      <Card title="Exposiciones registradas" className="mt-4">
        <Table rows={saved.slice(0, 20).map((s) => ({ id: s.id, tipo: s.kind, naturaleza: s.declared ? "real declarada" : "hipotética", detalle: s.kind === "equity" ? `${s.payload.ticker} ${s.payload.series} ${s.payload.shares} acc.` : `${s.payload.side} ${money(s.payload.notional)} ${s.payload.reference_rate}+${s.payload.spread}`, fecha: String(s.created_at).slice(0, 19) }))} />
      </Card>
    </>
  );
}
