#!/bin/bash
set -e

echo ""
echo "╔══════════════════════════════════════╗"
echo "║     BollettaAI v2 — Setup Script     ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. Controlla Python ──────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "❌ Python 3 non trovato. Installalo da https://python.org"
  exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✅ Python $PY_VER trovato"

# ── 2. Controlla API Key ─────────────────────────────────────
if [ -z "$GEMINI_API_KEY" ]; then
  echo ""
  echo "⚠️  GEMINI_API_KEY non trovata nelle variabili d'ambiente."
  echo "   Ottieni una chiave gratuita su: https://aistudio.google.com/apikey"
  echo ""
  read -p "   Incolla qui la tua API Key Gemini: " APIKEY
  if [ -z "$APIKEY" ]; then
    echo "❌ API Key obbligatoria per l'analisi AI."
    exit 1
  fi
  export GEMINI_API_KEY="$APIKEY"
  echo ""
  echo "   Per salvarla permanentemente, aggiungi questa riga al tuo ~/.bashrc o ~/.zshrc:"
  echo "   export GEMINI_API_KEY=\"$APIKEY\""
fi

echo "✅ GEMINI_API_KEY configurata"

# ── 3. Virtual environment ───────────────────────────────────
if [ ! -d ".venv" ]; then
  echo ""
  echo "📦 Creo virtual environment Python..."
  python3 -m venv .venv
fi
source .venv/bin/activate
echo "✅ Virtual environment attivo"

# ── 4. Installa dipendenze ───────────────────────────────────
echo ""
echo "📥 Installo dipendenze..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "✅ Dipendenze installate"

# ── 5. Avvia server ─────────────────────────────────────────
echo ""
echo "════════════════════════════════════════"
echo "  🚀 BollettaAI in avvio..."
echo "  📌 Apri il browser su: http://localhost:8000"
echo "  🛑 Per fermare: Ctrl+C"
echo "════════════════════════════════════════"
echo ""

cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
