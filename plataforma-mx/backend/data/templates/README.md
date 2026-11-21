# Plantillas de importación

Las plantillas contienen sólo encabezados: la plataforma no incluye datos precargados.
Cada renglón debe provenir de una fuente verificable (BMV, BIVA, MexDer, CNBV, Banxico,
INEGI o reportes oficiales de la emisora) y declarar su procedencia.

| Archivo | Valores controlados |
|---|---|
| catalog_template.csv | `exchange`: BMV/BIVA · `derivatives`: `futuro`, `opcion` o `futuro\|opcion` · `active`: true/false |
| prices_template.csv | `price_type`: spot, ultimo_negociado, cierre_oficial, cierre_ajustado, precio_colocacion, precio_futuro, precio_liquidacion, prima_observada · `freshness`: tiempo_real, retrasado, intradia, preliminar, oficial_cierre, historico, desactualizado · `origin`: observado_fuente_oficial, observado_proveedor_secundario, declarado_por_usuario · `precision`: decimales publicados · `data_version`: incremente para correcciones oficiales |
| rates_template.csv | `value_pct` en porcentaje tal como se publica · `origin` como arriba |
| curve_template.csv | `days` desde la fecha de la curva; `value` tasa cero (%) o factor de descuento, según el formulario |
| futures_contracts_template.csv | `settlement`: fisica/financiera · `initial_margin`: AIM publicada (opcional) — no incluya estilo de ejercicio |
| option_contracts_template.csv | `option_type`: call/put · `style`: europea/americana |
| financials_template.csv | `statement`: income/balance/cashflow · `period_type`: Q/FY · `basis`: consolidado/individual. Partidas reconocidas: revenue, gross_profit, ebitda, ebit, net_income, interest_expense, depreciation_amortization, total_assets, current_assets, inventories, cash, total_liabilities, current_liabilities, total_debt, total_equity, minority_interest, cfo, cfi, cff, capex, dividends_paid |
