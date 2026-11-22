"use client";
import { useEffect, useMemo, useState } from "react";
import RequireAsset from "@/components/RequireAsset";
import { YahooFinancials } from "@/components/YahooFetch";
import { AuditInfo, Card, ErrorBox, Notice, Num, PageHeader, Select, Table, Text, Upload, useRun } from "@/components/ui";
import { api, Calc } from "@/lib/api";
import { num, pct } from "@/lib/format";

const TABS: [string, string][] = [["income", "Estado de resultados"], ["balance", "Balance general"], ["cashflow", "Flujos de efectivo"]];

function View({ ticker, series }: { ticker: string; series: string }) {
  const [stmts, setStmts] = useState<any[]>([]);
  const [tab, setTab] = useState("income");
  const [ptype, setPtype] = useState("FY");
  const [basis, setBasis] = useState("consolidado");
  const [mode, setMode] = useState<"abs" | "h" | "v">("abs");
  const [mk, setMk] = useState<any>({ price: NaN, price_source: "", shares: NaN, dps_ttm: NaN, tax_rate: NaN });
  const { data, error, busy, run } = useRun<Calc>();
  const load = () => api.get(`/financials/${ticker}`).then(setStmts).catch(() => setStmts([]));
  useEffect(() => {
    load();
  }, [ticker]);
  const sel = stmts.filter((s) => s.statement === tab && s.period_type === ptype && s.basis === basis);
  const items = useMemo(() => Array.from(new Set(sel.flatMap((s) => Object.keys(s.items)))), [sel]);
  const table = items.map((it) => {
    const row: any = { partida: it };
    sel.forEach((s, i) => {
      const v = s.items[it];
      if (mode === "abs") row[s.period_end] = num(v);
      else if (mode === "h") {
        const prev = i > 0 ? sel[i - 1].items[it] : undefined;
        row[s.period_end] = prev ? pct(v / prev - 1) : "—";
      } else {
        const b = s.items[tab === "balance" ? "total_assets" : tab === "income" ? "revenue" : "cfo"];
        row[s.period_end] = b ? pct(v / b) : "—";
      }
    });
    return row;
  });
  const fin = (k: string) => (Number.isFinite(mk[k]) ? mk[k] : null);
  const goRatios = () => run(() => api.post("/ratios", { ticker, period_type: ptype, basis, price: fin("price"), price_source: mk.price_source || null, shares: fin("shares"), dps_ttm: fin("dps_ttm"), tax_rate: fin("tax_rate") }));
  return (
    <>
      <Card title="Estados financieros">
        <div className="mb-3 flex flex-wrap gap-2">
          {TABS.map(([k, l]) => (
            <button key={k} className={k === tab ? "btn" : "btn-ghost"} onClick={() => setTab(k)}>
              {l}
            </button>
          ))}
          <div className="w-32"><Select label="Periodo" value={ptype} onChange={setPtype} options={[["FY", "Anual"], ["Q", "Trimestral"]]} /></div>
          <div className="w-40"><Select label="Base" value={basis} onChange={setBasis} options={[["consolidado", "Consolidado"], ["individual", "Individual"]]} /></div>
          <div className="w-44"><Select label="Vista" value={mode} onChange={(v) => setMode(v as any)} options={[["abs", "Cifras"], ["h", "Análisis horizontal"], ["v", "Análisis vertical"]]} /></div>
        </div>
        {sel.length ? (
          <>
            <Table rows={table} />
            <p className="mt-1 text-[11px] text-slate-500">Fuentes: {Array.from(new Set(sel.map((s) => `${s.source} (${s.currency} ${s.units})`))).join("; ")}</p>
          </>
        ) : (
          <Notice tone="warn">Sin estados financieros importados para esta combinación. Importe reportes trimestrales/anuales verificables (CNBV, BMV/BIVA o reportes oficiales de la emisora).</Notice>
        )}
      </Card>
      <Card title="Ratios financieros y de mercado" className="mt-4">
        <Notice>Si deja vacíos precio, acciones o dividendo, se usan los datos cargados: último cierre, acciones del balance y dividendos de los últimos 12 meses, cada uno con su fuente. Si los estados están en otra moneda que el precio, no se calculan múltiplos de mercado. Las razones sin insumos completos se muestran como no calculables, nunca se estiman.</Notice>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
          <Num label="Precio" value={mk.price} onChange={(v) => setMk({ ...mk, price: v })} />
          <Text label="Fuente del precio" value={mk.price_source} onChange={(v) => setMk({ ...mk, price_source: v })} />
          <Num label="Acciones en circulación" value={mk.shares} onChange={(v) => setMk({ ...mk, shares: v })} />
          <Num label="Dividendo por acción 12m" value={mk.dps_ttm} onChange={(v) => setMk({ ...mk, dps_ttm: v })} />
          <Num label="Tasa de impuestos (ROIC)" value={mk.tax_rate} onChange={(v) => setMk({ ...mk, tax_rate: v })} />
        </div>
        <button className="btn mt-2" onClick={goRatios} disabled={busy}>
          Calcular ratios
        </button>
        <ErrorBox error={error} />
        {data && (
          <>
            {data.result.notes?.map((n: string) => <Notice key={n} tone="warn">{n}</Notice>)}
            <p className="mt-2 text-xs">Insumos usados: precio {num(data.result.inputs_used?.price)} · acciones {num(data.result.inputs_used?.shares, 0)} · dividendo 12m {num(data.result.inputs_used?.dps_ttm, 4)} · moneda de los estados {data.result.inputs_used?.statement_currency ?? "—"}</p>
            <p className="mt-1 text-xs">Periodo: {data.result.period_end} · Capitalización: {num(data.result.market_cap)} · VE: {num(data.result.enterprise_value)} · Deuda neta: {num(data.result.net_debt)}</p>
            <Table rows={Object.entries(data.result.ratios).map(([k, v]: any) => ({ razón: k, valor: v.value === null ? "no calculable" : num(v.value, 4), fórmula: v.formula, faltantes: v.missing.join(", "), interpretación: v.explanation }))} />
            <AuditInfo calc={data} />
          </>
        )}
      </Card>
      <Card title="Yahoo Finance — estados financieros y dividendos" className="mt-4">
        <YahooFinancials ticker={ticker} series={series} onDone={load} />
      </Card>
      <Card title="Importar estados financieros desde archivo" className="mt-4">
        <Notice>Formato largo: un renglón por partida (ticker, estado, periodo, fecha de cierre, base, moneda, unidades, partida, valor, fuente, fecha de consulta). Dividendos, reportes y previsiones de analistas sólo se integran si provienen de fuentes legalmente utilizables; no se generan consensos.</Notice>
        <Upload endpoint="/financials/import" label="CSV/Excel" template="financials_template.csv" onDone={load} />
      </Card>
    </>
  );
}

export default function Financieros() {
  return (
    <>
      <PageHeader title="Estados financieros" subtitle="Resumen, estado de resultados, balance, flujos, ratios y análisis horizontal/vertical, respetando base consolidada/individual y periodos contables." />
      <RequireAsset>{(a) => <View {...a} />}</RequireAsset>
    </>
  );
}
