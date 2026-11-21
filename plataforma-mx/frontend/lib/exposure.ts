"use client";
export type EquityExposureForm = {
  kind: "equity";
  ticker: string;
  series: string;
  shares: number;
  declared: boolean;
  horizon_years: number;
  r: number;
  r_origin: string;
  q: number;
  sigma: number | null;
  sigma_origin: string | null;
  multiplier: number;
  option_expiry_years: number | null;
  templates: string[];
  commission_per_contract: number;
  futures_symbol: string | null;
  futures_price: number | null;
  futures_price_source: string | null;
  budget: number | null;
  objective: string;
};

export type RateExposureForm = {
  kind: "rate";
  curve_id: number;
  side: "pasivo" | "activo";
  notional: number;
  currency: string;
  reference_rate: string;
  spread: number;
  start: string;
  end: string;
  frequency: string;
  day_count: string;
  rate_style: string;
  declared: boolean;
  model: string;
  vol: number;
  vol_origin: string;
  cap_strike: number | null;
  floor_strike: number | null;
};

export type ExposureForm = EquityExposureForm | RateExposureForm;

export function saveExposure(e: ExposureForm) {
  try {
    localStorage.setItem("lastExposure", JSON.stringify(e));
  } catch {}
}
export function loadExposure(): ExposureForm | null {
  try {
    return JSON.parse(localStorage.getItem("lastExposure") || "null");
  } catch {
    return null;
  }
}

/** Construye el cuerpo de la petición al motor de escenarios. */
export function scenarioRequest(e: ExposureForm, profiles: Record<string, any> = {}) {
  if (e.kind === "equity") {
    const { kind, ...rest } = e;
    return { path: "/scenarios/equity", body: { ...rest, profiles } };
  }
  const strikes: any = {};
  if (e.cap_strike !== null && Number.isFinite(e.cap_strike)) strikes.cap = e.cap_strike;
  if (e.floor_strike !== null && Number.isFinite(e.floor_strike)) strikes.floor = e.floor_strike;
  return {
    path: "/scenarios/rates",
    body: { curve_id: e.curve_id, kind: e.side, notional: e.notional, currency: e.currency, reference_rate: e.reference_rate, spread: e.spread, start: e.start, end: e.end, frequency: e.frequency, day_count: e.day_count, rate_style: e.rate_style, declared: e.declared, model: e.model, vol: e.vol, vol_origin: e.vol_origin, strikes: Object.keys(strikes).length ? strikes : null, profiles },
  };
}
