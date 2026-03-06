FROM python:3.11-slim

WORKDIR /app

# Dipendenze sistema (per httpx e multipart)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Installa dipendenze Python prima del codice (ottimizza layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copia il codice
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Crea cartella dati (sovrascritta dal volume in produzione)
RUN mkdir -p /app/data

# Healthcheck interno
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1"]  # SQLite non supporta multi-process writes
