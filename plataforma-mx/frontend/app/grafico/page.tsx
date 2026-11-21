"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Plot from "@/components/Plot";
import RequireAsset from "@/components/RequireAsset";
import { AuditInfo, Card, ErrorBox, Notice, Num, PageHeader, useRun } from "@/components/ui";
import { api, Calc } from "@/lib/api";
import { num } from "@/lib/format";

const COLORS: Record<string, string> = { confirmada: "#14B8A6", en_formacion: "#F59E0B", invalidada: "#94A3B8", vigente: "#2563EB" };

function View({ ticker, series }: { ticker: string; series: string }) {
  const [p, setP] = useState({ pivot_left: 5, pivot_right: 5, tolerance: 0.03, min_depth: 0.03 });
  const [px, setPx] = useState<any>(null);
  const [show, setShow] = useState<Record<string, boolean>>({});
  const [drawn, setDrawn] = useState<any[]>([]);
  const { data, error, busy, run } = useRun<Calc>();
  useEffect(() => {
    api.get(`/prices/${ticker}/${encodeURIComponent(series)}`).then(setPx).catch(() => setPx(null));
    try {
      setDrawn(JSON.parse(localStorage.getItem(`draw:${ticker}:${series}`) || "[]"));
    } catch {}
  }, [ticker, series]);
  const go = () => run(() => api.post("/patterns", { ticker, series, ...p }));
  const pats: any[] = data?.result.patterns ?? [];
  const rows = px?.rows ?? [];
  const shapes = useMemo(() => {
    const s: any[] = [];
    pats.forEach((f, i) => {
      if (show[i] === false) return;
      const c = COLORS[f.status] ?? "#64748B";
      if (f.level) s.push({ type: "line", xref: "paper", x0: 0, x1: 1, y0: f.level, y1: f.level, line: { color: c, dash: "dot", width: 1 } });
      if (f.confirmation_level && f.points?.length) s.push({ type: "line", x0: f.points[0].date, x1: rows.at(-1)?.date, y0: f.confirmation_level, y1: f.confirmation_level, line: { color: c, dash: "dash", width: 1 } });
    });
    return [...s, ...drawn];
  }, [pats, show, drawn, rows]);
  const traces = useMemo(() => {
    if (!rows.length) return [];
    const t: any[] = [{ type: "candlestick", x: rows.map((r: any) => r.date), open: rows.map((r: any) => r.open), high: rows.map((r: any) => r.high), low: rows.map((r: any) => r.low), close: rows.map((r: any) => r.close), name: ticker, increasing: { line: { color: "#14B8A6" } }, decreasing: { line: { color: "#E11D48" } } }];
    pats.forEach((f, i) => {
      if (show[i] === false || !f.points?.length) return;
      t.push({ type: "scatter", mode: "lines+markers", x: f.points.map((q: any) => q.date), y: f.points.map((q: any) => q.price), name: `${f.pattern} (${f.status})`, line: { color: COLORS[f.status] ?? "#64748B", width: 1.5 } });
    });
    return t;
  }, [rows, pats, show, ticker]);
  const layout = useMemo(() => ({ shapes, dragmode: "drawline", newshape: { line: { color: "#A855F7", width: 2 } }, xaxis: { rangeslider: { visible: false } } }), [shapes]);
  const config = useMemo(() => ({ modeBarButtonsToAdd: ["drawline", "drawrect", "eraseshape"] }), []);
  const onRelayout = useCallback(
    (e: any) => {
      if (e.shapes) {
        const user = e.shapes.filter((s: any) => s.line?.color === "#A855F7");
        setDrawn(user);
        try {
          localStorage.setItem(`draw:${ticker}:${series}`, JSON.stringify(user));
        } catch {}
      }
    },
    [ticker, series]
  );
  return (
    <>
      <Card title="Parámetros de detección">
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          <Num label="Pivote: barras izq." value={p.pivot_left} onChange={(v) => setP({ ...p, pivot_left: v })} step="1" />
          <Num label="Pivote: barras der." value={p.pivot_right} onChange={(v) => setP({ ...p, pivot_right: v })} step="1" />
          <Num label="Tolerancia de igualdad" value={p.tolerance} onChange={(v) => setP({ ...p, tolerance: v })} />
          <Num label="Profundidad mínima" value={p.min_depth} onChange={(v) => setP({ ...p, min_depth: v })} />
        </div>
        <button className="btn mt-3" onClick={go} disabled={busy}>
          Detectar figuras
        </button>
        <ErrorBox error={error} />
      </Card>
      <Card title="Gráfico interactivo" className="mt-4">
        {!rows.length ? (
          <Notice tone="warn">Sin precios cargados para el activo.</Notice>
        ) : (
          <>
            <Plot data={traces} layout={layout} config={config} height={520} onRelayout={onRelayout} />
            <p className="text-xs text-slate-500">
              Dibujo manual: use las herramientas de línea/rectángulo de la barra del gráfico (se guardan en este navegador). {drawn.length} trazos manuales.{" "}
              <button className="underline" onClick={() => { setDrawn([]); try { localStorage.removeItem(`draw:${ticker}:${series}`); } catch {} }}>
                Borrar trazos
              </button>
            </p>
          </>
        )}
      </Card>
      {pats.length > 0 && (
        <Card title="Figuras (criterios, puntos, confirmación e invalidación)" className="mt-4">
          <div className="max-h-96 overflow-auto">
            <table className="tbl">
              <thead>
                <tr>{["Ver", "Figura", "Estado", "Puntos", "Confirmación", "Invalidación", "Criterio"].map((h) => <th key={h}>{h}</th>)}</tr>
              </thead>
              <tbody>
                {pats.map((f, i) => (
                  <tr key={i}>
                    <td><input type="checkbox" checked={show[i] !== false} onChange={(e) => setShow({ ...show, [i]: e.target.checked })} /></td>
                    <td>{f.pattern}</td>
                    <td style={{ color: COLORS[f.status] }}>{f.status}</td>
                    <td>{(f.points ?? []).map((q: any) => `${String(q.date).slice(0, 10)}@${num(q.price)}`).join(" · ") || "—"}</td>
                    <td>{num(f.confirmation_level ?? f.level)}</td>
                    <td>{num(f.invalidation_level)}</td>
                    <td className="max-w-xs">{f.criteria}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-1 text-xs text-slate-500">{data?.result.disclaimer}</p>
          <AuditInfo calc={data} />
        </Card>
      )}
    </>
  );
}

export default function Grafico() {
  return (
    <>
      <PageHeader title="Análisis gráfico — chartismo" subtitle="Detección algorítmica de doble techo/suelo, HCH (e invertido), triángulos, banderas, banderines, canales, cuñas, soportes y resistencias, con dibujo manual." />
      <RequireAsset>{(a) => <View {...a} />}</RequireAsset>
    </>
  );
}
