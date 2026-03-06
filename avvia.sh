#!/bin/bash
set -e
cd "$(dirname "$0")"

echo ""
echo "=========================================="
echo "   BollettaAI - Avvio Sito Completo"
echo "=========================================="
echo ""

command -v python3 &>/dev/null || { echo "ERRORE: Python 3 non trovato"; exit 1; }
echo "[OK] Python: $(python3 --version)"

if [ -z "$GEMINI_API_KEY" ]; then
  echo ""
  echo "GEMINI_API_KEY non configurata."
  echo "Ottienila su: https://aistudio.google.com/apikey"
  read -p "Incolla qui la chiave: " GEMINI_API_KEY
  [ -z "$GEMINI_API_KEY" ] && echo "ERRORE: API Key obbligatoria." && exit 1
  export GEMINI_API_KEY
fi
echo "[OK] GEMINI_API_KEY configurata"

export ADMIN_TOKEN=${ADMIN_TOKEN:-"admin123"}
echo "[OK] ADMIN_TOKEN: $ADMIN_TOKEN"
if [ "$ADMIN_TOKEN" = "admin123" ]; then
  echo "     SUGGERIMENTO: cambialo con: export ADMIN_TOKEN=tuo-token-sicuro"
fi

[ ! -d ".venv" ] && { echo "Creo virtual environment..."; python3 -m venv .venv; }
source .venv/bin/activate
echo "[OK] Virtual environment attivo"

echo "Installo dipendenze..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "[OK] Dipendenze installate"

echo ""
echo "=========================================="
echo "  Sito pubblico:  http://localhost:8000"
echo "  Pannello admin: http://localhost:8000/admin"
echo "  Token admin:    $ADMIN_TOKEN"
echo "  Per fermare: Ctrl+C"
echo "=========================================="
echo ""

cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
