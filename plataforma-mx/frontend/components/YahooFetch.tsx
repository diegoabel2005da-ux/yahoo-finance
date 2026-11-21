"use client";
import { useState } from "react";
import { ErrorBox, Notice, Select, useRun } from "./ui";
import { api } from "@/lib/api";

/** Descarga de precios desde Yahoo Finance (fuente de referencia designada por el usuario). */
export function YahooPrices({ ticker, series, onDone }: { ticker: string; series: string; onDone?: () => void }) {
  const [period, setPeriod] = useState("5y");
  const one = useRun<any>();
  const all = useRun<any>();
  const r = one.data;
  return (
    <div className="space-y-2">
      <Notice>
        Fuente de referencia designada: <b>Yahoo Finance</b> (yfinance), para uso personal y de investigación. Las barras sin cierre o de la sesión en curso se rechazan; no se rellenan. «Close» de Yahoo está ajustado por splits; «Adj Close» se guarda como cierre ajustado.
      </Notice>
      <div className="flex flex-wrap items-end gap-2">
        <div className="w-36">
          <Select label="Periodo" value={period} onChange={setPeriod} options={[["1y", "1 año"], ["2y", "2 años"], ["5y", "5 años"], ["10y", "10 años"], ["max", "Máximo disponible"]]} />
        </div>
        <button className="btn" disabled={one.busy} onClick={() => one.run(async () => { const x = await api.post("/yahoo/prices", { ticker, series, period }); onDone?.(); return x; })}>
          {one.busy ? "Descargando…" : `Descargar ${ticker} ${series} de Yahoo`}
        </button>
        <button className="btn-ghost" disabled={all.busy} onClick={() => all.run(async () => { const x = await api.post("/yahoo/refresh", {}); onDone?.(); return x; })}>
          {all.busy ? "Actualizando…" : "Actualizar todas las emisoras vigentes"}
        </button>
      </div>
      <ErrorBox error={one.error || all.error} />
      {r && (r.status === "ok" ? (
        <p className="text-xs">
          {r.symbol}: {r.accepted_rows} sesiones nuevas · {r.duplicates_skipped ?? 0} ya existentes · {r.rejected?.length ?? 0} rechazadas
          {r.rejected?.length ? ` (${r.rejected.slice(0, 3).map((x: any) => `${x.date ?? "renglón " + x.row}: ${x.errors[0]}`).join("; ")})` : ""}
          {r.discrepancies?.length ? ` · ${r.discrepancies.length} discrepancias` : ""}
        </p>
      ) : <Notice tone="warn">No disponible ({r.symbol}): {r.reason}</Notice>)}
      {all.data && <p className="text-xs">{all.data.map((x: any) => `${x.ticker} ${x.series}: ${x.status === "no_disponible" ? "no disponible" : x.status === "al_dia" ? "al día" : `+${x.accepted_rows}`}`).join(" · ")}</p>}
    </div>
  );
}

export function YahooFinancials({ ticker, series, onDone }: { ticker: string; series: string; onDone?: () => void }) {
  const fin = useRun<any>();
  const div = useRun<any>();
  const go = (quarterly: boolean) => fin.run(async () => { const x = await api.post("/yahoo/financials", { ticker, series, quarterly }); onDone?.(); return x; });
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <button className="btn" disabled={fin.busy} onClick={() => go(false)}>Importar anuales de Yahoo</button>
        <button className="btn" disabled={fin.busy} onClick={() => go(true)}>Importar trimestrales de Yahoo</button>
        <button className="btn-ghost" disabled={div.busy} onClick={() => div.run(() => api.get(`/yahoo/dividends/${ticker}/${encodeURIComponent(series)}`))}>Ver dividendos</button>
      </div>
      <ErrorBox error={fin.error || div.error} />
      {fin.data && (fin.data.status === "ok" ? (
        <p className="text-xs">
          {fin.data.symbol}: {fin.data.statements} estados importados ({fin.data.currency}).
          {Object.keys(fin.data.missing_items ?? {}).length ? ` Partidas que Yahoo no publica (quedan como no disponibles): ${Object.entries(fin.data.missing_items).map(([k, v]: any) => `${k}: ${v.join(", ")}`).join(" · ")}.` : ""}
        </p>
      ) : <Notice tone="warn">No disponible: {fin.data.reason}</Notice>)}
      {div.data && (div.data.status === "ok" ? (
        <div className="text-xs">
          <p>Dividendo por acción últimos 12 meses: <b>{div.data.dps_ttm ?? "—"}</b> · {div.data.note}</p>
          <div className="mt-1 max-h-40 overflow-auto">
            <table className="tbl"><thead><tr><th>Fecha ex</th><th>Monto</th></tr></thead>
              <tbody>{div.data.dividends.slice(-20).reverse().map((d: any) => <tr key={d.ex_date}><td>{d.ex_date}</td><td>{d.amount}</td></tr>)}</tbody>
            </table>
          </div>
        </div>
      ) : <Notice tone="warn">No disponible: {div.data.reason}</Notice>)}
    </div>
  );
}
