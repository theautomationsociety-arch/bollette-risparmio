# 🔌 BollettaAI v2 — Comparatore Bollette Luce & Gas per PMI

> Analizza automaticamente le bollette elettriche e del gas con Google Gemini AI,  
> confronta le offerte del mercato libero e identifica i risparmi per la tua PMI.

---

## ✨ Funzionalità v2

| Funzione | Descrizione |
|----------|-------------|
| 📄 **Analisi Luce AI** | Estrae POD, fasce F1/F2/F3, costi, dati tecnici da qualsiasi bolletta PDF |
| 🔥 **Analisi Gas AI** | Estrae PDR, consumi Smc, costi, accise regionali da bollette gas |
| 🏆 **Comparazione Offerte** | Confronta con 10+ offerte luce e 7+ offerte gas, calcola risparmio annuo |
| 📊 **Dashboard** | Grafici andamento spese nel tempo per luce e gas |
| 📋 **Storico** | Tutte le bollette salvate, filtrabili per tipo, con eliminazione |
| 🏷️ **Gestione Offerte** | Aggiungi/disattiva offerte dal pannello web, senza toccare il codice |
| 📥 **Export CSV** | Scarica tutte le bollette in formato CSV (compatibile Excel italiano) |
| 🤖 **Insight AI** | Anomalie rilevate e suggerimenti personalizzati per ridurre i costi |
| 🐳 **Docker ready** | Avvio con un solo comando via Docker Compose |

---

## ⚡ Avvio Rapido (senza Docker)

### Prerequisiti
- Python 3.10 o superiore
- Una API Key Google Gemini **gratuita** → [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

### Mac / Linux
```bash
# Rendi eseguibile lo script e avvia
chmod +x avvia.sh
./avvia.sh
```
Lo script installa automaticamente le dipendenze, crea il virtual environment  
e ti chiede la API Key se non è già impostata.

### Windows
Doppio click su `avvia.bat`  
oppure da PowerShell:
```powershell
$env:GEMINI_API_KEY="la-tua-chiave"
pip install -r requirements.txt
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Manuale (qualsiasi OS)
```bash
# Imposta la chiave API
export GEMINI_API_KEY="la-tua-chiave"   # Mac/Linux
set GEMINI_API_KEY=la-tua-chiave        # Windows CMD

# Installa dipendenze
pip install -r requirements.txt

# Avvia il server
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Poi apri **http://localhost:8000** nel browser.

---

## 🐳 Avvio con Docker (consigliato per produzione)

```bash
# 1. Copia il file .env e imposta la tua chiave
cp .env.example .env
# Modifica .env e inserisci GEMINI_API_KEY=...

# 2. Avvia tutto
docker-compose up -d

# 3. Ferma
docker-compose down
```

I dati sono persistenti nella cartella `data/` anche dopo il riavvio del container.

---

## 📁 Struttura Progetto

```
comparatore-v2/
├── backend/
│   └── main.py              # API FastAPI completa
├── frontend/
│   └── index.html           # SPA interfaccia web
├── data/
│   └── bollette.db          # Database SQLite (creato automaticamente)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── avvia.sh                 # Avvio Mac/Linux
├── avvia.bat                # Avvio Windows
└── .env.example             # Template variabili d'ambiente
```

---

## 🔌 API Endpoints

### Bollette
| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `POST` | `/api/analizza/luce` | Analizza PDF bolletta elettrica |
| `POST` | `/api/analizza/gas` | Analizza PDF bolletta gas |
| `GET` | `/api/bollette` | Lista bollette (`?tipo=luce\|gas`) |
| `GET` | `/api/bollette/{id}` | Dettaglio bolletta |
| `DELETE` | `/api/bollette/{id}` | Elimina bolletta |

### Comparazione
| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `POST` | `/api/compara/{id}` | Compara con tutte le offerte attive |

### Offerte
| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `GET` | `/api/offerte/luce` | Lista offerte luce |
| `GET` | `/api/offerte/gas` | Lista offerte gas |
| `POST` | `/api/offerte/luce` | Crea nuova offerta luce |
| `POST` | `/api/offerte/gas` | Crea nuova offerta gas |
| `DELETE` | `/api/offerte/luce/{id}` | Disattiva offerta luce |
| `DELETE` | `/api/offerte/gas/{id}` | Disattiva offerta gas |

### Utilità
| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `GET` | `/api/statistiche` | Statistiche aggregate con trend mensile |
| `GET` | `/api/storico/consumi/{pod_pdr}` | Storico consumi per POD/PDR specifico |
| `GET` | `/api/export/csv` | Export CSV di tutte le bollette |
| `GET` | `/api/export/report/{id}` | Export JSON report comparativo |
| `GET` | `/api/health` | Health check e stato API Key |
| `GET` | `/docs` | Documentazione interattiva (Swagger UI) |

---

## 🗃️ Database

SQLite auto-creato in `data/bollette.db`. Tabelle:

| Tabella | Contenuto |
|---------|-----------|
| `bollette` | Tutte le bollette analizzate (luce + gas) |
| `offerte_luce` | Database offerte elettriche |
| `offerte_gas` | Database offerte gas |
| `comparazioni` | Storico comparazioni effettuate |
| `note_bollette` | Note manuali sulle bollette |

---

## 🔒 Sicurezza

- La **GEMINI_API_KEY** viene letta esclusivamente da variabile d'ambiente, mai hardcoded
- I **PDF delle bollette non vengono salvati** su disco: solo i dati estratti nel DB
- Il database SQLite è locale; i soli dati inviati a server esterni sono i PDF a Google Gemini per l'analisi

---

## 🔮 Roadmap

- [ ] Autenticazione multi-utente (username/password)
- [ ] Aggiornamento automatico prezzi offerte da ARERA via scraping schedulato
- [ ] Notifiche email scadenza offerte
- [ ] Grafico radar confronto offerte
- [ ] Analisi multi-POD (più sedi aziendali)
- [ ] Integrazione fatturazione elettronica XML
- [ ] Report PDF esportabile con loghi e branding PMI
