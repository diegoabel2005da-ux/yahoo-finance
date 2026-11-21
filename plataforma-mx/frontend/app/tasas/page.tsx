"use client";
import { useEffect, useState } from "react";
import Plot from "@/components/Plot";
import { Card, ErrorBox, Notice, PageHeader, Select, Table, Text, Upload, useRun } from "@/components/ui";
import { api } from "@/lib/api";
import { pct } from "@/lib/format";

export default function Tasas() {
  const [rates, setRates] = useState<any[]>([]);
  const [code, setCode] = useState("");
  const [series, setSeries] = useState<any[]>([]);
  const [curves, setCurves] = useState<any[]>([]);
  const [curveId, setCurveId] = useState("");
  const [curve, setCurve] = useState<any>(null);
  const [bx, setBx] = useState({ rate_code: "TIIE_28", start: "", end: "" });
  const fetchBx = useRun<any>();
  const cetes = useRun<any>();
  const [cetesDate, setCetesDate] = useState("");
  const [cf, setCf] = useState({ name: "", curve_date: "", quote_kind: "zero_rate_pct", compounding: "continua", day_count: "ACT/360", interpolation: "log_linear_df", source: "", origin: "observado_proveedor_secundario" });
  const loadRates = () => api.get("/rates").then(setRates).catch(() => {});
  const loadCurves = () => api.get("/curves").then(setCurves).catch(() => {});
  useEffect(() => {
    loadRates();
    loadCurves();
  }, []);
  useEffect(() => {
    if (code) api.get(`/rates/${code}`).then(setSeries).catch(() => setSeries([]));
  }, [code]);
  useEffect(() => {
    if (curveId) api.get(`/curves/${curveId}`).then(setCurve).catch(() => setCurve(null));
  }, [curveId]);
  return (
    <>
      <PageHeader title="Derivados de tasas" subtitle="Tasas de referencia verificables (TIIE de Fondeo, TIIE a plazo, gubernamentales) y curvas importadas: tasas cero, factores de descuento y forwards con interpolación documentada." />
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Tasas de referencia">
          {rates.length ? (
            <>
              <Table rows={rates.map((r) => ({ código: r.rate_code, nombre: r.rate_name, desde: r.first, hasta: r.last, observaciones: r.observations }))} />
              <div className="mt-2 max-w-xs">
                <Select label="Ver serie" value={code} onChange={setCode} options={[["", "—"], ...rates.map((r) => [r.rate_code, r.rate_code] as [string, string])]} />
              </div>
            </>
          ) : (
            <Notice tone="warn">Sin tasas cargadas. Obténgalas de Banxico (SIE) o impórtelas con su fuente.</Notice>
          )}
          <h3 className="mt-4 text-xs font-semibold uppercase text-slate-500">Banxico SIE</h3>
          <div className="grid grid-cols-3 gap-2">
            <Select label="Serie" value={bx.rate_code} onChange={(v) => setBx({ ...bx, rate_code: v })} options={["TIIE_28", "TIIE_91", "TIIE_182", "TIIE_FONDEO", "TASA_OBJETIVO", "CETES_28", "CETES_91", "CETES_182", "CETES_364"].map((x) => [x, x])} />
            <Text label="Desde" type="date" value={bx.start} onChange={(v) => setBx({ ...bx, start: v })} />
            <Text label="Hasta" type="date" value={bx.end} onChange={(v) => setBx({ ...bx, end: v })} />
          </div>
          <button
            className="btn mt-2"
            disabled={!bx.start || !bx.end}
            onClick={() =>
              fetchBx.run(async () => {
                const fd = new FormData();
                Object.entries(bx).forEach(([k, v]) => fd.append(k, v));
                const r = await api.form("/rates/banxico", fd);
                loadRates();
                return r;
              })
            }
          >
            Consultar SIE
          </button>
          <ErrorBox error={fetchBx.error} />
          {fetchBx.data && (fetchBx.data.status === "ok" ? <p className="mt-1 text-xs">Serie {fetchBx.data.series}: {fetchBx.data.accepted} observaciones nuevas.</p> : <Notice tone="warn">No disponible: {fetchBx.data.reason}. Use la importación validada.</Notice>)}
          <p className="mt-1 text-[11px] text-slate-500">Requiere BANXICO_TOKEN en el backend. Los identificadores de serie son configurables y deben verificarse en el catálogo SIE. Los días sin dato («N/E») no se rellenan.</p>
          <div className="mt-3">
            <Upload endpoint="/rates/import" label="Importar tasas (CSV/Excel)" template="rates_template.csv" onDone={loadRates} />
          </div>
        </Card>
        <Card title={code ? `Serie ${code}` : "Serie"}>
          {series.length ? (
            <>
              <Plot data={[{ x: series.map((s) => s.date), y: series.map((s) => Number(s.value_pct)), name: code, line: { color: "#0B1F3A" } }]} layout={{ yaxis: { title: "%" } }} height={280} />
              <p className="text-[11px] text-slate-500">Convención: {series[0].convention} · Fuente: {series.at(-1).source} · Último dato: {series.at(-1).date}</p>
            </>
          ) : (
            <p className="text-sm text-slate-500">Seleccione una tasa.</p>
          )}
        </Card>
      </div>
      <Card title="Curvas de tasas" className="mt-4">
        <Notice>Una tasa spot aislada no sustituye una curva. Importe nodos verificados (p. ej. de un proveedor de precios autorizado). Con menos de 2 nodos no se construye curva y fuera del último nodo no se extrapola sin advertencia.</Notice>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          <Text label="Nombre" value={cf.name} onChange={(v) => setCf({ ...cf, name: v })} />
          <Text label="Fecha de la curva" type="date" value={cf.curve_date} onChange={(v) => setCf({ ...cf, curve_date: v })} />
          <Select label="Tipo de dato" value={cf.quote_kind} onChange={(v) => setCf({ ...cf, quote_kind: v })} options={[["zero_rate_pct", "Tasa cero (%)"], ["zero_rate", "Tasa cero (decimal)"], ["discount_factor", "Factor de descuento"]]} />
          <Select label="Capitalización" value={cf.compounding} onChange={(v) => setCf({ ...cf, compounding: v })} options={["continua", "simple", "periodo_28d", "mensual", "trimestral", "semestral", "anual"].map((x) => [x, x])} />
          <Select label="Base (tasas simples)" value={cf.day_count} onChange={(v) => setCf({ ...cf, day_count: v })} options={["ACT/360", "ACT/365F", "30/360"].map((x) => [x, x])} />
          <Select label="Interpolación" value={cf.interpolation} onChange={(v) => setCf({ ...cf, interpolation: v })} options={[["log_linear_df", "Log-lineal en DF (forward constante)"], ["linear_zero", "Lineal en tasa cero"]]} />
          <Text label="Fuente" value={cf.source} onChange={(v) => setCf({ ...cf, source: v })} />
          <Select label="Origen" value={cf.origin} onChange={(v) => setCf({ ...cf, origin: v })} options={[["observado_fuente_oficial", "Fuente oficial"], ["observado_proveedor_secundario", "Proveedor"], ["supuesto_del_usuario", "Hipotética (supuesto)"]]} />
        </div>
        <div className="mt-2 rounded border border-slate-200 p-2 dark:border-navy-700">
          <h3 className="text-xs font-semibold uppercase text-slate-500">Curva oficial CETES (Banxico, subasta semanal)</h3>
          <div className="flex flex-wrap items-end gap-2">
            <div className="w-44"><Text label="Fecha de la curva" type="date" value={cetesDate} onChange={setCetesDate} /></div>
            <button className="btn" disabled={cetes.busy} onClick={() => cetes.run(async () => { const r = await api.post("/curves/banxico-cetes", { curve_date: cetesDate || null }); loadCurves(); setCurveId(String(r.curve_id)); return r; })}>
              {cetes.busy ? "Construyendo…" : "Construir curva CETES"}
            </button>
          </div>
          <ErrorBox error={cetes.error} />
          {cetes.data && <p className="mt-1 text-xs">Curva #{cetes.data.curve_id}: {cetes.data.auctions.map((a: any) => `${a.tenor} ${a.yield_pct}% (${a.auction_date})`).join(" · ")}. {cetes.data.notes.join(" ")}</p>}
        </div>
        <div className="mt-2">
          <Upload endpoint="/curves/import" label="Nodos (days, value)" extra={cf} template="curve_template.csv" onDone={loadCurves} />
        </div>
        <div className="mt-3 max-w-md">
          <Select label="Ver curva" value={curveId} onChange={setCurveId} options={[["", "—"], ...curves.map((c) => [String(c.id), `#${c.id} ${c.name} ${c.curve_date} (${c.nodes} nodos)`] as [string, string])]} />
        </div>
        {curve && (
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <div>
              <Plot data={[{ x: curve.nodes.map((n: any) => n.days), y: curve.nodes.map((n: any) => n.zero_cont), name: "Cero continua", mode: "lines+markers", line: { color: "#0B1F3A" } }, { x: curve.forwards_28d.map((_: any, i: number) => 28 * (i + 0.5)), y: curve.forwards_28d.map((f: any) => f.forward_simple_act360), name: "Forward 28d (ACT/360)", line: { color: "#14B8A6", shape: "hv" } }]} layout={{ yaxis: { tickformat: ".2%" }, xaxis: { title: "días" } }} height={300} />
              <p className="text-[11px] text-slate-500">{curve.source} · {curve.origin} · {curve.interpolation}. {curve.note}</p>
            </div>
            <Table rows={curve.nodes.map((n: any) => ({ días: n.days, "cero cont.": pct(n.zero_cont, 4), DF: n.df.toFixed(8) }))} />
          </div>
        )}
      </Card>
    </>
  );
}
