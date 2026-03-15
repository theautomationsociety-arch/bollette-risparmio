"""
Bollette Risparmio — Backend Pubblico + Admin
Sito comparatore bollette Luce & Gas — struttura ispirata ad AIChange.it
"""

import os, json, uuid, logging, io, re, httpx, time, collections, html as _html, csv, asyncio
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager, contextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, Body, Request, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
import sqlite3
from google import genai as _genai
from google.genai import types as _types
try:
    import resend as _resend
    _RESEND_OK = True
except ImportError:
    _RESEND_OK = False
from backend.email_utils import (
    build_risultati, build_consulente_utente, build_consulente_admin,
    build_ricontatto_admin, send_email as _send_email
)
import backend.guide_pages as _gp
import backend.arera_scraper as _arera

# ── Paths ──────────────────────────────────────────────────────────────────
BASE       = Path(__file__).parent.parent
FRONTEND   = BASE / "frontend"
DB_PATH    = BASE / "data" / "db.sqlite"
LOG_PATH   = BASE / "data" / "app.log"
LOG_PATH.parent.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(str(LOG_PATH)), logging.StreamHandler()])
log = logging.getLogger(__name__)

# ── Costanti fiscali italiane 2025 ─────────────────────────────────────────
IVA = {"D2": 0.10, "D3": 0.10, "BTA": 0.22, "CDO": 0.10}
PROFILI = {
    "D2":  "Domestico Residente",
    "D3":  "Domestico Non Residente",
    "BTA": "PMI / Non Domestico",
    "CDO": "Condominio",
}
ADMIN_TOKEN  = os.environ.get("ADMIN_TOKEN", "admin123")
RESEND_KEY   = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL   = os.environ.get("FROM_EMAIL", "Bollette Risparmio <onboarding@resend.dev>")
ADMIN_EMAIL  = os.environ.get("ADMIN_EMAIL", "")
SITE_URL     = os.environ.get("SITE_URL", "https://www.bolletterisparmio.it")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ── Rate limiting (in-memory, per IP) ────────────────────────────────────
# Finestra scorrevole: max RATE_LIMIT_MAX richieste per IP in RATE_LIMIT_WINDOW secondi
RATE_LIMIT_WINDOW = int(os.environ.get("RATE_LIMIT_WINDOW", "3600"))  # 1 ora
RATE_LIMIT_MAX    = int(os.environ.get("RATE_LIMIT_MAX", "10"))        # 10 analisi/ora
_rate_store: dict[str, collections.deque] = {}

def _check_rate_limit(ip: str) -> None:
    """Solleva 429 se l'IP ha superato il limite di richieste."""
    now = time.time()
    if ip not in _rate_store:
        _rate_store[ip] = collections.deque()
    q = _rate_store[ip]
    # Rimuovi timestamp scaduti
    while q and now - q[0] > RATE_LIMIT_WINDOW:
        q.popleft()
    if len(q) >= RATE_LIMIT_MAX:
        retry_after = int(RATE_LIMIT_WINDOW - (now - q[0])) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Troppe richieste. Riprova tra {retry_after} secondi.",
            headers={"Retry-After": str(retry_after)},
        )
    q.append(now)

# ── Background task: ARERA daily sync ──────────────────────────────────────
async def _daily_arera_sync():
    """Loop infinito: sincronizza le offerte ARERA ogni 24 ore."""
    # Attesa iniziale breve per dare tempo all'app di avviarsi
    await asyncio.sleep(10)
    while True:
        try:
            with db() as conn:
                result = await _arera.run_sync(conn)
            log.info(f"ARERA daily sync: {result}")
        except Exception as e:
            log.error(f"ARERA daily sync fallita: {e}")
        await asyncio.sleep(24 * 3600)

# ── Lifespan ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Avvisa se ADMIN_TOKEN è il valore di default non sicuro
    _weak_tokens = {"admin123", "admin", "password", "secret", "test", ""}
    if ADMIN_TOKEN in _weak_tokens or len(ADMIN_TOKEN) < 16:
        log.warning(
            "⚠️  ADMIN_TOKEN debole o di default! Imposta una variabile d'ambiente "
            "ADMIN_TOKEN con almeno 16 caratteri casuali prima del deploy."
        )
    if not GEMINI_API_KEY:
        log.warning("⚠️  GEMINI_API_KEY non configurata: le analisi AI non funzioneranno.")
    log.info("Bollette Risparmio avviato")
    _arera_task = asyncio.create_task(_daily_arera_sync())
    try:
        yield
    finally:
        _arera_task.cancel()
        try:
            await _arera_task
        except asyncio.CancelledError:
            pass

app = FastAPI(title="Bollette Risparmio", version="1.0.0", lifespan=lifespan)
_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS","*").split(",")]
app.add_middleware(CORSMiddleware,
    allow_origins=_ORIGINS,
    allow_methods=["GET","POST","PATCH","DELETE"],
    allow_headers=["Authorization","Content-Type"])

if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")

# ── Auth admin ─────────────────────────────────────────────────────────────
def require_admin(request: Request):
    token = request.headers.get("Authorization","").replace("Bearer ","")
    if token != ADMIN_TOKEN:
        raise HTTPException(401, "Non autorizzato")

# ── DB ─────────────────────────────────────────────────────────────────────
def get_db():
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    c = get_db()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS bollette (
            id TEXT PRIMARY KEY,
            tipo TEXT DEFAULT 'luce',
            profilo TEXT DEFAULT 'D2',
            nome_file TEXT, data_upload TEXT,
            fornitore TEXT, num_fattura TEXT,
            periodo_inizio TEXT, periodo_fine TEXT, scadenza TEXT,
            totale REAL, mercato TEXT, pod_pdr TEXT,
            potenza REAL, consumo REAL, unita TEXT DEFAULT 'kWh',
            spesa_energia REAL, spesa_trasporto REAL,
            oneri REAL, iva REAL,
            dati_json TEXT, costo_unit REAL,
            lead_id TEXT,
            potenza_disponibile REAL,
            zona_climatica TEXT,
            bonus_sociale REAL,
            confidence_score INTEGER,
            prezzo_medio REAL
        );

        CREATE TABLE IF NOT EXISTS offerte_luce (
            id TEXT PRIMARY KEY,
            fornitore TEXT, nome TEXT,
            tipo TEXT DEFAULT 'FISSO',
            profili TEXT DEFAULT 'D2,D3,BTA,CDO',
            prezzo_f1 REAL, prezzo_f2 REAL, prezzo_f3 REAL,
            prezzo_f23 REAL, prezzo_mono REAL, spread_pun REAL,
            quota_fissa REAL DEFAULT 0,
            oneri_trasp REAL DEFAULT 0,
            sconto_bifuel REAL DEFAULT 0,
            valida_fino TEXT, note TEXT, mercato TEXT DEFAULT 'Libero',
            url TEXT, attiva INTEGER DEFAULT 1, inserita TEXT,
            fonte TEXT DEFAULT 'manuale',
            cod_offerta TEXT,
            piva_fornitore TEXT,
            descrizione TEXT,
            durata INTEGER,
            garanzie TEXT,
            telefono TEXT,
            modalita_attivazione TEXT,
            metodi_pagamento TEXT,
            data_inizio TEXT,
            zone TEXT,
            domestico_residente TEXT,
            offerta_congiunta_ee TEXT,
            offerta_congiunta_gas TEXT,
            condizioni TEXT,
            sconto_json TEXT
        );

        CREATE TABLE IF NOT EXISTS offerte_gas (
            id TEXT PRIMARY KEY,
            fornitore TEXT, nome TEXT,
            tipo TEXT DEFAULT 'FISSO',
            profili TEXT DEFAULT 'D2,D3,BTA',
            prezzo_smc REAL, spread_psv REAL,
            quota_fissa REAL DEFAULT 0,
            quota_var REAL DEFAULT 0,
            sconto_bifuel REAL DEFAULT 0,
            valida_fino TEXT, note TEXT, mercato TEXT DEFAULT 'Libero',
            url TEXT, attiva INTEGER DEFAULT 1, inserita TEXT,
            fonte TEXT DEFAULT 'manuale',
            cod_offerta TEXT,
            piva_fornitore TEXT,
            descrizione TEXT,
            durata INTEGER,
            garanzie TEXT,
            telefono TEXT,
            modalita_attivazione TEXT,
            metodi_pagamento TEXT,
            data_inizio TEXT,
            zone TEXT,
            domestico_residente TEXT,
            offerta_congiunta_ee TEXT,
            offerta_congiunta_gas TEXT,
            condizioni TEXT,
            sconto_json TEXT
        );

        CREATE TABLE IF NOT EXISTS offerte_dual (
            id TEXT PRIMARY KEY,
            fornitore TEXT, nome TEXT,
            tipo TEXT DEFAULT 'FISSO',
            profili TEXT DEFAULT 'D2,D3',
            cod_offerta TEXT,
            piva_fornitore TEXT,
            descrizione TEXT,
            durata INTEGER,
            garanzie TEXT,
            telefono TEXT,
            url TEXT,
            modalita_attivazione TEXT,
            metodi_pagamento TEXT,
            data_inizio TEXT,
            valida_fino TEXT,
            zone TEXT,
            domestico_residente TEXT,
            offerta_congiunta_ee TEXT,
            offerta_congiunta_gas TEXT,
            condizioni TEXT,
            sconto_json TEXT,
            prezzo_f1 REAL, prezzo_f2 REAL, prezzo_f3 REAL,
            prezzo_f23 REAL, prezzo_mono REAL, spread_pun REAL,
            quota_fissa_ee REAL DEFAULT 0,
            prezzo_smc REAL, spread_psv REAL,
            quota_fissa_gas REAL DEFAULT 0,
            quota_var_gas REAL DEFAULT 0,
            note TEXT, mercato TEXT DEFAULT 'Libero',
            attiva INTEGER DEFAULT 1, inserita TEXT,
            fonte TEXT DEFAULT 'arera'
        );

        CREATE TABLE IF NOT EXISTS parametri_regolatori (
            nome TEXT,
            tipo TEXT,
            valore REAL,
            descrizione TEXT,
            aggiornato TEXT,
            PRIMARY KEY (nome, tipo)
        );

        CREATE TABLE IF NOT EXISTS indici (
            id TEXT PRIMARY KEY,
            tipo TEXT, periodo TEXT,
            valore REAL, fonte TEXT, aggiornato TEXT
        );

        CREATE TABLE IF NOT EXISTS leads (
            id TEXT PRIMARY KEY,
            nome TEXT, cognome TEXT, email TEXT, telefono TEXT,
            tipo_richiesta TEXT DEFAULT 'analisi',
            bolletta_id TEXT,
            consenso_privacy INTEGER DEFAULT 0,
            consenso_marketing INTEGER DEFAULT 0,
            data TEXT,
            note TEXT,
            stato TEXT DEFAULT 'nuovo',
            fascia_oraria_preferita TEXT,
            offerta_richiesta TEXT
        );

        CREATE TABLE IF NOT EXISTS comparazioni (
            id TEXT PRIMARY KEY,
            bolletta_id TEXT, tipo TEXT, profilo TEXT,
            data TEXT, risultati_json TEXT, bifuel INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_b_tipo ON bollette(tipo);
        CREATE INDEX IF NOT EXISTS idx_l_email ON leads(email);
        CREATE INDEX IF NOT EXISTS idx_l_stato ON leads(stato);
        CREATE INDEX IF NOT EXISTS idx_i_tipo ON indici(tipo, periodo);
    """)
    c.commit()
    # Migrate existing DBs: add columns added after initial deploy
    for tbl, col, typedef in [
        ("leads",         "fascia_oraria_preferita", "TEXT"),
        ("leads",         "offerta_richiesta",        "TEXT"),
        ("bollette",      "potenza_disponibile",      "REAL"),
        ("bollette",      "zona_climatica",           "TEXT"),
        ("bollette",      "bonus_sociale",            "REAL"),
        ("bollette",      "confidence_score",         "INTEGER"),
        ("bollette",      "prezzo_medio",             "REAL"),
        ("offerte_luce",  "fonte",                   "TEXT DEFAULT 'manuale'"),
        ("offerte_gas",   "fonte",                   "TEXT DEFAULT 'manuale'"),
        # ── Nuove colonne dettaglio offerte (ARERA full parse) ──
        ("offerte_luce",  "cod_offerta",             "TEXT"),
        ("offerte_luce",  "piva_fornitore",          "TEXT"),
        ("offerte_luce",  "descrizione",             "TEXT"),
        ("offerte_luce",  "durata",                  "INTEGER"),
        ("offerte_luce",  "garanzie",                "TEXT"),
        ("offerte_luce",  "telefono",                "TEXT"),
        ("offerte_luce",  "modalita_attivazione",    "TEXT"),
        ("offerte_luce",  "metodi_pagamento",        "TEXT"),
        ("offerte_luce",  "data_inizio",             "TEXT"),
        ("offerte_luce",  "zone",                    "TEXT"),
        ("offerte_luce",  "domestico_residente",     "TEXT"),
        ("offerte_luce",  "offerta_congiunta_ee",    "TEXT"),
        ("offerte_luce",  "offerta_congiunta_gas",   "TEXT"),
        ("offerte_luce",  "condizioni",              "TEXT"),
        ("offerte_luce",  "sconto_json",             "TEXT"),
        ("offerte_gas",   "cod_offerta",             "TEXT"),
        ("offerte_gas",   "piva_fornitore",          "TEXT"),
        ("offerte_gas",   "descrizione",             "TEXT"),
        ("offerte_gas",   "durata",                  "INTEGER"),
        ("offerte_gas",   "garanzie",                "TEXT"),
        ("offerte_gas",   "telefono",                "TEXT"),
        ("offerte_gas",   "modalita_attivazione",    "TEXT"),
        ("offerte_gas",   "metodi_pagamento",        "TEXT"),
        ("offerte_gas",   "data_inizio",             "TEXT"),
        ("offerte_gas",   "zone",                    "TEXT"),
        ("offerte_gas",   "domestico_residente",     "TEXT"),
        ("offerte_gas",   "offerta_congiunta_ee",    "TEXT"),
        ("offerte_gas",   "offerta_congiunta_gas",   "TEXT"),
        ("offerte_gas",   "condizioni",              "TEXT"),
        ("offerte_gas",   "sconto_json",             "TEXT"),
    ]:
        try:
            c.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {typedef}")
            c.commit()
        except Exception:
            pass  # Column already exists
    if c.execute("SELECT COUNT(*) FROM indici").fetchone()[0] == 0:
        _seed_indici(c)
    c.close()

def _seed_indici(c):
    now = datetime.now().isoformat()
    rows = [
        ("pun-2026-02","PUN","2026-02",0.1298,"Portale Offerte ARERA",now),
        ("pun-2026-01","PUN","2026-01",0.1327,"Portale Offerte ARERA",now),
        ("pun-2025-12","PUN","2025-12",0.1155,"Portale Offerte ARERA",now),
        ("pun-2025-11","PUN","2025-11",0.1212,"Portale Offerte ARERA",now),
        ("pun-2025-10","PUN","2025-10",0.1110,"Portale Offerte ARERA",now),
        ("psv-2026-02","PSV","2026-02",0.3710,"Portale Offerte ARERA",now),
        ("psv-2026-01","PSV","2026-01",0.3820,"Portale Offerte ARERA",now),
        ("psv-2025-12","PSV","2025-12",0.3650,"Portale Offerte ARERA",now),
        ("psv-2025-11","PSV","2025-11",0.3580,"Portale Offerte ARERA",now),
    ]
    c.executemany("INSERT INTO indici (id,tipo,periodo,valore,fonte,aggiornato) VALUES (?,?,?,?,?,?)", rows)
    c.commit()

# ── Helpers ────────────────────────────────────────────────────────────────
_gemini_client: "_genai.Client | None" = None

def gemini() -> "_genai.Client":
    """Restituisce il client Gemini, creandolo una sola volta (singleton)."""
    global _gemini_client
    k = os.environ.get("GEMINI_API_KEY", "")
    if not k:
        raise HTTPException(500, "GEMINI_API_KEY non configurata")
    if _gemini_client is None:
        _gemini_client = _genai.Client(api_key=k)
    return _gemini_client

def parse_json(text):
    return json.loads(text.replace("```json","").replace("```","").strip())

def mesi(d1,d2):
    try: return max(1, round((date.fromisoformat(d2)-date.fromisoformat(d1)).days/30))
    except (ValueError, TypeError): return 1

def pun_last(c): r=c.execute("SELECT valore FROM indici WHERE tipo='PUN' ORDER BY periodo DESC LIMIT 1").fetchone(); return r["valore"] if r else 0.113
def psv_last(c): r=c.execute("SELECT valore FROM indici WHERE tipo='PSV' ORDER BY periodo DESC LIMIT 1").fetchone(); return r["valore"] if r else 0.382

# ── Parametri regolatori — costi regolati per stima spesa annua ─────────────
def _load_params(c, tipo: str) -> dict:
    """Carica parametri regolatori dal DB come dict {nome: valore}."""
    rows = c.execute(
        "SELECT nome, valore FROM parametri_regolatori WHERE tipo=?", (tipo,)
    ).fetchall()
    return {r["nome"]: r["valore"] for r in rows} if rows else {}

def _costi_regolati_luce(params: dict, consumo_annuo: float, profilo: str, potenza: float = 3.0) -> dict:
    """
    Calcola costi regolati annui per elettricità (trasporto, distribuzione,
    oneri di sistema, accise, misura, qualità, perequazione).

    Restituisce dict con 'variabile' (€/kWh), 'fisso' (€/anno), 'totale' (€/anno).
    Se i parametri non sono disponibili, restituisce zero.
    """
    if not params:
        return {"variabile": 0, "fisso": 0, "totale": 0}

    p = params.get
    is_res = profilo in ("D2", "CDO")

    # ── Componenti variabili (€/kWh) ──
    # Accise
    if is_res:
        accisa = p("acc_c_r_l", 0.0227)
    else:
        accisa = p("acc_c_nr", 0.0227)

    # Oneri di sistema
    if is_res:
        asos_v = p("asos_dr", 0)
        arim_v = p("arim_dr", 0)
    elif profilo == "D3":
        asos_v = p("asos_dnr_v", 0)
        arim_v = p("arim_dnr_v", 0)
    else:
        # BTA — usa BTA1 come default
        asos_v = p("asos_nd_b1_c", 0)
        arim_v = p("arim_nd_b1_c", 0)

    # Trasporto e distribuzione variabile
    tras = p("tras", 0)
    sigma3 = p("sigma3", 0)  # misura variabile
    dis_c = 0 if profilo in ("D2", "D3", "CDO") else p("dis_b1_c", 0)

    # Perequazione e qualità variabile
    uc3 = p("uc3", 0)
    uc6p = p("uc6p_d", 0) if profilo in ("D2", "D3", "CDO") else p("uc6p_nd", 0)

    # Dispacciamento variabile
    disp_var = p("cdispd", 0)

    var_per_kwh = accisa + asos_v + arim_v + tras + sigma3 + dis_c + uc3 + uc6p + disp_var

    # ── Componenti fisse (€/anno) ──
    sigma1 = p("sigma1", 0)   # distribuzione fissa
    sigma2 = p("sigma2", 0)   # trasporto fissa
    mis = p("mis", 0)         # misura fissa
    uc6s = p("uc6s_d", 0) if profilo in ("D2", "D3", "CDO") else p("uc6s_nd", 0)
    dispbt = p("dispbt_d", 0) if profilo in ("D2", "D3", "CDO") else p("dispbt_nd", 0)

    # Oneri fissi (non-residenti hanno componente fissa ASOS)
    asos_f = p("asos_dnr_f", 0) if profilo == "D3" else 0
    arim_f = p("arim_dnr_f", 0) if profilo == "D3" else 0

    # Distribuzione per potenza (BTA)
    if profilo == "BTA":
        dis_f = p("dis_b1_f", 0)
        dis_p = p("dis_b1_p", 0) * potenza
    else:
        dis_f = 0
        dis_p = 0

    fisso_annuo = sigma1 + sigma2 + mis + uc6s + dispbt + asos_f + arim_f + dis_f + dis_p

    totale = var_per_kwh * consumo_annuo + fisso_annuo
    return {"variabile": round(var_per_kwh, 6), "fisso": round(fisso_annuo, 2), "totale": round(totale, 2)}

def _costi_regolati_gas(params: dict, consumo_annuo_smc: float, profilo: str, zona: int = 3) -> dict:
    """
    Calcola costi regolati annui per gas (trasporto, distribuzione,
    oneri, misura).

    zona: 1=Nord-Occ, 2=Nord-Or, 3=Centrale, 4=Sud-Or, 5=Sud-Occ, 6=Meridionale
    """
    if not params:
        return {"variabile": 0, "fisso": 0, "totale": 0}

    p = params.get
    is_dom = profilo in ("D2", "D3", "CDO")
    a = str(zona)

    # ── Componenti variabili (€/Smc) ──
    qt = p("qt", 0)           # trasporto
    re = p("re", 0)           # risparmio energetico
    gs = p("gs", 0)           # bonus gas
    rs = p("rs", 0)           # qualità
    ug1 = p("ug1", 0)         # perequazione
    ug3 = p("ug3", 0)         # recupero morosità
    qvd_v = p("qvd_v_d", 0) if is_dom else p("qvd_v_nd", 0)
    cpr = p("cpr", 0)

    # TAU3 misura variabile — usa scaglione 2 (0-120 Smc tipico domestico)
    tau3 = p(f"tau3_f2_a{a}", 0)

    # UG2 — scaglione 2 (tipico)
    ug2_key = f"ug2p_{'d' if is_dom else 'nd'}_f2"
    ug2 = p(ug2_key, 0)

    var_per_smc = qt + re + gs + rs + ug1 + ug3 + qvd_v + cpr + tau3 + ug2

    # ── Componenti fisse (€/anno) ──
    tau1 = p(f"tau1_cc1_a{a}", 0)     # distribuzione fissa (contatore <G6, domestico)
    qvd_f = p("qvd_f_d", 0) if is_dom else p("qvd_f_nd", 0)

    # ST e VR
    st = p(f"st_a{a}", 0)
    vr = p(f"vr_a{a}", 0)

    # UG2 fisso
    ug2s = p("ug2s", 0)

    fisso_annuo = tau1 + qvd_f + st + vr + ug2s

    totale = var_per_smc * consumo_annuo_smc + fisso_annuo
    return {"variabile": round(var_per_smc, 6), "fisso": round(fisso_annuo, 2), "totale": round(totale, 2)}

def se(to, subj, html):
    """Shorthand send_email usando le variabili globali."""
    return _send_email(to, subj, html, RESEND_KEY, FROM_EMAIL)

@contextmanager
def db():
    """Context manager: garantisce chiusura connessione anche in caso di eccezione."""
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()

# ── Prompts ────────────────────────────────────────────────────────────────
P_LUCE = """
RUOLO: Sei un analista esperto di bollette elettriche italiane.
I dati che estrai verranno usati per calcolare il costo unitario
per fascia e confrontare l'offerta attuale con alternative di mercato.
La precisione sui consumi per fascia e sui costi e' FONDAMENTALE.

ISTRUZIONI:
- Analizza TUTTE le pagine del documento, non solo la prima.
- Se un valore non e' leggibile o non presente, usa null (MAI inventare).
- Se il valore e' esplicitamente zero nel documento, usa 0.0.
- Verifica che la somma dei costi parziali sia coerente col totale fattura.
- Per i consumi per fascia: se il documento riporta solo un consumo totale
  senza ripartizione F1/F2/F3, metti il totale in consumo_totale_periodo
  e lascia le fasce a null.
- Per il prezzo unitario: se la bolletta mostra un solo prezzo medio,
  compilalo in prezzo_medio_kwh e lascia i prezzi per fascia a null.

Restituisci SOLO un oggetto JSON con questa struttura esatta:
{
  "dati_generali": {
    "fornitore": null,
    "numero_fattura": null,
    "periodo_fatturazione": {"inizio": null, "fine": null},
    "scadenza": null,
    "totale_fattura": null,
    "mercato": null,
    "profilo_stimato": null
  },
  "dati_tecnici": {
    "pod_pdr": null,
    "potenza_impegnata": null,
    "potenza_disponibile": null,
    "tipologia_uso": null,
    "indirizzo_fornitura": null
  },
  "letture_e_consumi": {
    "consumo_totale_periodo": null,
    "prezzo_medio_kwh": null,
    "ripartizione_fasce": {
      "F1": {"consumo": null, "prezzo_unitario": null},
      "F2": {"consumo": null, "prezzo_unitario": null},
      "F3": {"consumo": null, "prezzo_unitario": null},
      "F23": {"consumo": null, "prezzo_unitario": null}
    },
    "lettura_stimata_o_reale": null
  },
  "dettaglio_costi": {
    "spesa_materia_energia": null,
    "trasporto_gestione_contatore": null,
    "oneri_sistema": null,
    "imposte_iva": null,
    "accise": null,
    "canone_rai": null,
    "altre_partite": null,
    "bonus_sociale": null
  },
  "analisi_ai": {
    "anomalie_rilevate": ["Sii SPECIFICO con numeri: es. Il costo F1 di X.XX euro/kWh supera la media di mercato (Y.YY euro/kWh) del Z%"],
    "suggerimenti": ["Suggerimenti CONCRETI e AZIONABILI con cifre stimate"],
    "fascia_consumo": null,
    "confidence_score": null,
    "campi_incerti": []
  }
}
Nota: anomalie_rilevate e suggerimenti devono essere array vuoti [] se non ci sono elementi da segnalare."""

P_GAS = """
RUOLO: Sei un analista esperto di bollette gas italiane.
I dati che estrai verranno usati per calcolare il costo unitario euro/Smc
e confrontare l'offerta attuale con alternative di mercato.
La precisione sul consumo in Smc e sul costo della materia prima
e' FONDAMENTALE per la comparazione.

ISTRUZIONI:
- Analizza TUTTE le pagine del documento, non solo la prima.
- Se un valore non e' leggibile o non presente, usa null (MAI inventare).
- Se il valore e' esplicitamente zero nel documento, usa 0.0.
- Verifica coerenza: somma costi parziali deve approssimare il totale fattura.
- Il consumo deve essere in Smc (Standard metri cubi). Se la bolletta
  riporta mc, usa il coefficiente di conversione per convertire in Smc.
- ATTENZIONE: consumo_totale_smc e' il dato PIU' CRITICO di tutta
  l'analisi. Verifica che sia coerente col periodo di fatturazione.

Restituisci SOLO un oggetto JSON con questa struttura esatta:
{
  "dati_generali": {
    "fornitore": null,
    "numero_fattura": null,
    "periodo_fatturazione": {"inizio": null, "fine": null},
    "scadenza": null,
    "totale_fattura": null,
    "mercato": null,
    "profilo_stimato": null
  },
  "dati_tecnici": {
    "pdr": null,
    "tipologia_uso": null,
    "indirizzo_fornitura": null,
    "coefficiente_conversione": null,
    "zona_climatica": null
  },
  "letture_e_consumi": {
    "consumo_totale_smc": null,
    "consumo_totale_kwh": null,
    "prezzo_medio_smc": null,
    "lettura_stimata_o_reale": null
  },
  "dettaglio_costi": {
    "spesa_materia_gas": null,
    "trasporto_distribuzione": null,
    "oneri_sistema": null,
    "imposte_iva": null,
    "accise": null,
    "addizionale_regionale": null,
    "altre_partite": null,
    "bonus_sociale": null
  },
  "analisi_ai": {
    "anomalie_rilevate": ["Sii SPECIFICO: es. Il prezzo medio di X.XX euro/Smc e' superiore all'indice PSV corrente di Y.YY euro/Smc del Z%"],
    "suggerimenti": ["Suggerimenti CONCRETI e AZIONABILI con risparmio stimato"],
    "fascia_consumo": null,
    "confidence_score": null,
    "campi_incerti": []
  }
}
Nota: anomalie_rilevate e suggerimenti devono essere array vuoti [] se non ci sono elementi da segnalare."""

P_OFFERTA = """
RUOLO: Sei un analista esperto del mercato energetico italiano.
Stai estraendo i dati di un'offerta commerciale (CTE) per inserirli
in un database di confronto tariffe. I prezzi che estrai verranno
usati per calcolare il costo annuo e il risparmio per i clienti.
La precisione dei prezzi unitari e' FONDAMENTALE.

ISTRUZIONI:
- Estrai TUTTI i dati disponibili nel documento.
- I prezzi devono essere in euro/kWh (luce) o euro/Smc (gas), NETTI,
  riferiti alla sola componente energia/materia prima.
  Se il documento riporta prezzi LORDI (IVA inclusa), convertili a netti.
  Se non sei sicuro, estrai il valore e segnalalo nelle note.
- La quota_fissa deve essere ANNUALE in euro/anno.
  Se il documento la indica mensile, moltiplica per 12.
- Se un valore non e' presente, usa null (MAI inventare).
- Per offerte che combinano componente fissa + spread su PUN/PSV,
  usa tipo_prezzo: 'MISTO' e compila sia i prezzi fissi che lo spread.

Restituisci SOLO un oggetto JSON con questa struttura:
{
  "tipo_utenza": null,
  "fornitore": null,
  "nome_offerta": null,
  "tipo_prezzo": null,
  "profili_compatibili": null,
  "prezzo_f1_eur_kwh": null,
  "prezzo_f2_eur_kwh": null,
  "prezzo_f3_eur_kwh": null,
  "prezzo_f23_eur_kwh": null,
  "prezzo_mono_eur_kwh": null,
  "spread_pun": null,
  "oneri_trasporto_eur_kwh": null,
  "prezzo_smc": null,
  "spread_psv": null,
  "quota_variabile_smc": null,
  "quota_fissa_annua_eur": null,
  "sconto_bifuel_percentuale": null,
  "valida_fino": null,
  "durata_contratto_mesi": null,
  "mercato": null,
  "note": null,
  "prezzi_lordi_o_netti": null
}
Valori attesi: tipo_utenza in ['luce','gas'], tipo_prezzo in ['FISSO','VARIABILE','MISTO'], mercato in ['Libero','Tutelato']."""

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — Pagine
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/favicon.svg", include_in_schema=False)
async def favicon(): return FileResponse(str(FRONTEND/"favicon.svg"), media_type="image/svg+xml")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico(): return FileResponse(str(FRONTEND/"favicon.svg"), media_type="image/svg+xml")

@app.get("/", include_in_schema=False)
async def root(): return FileResponse(str(FRONTEND/"index.html"))

@app.get("/admin", include_in_schema=False)
async def admin_page(): return FileResponse(str(FRONTEND/"admin.html"))

@app.get("/api/health")
async def health():
    with db() as c:
        n = {t: c.execute("SELECT COUNT(*) FROM bollette WHERE tipo=?", (t,)).fetchone()[0] for t in ("luce", "gas")}
        pun = pun_last(c)
    return {"ok": True, "bollette": n, "pun": pun, "gemini": bool(os.environ.get("GEMINI_API_KEY"))}

@app.get("/robots.txt", include_in_schema=False)
async def robots():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        f"User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /api/\n\nSitemap: {SITE_URL}/sitemap.xml"
    )

@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap():
    from fastapi.responses import Response
    today = datetime.now().strftime("%Y-%m-%d")
    urls = [
        (SITE_URL,                                                            "1.0", "daily"),
        (f"{SITE_URL}/offerte",                                               "0.9", "weekly"),
        (f"{SITE_URL}/come-funziona",                                         "0.8", "monthly"),
        (f"{SITE_URL}/chi-siamo",                                             "0.7", "monthly"),
        (f"{SITE_URL}/guide",                                                 "0.8", "weekly"),
        (f"{SITE_URL}/guida/differenza-mercato-libero-tutelato",              "0.9", "monthly"),
        (f"{SITE_URL}/guida/come-leggere-bolletta-luce",                      "0.9", "monthly"),
        (f"{SITE_URL}/guida/fasce-orarie-f1-f2-f3",                          "0.9", "monthly"),
        (f"{SITE_URL}/guida/come-cambiare-fornitore-energia",                 "0.9", "monthly"),
        (f"{SITE_URL}/guida/pun-psv-cosa-sono",                              "0.9", "monthly"),
    ]
    locs = "\n".join(
        f"  <url><loc>{u}</loc><lastmod>{today}</lastmod>"
        f"<changefreq>{cf}</changefreq><priority>{p}</priority></url>"
        for u, p, cf in urls
    )
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{locs}
</urlset>'''
    return Response(content=xml, media_type="application/xml")

# ══════════════════════════════════════════════════════════════════════════════
# GUIDE — Pagine pillar SEO
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/guide", include_in_schema=False)
async def guide_index():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(_gp.guida_index())

@app.get("/guida/differenza-mercato-libero-tutelato", include_in_schema=False)
async def guida1():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(_gp.guida_mercato_libero())

@app.get("/guida/come-leggere-bolletta-luce", include_in_schema=False)
async def guida2():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(_gp.guida_bolletta_luce())

@app.get("/guida/fasce-orarie-f1-f2-f3", include_in_schema=False)
async def guida3():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(_gp.guida_fasce_orarie())

@app.get("/guida/come-cambiare-fornitore-energia", include_in_schema=False)
async def guida4():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(_gp.guida_cambiare_fornitore())

@app.get("/guida/pun-psv-cosa-sono", include_in_schema=False)
async def guida5():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(_gp.guida_pun_psv())

# ══════════════════════════════════════════════════════════════════════════════
# ANALISI PUBBLICA
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/analizza/{tipo}")
async def analizza(request: Request, tipo: str, file: UploadFile = File(...), profilo: str = "D2", lead_id: Optional[str] = None):
    # Rate limiting per IP
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown").split(",")[0].strip()
    _check_rate_limit(client_ip)

    if tipo not in ("luce","gas"): raise HTTPException(400,"tipo deve essere luce o gas")
    if profilo not in IVA: raise HTTPException(400,"profilo non valido")
    raw = await file.read()
    if len(raw) > 15*1024*1024: raise HTTPException(400,"File troppo grande (max 15 MB)")

    # Determina il mime type corretto in base all'estensione del file caricato
    ext = (file.filename or "").lower().rsplit(".", 1)[-1]
    mime_map = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}
    mime = mime_map.get(ext, "application/pdf")

    client = gemini()
    prompt = P_LUCE if tipo=="luce" else P_GAS
    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt, _types.Part.from_bytes(data=raw, mime_type=mime)],
            config=_types.GenerateContentConfig(response_mime_type="application/json")
        )
        raw_text = resp.text or ""
        if not raw_text.strip():
            raise HTTPException(503, "Il servizio AI non ha restituito dati. Riprova tra qualche minuto.")
        dati = parse_json(raw_text)
    except HTTPException: raise
    except json.JSONDecodeError as e:
        log.warning(f"Gemini risposta malformata (JSON): {e}")
        raise HTTPException(503, "Risposta AI non valida. Riprova tra qualche minuto.")
    except Exception as e:
        err_str = str(e).lower()
        if "quota" in err_str or "resource_exhausted" in err_str or "429" in err_str:
            log.warning(f"Gemini quota esaurita: {e}")
            raise HTTPException(503, "Servizio AI temporaneamente non disponibile (quota). Riprova tra qualche minuto.")
        log.error(f"Errore Gemini analisi: {e}")
        raise HTTPException(500, f"Errore AI: {e}")

    dg=dati.get("dati_generali",{}); dt=dati.get("dati_tecnici",{}); lc=dati.get("letture_e_consumi",{}); dc=dati.get("dettaglio_costi",{}); pf=dg.get("periodo_fatturazione") or {}
    profilo_ai = (dg.get("profilo_stimato") or profilo).upper()
    profilo_f  = profilo if profilo != "D2" else (profilo_ai if profilo_ai in IVA else "D2")
    consumo    = lc.get("consumo_totale_periodo") or lc.get("consumo_totale_smc") or 0
    unita      = "kWh" if tipo=="luce" else "Smc"
    pod_pdr    = dt.get("pod_pdr") or dt.get("pdr")
    spesa_e    = dc.get("spesa_materia_energia") or dc.get("spesa_materia_gas") or 0
    # Nuovi campi estratti dal prompt TO-BE
    prezzo_medio  = lc.get("prezzo_medio_kwh") if tipo == "luce" else lc.get("prezzo_medio_smc")
    potenza_disp  = dt.get("potenza_disponibile") if tipo == "luce" else None
    zona_clim     = dt.get("zona_climatica") if tipo == "gas" else None
    bonus         = dc.get("bonus_sociale") or 0
    confidence    = (dati.get("analisi_ai") or {}).get("confidence_score")
    # prezzo_medio ha la precedenza sul calcolo derivato
    costo_u       = prezzo_medio or (round(spesa_e / consumo, 5) if consumo > 0 else None)
    bid           = str(uuid.uuid4())

    with db() as c:
        c.execute(
            "INSERT INTO bollette (id,tipo,profilo,nome_file,data_upload,fornitore,num_fattura,"
            "periodo_inizio,periodo_fine,scadenza,totale,mercato,pod_pdr,potenza,consumo,unita,"
            "spesa_energia,spesa_trasporto,oneri,iva,dati_json,costo_unit,lead_id,"
            "potenza_disponibile,zona_climatica,bonus_sociale,confidence_score,prezzo_medio) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (bid, tipo, profilo_f, file.filename, datetime.now().isoformat(),
             dg.get("fornitore"), dg.get("numero_fattura"),
             pf.get("inizio"), pf.get("fine"), dg.get("scadenza"),
             dg.get("totale_fattura"), dg.get("mercato"), pod_pdr,
             dt.get("potenza_impegnata"), consumo, unita, spesa_e,
             dc.get("trasporto_gestione_contatore") or dc.get("trasporto_distribuzione"),
             dc.get("oneri_sistema"), dc.get("imposte_iva"),
             json.dumps(dati, ensure_ascii=False), costo_u, lead_id,
             potenza_disp, zona_clim, bonus if bonus else None, confidence, prezzo_medio))
        c.commit()
    return {"bolletta_id":bid,"tipo":tipo,"profilo":profilo_f,"profilo_label":PROFILI.get(profilo_f),"dati":dati,"costo_unitario":costo_u,"unita":unita}

# ── Recupera analisi salvata (per persistenza/link condivisibile) ────────────
@app.get("/api/analisi/{bid}")
async def get_analisi(bid: str):
    with db() as c:
        row = c.execute("SELECT * FROM bollette WHERE id=?", (bid,)).fetchone()
        if not row:
            raise HTTPException(404, "Analisi non trovata")
        b = dict(row)
        dati = json.loads(b["dati_json"]) if b["dati_json"] else {}
        # Recupera anche l'ultima comparazione se esiste
        comp = c.execute(
            "SELECT risultati_json FROM comparazioni WHERE bolletta_id=? ORDER BY data DESC LIMIT 1",
            (bid,)
        ).fetchone()
        offerte = json.loads(comp["risultati_json"]) if comp else None
    return {
        "bolletta_id": bid,
        "tipo": b["tipo"],
        "profilo": b["profilo"],
        "profilo_label": PROFILI.get(b["profilo"]),
        "dati": dati,
        "costo_unitario": b.get("costo_unit"),
        "unita": b.get("unita") or ("kWh" if b["tipo"]=="luce" else "Smc"),
        "offerte": offerte,
        "fornitore": b.get("fornitore"),
        "data_upload": b.get("data_upload"),
    }

# ── Comparazione ────────────────────────────────────────────────────────────
@app.post("/api/compara/{bid}")
async def compara(bid: str, bifuel_id: Optional[str] = Body(None, embed=True), bg: BackgroundTasks = None):
    with db() as c:
        row = c.execute("SELECT * FROM bollette WHERE id=?", (bid,)).fetchone()
        if not row:
            raise HTTPException(404, "Non trovata")
        b=dict(row); tipo=b["tipo"]; profilo=b["profilo"]
        dati=json.loads(b["dati_json"]) if b["dati_json"] else {}
        m=mesi(b.get("periodo_inizio",""),b.get("periodo_fine","")); fa=12/m
        att_annuo=(b.get("totale") or 0)*fa
        pun=pun_last(c); psv=psv_last(c)
        params_e=_load_params(c,"E"); params_g=_load_params(c,"G")
        bifuel=False
        if bifuel_id:
            o2=c.execute("SELECT tipo FROM bollette WHERE id=?", (bifuel_id,)).fetchone()
            bifuel=bool(o2 and o2["tipo"]!=tipo)
        if tipo=="luce": risultati=_cmp_luce(c,b,dati,m,fa,att_annuo,profilo,pun,bifuel,params_e)
        else:            risultati=_cmp_gas(c,b,dati,m,fa,att_annuo,profilo,psv,bifuel,params_g)
        risultati.sort(key=lambda x:x["spesa_annua_stimata"] if x.get("spesa_annua_stimata") else x["costo_annuo"])
        cid=str(uuid.uuid4())
        c.execute("INSERT INTO comparazioni (id,bolletta_id,tipo,profilo,data,risultati_json,bifuel) VALUES (?,?,?,?,?,?,?)",
            (cid,bid,tipo,profilo,datetime.now().isoformat(),json.dumps(risultati,ensure_ascii=False),int(bifuel)))
        c.commit()
        # Recupera email del lead associato per inviare i risultati
        _lead_email = None; _lead_nome = None
        if b.get("lead_id"):
            lr = c.execute("SELECT nome, email FROM leads WHERE id=?", (b["lead_id"],)).fetchone()
            if lr and lr["email"]:
                _lead_email = lr["email"]; _lead_nome = lr["nome"] or ""

    # Data ultima offerta nel DB (per mostrare all'utente quando sono stati aggiornati i dati)
    with db() as c2:
        t_off = "offerte_luce" if tipo == "luce" else "offerte_gas"
        _ultimo_agg = c2.execute(f"SELECT MAX(inserita) FROM {t_off} WHERE attiva=1").fetchone()[0]

    # Costi regolati per il response
    consumo_annuo = (b.get("consumo") or 0) * (12 / m)
    potenza = b.get("potenza") or b.get("potenza_disponibile") or 3.0
    if tipo == "luce":
        reg_info = _costi_regolati_luce(params_e, consumo_annuo, profilo, potenza)
    else:
        zona_map = {"A": 6, "B": 5, "C": 3, "D": 3, "E": 2, "F": 1}
        zc = b.get("zona_climatica") or "C"
        zona = zona_map.get(zc.upper()[:1], 3)
        reg_info = _costi_regolati_gas(params_g, consumo_annuo, profilo, zona)

    out = {"bolletta_id":bid,"tipo":tipo,"profilo":profilo,"profilo_label":PROFILI.get(profilo),"fornitore_attuale":b.get("fornitore"),"totale_attuale":b.get("totale"),"costo_annuo_attuale":round(att_annuo,2),"periodo_mesi":m,"consumo":b.get("consumo"),"unita":b.get("unita"),"iva_perc":IVA.get(profilo,0.22)*100,"bifuel":bifuel,"pun":pun,"psv":psv,"offerte":risultati,"migliore":risultati[0] if risultati else None,"risparmio_max":round(risultati[0]["risparmio_annuo"],2) if risultati else 0,"ultimo_aggiornamento_offerte":_ultimo_agg,"costi_regolati":reg_info}

    # Invia email con i risultati se abbiamo l'email del lead
    if _lead_email and bg:
        subj, html = build_risultati(
            nome=_lead_nome, tipo=tipo, profilo_label=PROFILI.get(profilo,""),
            totale=b.get("totale") or 0, consumo=b.get("consumo") or 0,
            unita=b.get("unita") or ("kWh" if tipo=="luce" else "Smc"),
            risparmio_max=out["risparmio_max"],
            offerta_migliore=risultati[0] if risultati else None,
            costo_annuo_attuale=out["costo_annuo_attuale"],
            fornitore_attuale=b.get("fornitore") or "",
            site_url=SITE_URL, from_email=FROM_EMAIL,
        )
        bg.add_task(se, _lead_email, subj, html)

    return out

def _cmp_luce(c,b,dati,m,fa,att,profilo,pun,bifuel,params=None):
    f=dati.get("letture_e_consumi",{}).get("ripartizione_fasce",{})
    f1=(f.get("F1") or {}).get("consumo") or 0; f2=(f.get("F2") or {}).get("consumo") or 0
    f3=(f.get("F3") or {}).get("consumo") or 0; f23=(f.get("F23") or {}).get("consumo") or 0
    tot=b.get("consumo") or (f1+f2+f3+f23); iva=IVA.get(profilo,0.22)
    potenza=b.get("potenza") or b.get("potenza_disponibile") or 3.0
    consumo_annuo=tot*fa
    reg=_costi_regolati_luce(params or {}, consumo_annuo, profilo, potenza)
    offs=c.execute("SELECT * FROM offerte_luce WHERE attiva=1 AND (profili LIKE ? OR profili LIKE ? OR profili LIKE ? OR profili=?)",(f"%{profilo}%",f"{profilo},%",f"%,{profilo}",profilo)).fetchall()
    res=[]
    for o in offs:
        of=dict(o); sb=(of.get("sconto_bifuel") or 0)/100 if bifuel else 0
        if of.get("tipo")=="VARIABILE" and of.get("spread_pun"):
            sp=of["spread_pun"]; p1=pun+sp; p2=pun+sp*0.85; p3=pun+sp*0.75; p23=pun+sp*0.80
            pmono=pun+sp
        else:
            p1=of.get("prezzo_f1"); p2=of.get("prezzo_f2"); p3=of.get("prezzo_f3")
            p23=of.get("prezzo_f23"); pmono=of.get("prezzo_mono")
            if not any([p1, p2, p3, pmono]):
                continue
            if p1 is None and pmono: p1=pmono
            if p2 is None: p2=p1
            if p3 is None: p3=p1
            if p23 is None: p23=round((p2+p3)/2,6) if p2 and p3 else p1
            if pmono is None: pmono=p1
            p1=p1 or 0; p2=p2 or 0; p3=p3 or 0; p23=p23 or 0
        if f1 and (f2 or f3): ce=f1*p1+f2*p2+f3*p3
        elif f1 and f23: ce=f1*p1+f23*p23
        elif tot:
            p_unit = (pmono or
                      dati.get("letture_e_consumi", {}).get("prezzo_medio_kwh") or
                      p1)
            ce = tot * p_unit if p_unit else 0
        else: ce=0
        qf=(of.get("quota_fissa") or 0)/12*m; tr=(of.get("oneri_trasp") or 0)*m
        sub=ce+qf+tr; cp=(sub+sub*iva)*(1-sb); ca=cp*fa; risp=att-ca
        # Spesa annua stimata = costo commerciale annuo + costi regolati (con IVA)
        spesa_stim = round(ca + reg["totale"] * (1 + iva), 2) if reg["totale"] else None
        res.append({"id":of["id"],"fornitore":of["fornitore"],"nome":of["nome"],"tipo":of["tipo"],"profili":of.get("profili",""),"spread_pun":of.get("spread_pun"),"prezzo_f1":of.get("prezzo_f1"),"prezzo_f2":of.get("prezzo_f2"),"prezzo_f3":of.get("prezzo_f3"),"prezzo_f23":of.get("prezzo_f23"),"quota_fissa":of.get("quota_fissa"),"sconto_bifuel":of.get("sconto_bifuel",0),"bifuel_applicato":bifuel,"costo_periodo":round(cp,2),"costo_annuo":round(ca,2),"spesa_annua_stimata":spesa_stim,"risparmio_annuo":round(risp,2),"perc_risparmio":round(risp/att*100,1) if att>0 else 0,"note":of.get("note"),"valida_fino":of.get("valida_fino"),"url":of.get("url"),"mercato":of.get("mercato"),"durata":of.get("durata"),"telefono":of.get("telefono"),"descrizione":of.get("descrizione")})
    return res

def _cmp_gas(c,b,dati,m,fa,att,profilo,psv,bifuel,params=None):
    smc=b.get("consumo") or 0; iva=IVA.get(profilo,0.22)
    consumo_annuo_smc=smc*fa
    # Zona climatica: da bolletta o default 3 (Centrale)
    zona_map={"A":6,"B":5,"C":3,"D":3,"E":2,"F":1}
    zc=b.get("zona_climatica") or "C"
    zona=zona_map.get(zc.upper()[:1], 3)
    reg=_costi_regolati_gas(params or {}, consumo_annuo_smc, profilo, zona)
    offs=c.execute("SELECT * FROM offerte_gas WHERE attiva=1 AND (profili LIKE ? OR profili LIKE ? OR profili LIKE ? OR profili=?)",(f"%{profilo}%",f"{profilo},%",f"%,{profilo}",profilo)).fetchall()
    res=[]
    for o in offs:
        of=dict(o); sb=(of.get("sconto_bifuel") or 0)/100 if bifuel else 0
        if of.get("tipo")=="VARIABILE":
            if not of.get("spread_psv"): continue
            p=psv+of["spread_psv"]
        else:
            if not of.get("prezzo_smc"): continue
            p=of["prezzo_smc"]
        ce=smc*p; qv=smc*(of.get("quota_var") or 0); qf=(of.get("quota_fissa") or 0)/12*m
        sub=ce+qv+qf; cp=(sub+sub*iva)*(1-sb); ca=cp*fa; risp=att-ca
        spesa_stim = round(ca + reg["totale"] * (1 + iva), 2) if reg["totale"] else None
        res.append({"id":of["id"],"fornitore":of["fornitore"],"nome":of["nome"],"tipo":of["tipo"],"profili":of.get("profili",""),"prezzo_smc":of.get("prezzo_smc"),"spread_psv":of.get("spread_psv"),"quota_fissa":of.get("quota_fissa"),"sconto_bifuel":of.get("sconto_bifuel",0),"bifuel_applicato":bifuel,"costo_periodo":round(cp,2),"costo_annuo":round(ca,2),"spesa_annua_stimata":spesa_stim,"risparmio_annuo":round(risp,2),"perc_risparmio":round(risp/att*100,1) if att>0 else 0,"note":of.get("note"),"valida_fino":of.get("valida_fino"),"url":of.get("url"),"mercato":of.get("mercato"),"durata":of.get("durata"),"telefono":of.get("telefono"),"descrizione":of.get("descrizione")})
    return res

# ══════════════════════════════════════════════════════════════════════════════
# LEADS — raccolta contatti
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/leads")
async def salva_lead(payload: dict = Body(...), bg: BackgroundTasks = None):
    lid = str(uuid.uuid4())
    # Accept both 'tipo_richiesta' (new) and 'tipo' (legacy) keys
    tipo_req = payload.get("tipo_richiesta") or payload.get("tipo") or "analisi"
    with db() as c:
        c.execute(
            "INSERT INTO leads (id,nome,cognome,email,telefono,tipo_richiesta,bolletta_id,"
            "consenso_privacy,consenso_marketing,data,note,fascia_oraria_preferita,offerta_richiesta) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (lid, payload.get("nome"), payload.get("cognome"), payload.get("email"), payload.get("telefono"),
             tipo_req, payload.get("bolletta_id"),
             int(payload.get("consenso_privacy", False)), int(payload.get("consenso_marketing", False)),
             datetime.now().isoformat(), payload.get("note"),
             payload.get("fascia_oraria_preferita"), payload.get("offerta_richiesta")))
        if payload.get("bolletta_id"):
            c.execute("UPDATE bollette SET lead_id=? WHERE id=?", (lid, payload["bolletta_id"]))
        c.commit()
    log.info(f"Nuovo lead [{tipo_req}]: {payload.get('email') or payload.get('telefono')}")

    # ── Email in background ─────────────────────────────────────────────
    to_email = payload.get("email", "") or ""
    nome_u   = payload.get("nome", "") or ""
    cognome_u= payload.get("cognome", "") or ""

    if to_email and tipo_req == "consulente" and bg:
        # 1. Conferma all'utente
        subj, html = build_consulente_utente(nome_u, to_email, SITE_URL, FROM_EMAIL)
        bg.add_task(se, to_email, subj, html)
        # 2. Notifica all'admin
        if ADMIN_EMAIL:
            subj_a, html_a = build_consulente_admin(
                nome_u, cognome_u, to_email,
                payload.get("telefono","") or "",
                bool(payload.get("consenso_marketing")),
                payload.get("bolletta_id","") or "",
                SITE_URL, FROM_EMAIL,
            )
            bg.add_task(se, ADMIN_EMAIL, subj_a, html_a)

    elif tipo_req == "ricontatto" and bg and ADMIN_EMAIL:
        # Urgenza: il lead vuole essere richiamato
        subj_a, html_a = build_ricontatto_admin(
            nome_u, cognome_u,
            payload.get("telefono","") or "",
            payload.get("fascia_oraria_preferita","") or "",
            payload.get("offerta_richiesta","") or "",
            payload.get("bolletta_id","") or "",
            SITE_URL, FROM_EMAIL,
        )
        bg.add_task(se, ADMIN_EMAIL, subj_a, html_a)

    return {"lead_id": lid, "saved": True}

# ══════════════════════════════════════════════════════════════════════════════
# OFFERTE — lettura pubblica
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/offerte/{tipo}")
async def offerte_pubbliche(tipo: str, profilo: Optional[str]=None):
    t = "offerte_luce" if tipo=="luce" else "offerte_gas"
    q = f"SELECT * FROM {t} WHERE attiva=1"
    p = []
    if profilo:
        q += " AND (profili LIKE ? OR profili LIKE ? OR profili LIKE ? OR profili=?)"
        p.extend([f"%{profilo}%",f"{profilo},%",f"%,{profilo}",profilo])
    with db() as c:
        rows = c.execute(q+" ORDER BY fornitore", p).fetchall()
        max_inserita = c.execute(f"SELECT MAX(inserita) FROM {t} WHERE attiva=1").fetchone()[0]
    return {
        "offerte": [dict(r) for r in rows],
        "ultimo_aggiornamento": max_inserita,
    }

@app.get("/api/indici")
async def indici_pubblici():
    with db() as c:
        rows = c.execute("SELECT * FROM indici ORDER BY tipo, periodo DESC").fetchall()
    out = {}
    for r in rows: out.setdefault(r["tipo"],[]).append(dict(r))
    return out

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN API — protette da token
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/admin/stats", dependencies=[Depends(require_admin)])
async def admin_stats():
    with db() as c:
        bl   = dict(c.execute("SELECT COUNT(*) n, AVG(totale) avg FROM bollette WHERE tipo='luce'").fetchone())
        bg   = dict(c.execute("SELECT COUNT(*) n, AVG(totale) avg FROM bollette WHERE tipo='gas'").fetchone())
        tl   = dict(c.execute("SELECT COUNT(*) n FROM leads").fetchone())
        ln   = dict(c.execute("SELECT COUNT(*) n FROM leads WHERE stato='nuovo'").fetchone())
        risp = c.execute("SELECT SUM(json_extract(risultati_json,'$[0].risparmio_annuo')) t FROM comparazioni WHERE json_extract(risultati_json,'$[0].risparmio_annuo')>0").fetchone()
        pun  = pun_last(c)
        psv  = psv_last(c)
        trend = [dict(r) for r in c.execute("SELECT strftime('%Y-%m',data_upload) m, tipo, COUNT(*) n, SUM(totale) tot FROM bollette GROUP BY m,tipo ORDER BY m DESC LIMIT 24").fetchall()]
    return {"luce": bl, "gas": bg, "leads_totali": tl["n"], "leads_nuovi": ln["n"], "risparmio_identificato": risp["t"] or 0, "pun": pun, "psv": psv, "trend": trend}

@app.get("/api/admin/leads", dependencies=[Depends(require_admin)])
async def admin_leads(stato: Optional[str]=None, limit: int=100):
    q = "SELECT * FROM leads WHERE 1=1"
    p: list = []
    if stato:
        q += " AND stato=?"; p.append(stato)
    q += " ORDER BY data DESC LIMIT ?"; p.append(limit)
    with db() as c:
        rows = c.execute(q, p).fetchall()
    return [dict(r) for r in rows]

@app.patch("/api/admin/leads/{lid}", dependencies=[Depends(require_admin)])
async def update_lead(lid: str, payload: dict = Body(...)):
    with db() as c:
        if "stato" in payload:
            c.execute("UPDATE leads SET stato=? WHERE id=?", (payload["stato"], lid))
        if "note" in payload:
            c.execute("UPDATE leads SET note=? WHERE id=?", (payload["note"], lid))
        c.commit()
    return {"updated": True}

@app.get("/api/admin/bollette", dependencies=[Depends(require_admin)])
async def admin_bollette(tipo: Optional[str]=None, limit: int=100):
    q = "SELECT id,tipo,profilo,nome_file,data_upload,fornitore,periodo_inizio,periodo_fine,totale,consumo,unita,costo_unit,mercato,pod_pdr,lead_id FROM bollette WHERE 1=1"
    p: list = []
    if tipo:
        q += " AND tipo=?"; p.append(tipo)
    q += " ORDER BY data_upload DESC LIMIT ?"; p.append(limit)
    with db() as c:
        rows = c.execute(q, p).fetchall()
    return [dict(r) for r in rows]

@app.delete("/api/admin/bollette/{bid}", dependencies=[Depends(require_admin)])
async def del_bolletta(bid: str):
    with db() as c:
        c.execute("DELETE FROM comparazioni WHERE bolletta_id=?", (bid,))
        c.execute("DELETE FROM bollette WHERE id=?", (bid,))
        c.commit()
    return {"deleted": True}

# Offerte admin CRUD
@app.post("/api/admin/offerte/estrai-pdf", dependencies=[Depends(require_admin)])
async def estrai_offerta_pdf(file: UploadFile = File(...)):
    """Estrae dati offerta da PDF usando Gemini AI."""
    raw = await file.read()
    if len(raw) > 15*1024*1024:
        raise HTTPException(400, "File troppo grande (max 15 MB)")
    client = gemini()
    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[P_OFFERTA, _types.Part.from_bytes(data=raw, mime_type="application/pdf")],
            config=_types.GenerateContentConfig(response_mime_type="application/json")
        )
        dati = parse_json(resp.text)
        return {"dati": dati, "fonte": "pdf"}
    except HTTPException: raise
    except Exception as e:
        log.error(f"estrai_offerta_pdf error: {e}")
        raise HTTPException(500, f"Errore AI: {e}")

@app.post("/api/admin/offerte/estrai-url", dependencies=[Depends(require_admin)])
async def estrai_offerta_url(url: str = Body(..., embed=True)):
    """Estrae dati offerta da URL usando Gemini AI."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent":"Mozilla/5.0"}) as hc:
            r = await hc.get(url)
            html = r.text
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()[:8000]
        client = gemini()
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[P_OFFERTA + f"\n\nContenuto pagina:\n{text}"],
            config=_types.GenerateContentConfig(response_mime_type="application/json")
        )
        dati = parse_json(resp.text)
        return {"dati": dati, "fonte": "url"}
    except HTTPException: raise
    except Exception as e:
        log.error(f"estrai_offerta_url error: {e}")
        raise HTTPException(500, f"Errore: {e}")

@app.post("/api/admin/offerte/{tipo}", dependencies=[Depends(require_admin)])
async def add_offerta(tipo: str, payload: dict = Body(...)):
    if not payload.get("fornitore") or not payload.get("nome"):
        raise HTTPException(400,"fornitore e nome obbligatori")
    oid = payload.get("id") or str(uuid.uuid4())
    now = datetime.now().isoformat()
    # Accetta sia i nomi DB (prezzo_mono) sia i nuovi nomi Gemini (prezzo_mono_eur_kwh)
    def _f(key, new_key=None, default=None):
        return payload.get(key) or (payload.get(new_key) if new_key else None) or default

    with db() as c:
        if tipo=="luce":
            c.execute(
                "INSERT INTO offerte_luce (id,fornitore,nome,tipo,profili,prezzo_f1,prezzo_f2,"
                "prezzo_f3,prezzo_f23,prezzo_mono,spread_pun,quota_fissa,oneri_trasp,sconto_bifuel,"
                "valida_fino,note,mercato,url,attiva,inserita) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)",
                (oid, payload["fornitore"], payload["nome"],
                 _f("tipo", default="FISSO"),
                 _f("profili", default="D2,D3,BTA,CDO"),
                 _f("prezzo_f1", "prezzo_f1_eur_kwh"),
                 _f("prezzo_f2", "prezzo_f2_eur_kwh"),
                 _f("prezzo_f3", "prezzo_f3_eur_kwh"),
                 _f("prezzo_f23", "prezzo_f23_eur_kwh"),
                 _f("prezzo_mono", "prezzo_mono_eur_kwh"),
                 _f("spread_pun"),
                 _f("quota_fissa", "quota_fissa_annua_eur", 0),
                 _f("oneri_trasp", "oneri_trasporto_eur_kwh", 0),
                 _f("sconto_bifuel", "sconto_bifuel_percentuale", 0),
                 _f("valida_fino"), _f("note"),
                 _f("mercato", default="Libero"),
                 _f("url"), now))
        else:
            c.execute(
                "INSERT INTO offerte_gas (id,fornitore,nome,tipo,profili,prezzo_smc,spread_psv,"
                "quota_fissa,quota_var,sconto_bifuel,valida_fino,note,mercato,url,attiva,inserita) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)",
                (oid, payload["fornitore"], payload["nome"],
                 _f("tipo", default="FISSO"),
                 _f("profili", default="D2,D3,BTA"),
                 _f("prezzo_smc"),
                 _f("spread_psv"),
                 _f("quota_fissa", "quota_fissa_annua_eur", 0),
                 _f("quota_var", "quota_variabile_smc", 0),
                 _f("sconto_bifuel", "sconto_bifuel_percentuale", 0),
                 _f("valida_fino"), _f("note"),
                 _f("mercato", default="Libero"),
                 _f("url"), now))
        c.commit()
    return {"id": oid, "created": True}

@app.delete("/api/admin/offerte/{tipo}/{oid}", dependencies=[Depends(require_admin)])
async def del_offerta(tipo: str, oid: str):
    t = "offerte_luce" if tipo=="luce" else "offerte_gas"
    with db() as c:
        c.execute(f"UPDATE {t} SET attiva=0 WHERE id=?", (oid,))
        c.commit()
    return {"deactivated": True}

# Indici admin
@app.post("/api/admin/indici/aggiorna", dependencies=[Depends(require_admin)])
async def aggiorna_indici(bg: BackgroundTasks):
    bg.add_task(_fetch_indici)
    return {"message":"Aggiornamento avviato in background. Ricarica tra 30 secondi."}

@app.post("/api/admin/indici/manuale", dependencies=[Depends(require_admin)])
async def indice_manuale(payload: dict = Body(...)):
    tipo=payload.get("tipo","").upper(); periodo=payload.get("periodo",""); valore=payload.get("valore")
    if tipo not in ("PUN","PSV") or not periodo or valore is None: raise HTTPException(400,"tipo, periodo, valore richiesti")
    iid = f"{tipo.lower()}-{periodo}"
    with db() as c:
        c.execute("INSERT OR REPLACE INTO indici (id,tipo,periodo,valore,fonte,aggiornato) VALUES (?,?,?,?,'Manuale',?)",
            (iid, tipo, periodo, float(valore), datetime.now().isoformat()))
        c.commit()
    return {"updated": True}

_INDICI_ENDPOINTS = [
    # Endpoint API (stessa famiglia di geoService che funziona)
    "https://www.ilportaleofferte.it/portaleOfferte/api/rs/it/portal/prezziStoriciService.json",
    "https://www.ilportaleofferte.it/portaleOfferte/api/rs/it/portal/indiciMercatoService.json",
    # Endpoint REST classico (bloccato da WAF ma proviamo comunque)
    "https://www.ilportaleofferte.it/portaleOfferte/rest/prezziStoriciIndici",
]
_INDICI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "application/json, */*",
    "Accept-Language": "it-IT,it;q=0.9",
    "Referer": "https://www.ilportaleofferte.it/portaleOfferte/it/confronto-tariffe-prezzi-luce-gas.page",
    "X-Requested-With": "XMLHttpRequest",
}

async def _fetch_indici():
    """
    Tenta di aggiornare gli indici PUN/PSV dal Portale ARERA.
    Prova più endpoint in sequenza; se tutti falliscono, mantiene i dati esistenti.
    """
    data = None
    endpoint_ok = None
    try:
        async with httpx.AsyncClient(
            headers=_INDICI_HEADERS, follow_redirects=True, timeout=20,
            # verify=False: il portale ARERA usa certificati intermedi non sempre riconosciuti
            # da Python su alcuni ambienti (es. Railway). Acceptable perché stiamo solo
            # leggendo dati pubblici di prezzi — nessun dato sensibile in transito.
            # Rimuovere se ARERA aggiorna la catena di certificati.
            verify=False,
        ) as hc:
            # Warm-up: ottieni cookie di sessione
            try:
                await hc.get(
                    "https://www.ilportaleofferte.it/portaleOfferte/it/confronto-tariffe-prezzi-luce-gas.page",
                    timeout=10,
                )
            except Exception:
                pass
            for endpoint in _INDICI_ENDPOINTS:
                try:
                    r = await hc.get(endpoint)
                    if r.status_code == 200 and r.text.strip().startswith(("[", "{")):
                        data = r.json()
                        endpoint_ok = endpoint
                        break
                    else:
                        log.debug(f"Indici {endpoint}: status={r.status_code}, body_len={len(r.text)}")
                except Exception as e:
                    log.debug(f"Indici {endpoint}: {e}")
    except Exception as e:
        log.error(f"Errore connessione fetch indici: {e}")
        return

    if data is None:
        log.warning(
            "Indici PUN/PSV: nessun endpoint ARERA disponibile. "
            "Aggiorna manualmente via POST /api/admin/indici/manuale"
        )
        return

    count = 0
    try:
        items = data if isinstance(data, list) else (
            data.get("prezzi") or data.get("indici") or data.get("result", {}).get("indici") or []
        )
        with db() as c:
            for e in items:
                tipo = (e.get("codiceIndice") or e.get("tipo") or "").upper()
                mese = e.get("meseAnno") or e.get("periodo") or ""
                v = e.get("prezzoMedio") or e.get("valore")
                if tipo not in ("PUN", "PSV", "CMEM") or not mese or v is None:
                    continue
                # Formato mese: "MM/YYYY" → "YYYY-MM"
                parts = str(mese).split("/")
                if len(parts) == 2:
                    periodo = f"{parts[1]}-{parts[0].zfill(2)}"
                elif len(parts) == 1 and len(mese) == 7:
                    periodo = mese  # già "YYYY-MM"
                else:
                    continue
                iid = f"{tipo.lower()}-{periodo}"
                c.execute(
                    "INSERT OR REPLACE INTO indici (id,tipo,periodo,valore,fonte,aggiornato) VALUES (?,?,?,?,'Portale ARERA',?)",
                    (iid, tipo, periodo, float(v), datetime.now().isoformat()),
                )
                count += 1
            c.commit()
        log.info(f"Indici aggiornati: {count} record da {endpoint_ok}")
    except Exception as e:
        log.error(f"Errore salvataggio indici: {e}")

# ── Sync ARERA manuale ─────────────────────────────────────────────────────
@app.post("/api/admin/sync-arera", dependencies=[Depends(require_admin)])
async def sync_arera_manual():
    """Forza il download e l'aggiornamento delle offerte ARERA (flush-and-fill)."""
    try:
        with db() as conn:
            result = await _arera.run_sync(conn)
        return result
    except Exception as e:
        log.error(f"sync-arera manuale fallita: {e}")
        raise HTTPException(500, f"Sync fallita: {e}")

# Export CSV admin
@app.get("/api/admin/export/bollette", dependencies=[Depends(require_admin)])
async def export_bollette():
    fields = ("id","tipo","profilo","fornitore","periodo_inizio","periodo_fine","totale","consumo","unita","costo_unit","mercato","pod_pdr")
    with db() as c:
        rows = c.execute("SELECT * FROM bollette ORDER BY data_upload DESC").fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(fields)
    for r in rows:
        d = dict(r); w.writerow([str(d.get(k, "") or "") for k in fields])
    return StreamingResponse(io.BytesIO(buf.getvalue().encode("utf-8-sig")), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=bollette_{datetime.now().strftime('%Y%m%d')}.csv"})

@app.get("/api/admin/export/leads", dependencies=[Depends(require_admin)])
async def export_leads():
    fields = ("id","nome","cognome","email","telefono","tipo_richiesta","bolletta_id","data","stato","note")
    with db() as c:
        rows = c.execute("SELECT * FROM leads ORDER BY data DESC").fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(fields)
    for r in rows:
        d = dict(r); w.writerow([str(d.get(k, "") or "") for k in fields])
    return StreamingResponse(io.BytesIO(buf.getvalue().encode("utf-8-sig")), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=leads_{datetime.now().strftime('%Y%m%d')}.csv"})

# ══════════════════════════════════════════════════════════════════════════════
# PAGINE INTERNE
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/offerte", include_in_schema=False)
async def pagina_offerte_route():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(_gp.pagina_offerte())

@app.get("/come-funziona", include_in_schema=False)
async def pagina_come_funziona_route():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(_gp.pagina_come_funziona())

@app.get("/chi-siamo", include_in_schema=False)
async def pagina_chi_siamo_route():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(_gp.pagina_chi_siamo())

# ══════════════════════════════════════════════════════════════════════════════
# PAGINE LEGALI
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/trattamento-dati", include_in_schema=False)
@app.get("/condizioni-generali", include_in_schema=False)
@app.get("/termini", include_in_schema=False)
async def pagina_termini_route():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(_gp.pagina_termini())

@app.get("/privacy", include_in_schema=False)
async def pagina_privacy_route():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(_gp.pagina_privacy())

# ══════════════════════════════════════════════════════════════════════════════
# LINK CONDIVISIBILE ANALISI
# GET /risultati/{bolletta_id}  → ricarica la pagina con l'analisi già fatta
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/risultati/{bolletta_id}", include_in_schema=False)
async def risultati_condivisibili(bolletta_id: str):
    """
    Pagina pubblica condivisibile per un'analisi già eseguita.
    Carica index.html con un meta tag che fa partire auto-load dell'analisi via JS.
    """
    from fastapi.responses import HTMLResponse
    # Validazione UUID — rifiuta qualsiasi ID non conforme prima di procedere
    _UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
    if not _UUID_RE.match(bolletta_id):
        raise HTTPException(400, "ID non valido.")
    # Verifica che la bolletta esista
    with db() as c:
        row = c.execute("SELECT id, tipo, profilo FROM bollette WHERE id=?", (bolletta_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Analisi non trovata o scaduta.")
    # Inietta i meta tag — escape HTML per prevenire XSS
    r = dict(row)
    safe_id     = _html.escape(r["id"],      quote=True)
    safe_tipo   = _html.escape(r["tipo"],    quote=True)
    safe_profilo = _html.escape(r["profilo"], quote=True)
    page = (FRONTEND / "index.html").read_text(encoding="utf-8")
    inject = (
        f'<meta name="br-risultati-id" content="{safe_id}">\n'
        f'  <meta name="br-risultati-tipo" content="{safe_tipo}">\n'
        f'  <meta name="br-risultati-profilo" content="{safe_profilo}">'
    )
    page = page.replace('<meta name="viewport"', f'{inject}\n  <meta name="viewport"', 1)
    return HTMLResponse(page)
