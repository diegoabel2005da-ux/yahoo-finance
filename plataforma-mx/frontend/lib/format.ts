const z = (v: number, d = 2) => (Math.abs(v) < 0.5 * 10 ** -d ? 0 : v);
const nf = (d: number) => new Intl.NumberFormat("es-MX", { minimumFractionDigits: d, maximumFractionDigits: d });
export const num = (v: any, d = 2) => (v === null || v === undefined || Number.isNaN(v) ? "—" : nf(d).format(z(Number(v), d)));
export const pct = (v: any, d = 2) => (v === null || v === undefined || Number.isNaN(v) ? "—" : nf(d).format(Number(v) * 100) + " %");
export const money = (v: any, cur = "MXN") => (v === null || v === undefined ? "—" : `${nf(2).format(z(Number(v)))} ${cur}`);
export const SCENARIOS = ["estres_adverso_severo", "adverso_moderado", "base", "favorable_moderado", "favorable_extremo"] as const;
export const SCEN_LABEL: Record<string, string> = {
  estres_adverso_severo: "Estrés adverso severo",
  adverso_moderado: "Adverso moderado",
  base: "Base / estabilidad",
  favorable_moderado: "Favorable moderado",
  favorable_extremo: "Favorable extremo",
};
export const ORIGIN_LABEL: Record<string, string> = {
  observado_fuente_oficial: "Oficial / referencia",
  observado_proveedor_secundario: "Proveedor secundario",
  declarado_por_usuario: "Declarado",
  supuesto_del_usuario: "Supuesto",
  resultado_de_modelo: "Teórico (modelo)",
};
