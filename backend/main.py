"""
BollettaAI v3 — Backend
Comparatore bollette Luce + Gas per clienti domestici e PMI italiane.
Novità v3:
  - Profili utenza: Domestico Residente (D2), Non Residente (D3), PMI/BTA, Condominio
  - IVA e accise corrette per profilo
  - Offerte BiFuel con sconti combinati luce+gas
  - Aggiornamento PUN/PSV da Portale Offerte open data (senza API key)
  - Caricamento offerte da PDF, file o URL con estrazione AI
"""

import os, json, uuid, logging, io, csv, re, httpx
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, Body, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
import sqlite3

# ─── Logging ──────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent.parent
FRONTEND_PATH = BASE_DIR / "frontend"
DB_PATH       = BASE_DIR / "data" / "bollette.db"
LOG_PATH      = BASE_DIR / "data" / "app.log"
LOG_PATH.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(str(LOG_PATH)), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ─── Costanti fiscali italiane ────────────────────────────────────────────────
# IVA per tipologia utenza
IVA = {
    "D2":  0.10,   # domestico residente
    "D3":  0.10,   # domestico non residente
    "BTA": 0.22,   # PMI / uso business
    "CDO": 0.10,   # condominio (uso comune)
}

# Accise elettricità €/kWh (2025) — variano per profilo e scaglione
ACCISE_LUCE = {
    "D2":  {"base": 0.0227, "oltre_1800": 0.0227},  # flat per domestico
    "D3":  {"base": 0.0227, "oltre_1800": 0.0227},
    "BTA": {"base": 0.01240, "oltre_1800": 0.01240}, # non domestico
    "CDO": {"base": 0.0227, "oltre_1800": 0.0227},
}

# Accise gas €/Smc (2025)
ACCISE_GAS = {
    "D2":  {"uso_riscaldamento": 0.0174, "altri_usi": 0.0042},
    "D3":  {"uso_riscaldamento": 0.0174, "altri_usi": 0.0042},
    "BTA": {"uso_riscaldamento": 0.0349, "altri_usi": 0.0125},
    "CDO": {"uso_riscaldamento": 0.0174, "altri_usi": 0.0042},
}

PROFILI_LABEL = {
    "D2":  "Domestico Residente",
    "D3":  "Domestico Non Residente",
    "BTA": "PMI / Non Domestico BT",
    "CDO": "Condominio",
}

# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("BollettaAI v3 avviato")
    yield

app = FastAPI(
    title="BollettaAI v3",
    description="Comparatore bollette Luce & Gas — domestico e PMI",
    version="3.0.0",
    lifespan=lifespan
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

if FRONTEND_PATH.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_PATH)), name="static")

# ─── DB ───────────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS bollette (
            id                  TEXT PRIMARY KEY,
            tipo_utenza         TEXT DEFAULT 'luce',
            profilo_utenza      TEXT DEFAULT 'D2',
            nome_file           TEXT,
            data_caricamento    TEXT,
            fornitore           TEXT,
            numero_fattura      TEXT,
            periodo_inizio      TEXT,
            periodo_fine        TEXT,
            scadenza            TEXT,
            totale_fattura      REAL,
            mercato             TEXT,
            pod_pdr             TEXT,
            potenza_impegnata   REAL,
            consumo_totale      REAL,
            unita_misura        TEXT DEFAULT 'kWh',
            spesa_energia       REAL,
            spesa_trasporto     REAL,
            oneri_sistema       REAL,
            imposte_iva         REAL,
            dati_json           TEXT,
            costo_unitario_eff  REAL,
            note_utente         TEXT,
            stato               TEXT DEFAULT 'elaborata'
        );

        CREATE TABLE IF NOT EXISTS offerte_luce (
            id                    TEXT PRIMARY KEY,
            fornitore             TEXT NOT NULL,
            nome_offerta          TEXT NOT NULL,
            tipo                  TEXT DEFAULT 'FISSO',
            profili_compatibili   TEXT DEFAULT 'D2,D3,BTA,CDO',
            prezzo_f1             REAL,
            prezzo_f2             REAL,
            prezzo_f3             REAL,
            prezzo_f23            REAL,
            prezzo_monorario      REAL,
            spread_pun            REAL,
            quota_fissa_annua     REAL DEFAULT 0,
            oneri_trasporto_stima REAL DEFAULT 0,
            sconto_bifuel_perc    REAL DEFAULT 0,
            valida_fino           TEXT,
            note                  TEXT,
            mercato               TEXT DEFAULT 'Libero',
            url_offerta           TEXT,
            attiva                INTEGER DEFAULT 1,
            data_inserimento      TEXT
        );

        CREATE TABLE IF NOT EXISTS offerte_gas (
            id                    TEXT PRIMARY KEY,
            fornitore             TEXT NOT NULL,
            nome_offerta          TEXT NOT NULL,
            tipo                  TEXT DEFAULT 'FISSO',
            profili_compatibili   TEXT DEFAULT 'D2,D3,BTA,CDO',
            uso_gas               TEXT DEFAULT 'CACR',
            prezzo_smc            REAL,
            spread_psv            REAL,
            quota_fissa_annua     REAL DEFAULT 0,
            quota_variabile_smc   REAL DEFAULT 0,
            sconto_bifuel_perc    REAL DEFAULT 0,
            valida_fino           TEXT,
            note                  TEXT,
            mercato               TEXT DEFAULT 'Libero',
            url_offerta           TEXT,
            attiva                INTEGER DEFAULT 1,
            data_inserimento      TEXT
        );

        CREATE TABLE IF NOT EXISTS indici_mercato (
            id          TEXT PRIMARY KEY,
            tipo        TEXT NOT NULL,
            periodo     TEXT NOT NULL,
            valore      REAL NOT NULL,
            fonte       TEXT,
            aggiornato  TEXT
        );

        CREATE TABLE IF NOT EXISTS comparazioni (
            id                  TEXT PRIMARY KEY,
            bolletta_id         TEXT,
            tipo_utenza         TEXT,
            profilo_utenza      TEXT,
            data_comparazione   TEXT,
            risultati_json      TEXT,
            bifuel_applicato    INTEGER DEFAULT 0,
            FOREIGN KEY (bolletta_id) REFERENCES bollette(id)
        );

        CREATE INDEX IF NOT EXISTS idx_bollette_tipo   ON bollette(tipo_utenza);
        CREATE INDEX IF NOT EXISTS idx_bollette_profilo ON bollette(profilo_utenza);
        CREATE INDEX IF NOT EXISTS idx_bollette_pod    ON bollette(pod_pdr);
        CREATE INDEX IF NOT EXISTS idx_indici_tipo     ON indici_mercato(tipo, periodo);
    """)
    conn.commit()

    if conn.execute("SELECT COUNT(*) FROM offerte_luce").fetchone()[0] == 0:
        _seed_offerte_luce(conn)
    if conn.execute("SELECT COUNT(*) FROM offerte_gas").fetchone()[0] == 0:
        _seed_offerte_gas(conn)
    if conn.execute("SELECT COUNT(*) FROM indici_mercato").fetchone()[0] == 0:
        _seed_indici(conn)
    conn.close()

def _seed_offerte_luce(conn):
    now = datetime.now().isoformat()
    # profili_compatibili: D2=residente, D3=non residente, BTA=PMI, CDO=condominio
    offerte = [
        # id, fornitore, nome, tipo, profili, f1, f2, f3, f23, mono, spread_pun, qf_annua, trasp/mese, sconto_bifuel%, valida, note, mercato, url
        ("enel-luce-web",   "Enel Energia",   "Luce Web",            "VARIABILE", "D2,D3,BTA,CDO", 0.1823,0.1523,0.1423,0.1473,None, 0.018, 72.0,  45.0, 5.0,  "2026-12-31","Indicizzato PUN, sconto 5% se attivi anche gas Enel","Libero","https://www.enel.it"),
        ("a2a-smart",       "A2A Energia",    "Smart Business",      "FISSO",     "BTA,CDO",       0.1650,0.1450,0.1350,None,  None, None,  84.0,  50.0, 4.0,  "2026-06-30","Prezzo fisso 12 mesi, per PMI e condomini",          "Libero","https://www.a2a.eu"),
        ("a2a-casa",        "A2A Energia",    "Smart Casa",          "FISSO",     "D2,D3",         0.1670,0.1470,None,  0.1470,None, None,  72.0,  45.0, 4.0,  "2026-06-30","Per clienti domestici, biorario F1/F23",             "Libero","https://www.a2a.eu"),
        ("eni-business",    "Eni Plenitude",  "Plenitude Business",  "FISSO",     "BTA",           0.1720,0.1520,0.1420,None,  None, None,  96.0,  48.0, 5.0,  "2026-09-30","100% rinnovabile, solo PMI",                         "Libero","https://www.plenitude.com"),
        ("eni-casa",        "Eni Plenitude",  "Plenitude Casa",      "FISSO",     "D2,D3",         0.1700,0.1500,None,  0.1500,None, None,  84.0,  46.0, 5.0,  "2026-09-30","100% rinnovabile, clienti domestici",               "Libero","https://www.plenitude.com"),
        ("wekiwi-pmi",      "Wekiwi",         "PMI Digitale",        "FISSO",     "BTA",           0.1590,0.1390,0.1290,None,  None, None,  48.0,  40.0, 3.0,  "2026-08-31","Solo PMI, gestione 100% online",                    "Libero","https://www.wekiwi.it"),
        ("wekiwi-casa",     "Wekiwi",         "Casa Digitale",       "FISSO",     "D2,D3",         0.1610,0.1410,None,  0.1410,None, None,  42.0,  39.0, 3.0,  "2026-08-31","Domestico, senza canone se paghi domiciliato",      "Libero","https://www.wekiwi.it"),
        ("sorgenia-open",   "Sorgenia",       "Open Power",          "VARIABILE", "D2,D3,BTA,CDO", 0.1800,0.1500,0.1400,0.1450,None, 0.017, 54.0,  43.0, 4.5,  "2026-12-31","100% rinnovabile, app dedicata, bifuel -4.5%",      "Libero","https://www.sorgenia.it"),
        ("illumia-smart",   "Illumia",        "Smart Business",      "FISSO",     "BTA,CDO",       0.1610,0.1410,0.1310,None,  None, None,  60.0,  41.0, 3.5,  "2026-09-30","PMI e condomini, assistenza 7/7",                   "Libero","https://www.illumia.it"),
        ("illumia-casa",    "Illumia",        "Smart Casa",          "FISSO",     "D2,D3",         0.1625,0.1425,None,  0.1425,None, None,  54.0,  40.0, 3.5,  "2026-09-30","Domestico, prezzo fisso 12 mesi",                   "Libero","https://www.illumia.it"),
        ("acea-easy",       "Acea Energia",   "Easy Business",       "FISSO",     "BTA,CDO",       0.1700,0.1500,0.1400,None,  None, None,  78.0,  46.0, 4.0,  "2026-10-31","PMI Roma e Centro Italia",                          "Libero","https://www.acea.it"),
        ("edison-start",    "Edison Energia", "Start Famiglia",      "FISSO",     "D2,D3",         0.1630,0.1430,None,  0.1430,None, None,  66.0,  44.0, 4.0,  "2026-07-31","Canone mensile incluso 24 mesi",                    "Libero","https://www.edison.it"),
    ]
    conn.executemany("""
        INSERT INTO offerte_luce (id, fornitore, nome_offerta, tipo, profili_compatibili,
            prezzo_f1, prezzo_f2, prezzo_f3, prezzo_f23, prezzo_monorario, spread_pun,
            quota_fissa_annua, oneri_trasporto_stima, sconto_bifuel_perc,
            valida_fino, note, mercato, url_offerta, attiva, data_inserimento)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)
    """, [o + (now,) for o in offerte])
    conn.commit()

def _seed_offerte_gas(conn):
    now = datetime.now().isoformat()
    offerte = [
        # id, fornitore, nome, tipo, profili, uso_gas, prezzo_smc, spread_psv, qf_annua, qvar_smc, sconto_bifuel%, valida, note, mercato, url
        ("enel-gas",        "Enel Energia",  "Gas Web",             "VARIABILE","D2,D3,BTA", "CACR", 0.48, 0.02,  60.0, 0.02,  5.0, "2026-12-31","Indicizzato PSV+spread, -5% se attivi anche luce","Libero","https://www.enel.it"),
        ("a2a-gas-smart",   "A2A Energia",   "Gas Smart Business",  "FISSO",    "BTA",       "C",    0.52, None,  72.0, 0.02,  4.0, "2026-06-30","Prezzo fisso 12 mesi, PMI uso cottura",            "Libero","https://www.a2a.eu"),
        ("a2a-gas-casa",    "A2A Energia",   "Gas Smart Casa",      "FISSO",    "D2,D3",     "CACR", 0.50, None,  66.0, 0.02,  4.0, "2026-06-30","Domestico CACR, prezzo fisso",                    "Libero","https://www.a2a.eu"),
        ("eni-gas-plus",    "Eni Plenitude", "Gas Plus Business",   "FISSO",    "BTA",       "C",    0.50, None,  84.0, 0.025, 5.0, "2026-09-30","Sconto 5% con offerta luce Plenitude",            "Libero","https://www.plenitude.com"),
        ("eni-gas-casa",    "Eni Plenitude", "Gas Plus Casa",       "FISSO",    "D2,D3",     "CACR", 0.49, None,  78.0, 0.022, 5.0, "2026-09-30","Domestico CACR, 100% compensazione CO2",          "Libero","https://www.plenitude.com"),
        ("sorgenia-gas",    "Sorgenia",      "Open Gas",            "VARIABILE","D2,D3,BTA", "CACR", 0.47, 0.019, 54.0, 0.02,  4.5, "2026-12-31","PSV+spread, CO2 neutralizzato, -4.5% bifuel",     "Libero","https://www.sorgenia.it"),
        ("illumia-gas",     "Illumia",       "Gas Smart",           "FISSO",    "D2,D3,BTA", "CACR", 0.495,None,  60.0, 0.019, 3.5, "2026-09-30","Fisso 12 mesi, gestione online",                  "Libero","https://www.illumia.it"),
        ("wekiwi-gas",      "Wekiwi",        "Gas Digitale",        "FISSO",    "D2,D3,BTA", "CACR", 0.488,None,  48.0, 0.018, 3.0, "2026-08-31","Solo online, fattura digitale",                   "Libero","https://www.wekiwi.it"),
    ]
    conn.executemany("""
        INSERT INTO offerte_gas (id, fornitore, nome_offerta, tipo, profili_compatibili,
            uso_gas, prezzo_smc, spread_psv, quota_fissa_annua, quota_variabile_smc,
            sconto_bifuel_perc, valida_fino, note, mercato, url_offerta, attiva, data_inserimento)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)
    """, [o + (now,) for o in offerte])
    conn.commit()

def _seed_indici(conn):
    now = datetime.now().isoformat()
    indici = [
        ("pun-2026-01", "PUN",  "2026-01", 0.1327, "GME/Portale Offerte", now),
        ("pun-2025-12", "PUN",  "2025-12", 0.1155, "GME/Portale Offerte", now),
        ("pun-2025-11", "PUN",  "2025-11", 0.1212, "GME/Portale Offerte", now),
        ("pun-2025-10", "PUN",  "2025-10", 0.1110, "GME/Portale Offerte", now),
        ("pun-2025-09", "PUN",  "2025-09", 0.1085, "GME/Portale Offerte", now),
        ("pun-2025-08", "PUN",  "2025-08", 0.1045, "GME/Portale Offerte", now),
        ("psv-2026-01", "PSV",  "2026-01", 0.3820, "GME/Portale Offerte", now),
        ("psv-2025-12", "PSV",  "2025-12", 0.3650, "GME/Portale Offerte", now),
        ("psv-2025-11", "PSV",  "2025-11", 0.3580, "GME/Portale Offerte", now),
        ("psv-2025-10", "PSV",  "2025-10", 0.3420, "GME/Portale Offerte", now),
    ]
    conn.executemany("""
        INSERT INTO indici_mercato (id, tipo, periodo, valore, fonte, aggiornato)
        VALUES (?,?,?,?,?,?)
    """, indici)
    conn.commit()

# ─── Helpers ──────────────────────────────────────────────────────────────────
def _get_gemini_client():
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise HTTPException(500, "GEMINI_API_KEY non configurata")
    from google import genai
    return genai.Client(api_key=key)

def _parse_json_response(text: str) -> dict:
    clean = text.replace("```json","").replace("```","").strip()
    return json.loads(clean)

def _calcola_mesi(d1_str, d2_str) -> int:
    try:
        d1 = date.fromisoformat(d1_str)
        d2 = date.fromisoformat(d2_str)
        return max(1, round((d2-d1).days/30))
    except:
        return 1

def _ultimo_pun(conn) -> float:
    row = conn.execute(
        "SELECT valore FROM indici_mercato WHERE tipo='PUN' ORDER BY periodo DESC LIMIT 1"
    ).fetchone()
    return row["valore"] if row else 0.113

def _ultimo_psv(conn) -> float:
    row = conn.execute(
        "SELECT valore FROM indici_mercato WHERE tipo='PSV' ORDER BY periodo DESC LIMIT 1"
    ).fetchone()
    return row["valore"] if row else 0.382

# ─── Prompt AI ────────────────────────────────────────────────────────────────
PROMPT_LUCE = """
Analizza questa bolletta elettrica italiana. Identifica il tipo cliente (domestico/PMI).
Restituisci SOLO JSON valido, nessun testo fuori:
{
  "dati_generali": {
    "fornitore": null, "numero_fattura": null,
    "periodo_fatturazione": {"inizio": "YYYY-MM-DD", "fine": "YYYY-MM-DD"},
    "scadenza": null, "totale_fattura": 0.0,
    "mercato": "Libero o Tutelato",
    "profilo_stimato": "D2 o D3 o BTA o CDO"
  },
  "dati_tecnici": {
    "pod_pdr": null, "potenza_impegnata": 0.0, "potenza_disponibile": 0.0,
    "tipologia_uso": null, "indirizzo_fornitura": null, "tensione": null
  },
  "letture_e_consumi": {
    "consumo_totale_periodo": 0.0,
    "ripartizione_fasce": {
      "F1": {"consumo": 0.0, "prezzo_unitario": 0.0},
      "F2": {"consumo": 0.0, "prezzo_unitario": 0.0},
      "F3": {"consumo": 0.0, "prezzo_unitario": 0.0},
      "F23": {"consumo": 0.0, "prezzo_unitario": 0.0}
    },
    "lettura_stimata_o_reale": null,
    "lettura_precedente": 0.0, "lettura_attuale": 0.0
  },
  "dettaglio_costi": {
    "spesa_materia_energia": 0.0, "trasporto_gestione_contatore": 0.0,
    "oneri_sistema": 0.0, "imposte_iva": 0.0,
    "canone_rai": 0.0, "accise": 0.0, "altre_partite": 0.0
  },
  "analisi_ai": {
    "anomalie_rilevate": [], "suggerimenti": [],
    "fascia_consumo": "basso|medio|alto",
    "efficienza_energetica": null, "note_aggiuntive": null
  }
}
"""

PROMPT_GAS = """
Analizza questa bolletta gas italiana. Identifica il tipo cliente e l'uso del gas.
Restituisci SOLO JSON valido, nessun testo fuori:
{
  "dati_generali": {
    "fornitore": null, "numero_fattura": null,
    "periodo_fatturazione": {"inizio": "YYYY-MM-DD", "fine": "YYYY-MM-DD"},
    "scadenza": null, "totale_fattura": 0.0,
    "mercato": "Libero o Tutelato",
    "profilo_stimato": "D2 o D3 o BTA"
  },
  "dati_tecnici": {
    "pdr": null, "remi": null, "classe_contatore": null,
    "tipologia_uso": null, "uso_gas": "CACR o C o R o CA",
    "indirizzo_fornitura": null, "coefficiente_conversione": 0.0
  },
  "letture_e_consumi": {
    "consumo_totale_smc": 0.0, "consumo_totale_kwh": 0.0,
    "potere_calorifico": 0.0, "lettura_stimata_o_reale": null,
    "lettura_precedente": 0.0, "lettura_attuale": 0.0
  },
  "dettaglio_costi": {
    "spesa_materia_gas": 0.0, "trasporto_distribuzione": 0.0,
    "oneri_sistema": 0.0, "imposte_iva": 0.0,
    "accise": 0.0, "addizionale_regionale": 0.0, "altre_partite": 0.0
  },
  "analisi_ai": {
    "anomalie_rilevate": [], "suggerimenti": [],
    "fascia_consumo": "basso|medio|alto",
    "stagionalita": null, "note_aggiuntive": null
  }
}
"""

PROMPT_OFFERTA = """
Estrai i dettagli di questa offerta commerciale di energia elettrica o gas.
Identifica se è per domestico (D2/D3) o PMI (BTA) o entrambi.
Restituisci SOLO JSON valido:
{
  "tipo_utenza": "luce o gas",
  "fornitore": null,
  "nome_offerta": null,
  "tipo_prezzo": "FISSO o VARIABILE",
  "profili_compatibili": "D2,D3 o BTA o D2,D3,BTA",
  "uso_gas": "CACR o C o null (solo per gas)",
  "prezzo_f1_eur_kwh": null,
  "prezzo_f2_eur_kwh": null,
  "prezzo_f3_eur_kwh": null,
  "prezzo_f23_eur_kwh": null,
  "prezzo_monorario_eur_kwh": null,
  "spread_pun": null,
  "prezzo_smc": null,
  "spread_psv": null,
  "quota_fissa_annua_eur": null,
  "sconto_bifuel_percentuale": null,
  "valida_fino": "YYYY-MM-DD o null",
  "note": null,
  "mercato": "Libero o Tutelato"
}
"""

# ═══════════════════════════════════════════════════════════════════════════════
# ROOT & HEALTH
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/", include_in_schema=False)
async def root():
    idx = FRONTEND_PATH / "index.html"
    return FileResponse(str(idx)) if idx.exists() else {"msg":"BollettaAI v3"}

@app.get("/api/health")
async def health():
    conn = get_db()
    n_luce = conn.execute("SELECT COUNT(*) FROM bollette WHERE tipo_utenza='luce'").fetchone()[0]
    n_gas  = conn.execute("SELECT COUNT(*) FROM bollette WHERE tipo_utenza='gas'").fetchone()[0]
    pun    = _ultimo_pun(conn)
    psv    = _ultimo_psv(conn)
    conn.close()
    return {
        "status": "ok", "version": "3.0.0",
        "gemini_key_set": bool(os.environ.get("GEMINI_API_KEY")),
        "bollette": {"luce": n_luce, "gas": n_gas},
        "indici": {"PUN_ultimo": pun, "PSV_ultimo": psv},
        "timestamp": datetime.now().isoformat()
    }

# ═══════════════════════════════════════════════════════════════════════════════
# ANALISI BOLLETTE
# ═══════════════════════════════════════════════════════════════════════════════
@app.post("/api/analizza/luce")
async def analizza_luce(
    file: UploadFile = File(...),
    profilo: str = "D2"
):
    return await _analizza(file, "luce", profilo)

@app.post("/api/analizza/gas")
async def analizza_gas(
    file: UploadFile = File(...),
    profilo: str = "D2"
):
    return await _analizza(file, "gas", profilo)

async def _analizza(file: UploadFile, tipo: str, profilo: str):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Solo PDF accettati")
    if profilo not in IVA:
        raise HTTPException(400, f"Profilo non valido. Valori: {list(IVA.keys())}")

    raw = await file.read()
    if len(raw) > 15*1024*1024:
        raise HTTPException(400, "File troppo grande (max 15 MB)")

    from google.genai import types
    client = _get_gemini_client()
    prompt = PROMPT_LUCE if tipo == "luce" else PROMPT_GAS

    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt, types.Part.from_bytes(data=raw, mime_type="application/pdf")],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        dati = _parse_json_response(resp.text)
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        raise HTTPException(500, f"Errore AI: {e}")

    # Usa profilo suggerito dall'AI se l'utente non l'ha specificato esplicitamente
    profilo_ai = (dati.get("dati_generali",{}).get("profilo_stimato") or profilo).upper()
    profilo_finale = profilo if profilo != "D2" else (profilo_ai if profilo_ai in IVA else "D2")

    bid = str(uuid.uuid4())
    dg  = dati.get("dati_generali",{})
    dt  = dati.get("dati_tecnici",{})
    lc  = dati.get("letture_e_consumi",{})
    dc  = dati.get("dettaglio_costi",{})
    pf  = dg.get("periodo_fatturazione") or {}

    consumo = (lc.get("consumo_totale_periodo") or lc.get("consumo_totale_smc") or 0)
    unita   = "kWh" if tipo=="luce" else "Smc"
    pod_pdr = dt.get("pod_pdr") or dt.get("pdr")
    spesa_e = dc.get("spesa_materia_energia") or dc.get("spesa_materia_gas") or 0
    costo_u = round(spesa_e/consumo,5) if consumo>0 else None

    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO bollette (id, tipo_utenza, profilo_utenza, nome_file, data_caricamento,
                fornitore, numero_fattura, periodo_inizio, periodo_fine, scadenza,
                totale_fattura, mercato, pod_pdr, potenza_impegnata, consumo_totale,
                unita_misura, spesa_energia, spesa_trasporto, oneri_sistema, imposte_iva,
                dati_json, costo_unitario_eff)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            bid, tipo, profilo_finale, file.filename, datetime.now().isoformat(),
            dg.get("fornitore"), dg.get("numero_fattura"),
            pf.get("inizio"), pf.get("fine"), dg.get("scadenza"),
            dg.get("totale_fattura"), dg.get("mercato"),
            pod_pdr, dt.get("potenza_impegnata"), consumo, unita,
            spesa_e,
            dc.get("trasporto_gestione_contatore") or dc.get("trasporto_distribuzione"),
            dc.get("oneri_sistema"), dc.get("imposte_iva"),
            json.dumps(dati, ensure_ascii=False), costo_u
        ))
        conn.commit(); conn.close()
    except Exception as e:
        logger.error(f"DB error: {e}")

    return {
        "bolletta_id": bid, "tipo_utenza": tipo,
        "profilo_utenza": profilo_finale,
        "profilo_label": PROFILI_LABEL.get(profilo_finale),
        "dati": dati, "costo_unitario_effettivo": costo_u, "unita_misura": unita
    }

# ═══════════════════════════════════════════════════════════════════════════════
# GESTIONE BOLLETTE
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/api/bollette")
async def lista_bollette(tipo: Optional[str]=None, profilo: Optional[str]=None, limit:int=100):
    conn = get_db()
    q = "SELECT id,tipo_utenza,profilo_utenza,nome_file,data_caricamento,fornitore,periodo_inizio,periodo_fine,totale_fattura,consumo_totale,unita_misura,costo_unitario_eff,mercato,pod_pdr FROM bollette WHERE 1=1"
    p = []
    if tipo:    q += " AND tipo_utenza=?";    p.append(tipo)
    if profilo: q += " AND profilo_utenza=?"; p.append(profilo)
    q += " ORDER BY data_caricamento DESC LIMIT ?"; p.append(limit)
    rows = conn.execute(q,p).fetchall(); conn.close()
    return [dict(r) for r in rows]

@app.get("/api/bollette/{bid}")
async def dettaglio_bolletta(bid: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM bollette WHERE id=?", (bid,)).fetchone()
    conn.close()
    if not row: raise HTTPException(404,"Non trovata")
    d = dict(row)
    if d.get("dati_json"): d["dati"] = json.loads(d["dati_json"])
    return d

@app.delete("/api/bollette/{bid}")
async def elimina_bolletta(bid: str):
    conn = get_db()
    conn.execute("DELETE FROM comparazioni WHERE bolletta_id=?", (bid,))
    r = conn.execute("DELETE FROM bollette WHERE id=?", (bid,))
    conn.commit(); conn.close()
    if r.rowcount==0: raise HTTPException(404,"Non trovata")
    return {"deleted": True}

@app.patch("/api/bollette/{bid}")
async def aggiorna_bolletta(bid: str, payload: dict = Body(...)):
    conn = get_db()
    if "nota" in payload:
        conn.execute("UPDATE bollette SET note_utente=? WHERE id=?", (payload["nota"], bid))
    if "profilo_utenza" in payload and payload["profilo_utenza"] in IVA:
        conn.execute("UPDATE bollette SET profilo_utenza=? WHERE id=?", (payload["profilo_utenza"], bid))
    conn.commit(); conn.close()
    return {"updated": True}

# ═══════════════════════════════════════════════════════════════════════════════
# COMPARAZIONE — con profilo, bifuel, PUN/PSV dinamico
# ═══════════════════════════════════════════════════════════════════════════════
@app.post("/api/compara/{bid}")
async def compara(bid: str, bifuel_bolletta_id: Optional[str] = Body(None, embed=True)):
    """
    Compara una bolletta con tutte le offerte compatibili col suo profilo.
    Se si passa bifuel_bolletta_id (id dell'altra bolletta luce/gas dello stesso utente),
    applica lo sconto BiFuel alle offerte che lo prevedono.
    """
    conn = get_db()
    row = conn.execute("SELECT * FROM bollette WHERE id=?", (bid,)).fetchone()
    if not row: conn.close(); raise HTTPException(404,"Bolletta non trovata")
    b = dict(row)
    tipo    = b.get("tipo_utenza","luce")
    profilo = b.get("profilo_utenza","D2")
    dati    = json.loads(b["dati_json"]) if b["dati_json"] else {}
    mesi    = _calcola_mesi(b.get("periodo_inizio",""), b.get("periodo_fine",""))
    fatt    = 12/mesi
    costo_att_annuo = (b.get("totale_fattura") or 0) * fatt
    pun = _ultimo_pun(conn)
    psv = _ultimo_psv(conn)

    # Verifica se c'è l'altra bolletta per bifuel
    bifuel_attivo = False
    if bifuel_bolletta_id:
        other = conn.execute("SELECT id,tipo_utenza FROM bollette WHERE id=?", (bifuel_bolletta_id,)).fetchone()
        bifuel_attivo = bool(other and other["tipo_utenza"] != tipo)

    if tipo == "luce":
        risultati = _compara_luce(conn, b, dati, mesi, fatt, costo_att_annuo, profilo, pun, bifuel_attivo)
    else:
        risultati = _compara_gas(conn, b, dati, mesi, fatt, costo_att_annuo, profilo, psv, bifuel_attivo)

    risultati.sort(key=lambda x: x["costo_stimato_annuo"])
    conn.execute("""
        INSERT INTO comparazioni (id,bolletta_id,tipo_utenza,profilo_utenza,data_comparazione,risultati_json,bifuel_applicato)
        VALUES (?,?,?,?,?,?,?)
    """, (str(uuid.uuid4()), bid, tipo, profilo, datetime.now().isoformat(),
          json.dumps(risultati, ensure_ascii=False), int(bifuel_attivo)))
    conn.commit(); conn.close()

    return {
        "bolletta_id": bid, "tipo_utenza": tipo,
        "profilo_utenza": profilo, "profilo_label": PROFILI_LABEL.get(profilo),
        "fornitore_attuale": b.get("fornitore"),
        "costo_attuale_periodo": b.get("totale_fattura"),
        "costo_attuale_annuo_stimato": round(costo_att_annuo,2),
        "periodo_mesi": mesi,
        "consumo_totale": b.get("consumo_totale"),
        "unita_misura": b.get("unita_misura"),
        "iva_applicata_perc": IVA.get(profilo,0.22)*100,
        "bifuel_attivo": bifuel_attivo,
        "pun_utilizzato": pun, "psv_utilizzato": psv,
        "offerte": risultati,
        "migliore_offerta": risultati[0] if risultati else None,
        "risparmio_massimo_annuo": round(risultati[0]["risparmio_annuo_vs_attuale"],2) if risultati else 0
    }

def _costo_luce(of: dict, f1,f2,f3,f23, consumo_tot, mesi, pun, iva_rate) -> float:
    """Calcola costo energia per un'offerta luce con gestione PUN e fasce domestico/PMI."""
    # Prezzo effettivo per fascia
    if of.get("tipo") == "VARIABILE" and of.get("spread_pun"):
        pe_f1  = pun + of["spread_pun"]
        pe_f2  = pun + of["spread_pun"] * 0.85
        pe_f3  = pun + of["spread_pun"] * 0.75
        pe_f23 = pun + of["spread_pun"] * 0.80
    else:
        pe_f1  = of.get("prezzo_f1") or 0
        pe_f2  = of.get("prezzo_f2") or 0
        pe_f3  = of.get("prezzo_f3") or 0
        pe_f23 = of.get("prezzo_f23") or 0

    # Fasce disponibili
    if f1 and (f2 or f3):
        # triorario (PMI)
        ce = f1*pe_f1 + f2*pe_f2 + f3*pe_f3
    elif f1 and f23:
        # biorario (domestico)
        ce = f1*pe_f1 + f23*pe_f23
    elif consumo_tot:
        if of.get("prezzo_monorario"):
            ce = consumo_tot * of["prezzo_monorario"]
        elif pe_f1:
            ce = consumo_tot * pe_f1  # worst case: tutto in F1
        else:
            p_medio = (pe_f1+pe_f2+pe_f3)/3 if pe_f1 else 0
            ce = consumo_tot * p_medio
    else:
        ce = 0

    qf     = (of.get("quota_fissa_annua") or 0) / 12 * mesi
    trasp  = (of.get("oneri_trasporto_stima") or 0) * mesi
    sub    = ce + qf + trasp
    iva    = sub * iva_rate
    return ce, sub + iva

def _compara_luce(conn, b, dati, mesi, fatt, costo_att_annuo, profilo, pun, bifuel) -> list:
    fasce = dati.get("letture_e_consumi",{}).get("ripartizione_fasce",{})
    f1    = (fasce.get("F1") or {}).get("consumo") or 0
    f2    = (fasce.get("F2") or {}).get("consumo") or 0
    f3    = (fasce.get("F3") or {}).get("consumo") or 0
    f23   = (fasce.get("F23") or {}).get("consumo") or 0
    consumo = b.get("consumo_totale") or (f1+f2+f3+f23)
    iva     = IVA.get(profilo, 0.22)
    offerte = conn.execute(
        "SELECT * FROM offerte_luce WHERE attiva=1 AND (profili_compatibili LIKE ? OR profili_compatibili LIKE ? OR profili_compatibili LIKE ? OR profili_compatibili=?)",
        (f"%{profilo}%",f"{profilo},%",f"%,{profilo}",profilo)
    ).fetchall()
    res = []
    for o in offerte:
        of = dict(o)
        sconto_bf = (of.get("sconto_bifuel_perc") or 0) / 100 if bifuel else 0
        ce, costo_p = _costo_luce(of, f1,f2,f3,f23, consumo, mesi, pun, iva)
        costo_p *= (1 - sconto_bf)
        costo_a  = costo_p * fatt
        risp     = costo_att_annuo - costo_a
        pm_kwh   = ce/consumo if consumo else 0
        res.append({
            "offerta_id": of["id"], "fornitore": of["fornitore"],
            "nome_offerta": of["nome_offerta"], "tipo": of["tipo"],
            "profili_compatibili": of.get("profili_compatibili",""),
            "prezzo_medio_kwh": round(pm_kwh,4),
            "prezzo_f1": of.get("prezzo_f1"), "prezzo_f2": of.get("prezzo_f2"),
            "prezzo_f3": of.get("prezzo_f3"), "prezzo_f23": of.get("prezzo_f23"),
            "spread_pun": of.get("spread_pun"),
            "quota_fissa_annua": of.get("quota_fissa_annua"),
            "sconto_bifuel_perc": of.get("sconto_bifuel_perc",0),
            "bifuel_applicato": bifuel,
            "costo_stimato_periodo": round(costo_p,2),
            "costo_stimato_annuo": round(costo_a,2),
            "risparmio_annuo_vs_attuale": round(risp,2),
            "percentuale_risparmio": round(risp/costo_att_annuo*100,1) if costo_att_annuo>0 else 0,
            "note": of.get("note"), "valida_fino": of.get("valida_fino"),
            "url_offerta": of.get("url_offerta"), "mercato": of.get("mercato")
        })
    return res

def _compara_gas(conn, b, dati, mesi, fatt, costo_att_annuo, profilo, psv, bifuel) -> list:
    consumo_smc = b.get("consumo_totale") or 0
    iva         = IVA.get(profilo, 0.22)
    offerte = conn.execute(
        "SELECT * FROM offerte_gas WHERE attiva=1 AND (profili_compatibili LIKE ? OR profili_compatibili LIKE ? OR profili_compatibili LIKE ? OR profili_compatibili=?)",
        (f"%{profilo}%",f"{profilo},%",f"%,{profilo}",profilo)
    ).fetchall()
    res = []
    for o in offerte:
        of = dict(o)
        sconto_bf = (of.get("sconto_bifuel_perc") or 0)/100 if bifuel else 0
        if of.get("tipo")=="VARIABILE" and of.get("spread_psv"):
            p_smc = psv + of["spread_psv"]
        else:
            p_smc = of.get("prezzo_smc") or 0

        ce    = consumo_smc * p_smc
        qv    = consumo_smc * (of.get("quota_variabile_smc") or 0)
        qf    = (of.get("quota_fissa_annua") or 0)/12 * mesi
        sub   = ce + qv + qf
        iva_e = sub * iva
        costo_p = (sub + iva_e) * (1 - sconto_bf)
        costo_a = costo_p * fatt
        risp    = costo_att_annuo - costo_a

        res.append({
            "offerta_id": of["id"], "fornitore": of["fornitore"],
            "nome_offerta": of["nome_offerta"], "tipo": of["tipo"],
            "profili_compatibili": of.get("profili_compatibili",""),
            "uso_gas": of.get("uso_gas",""),
            "prezzo_smc": of.get("prezzo_smc"), "spread_psv": of.get("spread_psv"),
            "quota_fissa_annua": of.get("quota_fissa_annua"),
            "sconto_bifuel_perc": of.get("sconto_bifuel_perc",0),
            "bifuel_applicato": bifuel,
            "costo_stimato_periodo": round(costo_p,2),
            "costo_stimato_annuo": round(costo_a,2),
            "risparmio_annuo_vs_attuale": round(risp,2),
            "percentuale_risparmio": round(risp/costo_att_annuo*100,1) if costo_att_annuo>0 else 0,
            "note": of.get("note"), "valida_fino": of.get("valida_fino"),
            "url_offerta": of.get("url_offerta"), "mercato": of.get("mercato")
        })
    return res

# ═══════════════════════════════════════════════════════════════════════════════
# OFFERTE — CRUD + caricamento AI da PDF/URL/file
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/api/offerte/luce")
async def get_offerte_luce(profilo: Optional[str]=None):
    conn = get_db()
    q = "SELECT * FROM offerte_luce WHERE attiva=1"
    p = []
    if profilo:
        q += " AND (profili_compatibili LIKE ? OR profili_compatibili LIKE ? OR profili_compatibili LIKE ? OR profili_compatibili=?)"
        p.extend([f"%{profilo}%",f"{profilo},%",f"%,{profilo}",profilo])
    q += " ORDER BY fornitore"
    rows = conn.execute(q,p).fetchall(); conn.close()
    return [dict(r) for r in rows]

@app.get("/api/offerte/gas")
async def get_offerte_gas(profilo: Optional[str]=None):
    conn = get_db()
    q = "SELECT * FROM offerte_gas WHERE attiva=1"
    p = []
    if profilo:
        q += " AND (profili_compatibili LIKE ? OR profili_compatibili LIKE ? OR profili_compatibili LIKE ? OR profili_compatibili=?)"
        p.extend([f"%{profilo}%",f"{profilo},%",f"%,{profilo}",profilo])
    q += " ORDER BY fornitore"
    rows = conn.execute(q,p).fetchall(); conn.close()
    return [dict(r) for r in rows]

@app.post("/api/offerte/estrai-da-pdf")
async def estrai_offerta_da_pdf(file: UploadFile = File(...)):
    """Carica PDF di un'offerta commerciale e ne estrae i dati con AI."""
    raw = await file.read()
    if len(raw) > 10*1024*1024: raise HTTPException(400,"File troppo grande")
    from google.genai import types
    client = _get_gemini_client()
    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[PROMPT_OFFERTA, types.Part.from_bytes(data=raw, mime_type="application/pdf")],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        dati = _parse_json_response(resp.text)
        return {"estratto": True, "dati": dati, "fonte": "pdf", "nome_file": file.filename}
    except Exception as e:
        raise HTTPException(500, f"Errore AI: {e}")

@app.post("/api/offerte/estrai-da-url")
async def estrai_offerta_da_url(url: str = Body(..., embed=True)):
    """Scarica una pagina web di offerta e tenta l'estrazione AI."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                      headers={"User-Agent":"Mozilla/5.0"}) as c:
            r = await c.get(url)
            html = r.text
    except Exception as e:
        raise HTTPException(400, f"Impossibile scaricare l'URL: {e}")

    # Pulizia HTML basilare
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()[:8000]  # max 8000 char per Gemini

    client = _get_gemini_client()
    try:
        prompt_url = PROMPT_OFFERTA + f"\n\nContenuto pagina web:\n{text}"
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt_url],
            # config omesso: risposta testuale per URL (HTML già pulito)
        )
        dati = _parse_json_response(resp.text)
        return {"estratto": True, "dati": dati, "fonte": "url", "url": url}
    except Exception as e:
        raise HTTPException(500, f"Errore AI: {e}")

@app.post("/api/offerte/luce")
async def crea_offerta_luce(offerta: dict = Body(...)):
    if not offerta.get("fornitore") or not offerta.get("nome_offerta"):
        raise HTTPException(400,"fornitore e nome_offerta obbligatori")
    oid = offerta.get("id") or str(uuid.uuid4())
    conn = get_db()
    conn.execute("""
        INSERT INTO offerte_luce (id,fornitore,nome_offerta,tipo,profili_compatibili,
            prezzo_f1,prezzo_f2,prezzo_f3,prezzo_f23,prezzo_monorario,spread_pun,
            quota_fissa_annua,oneri_trasporto_stima,sconto_bifuel_perc,
            valida_fino,note,mercato,url_offerta,attiva,data_inserimento)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)
    """, (oid, offerta["fornitore"], offerta["nome_offerta"],
          offerta.get("tipo","FISSO"), offerta.get("profili_compatibili","D2,D3,BTA,CDO"),
          offerta.get("prezzo_f1"), offerta.get("prezzo_f2"),
          offerta.get("prezzo_f3"), offerta.get("prezzo_f23"),
          offerta.get("prezzo_monorario"), offerta.get("spread_pun"),
          offerta.get("quota_fissa_annua",0), offerta.get("oneri_trasporto_stima",0),
          offerta.get("sconto_bifuel_perc",0), offerta.get("valida_fino"),
          offerta.get("note"), offerta.get("mercato","Libero"),
          offerta.get("url_offerta"), datetime.now().isoformat()))
    conn.commit(); conn.close()
    return {"id": oid, "created": True}

@app.post("/api/offerte/gas")
async def crea_offerta_gas(offerta: dict = Body(...)):
    if not offerta.get("fornitore") or not offerta.get("nome_offerta"):
        raise HTTPException(400,"fornitore e nome_offerta obbligatori")
    oid = offerta.get("id") or str(uuid.uuid4())
    conn = get_db()
    conn.execute("""
        INSERT INTO offerte_gas (id,fornitore,nome_offerta,tipo,profili_compatibili,
            uso_gas,prezzo_smc,spread_psv,quota_fissa_annua,quota_variabile_smc,
            sconto_bifuel_perc,valida_fino,note,mercato,url_offerta,attiva,data_inserimento)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)
    """, (oid, offerta["fornitore"], offerta["nome_offerta"],
          offerta.get("tipo","FISSO"), offerta.get("profili_compatibili","D2,D3,BTA"),
          offerta.get("uso_gas","CACR"),
          offerta.get("prezzo_smc"), offerta.get("spread_psv"),
          offerta.get("quota_fissa_annua",0), offerta.get("quota_variabile_smc",0),
          offerta.get("sconto_bifuel_perc",0), offerta.get("valida_fino"),
          offerta.get("note"), offerta.get("mercato","Libero"),
          offerta.get("url_offerta"), datetime.now().isoformat()))
    conn.commit(); conn.close()
    return {"id": oid, "created": True}

@app.delete("/api/offerte/luce/{oid}")
async def del_offerta_luce(oid: str):
    conn = get_db()
    conn.execute("UPDATE offerte_luce SET attiva=0 WHERE id=?", (oid,))
    conn.commit(); conn.close()
    return {"deactivated": True}

@app.delete("/api/offerte/gas/{oid}")
async def del_offerta_gas(oid: str):
    conn = get_db()
    conn.execute("UPDATE offerte_gas SET attiva=0 WHERE id=?", (oid,))
    conn.commit(); conn.close()
    return {"deactivated": True}

# ═══════════════════════════════════════════════════════════════════════════════
# INDICI PUN / PSV — aggiornamento dal Portale Offerte open data
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/api/indici")
async def get_indici():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM indici_mercato ORDER BY tipo, periodo DESC"
    ).fetchall(); conn.close()
    data = {}
    for r in rows:
        t = r["tipo"]
        data.setdefault(t, []).append(dict(r))
    return data

@app.post("/api/indici/aggiorna")
async def aggiorna_indici(background_tasks: BackgroundTasks):
    """
    Aggiorna PUN e PSV dal Portale Offerte ARERA (ilportaleofferte.it open data).
    L'operazione è asincrona — risposta immediata, aggiornamento in background.
    """
    background_tasks.add_task(_fetch_indici_portale_offerte)
    return {"message": "Aggiornamento avviato in background. Ricarica tra 30 secondi."}

@app.post("/api/indici/manuale")
async def indice_manuale(payload: dict = Body(...)):
    """Inserisce manualmente un valore PUN o PSV."""
    tipo   = payload.get("tipo","").upper()
    periodo = payload.get("periodo","")
    valore  = payload.get("valore")
    if tipo not in ("PUN","PSV") or not periodo or valore is None:
        raise HTTPException(400,"Richiesti: tipo (PUN|PSV), periodo (YYYY-MM), valore")
    iid = f"{tipo.lower()}-{periodo}"
    conn = get_db()
    conn.execute("""
        INSERT OR REPLACE INTO indici_mercato (id,tipo,periodo,valore,fonte,aggiornato)
        VALUES (?,?,?,?,'Manuale',?)
    """, (iid, tipo, periodo, float(valore), datetime.now().isoformat()))
    conn.commit(); conn.close()
    return {"updated": True, "id": iid}

async def _fetch_indici_portale_offerte():
    """
    Strategia a 3 livelli per aggiornare PUN e PSV:
    1. Tenta scraping pagina GME (pubblica, no auth) per estrarre valore corrente
    2. Fallback: tenta Portale Offerte ARERA open data
    3. Fallback finale: logga istruzione manuale
    I valori sono in €/MWh sul GME — li convertiamo in €/kWh (divide 1000).
    """
    now = datetime.now()
    count = 0

    # ── Livello 1: Scraping GME "Prezzo medio per fasce" ───────────────────────
    # Il GME pubblica PDF mensili con URL a pattern fisso:
    # https://gme.mercatoelettrico.org/Portals/0/Documents/it-IT/
    #   YYYYMMDD PrezzomedioperfasceNomeMese YYYY.pdf
    # La pagina indice è navigabile e mostra i link agli ultimi PDF.
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                      headers={"User-Agent": "Mozilla/5.0 (compatible; BollettaAI/3.0)"}) as c:
            r = await c.get("https://gme.mercatoelettrico.org/it-it/Home/Pubblicazioni/PrezzoMedioFasce")
            html = r.text

        # Estrai URL PDF più recente dalla pagina
        pdf_urls = re.findall(r'/Portals/0/Documents/it-IT/(\d{8}PrezzomedioperfasceGennaio\d{4}\.pdf|'
                              r'\d{8}PrezzomedioperfasceFebbraio\d{4}\.pdf|'
                              r'\d{8}PrezzomedioperfasceMarzo\d{4}\.pdf|'
                              r'\d{8}PrezzomedioperfasceAprile\d{4}\.pdf|'
                              r'\d{8}PrezzomedioperfasceMaggio\d{4}\.pdf|'
                              r'\d{8}PrezzomedioperfasceGiugno\d{4}\.pdf|'
                              r'\d{8}PrezzomedioperfasseLuglio\d{4}\.pdf|'
                              r'\d{8}PrezzomedioperfasceAgosto\d{4}\.pdf|'
                              r'\d{8}PrezzomedioperfasceSettembre\d{4}\.pdf|'
                              r'\d{8}PrezzomedioperfasceOttobre\d{4}\.pdf|'
                              r'\d{8}PrezzomedioperfasceNovembre\d{4}\.pdf|'
                              r'\d{8}PrezzomedioperfasceDicembre\d{4}\.pdf)', html, re.IGNORECASE)

        # Alternativa più generica
        if not pdf_urls:
            pdf_matches = re.findall(r'/Portals/0/Documents/it-IT/(\d{8}Prezzomedio[^"\']+\.pdf)', html, re.IGNORECASE)
            pdf_urls = pdf_matches

        if pdf_urls:
            pdf_filename = sorted(set(pdf_urls))[-1]  # più recente per nome file
            pdf_url = f"https://gme.mercatoelettrico.org/Portals/0/Documents/it-IT/{pdf_filename}"

            # Scarica il PDF e usalo con Gemini per estrarne il PUN medio mensile
            pdf_r = await c.get(pdf_url)
            if pdf_r.status_code == 200 and len(pdf_r.content) > 1000:
                api_key = os.environ.get("GEMINI_API_KEY","")
                if api_key:
                    from google import genai as _genai
                    from google.genai import types as _types
                    _client = _genai.Client(api_key=api_key)
                    prompt_pun = (
                        "Questo è il report mensile GME 'Prezzo medio per fasce'. "
                        "Estrai il PUN medio mensile (prezzo baseload o PUN Index medio) espresso in €/MWh. "
                        "Restituisci SOLO JSON: {\"periodo\": \"YYYY-MM\", \"pun_eur_mwh\": 0.0, \"mese_anno\": \"Mese YYYY\"}"
                    )
                    resp = _client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=[prompt_pun, _types.Part.from_bytes(data=pdf_r.content, mime_type="application/pdf")],
                    )
                    extracted = _parse_json_response(resp.text)
                    periodo = extracted.get("periodo") or now.strftime("%Y-%m")
                    pun_mwh = float(extracted.get("pun_eur_mwh") or 0)
                    if pun_mwh > 0:
                        pun_kwh = round(pun_mwh / 1000, 6)  # converti €/MWh → €/kWh
                        conn = get_db()
                        conn.execute("""
                            INSERT OR REPLACE INTO indici_mercato (id,tipo,periodo,valore,fonte,aggiornato)
                            VALUES (?,?,?,?,'GME Prezzo medio per fasce',?)
                        """, (f"pun-{periodo}", "PUN", periodo, pun_kwh, now.isoformat()))
                        conn.commit(); conn.close()
                        count += 1
                        logger.info(f"PUN {periodo}: {pun_kwh} €/kWh (da PDF GME)")
    except Exception as e:
        logger.warning(f"GME PDF scraping fallito: {e}")

    # ── Livello 2: Portale Offerte ARERA (fallback) ────────────────────────────
    if count == 0:
        try:
            url = "https://www.ilportaleofferte.it/portaleOfferte/rest/prezziStoriciIndici"
            async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                          headers={"User-Agent": "Mozilla/5.0"}) as c:
                r = await c.get(url)
                if r.status_code == 200:
                    data = r.json()
                    conn = get_db()
                    for entry in data:
                        tipo_raw = entry.get("codiceIndice","").upper()
                        mese     = entry.get("meseAnno","")
                        valore   = entry.get("prezzoMedio")
                        if not tipo_raw or not mese or valore is None:
                            continue
                        tipo_db = "PUN" if "PUN" in tipo_raw else ("PSV" if "PSV" in tipo_raw else None)
                        if not tipo_db:
                            continue
                        parts = mese.split("/")
                        if len(parts) != 2:
                            continue
                        periodo = f"{parts[1]}-{parts[0].zfill(2)}"
                        # Portale Offerte dà valori in c€/kWh — convertiamo in €/kWh
                        v_kwh = float(valore) / 100 if float(valore) > 1 else float(valore)
                        iid = f"{tipo_db.lower()}-{periodo}"
                        conn.execute("""
                            INSERT OR REPLACE INTO indici_mercato (id,tipo,periodo,valore,fonte,aggiornato)
                            VALUES (?,?,?,?,'Portale Offerte ARERA',?)
                        """, (iid, tipo_db, periodo, v_kwh, now.isoformat()))
                        count += 1
                    conn.commit(); conn.close()
                    logger.info(f"Portale Offerte: aggiornati {count} indici")
        except Exception as e2:
            logger.warning(f"Portale Offerte fallito: {e2}")

    # ── Livello 3: fallback finale ─────────────────────────────────────────────
    if count == 0:
        logger.warning(
            "Aggiornamento automatico non riuscito. "
            "Inserisci manualmente il PUN su: POST /api/indici/manuale "
            "oppure usa il pulsante '+ Inserisci' nella sezione PUN/PSV. "
            "Fonte: https://gme.mercatoelettrico.org/it-it/Home/Pubblicazioni/PrezzoMedioFasce"
        )
    else:
        logger.info(f"Aggiornamento indici completato: {count} voci")


# ═══════════════════════════════════════════════════════════════════════════════
# STATISTICHE & EXPORT
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/api/statistiche")
async def statistiche():
    conn = get_db()
    sl = dict(conn.execute("SELECT COUNT(*) n,AVG(totale_fattura) avg_f,SUM(consumo_totale) tot_c,AVG(costo_unitario_eff) avg_kwh FROM bollette WHERE tipo_utenza='luce'").fetchone())
    sg = dict(conn.execute("SELECT COUNT(*) n,AVG(totale_fattura) avg_f,SUM(consumo_totale) tot_c,AVG(costo_unitario_eff) avg_smc FROM bollette WHERE tipo_utenza='gas'").fetchone())
    trend = [dict(r) for r in conn.execute("SELECT strftime('%Y-%m',data_caricamento) mese,tipo_utenza,COUNT(*) n,SUM(totale_fattura) tot FROM bollette GROUP BY mese,tipo_utenza ORDER BY mese DESC LIMIT 24").fetchall()]
    per_profilo = [dict(r) for r in conn.execute("SELECT profilo_utenza,tipo_utenza,COUNT(*) n,AVG(totale_fattura) avg_f FROM bollette GROUP BY profilo_utenza,tipo_utenza").fetchall()]
    risp = conn.execute("SELECT SUM(json_extract(risultati_json,'$[0].risparmio_annuo_vs_attuale')) tot FROM comparazioni WHERE json_extract(risultati_json,'$[0].risparmio_annuo_vs_attuale')>0").fetchone()
    pun_last = [dict(r) for r in conn.execute("SELECT periodo,valore FROM indici_mercato WHERE tipo='PUN' ORDER BY periodo DESC LIMIT 6").fetchall()]
    psv_last = [dict(r) for r in conn.execute("SELECT periodo,valore FROM indici_mercato WHERE tipo='PSV' ORDER BY periodo DESC LIMIT 6").fetchall()]
    conn.close()
    return {
        "luce": sl, "gas": sg, "trend_mensile": trend,
        "per_profilo": per_profilo,
        "risparmio_totale_identificato": risp["tot"] or 0,
        "pun_ultimi_mesi": pun_last, "psv_ultimi_mesi": psv_last,
        "profili": PROFILI_LABEL
    }

@app.get("/api/export/csv")
async def export_csv(tipo: Optional[str]=None, profilo: Optional[str]=None):
    conn = get_db()
    q = "SELECT * FROM bollette WHERE 1=1"
    p = []
    if tipo:    q += " AND tipo_utenza=?";    p.append(tipo)
    if profilo: q += " AND profilo_utenza=?"; p.append(profilo)
    q += " ORDER BY data_caricamento DESC"
    rows = conn.execute(q,p).fetchall(); conn.close()
    lines = ["id,tipo,profilo,fornitore,periodo_inizio,periodo_fine,totale_eur,consumo,unita,costo_unitario,mercato,pod_pdr"]
    for r in rows:
        d = dict(r)
        lines.append(",".join([str(d.get(k,"") or "") for k in
            ("id","tipo_utenza","profilo_utenza","fornitore","periodo_inizio","periodo_fine",
             "totale_fattura","consumo_totale","unita_misura","costo_unitario_eff","mercato","pod_pdr")]))
    return StreamingResponse(
        io.BytesIO("\n".join(lines).encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition":f"attachment; filename=bollette_{datetime.now().strftime('%Y%m%d')}.csv"}
    )
