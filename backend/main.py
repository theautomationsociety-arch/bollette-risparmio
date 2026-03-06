"""
BollettaAI — Backend Pubblico + Admin
Sito comparatore bollette Luce & Gas — struttura ispirata ad AIChange.it
"""

import os, json, uuid, logging, io, re, httpx
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, Body, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
import sqlite3

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
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "admin123")

# ── Lifespan ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log.info("BollettaAI avviato")
    yield

app = FastAPI(title="BollettaAI", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

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
    if c.execute("SELECT COUNT(*) FROM offerte_luce").fetchone()[0] == 0:
        _seed_luce(c)
    if c.execute("SELECT COUNT(*) FROM offerte_gas").fetchone()[0] == 0:
        _seed_gas(c)
    if c.execute("SELECT COUNT(*) FROM indici").fetchone()[0] == 0:
        _seed_indici(c)
    c.close()

def _seed_luce(c):
    now = datetime.now().isoformat()
    rows = [
        ("enel-web",     "Enel Energia",   "Luce Web",           "VARIABILE","D2,D3,BTA,CDO",0.1823,0.1523,0.1423,0.1473,None,0.018, 72, 45, 5.0,"2026-12-31","Indicizzato PUN, sconto 5% bifuel","Libero","https://www.enel.it"),
        ("a2a-biz",      "A2A Energia",    "Smart Business",     "FISSO",    "BTA,CDO",       0.1650,0.1450,0.1350,None,  None,None,  84, 50, 4.0,"2026-06-30","PMI e condomini, fisso 12 mesi",  "Libero","https://www.a2a.eu"),
        ("a2a-casa",     "A2A Energia",    "Smart Casa",         "FISSO",    "D2,D3",         0.1670,0.1470,None,  0.1470,None,None,  72, 45, 4.0,"2026-06-30","Domestico, biorario F1/F23",      "Libero","https://www.a2a.eu"),
        ("eni-biz",      "Eni Plenitude",  "Business Verde",     "FISSO",    "BTA",           0.1720,0.1520,0.1420,None,  None,None,  96, 48, 5.0,"2026-09-30","100% rinnovabile PMI",            "Libero","https://www.plenitude.com"),
        ("eni-casa",     "Eni Plenitude",  "Casa Verde",         "FISSO",    "D2,D3",         0.1700,0.1500,None,  0.1500,None,None,  84, 46, 5.0,"2026-09-30","100% rinnovabile domestico",      "Libero","https://www.plenitude.com"),
        ("sorgenia",     "Sorgenia",       "Open Power",         "VARIABILE","D2,D3,BTA,CDO", 0.1800,0.1500,0.1400,0.1450,None,0.017, 54, 43, 4.5,"2026-12-31","Rinnovabile, app PMI, -4.5% bifuel","Libero","https://www.sorgenia.it"),
        ("wekiwi-biz",   "Wekiwi",         "PMI Digitale",       "FISSO",    "BTA",           0.1590,0.1390,0.1290,None,  None,None,  48, 40, 3.0,"2026-08-31","Solo online, PMI",               "Libero","https://www.wekiwi.it"),
        ("wekiwi-casa",  "Wekiwi",         "Casa Digitale",      "FISSO",    "D2,D3",         0.1610,0.1410,None,  0.1410,None,None,  42, 39, 3.0,"2026-08-31","Domestico, senza canone dom.",    "Libero","https://www.wekiwi.it"),
        ("illumia-biz",  "Illumia",        "Smart Business",     "FISSO",    "BTA,CDO",       0.1610,0.1410,0.1310,None,  None,None,  60, 41, 3.5,"2026-09-30","PMI assistenza 7/7",             "Libero","https://www.illumia.it"),
        ("illumia-casa", "Illumia",        "Smart Casa",         "FISSO",    "D2,D3",         0.1625,0.1425,None,  0.1425,None,None,  54, 40, 3.5,"2026-09-30","Domestico fisso 12 mesi",         "Libero","https://www.illumia.it"),
        ("edison",       "Edison Energia", "Start Famiglia",     "FISSO",    "D2,D3",         0.1630,0.1430,None,  0.1430,None,None,  66, 44, 4.0,"2026-07-31","Canone incluso 24 mesi",          "Libero","https://www.edison.it"),
        ("iren-casa",    "Iren Mercato",   "Luce Sempre",        "FISSO",    "D2,D3",         0.1645,0.1445,None,  0.1445,None,None,  60, 42, 3.5,"2026-08-31","Domestico Nord Italia",           "Libero","https://www.irenmercato.it"),
        ("octopus",      "Octopus Energy", "Energia Verde",      "VARIABILE","D2,D3,BTA,CDO", 0.1790,0.1490,0.1390,0.1440,None,0.016, 48, 41, 4.0,"2026-12-31","100% rinnovabile, app smart",    "Libero","https://www.octopusenergy.it"),
    ]
    c.executemany("""INSERT INTO offerte_luce (id,fornitore,nome,tipo,profili,prezzo_f1,prezzo_f2,prezzo_f3,prezzo_f23,prezzo_mono,spread_pun,quota_fissa,oneri_trasp,sconto_bifuel,valida_fino,note,mercato,url,attiva,inserita) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)""",
        [r+(now,) for r in rows])
    c.commit()

def _seed_gas(c):
    now = datetime.now().isoformat()
    rows = [
        ("enel-gas",    "Enel Energia",  "Gas Web",         "VARIABILE","D2,D3,BTA",0.48,0.02, 60,0.02, 5.0,"2026-12-31","PSV+spread, -5% bifuel",                "Libero","https://www.enel.it"),
        ("a2a-gas-biz", "A2A Energia",   "Gas Business",    "FISSO",    "BTA",       0.52,None, 72,0.02, 4.0,"2026-06-30","PMI fisso 12 mesi",                     "Libero","https://www.a2a.eu"),
        ("a2a-gas-casa","A2A Energia",   "Gas Smart Casa",  "FISSO",    "D2,D3",     0.50,None, 66,0.02, 4.0,"2026-06-30","Domestico CACR fisso",                  "Libero","https://www.a2a.eu"),
        ("eni-gas-biz", "Eni Plenitude", "Gas Business",    "FISSO",    "BTA",       0.50,None, 84,0.025,5.0,"2026-09-30","Sconto 5% con luce Plenitude",          "Libero","https://www.plenitude.com"),
        ("eni-gas-casa","Eni Plenitude", "Gas Casa Verde",  "FISSO",    "D2,D3",     0.49,None, 78,0.022,5.0,"2026-09-30","Domestico CO2 neutro",                  "Libero","https://www.plenitude.com"),
        ("sorgenia-gas","Sorgenia",      "Open Gas",        "VARIABILE","D2,D3,BTA", 0.47,0.019,54,0.02, 4.5,"2026-12-31","PSV+spread, -4.5% bifuel",              "Libero","https://www.sorgenia.it"),
        ("illumia-gas", "Illumia",       "Gas Smart",       "FISSO",    "D2,D3,BTA", 0.495,None,60,0.019,3.5,"2026-09-30","Online, fisso 12 mesi",                 "Libero","https://www.illumia.it"),
        ("wekiwi-gas",  "Wekiwi",        "Gas Digitale",    "FISSO",    "D2,D3,BTA", 0.488,None,48,0.018,3.0,"2026-08-31","Solo online",                           "Libero","https://www.wekiwi.it"),
        ("iren-gas",    "Iren Mercato",  "Gas Sempre",      "FISSO",    "D2,D3",     0.502,None,60,0.02, 3.5,"2026-08-31","Domestico Nord Italia",                 "Libero","https://www.irenmercato.it"),
    ]
    c.executemany("""INSERT INTO offerte_gas (id,fornitore,nome,tipo,profili,prezzo_smc,spread_psv,quota_fissa,quota_var,sconto_bifuel,valida_fino,note,mercato,url,attiva,inserita) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)""",
        [r+(now,) for r in rows])
    c.commit()

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
def gemini():
    k = os.environ.get("GEMINI_API_KEY","")
    if not k: raise HTTPException(500,"GEMINI_API_KEY non configurata")
    from google import genai
    return genai.Client(api_key=k)

def parse_json(text):
    return json.loads(text.replace("```json","").replace("```","").strip())

def mesi(d1,d2):
    try: return max(1, round((date.fromisoformat(d2)-date.fromisoformat(d1)).days/30))
    except: return 1

def pun_last(c): r=c.execute("SELECT valore FROM indici WHERE tipo='PUN' ORDER BY periodo DESC LIMIT 1").fetchone(); return r["valore"] if r else 0.113
def psv_last(c): r=c.execute("SELECT valore FROM indici WHERE tipo='PSV' ORDER BY periodo DESC LIMIT 1").fetchone(); return r["valore"] if r else 0.382

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

# ══════════════════════════════════════════════════════════════════════════════
# ANALISI PUBBLICA
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/analizza/{tipo}")
async def analizza(tipo: str, file: UploadFile = File(...), profilo: str = "D2", lead_id: Optional[str] = None):
    if tipo not in ("luce","gas"): raise HTTPException(400,"tipo deve essere luce o gas")
    if profilo not in IVA: raise HTTPException(400,"profilo non valido")
    raw = await file.read()
    if len(raw) > 15*1024*1024: raise HTTPException(400,"File troppo grande (max 15 MB)")

    from google.genai import types
    client = gemini()
    prompt = P_LUCE if tipo=="luce" else P_GAS
    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt, types.Part.from_bytes(data=raw, mime_type="application/pdf")],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        dati = parse_json(resp.text)
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, f"Errore AI: {e}")

    dg=dati.get("dati_generali",{}); dt=dati.get("dati_tecnici",{}); lc=dati.get("letture_e_consumi",{}); dc=dati.get("dettaglio_costi",{}); pf=dg.get("periodo_fatturazione") or {}
    profilo_ai = (dg.get("profilo_stimato") or profilo).upper()
    profilo_f  = profilo if profilo != "D2" else (profilo_ai if profilo_ai in IVA else "D2")
    consumo    = lc.get("consumo_totale_periodo") or lc.get("consumo_totale_smc") or 0
    unita      = "kWh" if tipo=="luce" else "Smc"
    pod_pdr    = dt.get("pod_pdr") or dt.get("pdr")
    spesa_e    = dc.get("spesa_materia_energia") or dc.get("spesa_materia_gas") or 0
    costo_u    = round(spesa_e/consumo,5) if consumo>0 else None
    bid        = str(uuid.uuid4())

    c = get_db()
    c.execute("""INSERT INTO bollette (id,tipo,profilo,nome_file,data_upload,fornitore,num_fattura,periodo_inizio,periodo_fine,scadenza,totale,mercato,pod_pdr,potenza,consumo,unita,spesa_energia,spesa_trasporto,oneri,iva,dati_json,costo_unit,lead_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (bid,tipo,profilo_f,file.filename,datetime.now().isoformat(),dg.get("fornitore"),dg.get("numero_fattura"),pf.get("inizio"),pf.get("fine"),dg.get("scadenza"),dg.get("totale_fattura"),dg.get("mercato"),pod_pdr,dt.get("potenza_impegnata"),consumo,unita,spesa_e,dc.get("trasporto_gestione_contatore") or dc.get("trasporto_distribuzione"),dc.get("oneri_sistema"),dc.get("imposte_iva"),json.dumps(dati,ensure_ascii=False),costo_u,lead_id))
    c.commit(); c.close()
    return {"bolletta_id":bid,"tipo":tipo,"profilo":profilo_f,"profilo_label":PROFILI.get(profilo_f),"dati":dati,"costo_unitario":costo_u,"unita":unita}

# ── Comparazione ────────────────────────────────────────────────────────────
@app.post("/api/compara/{bid}")
async def compara(bid: str, bifuel_id: Optional[str] = Body(None, embed=True)):
    c = get_db()
    row = c.execute("SELECT * FROM bollette WHERE id=?", (bid,)).fetchone()
    if not row: c.close(); raise HTTPException(404,"Non trovata")
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
    c.commit(); c.close()
    return {"bolletta_id":bid,"tipo":tipo,"profilo":profilo,"profilo_label":PROFILI.get(profilo),"fornitore_attuale":b.get("fornitore"),"totale_attuale":b.get("totale"),"costo_annuo_attuale":round(att_annuo,2),"periodo_mesi":m,"consumo":b.get("consumo"),"unita":b.get("unita"),"iva_perc":IVA.get(profilo,0.22)*100,"bifuel":bifuel,"pun":pun,"psv":psv,"offerte":risultati,"migliore":risultati[0] if risultati else None,"risparmio_max":round(risultati[0]["risparmio_annuo"],2) if risultati else 0}

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
        elif tot: ce=tot*(of.get("prezzo_mono") or p1 or (p1+p2+p3)/3 if (p1+p2+p3)>0 else 0)
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
async def salva_lead(payload: dict = Body(...)):
    lid = str(uuid.uuid4())
    c = get_db()
    c.execute("INSERT INTO leads (id,nome,cognome,email,telefono,tipo_richiesta,bolletta_id,consenso_privacy,consenso_marketing,data,note) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (lid, payload.get("nome"), payload.get("cognome"), payload.get("email"), payload.get("telefono"),
         payload.get("tipo","analisi"), payload.get("bolletta_id"),
         int(payload.get("consenso_privacy",False)), int(payload.get("consenso_marketing",False)),
         datetime.now().isoformat(), payload.get("note")))
    # Collega il lead alla bolletta se presente
    if payload.get("bolletta_id"):
        c.execute("UPDATE bollette SET lead_id=? WHERE id=?", (lid, payload["bolletta_id"]))
    c.commit(); c.close()
    log.info(f"Nuovo lead: {payload.get('email')}")
    return {"lead_id": lid, "saved": True}

# ══════════════════════════════════════════════════════════════════════════════
# OFFERTE — lettura pubblica
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/offerte/{tipo}")
async def offerte_pubbliche(tipo: str, profilo: Optional[str]=None):
    c = get_db()
    t = "offerte_luce" if tipo=="luce" else "offerte_gas"
    q = f"SELECT * FROM {t} WHERE attiva=1"
    p = []
    if profilo:
        q += " AND (profili LIKE ? OR profili LIKE ? OR profili LIKE ? OR profili=?)"
        p.extend([f"%{profilo}%",f"{profilo},%",f"%,{profilo}",profilo])
    rows = c.execute(q+" ORDER BY fornitore", p).fetchall(); c.close()
    return [dict(r) for r in rows]

@app.get("/api/indici")
async def indici_pubblici():
    c = get_db()
    rows = c.execute("SELECT * FROM indici ORDER BY tipo, periodo DESC").fetchall(); c.close()
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

@app.post("/api/admin/offerte/estrai-pdf", dependencies=[Depends(require_admin)])
async def estrai_offerta_pdf(file: UploadFile = File(...)):
    raw = await file.read()
    from google.genai import types
    client = gemini()
    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[P_OFFERTA, types.Part.from_bytes(data=raw, mime_type="application/pdf")]
        )
        dati = parse_json(resp.text)
        return {"dati":dati,"fonte":"pdf"}
    except Exception as e: raise HTTPException(500,f"Errore AI: {e}")

@app.post("/api/admin/offerte/estrai-url", dependencies=[Depends(require_admin)])
async def estrai_offerta_url(url: str = Body(..., embed=True)):
    try:
        async with httpx.AsyncClient(timeout=15,follow_redirects=True,headers={"User-Agent":"Mozilla/5.0"}) as hc:
            r = await hc.get(url); html=r.text
        text = re.sub(r'<[^>]+>',' ',html); text=re.sub(r'\s+',' ',text).strip()[:8000]
        client = gemini()
        resp = client.models.generate_content(model="gemini-2.5-flash",contents=[P_OFFERTA+f"\n\nContenuto pagina:\n{text}"])
        dati = parse_json(resp.text)
        return {"dati":dati,"fonte":"url"}
    except HTTPException: raise
    except Exception as e: raise HTTPException(500,f"Errore: {e}")

# Indici admin
@app.post("/api/admin/indici/aggiorna", dependencies=[Depends(require_admin)])
async def aggiorna_indici():
    import asyncio
    asyncio.create_task(_fetch_indici())
    return {"message":"Aggiornamento avviato"}

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

async def _fetch_indici():
    try:
        async with httpx.AsyncClient(timeout=20,follow_redirects=True) as hc:
            r = await hc.get("https://www.ilportaleofferte.it/portaleOfferte/rest/prezziStoriciIndici")
            data = r.json()
        c = get_db(); count=0
        for e in data:
            tipo=(e.get("codiceIndice") or "").upper()
            mese=e.get("meseAnno",""); v=e.get("prezzoMedio")
            if tipo not in ("PUN","PSV","CMEM") or not mese or v is None: continue
            parts=mese.split("/")
            if len(parts)!=2: continue
            periodo=f"{parts[1]}-{parts[0].zfill(2)}"; iid=f"{tipo.lower()}-{periodo}"
            c.execute("INSERT OR REPLACE INTO indici (id,tipo,periodo,valore,fonte,aggiornato) VALUES (?,?,?,?,'Portale ARERA',?)",(iid,tipo,periodo,float(v),datetime.now().isoformat()))
            count+=1
        c.commit(); c.close(); log.info(f"Indici aggiornati: {count}")
    except Exception as e: log.error(f"Errore indici: {e}")

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
