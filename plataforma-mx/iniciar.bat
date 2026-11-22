@echo off
REM Arranca la plataforma en Windows: backend (puerto 8000) y frontend (puerto 3000).
cd /d "%~dp0backend"
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip -q
  .venv\Scripts\pip install -r requirements.txt -q
)
if not exist .env (
  copy .env.example .env >nul
  echo Se creo backend\.env: complete DATABASE_URL o dejelo vacio para usar SQLite.
)
start "Backend - Plataforma MX" cmd /k .venv\Scripts\uvicorn app.main:app --port 8000
cd /d "%~dp0frontend"
if not exist node_modules call npm install --no-audit --no-fund
if not exist .next call npm run build
echo Abra http://localhost:3000
call npm start
