# Prompts para construir «Plataforma MX» en Base44

## Cómo usar este documento

1. En Base44 crea una app nueva y pega el **PROMPT 1 (maestro)**. Espera a que termine de construir.
2. Importa los CSV de la carpeta `datos/` en las entidades indicadas (ver «Importación de datos», al final).
3. Pega los **PROMPTS 2 a 8**, uno por uno, en el chat de la misma app. Revisa cada fase antes de pasar a la siguiente.
4. En la configuración de la app (Secrets), agrega `BANXICO_TOKEN` con tu token del SIE de Banxico.
5. Ejecuta el **PROMPT 9 (verificación)**. Si algún valor de referencia no coincide, pídele a Base44 que lo corrija antes de usar la app.

Los CSV ya están validados: strikes corregidos, alias del boletín resueltos, AIM asignadas y escalas verificadas por dos métodos independientes. **No le pidas a Base44 que vuelva a leer los PDF de MexDer**: el boletín publica algunos strikes divididos entre 100 y usa nombres distintos a los del catálogo, y una lectura automática sin esas reglas produce datos erróneos.

---

## PROMPT 1 — Maestro: contexto, reglas y estructura

```
Construye una aplicación web profesional en ESPAÑOL llamada «Plataforma MX»: análisis financiero, valuación, derivados y coberturas del mercado mexicano. Es una herramienta de análisis e investigación de uso personal: NO ejecuta órdenes, NO promete resultados, NO presenta simulaciones como cotizaciones oficiales.

PRINCIPIO RECTOR: primero comprender y cuantificar el riesgo; después construir y comparar alternativas de cobertura.

REGLAS DE VERACIDAD (obligatorias en toda la app):
1. Nunca inventar cifras. Si falta un dato, mostrar «No disponible» y explicar qué falta. Nunca rellenar, interpolar ni estimar datos faltantes en silencio.
2. Cada cifra mostrada indica su FUENTE, FECHA y ORIGEN. Orígenes posibles: «Oficial / referencia» (dato observado: MexDer, Banxico, Yahoo Finance designado por el usuario como fuente de referencia), «Supuesto» (lo indica el usuario), «Teórico (modelo)» (resultado de un cálculo). Mostrar el origen como una etiqueta de color.
3. Nunca confundir precio de cierre, precio de liquidación, prima observada y prima teórica. Un precio teórico jamás se etiqueta como observado.
4. La volatilidad implícita sólo se calcula a partir de primas OBSERVADAS (precio de liquidación de MexDer). Nunca a partir de una prima teórica.
5. La AIM (aportación inicial mínima) es una GARANTÍA recuperable, no un costo.
6. Los futuros no son «americanos» ni «europeos». Las opciones sobre acciones de MexDer son americanas; las de IPC y dólar, europeas.
7. Caps y floors se presentan como instrumentos OTC teóricos: nunca afirmar que cotizan en MexDer.
8. Los escenarios son hipótesis de simulación: nunca asignarles probabilidades.
9. Toda operación de cálculo guarda un registro de auditoría (entradas, parámetros, fórmula, resultado, fecha).

DISEÑO: estilo terminal financiera profesional. Colores: azul marino #0B1F3A (barra lateral, encabezados), blanco, grises, turquesa #14B8A6 (acentos). Rojo sólo para pérdidas o alertas, siempre acompañado de texto. Modo claro y oscuro. Responsive. Tablas compactas con números alineados a la derecha y formato es-MX. Gráficos interactivos (Recharts o Plotly). Pie de página: «Herramienta de análisis e investigación. No ejecuta órdenes ni constituye recomendación».

MENÚ LATERAL (16 secciones, en este orden): 1 Inicio · 2 Emisoras · 3 Datos históricos · 4 Análisis y valuación · 5 Estados financieros · 6 Patrones y riesgos · 7 Análisis gráfico · 8 Futuros · 9 Opciones · 10 Derivados de tasas · 11 Caps y floors · 12 Estrategias · 13 Coberturas · 14 Perfiles y escenarios · 15 Reportes · 16 Estudios guardados.

SELECTOR GLOBAL: arriba de todas las páginas, un selector persistente de emisora+serie (p. ej. «WALMEX *», «AMX B»). Una emisora puede tener varias series: son instrumentos distintos.

ENTIDADES (crea exactamente estas, con estos campos):
- Instrument: ticker, series, issuer_name, sector, exchange, currency, derivatives (texto: «futuro», «opcion» o «futuro|opcion»), active (bool), yahoo_symbol, catalog_source, reviewed_on (fecha).
- PriceBar: ticker, series, fecha, open, high, low, close, adj_close, volume, fuente. (Un renglón por sesión. «close» es el cierre de referencia; «adj_close» el cierre ajustado por dividendos.)
- FuturesContract: symbol, underlying_ticker, expiry, multiplier, tick_size, tick_value, tipo_liquidacion, precio_liquidacion, liquidacion_anterior, interes_abierto, fecha_liquidacion, aim_larga, aim_corta, aim_periodo, notas, fuente.
- OptionSeries: underlying_ticker, underlying_series, option_type (call/put), strike, strike_publicado, escala_strike, expiry, estilo, multiplier, tipo_liquidacion, precio_liquidacion, liquidacion_anterior, interes_abierto, fecha_liquidacion, aim_corta, aim_larga, aim_periodo, notas.
- RateObservation: rate_code, rate_name, market_date, valor_pct, convencion, fuente.
- CurvePoint: curva, fecha_curva, dias, valor, tipo_valor (discount_factor o zero_rate), capitalizacion, base, interpolacion, fuente.
- FinancialItem: ticker, estado (income/balance/cashflow), periodo (FY/Q), fecha_cierre, base, moneda, partida, valor, fuente.
- CorporateAction: ticker, series, tipo (dividendo/split), fecha_ex, valor, moneda, fuente.
- Exposure: tipo (accion/pasivo_tasa/activo_tasa), declarada (bool), datos (JSON), creado.
- Study: titulo, version, calculos (JSON), resumen, creado.
- AuditLog: calculo, entradas (JSON), parametros (JSON), formulas (texto), resultado (JSON), fuentes (JSON), creado.

En esta primera fase construye: la estructura, el menú, el selector global, el modo claro/oscuro, las entidades, y las páginas 1 (Inicio) y 2 (Emisoras):
- Inicio: resumen del catálogo (número de instrumentos, fecha de revisión), fecha del último boletín de MexDer cargado (máximo de fecha_liquidacion), periodo de las AIM vigentes (aim_periodo), última fecha de precios y de tasas, y accesos a los módulos.
- Emisoras: tabla del catálogo con filtro, botón «Elegir» que fija el selector global, columnas: emisora, serie, sector, moneda, derivados, vigente, símbolo Yahoo, disponibilidad (precios / estados financieros / futuros / opciones: «✓» o «pendiente»). Al elegir una emisora, mostrar qué análisis están disponibles según los datos existentes.
```

---

## PROMPT 2 — Datos históricos y análisis técnico

```
Construye las páginas 3 (Datos históricos) y 4 (Análisis y valuación, parte técnica), usando la entidad PriceBar del instrumento seleccionado.

DATOS HISTÓRICOS
- Temporalidades: diaria, semanal, mensual, bimestral, trimestral, semestral, anual; rango de fechas personalizado.
- Agregación correcta: apertura = primera del periodo, máximo = máximo, mínimo = mínimo, cierre = último, volumen = suma; la fecha del renglón agregado es la ÚLTIMA sesión negociada del periodo. Bimestres y semestres calendario fijos (ene-feb, mar-abr…). Periodos sin datos se omiten.
- Fórmulas: rendimiento simple R_t = P_t/P_{t−1} − 1; logarítmico r_t = ln(P_t/P_{t−1}); acumulado P_t/P_0 − 1; drawdown P_t/max(P_s, s≤t) − 1.
- Volatilidad anualizada = desviación estándar MUESTRAL (n−1) de rendimientos logarítmicos × √(periodos por año): diaria 252, semanal 52, mensual 12, bimestral 6, trimestral 4, semestral 2, anual 1.
- Indicadores: último dato disponible y días hábiles de rezago, último cierre, variación, volatilidad, máximo/mínimo del histórico cargado, drawdown máximo con fechas pico→valle.
- Gráfico de velas + volumen; comparación de rendimiento acumulado contra el IPC (ticker «IPC», serie «*») sólo en fechas comunes (sin interpolar).
- Tabla de observaciones. Botón «Actualizar desde Yahoo» (se implementa en la fase 7).

ANÁLISIS TÉCNICO (todas las ventanas configurables; los primeros n−1 valores quedan vacíos, nunca inventados):
- ROC(n) = (P_t / P_{t−n} − 1) × 100. Mostrar cruces de cero.
- Williams %R(n) = −100 × (Máx_n − C) / (Máx_n − Mín_n); si Máx_n = Mín_n el valor es vacío.
- Estocástico: %K rápido = 100 × (C − Mín_k)/(Máx_k − Mín_k); %K lento = SMA(%K rápido, suavizado); %D = SMA(%K, d). Modalidades rápida y lenta.
- RSI 9, 14 y 25 con suavizado de WILDER: promedios iniciales = media simple de los primeros n cambios; después avg_t = (avg_{t−1}·(n−1) + x_t)/n; RSI = 100 − 100/(1 + avgGan/avgPerd); si avgPerd = 0 → 100.
- SMA 20/50/200 y EMA (α = 2/(n+1), sembrada con la SMA de los primeros n).
- Fibonacci: niveles 0, 23.6, 38.2, 50, 61.8, 78.6, 100 % y extensiones 127.2, 161.8, 200, 261.8 %. Tendencia alcista: nivel = Máx − f·(Máx − Mín). Anclas manuales o automáticas (último pivote fractal confirmado: máximo/mínimo estricto con L barras a la izquierda y R a la derecha; los últimos R datos no pueden confirmarse).
- Zonas de referencia (70/30, −20/−80) son descriptivas, no señales.
```

---

## PROMPT 3 — Estados financieros, ratios y DCF

```
Construye la página 5 (Estados financieros) y la parte de valuación de la página 4, usando FinancialItem, PriceBar, CorporateAction y RateObservation.

ESTADOS FINANCIEROS: pestañas Estado de resultados / Balance / Flujos; selector anual (FY) o trimestral (Q); vistas «cifras», «análisis horizontal» (variación vs periodo anterior) y «análisis vertical» (% de ingresos, de activo total o de flujo operativo). Mostrar moneda y fuente. Partidas: revenue, gross_profit, ebitda, ebit, net_income, interest_expense, depreciation_amortization, total_assets, current_assets, inventories, cash, total_liabilities, current_liabilities, total_debt, total_equity, minority_interest, shares_outstanding, cfo, cfi, cff, capex, dividends_paid.

RATIOS (calcular sólo si existen todos los insumos; si falta alguno, mostrar «no calculable» y cuáles faltan):
liquidez corriente = AC/PC; prueba ácida = (AC − inventarios)/PC; ROA = UN/activo total promedio; ROE = UN/capital promedio; ROIC = EBIT(1−t)/(deuda + capital − efectivo); márgenes bruto, operativo, neto y EBITDA sobre ingresos; deuda/capital; deuda neta/EBITDA = (deuda − efectivo)/EBITDA; cobertura de intereses = EBIT/gasto por intereses; payout = dividendos pagados/UN; P/E = precio/(UN/acciones); P/B = capitalización/capital; VE = capitalización + deuda neta + minoritario; VE/EBITDA; VE/ventas; rendimiento por dividendo = dividendos por acción de 12 meses / precio.
Insumos automáticos si el usuario no los da: precio = último close de PriceBar; acciones = shares_outstanding del balance; dividendo 12 meses = suma de CorporateAction tipo dividendo con fecha_ex en los 365 días previos al precio.
REGLA DE MONEDA: si los estados están en USD y el precio en MXN (CEMEX, GMEXICO, GRUMA, PE&OLES, ORBIA, VESTA, VOLAR, GISSA y los valores globales AAPL, META, NFLX, NVDA, TSLA), convertir el precio y los dividendos a USD con el tipo de cambio FIX (RateObservation rate_code «FIX») de la fecha del precio o la anterior más cercana, y decirlo en una nota. Si no hay FIX, NO calcular múltiplos de mercado.
Valores de control (cierre 2025-12-31, precio 54.42): WALMEX P/E ≈ 18.86, P/B ≈ 3.99, VE/EBITDA ≈ 9.65, rendimiento por dividendo ≈ 2.63 %, ROE ≈ 21.3 %.

DCF (FCFF) con supuestos editables por el usuario (etiquetados «Supuesto»): ingresos base, años, crecimiento, margen EBIT, tasa de impuestos, D&A/ingresos, CAPEX/ingresos, ΔCTN/Δingresos, deuda neta, acciones, minoritario.
FCFF_t = EBIT_t(1−t) + D&A_t − CAPEX_t − ΔCTN_t. Valor terminal Gordon = FCFF_N(1+g)/(WACC − g), exigir g < WACC; o múltiplo VE/EBITDA. VE = Σ FCFF_t/(1+WACC)^t + VT/(1+WACC)^N. Capital = VE − deuda neta − minoritario. Valor por acción = capital/acciones.
WACC directo o por CAPM: Ke = rf + β·prima de mercado + prima país + prima tamaño; WACC = E/V·Ke + D/V·Kd·(1−t).
Tabla de sensibilidad WACC × g. Leyenda obligatoria: «Valor teórico bajo los supuestos indicados; no implica que el precio de mercado lo alcanzará».
```

---

## PROMPT 4 — Patrones, riesgos y chartismo

```
Construye las páginas 6 (Patrones y riesgos) y 7 (Análisis gráfico).

RIESGO (frecuencia y fechas configurables):
- Volatilidad anualizada, drawdown máximo, asimetría, curtosis en exceso.
- VaR histórico (nivel c, p. ej. 95 %) = −cuantil_{1−c} de los rendimientos simples (interpolación lineal); ES histórico = −media de los rendimientos ≤ −VaR. Exigir al menos 20 observaciones.
- VaR paramétrico normal = −(μ + σ·z_{1−c}); ES normal = −μ + σ·φ(z_c)/(1−c).
- Beta contra el IPC sólo con fechas comunes: β = Cov(Ra, Rm)/Var(Rm) (muestral), con α, R², error estándar y número de observaciones. «Beta general» = últimos 2 años; «beta personalizada» = intervalo elegido. Valor de control: WALMEX vs IPC, 2 años diarios ≈ 0.76, R² ≈ 0.23.
- Liquidez: volumen e importe promedio de 20 sesiones, días sin operación, iliquidez de Amihud = media(|R_t|/importe_t).
- Leyenda: «Medidas históricas; no son predicciones».

TENDENCIAS (reglas visibles): primaria SMA200, secundaria SMA50, corto plazo SMA20. Alcista si precio > SMA y la pendiente de la SMA en 20 barras es > 0; bajista si precio < SMA y pendiente < 0; en otro caso lateral. Regresión log-lineal con R².

CHARTISMO sobre pivotes fractales (L y R configurables, tolerancia y profundidad mínima configurables): doble techo, doble suelo, hombro-cabeza-hombro y su inverso, triángulos (ascendente, descendente, simétrico), canales, cuñas, banderas y banderines, soportes y resistencias (agrupar pivotes a ±tolerancia con ≥2 toques). Cada figura muestra: criterio de detección, puntos con fechas, nivel de confirmación, nivel de invalidación y estado (en formación / confirmada / invalidada). En el gráfico de velas, dibujar las figuras y permitir dibujo manual de líneas y rectángulos (guardado en el navegador). Leyenda: «Figuras descriptivas; no son señales de operación».
```

---

## PROMPT 5 — Futuros y opciones

```
Construye las páginas 8 (Futuros) y 9 (Opciones) usando FuturesContract y OptionSeries.

FUTUROS
- Tabla de contratos listados del subyacente seleccionado: símbolo, vencimiento, precio de liquidación, liquidación anterior, interés abierto, fecha, multiplicador, puja, tipo de liquidación (física/financiera), AIM larga, AIM corta, periodo de la AIM, notas.
- Análisis de postura: compra o venta, número de contratos, precio inicial (precargado con el precio de liquidación al elegir el contrato), trayectoria de precios.
  P&L largo = n·M·(F_final − F_inicial); corto = −n·M·(F_final − F_inicial).
  Liquidación diaria: variación = signo·n·M·(F_t − F_{t−1}); si el saldo de garantías cae debajo del mantenimiento (fracción configurable de la AIM), aportación adicional hasta la AIM. AIM depositada = AIM del LADO elegido (larga o corta) × contratos. Mostrar aportaciones adicionales, efectivo máximo comprometido, comisiones, P&L neto y la nota «La AIM es una garantía recuperable». Resultado combinado con la posición en acciones si el usuario la indica.
  Valor de control: 10 contratos WALMEX DC26 en venta → AIM depositada 5,517.84 MXN; en compra 4,751.85 MXN.
- Stop-loss hipotético: si la trayectoria cruza el stop, la ejecución es al precio de cruce (con brecha) menos el deslizamiento en pujas; advertir que en el mercado real puede no ejecutarse al precio objetivo.
- Precio teórico por acarreo F = (S − VP dividendos)·e^{(r−q)T}, etiquetado «Teórico», y acarreo implícito ln(F/S)/T de un futuro observado.

OPCIONES
- Lista de series del subyacente con filtro por vencimiento: tipo, strike, strike publicado, vencimiento, precio de liquidación, liquidación anterior, interés abierto, AIM corta, estilo, multiplicador. Botón «Valorar» que precarga strike, plazo (días al vencimiento/365 desde fecha_liquidacion), estilo, multiplicador, prima observada (= precio de liquidación, origen «Oficial») y spot (último close de la misma fecha).
- Black-Scholes-Merton con dividendo continuo q: C = S·e^{−qT}·N(d1) − K·e^{−rT}·N(d2); P = K·e^{−rT}·N(−d2) − S·e^{−qT}·N(−d1); d1 = [ln(S/K) + (r − q + σ²/2)T]/(σ√T); d2 = d1 − σ√T. Griegas: delta, gamma, theta por año y por día (/365), vega y rho por 1.00 y por 1 punto porcentual (/100).
- Cox-Ross-Rubinstein (europea y AMERICANA): u = e^{σ√Δt}, d = 1/u, p = (e^{(r−q)Δt} − d)/(u − d); exigir 0 < p < 1. Ejercicio anticipado nodo por nodo. Árbol visible (≤12 pasos) con nodos de ejercicio anticipado resaltados. Tabla de convergencia vs BSM (10, 50, 100, 250, 500 pasos).
- Volatilidad implícita a partir de la prima OBSERVADA: primero validar cotas de no arbitraje (call europea en [max(S·e^{−qT} − K·e^{−rT}, 0), S·e^{−qT}]; americanas además ≥ valor intrínseco); luego Brent o bisección sobre σ. Para americanas con CRR, el límite inferior de σ debe ser max(0.0001, 1.05·|r − q|·√(T/pasos)) para que p sea válida. Si la prima viola las cotas, explicar «fuera de cotas de no arbitraje» (puede deberse a que el precio del subyacente difiere del de referencia de MexDer).
- Posiciones básicas long/short call/put: punto de equilibrio, pérdida y ganancia máximas (o «ilimitada»), garantías si es corta. Gráfico de resultado al vencimiento y, para europeas, revaluación previa con BSM (nunca usar el payoff terminal para valorar antes del vencimiento).
Valores de control: BSM S=42, K=40, r=10 %, σ=20 %, T=0.5 → call 4.7594, put 0.8086. CRR put americana S=50, K=50, r=10 %, σ=40 %, T=5/12, 5 pasos → 4.49. WALMEX call dic-2026 K=55 con liquidación 1.19, S=54.42, r=6.26 %, T=28/365, americana → volatilidad implícita ≈ 22 %.
```

---

## PROMPT 6 — Tasas, curvas, caps y floors

```
Construye las páginas 10 (Derivados de tasas) y 11 (Caps y floors) con RateObservation y CurvePoint.

TASAS: lista de series (TIIE_28, TIIE_91, TIIE_182, TIIE_FONDEO, TASA_OBJETIVO, CETES_28/91/182/364, BONO_M_3A/5A/10A/20A/30A, FIX) con primer y último dato; gráfico por serie con convención y fuente.
CURVAS: selector de curva (CurvePoint agrupado por «curva»); gráfico de tasa cero continua y forwards de 28 días; tabla de nodos (días, tasa cero, factor de descuento). Convertir: DF → cero continua z = −ln(DF)/t con t = días/365. Interpolación log-lineal en DF (forward constante por tramos). Fuera del último nodo: tasa plana y ADVERTENCIA visible.
Botón «Construir curva gubernamental»: CETES (simple ACT/360: DF = 1/(1 + y·d/360)) + Bonos M tratados como tasas PAR con cupón semestral de 182 días (c = y·182/360) por bootstrapping: DF_k = (1 − c·Σ_{j<k} DF_j)/(1 + c), con la tasa par interpolada linealmente entre nodos (la tasa par a 364 días se deriva de los CETES). Por omisión hasta 20 años; el nodo de 30 años es opcional y debe mostrar ADVERTENCIA, porque produce forwards inestables (con los datos de nov-2026 llegan a ~21.6 % a 29-30 años). Reportar la forward máxima y marcar tramos cuya forward supere en más de 3 puntos la tasa cero máxima previa. Rechazar subastas con más de 10 días (CETES) o 60 días (Bonos) de antigüedad.

CAPS Y FLOORS (OTC teóricos; leyenda obligatoria «No se afirma que coticen en MexDer»):
- Calendario: periodos de 28D, 91D, 182D o meses; base ACT/360 por defecto; ajuste de días hábiles «modified following» con calendario mexicano por reglas (1-ene, 1er lunes de feb, 3er lunes de mar, jueves y viernes santos, 1-may, 16-sep, 2-nov, 3er lunes de nov, 12-dic, 25-dic), marcado como aproximado.
- Caplet = N·α·max(R − K, 0); floorlet = N·α·max(K − R, 0), pagados al fin del periodo.
- Black-76: V = N·α·P(T_pago)·[F·N(d1) − K·N(d2)], d1 = [ln(F/K) + σ²τ/2]/(σ√τ); con desplazamiento s opcional (F+s, K+s). Bachelier: V = N·α·P·[(F − K)·N(d) + σ_n·√τ·φ(d)], d = (F − K)/(σ_n√τ). Floor por simetría.
- Forward del periodo F = (P(t1)/P(t2) − 1)/α.
- Tiempo de varianza τ: tasa fijada al inicio (TIIE 28) → τ = tiempo a la fijación. Tasa overnight compuesta en atraso (TIIE de Fondeo) → τ = t_s + (t_e − t_s)/3 si el periodo no ha iniciado; si ya inició, τ = t_e³/(3(t_e − t_s)²) y exigir el factor devengado observado. Si un periodo ya fijó, exigir la fijación conocida (no suponerla).
- Sensibilidades por diferencias finitas de 1 pb: PV01 paralelo, gamma, PV01 por nodo, pendiente, curvatura, vega (por 1 punto de vol lognormal o 1 pb de vol normal), theta de 1 día con forwards constantes. Paridad: Cap − Floor = Σ N·α·P·(F − K).
- Volatilidad: supuesto del usuario o botón «Usar volatilidad histórica de la tasa» (1 año: normal = sd(Δr)·√252, lognormal = sd(Δln r)·√252), etiquetada «Estimación histórica, no volatilidad implícita». Valor de control: TIIE 28 ≈ 87 pb normal / 12.3 % lognormal.
- Comparación Black-76 vs Bachelier con explicación de la diferencia.
```

---

## PROMPT 7 — Estrategias, coberturas, escenarios y actualización de datos

```
Construye las páginas 12 (Estrategias), 13 (Coberturas) y 14 (Perfiles y escenarios), y las funciones backend de actualización.

ESTRATEGIAS: plantillas Protective Put, Call protectora, Covered Call, Collar, Venta/Compra de futuros, Long/Short Straddle, Long/Short Strangle, Long/Short Call Butterfly, Long/Short Put Butterfly, y constructor manual por legs (tipo, cantidad ±, multiplicador, strike, vencimiento, prima y su origen, precio de entrada). Validar signos, strikes, vencimientos y primas; advertir calls vendidas descubiertas (pérdida ilimitada), puts vendidas (obligación) y garantías de futuros. Clasificar cada estrategia por función económica: cobertura directa, parcial, cruzada, estrategia de volatilidad, ingreso por primas, o no compatible con la exposición. Gráfico de resultado al vencimiento y revaluado antes del vencimiento.

COBERTURAS: registrar exposición accionaria (acciones ±, horizonte, r y su fuente, q, σ histórica de 252 sesiones o supuesto, presupuesto, objetivo) o de tasa variable (pasivo o activo, nocional, tasa de referencia, margen, fechas, periodicidad, curva, modelo, σ). Si el usuario elige un futuro listado, usar su precio de liquidación y su vencimiento real. Matriz comparativa: alternativa, función económica, costo neto y % de la exposición, resultado en cada escenario, protección en estrés, participación en el alza (acciones) o mejora vs sin cobertura (tasas), cumplimiento de restricciones del perfil y riesgos no cubiertos. Ordenar por criterio explícito (mejor estrés, menor costo, mejor base, mejor favorable extremo, mayor protección); sin puntuaciones opacas.

ESCENARIOS: 3 perfiles × estrategias × 5 escenarios (estrés adverso severo, adverso moderado, base, favorable moderado, favorable extremo). «Adverso» se define según la exposición (acciones largas: caída; cortas: alza; pasivo a tasa variable: alza de tasas; activo: baja). Dentro de un perfil, el MISMO choque se aplica a todas las estrategias. Choques por defecto (editables):
- Conservador: precio 35/15/0/10/25 %, vol +15/+5/0/−2/+3 pts; tasas 300/125/0/75/200 pb; pérdida máx. tolerada 8 %, presupuesto 5 %, strike put 100 % S0, call vendida 108 %, razón de cobertura 1.
- Equilibrado: 25/10/0/10/25 %, vol +10/+3/0/−2/+3; tasas 200/100/0/100/200 pb; 15 %, 3 %, put 95 %, call 105 %, razón 1, strike cap = forward promedio + 50 pb, floor − 50 pb.
- Agresivo: 20/8/0/12/35 %, vol +8/+2/0/−2/+5; tasas 150/75/0/100/250 pb; 25 %, 1.5 %, put 90 %, call 110 %, razón 0.5, cap +100 pb, floor −100 pb.
Acciones: precio final = S0·(1 + choque); opciones con vencimiento posterior al horizonte se REVALÚAN (BSM o CRR), no se usa el payoff. Tasas: la curva se desplaza (paralelo, pendiente, curvatura) y las tasas realizadas = forwards desplazadas (hipótesis); reportar flujos por periodo no descontados, VP, MTM del derivado tras el choque y P&L económico = VP(pagos) − prima. Editor de choques y preferencias por perfil; guardar versiones; gráfico de barras por escenario y comparación lado a lado.

IA EXPLICATIVA (usar la integración de LLM de Base44): recibe SOLO el JSON del resultado calculado y responde en español. Instrucciones fijas: no generar cifras nuevas, primas, tasas, volatilidades ni probabilidades; usar sólo cifras del contexto; distinguir observado/supuesto/teórico; si falta información, decirlo. Después, verificar que cada número de la respuesta exista en el contexto (con tolerancia de redondeo) y avisar si alguno no es rastreable.

FUNCIONES BACKEND DE ACTUALIZACIÓN (botón «Actualizar todos los datos» en Inicio):
- Yahoo Finance (fuente de referencia designada por el usuario, uso personal): GET https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?range=5y&interval=1d&events=div%2Csplit . Guardar en PriceBar sólo sesiones con cierre publicado (si close es null, RECHAZAR el renglón; nunca rellenar) y que no sean de la sesión en curso antes de las 16:00 hora de Ciudad de México. Redondear a 2 decimales. Insertar sólo fechas nuevas (actualización incremental). Dividendos y splits → CorporateAction. Fuente: «Yahoo Finance · fuente de referencia designada por el usuario · {símbolo}».
- Banxico SIE: GET https://www.banxico.org.mx/SieAPIRest/service/v1/series/{id}/datos/{inicio}/{fin} con encabezado «Bmx-Token: {BANXICO_TOKEN}» (secreto de la app). Series verificadas: TIIE_28 SF43783, TIIE_91 SF43878, TIIE_182 SF111916, TIIE_FONDEO SF331451, TASA_OBJETIVO SF61745, CETES_28 SF43936, CETES_91 SF43939, CETES_182 SF43942, CETES_364 SF43945, BONO_M_3A SF43883, BONO_M_5A SF43886, BONO_M_10A SF44071, BONO_M_20A SF45384, BONO_M_30A SF60696, FIX SF43718. Fechas vienen como dd/mm/aaaa; los días con dato «N/E» se omiten. Si responde 401, mostrar «Token de Banxico inválido o ausente».
```

---

## PROMPT 8 — Reportes, estudios y carga de boletines nuevos

```
Construye las páginas 15 (Reportes) y 16 (Estudios guardados), y la carga de datos nuevos de MexDer.

REPORTES: el usuario selecciona registros de AuditLog y genera:
- Excel (SheetJS) con hojas: Portada, Fuentes y fechas, Datos históricos, Estados financieros, Ratios, DCF, Análisis técnico, Riesgo, Futuros, Opciones, Curvas de tasas, Caps y floors, Estrategias, Perfiles de riesgo, Escenarios, Comparativas, Fórmulas y supuestos. Las secciones sin cálculo dicen «Sin datos». Incluir fórmulas de Excel auditables donde sea posible (rendimiento simple, FCFF, VP, caplet = N·α·DF·unidad, resultado combinado = exposición + derivado).
- PDF (jsPDF) con portada, resumen ejecutivo, metodología, fuentes, gráficos, tablas de escenarios por perfil, conclusiones, limitaciones y anexo de fórmulas. Identificar claramente lo oficial frente a lo teórico o simulado.
ESTUDIOS: guardar un conjunto de cálculos con título y versión (la versión aumenta si el título se repite); abrir y regenerar Excel/PDF.

CARGA DE DATOS NUEVOS DE MEXDER (páginas Futuros y Opciones): permitir subir CSV con las mismas columnas que FuturesContract / OptionSeries para actualizar precios de liquidación (insertar o actualizar por símbolo / por subyacente+vencimiento+tipo+strike). Reglas a respetar al preparar esos CSV a partir del boletín de MexDer:
1. En varios subyacentes el boletín publica el strike DIVIDIDO ENTRE 100 (p. ej. ASUR «5.2» = $520). Verificar la escala con paridad put-call en el vencimiento más cercano: K_implícito ≈ S − (C − P); razón K_implícito/K_publicado ≈ 1 → ×1, ≈ 100 → ×100. Guardar strike real, strike publicado y escala.
2. Alias del boletín: «ALFA A» = SIGMAF A; «AMERICA MOVIL B» = AMX B; «KOF L» = KOF UBL; «WALMEX V» = WALMEX *.
3. Futuro TIEF: vence el primer día hábil del mes SIGUIENTE a la serie (vencimiento 1-dic-2026 = serie NV26).
4. Vencimientos con día de un dígito («2026/DIC/1») también son válidos.
5. AIM: futuros con valor distinto para larga y corta; opciones con AIM corta (la larga es 0). Asignarlas sólo a contratos existentes; nunca crear contratos que no estén en el boletín.
```

---

## PROMPT 9 — Verificación final

```
Verifica la app con estos valores de referencia y corrige cualquier diferencia antes de terminar. Muéstrame una tabla «esperado vs obtenido»:
1. BSM call S=42, K=40, r=0.10, σ=0.20, T=0.5, q=0 → 4.7594; put → 0.8086. Paridad C − P = S·e^{−qT} − K·e^{−rT}.
2. CRR put americana S=50, K=50, r=0.10, σ=0.40, T=5/12, 5 pasos → 4.49 (con 1000 pasos ≈ 4.28). Call americana sin dividendos = call europea.
3. RSI(14) de Wilder sobre los cierres 44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955, 45.4245, 45.8433, 46.0826, 45.8931, 46.0328, 45.6140, 46.2820, 46.2820, 46.0028, 46.0328, 46.4116, 46.2222, 45.6439 → primer valor 70.53, segundo 66.32.
4. Fibonacci máximo 200, mínimo 100, alcista → 61.8 % = 138.2; extensión 161.8 % = 261.8.
5. DCF: ingresos 1000, 2 años, crecimiento 10 %, margen EBIT 20 %, t 30 %, D&A 5 %, CAPEX 6 %, ΔCTN/Δventas 10 %, WACC 10 %, g 3 %, deuda neta 200, 10 acciones → reproducir VE = FCFF1/1.1 + FCFF2/1.21 + [FCFF2·1.03/0.07]/1.21.
6. Cap: paridad Cap − Floor = Σ N·α·P·(F − K); el valor del cap baja al subir el strike y el del floor sube; los valores escalan linealmente con el nocional.
7. Bootstrapping: con los DF obtenidos, un bono par a 5 años (10 cupones de y·182/360) debe valer exactamente 1.
8. Datos importados: 38 instrumentos; 512 contratos de futuros (444 con AIM); 6,336 series de opciones (6,008 con AIM corta); WALMEX close 2026-11-20 = 54.42; WALMEX DC26 AIM corta ≈ 551.78; ASUR call dic-2026 strike 520 (publicado 5.2); TIIE_28 2026-11-20 = 6.5147.
9. Recorre las 16 páginas y confirma que ninguna muestra errores ni cifras sin fuente.
```

---

## Importación de datos (carpeta `datos/`)

En Base44, abre cada entidad → **Import** (o «Importar CSV») y sube el archivo correspondiente. Los nombres de columna coinciden con los campos del PROMPT 1.

| Archivo | Entidad | Renglones | Contenido |
|---|---|---|---|
| `01_instrumentos.csv` | Instrument | 38 | Catálogo MexDer (rev. 21-nov-2026): 31 acciones con futuro, NAFTRAC, 5 valores globales (SIC) e IPC, con su símbolo Yahoo |
| `02_contratos_futuros.csv` | FuturesContract | 512 | Boletín de futuros MexDer del 20-nov-2026 + AIM de octubre 2026 (larga/corta) |
| `03_series_opciones.csv` | OptionSeries | 6,336 | Boletín de opciones del 20-nov-2026 con strikes en escala real + AIM corta de octubre 2026 |
| `04_tasas_banxico.csv` | RateObservation | 3,801 | 15 series del SIE (nov-2024 a nov-2026) |
| `05_curvas.csv` | CurvePoint | 42 | Curva gubernamental (CETES + Bonos M, bootstrapping) a 20 años del 20-nov-2026 |
| `06_estados_financieros.csv` | FinancialItem | 6,521 | Estados anuales y trimestrales de 37 emisoras (Yahoo) |
| `07_dividendos_splits.csv` | CorporateAction | 1,271 | Dividendos y splits (Yahoo) |
| `08_precios_diarios_parte1…6.csv` | PriceBar | 47,124 | 5 años de OHLCV diario de los 38 instrumentos (Yahoo), dividido en 6 partes de menos de 10,000 renglones |

Si Base44 limita el tamaño de importación, sube primero los archivos 01 a 07 y los precios por partes. Los precios también se pueden descargar después con «Actualizar todos los datos».

**Límites conocidos que la app debe mostrar con honestidad:**
- Calendario de días inhábiles aproximado.
- Volatilidad de caps y floors sin cotizaciones de mercado.
- Sin estimaciones de analistas.
- AIM de octubre de 2026 hasta cargar un archivo más reciente.
- Precios de referencia de Yahoo, no cierres oficiales de la BMV.
