"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAsset } from "@/lib/asset";

export const MENU: [string, string][] = [
  ["/", "Inicio"],
  ["/emisoras", "Emisoras"],
  ["/historicos", "Datos históricos"],
  ["/analisis", "Análisis y valuación"],
  ["/financieros", "Estados financieros"],
  ["/riesgos", "Patrones y riesgos"],
  ["/grafico", "Análisis gráfico"],
  ["/futuros", "Futuros"],
  ["/opciones", "Opciones"],
  ["/tasas", "Derivados de tasas"],
  ["/caps-floors", "Caps y floors"],
  ["/estrategias", "Estrategias"],
  ["/coberturas", "Coberturas"],
  ["/escenarios", "Perfiles y escenarios"],
  ["/reportes", "Reportes"],
  ["/estudios", "Estudios guardados"],
];

function AssetSelector() {
  const { asset, setAsset } = useAsset();
  const [list, setList] = useState<any[]>([]);
  useEffect(() => {
    api.get("/catalog").then((c) => setList(c.instruments)).catch(() => setList([]));
  }, []);
  return (
    <select
      aria-label="Activo seleccionado"
      className="input max-w-xs"
      value={asset ? `${asset.ticker}|${asset.series}` : ""}
      onChange={(e) => {
        const [t, s] = e.target.value.split("|");
        const i = list.find((x) => x.ticker === t && x.series === s);
        setAsset(t ? { ticker: t, series: s, issuer_name: i?.issuer_name } : null);
      }}
    >
      <option value="">{list.length ? "Seleccione emisora/serie…" : "Catálogo vacío: importe el universo MexDer"}</option>
      {list.map((i) => (
        <option key={i.id} value={`${i.ticker}|${i.series}`}>
          {i.ticker} {i.series} — {i.issuer_name} {i.active ? "" : "(no vigente)"}
        </option>
      ))}
    </select>
  );
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const [dark, setDark] = useState(false);
  useEffect(() => {
    let d = false;
    try {
      d = localStorage.getItem("theme") === "dark" || (!localStorage.getItem("theme") && matchMedia("(prefers-color-scheme: dark)").matches);
    } catch {}
    setDark(d);
    document.documentElement.classList.toggle("dark", d);
  }, []);
  const toggle = () => {
    const d = !dark;
    setDark(d);
    document.documentElement.classList.toggle("dark", d);
    try {
      localStorage.setItem("theme", d ? "dark" : "light");
    } catch {}
  };
  return (
    <div className="flex min-h-screen">
      <aside className={`${open ? "block" : "hidden"} fixed inset-y-0 z-30 w-60 overflow-y-auto bg-navy-900 text-slate-200 md:static md:block`}>
        <div className="border-b border-navy-700 px-4 py-4">
          <div className="text-sm font-bold tracking-wide text-white">PLATAFORMA MX</div>
          <div className="text-[10px] uppercase tracking-widest text-turq">Análisis · Valuación · Coberturas</div>
        </div>
        <nav className="py-2">
          {MENU.map(([href, label], i) => {
            const active = href === "/" ? path === "/" : path.startsWith(href);
            return (
              <Link key={href} href={href} onClick={() => setOpen(false)} className={`flex items-center gap-2 px-4 py-1.5 text-sm ${active ? "border-l-2 border-turq bg-navy-800 text-white" : "border-l-2 border-transparent hover:bg-navy-800"}`}>
                <span className="w-5 text-right font-mono text-[10px] text-slate-500">{i + 1}</span>
                {label}
              </Link>
            );
          })}
        </nav>
        <p className="px-4 pb-4 text-[10px] leading-snug text-slate-400">Herramienta de análisis e investigación. No ejecuta órdenes ni constituye recomendación.</p>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex flex-wrap items-center gap-2 border-b border-slate-200 bg-white/90 px-4 py-2 backdrop-blur dark:border-navy-700 dark:bg-navy-900/90">
          <button className="btn-ghost md:hidden" onClick={() => setOpen(!open)} aria-label="Menú">
            ☰
          </button>
          <AssetSelector />
          <div className="ml-auto flex items-center gap-2">
            <button className="btn-ghost" onClick={toggle} aria-label="Cambiar tema">
              {dark ? "Modo claro" : "Modo oscuro"}
            </button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 p-4">{children}</main>
      </div>
    </div>
  );
}
