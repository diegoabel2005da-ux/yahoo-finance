"use client";
import { useEffect, useState } from "react";
import Plot from "@/components/Plot";
import { AuditInfo, Card, ErrorBox, Notice, Num, PageHeader, Select, Stat, Table, Text, Upload, useRun } from "@/components/ui";
import { api, Calc } from "@/lib/api";
import { useAsset } from "@/lib/asset";
import { money, num, pct } from "@/lib/format";

export default function Futuros() {
  const { asset } = useAsset();
  const [contracts, setContracts] = useState<any[]>([]);
  const load = () => api.get("/futures/contracts", { underlying: asset?.ticker }).then(setContracts).catch(() => setContracts([]));
  useEffect(() => {
    load();
  }, [asset]);
  const [f, setF] = useState<any>({ contract_symbol: "", contracts: 10, multiplier: 100, side: "short", f_initial: NaN, path: "", initial_margin_per_contract: NaN, maintenance_ratio: 0.8, commission_per_contract_side: 0, underlying_shares: 0, spot_initial: NaN, spot_final: NaN, stop: NaN, slippage_ticks: 1, tick: 0.01 });
  const set = (k: string) => (v: any) => setF({ ...f, [k]: v });
  const an = useRun<Calc>();
  const fin = (v: number) => (Number.isFinite(v) ? v : null);
  const go = () => {
    const path = f.path.split(/[\s,;]+/).filter(Boolean).map(Number);
    an.run(() =>
      api.post("/futures/analyze", {
        contracts: f.contracts, multiplier: f.multiplier, side: f.side, f_initial: f.f_initial, price_path: path,
        contract_symbol: f.contract_symbol || null, initial_margin_per_contract: fin(f.initial_margin_per_contract),
        margin_origin: "supuesto_del_usuario", maintenance_ratio: f.maintenance_ratio, commission_per_contract_side: f.commission_per_contract_side,
        underlying_shares: f.underlying_shares, spot_initial: fin(f.spot_initial), spot_final: fin(f.spot_final), stop: fin(f.stop), slippage_ticks: f.slippage_ticks, tick: f.tick,
      })
    );
  };
  const [c, setC] = useState<any>({ spot: NaN, r: NaN, T: 0.25, q: 0, divs_pv: 0, observed_futures: NaN });
  const carry = useRun<Calc>();
  const r = an.data?.result;
  return (
    <>
      <PageHeader title="Futuros" subtitle="Contratos realmente listados (importados de MexDer), P&L de posturas largas y cortas, AIMs, liquidación diaria, necesidades de liquidez y stop-loss hipotético. Los futuros no tienen estilo americano ni europeo." />
      <Card title={`Contratos listados importados ${asset ? `— ${asset.ticker}` : ""}`}>
        {contracts.length ? (
          <Table rows={contracts.map((x) => ({ símbolo: x.symbol, subyacente: x.underlying_ticker, vencimiento: x.expiry, multiplicador: x.multiplier, tick: x.tick_size, "valor tick": x.tick_value, moneda: x.currency, liquidación: x.settlement, AIM: x.initial_margin ?? "no importada", "AIM al": x.margin_as_of ?? "—", fuente: x.source, revisión: x.reviewed_on }))} />
        ) : (
          <Notice tone="warn">Sin contratos importados para este subyacente. Las fechas de vencimiento deben ser las contractuales publicadas por MexDer; la plataforma no las genera.</Notice>
        )}
        <div className="mt-3">
          <Upload endpoint="/futures/contracts/import" label="Especificaciones de contratos (MexDer)" template="futures_contracts_template.csv" onDone={load} />
        </div>
      </Card>
      <Card title="Análisis de postura" className="mt-4">
        <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
          <Select label="Contrato" value={f.contract_symbol} onChange={(v) => { const k = contracts.find((x) => x.symbol === v); setF({ ...f, contract_symbol: v, multiplier: k ? Number(k.multiplier) : f.multiplier, tick: k ? Number(k.tick_size) : f.tick }); }} options={[["", "Teórico (sin contrato)"], ...contracts.map((x) => [x.symbol, `${x.symbol} ${x.expiry}`] as [string, string])]} />
          <Select label="Postura" value={f.side} onChange={set("side")} options={[["long", "Compra"], ["short", "Venta"]]} />
          <Num label="Contratos" value={f.contracts} onChange={set("contracts")} />
          <Num label="Multiplicador" value={f.multiplier} onChange={set("multiplier")} />
          <Num label="Precio futuro inicial" value={f.f_initial} onChange={set("f_initial")} />
          <Text label="Trayectoria de precios futuros (liquidaciones)" value={f.path} onChange={set("path")} placeholder="p.ej. 101.2, 99.8, 98.5" />
          <Num label="AIM por contrato (si no importada)" value={f.initial_margin_per_contract} onChange={set("initial_margin_per_contract")} />
          <Num label="Mantenimiento / AIM (supuesto)" value={f.maintenance_ratio} onChange={set("maintenance_ratio")} />
          <Num label="Comisión por contrato y lado" value={f.commission_per_contract_side} onChange={set("commission_per_contract_side")} />
          <Num label="Acciones en posición subyacente" value={f.underlying_shares} onChange={set("underlying_shares")} />
          <Num label="Spot inicial" value={f.spot_initial} onChange={set("spot_initial")} />
          <Num label="Spot final" value={f.spot_final} onChange={set("spot_final")} />
          <Num label="Stop-loss hipotético" value={f.stop} onChange={set("stop")} />
          <Num label="Deslizamiento (ticks)" value={f.slippage_ticks} onChange={set("slippage_ticks")} />
        </div>
        <button className="btn mt-3" onClick={go} disabled={an.busy}>
          Analizar
        </button>
        <ErrorBox error={an.error} />
        {r && (
          <div className="mt-3 space-y-3">
            <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
              <Stat label="P&L bruto del futuro" value={money(r.gross_pnl)} />
              {r.combined && <Stat label="P&L subyacente" value={money(r.combined.underlying_pnl)} />}
              {r.combined && <Stat label="Resultado combinado" value={money(r.combined.combined_pnl)} />}
              {r.margin?.initial_margin !== undefined && <Stat label="AIM depositada (recuperable)" value={money(r.margin.initial_margin)} sub={r.margin.margin_origin} />}
              {r.margin?.total_margin_calls !== undefined && <Stat label="Aportaciones adicionales" value={money(r.margin.total_margin_calls)} sub={`máx. efectivo comprometido ${money(r.margin.max_cash_committed)}`} />}
            </div>
            {r.margin?.daily && (
              <>
                <Plot data={[{ type: "bar", x: r.margin.daily.map((d: any) => d.t), y: r.margin.daily.map((d: any) => d.variation_margin), name: "Liquidación diaria", marker: { color: r.margin.daily.map((d: any) => (d.variation_margin >= 0 ? "#14B8A6" : "#E11D48")) } }, { x: r.margin.daily.map((d: any) => d.t), y: r.margin.daily.map((d: any) => d.balance), name: "Saldo de garantías", yaxis: "y2", line: { color: "#0B1F3A" } }]} layout={{ yaxis2: { overlaying: "y", side: "right" } }} height={260} />
                <Table rows={r.margin.daily} />
                <p className="text-xs text-slate-500">{r.margin.note} Comisiones: {money(r.margin.commissions)} · P&L neto: {money(r.margin.net_pnl)}</p>
              </>
            )}
            {r.margin?.status === "no_disponible" && <Notice tone="warn">{r.margin.reason}</Notice>}
            {r.stop_loss && <Notice tone="warn">Stop-loss: {r.stop_loss.stopped ? `ejecutado en paso ${r.stop_loss.step} a ${num(r.stop_loss.fill)} (brecha vs stop ${num(r.stop_loss.gap_vs_stop)}), P&L ${money(r.stop_loss.pnl)}. ${r.stop_loss.warning}` : `no activado; P&L ${money(r.stop_loss.pnl)}`}</Notice>}
            <p className="text-xs text-slate-500">Estilo de ejercicio: {r.exercise_style}. Contrato: {r.contract.symbol ?? r.contract.status}</p>
            <AuditInfo calc={an.data} />
          </div>
        )}
      </Card>
      <Card title="Precio teórico por costo de acarreo" className="mt-4">
        <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
          <Num label="Spot" value={c.spot} onChange={(v) => setC({ ...c, spot: v })} />
          <Num label="r (continua)" value={c.r} onChange={(v) => setC({ ...c, r: v })} />
          <Num label="T (años)" value={c.T} onChange={(v) => setC({ ...c, T: v })} />
          <Num label="q" value={c.q} onChange={(v) => setC({ ...c, q: v })} />
          <Num label="VP dividendos" value={c.divs_pv} onChange={(v) => setC({ ...c, divs_pv: v })} />
          <Num label="Futuro observado (opcional)" value={c.observed_futures} onChange={(v) => setC({ ...c, observed_futures: v })} />
        </div>
        <button className="btn mt-2" onClick={() => carry.run(() => api.post("/futures/carry", { ...c, observed_futures: Number.isFinite(c.observed_futures) ? c.observed_futures : null }))}>
          Calcular
        </button>
        <ErrorBox error={carry.error} />
        {carry.data && (
          <p className="mt-2 text-sm">
            Precio teórico: <b>{num(carry.data.result.theoretical_price, 4)}</b> (resultado de modelo, no cotización)
            {carry.data.result.implied_carry !== undefined && <> · Acarreo implícito en el futuro observado: {pct(carry.data.result.implied_carry, 3)} · Base: {num(carry.data.result.basis, 4)}</>}
          </p>
        )}
      </Card>
    </>
  );
}
