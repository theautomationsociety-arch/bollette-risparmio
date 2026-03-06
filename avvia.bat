@echo off
setlocal enabledelayedexpansion

echo.
echo ==========================================
echo    BollettaAI - Avvio Sito Completo
echo ==========================================
echo.

cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo ERRORE: Python non trovato. Scaricalo da https://python.org
    pause
    exit /b 1
)
echo [OK] Python trovato

if "%GEMINI_API_KEY%"=="" (
    echo.
    echo ATTENZIONE: GEMINI_API_KEY non configurata.
    echo Ottienila su: https://aistudio.google.com/apikey
    echo.
    set /p GEMINI_API_KEY="Incolla la tua API Key Gemini: "
    if "!GEMINI_API_KEY!"=="" (
        echo ERRORE: API Key obbligatoria.
        pause
        exit /b 1
    )
    echo.
    echo Per salvarla definitivamente:
    echo Pannello di Controllo - Sistema - Variabili d'ambiente
    echo Aggiungi: GEMINI_API_KEY = la-tua-chiave
)
echo [OK] GEMINI_API_KEY configurata

if "%ADMIN_TOKEN%"=="" (
    echo.
    echo ATTENZIONE: ADMIN_TOKEN non configurato.
    echo Il token di default e': admin123
    echo Impostane uno sicuro con: set ADMIN_TOKEN=tuo-token-segreto
    set ADMIN_TOKEN=admin123
)
echo [OK] ADMIN_TOKEN: !ADMIN_TOKEN!

if not exist ".venv" (
    echo.
    echo Creo virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
echo [OK] Virtual environment attivo

echo.
echo Installo dipendenze...
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt
if errorlevel 1 (
    echo ERRORE installazione dipendenze.
    pause
    exit /b 1
)
echo [OK] Dipendenze installate

echo.
echo ==========================================
echo   Sito pubblico:  http://localhost:8000
echo   Pannello admin: http://localhost:8000/admin
echo   Token admin:    !ADMIN_TOKEN!
echo   Per fermare:    Ctrl+C
echo ==========================================
echo.

cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

echo.
echo Server fermato.
pause
