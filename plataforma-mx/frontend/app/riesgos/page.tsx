"use client";
import { useState } from "react";
import RequireAsset from "@/components/RequireAsset";
import { AuditInfo, Card, ErrorBox, Num, PageHeader, Select, Stat, Table, Text, useRun } from "@/components/ui";
import { api, Calc } from "@/lib/api";
import { num, pct } from "@/lib/format";

function View({ ticker, series }: { ticker: string; series: string }) {
  const [bench, setBench] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [conf, setConf] = useState(0.95);
  const [years, setYears] = useState(2);
  const [freq, setFreq] = useState("diaria");
  const risk = useRun<Calc>();
  const pat = useRun<Calc>();
  const go = () => {
    const [bt, bs] = bench.trim().split(/\s+/);
    risk.run(() => api.post("/risk", { ticker, series, benchmark_ticker: bt || null, benchmark_series: bs ?? null, start: start || null, end: end || null, confidence: conf, general_beta_years: years, freq }));
    pat.run(() => api.post("/patterns", { ticker, series, start: start || null, end: end || null }));
  };
  const r = risk.data?.result;
  const p = pat.data?.result;
  const betaRow = (b: any, label: string) => (b ? (b.error ? { beta: label, valor: b.error } : { beta: label, valor: num(b.beta, 4), "R²": num(b.r_squared, 4), "error est.": num(b.std_error_beta, 4), obs: b.observations, periodo: `${String(b.start).slice(0, 10)} → ${String(b.end).slice(0, 10)}`, horizonte: b.horizon ?? "intervalo seleccionado", método: b.methodology }) : null);
  return (
    <>
      <Card title="Parámetros">
        <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
          <Text label="Índice de referencia (TICKER SERIE)" value={bench} onChange={setBench} placeholder="índice importado en el catálogo" />
          <Text label="Desde (beta personalizada)" type="date" value={start} onChange={setStart} />
          <Text label="Hasta" type="date" value={end} onChange={setEnd} />
          <Num label="Confianza VaR/ES" value={conf} onChange={setConf} />
          <Num label="Horizonte beta general (años)" value={years} onChange={setYears} step="1" />
          <Select label="Frecuencia" value={freq} onChange={setFreq} options={["diaria", "semanal", "mensual"].map((f) => [f, f])} />
        </div>
        <button className="btn mt-3" onClick={go} disabled={risk.busy}>
          Calcular
        </button>
        <ErrorBox error={risk.error} />
      </Card>
      {r && (
        <>
          <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-6">
            <Stat label="Volatilidad anualizada" value={pct(r.volatility_annual)} sub={`${r.period.observations} obs.`} />
            <Stat label="Drawdown máximo" value={pct(r.max_drawdown.max_drawdown)} sub={`${String(r.max_drawdown.peak_date).slice(0, 10)} → ${String(r.max_drawdown.trough_date).slice(0, 10)}`} />
            <Stat label={`VaR histórico ${conf * 100}% (1 periodo)`} value={pct(r.summary.var_hist?.var)} />
            <Stat label="Expected Shortfall histórico" value={pct(r.summary.var_hist?.es)} />
            <Stat label="VaR paramétrico normal" value={pct(r.summary.var_param?.var)} />
            <Stat label="Curtosis en exceso" value={num(r.summary.excess_kurtosis, 2)} sub={`asimetría ${num(r.summary.skew, 2)}`} />
          </div>
          <p className="mt-1 text-xs text-slate-500">{r.summary.disclaimer}</p>
          {(r.beta_general || r.beta_custom) && (
            <Card title="Beta" className="mt-4">
              <Table rows={[betaRow(r.beta_general, "general"), betaRow(r.beta_custom, "personalizada")].filter(Boolean) as any[]} />
            </Card>
          )}
          {r.liquidity && (
            <Card title="Riesgo de liquidez (últimas sesiones)" className="mt-4">
              <Table rows={[{ "volumen promedio": num(r.liquidity.avg_volume, 0), "importe promedio": num(r.liquidity.avg_turnover), "días sin operación": r.liquidity.zero_volume_days, "iliquidez de Amihud": r.liquidity.amihud_illiquidity?.toExponential(3), ventana: r.liquidity.window }]} />
            </Card>
          )}
          <AuditInfo calc={risk.data} />
        </>
      )}
      <ErrorBox error={pat.error} />
      {p && (
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Card title="Tendencias (reglas documentadas)">
            <Table rows={["primaria", "secundaria", "corto_plazo"].map((k) => ({ tendencia: k, estado: p.trends[k].state, ventana: p.trends[k].window, SMA: num(p.trends[k].sma), "pendiente 20": pct(p.trends[k].sma_slope_20) }))} />
            <p className="mt-1 text-xs text-slate-500">{p.trends.rules}</p>
            <p className="mt-1 text-xs">Regresión log-lineal: {p.regression.direction}, R² {num(p.regression.r_squared, 3)}</p>
            <p className="mt-1 text-xs">Cambios estructurales: {p.structural_breaks.map((b: any) => String(b.date).slice(0, 10)).join(", ") || "—"}</p>
          </Card>
          <Card title="Figuras detectadas">
            <Table rows={p.patterns.map((f: any) => ({ figura: f.pattern, estado: f.status, confirmación: num(f.confirmation_level ?? f.level), invalidación: num(f.invalidation_level), criterio: f.criteria }))} />
            <p className="mt-1 text-xs text-slate-500">{p.disclaimer}</p>
          </Card>
        </div>
      )}
    </>
  );
}

export default function Riesgos() {
  return (
    <>
      <PageHeader title="Patrones y riesgos" subtitle="Volatilidad, drawdown, VaR, Expected Shortfall, beta general y personalizada con R², liquidez y tendencias. Métricas estadísticas históricas, no estimaciones infalibles del futuro." />
      <RequireAsset>{(a) => <View {...a} />}</RequireAsset>
    </>
  );
}
