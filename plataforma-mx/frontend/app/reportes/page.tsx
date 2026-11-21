"use client";
import { useEffect, useState } from "react";
import { Card, ErrorBox, Notice, PageHeader, Text, useRun } from "@/components/ui";
import { api } from "@/lib/api";
import { useAsset } from "@/lib/asset";

export default function Reportes() {
  const { asset } = useAsset();
  const [audit, setAudit] = useState<any[]>([]);
  const [sel, setSel] = useState<number[]>([]);
  const [title, setTitle] = useState("Informe de análisis y coberturas");
  const [summary, setSummary] = useState("");
  const [concl, setConcl] = useState("");
  const dl = useRun<any>();
  const save = useRun<any>();
  useEffect(() => {
    api.get("/audit", { limit: 100 }).then(setAudit).catch(() => {});
  }, []);
  const body = () => ({ title, subject: asset ? `${asset.ticker} ${asset.series}` : "Exposición a tasas", audit_ids: sel, executive_summary: summary || null, conclusions: concl || null });
  const toggle = (id: number) => setSel(sel.includes(id) ? sel.filter((x) => x !== id) : [...sel, id]);
  return (
    <>
      <PageHeader title="Reportes" subtitle="Excel (17 hojas, con fórmulas auditables) y PDF profesional generados del mismo objeto de estudio del backend: los valores coinciden con la interfaz." />
      <Card title="1. Seleccione los cálculos auditados a incluir">
        <Notice>Cada cálculo conserva entradas, parámetros, fórmulas, fuentes y huella sha256. Las secciones sin cálculo se muestran explícitamente como «sin datos».</Notice>
        <div className="max-h-80 overflow-auto">
          <table className="tbl">
            <thead><tr><th></th><th>#</th><th>Cálculo</th><th>Fecha</th><th>Huella</th></tr></thead>
            <tbody>
              {audit.map((a) => (
                <tr key={a.id}>
                  <td><input type="checkbox" checked={sel.includes(a.id)} onChange={() => toggle(a.id)} /></td>
                  <td>{a.id}</td>
                  <td>{a.calculation}</td>
                  <td>{String(a.created_at).slice(0, 19)}</td>
                  <td className="font-mono">{a.digest.slice(0, 16)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card title="2. Contenido" className="mt-4">
        <div className="grid gap-2 md:grid-cols-2">
          <Text label="Título" value={title} onChange={setTitle} />
          <div />
          <label className="block"><span className="label">Resumen ejecutivo (vacío = resumen por reglas de los escenarios)</span><textarea className="input h-24" value={summary} onChange={(e) => setSummary(e.target.value)} /></label>
          <label className="block"><span className="label">Conclusiones del analista</span><textarea className="input h-24" value={concl} onChange={(e) => setConcl(e.target.value)} /></label>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button className="btn" disabled={!sel.length || dl.busy} onClick={() => dl.run(() => api.download("/reports/xlsx", body(), "informe.xlsx"))}>Descargar Excel</button>
          <button className="btn" disabled={!sel.length || dl.busy} onClick={() => dl.run(() => api.download("/reports/pdf", body(), "informe.pdf"))}>Descargar PDF</button>
          <button className="btn-ghost" disabled={!sel.length} onClick={() => save.run(() => api.post("/studies", body()))}>Guardar como estudio</button>
        </div>
        <ErrorBox error={dl.error || save.error} />
        {save.data && <p className="mt-2 text-xs">Estudio #{save.data.id} guardado (versión {save.data.version}).</p>}
      </Card>
    </>
  );
}
