"""
ARERA Portale Offerte — scraper XML per offerte mercato libero luce, gas e dual fuel.

URL patterns:
  Offerte:
    https://www.ilportaleofferte.it/portaleOfferte/resources/opendata/csv/offerteML/
    YYYY_M/PO_Offerte_{E|G|D}_MLIBERO_YYYYMMDD.xml

  Parametri regolatori:
    https://www.ilportaleofferte.it/portaleOfferte/resources/opendata/csv/parametriML/
    YYYY_M/PO_Parametri_Mercato_Libero_{E|G}_YYYYMMDD.csv

Strategia flush-and-fill:
  - Elimina tutte le offerte con fonte='arera'
  - Inserisce le offerte parse dall'XML con fonte='arera'
  - Le offerte manuali (fonte='manuale' o NULL) non vengono toccate

Mappatura MACROAREA (da schema ARERA):
  01 = quota fissa commerciale (€/anno)
  02 = spread PUN (€/kWh) — solo offerte luce VARIABILE
       per gas: componente variabile/sbilanciamento (€/Smc)
  04 = prezzo energia fisso (€/kWh luce, €/Smc gas) OPPURE spread PSV (€/Smc gas VARIABILE)
  06 = componente verde / extra — ignorata
  99 = altro — ignorato

TIPO_OFFERTA:
  01 = FISSO
  02 = VARIABILE (indicizzato PUN/PSV)

FASCIA_COMPONENTE:
  01=F1, 02=F2, 03=F3, 91=bioraria (F2+F3)

TIPO_CLIENTE:
  01 = domestico

DOMESTICO_RESIDENTE:
  01 = residente, 02 = non residente, 03 = entrambi

MODALITA_PAGAMENTO:
  01 = bollettino, 02 = domiciliazione, 03 = carta credito, 04 = bonifico, 99 = altro

TIPOLOGIA_CONDIZIONE:
  01 = penale recesso, 02 = deposito cauzionale, 03 = garanzia, 04 = altro
"""

import csv
import io
import json
import uuid
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

# ── Costanti ────────────────────────────────────────────────────────────────
NS = "http://www.acquirenteunico.it/schemas/SII_AU/OffertaRetail/01"

# MACROAREA
MA_QUOTA_FISSA   = "01"  # €/anno  (quota commerciale fissa)
MA_SPREAD_PUN    = "02"  # €/kWh   (spread PUN, offerte VARIABILE luce)
MA_ENERGIA_FISSO = "04"  # €/kWh luce FISSO  ||  €/Smc gas (FISSO e VARIABILE spread PSV)

# FASCIA_COMPONENTE
FASCIA_01 = "01"   # F1
FASCIA_02 = "02"   # F2
FASCIA_03 = "03"   # F3
FASCIA_91 = "91"   # bioraria F2+F3

TIPO_OFFERTA_FISSO     = "01"
TIPO_OFFERTA_VARIABILE = "02"
TIPO_CLIENTE_DOMESTICO = "01"

# ── Helpers XML ─────────────────────────────────────────────────────────────
def _tag(name: str) -> str:
    return f"{{{NS}}}{name}"

def _txt(elem, path: str, default=None):
    """Restituisce il testo di un sotto-elemento, navigando con slash."""
    cur = elem
    for p in path.split("/"):
        cur = cur.find(_tag(p))
        if cur is None:
            return default
    return (cur.text or "").strip() or default

def _vendor_name(url_offerta: str, url_sito: str) -> str:
    """Deriva il nome del fornitore dall'URL."""
    url = url_sito or url_offerta
    if not url:
        return "Fornitore ARERA"
    try:
        host = urlparse(url).netloc or url
        host = host.removeprefix("www.")
        name = host.split(".")[0].replace("-", " ").title()
        return name or "Fornitore ARERA"
    except Exception:
        return "Fornitore ARERA"

def _parse_date(raw: str | None) -> str | None:
    """Converte 'DD/MM/YYYY_HH:MM:SS' o 'DD/MM/YYYY' in 'YYYY-MM-DD'."""
    if not raw:
        return None
    try:
        part = raw.split("_")[0]
        d, m, y = part.split("/")
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    except Exception:
        return None

def _f(val) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None

# ── Helpers comuni per campi dettaglio ──────────────────────────────────────
def _extract_common(elem) -> dict:
    """Estrae i campi comuni a tutte le offerte (luce, gas, dual)."""
    cod = _txt(elem, "IdentificativiOfferta/COD_OFFERTA")
    piva = _txt(elem, "IdentificativiOfferta/PIVA_UTENTE")
    nome = (_txt(elem, "DettaglioOfferta/NOME_OFFERTA") or "Offerta ARERA").strip()
    desc = _txt(elem, "DettaglioOfferta/DESCRIZIONE")
    durata = _txt(elem, "DettaglioOfferta/DURATA")
    garanzie = _txt(elem, "DettaglioOfferta/GARANZIE")
    dom_res = _txt(elem, "DettaglioOfferta/DOMESTICO_RESIDENTE")

    url_sito = _txt(elem, "DettaglioOfferta/Contatti/URL_SITO_VENDITORE") or ""
    url_offerta = _txt(elem, "DettaglioOfferta/Contatti/URL_OFFERTA") or url_sito
    telefono = _txt(elem, "DettaglioOfferta/Contatti/TELEFONO")
    fornitore = _vendor_name(url_offerta, url_sito)

    idx = _txt(elem, "RiferimentiPrezzoEnergia/IDX_PREZZO_ENERGIA") or ""
    data_inizio = _parse_date(_txt(elem, "ValiditaOfferta/DATA_INIZIO"))
    valida_fino = _parse_date(_txt(elem, "ValiditaOfferta/DATA_FINE"))

    # Modalità attivazione (lista)
    mod_att = []
    for ma in elem.findall(_tag("DettaglioOfferta") + "/" + _tag("ModalitaAttivazione")):
        m = _txt(ma, "MODALITA")
        if m:
            mod_att.append(m)

    # Metodi pagamento (lista di dict)
    met_pag = []
    for mp in elem.findall(_tag("MetodoPagamento")):
        cod_mp = _txt(mp, "MODALITA_PAGAMENTO")
        desc_mp = _txt(mp, "DESCRIZIONE")
        if cod_mp:
            met_pag.append({"codice": cod_mp, "descrizione": desc_mp})

    # Zone offerta (regioni e province)
    zone_data = {"regioni": [], "province": []}
    for zo in elem.findall(_tag("ZoneOfferta")):
        for r in zo.findall(_tag("REGIONE")):
            if r.text and r.text.strip():
                zone_data["regioni"].append(r.text.strip())
        for p in zo.findall(_tag("PROVINCIA")):
            if p.text and p.text.strip():
                zone_data["province"].append(p.text.strip())
    # Deduplica
    zone_data["regioni"] = sorted(set(zone_data["regioni"]))
    zone_data["province"] = sorted(set(zone_data["province"]))
    zone_json = json.dumps(zone_data, ensure_ascii=False) if (zone_data["regioni"] or zone_data["province"]) else None

    # Condizioni contrattuali
    condizioni = []
    for cc in elem.findall(_tag("CondizioniContrattuali")):
        tip = _txt(cc, "TIPOLOGIA_CONDIZIONE")
        desc_cc = _txt(cc, "DESCRIZIONE")
        lim = _txt(cc, "LIMITANTE")
        if tip:
            condizioni.append({"tipo": tip, "descrizione": desc_cc, "limitante": lim})
    cond_json = json.dumps(condizioni, ensure_ascii=False) if condizioni else None

    # Sconti
    sconti = []
    for sc in elem.findall(_tag("Sconto")):
        s = {
            "nome": _txt(sc, "NOME"),
            "descrizione": _txt(sc, "DESCRIZIONE"),
            "validita": _txt(sc, "VALIDITA"),
            "iva": _txt(sc, "IVA_SCONTO"),
        }
        # Prezzi sconto
        prezzi_sc = []
        for ps in sc.findall(_tag("PrezziSconto")):
            prezzi_sc.append({
                "fascia": _txt(ps, "FASCIA_COMPONENTE"),
                "prezzo": _txt(ps, "PREZZO"),
                "unita": _txt(ps, "UNITA_MISURA"),
            })
        if prezzi_sc:
            s["prezzi"] = prezzi_sc
        sconti.append(s)
    sconto_json = json.dumps(sconti, ensure_ascii=False) if sconti else None

    # Offerte congiunte (dual)
    oc_ee = _txt(elem, "OffertaDual/OFFERTE_CONGIUNTE_EE")
    oc_gas = _txt(elem, "OffertaDual/OFFERTE_CONGIUNTE_GAS")

    return {
        "cod_offerta": cod,
        "piva_fornitore": piva,
        "fornitore": fornitore,
        "nome": nome,
        "descrizione": desc,
        "durata": int(durata) if durata and durata.isdigit() else None,
        "garanzie": garanzie,
        "telefono": telefono,
        "url": url_offerta or url_sito,
        "url_sito": url_sito,
        "modalita_attivazione": json.dumps(mod_att) if mod_att else None,
        "metodi_pagamento": json.dumps(met_pag, ensure_ascii=False) if met_pag else None,
        "data_inizio": data_inizio,
        "valida_fino": valida_fino,
        "zone": zone_json,
        "domestico_residente": dom_res,
        "offerta_congiunta_ee": oc_ee,
        "offerta_congiunta_gas": oc_gas,
        "condizioni": cond_json,
        "sconto_json": sconto_json,
        "idx": idx,
    }

# ── Helpers prezzi ──────────────────────────────────────────────────────────
def _parse_prezzi_luce(elem, is_variabile: bool) -> dict:
    """Estrae prezzi energia luce (fasce, spread PUN, quota fissa)."""
    prezzo_f1 = prezzo_f2 = prezzo_f3 = prezzo_f23 = prezzo_mono = None
    spread_pun = None
    quota_fissa = None

    for comp in elem.findall(_tag("ComponenteImpresa")):
        macro = _txt(comp, "MACROAREA")

        if macro == MA_QUOTA_FISSA:
            if quota_fissa is None:
                for intv in comp.findall(_tag("IntervalloPrezzi")):
                    v = _f(_txt(intv, "PREZZO"))
                    um = _txt(intv, "UNITA_MISURA")
                    if v is not None:
                        quota_fissa = v * 12 if um == "02" else v
                        break

        elif macro == MA_SPREAD_PUN and is_variabile:
            for intv in comp.findall(_tag("IntervalloPrezzi")):
                fascia = _txt(intv, "FASCIA_COMPONENTE")
                v = _f(_txt(intv, "PREZZO"))
                if v is None:
                    continue
                if fascia == FASCIA_01:
                    spread_pun = v
                    break
                elif spread_pun is None:
                    spread_pun = v

        elif macro == MA_ENERGIA_FISSO and not is_variabile:
            for intv in comp.findall(_tag("IntervalloPrezzi")):
                fascia = _txt(intv, "FASCIA_COMPONENTE")
                v = _f(_txt(intv, "PREZZO"))
                if v is None:
                    continue
                if fascia == FASCIA_01:
                    prezzo_f1 = v
                elif fascia == FASCIA_02:
                    prezzo_f2 = v
                elif fascia == FASCIA_03:
                    prezzo_f3 = v
                elif fascia == FASCIA_91:
                    prezzo_f23 = v
                elif fascia is None:
                    prezzo_mono = v

    # Normalizzazione prezzi FISSO
    if not is_variabile:
        if prezzo_mono is not None and prezzo_f1 is None:
            prezzo_f1 = prezzo_f2 = prezzo_f3 = prezzo_mono
            if prezzo_f23 is None:
                prezzo_f23 = prezzo_mono
        elif prezzo_f1 is not None and prezzo_f2 is None and prezzo_f3 is None and prezzo_f23 is None:
            prezzo_f2 = prezzo_f3 = prezzo_f23 = prezzo_f1
            prezzo_mono = prezzo_f1
        elif prezzo_f1 is not None and prezzo_f23 is not None and prezzo_f2 is None:
            prezzo_f2 = prezzo_f3 = prezzo_f23
            prezzo_mono = round(0.40 * prezzo_f1 + 0.60 * prezzo_f23, 6)
        elif prezzo_f1 is not None and prezzo_f2 is not None and prezzo_f3 is not None:
            if prezzo_mono is None:
                prezzo_mono = round(0.40 * prezzo_f1 + 0.35 * prezzo_f2 + 0.25 * prezzo_f3, 6)
            if prezzo_f23 is None:
                prezzo_f23 = round((prezzo_f2 + prezzo_f3) / 2, 6)

    return {
        "prezzo_f1": prezzo_f1, "prezzo_f2": prezzo_f2, "prezzo_f3": prezzo_f3,
        "prezzo_f23": prezzo_f23, "prezzo_mono": prezzo_mono,
        "spread_pun": spread_pun, "quota_fissa": quota_fissa or 0.0,
    }


def _parse_prezzi_gas(elem, is_variabile: bool) -> dict:
    """Estrae prezzi gas (prezzo_smc, spread_psv, quota_fissa, quota_var)."""
    prezzo_smc = spread_psv = quota_fissa = quota_var = None

    for comp in elem.findall(_tag("ComponenteImpresa")):
        macro = _txt(comp, "MACROAREA")

        if macro == MA_QUOTA_FISSA:
            if quota_fissa is None:
                for intv in comp.findall(_tag("IntervalloPrezzi")):
                    v = _f(_txt(intv, "PREZZO"))
                    um = _txt(intv, "UNITA_MISURA")
                    if v is not None:
                        quota_fissa = v * 12 if um == "02" else v
                        break

        elif macro == "02":
            if quota_var is None:
                for intv in comp.findall(_tag("IntervalloPrezzi")):
                    v = _f(_txt(intv, "PREZZO"))
                    if v is not None:
                        quota_var = v
                        break

        elif macro == MA_ENERGIA_FISSO:
            for intv in comp.findall(_tag("IntervalloPrezzi")):
                v = _f(_txt(intv, "PREZZO"))
                if v is None:
                    continue
                if is_variabile:
                    if spread_psv is None:
                        spread_psv = v
                else:
                    if prezzo_smc is None:
                        prezzo_smc = v

    return {
        "prezzo_smc": prezzo_smc, "spread_psv": spread_psv,
        "quota_fissa": quota_fissa or 0.0, "quota_var": quota_var or 0.0,
    }


# ── Parser offerta luce ─────────────────────────────────────────────────────
def _parse_luce_offerta(elem) -> dict | None:
    """Estrae un dict compatibile con offerte_luce da un elemento <offerta>."""
    tipo_cliente = _txt(elem, "DettaglioOfferta/TIPO_CLIENTE")
    if tipo_cliente != TIPO_CLIENTE_DOMESTICO:
        return None

    tipo_off_raw = _txt(elem, "DettaglioOfferta/TIPO_OFFERTA") or TIPO_OFFERTA_FISSO
    is_variabile = tipo_off_raw == TIPO_OFFERTA_VARIABILE
    tipo_label = "VARIABILE" if is_variabile else "FISSO"

    common = _extract_common(elem)
    prezzi = _parse_prezzi_luce(elem, is_variabile)
    idx_label = f" — IDX {common['idx']}" if common["idx"] else ""

    return {
        "id":         str(uuid.uuid4()),
        "fornitore":  common["fornitore"],
        "nome":       common["nome"],
        "tipo":       tipo_label,
        "profili":    "D2,D3",
        **prezzi,
        "valida_fino": common["valida_fino"],
        "url":        common["url"],
        "note":       f"ARERA Portale Offerte{idx_label}",
        "mercato":    "Libero",
        "fonte":      "arera",
        "inserita":   datetime.now().isoformat(),
        # Nuovi campi dettaglio
        "cod_offerta":           common["cod_offerta"],
        "piva_fornitore":        common["piva_fornitore"],
        "descrizione":           common["descrizione"],
        "durata":                common["durata"],
        "garanzie":              common["garanzie"],
        "telefono":              common["telefono"],
        "modalita_attivazione":  common["modalita_attivazione"],
        "metodi_pagamento":      common["metodi_pagamento"],
        "data_inizio":           common["data_inizio"],
        "zone":                  common["zone"],
        "domestico_residente":   common["domestico_residente"],
        "offerta_congiunta_ee":  common["offerta_congiunta_ee"],
        "offerta_congiunta_gas": common["offerta_congiunta_gas"],
        "condizioni":            common["condizioni"],
        "sconto_json":           common["sconto_json"],
    }

# ── Parser offerta gas ───────────────────────────────────────────────────────
def _parse_gas_offerta(elem) -> dict | None:
    """Estrae un dict compatibile con offerte_gas da un elemento <offerta>."""
    tipo_cliente = _txt(elem, "DettaglioOfferta/TIPO_CLIENTE")
    if tipo_cliente != TIPO_CLIENTE_DOMESTICO:
        return None

    tipo_off_raw = _txt(elem, "DettaglioOfferta/TIPO_OFFERTA") or TIPO_OFFERTA_FISSO
    is_variabile = tipo_off_raw == TIPO_OFFERTA_VARIABILE
    tipo_label = "VARIABILE" if is_variabile else "FISSO"

    common = _extract_common(elem)
    prezzi = _parse_prezzi_gas(elem, is_variabile)
    idx_label = f" — IDX {common['idx']}" if common["idx"] else ""

    return {
        "id":          str(uuid.uuid4()),
        "fornitore":   common["fornitore"],
        "nome":        common["nome"],
        "tipo":        tipo_label,
        "profili":     "D2,D3",
        **prezzi,
        "valida_fino": common["valida_fino"],
        "url":         common["url"],
        "note":        f"ARERA Portale Offerte{idx_label}",
        "mercato":     "Libero",
        "fonte":       "arera",
        "inserita":    datetime.now().isoformat(),
        # Nuovi campi dettaglio
        "cod_offerta":           common["cod_offerta"],
        "piva_fornitore":        common["piva_fornitore"],
        "descrizione":           common["descrizione"],
        "durata":                common["durata"],
        "garanzie":              common["garanzie"],
        "telefono":              common["telefono"],
        "modalita_attivazione":  common["modalita_attivazione"],
        "metodi_pagamento":      common["metodi_pagamento"],
        "data_inizio":           common["data_inizio"],
        "zone":                  common["zone"],
        "domestico_residente":   common["domestico_residente"],
        "offerta_congiunta_ee":  common["offerta_congiunta_ee"],
        "offerta_congiunta_gas": common["offerta_congiunta_gas"],
        "condizioni":            common["condizioni"],
        "sconto_json":           common["sconto_json"],
    }

# ── Parser offerta dual fuel ────────────────────────────────────────────────
def _parse_dual_offerta(elem) -> dict | None:
    """Estrae un dict compatibile con offerte_dual da un elemento <offerta>."""
    tipo_cliente = _txt(elem, "DettaglioOfferta/TIPO_CLIENTE")
    if tipo_cliente != TIPO_CLIENTE_DOMESTICO:
        return None

    tipo_off_raw = _txt(elem, "DettaglioOfferta/TIPO_OFFERTA") or TIPO_OFFERTA_FISSO
    is_variabile = tipo_off_raw == TIPO_OFFERTA_VARIABILE
    tipo_label = "VARIABILE" if is_variabile else "FISSO"

    common = _extract_common(elem)
    prezzi_ee = _parse_prezzi_luce(elem, is_variabile)
    prezzi_gas = _parse_prezzi_gas(elem, is_variabile)
    idx_label = f" — IDX {common['idx']}" if common["idx"] else ""

    return {
        "id":          str(uuid.uuid4()),
        "fornitore":   common["fornitore"],
        "nome":        common["nome"],
        "tipo":        tipo_label,
        "profili":     "D2,D3",
        # Prezzi luce
        "prezzo_f1":   prezzi_ee["prezzo_f1"],
        "prezzo_f2":   prezzi_ee["prezzo_f2"],
        "prezzo_f3":   prezzi_ee["prezzo_f3"],
        "prezzo_f23":  prezzi_ee["prezzo_f23"],
        "prezzo_mono": prezzi_ee["prezzo_mono"],
        "spread_pun":  prezzi_ee["spread_pun"],
        "quota_fissa_ee": prezzi_ee["quota_fissa"],
        # Prezzi gas
        "prezzo_smc":  prezzi_gas["prezzo_smc"],
        "spread_psv":  prezzi_gas["spread_psv"],
        "quota_fissa_gas": prezzi_gas["quota_fissa"],
        "quota_var_gas":   prezzi_gas["quota_var"],
        # Comuni
        "valida_fino": common["valida_fino"],
        "url":         common["url"],
        "note":        f"ARERA Portale Offerte Dual{idx_label}",
        "mercato":     "Libero",
        "fonte":       "arera",
        "inserita":    datetime.now().isoformat(),
        "cod_offerta":           common["cod_offerta"],
        "piva_fornitore":        common["piva_fornitore"],
        "descrizione":           common["descrizione"],
        "durata":                common["durata"],
        "garanzie":              common["garanzie"],
        "telefono":              common["telefono"],
        "modalita_attivazione":  common["modalita_attivazione"],
        "metodi_pagamento":      common["metodi_pagamento"],
        "data_inizio":           common["data_inizio"],
        "zone":                  common["zone"],
        "domestico_residente":   common["domestico_residente"],
        "offerta_congiunta_ee":  common["offerta_congiunta_ee"],
        "offerta_congiunta_gas": common["offerta_congiunta_gas"],
        "condizioni":            common["condizioni"],
        "sconto_json":           common["sconto_json"],
    }

# ── Parser principale ────────────────────────────────────────────────────────
_PARSER_MAP = {
    "E": _parse_luce_offerta,
    "G": _parse_gas_offerta,
    "D": _parse_dual_offerta,
}

def parse_offerte_xml(content: bytes, tipo: str) -> list[dict]:
    """
    Parsa contenuto XML ARERA. tipo='E' → luce, 'G' → gas, 'D' → dual.
    Usa iterparse per efficienza su file grandi (>10 MB).
    """
    parser_fn = _PARSER_MAP[tipo]
    offerte, skipped = [], 0
    offerta_tag = _tag("offerta")

    for event, elem in ET.iterparse(io.BytesIO(content), events=("end",)):
        if elem.tag != offerta_tag:
            continue
        try:
            result = parser_fn(elem)
            if result:
                offerte.append(result)
            else:
                skipped += 1
        except Exception as e:
            log.debug(f"Errore parse offerta XML: {e}")
            skipped += 1
        finally:
            elem.clear()

    log.info(f"XML tipo={tipo}: {len(offerte)} offerte parsed, {skipped} scartate (non domestiche)")
    return offerte

# ── SQL columns ─────────────────────────────────────────────────────────────
_COLS_LUCE = (
    "id, fornitore, nome, tipo, profili, "
    "prezzo_f1, prezzo_f2, prezzo_f3, prezzo_f23, prezzo_mono, spread_pun, "
    "quota_fissa, valida_fino, url, note, mercato, fonte, inserita, "
    "cod_offerta, piva_fornitore, descrizione, durata, garanzie, telefono, "
    "modalita_attivazione, metodi_pagamento, data_inizio, zone, "
    "domestico_residente, offerta_congiunta_ee, offerta_congiunta_gas, "
    "condizioni, sconto_json"
)
_VALS_LUCE = ", ".join(f":{c.strip()}" for c in _COLS_LUCE.split(","))

_COLS_GAS = (
    "id, fornitore, nome, tipo, profili, "
    "prezzo_smc, spread_psv, quota_fissa, quota_var, "
    "valida_fino, url, note, mercato, fonte, inserita, "
    "cod_offerta, piva_fornitore, descrizione, durata, garanzie, telefono, "
    "modalita_attivazione, metodi_pagamento, data_inizio, zone, "
    "domestico_residente, offerta_congiunta_ee, offerta_congiunta_gas, "
    "condizioni, sconto_json"
)
_VALS_GAS = ", ".join(f":{c.strip()}" for c in _COLS_GAS.split(","))

_COLS_DUAL = (
    "id, fornitore, nome, tipo, profili, cod_offerta, piva_fornitore, "
    "descrizione, durata, garanzie, telefono, url, "
    "modalita_attivazione, metodi_pagamento, data_inizio, valida_fino, "
    "zone, domestico_residente, offerta_congiunta_ee, offerta_congiunta_gas, "
    "condizioni, sconto_json, "
    "prezzo_f1, prezzo_f2, prezzo_f3, prezzo_f23, prezzo_mono, spread_pun, "
    "quota_fissa_ee, prezzo_smc, spread_psv, quota_fissa_gas, quota_var_gas, "
    "note, mercato, fonte, inserita"
)
_VALS_DUAL = ", ".join(f":{c.strip()}" for c in _COLS_DUAL.split(","))

# ── Flush and fill ───────────────────────────────────────────────────────────
def flush_and_fill(conn, offerte_luce: list[dict], offerte_gas: list[dict],
                   offerte_dual: list[dict] | None = None) -> dict:
    """
    DELETE WHERE fonte='arera', poi INSERT bulk.
    Preserva offerte manuali (fonte='manuale' o NULL).
    """
    conn.execute("DELETE FROM offerte_luce WHERE fonte='arera'")
    conn.execute("DELETE FROM offerte_gas  WHERE fonte='arera'")
    conn.execute("DELETE FROM offerte_dual WHERE fonte='arera'")

    if offerte_luce:
        conn.executemany(
            f"INSERT INTO offerte_luce ({_COLS_LUCE}) VALUES ({_VALS_LUCE})",
            offerte_luce,
        )

    if offerte_gas:
        conn.executemany(
            f"INSERT INTO offerte_gas ({_COLS_GAS}) VALUES ({_VALS_GAS})",
            offerte_gas,
        )

    if offerte_dual:
        conn.executemany(
            f"INSERT INTO offerte_dual ({_COLS_DUAL}) VALUES ({_VALS_DUAL})",
            offerte_dual,
        )

    conn.commit()
    return {
        "luce": len(offerte_luce),
        "gas": len(offerte_gas),
        "dual": len(offerte_dual) if offerte_dual else 0,
    }

# ── Parametri regolatori (CSV) ──────────────────────────────────────────────
def _build_parametri_url(tipo: str, dt: date) -> str:
    """tipo: 'E' o 'G'."""
    base = "https://www.ilportaleofferte.it/portaleOfferte/resources/opendata/csv/parametriML"
    return f"{base}/{dt.year}_{dt.month}/PO_Parametri_Mercato_Libero_{tipo}_{dt.strftime('%Y%m%d')}.csv"


def parse_parametri_csv(content: bytes, tipo: str) -> list[dict]:
    """Parsa CSV parametri regolatori. Restituisce lista di dict per INSERT."""
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    now = datetime.now().isoformat()
    rows = []
    for r in reader:
        nome = (r.get("nome_parametro") or "").strip()
        val = _f(r.get("valore"))
        desc = (r.get("descrizione") or "").strip()
        if nome and val is not None:
            rows.append({
                "nome": nome, "tipo": tipo,
                "valore": val, "descrizione": desc,
                "aggiornato": now,
            })
    log.info(f"Parametri CSV tipo={tipo}: {len(rows)} parametri parsed")
    return rows


def flush_and_fill_parametri(conn, parametri: list[dict]) -> int:
    """Upsert parametri regolatori (INSERT OR REPLACE)."""
    if not parametri:
        return 0
    conn.executemany(
        """INSERT OR REPLACE INTO parametri_regolatori
           (nome, tipo, valore, descrizione, aggiornato)
           VALUES (:nome, :tipo, :valore, :descrizione, :aggiornato)""",
        parametri,
    )
    conn.commit()
    return len(parametri)


# ── Download ─────────────────────────────────────────────────────────────────
async def download_xml(tipo: str, dt: date) -> bytes | None:
    """
    Scarica l'XML per il giorno dt, con fallback sui 3 giorni precedenti
    (per gestire weekend e festivi in cui ARERA non pubblica).
    """
    timeout = httpx.Timeout(90.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for delta in range(4):
            target = dt - timedelta(days=delta)
            url = _build_url(tipo, target)
            try:
                r = await client.get(url)
                if r.status_code == 200 and len(r.content) > 1000:
                    log.info(f"XML scaricato: {url} ({len(r.content):,} bytes)")
                    return r.content
                log.debug(f"XML non trovato (status={r.status_code}): {url}")
            except Exception as e:
                log.debug(f"Download fallito {url}: {e}")
    return None


async def download_parametri_csv(tipo: str, dt: date) -> bytes | None:
    """Scarica CSV parametri con fallback 3 giorni."""
    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for delta in range(4):
            target = dt - timedelta(days=delta)
            url = _build_parametri_url(tipo, target)
            try:
                r = await client.get(url)
                if r.status_code == 200 and len(r.content) > 100:
                    log.info(f"CSV parametri scaricato: {url} ({len(r.content):,} bytes)")
                    return r.content
                log.debug(f"CSV parametri non trovato (status={r.status_code}): {url}")
            except Exception as e:
                log.debug(f"Download parametri fallito {url}: {e}")
    return None


# ── URL builder ─────────────────────────────────────────────────────────────
def _build_url(tipo: str, dt: date) -> str:
    """tipo: 'E' (elettricità), 'G' (gas) o 'D' (dual fuel)."""
    base = "https://www.ilportaleofferte.it/portaleOfferte/resources/opendata/csv/offerteML"
    return f"{base}/{dt.year}_{dt.month}/PO_Offerte_{tipo}_MLIBERO_{dt.strftime('%Y%m%d')}.xml"


# ── Entry point ──────────────────────────────────────────────────────────────
async def run_sync(conn) -> dict:
    """Scarica e sincronizza offerte ARERA (luce + gas + dual) e parametri nel DB."""
    today = date.today()

    # Download XML offerte (E, G, D in parallelo via httpx)
    content_e = await download_xml("E", today)
    content_g = await download_xml("G", today)
    content_d = await download_xml("D", today)

    if content_e is None and content_g is None and content_d is None:
        return {"ok": False, "error": "Nessun XML ARERA disponibile (provati ultimi 4 giorni)"}

    offerte_luce = parse_offerte_xml(content_e, "E") if content_e else []
    offerte_gas  = parse_offerte_xml(content_g, "G") if content_g else []
    offerte_dual = parse_offerte_xml(content_d, "D") if content_d else []

    counts = flush_and_fill(conn, offerte_luce, offerte_gas, offerte_dual)

    # Download e sync parametri regolatori
    param_count = 0
    csv_e = await download_parametri_csv("E", today)
    csv_g = await download_parametri_csv("G", today)
    all_params = []
    if csv_e:
        all_params.extend(parse_parametri_csv(csv_e, "E"))
    if csv_g:
        all_params.extend(parse_parametri_csv(csv_g, "G"))
    if all_params:
        param_count = flush_and_fill_parametri(conn, all_params)

    log.info(f"ARERA sync: luce={counts['luce']}, gas={counts['gas']}, dual={counts['dual']}, parametri={param_count}")
    return {"ok": True, "data": today.isoformat(), **counts, "parametri": param_count}
