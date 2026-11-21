"use client";
import { useEffect, useMemo, useState } from "react";
import Plot from "@/components/Plot";
import { YahooPrices } from "@/components/YahooFetch";
import RequireAsset from "@/components/RequireAsset";
import { Card, ErrorBox, Notice, PageHeader, Select, Stat, Table, Text, Upload } from "@/components/ui";
import { api } from "@/lib/api";
import { num, pct } from "@/lib/format";

const FREQS: [string, string][] = ["diaria", "semanal", "mensual", "bimestral", "trimestral", "semestral", "anual"].map((f) => [f, f]);
const PTYPES: [string, string][] = [
  ["cierre_oficial", "Cierre oficial"],
  ["cierre_ajustado", "Cierre ajustado"],
  ["ultimo_negociado", "Último negociado"],
  ["spot", "Spot"],
];

function View({ ticker, series }: { ticker: string; series: string }) {
  const [freq, setFreq] = useState("diaria");
  const [ptype, setPtype] = useState("cierre_oficial");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [bench, setBench] = useState("");
  const [data, setData] = useState<any>(null);
  const [bdata, setBdata] = useState<any>(null);
  const [err, setErr] = useState<any>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    setErr(null);
    api.get(`/prices/${ticker}/${encodeURIComponent(series)}`, { freq, price_type: ptype, start, end }).then(setData).catch((e) => { setErr(e); setData(null); });
  }, [ticker, series, freq, ptype, start, end, tick]);
  useEffect(() => {
    if (!bench) return setBdata(null);
    const [t, s] = bench.split(" ");
    api.get(`/prices/${t}/${encodeURIComponent(s ?? "")}`, { freq, start, end }).then(setBdata).catch(() => setBdata(null));
  }, [bench, freq, start, end]);
  const rows = data?.rows ?? [];
  const m = data?.meta;
  const chart = useMemo(() => {
    if (!rows.length) return [];
    const x = rows.map((r: any) => r.date);
    const tr: any[] = rows[0].open !== undefined && rows[0].high !== undefined
      ? [{ type: "candlestick", x, open: rows.map((r: any) => r.open), high: rows.map((r: any) => r.high), low: rows.map((r: any) => r.low), close: rows.map((r: any) => r.close), name: ticker, increasing: { line: { color: "#14B8A6" } }, decreasing: { line: { color: "#E11D48" } } }]
      : [{ type: "scatter", x, y: rows.map((r: any) => r.close), name: ticker, line: { color: "#0B1F3A" } }];
    if (rows[0].volume !== undefined) tr.push({ type: "bar", x, y: rows.map((r: any) => r.volume), name: "Volumen", yaxis: "y2", marker: { color: "rgba(100,116,139,0.35)" } });
    return tr;
  }, [rows, ticker]);
  const compare = useMemo(() => {
    if (!bdata?.rows?.length || !rows.length) return null;
    const bm = new Map(bdata.rows.map((r: any) => [r.date, r.close]));
    const common = rows.filter((r: any) => bm.has(r.date));
    if (common.length < 2) return null;
    const a0 = common[0].close, b0 = bm.get(common[0].date) as number;
    return [
      { x: common.map((r: any) => r.date), y: common.map((r: any) => r.close / a0 - 1), name: ticker, line: { color: "#0B1F3A" } },
      { x: common.map((r: any) => r.date), y: common.map((r: any) => (bm.get(r.date) as number) / b0 - 1), name: bench, line: { color: "#14B8A6" } },
    ];
  }, [bdata, rows, ticker, bench]);
  return (
    <>
      <Card title="Parámetros">
        <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
          <Select label="Temporalidad" value={freq} onChange={setFreq} options={FREQS} />
          <Select label="Tipo de precio" value={ptype} onChange={setPtype} options={PTYPES} />
          <Text label="Desde" type="date" value={start} onChange={setStart} />
          <Text label="Hasta" type="date" value={end} onChange={setEnd} />
          <Text label="Índice de comparación (TICKER SERIE)" value={bench} onChange={setBench} placeholder="p. ej. ticker del índice en el catálogo" />
        </div>
      </Card>
      <ErrorBox error={err} />
      {m && !m.available && <Notice tone="warn">{m.reason}. Importe datos verificados abajo.</Notice>}
      {m?.available && (
        <>
          <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-6">
            <Stat label="Último dato disponible" value={String(m.last_date)} sub={m.freshness?.status === "desactualizado" ? `${m.freshness.business_days_behind} días hábiles de rezago` : "al día (calendario por reglas)"} />
            <Stat label={`Último ${ptype.replace("_", " ")}`} value={num(rows.at(-1)?.close)} sub={m.currency} />
            <Stat label="Variación último periodo" value={pct(rows.at(-1)?.ret_simple)} />
            <Stat label="Volatilidad anualizada" value={pct(m.volatility_annual)} sub={`rend. log, ${freq}`} />
            <Stat label="Máx / mín histórico (cargado)" value={`${num(m.all_time_high)} / ${num(m.all_time_low)}`} />
            <Stat label="Drawdown máximo" value={pct(m.max_drawdown?.max_drawdown)} sub={`${m.max_drawdown?.peak_date?.slice(0, 10)} → ${m.max_drawdown?.trough_date?.slice(0, 10)}`} />
          </div>
          <Card title="Serie" className="mt-4">
            <Plot data={chart} height={420} layout={{ xaxis: { rangeslider: { visible: false } }, yaxis2: { overlaying: "y", side: "right", showgrid: false, title: "Volumen" } }} />
            <p className="text-[11px] text-slate-500">
              Fuentes: {m.sources.join(", ")} · Validación: {JSON.stringify(m.validation_counts)} · {m.aggregation} · Cierre ajustado disponible: {m.adjusted_close_available ? "sí" : "no"}
            </p>
          </Card>
          {compare && (
            <Card title="Rendimiento acumulado vs índice (fechas comunes)" className="mt-4">
              <Plot data={compare} height={300} layout={{ yaxis: { tickformat: ".1%" } }} />
            </Card>
          )}
          <Card title="Observaciones" className="mt-4">
            <Table rows={rows} fmt={{ ret_simple: (v) => pct(v, 3), ret_log: (v) => pct(v, 3), ret_cum: (v) => pct(v), drawdown: (v) => pct(v) }} />
          </Card>
        </>
      )}
      <Card title="Yahoo Finance" className="mt-4">
        <YahooPrices ticker={ticker} series={series} onDone={() => setTick((t) => t + 1)} />
      </Card>
      <Card title="Importar precios desde archivo" className="mt-4">
        <Notice>Cada renglón debe declarar fuente, tipo de precio, fechas de mercado/publicación/consulta, moneda, precisión publicada, estado de actualización y origen. Los renglones inválidos se rechazan; no se corrigen ni se rellenan. Las correcciones oficiales se cargan con un nuevo data_version.</Notice>
        <Upload endpoint="/prices/import" label="CSV/Excel de precios" template="prices_template.csv" onDone={() => setTick((t) => t + 1)} />
      </Card>
    </>
  );
}

export default function Historicos() {
  return (
    <>
      <PageHeader title="Datos históricos" subtitle="OHLCV con temporalidad configurable, rendimientos simples, logarítmicos y acumulados, volatilidad y drawdown. Al agregar: primera apertura, máximo, mínimo, último cierre y volumen total." />
      <RequireAsset>{(a) => <View {...a} />}</RequireAsset>
    </>
  );
}
