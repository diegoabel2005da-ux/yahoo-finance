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
  tests/           76 pruebas: valores de referencia independientes, no arbitraje, integración de la API
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

### Catálogo cargado

`backend/data/catalogs/mexder_catalogo_2026-11-21.csv` es la revisión del catálogo tomada de las páginas «Contratos de futuro listados» y «Contratos de opción listados» de MexDer (texto copiado por el usuario el 21-nov-2026): 38 instrumentos, de los cuales 30 tienen futuro y opción, 7 solo futuro y 1 solo opción. Incluye 31 acciones con futuro, NAFTRAC ISHRS (solo opciones), 5 valores globales del SIC y el S&P/BMV IPC, con sus claves de pizarra de futuros y opciones y su símbolo de Yahoo (verificado con cotización). La opción listada como «ALFA A» (clave AL) se unificó con SIGMAF A por confirmación del usuario (21-nov-2026). Pendiente: las series vigentes de futuros y opciones (vencimientos y strikes concretos), que la plataforma no genera a partir de las reglas.

### Boletines diarios de MexDer

`POST /api/mexder/bulletin` (botones en «Futuros» y «Opciones») importa el PDF del boletín básico de futuros u opciones. Se leen las secciones «Precios de liquidación e interés abierto»: cada serie vigente con su vencimiento real, la liquidación anterior y la actual, y el interés abierto. Las series se guardan como contratos listados, con historial por fecha en `contract_quotes`. El boletín del 20-nov-2026 dejó 424 series de futuros y 6,336 de opciones.

- **Alias del boletín:** ALFA A → SIGMAF A (confirmado por el usuario), AMERICA MOVIL B → AMX B, KOF L → KOF UBL, WALMEX V → WALMEX *. Quedan anotados en cada contrato.
- **Escala de strikes:** para varios subyacentes el boletín publica el strike dividido entre 100 (p. ej. ASUR «5.2» = $520). La escala se infiere en cada importación con la paridad put-call del vencimiento más cercano, contra el cierre del mismo día. Se guardan el strike publicado, el factor y la evidencia. Si no se puede decidir, la serie queda marcada como «escala no verificada». Si la paridad se desvía más de un 3 % tras la escala, se advierte que el precio del subyacente disponible no coincide con el de referencia de MexDer: el 20-nov ocurrió con META, NVDA y TSLA, cuyo precio del SIC en Yahoo difiere.
- **Precio de liquidación de opciones:** es el precio oficial que publica MexDer para cada serie. Si la serie no operó, MexDer lo determina con su metodología, así que no equivale a una prima negociada.
- **Vencimientos de un dígito y TIEF:** se leen series con vencimiento en días de uno o dos dígitos. El futuro de TIIE de Fondeo se identifica por el mes de la serie: vence el primer día hábil del mes siguiente, así que el vencimiento del 1-dic-2026 es la serie NV26. El boletín del 20-nov-2026 dejó 512 series de futuros.

### AIM unitarias (MexDer/Asigna)

`POST /api/mexder/aims` importa el Excel «AIMS_Unitarias_<Mes><Año>». Las hojas son Futuros (AIM distinta para larga y corta), Opciones (AIM corta por strike; la larga es 0) y Swaps (sólo se reporta).
- Las AIM se asignan únicamente a contratos ya importados de un boletín; las series que no existen se reportan y no se crean. Con el archivo de octubre de 2026 se asignaron 444 de 512 series de futuros y 6,008 de 6,360 de opciones. Las demás son series ya vencidas, strikes que MexDer dejó de listar en noviembre o la clase «DEUA», que no aparece en el boletín.
- Los strikes del archivo vienen en su escala real y coinciden con la escala ×100 que se infiere del boletín por paridad put-call, lo que es una verificación independiente.
- El periodo se toma del nombre del archivo (octubre 2026 se registra al 31-oct-2026) y la plataforma no lo presenta como AIM vigente del día. El análisis de futuros usa la AIM del lado elegido (larga o corta).

### Yahoo Finance como fuente de referencia

Por decisión del usuario (uso personal y de investigación, términos de Yahoo revisados y aceptados), **Yahoo Finance** (librería `yfinance`) es la fuente de referencia de precios, estados financieros y dividendos. Sus observaciones se registran como fuente oficial/de referencia, con la fuente siempre explícita («Yahoo Finance (yfinance) · fuente de referencia designada por el usuario · SÍMBOLO»).

- Símbolos: emisora + serie + `.MX` (`WALMEX.MX`, `GFNORTEO.MX`, `CEMEXCPO.MX`). Los índices y casos especiales usan la columna `yahoo_symbol` del catálogo (p. ej. `^MXX` para el S&P/BMV IPC).
- Las barras sin cierre (NaN) y las de la sesión en curso se rechazan; no se rellenan.
- Los precios se guardan a 2 decimales (precisión de puja de la BMV), redondeados desde los flotantes de Yahoo.
- `Close` de Yahoo está ajustado por splits; `Adj Close` (dividendos) se guarda como cierre ajustado. Ninguno equivale necesariamente al precio de la subasta de cierre de la BMV.
- Endpoints: `POST /api/yahoo/prices`, `POST /api/yahoo/refresh` (todas las vigentes, incremental), `POST /api/yahoo/financials`, `GET /api/yahoo/dividends/{ticker}/{serie}`.
- Red: el entorno necesita acceso a `query1.finance.yahoo.com`, `query2.finance.yahoo.com`, `fc.yahoo.com` y `finance.yahoo.com`.

### Banxico (SIE)

Con `BANXICO_TOKEN` configurado, `POST /api/rates/banxico` descarga series oficiales. Los identificadores se verificaron contra el título oficial que devuelve la API de Banxico (21-nov-2026): TIIE 28 `SF43783`, TIIE 91 `SF43878`, TIIE 182 `SF111916`, TIIE de Fondeo `SF331451`, tasa objetivo `SF61745`, y CETES 28/91/182/364 `SF43936`/`SF43939`/`SF43942`/`SF43945`.
`POST /api/curves/banxico-cetes` construye una curva cero con los rendimientos de la última subasta semanal de CETES (simple ACT/360, nodos de 28 a 364 días). Si alguna subasta es demasiado antigua, la curva no se construye. Requiere acceso de red a `www.banxico.org.mx`. El token no se guarda en el repositorio.

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
