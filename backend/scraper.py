"""
scraper.py — Scraping robusto offerte luce/gas
==============================================
Chiamato da main.py via endpoint admin:
  POST /api/admin/scraper/run          → esegue subito (background)
  GET  /api/admin/scraper/status       → ultimo run, offerte trovate, errori
  POST /api/admin/scraper/schedule     → abilita/disabilita run automatico (ogni N ore)

Architettura a 3 livelli:
  TIER 1: ARERA Portale Offerte REST API  — ufficiale, strutturato, 0 AI
  TIER 2: JSON-LD / structured data       — estratto direttamente dall'HTML
  TIER 3: Gemini AI extraction            — solo su pagine con contenuto reale

RIMOSSO: Selectra, SosTariffe, Facile.it — sono SPA React/Vue.
httpx ottiene solo HTML skeleton vuoto → Gemini riceve testo inutile.
"""

import asyncio
import json
import logging
import os
import re
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
    "auto_ogni_ore": 0,
    "_scheduler_task": None,
    "fonti_consecutive_fallite": 0,
}

ALERT_FONTI_CONSECUTIVE = int(os.environ.get("SCRAPER_ALERT_THRESHOLD", "3"))

# ── Singleton Gemini client ────────────────────────────────────────────────
_gemini_client: "genai.Client | None" = None

def _get_gemini_client(api_key: str) -> "genai.Client":
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


# ══════════════════════════════════════════════════════════════════════════════
# TIER 1 — ARERA PORTALE OFFERTE (fonte ufficiale, REST API)
# ══════════════════════════════════════════════════════════════════════════════

ARERA_BASE = "https://www.ilportaleofferte.it/portaleOfferte/rest"

# Segmenti ARERA → profili nostri
_ARERA_SEG_LUCE = {
    "D2": "D2",    # Domestico residente
    "D3": "D3",    # Domestico non residente
    "BT": "BTA",   # Non domestico / PMI
}
_ARERA_SEG_GAS = {
    "D2": "D2",
    "D3": "D3",
    "BT": "BTA",
}

async def _arera_fetch(tipo: str) -> list[dict]:
    """
    Chiama ARERA portale offerte e ritorna lista di offerte normalizzate.
    tipo: "luce" o "gas"
    """
    tipo_arera = "EE" if tipo == "luce" else "GN"
    offerte_out: list[dict] = []

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True,
                                     headers={"Accept": "application/json",
                                              "User-Agent": "Mozilla/5.0"}) as hc:

            # Endpoint che sicuramente esiste per i prezzi di riferimento
            # Proviamo anche l'endpoint offerte pubbliche
            endpoints_da_provare = [
                f"{ARERA_BASE}/offertePubblicheVendita",
                f"{ARERA_BASE}/offerte",
            ]

            raw_offerte = []
            for endpoint in endpoints_da_provare:
                try:
                    # Prova prima GET senza parametri
                    r = await hc.get(endpoint, params={"tipoFornitura": tipo_arera})
                    if r.status_code == 200:
                        data = r.json()
                        if isinstance(data, list) and len(data) > 0:
                            raw_offerte = data
                            log.info(f"ARERA API ({endpoint}): {len(raw_offerte)} offerte {tipo}")
                            break
                        elif isinstance(data, dict) and data.get("offerte"):
                            raw_offerte = data["offerte"]
                            log.info(f"ARERA API ({endpoint}): {len(raw_offerte)} offerte {tipo}")
                            break
                    # Prova POST
                    r2 = await hc.post(endpoint, json={"tipoFornitura": tipo_arera},
                                       headers={"Content-Type": "application/json"})
                    if r2.status_code == 200:
                        data = r2.json()
                        if isinstance(data, list) and len(data) > 0:
                            raw_offerte = data
                            log.info(f"ARERA API POST ({endpoint}): {len(raw_offerte)} offerte {tipo}")
                            break
                except Exception as e:
                    log.debug(f"ARERA endpoint {endpoint} fallito: {e}")
                    continue

            if not raw_offerte:
                log.info(f"ARERA API: nessun dato trovato per {tipo} (endpoint non disponibili)")
                return []

            # Normalizza campi ARERA → schema nostro
            for o in raw_offerte:
                try:
                    offerta = _normalizza_arera(o, tipo)
                    if offerta:
                        offerte_out.append(offerta)
                except Exception as e:
                    log.debug(f"Normalizzazione ARERA fallita: {e} — {o}")
                    continue

    except Exception as e:
        log.warning(f"ARERA fetch fallito per {tipo}: {e}")

    return offerte_out


def _normalizza_arera(o: dict, tipo: str) -> dict | None:
    """Mappa un record ARERA al nostro schema DB."""
    # Campi possibili ARERA (naming varia tra versioni API)
    fornitore = (
        o.get("ragioneSocialeForn") or o.get("fornitore") or
        o.get("denominazioneForn") or o.get("nomeFornitore") or ""
    ).strip()
    nome = (
        o.get("denominazioneOfferta") or o.get("nomeOfferta") or
        o.get("nome") or o.get("descrizioneOfferta") or ""
    ).strip()

    if not fornitore or not nome:
        return None

    tipo_prezzo = "FISSO"
    tp_raw = str(o.get("tipoOfferta") or o.get("tipologiaOfferta") or "").upper()
    if "VAR" in tp_raw or "INDIC" in tp_raw or "PUN" in tp_raw or "PSV" in tp_raw:
        tipo_prezzo = "VARIABILE"

    segmento = str(o.get("segmento") or o.get("tipoCliente") or "D2").upper()
    profili = _ARERA_SEG_LUCE.get(segmento, "D2,D3") if tipo == "luce" else _ARERA_SEG_GAS.get(segmento, "D2,D3")

    valida_fino = o.get("dataFineOfferta") or o.get("scadenzaOfferta") or o.get("validaFino")

    if tipo == "luce":
        # Prezzi luce: ARERA usa €/kWh
        p_f1   = _to_float(o.get("prezzoF1") or o.get("prezzo_f1") or o.get("prezzoEE") or o.get("prezzoEnergia"))
        p_f2   = _to_float(o.get("prezzoF2") or o.get("prezzo_f2"))
        p_f3   = _to_float(o.get("prezzoF3") or o.get("prezzo_f3"))
        p_f23  = _to_float(o.get("prezzoF23") or o.get("prezzo_f23"))
        p_mono = _to_float(o.get("prezzoMonorario") or o.get("prezzo_mono") or o.get("prezzoUnico"))
        spread = _to_float(o.get("spreadPUN") or o.get("spread_pun"))
        qfissa = _to_float(o.get("quotaFissaAnnua") or o.get("quotaFissa") or o.get("quota_fissa"))
        # ARERA esprime QF in €/anno, noi in €/anno (ma mettiamo /12*12 per consistenza)
        # Controlla range plausibilità
        prezzo_max = max(p_f1 or 0, p_mono or 0, spread or 0)
        if tipo_prezzo == "FISSO" and prezzo_max < 0.01:
            return None
        return {
            "fornitore": fornitore, "nome": nome,
            "tipo_prezzo": tipo_prezzo, "profili": profili,
            "prezzo_f1": p_f1, "prezzo_f2": p_f2, "prezzo_f3": p_f3,
            "prezzo_f23": p_f23, "prezzo_mono": p_mono, "spread_pun": spread,
            "quota_fissa": qfissa or 0, "sconto_bifuel": 0,
            "valida_fino": valida_fino, "mercato": "Libero",
            "url": o.get("urlOfferta") or o.get("url"),
            "note": o.get("note") or o.get("descrizione"),
        }
    else:  # gas
        p_smc = _to_float(o.get("prezzoSmc") or o.get("prezzo_smc") or o.get("prezzoGN") or o.get("prezzoEnergia"))
        spread = _to_float(o.get("spreadPSV") or o.get("spread_psv"))
        qfissa = _to_float(o.get("quotaFissaAnnua") or o.get("quotaFissa") or o.get("quota_fissa"))
        prezzo_max = max(p_smc or 0, spread or 0)
        if tipo_prezzo == "FISSO" and prezzo_max < 0.05:
            return None
        return {
            "fornitore": fornitore, "nome": nome,
            "tipo_prezzo": tipo_prezzo, "profili": profili,
            "prezzo_smc": p_smc, "spread_psv": spread,
            "quota_fissa": qfissa or 0, "quota_var": 0, "sconto_bifuel": 0,
            "valida_fino": valida_fino, "mercato": "Libero",
            "url": o.get("urlOfferta") or o.get("url"),
            "note": o.get("note") or o.get("descrizione"),
        }


def _to_float(v) -> float | None:
    """Converte valore ARERA in float, None se non convertibile."""
    if v is None:
        return None
    try:
        f = float(str(v).replace(",", ".").strip())
        return f if f > 0 else None
    except (ValueError, TypeError):
        return None


# ══════════════════════════════════════════════════════════════════════════════
# TIER 2 — JSON-LD / STRUCTURED DATA DA PAGINE PROVIDER
# ══════════════════════════════════════════════════════════════════════════════

async def _fetch_page(url: str, timeout: int = 25) -> str | None:
    """
    Scarica la pagina. Ritorna HTML grezzo (non ancora pulito).
    Usa headers realistici per evitare ban immediati.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
    }
    try:
        async with httpx.AsyncClient(
            headers=headers, follow_redirects=True,
            timeout=timeout, verify=False,
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.text
    except Exception as e:
        log.warning(f"Fetch fallito {url}: {e}")
        return None


def _estrai_json_ld(html: str) -> list[dict]:
    """
    Estrae tutti i blocchi JSON-LD dalla pagina.
    Molti provider embed dati strutturati qui (Product, Offer, etc.).
    """
    risultati = []
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE
    )
    for m in pattern.finditer(html):
        try:
            data = json.loads(m.group(1).strip())
            if isinstance(data, list):
                risultati.extend(data)
            else:
                risultati.append(data)
        except json.JSONDecodeError:
            continue
    return risultati


def _json_ld_to_offerta(ld: dict, fornitore_default: str, tipo: str, url: str) -> dict | None:
    """
    Prova a mappare un blocco JSON-LD schema.org a un'offerta energetica.
    Supporta: Product, Offer, Service.
    """
    tp = str(ld.get("@type", "")).lower()
    if not any(t in tp for t in ("product", "offer", "service")):
        return None

    nome = ld.get("name") or ld.get("description")
    if not nome:
        return None
    nome = str(nome).strip()[:100]

    fornitore = fornitore_default
    if ld.get("brand"):
        brand = ld["brand"]
        if isinstance(brand, dict):
            fornitore = brand.get("name", fornitore)
        elif isinstance(brand, str):
            fornitore = brand

    # Prezzo da offers embedded
    prezzo_val = None
    offers = ld.get("offers")
    if offers:
        if isinstance(offers, dict):
            offers = [offers]
        for off in (offers or []):
            p = off.get("price") or off.get("lowPrice")
            if p is not None:
                prezzo_val = _to_float(p)
                break

    # Prezzo diretto
    if prezzo_val is None:
        prezzo_val = _to_float(ld.get("price"))

    if prezzo_val is None or prezzo_val <= 0:
        return None

    if tipo == "luce":
        # Range plausibile kWh
        if not (0.01 < prezzo_val < 1.5):
            return None
        return {
            "fornitore": fornitore, "nome": nome,
            "tipo_prezzo": "FISSO", "profili": "D2,D3",
            "prezzo_f1": None, "prezzo_f2": None, "prezzo_f3": None,
            "prezzo_f23": None, "prezzo_mono": prezzo_val, "spread_pun": None,
            "quota_fissa": 0, "sconto_bifuel": 0,
            "valida_fino": None, "mercato": "Libero", "url": url, "note": None,
        }
    else:
        if not (0.05 < prezzo_val < 5.0):
            return None
        return {
            "fornitore": fornitore, "nome": nome,
            "tipo_prezzo": "FISSO", "profili": "D2,D3",
            "prezzo_smc": prezzo_val, "spread_psv": None,
            "quota_fissa": 0, "quota_var": 0, "sconto_bifuel": 0,
            "valida_fino": None, "mercato": "Libero", "url": url, "note": None,
        }


# ══════════════════════════════════════════════════════════════════════════════
# TIER 3 — GEMINI AI EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

PROMPT_ESTRAZIONE = """Sei un esperto di tariffe energetiche italiane. Analizza il testo di questa pagina web
e restituisci SOLO un JSON valido con le offerte trovate. Nessun markdown, nessun testo extra.

Schema JSON richiesto:
{{
  "offerte": [
    {{
      "fornitore": "Nome fornitore",
      "nome": "Nome offerta",
      "tipo_prezzo": "FISSO" o "VARIABILE",
      "profili": "D2,D3" o "BTA" o "D2,D3,BTA,CDO",
      {campi_tipo}
      "quota_fissa": 0.0,
      "sconto_bifuel": 0.0,
      "valida_fino": "YYYY-MM-DD o null",
      "note": "note brevi o null",
      "mercato": "Libero",
      "url": null
    }}
  ]
}}

{istruzioni_tipo}

Regole IMPORTANTI:
- Includi SOLO offerte con prezzi ESPLICITI e NUMERICI nella pagina
- Se non ci sono prezzi espliciti, rispondi {{"offerte": []}}
- Prezzi energia in €/kWh (luce) o €/Smc (gas), NON in centesimi
- quota_fissa in €/anno (o €/mese × 12)
- Massimo 8 offerte, le più complete

Testo pagina da analizzare:
{testo}
"""

CAMPI_LUCE = '"prezzo_f1": null, "prezzo_f2": null, "prezzo_f3": null, "prezzo_f23": null, "prezzo_mono": null, "spread_pun": null,'
ISTRUZIONI_LUCE = """Per LUCE:
- prezzo_f1/f2/f3/f23 in €/kWh (offerte multi-fascia)
- prezzo_mono in €/kWh (offerte monoraria o prezzo unico)
- spread_pun in €/kWh (offerte indicizzate PUN, es. PUN+0.015)
- Uno solo tra prezzo_mono, prezzo_f1, spread_pun deve essere non-null"""

CAMPI_GAS = '"prezzo_smc": null, "spread_psv": null, "quota_var": null,'
ISTRUZIONI_GAS = """Per GAS:
- prezzo_smc in €/Smc (offerte a prezzo fisso, tipicamente 0.3–1.5)
- spread_psv in €/Smc (offerte indicizzate PSV, tipicamente 0.01–0.10)
- quota_var in €/Smc (quota variabile aggiuntiva, spesso 0)"""


def _pulisci_html(html: str) -> str:
    """
    Rimuove tag HTML inutili, mantiene il testo con struttura leggibile.
    Conserva il contenuto dei tag <script type="application/ld+json"> prima di eliminarli.
    """
    # Rimuovi script (tranne ld+json già estratti separatamente)
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<svg[^>]*>.*?</svg>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
    # Converti tag comuni in newline per preservare struttura
    html = re.sub(r"<(?:br|p|div|li|tr|h[1-6])[^>]*>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;", " ", html)
    html = re.sub(r"&[a-z]+;", " ", html)
    html = re.sub(r"[ \t]{2,}", " ", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


def _ha_contenuto_prezzi(testo: str, tipo: str) -> bool:
    """
    Verifica che la pagina abbia effettivamente contenuto con prezzi.
    Evita chiamate Gemini su pagine vuote/skeleton SPA.
    """
    if len(testo) < 300:
        return False
    # Cerca pattern tipici di prezzi energetici italiani
    if tipo == "luce":
        patterns = [r"\d+[,.]\d+\s*€?/\s*k[Ww][Hh]", r"0[,.]\d{2,4}\s*€", r"cent[eiimo]+/k[Ww][Hh]",
                    r"prezzo\s+(?:f1|monorario|unico)", r"(?:offerta|tariffa)\s+luce", r"kWh"]
    else:
        patterns = [r"\d+[,.]\d+\s*€?/\s*[Ss]mc", r"0[,.]\d{2,4}\s*€",
                    r"prezzo\s+(?:gas|smc)", r"(?:offerta|tariffa)\s+gas", r"[Ss]mc"]
    return sum(1 for p in patterns if re.search(p, testo, re.IGNORECASE)) >= 2


async def _estrai_con_gemini(tipo: str, testo: str, api_key: str) -> list[dict]:
    """
    Usa Gemini per estrarre offerte strutturate dal testo pulito.
    Gestisce gracefully: quota esaurita, risposta vuota, JSON malformato.
    """
    if not _ha_contenuto_prezzi(testo, tipo):
        log.debug(f"Gemini skip: testo ({len(testo)} chars) non contiene prezzi energia")
        return []

    prompt_tmpl = PROMPT_ESTRAZIONE.format(
        campi_tipo=CAMPI_LUCE if tipo == "luce" else CAMPI_GAS,
        istruzioni_tipo=ISTRUZIONI_LUCE if tipo == "luce" else ISTRUZIONI_GAS,
        testo=testo[:20000],  # limite context
    )

    try:
        client = _get_gemini_client(api_key)
        resp = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.0-flash",
            contents=prompt_tmpl,
            config=gtypes.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=4096,
            ),
        )
        raw = (resp.text or "").strip()
        if not raw:
            log.warning("Gemini ha restituito risposta vuota")
            return []
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        offerte = data.get("offerte", [])
        log.info(f"Gemini estratte {len(offerte)} offerte ({tipo})")
        return offerte

    except json.JSONDecodeError as e:
        log.warning(f"Gemini JSON non valido: {e}")
        return []
    except Exception as e:
        err_str = str(e).lower()
        if "quota" in err_str or "resource_exhausted" in err_str or "429" in err_str:
            log.error(f"Gemini quota esaurita: {e}")
            raise  # Blocca il ciclo per non sprecare chiamate
        log.warning(f"Gemini estrazione fallita: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# VALIDAZIONE
# ══════════════════════════════════════════════════════════════════════════════

def _valida_luce(o: dict) -> bool:
    fornitore = str(o.get("fornitore", "")).strip()
    nome = str(o.get("nome", "")).strip()
    if not fornitore or not nome or len(fornitore) > 80 or len(nome) > 120:
        return False
    prezzi = [
        _to_float(o.get("prezzo_f1")), _to_float(o.get("prezzo_mono")),
        _to_float(o.get("spread_pun")),
    ]
    max_p = max((p for p in prezzi if p), default=0)
    return 0.005 < max_p < 2.0


def _valida_gas(o: dict) -> bool:
    fornitore = str(o.get("fornitore", "")).strip()
    nome = str(o.get("nome", "")).strip()
    if not fornitore or not nome or len(fornitore) > 80 or len(nome) > 120:
        return False
    prezzi = [_to_float(o.get("prezzo_smc")), _to_float(o.get("spread_psv"))]
    max_p = max((p for p in prezzi if p), default=0)
    return 0.05 < max_p < 5.0


def _offerta_id(fornitore: str, nome: str) -> str:
    slug = re.sub(r"[^a-z0-9]", "-", f"{fornitore}-{nome}".lower())
    return re.sub(r"-+", "-", slug).strip("-")[:60]


# ══════════════════════════════════════════════════════════════════════════════
# SALVATAGGIO NEL DB
# ══════════════════════════════════════════════════════════════════════════════

def _salva_offerte(offerte: list[dict], tipo: str, get_db) -> tuple[int, int]:
    """Inserisce o aggiorna offerte nel DB. Ritorna (inserite, aggiornate)."""
    inserite = aggiornate = 0
    ora = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    try:
        for o in offerte:
            oid = _offerta_id(o["fornitore"], o["nome"])
            esiste = conn.execute(
                f"SELECT id FROM offerte_{tipo} WHERE id=?", (oid,)
            ).fetchone()

            if tipo == "luce":
                if not _valida_luce(o):
                    continue
                vals = (
                    oid,
                    str(o.get("fornitore", ""))[:80],
                    str(o.get("nome", ""))[:120],
                    o.get("tipo_prezzo", "FISSO"),
                    o.get("profili", "D2,D3"),
                    _to_float(o.get("prezzo_f1")) or 0.0,
                    _to_float(o.get("prezzo_f2")) or 0.0,
                    _to_float(o.get("prezzo_f3")) or 0.0,
                    _to_float(o.get("prezzo_f23")) or 0.0,
                    _to_float(o.get("prezzo_mono")) or 0.0,
                    _to_float(o.get("spread_pun")) or 0.0,
                    _to_float(o.get("quota_fissa")) or 0.0,
                    0.0,  # oneri_trasp (ARERA non lo fornisce separatamente)
                    _to_float(o.get("sconto_bifuel")) or 0.0,
                    o.get("valida_fino"),
                    (o.get("note") or "")[:200] or None,
                    o.get("mercato", "Libero"),
                    o.get("url"),
                    ora,
                )
                if esiste:
                    conn.execute("""
                        UPDATE offerte_luce SET
                          fornitore=?,nome=?,tipo=?,profili=?,
                          prezzo_f1=?,prezzo_f2=?,prezzo_f3=?,prezzo_f23=?,prezzo_mono=?,
                          spread_pun=?,quota_fissa=?,oneri_trasp=?,sconto_bifuel=?,
                          valida_fino=?,note=?,mercato=?,url=?,inserita=?,attiva=1
                        WHERE id=?
                    """, vals[1:] + (oid,))
                    aggiornate += 1
                else:
                    conn.execute("""INSERT INTO offerte_luce
                        (id,fornitore,nome,tipo,profili,
                         prezzo_f1,prezzo_f2,prezzo_f3,prezzo_f23,prezzo_mono,
                         spread_pun,quota_fissa,oneri_trasp,sconto_bifuel,
                         valida_fino,note,mercato,url,attiva,inserita)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)
                    """, vals)
                    inserite += 1

            else:  # gas
                if not _valida_gas(o):
                    continue
                vals = (
                    oid,
                    str(o.get("fornitore", ""))[:80],
                    str(o.get("nome", ""))[:120],
                    o.get("tipo_prezzo", "FISSO"),
                    o.get("profili", "D2,D3"),
                    _to_float(o.get("prezzo_smc")) or 0.0,
                    _to_float(o.get("spread_psv")) or 0.0,
                    _to_float(o.get("quota_fissa")) or 0.0,
                    _to_float(o.get("quota_var")) or 0.0,
                    _to_float(o.get("sconto_bifuel")) or 0.0,
                    o.get("valida_fino"),
                    (o.get("note") or "")[:200] or None,
                    o.get("mercato", "Libero"),
                    o.get("url"),
                    ora,
                )
                if esiste:
                    conn.execute("""
                        UPDATE offerte_gas SET
                          fornitore=?,nome=?,tipo=?,profili=?,
                          prezzo_smc=?,spread_psv=?,quota_fissa=?,quota_var=?,sconto_bifuel=?,
                          valida_fino=?,note=?,mercato=?,url=?,inserita=?,attiva=1
                        WHERE id=?
                    """, vals[1:] + (oid,))
                    aggiornate += 1
                else:
                    conn.execute("""INSERT INTO offerte_gas
                        (id,fornitore,nome,tipo,profili,
                         prezzo_smc,spread_psv,quota_fissa,quota_var,sconto_bifuel,
                         valida_fino,note,mercato,url,attiva,inserita)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)
                    """, vals)
                    inserite += 1

        conn.commit()
    finally:
        conn.close()

    return inserite, aggiornate


# ══════════════════════════════════════════════════════════════════════════════
# FONTI PROVIDER DIRETTI (siti con HTML statico o parzialmente statico)
# ══════════════════════════════════════════════════════════════════════════════
# Sono inclusi SOLO provider con pagine che NON sono full-SPA React/Angular.
# Usiamo Tier 2 (JSON-LD) o Tier 3 (Gemini su HTML reale) a seconda del contenuto.

FORNITORI_DIRETTI = [
    # Wekiwi: sito relativamente semplice
    {"nome": "Wekiwi",          "tipo": "luce", "url": "https://www.wekiwi.it/luce-gas/offerte-luce/"},
    {"nome": "Wekiwi",          "tipo": "gas",  "url": "https://www.wekiwi.it/luce-gas/offerte-gas/"},
    # Pulsee
    {"nome": "Pulsee",          "tipo": "luce", "url": "https://www.pulsee.it/offerte"},
    # Illumia
    {"nome": "Illumia",         "tipo": "luce", "url": "https://www.illumia.it/offerte-luce/"},
    {"nome": "Illumia",         "tipo": "gas",  "url": "https://www.illumia.it/offerte-gas/"},
    # Acea
    {"nome": "Acea Energia",    "tipo": "luce", "url": "https://www.aceaenergia.it/offerte/luce"},
    {"nome": "Acea Energia",    "tipo": "gas",  "url": "https://www.aceaenergia.it/offerte/gas"},
    # Duferco
    {"nome": "Duferco Energia", "tipo": "luce", "url": "https://www.dufercoenergia.com/offerte/"},
    # Sorgenia (ha pagine con prezzi visibili)
    {"nome": "Sorgenia",        "tipo": "luce", "url": "https://www.sorgenia.it/offerte-luce"},
    {"nome": "Sorgenia",        "tipo": "gas",  "url": "https://www.sorgenia.it/offerte-gas"},
]


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
    _stato["fonti_consecutive_fallite"] = 0
    inserite_tot = aggiornate_tot = 0

    def logga(msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        riga = f"[{ts}] {msg}"
        _stato["log"].append(riga)
        log.info(msg)

    def registra_errore(nome: str, motivo: str):
        _stato["fonti_consecutive_fallite"] += 1
        msg = f"  ✗ {nome}: {motivo}"
        logga(msg)
        _stato["errori"].append(msg)
        n = _stato["fonti_consecutive_fallite"]
        if n >= ALERT_FONTI_CONSECUTIVE:
            log.error(
                f"🚨 ALERT SCRAPER: {n} fonti consecutive fallite "
                f"(soglia={ALERT_FONTI_CONSECUTIVE}). Verifica connettività o API."
            )

    def registra_successo():
        _stato["fonti_consecutive_fallite"] = 0

    try:
        logga("▶ Inizio scraping offerte")

        # ── TIER 1: ARERA API ─────────────────────────────────────────────
        logga("── TIER 1: ARERA Portale Offerte API ──")
        for tipo in ("luce", "gas"):
            logga(f"  ARERA {tipo.upper()}...")
            try:
                offerte_arera = await _arera_fetch(tipo)
                if offerte_arera:
                    ins, agg = _salva_offerte(offerte_arera, tipo, get_db)
                    inserite_tot += ins
                    aggiornate_tot += agg
                    logga(f"  ✓ ARERA {tipo}: {ins} nuove, {agg} aggiornate")
                    registra_successo()
                else:
                    logga(f"  ℹ ARERA {tipo}: API non disponibile o 0 offerte")
            except Exception as e:
                registra_errore(f"ARERA {tipo}", str(e))

        # ── TIER 2 + 3: Provider diretti ─────────────────────────────────
        logga("── TIER 2+3: Provider diretti (JSON-LD + Gemini) ──")
        for f in FORNITORI_DIRETTI:
            nome = f["nome"]
            tipo = f["tipo"]
            url  = f["url"]
            logga(f"  {nome} ({tipo}) → {url}")

            html_raw = await _fetch_page(url)
            if not html_raw:
                registra_errore(nome, "Fetch HTTP fallito")
                await asyncio.sleep(1)
                continue

            offerte_found: list[dict] = []

            # Tier 2: JSON-LD
            ld_blocks = _estrai_json_ld(html_raw)
            for ld in ld_blocks:
                offerta = _json_ld_to_offerta(ld, nome, tipo, url)
                if offerta:
                    offerte_found.append(offerta)
            if offerte_found:
                logga(f"    JSON-LD: {len(offerte_found)} offerte")

            # Tier 3: Gemini su testo pulito (solo se Tier 2 vuoto)
            if not offerte_found and gemini_api_key:
                testo = _pulisci_html(html_raw)
                logga(f"    Testo pulito: {len(testo)} chars")
                try:
                    offerte_gemini = await _estrai_con_gemini(tipo, testo, gemini_api_key)
                    # Forza fornitore corretto
                    for o in offerte_gemini:
                        if not o.get("fornitore") or o["fornitore"].lower() in ("null", "none", ""):
                            o["fornitore"] = nome
                        o.setdefault("url", url)
                    offerte_found.extend(offerte_gemini)
                    if offerte_gemini:
                        logga(f"    Gemini: {len(offerte_gemini)} offerte estratte")
                    else:
                        logga(f"    Gemini: 0 offerte (pagina senza prezzi espliciti)")
                except Exception as e:
                    if "quota" in str(e).lower() or "resource_exhausted" in str(e).lower():
                        registra_errore(nome, f"Gemini quota esaurita: {e}")
                        logga("  ⛔ Gemini quota — interrompo estrazione AI")
                        # Smetti di usare Gemini ma continua con altri provider
                        gemini_api_key = ""
                    else:
                        registra_errore(nome, f"Gemini errore: {e}")

            if offerte_found:
                ins, agg = _salva_offerte(offerte_found, tipo, get_db)
                inserite_tot += ins
                aggiornate_tot += agg
                logga(f"  ✓ {nome}: {ins} nuove, {agg} aggiornate")
                registra_successo()
            else:
                registra_errore(nome, "Nessuna offerta trovata (né JSON-LD né Gemini)")

            await asyncio.sleep(2)  # Pausa cortesia

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
        "in_corso":           _stato["in_corso"],
        "ultimo_run":         _stato["ultimo_run"],
        "offerte_trovate":    _stato["offerte_trovate"],
        "offerte_inserite":   _stato["offerte_inserite"],
        "offerte_aggiornate": _stato["offerte_aggiornate"],
        "errori":             _stato["errori"],
        "log":                _stato["log"][-50:],
        "auto_ogni_ore":      _stato["auto_ogni_ore"],
        "fonti_consecutive_fallite": _stato["fonti_consecutive_fallite"],
    }
