"use client";
import { useEffect, useState } from "react";
import { Card, ErrorBox, Notice, PageHeader, Table, Upload } from "@/components/ui";
import { api } from "@/lib/api";
import { useAsset } from "@/lib/asset";

export default function Emisoras() {
  const [cat, setCat] = useState<any>(null);
  const [filter, setFilter] = useState("");
  const [analyses, setAnalyses] = useState<any[] | null>(null);
  const [err, setErr] = useState<any>(null);
  const [source, setSource] = useState("");
  const { asset, setAsset } = useAsset();
  const load = () => api.get("/catalog").then(setCat).catch(setErr);
  useEffect(() => {
    load();
  }, []);
  useEffect(() => {
    if (asset) api.get(`/catalog/${asset.ticker}/${encodeURIComponent(asset.series)}/analyses`).then(setAnalyses).catch(() => setAnalyses(null));
  }, [asset]);
  const rows = (cat?.instruments ?? []).filter((i: any) => `${i.ticker} ${i.issuer_name} ${i.sector}`.toLowerCase().includes(filter.toLowerCase()));
  return (
    <>
      <PageHeader title="Emisoras" subtitle="Catálogo dinámico de subyacentes accionarios mexicanos con futuros u opciones listados en MexDer. Cada serie es un registro independiente." />
      <ErrorBox error={err} />
      <Card title="Actualizar catálogo">
        <Notice>
          MexDer no expone (en lo verificado) una API pública del universo de subyacentes. Descargue la relación vigente de contratos de futuros y opciones sobre acciones y cárguela con la plantilla. Las emisoras que no aparezcan en la nueva revisión se marcan como no vigentes, sin borrarse.
        </Notice>
        <div className="mb-2 max-w-md">
          <span className="label">Fuente de la revisión (URL o documento de MexDer)</span>
          <input className="input" value={source} onChange={(e) => setSource(e.target.value)} placeholder="p. ej. https://www.mexder.com.mx/... (fecha de publicación)" />
        </div>
        <Upload endpoint="/catalog/import" label="Archivo del catálogo" extra={{ source }} template="catalog_template.csv" onDone={load} />
      </Card>
      <Card title={`Universo (${rows.length})`} className="mt-4" actions={<input className="input max-w-xs" placeholder="Filtrar…" value={filter} onChange={(e) => setFilter(e.target.value)} />}>
        {rows.length === 0 ? (
          <p className="text-sm text-slate-500">Sin emisoras en el catálogo.</p>
        ) : (
          <div className="max-h-[28rem] overflow-auto">
            <table className="tbl">
              <thead>
                <tr>
                  {["", "Emisora", "Serie", "ISIN", "Sector", "Bolsa", "Moneda", "Derivados", "Vigente", "Revisión", "Precios", "Financieros", "Contratos", "Discrep."].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((i: any) => {
                  const sel = asset?.ticker === i.ticker && asset?.series === i.series;
                  return (
                    <tr key={i.id} className={sel ? "bg-teal-50 dark:bg-navy-800" : ""}>
                      <td>
                        <button className="btn-ghost px-2 py-0.5 text-xs" onClick={() => setAsset({ ticker: i.ticker, series: i.series, issuer_name: i.issuer_name })}>
                          {sel ? "✓" : "Elegir"}
                        </button>
                      </td>
                      <td>
                        <b>{i.ticker}</b> <span className="text-slate-500">{i.issuer_name}</span>
                      </td>
                      <td>{i.series}</td>
                      <td className="font-mono">{i.isin ?? "—"}</td>
                      <td>{i.sector ?? "—"}</td>
                      <td>{i.exchange}</td>
                      <td>{i.currency}</td>
                      <td>{i.derivatives.join(", ")}</td>
                      <td>{i.active ? "sí" : "no"}</td>
                      <td>{i.reviewed_on}</td>
                      <td>{i.availability.prices ? "✓" : "pendiente"}</td>
                      <td>{i.availability.financials ? "✓" : "pendiente"}</td>
                      <td>{i.availability.futures_contracts || i.availability.option_contracts ? "✓" : "pendiente"}</td>
                      <td className={i.availability.open_discrepancies ? "font-bold text-red-600" : ""}>{i.availability.open_discrepancies}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {asset && analyses && (
        <Card title={`Análisis disponibles — ${asset.ticker} ${asset.series}`} className="mt-4">
          <Table rows={analyses.map((a) => ({ análisis: a.analysis, disponible: a.available ? "sí" : a.blocked_by_discrepancies ? "bloqueado (discrepancias)" : "pendiente", requiere: a.requires }))} />
        </Card>
      )}
    </>
  );
}
