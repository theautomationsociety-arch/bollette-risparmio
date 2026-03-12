"""
Bollette Risparmio — Backend Pubblico + Admin
Sito comparatore bollette Luce & Gas — struttura ispirata ad AIChange.it
"""

import os, json, uuid, logging, io, re, httpx, time, collections
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
    build_risultati, build_consulente_utente, build_consulente_admin, send_email as _send_email
)
import backend.guide_pages as _gp

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
    yield

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
            lead_id TEXT
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
            url TEXT, attiva INTEGER DEFAULT 1, inserita TEXT
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
            url TEXT, attiva INTEGER DEFAULT 1, inserita TEXT
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
            stato TEXT DEFAULT 'nuovo'
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
P_LUCE = """Analizza questa bolletta elettrica italiana. Restituisci SOLO JSON:
{"dati_generali":{"fornitore":null,"numero_fattura":null,"periodo_fatturazione":{"inizio":"YYYY-MM-DD","fine":"YYYY-MM-DD"},"scadenza":null,"totale_fattura":0.0,"mercato":"Libero o Tutelato","profilo_stimato":"D2 o D3 o BTA o CDO"},
"dati_tecnici":{"pod_pdr":null,"potenza_impegnata":0.0,"tipologia_uso":null,"indirizzo_fornitura":null},
"letture_e_consumi":{"consumo_totale_periodo":0.0,"ripartizione_fasce":{"F1":{"consumo":0.0,"prezzo_unitario":0.0},"F2":{"consumo":0.0,"prezzo_unitario":0.0},"F3":{"consumo":0.0,"prezzo_unitario":0.0},"F23":{"consumo":0.0,"prezzo_unitario":0.0}},"lettura_stimata_o_reale":null},
"dettaglio_costi":{"spesa_materia_energia":0.0,"trasporto_gestione_contatore":0.0,"oneri_sistema":0.0,"imposte_iva":0.0,"accise":0.0,"canone_rai":0.0,"altre_partite":0.0},
"analisi_ai":{"anomalie_rilevate":[],"suggerimenti":[],"fascia_consumo":"basso|medio|alto"}}"""

P_GAS = """Analizza questa bolletta gas italiana. Restituisci SOLO JSON:
{"dati_generali":{"fornitore":null,"numero_fattura":null,"periodo_fatturazione":{"inizio":"YYYY-MM-DD","fine":"YYYY-MM-DD"},"scadenza":null,"totale_fattura":0.0,"mercato":"Libero o Tutelato","profilo_stimato":"D2 o D3 o BTA"},
"dati_tecnici":{"pdr":null,"tipologia_uso":null,"indirizzo_fornitura":null,"coefficiente_conversione":0.0},
"letture_e_consumi":{"consumo_totale_smc":0.0,"consumo_totale_kwh":0.0,"lettura_stimata_o_reale":null},
"dettaglio_costi":{"spesa_materia_gas":0.0,"trasporto_distribuzione":0.0,"oneri_sistema":0.0,"imposte_iva":0.0,"accise":0.0,"addizionale_regionale":0.0,"altre_partite":0.0},
"analisi_ai":{"anomalie_rilevate":[],"suggerimenti":[],"fascia_consumo":"basso|medio|alto"}}"""

P_OFFERTA = """Estrai dati da questa offerta commerciale energia italiana. Restituisci SOLO JSON:
{"tipo_utenza":"luce o gas","fornitore":null,"nome_offerta":null,"tipo_prezzo":"FISSO o VARIABILE","profili_compatibili":"D2,D3 o BTA o D2,D3,BTA,CDO","prezzo_f1_eur_kwh":null,"prezzo_f2_eur_kwh":null,"prezzo_f3_eur_kwh":null,"prezzo_f23_eur_kwh":null,"spread_pun":null,"prezzo_smc":null,"spread_psv":null,"quota_fissa_annua_eur":null,"sconto_bifuel_percentuale":null,"valida_fino":"YYYY-MM-DD o null","note":null,"mercato":"Libero o Tutelato"}"""

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — Pagine
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/", include_in_schema=False)
async def root(): return FileResponse(str(FRONTEND/"index.html"))

@app.get("/admin", include_in_schema=False)
async def admin_page(): return FileResponse(str(FRONTEND/"admin.html"))

@app.get("/api/health")
async def health():
    c = get_db()
    n = {t: c.execute(f"SELECT COUNT(*) FROM bollette WHERE tipo='{t}'").fetchone()[0] for t in ("luce","gas")}
    pun = pun_last(c); c.close()
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
        (f"{SITE_URL}/#come-funziona",                                        "0.8", "monthly"),
        (f"{SITE_URL}/#faq",                                                  "0.7", "monthly"),
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
    costo_u    = round(spesa_e/consumo,5) if consumo>0 else None
    bid        = str(uuid.uuid4())

    with db() as c:
        c.execute("""INSERT INTO bollette (id,tipo,profilo,nome_file,data_upload,fornitore,num_fattura,periodo_inizio,periodo_fine,scadenza,totale,mercato,pod_pdr,potenza,consumo,unita,spesa_energia,spesa_trasporto,oneri,iva,dati_json,costo_unit,lead_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (bid,tipo,profilo_f,file.filename,datetime.now().isoformat(),dg.get("fornitore"),dg.get("numero_fattura"),pf.get("inizio"),pf.get("fine"),dg.get("scadenza"),dg.get("totale_fattura"),dg.get("mercato"),pod_pdr,dt.get("potenza_impegnata"),consumo,unita,spesa_e,dc.get("trasporto_gestione_contatore") or dc.get("trasporto_distribuzione"),dc.get("oneri_sistema"),dc.get("imposte_iva"),json.dumps(dati,ensure_ascii=False),costo_u,lead_id))
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
        bifuel=False
        if bifuel_id:
            o2=c.execute("SELECT tipo FROM bollette WHERE id=?", (bifuel_id,)).fetchone()
            bifuel=bool(o2 and o2["tipo"]!=tipo)
        if tipo=="luce": risultati=_cmp_luce(c,b,dati,m,fa,att_annuo,profilo,pun,bifuel)
        else:            risultati=_cmp_gas(c,b,dati,m,fa,att_annuo,profilo,psv,bifuel)
        risultati.sort(key=lambda x:x["costo_annuo"])
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

    out = {"bolletta_id":bid,"tipo":tipo,"profilo":profilo,"profilo_label":PROFILI.get(profilo),"fornitore_attuale":b.get("fornitore"),"totale_attuale":b.get("totale"),"costo_annuo_attuale":round(att_annuo,2),"periodo_mesi":m,"consumo":b.get("consumo"),"unita":b.get("unita"),"iva_perc":IVA.get(profilo,0.22)*100,"bifuel":bifuel,"pun":pun,"psv":psv,"offerte":risultati,"migliore":risultati[0] if risultati else None,"risparmio_max":round(risultati[0]["risparmio_annuo"],2) if risultati else 0,"ultimo_aggiornamento_offerte":_ultimo_agg}

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

def _cmp_luce(c,b,dati,m,fa,att,profilo,pun,bifuel):
    f=dati.get("letture_e_consumi",{}).get("ripartizione_fasce",{})
    f1=(f.get("F1") or {}).get("consumo") or 0; f2=(f.get("F2") or {}).get("consumo") or 0
    f3=(f.get("F3") or {}).get("consumo") or 0; f23=(f.get("F23") or {}).get("consumo") or 0
    tot=b.get("consumo") or (f1+f2+f3+f23); iva=IVA.get(profilo,0.22)
    offs=c.execute("SELECT * FROM offerte_luce WHERE attiva=1 AND (profili LIKE ? OR profili LIKE ? OR profili LIKE ? OR profili=?)",(f"%{profilo}%",f"{profilo},%",f"%,{profilo}",profilo)).fetchall()
    res=[]
    for o in offs:
        of=dict(o); sb=(of.get("sconto_bifuel") or 0)/100 if bifuel else 0
        if of.get("tipo")=="VARIABILE" and of.get("spread_pun"):
            p1=pun+of["spread_pun"]; p2=pun+of["spread_pun"]*0.85; p3=pun+of["spread_pun"]*0.75; p23=pun+of["spread_pun"]*0.80
        else: p1=of.get("prezzo_f1") or 0; p2=of.get("prezzo_f2") or 0; p3=of.get("prezzo_f3") or 0; p23=of.get("prezzo_f23") or 0
        if f1 and (f2 or f3): ce=f1*p1+f2*p2+f3*p3
        elif f1 and f23: ce=f1*p1+f23*p23
        elif tot:
            avg_fasce = (p1+p2+p3)/3 if (p1+p2+p3) > 0 else p1
            p_unit = of.get("prezzo_mono") or p1 or avg_fasce
            ce = tot * p_unit
        else: ce=0
        qf=(of.get("quota_fissa") or 0)/12*m; tr=(of.get("oneri_trasp") or 0)*m
        sub=ce+qf+tr; cp=(sub+sub*iva)*(1-sb); ca=cp*fa; risp=att-ca
        res.append({"id":of["id"],"fornitore":of["fornitore"],"nome":of["nome"],"tipo":of["tipo"],"profili":of.get("profili",""),"spread_pun":of.get("spread_pun"),"prezzo_f1":of.get("prezzo_f1"),"prezzo_f2":of.get("prezzo_f2"),"prezzo_f3":of.get("prezzo_f3"),"prezzo_f23":of.get("prezzo_f23"),"quota_fissa":of.get("quota_fissa"),"sconto_bifuel":of.get("sconto_bifuel",0),"bifuel_applicato":bifuel,"costo_periodo":round(cp,2),"costo_annuo":round(ca,2),"risparmio_annuo":round(risp,2),"perc_risparmio":round(risp/att*100,1) if att>0 else 0,"note":of.get("note"),"valida_fino":of.get("valida_fino"),"url":of.get("url"),"mercato":of.get("mercato")})
    return res

def _cmp_gas(c,b,dati,m,fa,att,profilo,psv,bifuel):
    smc=b.get("consumo") or 0; iva=IVA.get(profilo,0.22)
    offs=c.execute("SELECT * FROM offerte_gas WHERE attiva=1 AND (profili LIKE ? OR profili LIKE ? OR profili LIKE ? OR profili=?)",(f"%{profilo}%",f"{profilo},%",f"%,{profilo}",profilo)).fetchall()
    res=[]
    for o in offs:
        of=dict(o); sb=(of.get("sconto_bifuel") or 0)/100 if bifuel else 0
        p=psv+(of.get("spread_psv") or 0) if of.get("tipo")=="VARIABILE" and of.get("spread_psv") else (of.get("prezzo_smc") or 0)
        ce=smc*p; qv=smc*(of.get("quota_var") or 0); qf=(of.get("quota_fissa") or 0)/12*m
        sub=ce+qv+qf; cp=(sub+sub*iva)*(1-sb); ca=cp*fa; risp=att-ca
        res.append({"id":of["id"],"fornitore":of["fornitore"],"nome":of["nome"],"tipo":of["tipo"],"profili":of.get("profili",""),"prezzo_smc":of.get("prezzo_smc"),"spread_psv":of.get("spread_psv"),"quota_fissa":of.get("quota_fissa"),"sconto_bifuel":of.get("sconto_bifuel",0),"bifuel_applicato":bifuel,"costo_periodo":round(cp,2),"costo_annuo":round(ca,2),"risparmio_annuo":round(risp,2),"perc_risparmio":round(risp/att*100,1) if att>0 else 0,"note":of.get("note"),"valida_fino":of.get("valida_fino"),"url":of.get("url"),"mercato":of.get("mercato")})
    return res

# ══════════════════════════════════════════════════════════════════════════════
# LEADS — raccolta contatti
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/leads")
async def salva_lead(payload: dict = Body(...), bg: BackgroundTasks = None):
    lid = str(uuid.uuid4())
    with db() as c:
        c.execute("INSERT INTO leads (id,nome,cognome,email,telefono,tipo_richiesta,bolletta_id,consenso_privacy,consenso_marketing,data,note) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (lid, payload.get("nome"), payload.get("cognome"), payload.get("email"), payload.get("telefono"),
             payload.get("tipo","analisi"), payload.get("bolletta_id"),
             int(payload.get("consenso_privacy",False)), int(payload.get("consenso_marketing",False)),
             datetime.now().isoformat(), payload.get("note")))
        if payload.get("bolletta_id"):
            c.execute("UPDATE bollette SET lead_id=? WHERE id=?", (lid, payload["bolletta_id"]))
        c.commit()
    log.info(f"Nuovo lead: {payload.get('email')}")

    # ── Email in background ─────────────────────────────────────────────
    tipo_req = payload.get("tipo", "analisi")
    to_email = payload.get("email", "")
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
    c = get_db()
    bl = dict(c.execute("SELECT COUNT(*) n, AVG(totale) avg FROM bollette WHERE tipo='luce'").fetchone())
    bg = dict(c.execute("SELECT COUNT(*) n, AVG(totale) avg FROM bollette WHERE tipo='gas'").fetchone())
    tl = dict(c.execute("SELECT COUNT(*) n FROM leads").fetchone())
    ln = dict(c.execute("SELECT COUNT(*) n FROM leads WHERE stato='nuovo'").fetchone())
    risp = c.execute("SELECT SUM(json_extract(risultati_json,'$[0].risparmio_annuo')) t FROM comparazioni WHERE json_extract(risultati_json,'$[0].risparmio_annuo')>0").fetchone()
    pun = pun_last(c); psv = psv_last(c)
    trend = [dict(r) for r in c.execute("SELECT strftime('%Y-%m',data_upload) m, tipo, COUNT(*) n, SUM(totale) tot FROM bollette GROUP BY m,tipo ORDER BY m DESC LIMIT 24").fetchall()]
    c.close()
    return {"luce":bl,"gas":bg,"leads_totali":tl["n"],"leads_nuovi":ln["n"],"risparmio_identificato":risp["t"] or 0,"pun":pun,"psv":psv,"trend":trend}

@app.get("/api/admin/leads", dependencies=[Depends(require_admin)])
async def admin_leads(stato: Optional[str]=None, limit: int=100):
    c = get_db()
    q = "SELECT * FROM leads WHERE 1=1"
    p = []
    if stato: q += " AND stato=?"; p.append(stato)
    q += " ORDER BY data DESC LIMIT ?"; p.append(limit)
    rows = c.execute(q,p).fetchall(); c.close()
    return [dict(r) for r in rows]

@app.patch("/api/admin/leads/{lid}", dependencies=[Depends(require_admin)])
async def update_lead(lid: str, payload: dict = Body(...)):
    c = get_db()
    if "stato" in payload:
        c.execute("UPDATE leads SET stato=? WHERE id=?", (payload["stato"],lid))
    if "note" in payload:
        c.execute("UPDATE leads SET note=? WHERE id=?", (payload["note"],lid))
    c.commit(); c.close()
    return {"updated": True}

@app.get("/api/admin/bollette", dependencies=[Depends(require_admin)])
async def admin_bollette(tipo: Optional[str]=None, limit: int=100):
    c = get_db()
    q = "SELECT id,tipo,profilo,nome_file,data_upload,fornitore,periodo_inizio,periodo_fine,totale,consumo,unita,costo_unit,mercato,pod_pdr,lead_id FROM bollette WHERE 1=1"
    p = []
    if tipo: q += " AND tipo=?"; p.append(tipo)
    q += " ORDER BY data_upload DESC LIMIT ?"; p.append(limit)
    rows = c.execute(q,p).fetchall(); c.close()
    return [dict(r) for r in rows]

@app.delete("/api/admin/bollette/{bid}", dependencies=[Depends(require_admin)])
async def del_bolletta(bid: str):
    c = get_db()
    c.execute("DELETE FROM comparazioni WHERE bolletta_id=?", (bid,))
    c.execute("DELETE FROM bollette WHERE id=?", (bid,))
    c.commit(); c.close()
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
    c = get_db()
    if tipo=="luce":
        c.execute("""INSERT INTO offerte_luce (id,fornitore,nome,tipo,profili,prezzo_f1,prezzo_f2,prezzo_f3,prezzo_f23,prezzo_mono,spread_pun,quota_fissa,oneri_trasp,sconto_bifuel,valida_fino,note,mercato,url,attiva,inserita) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)""",
            (oid,payload["fornitore"],payload["nome"],payload.get("tipo","FISSO"),payload.get("profili","D2,D3,BTA,CDO"),payload.get("prezzo_f1"),payload.get("prezzo_f2"),payload.get("prezzo_f3"),payload.get("prezzo_f23"),payload.get("prezzo_mono"),payload.get("spread_pun"),payload.get("quota_fissa",0),payload.get("oneri_trasp",0),payload.get("sconto_bifuel",0),payload.get("valida_fino"),payload.get("note"),payload.get("mercato","Libero"),payload.get("url"),now))
    else:
        c.execute("""INSERT INTO offerte_gas (id,fornitore,nome,tipo,profili,prezzo_smc,spread_psv,quota_fissa,quota_var,sconto_bifuel,valida_fino,note,mercato,url,attiva,inserita) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)""",
            (oid,payload["fornitore"],payload["nome"],payload.get("tipo","FISSO"),payload.get("profili","D2,D3,BTA"),payload.get("prezzo_smc"),payload.get("spread_psv"),payload.get("quota_fissa",0),payload.get("quota_var",0),payload.get("sconto_bifuel",0),payload.get("valida_fino"),payload.get("note"),payload.get("mercato","Libero"),payload.get("url"),now))
    c.commit(); c.close()
    return {"id":oid,"created":True}

@app.delete("/api/admin/offerte/{tipo}/{oid}", dependencies=[Depends(require_admin)])
async def del_offerta(tipo: str, oid: str):
    t = "offerte_luce" if tipo=="luce" else "offerte_gas"
    c = get_db(); c.execute(f"UPDATE {t} SET attiva=0 WHERE id=?", (oid,)); c.commit(); c.close()
    return {"deactivated":True}

# Indici admin
@app.post("/api/admin/indici/aggiorna", dependencies=[Depends(require_admin)])
async def aggiorna_indici(bg: BackgroundTasks):
    bg.add_task(_fetch_indici)
    return {"message":"Aggiornamento avviato in background. Ricarica tra 30 secondi."}

@app.post("/api/admin/indici/manuale", dependencies=[Depends(require_admin)])
async def indice_manuale(payload: dict = Body(...)):
    tipo=payload.get("tipo","").upper(); periodo=payload.get("periodo",""); valore=payload.get("valore")
    if tipo not in ("PUN","PSV") or not periodo or valore is None: raise HTTPException(400,"tipo, periodo, valore richiesti")
    iid=f"{tipo.lower()}-{periodo}"
    c = get_db()
    c.execute("INSERT OR REPLACE INTO indici (id,tipo,periodo,valore,fonte,aggiornato) VALUES (?,?,?,?,'Manuale',?)",
        (iid,tipo,periodo,float(valore),datetime.now().isoformat()))
    c.commit(); c.close()
    return {"updated":True}

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
            headers=_INDICI_HEADERS, follow_redirects=True, timeout=20, verify=False
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

    c = get_db(); count = 0
    try:
        items = data if isinstance(data, list) else (
            data.get("prezzi") or data.get("indici") or data.get("result", {}).get("indici") or []
        )
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
    finally:
        c.close()

# Export CSV admin
@app.get("/api/admin/export/bollette", dependencies=[Depends(require_admin)])
async def export_bollette():
    c = get_db(); rows = c.execute("SELECT * FROM bollette ORDER BY data_upload DESC").fetchall(); c.close()
    lines=["id,tipo,profilo,fornitore,periodo_inizio,periodo_fine,totale,consumo,unita,costo_unit,mercato,pod_pdr"]
    for r in rows:
        d=dict(r); lines.append(",".join([str(d.get(k,"") or "") for k in ("id","tipo","profilo","fornitore","periodo_inizio","periodo_fine","totale","consumo","unita","costo_unit","mercato","pod_pdr")]))
    return StreamingResponse(io.BytesIO("\n".join(lines).encode("utf-8-sig")),media_type="text/csv",headers={"Content-Disposition":f"attachment; filename=bollette_{datetime.now().strftime('%Y%m%d')}.csv"})

@app.get("/api/admin/export/leads", dependencies=[Depends(require_admin)])
async def export_leads():
    c = get_db(); rows = c.execute("SELECT * FROM leads ORDER BY data DESC").fetchall(); c.close()
    lines=["id,nome,cognome,email,telefono,tipo,bolletta_id,data,stato,note"]
    for r in rows:
        d=dict(r); lines.append(",".join([f'"{str(d.get(k,"") or "")}"' for k in ("id","nome","cognome","email","telefono","tipo_richiesta","bolletta_id","data","stato","note")]))
    return StreamingResponse(io.BytesIO("\n".join(lines).encode("utf-8-sig")),media_type="text/csv",headers={"Content-Disposition":f"attachment; filename=leads_{datetime.now().strftime('%Y%m%d')}.csv"})

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
    # Verifica che la bolletta esista
    with db() as c:
        row = c.execute("SELECT id, tipo, profilo FROM bollette WHERE id=?", (bolletta_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Analisi non trovata o scaduta.")
    # Serve la stessa index.html con un meta tag per il JS
    html = (FRONTEND / "index.html").read_text()
    # Inietta il bolletta_id nella pagina in modo che JS lo legga
    inject = f'<meta name="br-risultati-id" content="{bolletta_id}">\n  <meta name="br-risultati-tipo" content="{dict(row)["tipo"]}">\n  <meta name="br-risultati-profilo" content="{dict(row)["profilo"]}">'
    html = html.replace('<meta name="viewport"', f'{inject}\n  <meta name="viewport"', 1)
    return HTMLResponse(html)
