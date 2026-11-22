# Guía de inicio: Plataforma MX en tu computadora (con Supabase)

Esta guía deja la plataforma funcionando en tu computadora y leyendo los datos que ya están en Supabase.
Tiempo estimado: 15 a 20 minutos la primera vez; después, un solo comando.

---

## 1. Instala los programas necesarios (una sola vez)

| Programa | Versión | Dónde |
|---|---|---|
| **Python** | 3.11, 3.12 o 3.13 | https://www.python.org/downloads/ · En Windows marca **«Add Python to PATH»** al instalar |
| **Node.js** | 20 o superior (LTS) | https://nodejs.org/ |
| **Git** | cualquiera | https://git-scm.com/downloads |

Para comprobar, abre una terminal (en Windows: «Símbolo del sistema» o «PowerShell») y escribe:

```
python --version
node --version
git --version
```

En Mac, si `python` no existe, usa `python3`.

---

## 2. Descarga el proyecto (una sola vez)

```
git clone -b plataforma-mx https://github.com/diegoabel2005da-ux/yahoo-finance.git
cd yahoo-finance/plataforma-mx
```

---

## 3. Conecta Supabase (una sola vez)

1. Entra a **supabase.com**, abre tu proyecto y pulsa el botón **Connect** (arriba).
2. Elige **Session pooler** (no «Direct connection») y copia la URI. Se ve así:
   `postgresql://postgres.tlwqadsvlnrrhakuxojq:[YOUR-PASSWORD]@aws-…pooler.supabase.com:5432/postgres`
3. En la carpeta `plataforma-mx/backend`, copia el archivo **`.env.example`** con el nombre **`.env`**.
   El script de arranque lo crea solo si no existe.
4. Abre `.env` con un editor de texto y pega la URI en `DATABASE_URL=`, reemplazando `[YOUR-PASSWORD]` por la contraseña de tu base de datos, sin corchetes.
   Si no recuerdas la contraseña: Supabase → Project Settings → Database → **Reset database password**.
5. Deja `DB_SCHEMA=plataforma` y `AUTO_SEED=0`, porque los datos ya están en Supabase.
6. Opcional:
   - `BANXICO_TOKEN=`: tu token del SIE, para que «Actualizar todos los datos» descargue tasas de Banxico.
   - `ANTHROPIC_API_KEY=`: llave de la API de Claude, para la IA explicativa. Sin ella se usa el explicador por reglas.

> **Importante:** el archivo `.env` contiene tu contraseña. No lo compartas ni lo subas a GitHub; ya está excluido del repositorio.
>
> **Sin Supabase:** si dejas `DATABASE_URL` vacío y pones `AUTO_SEED=1`, la plataforma usa una base local (`plataforma.db`) y carga sola el catálogo, los boletines y las AIM. Luego pulsa «Actualizar todos los datos» en Inicio para descargar precios, fundamentales y tasas (unos minutos).

---

## 4. Arranca la plataforma

**Windows:** haz doble clic en **`iniciar.bat`** (carpeta `plataforma-mx`).
**Mac / Linux:** en la terminal, dentro de `plataforma-mx`:

```
./iniciar.sh
```

La primera vez instala todo (5 a 10 minutos). Las siguientes arranca en segundos.
Cuando veas «Abra http://localhost:3000», entra a esa dirección en tu navegador.

Para detenerla: cierra la ventana o pulsa `Ctrl + C` en la terminal.

### Arranque manual (si prefieres no usar el script)

Terminal 1, backend:

```
cd plataforma-mx/backend
python -m venv .venv
```

Activa el entorno: en Windows `.venv\Scripts\activate`, en Mac/Linux `source .venv/bin/activate`. Después:

```
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

Terminal 2, frontend:

```
cd plataforma-mx/frontend
npm install
npm run build
npm start
```

---

## 5. Comprueba que funciona

- http://localhost:8000/api/health → debe responder `"status":"ok"`.
- http://localhost:3000 → en **Emisoras** deben aparecer los **38 instrumentos**. Elige uno en el selector de arriba y revisa **Datos históricos**.

---

## 6. Rutina para mantener los datos al día

| Frecuencia | Qué hacer | Dónde |
|---|---|---|
| Cada día hábil | Descargar de mexder.com.mx el **Boletín de Futuros** y el **Boletín de Opciones** (versión básica, PDF) y subirlos | Páginas **Futuros** y **Opciones** → «Boletín diario de MexDer» |
| Cada día o cuando quieras | Actualizar precios, estados financieros, dividendos, tasas de Banxico y curva | **Inicio** → «Actualizar todos los datos (en línea)» |
| Cada mes | Subir el archivo **AIMS_Unitarias_<Mes><Año>.xls** cuando lo tengas | **Futuros** u **Opciones** → «AIM unitarias» |
| Cuando MexDer cambie el universo | Actualizar el catálogo con la plantilla | **Emisoras** → «Actualizar catálogo» |

Con Supabase conectado, todo lo que cargues queda guardado ahí automáticamente.

---

## 7. Problemas frecuentes

| Síntoma | Solución |
|---|---|
| `python` o `npm` «no se reconoce» | Reinstala Python marcando «Add Python to PATH», o Node.js, y abre una terminal nueva |
| `password authentication failed` | Revisa la contraseña en `.env`, sin corchetes `[ ]` |
| `connection refused` / `timeout` hacia Supabase | Usa la URI del **Session pooler** (puerto 5432), no la «Direct connection» |
| La página abre pero no muestra emisoras | Revisa que el backend esté corriendo (http://localhost:8000/api/health) y que `DATABASE_URL` sea correcta |
| `Address already in use` (puerto 8000 o 3000) | Ya hay otra copia corriendo: ciérrala o reinicia la computadora |
| Banxico responde 401 | Revisa `BANXICO_TOKEN` en `.env` |
| Cambiaste algo en el frontend y no se ve | Borra la carpeta `frontend/.next` y vuelve a arrancar |
