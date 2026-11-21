# Plataforma MX — análisis, valuación, derivados y coberturas

Plataforma web de **análisis e investigación** para subyacentes accionarios mexicanos listados en MexDer, con un módulo independiente de **caps y floors** sobre tasas en pesos.
No ejecuta órdenes ni hace recomendaciones. Los precios teóricos y los escenarios simulados siempre se etiquetan como tales.

> **Principio rector:** primero comprender y cuantificar el riesgo; después construir y comparar las alternativas de cobertura.

## Arquitectura

```
backend/   Python · FastAPI · SQLAlchemy (PostgreSQL vía DATABASE_URL; SQLite por defecto)
  app/core/        procedencia de datos (provenance.py), modelo de datos (db.py), auditoría (audit.py)
  app/engines/     motores de cálculo puros y probados
    timeseries.py  remuestreo OHLCV, rendimientos, volatilidad, drawdown
    technical.py   ROC, Williams %R, estocástico, RSI Wilder, SMA/EMA, Fibonacci, pivotes
    patterns.py    tendencias, cambios estructurales, chartismo algorítmico
    risk.py        beta (con R²), VaR/ES históricos y paramétricos, correlaciones, liquidez
    fundamental.py ratios, CAPM, WACC, DCF por FCFF, sensibilidad, múltiplos
    futures.py     P&L, liquidación diaria/AIM, acarreo, razón de cobertura, stop hipotético
    options.py     BSM + griegas, CRR (europeas/americanas, árbol, dividendos discretos), volatilidad implícita
    rates/         convenciones de días, calendario MX, curvas, Black-76, Bachelier, caps/floors
    strategies.py  legs, plantillas, validación, clasificación económica
    scenarios.py   perfiles × estrategias × 5 escenarios (acciones y tasas), ordenamiento
  app/services/    importadores validados, conectores a fuentes oficiales, acceso a mercado,
                   IA explicativa, reportes Excel/PDF
  app/api/         rutas REST (cada cálculo devuelve un audit_id reproducible)
  data/templates/  plantillas CSV de importación (sólo encabezados, sin datos)
  tests/           69 pruebas: valores de referencia independientes, no arbitraje, integración de la API
frontend/  Next.js 15 · React 19 · TypeScript · Tailwind · Plotly (16 módulos del menú)
docs/      metodología financiera y técnica
```

Toda la lógica financiera vive en el backend: el frontend sólo muestra resultados.

## Puesta en marcha

```bash
cd backend && pip install -r requirements.txt
```

```bash
cd backend && uvicorn app.main:app --port 8000
```

```bash
cd frontend && npm install && npm run build && npm start
```

Abra http://localhost:3000. El frontend redirige `/api/*` al backend (`BACKEND_URL`, por defecto `http://127.0.0.1:8000`).

Variables opcionales del backend:

| Variable | Uso |
|---|---|
| `DATABASE_URL` | p. ej. `postgresql+psycopg://user:pass@host/db` |
| `BANXICO_TOKEN` | token gratuito del SIE de Banxico para descargar tasas |
| `BANXICO_SERIES` | identificadores SIE: `TIIE_28=SF43783,TIIE_FONDEO=SF…` (verifíquelos en el catálogo SIE) |
| `ANTHROPIC_API_KEY` | activa la IA explicativa con modelo de lenguaje; sin ella se usa un explicador determinista por reglas |
| `AI_MODEL` | modelo de lenguaje (por defecto `claude-opus-5-5`) |
| `CORS_ORIGINS` | orígenes permitidos |

Pruebas:

```bash
cd backend && python -m pytest -q
```

## Veracidad de los datos

- **No hay datos precargados.** El catálogo, los precios, las tasas, las curvas, los contratos y los estados financieros entran por conectores autorizados o por importación validada de CSV/Excel (`data/templates/`).
- Cada precio guarda instrumento, serie, identificador, mercado, fuente, tipo de precio (9 tipos distintos), fechas de mercado, publicación y consulta, hora y zona, moneda, valor tal como se publicó, precisión publicada, estado de actualización, origen y versión.
- Los renglones inválidos se **rechazan** (nunca se corrigen ni se rellenan). Los precios teóricos no pueden importarse como datos de mercado.
- **Reconciliación:** las cifras de proveedores secundarios se comparan contra la fuente oficial (mismo instrumento, fecha, tipo y campo), a la precisión publicada. Una diferencia genera una discrepancia que **bloquea los cálculos críticos** de ese instrumento hasta que se documenta su resolución. La cifra oficial nunca se sobrescribe.
- **Auditoría:** cada cálculo guarda entradas, parámetros, fórmulas, fuentes y una huella SHA-256 del resultado (`GET /api/audit/{id}`).
- Las volatilidades implícitas sólo se calibran a partir de primas **observadas**. Una prima de modelo se rechaza.
- Los caps y floors se presentan como **instrumentos OTC parametrizados (teóricos)**. No se afirma que coticen en MexDer.

### Yahoo Finance como fuente de referencia

Por decisión del usuario (uso personal y de investigación, términos de Yahoo revisados y aceptados), **Yahoo Finance** (librería `yfinance`) es la fuente de referencia de precios, estados financieros y dividendos. Sus observaciones se registran como fuente oficial/de referencia, con la fuente siempre explícita («Yahoo Finance (yfinance) · fuente de referencia designada por el usuario · SÍMBOLO»).

- Símbolos: emisora + serie + `.MX` (`WALMEX.MX`, `GFNORTEO.MX`, `CEMEXCPO.MX`). Los índices y casos especiales usan la columna `yahoo_symbol` del catálogo (p. ej. `^MXX` para el S&P/BMV IPC).
- Las barras sin cierre (NaN) y las de la sesión en curso se rechazan; no se rellenan.
- Los precios se guardan a 2 decimales (precisión de puja de la BMV), redondeados desde los flotantes de Yahoo.
- `Close` de Yahoo está ajustado por splits; `Adj Close` (dividendos) se guarda como cierre ajustado. Ninguno equivale necesariamente al precio de la subasta de cierre de la BMV.
- Endpoints: `POST /api/yahoo/prices`, `POST /api/yahoo/refresh` (todas las vigentes, incremental), `POST /api/yahoo/financials`, `GET /api/yahoo/dividends/{ticker}/{serie}`.
- Red: el entorno necesita acceso a `query1.finance.yahoo.com`, `query2.finance.yahoo.com`, `fc.yahoo.com` y `finance.yahoo.com`.

### Estado de las fuentes en este entorno de desarrollo

Desde el entorno donde se construyó, MexDer y Banxico **no eran accesibles** (la red del entorno rechazó la conexión). Por eso el sistema se probó con datos **sintéticos de prueba** (fuente `PRUEBA-SINTETICA`, tickers ficticios) que viven sólo en las pruebas. Para operar con datos reales:

1. Importe en «Emisoras» la relación vigente de subyacentes de MexDer.
2. Importe precios (BMV/BIVA o un proveedor con licencia), especificaciones de contratos y AIMs de MexDer, estados financieros (CNBV/emisoras) y curvas de un proveedor autorizado.
3. Configure `BANXICO_TOKEN` y verifique los identificadores de serie del SIE.

## Criterios de aceptación del MVP (sección 23) — estado verificado

| # | Criterio | Estado |
|---|---|---|
| 1 | Catálogo actualizable del universo MexDer | Implementado (importación versionada; las emisoras ausentes pasan a no vigentes). **Falta cargar la publicación real de MexDer.** |
| 2 | Seleccionar cualquier instrumento | Sí (selector persistente; distingue emisora y serie) |
| 3 | Fuente, fecha y estado de validación en los datos | Sí |
| 4 | Precios oficiales reproducibles y verificables | Sí, con reconciliación y versiones de datos |
| 5–6 | Indicadores financieros y técnicos correctos, con periodos personalizados | Sí; probados contra referencias independientes |
| 7 | DCF editable | Sí, con CAPM/WACC y sensibilidad |
| 8 | Riesgos básicos | Sí |
| 9 | Posiciones reales declaradas e hipotéticas | Sí |
| 10 | Futuros con características contractuales | Sí, sobre los contratos importados |
| 11 | Opciones con modelos apropiados | Sí (BSM, CRR americana) |
| 12 | Caps/floors: valoración y simulación | Sí (Black-76, Bachelier, compuesta en atraso, sensibilidades, escenarios) |
| 13 | Estrategias principales | Sí (14 plantillas y constructor manual) |
| 14 | ≥5 escenarios por perfil y estrategia | Sí |
| 15 | Recálculo al modificar parámetros | Sí |
| 16 | IA sin inventar cifras | Sí: el prompt prohíbe cifras nuevas y la respuesta se verifica número por número contra el contexto |
| 17 | Exportación a Excel y PDF | Sí (17 hojas con fórmulas; PDF con gráficos) |
| 18 | Resultados auditables | Sí |
| 19 | Limitaciones de datos y modelos | Sí, en la interfaz y en los reportes |
| 20 | Ningún valor ficticio como oficial | Garantizado por validación de origen |

### Limitaciones conocidas

- El calendario de días inhábiles se basa en reglas (LFT art. 74 + inhábiles habituales). Importe el calendario oficial anual para producción.
- La volatilidad de caplets compuestos en atraso usa la aproximación de Lyashenko–Mercurio con volatilidad constante. No hay superficie de volatilidad: sin cotizaciones se usa una volatilidad plana declarada como supuesto.
- La curva se construye desde nodos importados (tasas cero o factores de descuento). No se hace bootstrapping de swaps TIIE.
- El tratamiento de dividendos discretos en CRR es la aproximación de precio libre de dividendos.
- La detección de figuras es por reglas sobre pivotes fractales: describe la geometría del precio, no da señales.
- No hay autenticación de usuarios; añádala antes de exponer el servicio.
