"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Card, Notice, PageHeader, Table } from "@/components/ui";
import { api } from "@/lib/api";
import { MENU } from "@/components/Shell";

export default function Home() {
  const [sources, setSources] = useState<any[] | null>(null);
  const [cat, setCat] = useState<any>(null);
  const [disc, setDisc] = useState<any[]>([]);
  const [audit, setAudit] = useState<any[]>([]);
  const [seed, setSeed] = useState<any>(null);
  const [adminReq, setAdminReq] = useState(false);
  const [token, setToken] = useState("");
  const [hasToken, setHasToken] = useState(false);
  const loadSeed = () => api.get("/seed/status").then(setSeed).catch(() => {});
  useEffect(() => {
    api.get("/sources/status").then(setSources).catch(() => setSources([]));
    api.get("/catalog").then(setCat).catch(() => {});
    api.get("/discrepancies").then(setDisc).catch(() => {});
    api.get("/audit", { limit: 10 }).then(setAudit).catch(() => {});
    loadSeed();
    api.get("/admin/status").then((d) => setAdminReq(d.admin_token_required)).catch(() => {});
    try { setHasToken(!!localStorage.getItem("adminToken")); } catch {}
  }, []);
  const saveToken = () => { try { token ? localStorage.setItem("adminToken", token) : localStorage.removeItem("adminToken"); setHasToken(!!token); setToken(""); } catch {} };
  useEffect(() => {
    if (!seed || !["en curso", "pendiente"].some((x) => seed.local === x || seed.online === x)) return;
    const t = setTimeout(loadSeed, 4000);
    return () => clearTimeout(t);
  }, [seed]);
  return (
    <>
      <PageHeader title="Inicio" subtitle="Primero comprender y cuantificar el riesgo; después construir y comparar las alternativas de cobertura. Todas las cifras muestran su fuente, fecha y estado de validación." />
      <div className="grid gap-4 md:grid-cols-3">
        <Card title="Catálogo">
          {cat?.revision ? (
            <p className="text-sm">
              Revisión #{cat.revision.id} · {cat.revision.source}
              <br />
              <span className="text-xs text-slate-500">Importada {String(cat.revision.imported_at).slice(0, 19)} · {cat.instruments.length} emisoras/series</span>
            </p>
          ) : (
            <Notice tone="warn">Catálogo vacío. Importe la relación vigente de subyacentes de MexDer en «Emisoras». La plataforma no precarga emisoras.</Notice>
          )}
        </Card>
        <Card title="Integridad de datos">
          <p className="text-sm">
            Discrepancias abiertas: <b className={disc.length ? "text-red-600" : ""}>{disc.length}</b>
          </p>
          <p className="text-xs text-slate-500">Las discrepancias bloquean los cálculos críticos del instrumento hasta documentar su resolución.</p>
        </Card>
        <Card title="Recorridos">
          <ol className="list-decimal space-y-0.5 pl-5 text-xs">
            <li>Acciones: emisora → históricos → análisis → riesgos → exposición → derivados → estrategias → escenarios → informe.</li>
            <li>Tasas: tasa → exposición → curva → cap/floor → sensibilidades → escenarios → informe.</li>
          </ol>
        </Card>
      </div>
      {adminReq && (
        <Card title="Token de administrador" className="mt-4">
          <p className="text-xs text-slate-600 dark:text-slate-400">Esta instalación es pública: consultar y calcular está abierto, pero importar o actualizar datos requiere el token de administrador. Se guarda sólo en este navegador.</p>
          <div className="mt-2 flex flex-wrap items-end gap-2">
            <input className="input max-w-xs" type="password" placeholder={hasToken ? "Token guardado en este navegador" : "Pegue el token"} value={token} onChange={(e) => setToken(e.target.value)} />
            <button className="btn" onClick={saveToken}>{token ? "Guardar token" : hasToken ? "Quitar token" : "Guardar token"}</button>
            <span className="text-xs">{hasToken ? "✓ Modo administrador activo en este navegador" : "Modo de sólo consulta"}</span>
          </div>
        </Card>
      )}
      <Card title="Datos de la plataforma" className="mt-4" actions={
        <button className="btn" disabled={seed?.online === "en curso"} onClick={() => api.post("/seed/refresh", {}).then(loadSeed)}>
          {seed?.online === "en curso" ? "Actualizando…" : "Actualizar todos los datos (en línea)"}
        </button>}>
        <p className="text-sm">Carga local del repositorio (catálogo, boletines de MexDer, AIM): <b>{seed?.local ?? "—"}</b> · Actualización en línea (Yahoo, Banxico, curva): <b>{seed?.online ?? "—"}</b></p>
        <p className="text-xs text-slate-500">Al iniciar con una base vacía se cargan automáticamente los datos semilla del repositorio. La actualización en línea descarga precios, estados financieros, dividendos y splits de Yahoo, series de Banxico y la curva gubernamental (varios minutos). Mientras no se suba un archivo más reciente, las AIM de octubre de 2026 son la referencia vigente y se muestran con su periodo.</p>
        {seed?.log?.length > 0 && <pre className="mt-2 max-h-40 overflow-auto rounded bg-slate-100 p-2 text-[11px] dark:bg-navy-950">{seed.log.slice(-15).join("\n")}</pre>}
      </Card>
      <Card title="Fuentes oficiales — conectividad" className="mt-4">
        {sources === null ? (
          <p className="text-sm text-slate-500">Verificando…</p>
        ) : (
          <Table
            rows={sources.map((s) => ({ fuente: s.source, url: s.url, accesible: s.reachable ? "sí" : "no", detalle: s.reachable ? s.status_code : s.error ?? s.status_code, acceso: s.access, alternativa: s.fallback ?? "" }))}
          />
        )}
        <p className="mt-2 text-xs text-slate-500">Cuando una fuente no es accesible o requiere licencia, los datos se incorporan mediante importación validada de CSV/Excel; nunca se sustituyen por cifras inventadas.</p>
      </Card>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <Card title="Módulos">
          <div className="grid grid-cols-2 gap-1 text-sm">
            {MENU.slice(1).map(([h, l]) => (
              <Link key={h} href={h} className="rounded px-2 py-1 hover:bg-slate-100 dark:hover:bg-navy-800">
                {l}
              </Link>
            ))}
          </div>
        </Card>
        <Card title="Cálculos recientes (auditables)">
          <Table rows={audit.map((a) => ({ id: a.id, calculo: a.calculation, fecha: String(a.created_at).slice(0, 19), digest: a.digest.slice(0, 12) }))} />
        </Card>
      </div>
    </>
  );
}
