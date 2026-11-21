"use client";
import { useEffect, useState } from "react";
import { Card, PageHeader, Table, useRun } from "@/components/ui";
import { api } from "@/lib/api";

export default function Estudios() {
  const [list, setList] = useState<any[]>([]);
  const [open, setOpen] = useState<any>(null);
  const dl = useRun<any>();
  useEffect(() => {
    api.get("/studies").then(setList).catch(() => {});
  }, []);
  return (
    <>
      <PageHeader title="Estudios guardados" subtitle="Estudios versionados. Cada uno referencia cálculos auditados reproducibles con sus datos originales." />
      <Card title="Estudios">
        <div className="max-h-96 overflow-auto">
          <table className="tbl">
            <thead><tr><th>#</th><th>Título</th><th>Versión</th><th>Fecha</th><th>Cálculos</th><th></th></tr></thead>
            <tbody>
              {list.map((s) => (
                <tr key={s.id}>
                  <td>{s.id}</td><td>{s.title}</td><td>v{s.version}</td><td>{String(s.created_at).slice(0, 19)}</td>
                  <td>{(s.audit_ids ?? []).map((a: number) => <a key={a} className="mr-1 underline" href={`/api/audit/${a}`} target="_blank" rel="noreferrer">#{a}</a>)}</td>
                  <td className="space-x-1">
                    <button className="btn-ghost px-2 py-0.5 text-xs" onClick={() => api.get(`/studies/${s.id}`).then(setOpen)}>Abrir</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      {open && (
        <Card title={`${open.title} — v${open.version}`} className="mt-4">
          <div className="mb-2 flex gap-2">
            <button className="btn" onClick={() => dl.run(() => api.download("/reports/xlsx", open.inputs, `${open.title}.xlsx`))}>Excel</button>
            <button className="btn" onClick={() => dl.run(() => api.download("/reports/pdf", open.inputs, `${open.title}.pdf`))}>PDF</button>
          </div>
          <Table rows={(open.results.sources ?? []).map((s: any) => ({ dato: s.dato, fuente: s.fuente, fecha: s.fecha, origen: s.origen }))} />
          {open.results.executive_summary && <pre className="mt-2 whitespace-pre-wrap text-xs">{open.results.executive_summary}</pre>}
        </Card>
      )}
    </>
  );
}
