"""
scraper.py — Scraping automatico offerte luce/gas
=================================================
Chiamato da main.py via endpoint admin:
  POST /api/admin/scraper/run          → esegue subito (background)
  GET  /api/admin/scraper/status       → ultimo run, offerte trovate, errori
  POST /api/admin/scraper/schedule     → abilita/disabilita run automatico (ogni N ore)

Fonti scraping (in ordine di affidabilità):
  1. Selectra      — comparatore IT con dati strutturati
  2. SosTariffe    — comparatore ARERA-accreditato
  3. Facile.it     → energia (fallback)
  4. Siti diretti  — Acea, Duferco, Energiasi, Union (parsing semplificato)

Il modulo usa httpx + Google Gemini per estrarre i dati tariffari
dal testo HTML grezzo: non è fragile agli aggiornamenti del DOM.
"""

import asyncio
import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from google import genai
from google.genai import types as gtypes

log = logging.getLogger("scraper")

# ── Stato condiviso (in-memory, non persistito) ────────────────────────────
_stato: dict[str, Any] = {
    "ultimo_run": None,
    "in_corso": False,
    "offerte_trovate": 0,
    "offerte_inserite": 0,
    "offerte_aggiornate": 0,
    "errori": [],
    "log": [],
    "auto_ogni_ore": 0,       # 0 = disabilitato
    "_scheduler_task": None,
}

# ── URL sorgenti ───────────────────────────────────────────────────────────
FONTI_LUCE = [
    {
        "nome": "Selectra Luce",
        "url": "https://selectra.info/energia/offerte-luce",
        "priorita": 1,
    },
    {
        "nome": "SosTariffe Luce",
        "url": "https://www.sostariffe.it/energia/offerte-luce/",
        "priorita": 2,
    },
    {
        "nome": "Facile Luce",
        "url": "https://www.facile.it/luce-gas/offerte-luce.html",
        "priorita": 3,
    },
]

FONTI_GAS = [
    {
        "nome": "Selectra Gas",
        "url": "https://selectra.info/gas/offerte-gas",
        "priorita": 1,
    },
    {
        "nome": "SosTariffe Gas",
        "url": "https://www.sostariffe.it/gas/offerte-gas/",
        "priorita": 2,
    },
    {
        "nome": "Facile Gas",
        "url": "https://www.facile.it/luce-gas/offerte-gas.html",
        "priorita": 3,
    },
]

# ── Siti diretti fornitori partner ────────────────────────────────────────
FORNITORI_DIRETTI = [
    {"nome": "Acea",    "tipo": "luce", "url": "https://www.aceaenergia.it/offerte/luce"},
    {"nome": "Acea",    "tipo": "gas",  "url": "https://www.aceaenergia.it/offerte/gas"},
    {"nome": "Duferco", "tipo": "luce", "url": "https://www.dufercoenergia.com/offerte/luce"},
    {"nome": "Duferco", "tipo": "gas",  "url": "https://www.dufercoenergia.com/offerte/gas"},
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

PROMPT_ESTRAZIONE = """
Sei un esperto di tariffe energetiche italiane. Analizza il testo HTML di una pagina web
di comparazione offerte luce/gas e restituisci SOLO un JSON valido, senza markdown, 
senza spiegazioni, senza testo fuori dal JSON.

Il JSON deve avere questa struttura esatta:
{{
  "tipo": "{tipo}",
  "offerte": [
    {{
      "fornitore": "Nome fornitore",
      "nome": "Nome offerta",
      "tipo_prezzo": "FISSO" oppure "VARIABILE",
      "profili": "D2,D3",
      {campi_tipo}
      "quota_fissa": 0.0,
      "sconto_bifuel": 0.0,
      "valida_fino": "YYYY-MM-DD oppure null",
      "note": "note brevi o null",
      "mercato": "Libero",
      "url": "url della pagina o null"
    }}
  ]
}}

{istruzioni_tipo}

Regole:
- Includi SOLO offerte con prezzi espliciti e verificabili
- Se un prezzo non è presente, ometti l'offerta
- quota_fissa in €/mese, prezzi energia in €/kWh o €/Smc
- Se non trovi offerte valide rispondi: {{"tipo": "{tipo}", "offerte": []}}
- Massimo 10 offerte per pagina, le più rappresentative e recenti

HTML da analizzare (estratto rilevante):
{html}
"""

CAMPI_LUCE = '"prezzo_f1": 0.0, "prezzo_mono": 0.0, "spread_pun": 0.0,'
ISTRUZIONI_LUCE = """Per offerte LUCE:
- prezzo_f1/f2/f3 in €/kWh per offerte monorarie/multiorarie
- prezzo_mono in €/kWh per offerte a prezzo unico
- spread_pun in €/kWh per offerte indicizzate PUN (es. PUN+0.02)
- Solo uno dei due tra prezzo_mono e prezzo_f1 deve essere > 0"""

CAMPI_GAS = '"prezzo_smc": 0.0, "spread_psv": 0.0,'
ISTRUZIONI_GAS = """Per offerte GAS:
- prezzo_smc in €/Smc per offerte a prezzo fisso
- spread_psv in €/Smc per offerte indicizzate PSV (es. PSV+0.05)
- quota_var in €/Smc eventuale quota variabile aggiuntiva"""


# ══════════════════════════════════════════════════════════════════════════════
# FETCH + CLEAN HTML
# ══════════════════════════════════════════════════════════════════════════════

async def _fetch_html(url: str, timeout: int = 20) -> str | None:
    """Scarica la pagina e pulisce l'HTML dai tag non utili."""
    try:
        async with httpx.AsyncClient(
            headers=HEADERS,
            follow_redirects=True,
            timeout=timeout,
            verify=False,           # alcuni siti hanno cert scaduti
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
            html = r.text
    except Exception as e:
        log.warning(f"Fetch fallito {url}: {e}")
        return None

    # Rimuovi script, stili, svg, commenti — mantieni solo testo utile
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<svg[^>]*>.*?</svg>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
    html = re.sub(r"<[^>]+>", " ", html)                       # strip tag restanti
    html = re.sub(r"\s{3,}", "  ", html)                       # normalizza spazi
    # Tronca: Gemini ha limite context, prendiamo i 18k chars più rilevanti
    # Cerca la sezione con i prezzi
    idx = html.lower().find("offert")
    if idx > 2000:
        html = html[max(0, idx - 500):]
    return html[:18000]


# ══════════════════════════════════════════════════════════════════════════════
# ESTRAZIONE CON GEMINI
# ══════════════════════════════════════════════════════════════════════════════

def _build_prompt(tipo: str, html: str) -> str:
    if tipo == "luce":
        return PROMPT_ESTRAZIONE.format(
            tipo=tipo,
            campi_tipo=CAMPI_LUCE,
            istruzioni_tipo=ISTRUZIONI_LUCE,
            html=html,
        )
    return PROMPT_ESTRAZIONE.format(
        tipo=tipo,
        campi_tipo=CAMPI_GAS,
        istruzioni_tipo=ISTRUZIONI_GAS,
        html=html,
    )


async def _estrai_con_gemini(tipo: str, html: str, api_key: str) -> list[dict]:
    """Usa Gemini per estrarre offerte strutturate dall'HTML."""
    try:
        client = genai.Client(api_key=api_key)
        prompt = _build_prompt(tipo, html)
        resp = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.0-flash",
            contents=prompt,
            config=gtypes.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=4000,
            ),
        )
        raw = resp.text.strip()
        # Rimuovi eventuale markdown
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        return data.get("offerte", [])
    except Exception as e:
        log.warning(f"Gemini estrazione fallita: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# VALIDAZIONE E NORMALIZZAZIONE
# ══════════════════════════════════════════════════════════════════════════════

def _valida_offerta_luce(o: dict) -> bool:
    """True se l'offerta luce ha dati minimi credibili."""
    fornitore = str(o.get("fornitore", "")).strip()
    nome = str(o.get("nome", "")).strip()
    if not fornitore or not nome:
        return False
    f1 = float(o.get("prezzo_f1") or 0)
    mono = float(o.get("prezzo_mono") or 0)
    pun = float(o.get("spread_pun") or 0)
    # Almeno un prezzo deve essere presente e plausibile (0.03 – 0.60 €/kWh)
    prezzo = max(f1, mono, pun)
    if prezzo < 0.01 or prezzo > 1.0:
        return False
    return True


def _valida_offerta_gas(o: dict) -> bool:
    fornitore = str(o.get("fornitore", "")).strip()
    nome = str(o.get("nome", "")).strip()
    if not fornitore or not nome:
        return False
    smc = float(o.get("prezzo_smc") or 0)
    psv = float(o.get("spread_psv") or 0)
    prezzo = max(smc, psv)
    if prezzo < 0.05 or prezzo > 3.0:
        return False
    return True


def _offerta_id(fornitore: str, nome: str) -> str:
    """ID deterministico: stesso fornitore+nome → stesso ID (evita duplicati)."""
    slug = re.sub(r"[^a-z0-9]", "-", f"{fornitore}-{nome}".lower())
    slug = re.sub(r"-+", "-", slug)[:60]
    return slug


# ══════════════════════════════════════════════════════════════════════════════
# SALVATAGGIO NEL DB
# ══════════════════════════════════════════════════════════════════════════════

def _salva_offerte(offerte: list[dict], tipo: str, get_db) -> tuple[int, int]:
    """
    Inserisce o aggiorna offerte nel DB.
    Ritorna (inserite, aggiornate).
    """
    inserite = aggiornate = 0
    ora = datetime.now(timezone.utc).isoformat()

    with get_db() as c:
        for o in offerte:
            oid = _offerta_id(o["fornitore"], o["nome"])
            esiste = c.execute(
                f"SELECT id FROM offerte_{tipo} WHERE id=?", (oid,)
            ).fetchone()

            if tipo == "luce":
                if not _valida_offerta_luce(o):
                    continue
                vals = (
                    oid,
                    o.get("fornitore", ""),
                    o.get("nome", ""),
                    o.get("tipo_prezzo", "FISSO"),
                    o.get("profili", "D2,D3"),
                    float(o.get("prezzo_f1") or 0),
                    float(o.get("prezzo_f2") or 0),
                    float(o.get("prezzo_f3") or 0),
                    float(o.get("prezzo_f23") or 0),
                    float(o.get("prezzo_mono") or 0),
                    float(o.get("spread_pun") or 0),
                    float(o.get("quota_fissa") or 0),
                    float(o.get("oneri_trasp") or 0),
                    float(o.get("sconto_bifuel") or 0),
                    o.get("valida_fino"),
                    o.get("note"),
                    o.get("mercato", "Libero"),
                    o.get("url"),
                    ora,
                )
                if esiste:
                    c.execute("""
                        UPDATE offerte_luce SET
                          fornitore=?,nome=?,tipo=?,profili=?,
                          prezzo_f1=?,prezzo_f2=?,prezzo_f3=?,prezzo_f23=?,prezzo_mono=?,
                          spread_pun=?,quota_fissa=?,oneri_trasp=?,sconto_bifuel=?,
                          valida_fino=?,note=?,mercato=?,url=?,inserita=?,attiva=1
                        WHERE id=?
                    """, vals[1:] + (oid,))
                    aggiornate += 1
                else:
                    c.execute("""INSERT INTO offerte_luce
                        (id,fornitore,nome,tipo,profili,
                         prezzo_f1,prezzo_f2,prezzo_f3,prezzo_f23,prezzo_mono,
                         spread_pun,quota_fissa,oneri_trasp,sconto_bifuel,
                         valida_fino,note,mercato,url,attiva,inserita)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)
                    """, vals)
                    inserite += 1

            else:  # gas
                if not _valida_offerta_gas(o):
                    continue
                vals = (
                    oid,
                    o.get("fornitore", ""),
                    o.get("nome", ""),
                    o.get("tipo_prezzo", "FISSO"),
                    o.get("profili", "D2,D3"),
                    float(o.get("prezzo_smc") or 0),
                    float(o.get("spread_psv") or 0),
                    float(o.get("quota_fissa") or 0),
                    float(o.get("quota_var") or 0),
                    float(o.get("sconto_bifuel") or 0),
                    o.get("valida_fino"),
                    o.get("note"),
                    o.get("mercato", "Libero"),
                    o.get("url"),
                    ora,
                )
                if esiste:
                    c.execute("""
                        UPDATE offerte_gas SET
                          fornitore=?,nome=?,tipo=?,profili=?,
                          prezzo_smc=?,spread_psv=?,quota_fissa=?,quota_var=?,sconto_bifuel=?,
                          valida_fino=?,note=?,mercato=?,url=?,inserita=?,attiva=1
                        WHERE id=?
                    """, vals[1:] + (oid,))
                    aggiornate += 1
                else:
                    c.execute("""INSERT INTO offerte_gas
                        (id,fornitore,nome,tipo,profili,
                         prezzo_smc,spread_psv,quota_fissa,quota_var,sconto_bifuel,
                         valida_fino,note,mercato,url,attiva,inserita)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)
                    """, vals)
                    inserite += 1

    return inserite, aggiornate


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════════

async def esegui_scraping(get_db, gemini_api_key: str) -> dict:
    """
    Esegui il ciclo completo di scraping.
    Chiamato dall'endpoint admin o dallo scheduler.
    Ritorna un dict con statistiche del run.
    """
    if _stato["in_corso"]:
        return {"errore": "Scraping già in corso, attendere il termine."}

    _stato["in_corso"] = True
    _stato["errori"] = []
    _stato["log"] = []
    inserite_tot = aggiornate_tot = 0

    def logga(msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        riga = f"[{ts}] {msg}"
        _stato["log"].append(riga)
        log.info(msg)

    try:
        logga("▶ Inizio scraping offerte")

        # ── Ciclo su tutte le fonti ──────────────────────────────────────
        for fonti, tipo in [(FONTI_LUCE, "luce"), (FONTI_GAS, "gas")]:
            logga(f"── Tipo: {tipo.upper()} ──")
            for fonte in sorted(fonti, key=lambda x: x["priorita"]):
                logga(f"  Fetch: {fonte['nome']} → {fonte['url']}")
                html = await _fetch_html(fonte["url"])
                if not html:
                    msg = f"  ✗ Fetch fallito: {fonte['nome']}"
                    logga(msg)
                    _stato["errori"].append(msg)
                    continue

                logga(f"  HTML ok ({len(html)} chars), invio a Gemini…")
                offerte = await _estrai_con_gemini(tipo, html, gemini_api_key)
                logga(f"  Gemini: {len(offerte)} offerte estratte")

                if offerte:
                    ins, agg = _salva_offerte(offerte, tipo, get_db)
                    inserite_tot += ins
                    aggiornate_tot += agg
                    logga(f"  ✓ Salvate: {ins} nuove, {agg} aggiornate")

                # Pausa cortesia tra richieste
                await asyncio.sleep(2)

        # ── Fornitori diretti ────────────────────────────────────────────
        logga("── Fornitori diretti ──")
        for f in FORNITORI_DIRETTI:
            logga(f"  Fetch: {f['nome']} {f['tipo']} → {f['url']}")
            html = await _fetch_html(f["url"])
            if not html:
                logga(f"  ✗ Fetch fallito: {f['nome']}")
                continue
            offerte = await _estrai_con_gemini(f["tipo"], html, gemini_api_key)
            if offerte:
                # Forza il fornitore corretto (sito ufficiale = fonte certa)
                for o in offerte:
                    o["fornitore"] = f["nome"]
                    o["url"] = f["url"]
                ins, agg = _salva_offerte(offerte, f["tipo"], get_db)
                inserite_tot += ins
                aggiornate_tot += agg
                logga(f"  ✓ {f['nome']}: {ins} nuove, {agg} aggiornate")
            await asyncio.sleep(2)

        _stato["offerte_trovate"] = inserite_tot + aggiornate_tot
        _stato["offerte_inserite"] = inserite_tot
        _stato["offerte_aggiornate"] = aggiornate_tot
        logga(f"✅ Fine scraping — {inserite_tot} nuove, {aggiornate_tot} aggiornate")

    except Exception as e:
        msg = f"Errore fatale scraping: {e}"
        log.exception(msg)
        _stato["errori"].append(msg)
    finally:
        _stato["in_corso"] = False
        _stato["ultimo_run"] = datetime.now(timezone.utc).isoformat()

    return {
        "inserite": inserite_tot,
        "aggiornate": aggiornate_tot,
        "errori": _stato["errori"],
        "log": _stato["log"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# SCHEDULER AUTOMATICO
# ══════════════════════════════════════════════════════════════════════════════

async def _scheduler_loop(get_db, gemini_api_key: str, ore: int):
    """Loop interno: attende N ore, poi riesegue."""
    log.info(f"Scheduler attivo — run ogni {ore}h")
    while True:
        await asyncio.sleep(ore * 3600)
        log.info("Scheduler: avvio run automatico")
        await esegui_scraping(get_db, gemini_api_key)


def avvia_scheduler(get_db, gemini_api_key: str, ore: int):
    """Avvia (o riavvia) lo scheduler automatico."""
    if _stato["_scheduler_task"] and not _stato["_scheduler_task"].done():
        _stato["_scheduler_task"].cancel()
    if ore > 0:
        task = asyncio.create_task(_scheduler_loop(get_db, gemini_api_key, ore))
        _stato["_scheduler_task"] = task
    _stato["auto_ogni_ore"] = ore


def stato_scraper() -> dict:
    return {
        "in_corso":         _stato["in_corso"],
        "ultimo_run":       _stato["ultimo_run"],
        "offerte_trovate":  _stato["offerte_trovate"],
        "offerte_inserite": _stato["offerte_inserite"],
        "offerte_aggiornate": _stato["offerte_aggiornate"],
        "errori":           _stato["errori"],
        "log":              _stato["log"][-50:],   # ultimi 50 log
        "auto_ogni_ore":    _stato["auto_ogni_ore"],
    }
