"use client";
import { useEffect, useRef } from "react";

/** Envoltorio de Plotly cargado dinámicamente en el cliente. */
export default function Plot({ data, layout = {}, height = 360, config = {}, onRelayout }: { data: any[]; layout?: any; height?: number; config?: any; onRelayout?: (e: any) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let cancelled = false;
    let plotly: any;
    (async () => {
      plotly = (await import("plotly.js-dist-min")).default;
      if (cancelled || !ref.current) return;
      const dark = document.documentElement.classList.contains("dark");
      const fg = dark ? "#CBD5E1" : "#334155";
      const grid = dark ? "#1E3A5F" : "#E2E8F0";
      await plotly.react(
        ref.current,
        data,
        {
          height,
          margin: { l: 56, r: 16, t: 28, b: 40 },
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          font: { color: fg, size: 11 },
          xaxis: { gridcolor: grid, ...(layout.xaxis ?? {}) },
          yaxis: { gridcolor: grid, ...(layout.yaxis ?? {}) },
          legend: { orientation: "h", y: -0.2 },
          ...layout,
        },
        { responsive: true, displaylogo: false, ...config }
      );
      if (onRelayout) (ref.current as any).on("plotly_relayout", onRelayout);
    })();
    return () => {
      cancelled = true;
    };
  }, [data, layout, height, config, onRelayout]);
  return <div ref={ref} className="w-full" />;
}
