@echo off
setlocal enabledelayedexpansion

echo.
echo ==========================================
echo    BollettaAI v3 - Setup e Avvio
echo ==========================================
echo.

cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo ERRORE: Python non trovato. Scaricalo da https://python.org
    pause
    exit /b 1
)
echo [OK] Python trovato:
python --version

if "%GEMINI_API_KEY%"=="" (
    echo.
    echo ATTENZIONE: GEMINI_API_KEY non configurata.
    echo Ottieni una chiave gratuita su: https://aistudio.google.com/apikey
    echo.
    set /p GEMINI_API_KEY="Incolla qui la tua API Key Gemini: "
    if "!GEMINI_API_KEY!"=="" (
        echo ERRORE: API Key obbligatoria.
        pause
        exit /b 1
    )
    echo.
    echo Per salvarla in modo permanente:
    echo Pannello di Controllo - Sistema - Variabili d'ambiente avanzate
    echo Aggiungi: GEMINI_API_KEY = la-tua-chiave
)
echo [OK] GEMINI_API_KEY configurata

if not exist ".venv" (
    echo.
    echo Creo virtual environment Python...
    python -m venv .venv
    if errorlevel 1 (
        echo ERRORE nella creazione del virtual environment.
        pause
        exit /b 1
    )
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
echo   Avvio server su http://localhost:8000
echo   Apri il browser su quell'indirizzo.
echo   Per fermare: premi Ctrl+C
echo ==========================================
echo.

cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

echo.
echo Server fermato.
pause
