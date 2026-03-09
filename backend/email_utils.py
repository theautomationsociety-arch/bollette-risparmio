"""
Bollette Risparmio — Email utilities (Resend)
Tre template: risultati analisi, conferma consulente (utente), notifica admin.
"""

import os
import logging

log = logging.getLogger(__name__)

try:
    import resend as _resend
    _RESEND_OK = True
except ImportError:
    _RESEND_OK = False


def _base(body_html: str, preview: str, site_url: str, from_email: str) -> str:
    prev = (
        f'<div style="display:none;max-height:0;overflow:hidden;color:#f0f6ff">{preview}</div>'
        if preview else ""
    )
    return (
        "<!DOCTYPE html>"
        '<html lang="it">'
        "<head>"
        '<meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">'
        "</head>"
        '<body style="margin:0;padding:0;background:#f0f6ff;font-family:Helvetica Neue,Arial,sans-serif">'
        + prev
        + '<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f6ff;padding:32px 16px">'
        "<tr><td align=\"center\">"
        '<table width="100%" style="max-width:560px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(13,27,42,.10)">'
        # Header
        '<tr><td style="background:linear-gradient(135deg,#0d1b2a 0%,#1e3a5f 100%);padding:24px 32px">'
        '<span style="font-size:1.3rem;font-weight:800;color:#ffffff;letter-spacing:-.5px">Bolletta'
        '<span style="color:#60a5fa">AI</span></span>'
        "</td></tr>"
        # Body
        '<tr><td style="padding:32px">'
        + body_html
        + "</td></tr>"
        # Footer
        '<tr><td style="background:#f8fafd;padding:20px 32px;border-top:1px solid #e4eaf2">'
        '<p style="margin:0;font-size:11px;color:#8a9ab0;line-height:1.6">'
        "Hai ricevuto questa email perché hai usato il servizio Bollette Risparmio.<br>"
        "I risultati sono stime indicative. Per informazioni: "
        f'<a href="mailto:info@bollette-risparmio.onrender.com" style="color:#2563eb">info@bollette-risparmio.onrender.com</a><br>'
        f'<a href="{site_url}" style="color:#2563eb">{site_url}</a>'
        "</p></td></tr>"
        "</table></td></tr></table>"
        "</body></html>"
    )


def build_risultati(
    nome: str,
    tipo: str,
    profilo_label: str,
    totale: float,
    consumo: float,
    unita: str,
    risparmio_max: float,
    offerta_migliore: dict,
    costo_annuo_attuale: float,
    fornitore_attuale: str,
    site_url: str,
    from_email: str,
) -> tuple:
    tipo_label = "elettrica" if tipo == "luce" else "del gas"
    tipo_emoji = "\u26a1" if tipo == "luce" else "\U0001f525"
    nome_str = f", {nome}" if nome else ""

    # -- Offerta migliore box --
    offerta_html = ""
    if offerta_migliore:
        off = offerta_migliore
        risp = off.get("risparmio_annuo", 0)
        risp_color = "#059669" if risp >= 0 else "#dc2626"
        risp_label = "Risparmio" if risp >= 0 else "Costo extra"
        vai_html = (
            f'<a href="{off["url"]}" style="display:inline-block;margin-top:14px;'
            'background:#059669;color:white;text-decoration:none;padding:10px 20px;'
            'border-radius:8px;font-weight:700;font-size:.88rem">Vai all\'offerta</a>'
            if off.get("url") else ""
        )
        offerta_html = (
            '<div style="background:#f0fdf4;border:1.5px solid #6ee7b7;border-radius:12px;padding:20px;margin:20px 0">'
            '<div style="font-size:11px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;color:#065f46;margin-bottom:8px">'
            "\u2b50 OFFERTA MIGLIORE TROVATA</div>"
            f'<div style="font-size:1.15rem;font-weight:800;color:#0d1b2a">{off.get("nome","")}</div>'
            f'<div style="font-size:.9rem;color:#5a6a7e;margin-bottom:12px">{off.get("fornitore","")}</div>'
            '<div style="display:flex;gap:16px;flex-wrap:wrap">'
            '<div><div style="font-size:11px;color:#5a6a7e;text-transform:uppercase;letter-spacing:.5px">Costo annuo</div>'
            f'<div style="font-size:1.3rem;font-weight:800;color:#0d1b2a">&#8364;{off.get("costo_annuo",0):,.0f}</div></div>'
            f'<div><div style="font-size:11px;color:#5a6a7e;text-transform:uppercase;letter-spacing:.5px">{risp_label}</div>'
            f'<div style="font-size:1.3rem;font-weight:800;color:{risp_color}">&#8364;{abs(risp):,.0f}/anno</div></div>'
            "</div>"
            + vai_html
            + "</div>"
        )

    # -- Risparmio banner --
    risparmio_html = ""
    if risparmio_max and risparmio_max > 50:
        risparmio_html = (
            '<div style="background:#eff6ff;border-radius:10px;padding:16px;margin:16px 0;text-align:center">'
            '<div style="font-size:11px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;color:#1e40af">'
            "RISPARMIO MASSIMO IDENTIFICATO</div>"
            f'<div style="font-size:2rem;font-weight:800;color:#1e40af;letter-spacing:-1px">&#8364;{risparmio_max:,.0f}/anno</div>'
            '<div style="font-size:.83rem;color:#5a6a7e">cambiando al fornitore pi&#249; conveniente</div>'
            "</div>"
        )

    body = (
        f'<h2 style="margin:0 0 6px;font-size:1.25rem;font-weight:800;color:#0d1b2a">'
        f"Ciao{nome_str}! Ecco la tua analisi {tipo_emoji}</h2>"
        f'<p style="margin:0 0 24px;font-size:.9rem;color:#5a6a7e">'
        f"Ho analizzato la tua bolletta {tipo_label} ({profilo_label}). Ecco il riepilogo:</p>"
        # KPI table
        '<table width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:8px">'
        "<tr>"
        '<td width="33%" style="text-align:center;padding:16px 8px;background:#f8fafd;border-radius:10px">'
        '<div style="font-size:11px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:#5a6a7e">Totale Fattura</div>'
        f'<div style="font-size:1.4rem;font-weight:800;color:#0d1b2a">&#8364;{totale:,.2f}</div></td>'
        '<td width="4%"></td>'
        '<td width="30%" style="text-align:center;padding:16px 8px;background:#f8fafd;border-radius:10px">'
        '<div style="font-size:11px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:#5a6a7e">Consumo</div>'
        f'<div style="font-size:1.4rem;font-weight:800;color:#0d1b2a">{consumo:,.0f}</div>'
        f'<div style="font-size:.75rem;color:#5a6a7e">{unita}</div></td>'
        '<td width="4%"></td>'
        '<td width="29%" style="text-align:center;padding:16px 8px;background:#f8fafd;border-radius:10px">'
        '<div style="font-size:11px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:#5a6a7e">Costo annuo att.</div>'
        f'<div style="font-size:1.4rem;font-weight:800;color:#0d1b2a">&#8364;{costo_annuo_attuale:,.0f}</div></td>'
        "</tr></table>"
        + risparmio_html
        + offerta_html
        + '<div style="border-top:1px solid #e4eaf2;padding-top:20px;margin-top:20px">'
        f'<p style="margin:0 0 12px;font-size:.88rem;color:#1a2332">Vuoi analizzare un\'altra bolletta?</p>'
        f'<a href="{site_url}" style="display:inline-block;background:#0d1b2a;color:white;'
        'text-decoration:none;padding:12px 24px;border-radius:10px;font-weight:700;font-size:.9rem">'
        "Analizza un'altra bolletta</a></div>"
        f'<p style="margin:16px 0 0;font-size:.8rem;color:#8a9ab0">'
        f"Fornitore attuale rilevato: <strong>{fornitore_attuale or 'non rilevato'}</strong></p>"
    )

    subject = f"Bollette Risparmio: la tua analisi bolletta {tipo_label}"
    if risparmio_max and risparmio_max > 50:
        subject += f" \u2014 risparmio possibile \u20ac{risparmio_max:,.0f}/anno"

    preview = (
        f"Analisi completata. Risparmio identificato: \u20ac{risparmio_max:,.0f}/anno"
        if risparmio_max and risparmio_max > 0
        else "La tua analisi bolletta e' pronta"
    )
    return subject, _base(body, preview, site_url, from_email)


def build_consulente_utente(nome: str, email: str, site_url: str, from_email: str) -> tuple:
    nome_str = nome or "Ciao"
    body = (
        f'<h2 style="margin:0 0 6px;font-size:1.25rem;font-weight:800;color:#0d1b2a">'
        f"Richiesta ricevuta, {nome_str}!</h2>"
        f'<p style="margin:0 0 20px;font-size:.9rem;color:#5a6a7e;line-height:1.65">'
        f"Abbiamo ricevuto la tua richiesta di consulenza per le tariffe energetiche.<br>"
        f"Un nostro consulente ti contatter&#224; entro <strong>24 ore lavorative</strong> "
        f"all'indirizzo <strong>{email}</strong>.</p>"
        '<div style="background:#f0fdf4;border-left:4px solid #059669;padding:16px 20px;border-radius:0 10px 10px 0;margin-bottom:20px">'
        '<p style="margin:0;font-size:.88rem;color:#065f46;line-height:1.65">'
        "Il consulente analizzera' la tua bolletta, verifichera' le offerte pi&#249; convenienti "
        "disponibili sul mercato libero e ti proporr&#224; la soluzione migliore per il tuo profilo.</p>"
        "</div>"
        f'<a href="{site_url}" style="display:inline-block;background:#0d1b2a;color:white;'
        'text-decoration:none;padding:12px 24px;border-radius:10px;font-weight:700;font-size:.9rem">'
        "Analizza subito</a>"
    )
    return (
        "Bollette Risparmio: consulenza richiesta \u2705",
        _base(body, "Consulenza confermata. Ti contatteremo entro 24 ore.", site_url, from_email),
    )


def build_consulente_admin(
    nome: str,
    cognome: str,
    email: str,
    telefono: str,
    consenso_mkt: bool,
    bolletta_id: str,
    site_url: str,
    from_email: str,
) -> tuple:
    body = (
        '<h2 style="margin:0 0 6px;font-size:1.25rem;font-weight:800;color:#0d1b2a">'
        "\U0001f514 Nuovo lead consulente</h2>"
        '<p style="margin:0 0 20px;font-size:.9rem;color:#5a6a7e">'
        "Un nuovo utente ha richiesto una consulenza personalizzata.</p>"
        '<table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafd;border-radius:10px;overflow:hidden;margin-bottom:20px">'
        f'<tr><td style="padding:12px 16px;border-bottom:1px solid #e4eaf2">'
        '<span style="font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#5a6a7e">Nome</span>'
        f"<br><strong>{nome} {cognome}</strong></td></tr>"
        f'<tr><td style="padding:12px 16px;border-bottom:1px solid #e4eaf2">'
        '<span style="font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#5a6a7e">Email</span>'
        f'<br><a href="mailto:{email}" style="color:#2563eb">{email}</a></td></tr>'
        f'<tr><td style="padding:12px 16px;border-bottom:1px solid #e4eaf2">'
        '<span style="font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#5a6a7e">Telefono</span>'
        f'<br><a href="tel:{telefono}" style="color:#2563eb">{telefono or "&#8212;"}</a></td></tr>'
        f'<tr><td style="padding:12px 16px;border-bottom:1px solid #e4eaf2">'
        '<span style="font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#5a6a7e">Bolletta analizzata</span>'
        f'<br><span style="font-size:.82rem;color:#5a6a7e">{bolletta_id or "nessuna"}</span></td></tr>'
        f'<tr><td style="padding:12px 16px">'
        '<span style="font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#5a6a7e">Consenso marketing</span>'
        f'<br>{"&#9989; S&#236;" if consenso_mkt else "&#10060; No"}</td></tr>'
        "</table>"
        f'<a href="{site_url}/admin" style="display:inline-block;background:#0d1b2a;color:white;'
        'text-decoration:none;padding:12px 24px;border-radius:10px;font-weight:700;font-size:.9rem">'
        "Apri pannello admin</a>"
    )
    return (
        f"\U0001f514 Nuovo lead consulente: {nome} {cognome}",
        _base(body, f"Nuovo lead: {nome} {cognome} — {email}", site_url, from_email),
    )


def send_email(to: str, subject: str, html: str, resend_key: str, from_email: str) -> bool:
    """Invia una email via Resend. Ritorna True se OK, False se disabilitato o errore."""
    if not _RESEND_OK or not resend_key:
        log.info(f"[EMAIL SKIP] Resend non configurato | {to} | {subject}")
        return False
    if not to or "@" not in to:
        log.warning(f"[EMAIL SKIP] Indirizzo non valido: {to!r}")
        return False
    try:
        _resend.api_key = resend_key
        _resend.Emails.send({
            "from": from_email,
            "to": [to],
            "subject": subject,
            "html": html,
        })
        log.info(f"[EMAIL OK] {to} | {subject}")
        return True
    except Exception as exc:
        log.error(f"[EMAIL ERR] {to} | {exc}")
        return False
