#!/usr/bin/env bash
# Arranca la plataforma en Mac/Linux: backend (puerto 8000) y frontend (puerto 3000).
set -e
cd "$(dirname "$0")"
echo "== Backend =="
cd backend
if [ ! -d .venv ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip -q
  ./.venv/bin/pip install -r requirements.txt -q
fi
[ -f .env ] || { cp .env.example .env; echo "Se creó backend/.env: complete DATABASE_URL (o déjelo vacío para usar SQLite)."; }
./.venv/bin/uvicorn app.main:app --port 8000 &
BACK=$!
cd ../frontend
echo "== Frontend =="
[ -d node_modules ] || npm install --no-audit --no-fund
[ -d .next ] || npm run build
trap 'kill $BACK 2>/dev/null' EXIT
echo "Abra http://localhost:3000"
npm start
