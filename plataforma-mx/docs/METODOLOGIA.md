# Metodología financiera y técnica

Referencias: Hull, *Options, Futures and Other Derivatives*; Wilder (1978); Lyashenko y Mercurio (2019), *Looking Forward to Backward-Looking Rates*.

## Series históricas
- Rendimiento simple: R_t = P_t/P_{t−1} − 1. Rendimiento logarítmico: r_t = ln(P_t/P_{t−1}).
- Volatilidad: desviación estándar muestral (ddof = 1) de los rendimientos logarítmicos × √(periodos por año). Periodos por año: diaria 252, semanal 52, mensual 12, bimestral 6, trimestral 4, semestral 2, anual 1.
- Agregación: primera apertura, máximo, mínimo, último cierre y suma de volumen. La fecha de cada periodo es la última sesión negociada. Bimestres y semestres son calendario fijo. Los periodos sin datos se omiten.
- Comparación con índices: sólo fechas comunes; no se interpola.

## Indicadores técnicos
- ROC(n) = (P_t/P_{t−n} − 1)·100.
- Williams %R = −100·(Máx_n − C)/(Máx_n − Mín_n). Vale NaN cuando el rango es cero.
- Estocástico: %K rápido = 100·(C − Mín_k)/(Máx_k − Mín_k). %K lento = SMA(%K rápido). %D = SMA(%K).
- RSI de Wilder: los promedios iniciales son la media simple de los primeros n cambios; después avg_t = (avg_{t−1}(n−1) + x_t)/n.
- Fibonacci: retrocesos de 0, 23.6, 38.2, 50, 61.8, 78.6 y 100 %, y extensiones de 127.2, 161.8, 200 y 261.8 %. Las anclas son manuales o el último pivote fractal confirmado.

## Riesgo
- β = Cov(R_a, R_m)/Var(R_m) sobre fechas comunes, con α, R² y error estándar por MCO.
- VaR histórico = −cuantil_{1−c}. ES = −media de la cola.
- VaR paramétrico normal = −(μ + σ z_{1−c}). ES normal = −μ + σ φ(z_c)/(1−c).
- Iliquidez de Amihud = media(|R_t| / importe operado_t).

## Valuación fundamental
- FCFF = EBIT(1−t) + D&A − CAPEX − ΔCTN.
- Ke (CAPM) = rf + β·PRM + prima país + prima tamaño. WACC = E/V·Ke + D/V·Kd(1−t).
- Valor terminal: Gordon, FCFF_N(1+g)/(WACC−g) con g < WACC, o múltiplo VE/EBITDA.
- Capital = VE − deuda neta − interés minoritario + activos no operativos.

## Futuros
- P&L = ±n·M·(F_T − F_0). Liquidación diaria contra el saldo de garantías: si el saldo cae bajo el mantenimiento, se exige aportación hasta la AIM.
- La AIM es una garantía recuperable, no un costo.
- Precio teórico por acarreo: F = (S − VP div)·e^{(r−q)T}. Es resultado de modelo, no cotización.
- Stop hipotético: si la trayectoria cruza el stop, la ejecución ocurre en el precio de cruce (incluida la brecha) más el deslizamiento.

## Opciones
- BSM con dividendo continuo q. Theta se expresa por año y por día natural; vega y rho por 1.00 y por 1 punto porcentual.
- CRR: u = e^{σ√Δt}, d = 1/u, p = (e^{(r−q)Δt} − d)/(u−d). Ejercicio anticipado nodo por nodo.
- Volatilidad implícita: Brent sobre σ ∈ [0.0001, 5]. Primero se validan las cotas de no arbitraje y el origen observado de la prima.
- Antes del vencimiento, las posiciones se revalúan con el modelo. El payoff sólo se usa al vencimiento.

## Tasas, caps y floors
- Convenciones de días: ACT/360 (TIIE), ACT/365F, 30/360, 30E/360. Ajuste following, modified following o preceding sobre el calendario MX.
- Calendario de pagos de 28D, 91D, 182D o meses, con amortización por periodo y rezago de fijación en días hábiles.
- Curva: nodos importados convertidos a tasa cero continua. Interpolación log-lineal en factores de descuento (forward constante a tramos) o lineal en la tasa cero. Fuera de los nodos se aplica tasa plana con advertencia.
- Forward simple: F = (P(t1)/P(t2) − 1)/α.
- Caplet con Black-76: N α P(T_p)[F N(d1) − K N(d2)]. Bachelier: N α P(T_p)[(F−K)N(d) + σ_n√τ φ(d)].
- Tiempo de varianza τ: t_fijación para tasas fijadas al inicio. Para tasas compuestas en atraso, t_s + (t_e − t_s)/3, o t_e³/(3(t_e − t_s)²) si el periodo ya inició.
- Las fijaciones conocidas y el factor devengado son obligatorios cuando el periodo ya fijó o está en curso: no se suponen.
- TIIE de Fondeo compuesta: [Π(1 + r_i d_i/360) − 1]·360/D. Exige una fijación por cada día hábil.
- Sensibilidades por diferencias finitas centrales de 1 pb: PV01 paralelo, gamma, key-rate PV01, pendiente, curvatura, vega y theta de 1 día con forwards constantes.
- Paridad: Cap − Floor = Σ N α P (F − K).

## Escenarios
- Tres perfiles (conservador, equilibrado y agresivo), cada uno con su conjunto visible de choques y sus preferencias: tolerancia de pérdida, presupuesto, strikes, razón de cobertura y offsets de strike en caps/floors.
- Cinco escenarios por combinación. Adverso o favorable se define según la exposición.
- Dentro de un perfil, la misma condición de mercado se aplica a todas las estrategias.
- Acciones: precio final = S0(1 + choque) y σ + desplazamiento. P&L combinado = exposición + overlay. Se reportan protección, delta remanente y participación en el alza.
- Tasas: la curva se desplaza (paralelo, pendiente, curvatura) y las tasas realizadas igualan las forwards desplazadas (hipótesis). Se reportan flujos no descontados, VP, MTM inmediato del derivado y P&L económico = VP(pagos) − prima.
- No se asignan probabilidades. El ordenamiento usa criterios explícitos; no hay puntuaciones opacas.
