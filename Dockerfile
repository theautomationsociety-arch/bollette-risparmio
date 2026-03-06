FROM python:3.11-slim

WORKDIR /app

# Dipendenze sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Dipendenze Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia sorgenti
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Crea cartella dati (il volume Docker si monterà qui)
RUN mkdir -p /app/data

EXPOSE 8000

# Avvia con uvicorn
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
