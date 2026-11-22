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
  tests/           80 pruebas: valores de referencia independientes, no arbitraje, integración de la API
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

## Datos semilla y actualización

El repositorio incluye los datos base para que la plataforma funcione en cualquier instalación:

| Archivo | Contenido |
|---|---|
| `backend/data/catalogs/mexder_catalogo_2026-11-21.csv` | Catálogo de subyacentes de MexDer (futuros y opciones) |
| `backend/data/seed/mexder/2026-11-20_Boletin_de_Futuros_Basico.pdf` | Boletín de futuros del 20-nov-2026 (512 series) |
| `backend/data/seed/mexder/2026-11-20_Boletin_de_Opciones_Basico.pdf` | Boletín de opciones del 20-nov-2026 (6,336 series) |
| `backend/data/seed/mexder/AIMS_Unitarias_Octubre26.xls` | AIM unitarias, periodo octubre 2026 |

- **Carga automática:** al arrancar el backend con una base vacía, se cargan en segundo plano y sin red el catálogo, los boletines y las AIM (unos 8 segundos). Se desactiva con `AUTO_SEED=0`. Manualmente: `python -m app.seed`.
- **Actualización en línea:** el botón «Actualizar todos los datos» de Inicio, o `python -m app.seed --online`, descarga precios, estados financieros, dividendos y splits de Yahoo, las series de Banxico y la curva gubernamental.
- **AIM vigentes:** mientras no se suba un archivo más reciente, las AIM de octubre de 2026 son la referencia. Siempre se muestran con su periodo y nunca como AIM de otro mes. Para actualizar, basta con poner el nuevo `AIMS_Unitarias_<Mes><Año>.xls` en `data/seed/mexder/` o subirlo desde la interfaz; se usa el de periodo más reciente.
- **Escala de strikes sin precios:** si al cargar no hay precios del subyacente para la paridad put-call, la escala se resuelve con los strikes del archivo de AIM, que vienen en escala real. Con los datos del 20-nov-2026, ambos métodos dan la misma escala en los 30 subyacentes.
- **Boletines nuevos:** se agregan con el botón de Futuros u Opciones, o dejando el PDF en `data/seed/mexder/` con la fecha al inicio del nombre.

## Supabase (PostgreSQL alojado)

La plataforma funciona sobre PostgreSQL sin cambios: la carga semilla, Yahoo, Banxico, análisis, derivados, escenarios, reportes y estudios se probaron sobre PostgreSQL 16 (Supabase usa 15/17).

1. En Supabase, abre **Project Settings → Database → Connection string** y copia la URI del **Session pooler** (es compatible con IPv4).
2. Define, en el servidor donde corra el backend (nunca en el repositorio):
   ```
   DATABASE_URL=postgresql+psycopg://postgres.<project_ref>:<CONTRASEÑA>@aws-0-<región>.pooler.supabase.com:5432/postgres?sslmode=require
   ```
3. Arranca el backend. Las tablas se crean en el esquema **`plataforma`** (configurable con `DB_SCHEMA`) y no en `public`, porque Supabase publica `public` por su API REST con la llave pública del proyecto. Si decides usar `public`, activa Row Level Security en todas las tablas.
4. Con la base vacía se cargan los datos semilla. Luego pulsa «Actualizar todos los datos» en Inicio.

**MCP de Supabase:** `.mcp.json` (raíz del repo) registra el servidor MCP del proyecto `tlwqadsvlnrrhakuxojq`. Claude Code pide aprobarlo y autenticarse con Supabase la primera vez. Permite consultar y administrar la base por HTTPS desde sesiones de Claude.

**Datos ya cargados en Supabase (22-nov-2026):** el proyecto `tlwqadsvlnrrhakuxojq` contiene en el esquema `plataforma` las 302,562 filas de la base de trabajo: 38 instrumentos, 282,744 observaciones de precio, 3,801 de tasas de Banxico, 938 estados financieros, 1,271 dividendos y splits, 512 futuros, 6,336 opciones, 6,848 precios de liquidación y 3 curvas. Se verificaron los conteos y valores de muestra con el MCP. Las tablas tienen RLS sin políticas y los roles `anon`/`authenticated` no tienen permisos, así que no son accesibles por la API pública.

**Resincronizar desde una base local:** `scripts/sync_supabase.py` sube una base SQLite por HTTPS mediante una función temporal `public.plataforma_load` (sólo `service_role`), con la llave secreta en el encabezado `apikey`. La función se crea antes de la carga y se borra al terminar. Las migraciones aplicadas fueron `plataforma_schema`, `plataforma_temp_loader` y `plataforma_post_load`, que ajusta las secuencias y borra la función.

**Nota sobre entornos en la nube de Claude Code:** esos contenedores sólo salen a internet por HTTPS mediante un proxy, así que el backend no puede abrir ahí una conexión directa de PostgreSQL (puerto 5432) hacia Supabase. En tu computadora o en un servidor (Render, Railway, Fly.io, una VM…) funciona con la `DATABASE_URL` anterior.

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
- Fundamentales en lote: `POST /api/yahoo/fundamentals-all` carga, para todas las emisoras vigentes, estados financieros anuales y trimestrales, dividendos y splits (tabla `corporate_actions`). Con la carga del 22-nov-2026 quedaron 433 estados anuales, 505 trimestrales, 1,224 dividendos y 47 splits. NAFTRAC (un ETF) no tiene estados financieros, y FRAGUA y LACOMER no tienen trimestrales en Yahoo.
- Ratios: si no se indican, se toman el último cierre, las acciones en circulación del balance y los dividendos de los últimos 12 meses, todos con su fuente. Varias emisoras reportan en dólares: CEMEX, GMEXICO, GRUMA, PE&OLES, ORBIA, VESTA, VOLAR, GISSA y los valores globales. Para ellas no se calculan múltiplos de mercado ni rendimiento por dividendo, porque mezclarían monedas.
- Red: el entorno necesita acceso a `query1.finance.yahoo.com`, `query2.finance.yahoo.com`, `fc.yahoo.com` y `finance.yahoo.com`.

### Banxico (SIE)

El token se guarda como **credencial del entorno**: el proxy de red lo inyecta en el encabezado `Bmx-Token` hacia `www.banxico.org.mx`. No vive en el código ni en variables. Fuera de ese entorno se puede definir `BANXICO_TOKEN`; si no hay ninguno, Banxico responde 401 y la plataforma lo reporta.

Series verificadas contra el título oficial de la API (21–22-nov-2026):

| Código | Serie SIE | Descripción |
|---|---|---|
| TIIE_28 / TIIE_91 / TIIE_182 | SF43783 / SF43878 / SF111916 | TIIE a 28, 91 y 182 días |
| TIIE_FONDEO | SF331451 | TIIE de Fondeo a un día hábil |
| TASA_OBJETIVO | SF61745 | Tasa objetivo |
| CETES_28 / 91 / 182 / 364 | SF43936 / SF43939 / SF43942 / SF43945 | Rendimiento de la subasta semanal |
| BONO_M_3A / 5A / 10A / 20A / 30A | SF43883 / SF43886 / SF44071 / SF45384 / SF60696 | Rendimiento de la subasta de Bonos a tasa fija |
| FIX | SF43718 | Tipo de cambio FIX, fecha de determinación |

- `POST /api/curves/banxico-cetes`: curva cero con CETES (hasta 364 días).
- `POST /api/curves/banxico-gov`: curva gubernamental con CETES y Bonos M. Los rendimientos de los Bonos M se tratan como tasas par con cupón semestral de 182 días y se obtienen los factores de descuento por bootstrapping, usando el plazo nominal de cada subasta. Por omisión la curva llega a 20 años. El nodo de 30 años es opcional porque, con tasas par cercanas al 10 %, amplifica las forwards del tramo largo (21.6 % a 29–30 años con los datos del 20-nov-2026). Cada construcción reporta un diagnóstico de forwards y rechaza subastas más antiguas que el límite (10 días para CETES, 60 para Bonos).
- `GET /api/rates/{código}/volatility`: volatilidad histórica normal y lognormal de la tasa. Es una estimación estadística, no una volatilidad implícita; en «Caps y floors» se puede usar como supuesto identificado.
- **FIX en ratios:** para emisoras que reportan en dólares y cotizan en pesos, el precio y los dividendos se convierten con el FIX del día del precio para calcular los múltiplos.

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
