"""
Bollette Risparmio — Guide SEO (5 pagine pillar)
Serve HTML completo, server-side, per ogni guida.
"""

from datetime import datetime

SITE_URL = "https://www.bolletterisparmio.it"

# ── CSS condiviso ────────────────────────────────────────────────────────
_CSS = """
:root{
  --navy:#1A2E4A;--ink:#1a2332;--muted:#5a6a7e;
  --border:#e4eaf2;--bg:#f8fafd;--white:#fff;
  --green:#059669;--green-l:#d1fae5;--green-d:#065f46;
  --blue:#E8500A;--blue-l:#FFF0E8;
  --orange:#E8500A;--orange-light:#FF6B2C;--yellow:#d97706;
  --r:12px;--r-sm:8px;
  --shadow-sm:0 1px 3px rgba(0,0,0,.08);
  --shadow:0 4px 16px rgba(26,46,74,.10);
  --t:180ms ease;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:'DM Sans',sans-serif;background:var(--white);color:var(--ink);-webkit-font-smoothing:antialiased;font-size:17px;line-height:1.75}

/* PROGRESS BAR */
#progress{position:fixed;top:0;left:0;height:3px;background:linear-gradient(90deg,var(--orange),var(--orange-light));width:0%;z-index:200;transition:width .1s}

/* NAV */
.nav{position:sticky;top:0;z-index:100;background:rgba(255,255,255,.92);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);padding:0 1.5rem;height:64px;display:flex;align-items:center;justify-content:space-between}
.nav-logo{display:flex;align-items:center;gap:.5rem;text-decoration:none}
.nav-logo-icon{width:32px;height:32px;background:linear-gradient(135deg,var(--navy),#1e40af);border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:1rem}
.nav-logo-text{font-family:'Sora','Bricolage Grotesque',sans-serif;font-weight:800;font-size:1.05rem;color:var(--navy);letter-spacing:-.5px}
.nav-logo-text span{color:var(--orange)}
.nav-cta{background:var(--navy);color:white;text-decoration:none;font-size:.84rem;font-weight:600;padding:7px 16px;border-radius:var(--r-sm);transition:all var(--t)}
.nav-cta:hover{background:#1e3a5f;transform:translateY(-1px)}

/* BREADCRUMB */
.breadcrumb-bar{background:var(--bg);border-bottom:1px solid var(--border);padding:.65rem 1.5rem}
.breadcrumb{max-width:860px;margin:0 auto;display:flex;align-items:center;gap:.5rem;font-size:.78rem;color:var(--muted);flex-wrap:wrap}
.breadcrumb a{color:var(--muted);text-decoration:none;transition:color var(--t)}
.breadcrumb a:hover{color:var(--blue)}
.breadcrumb-sep{color:var(--border)}

/* HERO GUIDA */
.guide-hero{background:linear-gradient(160deg,#f0f6ff 0%,#e8f4f8 60%,#f0fff8 100%);padding:3.5rem 1.5rem 2.5rem;border-bottom:1px solid var(--border)}
.guide-hero-inner{max-width:860px;margin:0 auto}
.guide-category{display:inline-flex;align-items:center;gap:.4rem;background:var(--blue-l);color:var(--blue);font-size:.72rem;font-weight:700;padding:4px 12px;border-radius:100px;letter-spacing:.5px;text-transform:uppercase;margin-bottom:1rem}
.guide-title{font-family:'Bricolage Grotesque',sans-serif;font-size:clamp(1.75rem,4vw,2.6rem);font-weight:800;color:var(--navy);letter-spacing:-1px;line-height:1.1;margin-bottom:.9rem}
.guide-desc{font-size:1rem;color:var(--muted);max-width:600px;line-height:1.7;margin-bottom:1.5rem}
.guide-meta{display:flex;gap:1.25rem;flex-wrap:wrap;font-size:.8rem;color:var(--muted)}
.guide-meta span{display:flex;align-items:center;gap:.3rem}

/* LAYOUT */
.guide-layout{max-width:1060px;margin:0 auto;padding:2.5rem 1.5rem 4rem;display:grid;grid-template-columns:1fr 280px;gap:3rem;align-items:start}
@media(max-width:860px){.guide-layout{grid-template-columns:1fr}}

/* ARTICLE */
.article h2{font-family:'Bricolage Grotesque',sans-serif;font-size:1.45rem;font-weight:800;color:var(--navy);letter-spacing:-.5px;margin:2.5rem 0 .9rem;padding-top:.5rem;border-top:2px solid var(--bg)}
.article h2:first-child{margin-top:0;border-top:none}
.article h3{font-family:'Bricolage Grotesque',sans-serif;font-size:1.1rem;font-weight:700;color:var(--ink);margin:1.75rem 0 .6rem}
.article p{margin-bottom:1.1rem;color:#2d3a4a;line-height:1.78}
.article ul,.article ol{margin:0 0 1.1rem 1.4rem;color:#2d3a4a}
.article li{margin-bottom:.45rem;line-height:1.7}
.article strong{color:var(--ink)}
.article a{color:var(--blue);text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:2px}

/* CALLOUT BOXES */
.box{border-radius:var(--r);padding:1.25rem 1.4rem;margin:1.75rem 0;font-size:.93rem;line-height:1.7}
.box-title{font-family:'Bricolage Grotesque',sans-serif;font-weight:700;font-size:.85rem;text-transform:uppercase;letter-spacing:.5px;margin-bottom:.6rem;display:flex;align-items:center;gap:.4rem}
.box-info{background:var(--blue-l);border-left:4px solid var(--blue)}
.box-info .box-title{color:#1e40af}
.box-warn{background:#fffbeb;border-left:4px solid var(--yellow)}
.box-warn .box-title{color:#92400e}
.box-ok{background:var(--green-l);border-left:4px solid var(--green)}
.box-ok .box-title{color:var(--green-d)}
.box-tip{background:#fdf4ff;border-left:4px solid #a855f7}
.box-tip .box-title{color:#6b21a8}

/* TABLE */
.data-table{width:100%;border-collapse:collapse;margin:1.5rem 0;font-size:.9rem;overflow:hidden;border-radius:var(--r-sm);border:1px solid var(--border)}
.data-table th{background:var(--navy);color:white;padding:10px 14px;text-align:left;font-family:'Bricolage Grotesque',sans-serif;font-weight:700;font-size:.8rem;letter-spacing:.4px;text-transform:uppercase}
.data-table td{padding:10px 14px;border-bottom:1px solid var(--border);vertical-align:top}
.data-table tr:last-child td{border:none}
.data-table tr:nth-child(even) td{background:var(--bg)}
.data-table-wrap{overflow-x:auto;margin:1.5rem 0}

/* FASCIA CARDS */
.fascia-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:.75rem;margin:1.5rem 0}
@media(max-width:600px){.fascia-grid{grid-template-columns:1fr}}
.fascia-card{border-radius:var(--r);padding:1.1rem;text-align:center;border:2px solid transparent}
.fascia-f1{background:#fff7ed;border-color:#fed7aa}
.fascia-f2{background:#fefce8;border-color:#fde68a}
.fascia-f3{background:#f0fdf4;border-color:#bbf7d0}
.fascia-label{font-family:'Bricolage Grotesque',sans-serif;font-size:1.6rem;font-weight:800;margin-bottom:.35rem}
.fascia-f1 .fascia-label{color:#c2410c}
.fascia-f2 .fascia-label{color:#a16207}
.fascia-f3 .fascia-label{color:#15803d}
.fascia-name{font-weight:700;font-size:.85rem;color:var(--ink);margin-bottom:.3rem}
.fascia-hours{font-size:.78rem;color:var(--muted);line-height:1.5}

/* STEP LIST */
.step-list{list-style:none;margin:1.5rem 0}
.step-list li{display:flex;gap:1rem;margin-bottom:1.3rem;align-items:flex-start}
.step-num{min-width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,var(--blue),#7c3aed);color:white;display:flex;align-items:center;justify-content:center;font-family:'Bricolage Grotesque',sans-serif;font-weight:800;font-size:.9rem;flex-shrink:0;margin-top:2px}
.step-content strong{display:block;font-family:'Bricolage Grotesque',sans-serif;font-weight:700;font-size:.95rem;margin-bottom:.2rem}
.step-content{font-size:.9rem;color:#2d3a4a;line-height:1.7}

/* INLINE CTA */
.inline-cta{background:linear-gradient(135deg,var(--navy) 0%,#1e3a5f 100%);border-radius:var(--r);padding:1.75rem;text-align:center;margin:2.25rem 0;color:white}
.inline-cta h4{font-family:'Bricolage Grotesque',sans-serif;font-weight:800;font-size:1.1rem;margin-bottom:.5rem}
.inline-cta p{font-size:.88rem;opacity:.75;margin-bottom:1.1rem;line-height:1.6}
.inline-cta a{display:inline-flex;align-items:center;gap:.4rem;background:white;color:var(--navy);text-decoration:none;border-radius:var(--r-sm);padding:.75rem 1.6rem;font-family:'Bricolage Grotesque',sans-serif;font-weight:700;font-size:.9rem;transition:all var(--t)}
.inline-cta a:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,0,0,.2)}

/* SIDEBAR */
.sidebar{position:sticky;top:80px}
.sidebar-card{background:white;border:1px solid var(--border);border-radius:var(--r);padding:1.25rem;margin-bottom:1rem;box-shadow:var(--shadow-sm)}
.sidebar-title{font-family:'Bricolage Grotesque',sans-serif;font-weight:700;font-size:.82rem;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-bottom:.9rem}
.toc-list{list-style:none}
.toc-list li{border-bottom:1px solid var(--bg);padding:.45rem 0}
.toc-list li:last-child{border:none}
.toc-list a{color:var(--muted);text-decoration:none;font-size:.84rem;transition:color var(--t);display:block}
.toc-list a:hover{color:var(--blue)}
.sidebar-cta{background:linear-gradient(135deg,var(--navy),#1e3a5f);border-radius:var(--r);padding:1.25rem;text-align:center;color:white}
.sidebar-cta h4{font-family:'Bricolage Grotesque',sans-serif;font-weight:800;font-size:.95rem;margin-bottom:.4rem}
.sidebar-cta p{font-size:.8rem;opacity:.65;margin-bottom:.9rem;line-height:1.55}
.sidebar-cta a{display:block;background:white;color:var(--navy);text-decoration:none;border-radius:var(--r-sm);padding:.7rem;font-family:'Bricolage Grotesque',sans-serif;font-weight:700;font-size:.84rem;transition:all var(--t)}
.sidebar-cta a:hover{transform:translateY(-1px)}

/* CORRELATE */
.correlate-section{max-width:860px;margin:0 auto 4rem;padding:0 1.5rem}
.correlate-title{font-family:'Bricolage Grotesque',sans-serif;font-weight:800;font-size:1.1rem;color:var(--navy);margin-bottom:1.1rem}
.correlate-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.75rem}
.correlate-card{background:var(--bg);border:1px solid var(--border);border-radius:var(--r);padding:1.1rem 1.25rem;text-decoration:none;display:block;transition:all var(--t)}
.correlate-card:hover{background:white;box-shadow:var(--shadow);transform:translateY(-2px)}
.correlate-card-cat{font-size:.68rem;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:var(--blue);margin-bottom:.35rem}
.correlate-card-title{font-family:'Bricolage Grotesque',sans-serif;font-weight:700;font-size:.9rem;color:var(--ink);margin-bottom:.3rem}
.correlate-card-desc{font-size:.78rem;color:var(--muted);line-height:1.55}

/* FOOTER */
.footer{background:var(--navy);padding:2.5rem 1.5rem;color:rgba(255,255,255,.45)}
.footer-inner{max-width:1060px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem}
.footer-logo{font-family:'Sora','Bricolage Grotesque',sans-serif;font-weight:800;color:white;font-size:1rem}
.footer-logo span{color:#FF6B2C}
.footer-links{display:flex;gap:1rem;flex-wrap:wrap}
.footer-links a{color:rgba(255,255,255,.35);text-decoration:none;font-size:.8rem;transition:color var(--t)}
.footer-links a:hover{color:rgba(255,255,255,.75)}
.footer-copy{font-size:.75rem;text-align:right}
@media(max-width:600px){.footer-inner{flex-direction:column;text-align:center}.footer-copy{text-align:center}}
"""

# ── Navbar ───────────────────────────────────────────────────────────────
_NAV = """<div id="progress"></div>
<nav class="nav">
  <a href="/" class="nav-logo">
    <svg width="32" height="32" viewBox="0 0 36 36" fill="none">
      <rect width="36" height="36" rx="10" fill="#1A2E4A"/>
      <path d="M11 22l5-8 4 6 3-4 3 6" stroke="#E8500A" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="18" cy="14" r="1.5" fill="#FF6B2C"/>
    </svg>
    <span class="nav-logo-text">Bollette <span>Risparmio</span></span>
  </a>
  <div style="display:flex;align-items:center;gap:.75rem">
    <a href="tel:0819131897" style="font-size:.82rem;color:var(--navy);text-decoration:none;font-weight:600;display:none" class="nav-phone-desktop">&#128222; 081 91 31 897</a>
    <a href="/" class="nav-cta">Analizza Bolletta &#x2192;</a>
  </div>
</nav>"""

# ── Footer ───────────────────────────────────────────────────────────────
_FOOTER = """<footer class="footer">
  <div class="footer-inner">
    <div>
      <div class="footer-logo">Bollette <span>Risparmio</span></div>
      <div style="font-size:.75rem;margin-top:.25rem">Analisi AI gratuita bollette luce e gas</div>
      <div style="font-size:.75rem;margin-top:.35rem;opacity:.6">Via Cesario Console 3, 80132 Napoli &middot; info@bolletterisparmio.it</div>
    </div>
    <div class="footer-links">
      <a href="/">Analisi AI Gratuita</a>
      <a href="/#offerte">Offerte Luce &amp; Gas</a>
      <a href="/guide">Guide Gratuite</a>
      <a href="/#contatti">Contatti</a>
    </div>
    <div class="footer-copy">
      &#169; Bollette Risparmio, diritti riservati.<br>
      <a href="https://www.iubenda.com/privacy-policy/30631851" target="_blank" style="color:rgba(255,255,255,.4);text-decoration:none;font-size:.72rem">Privacy Policy</a> &middot;
      <a href="https://www.bolletterisparmio.it/trattamento-dati/" target="_blank" style="color:rgba(255,255,255,.4);text-decoration:none;font-size:.72rem">Condizioni Generali</a>
    </div>
  </div>
</footer>
<script>
window.addEventListener('scroll',()=>{
  const p=document.getElementById('progress');
  const h=document.documentElement;
  const pct=(h.scrollTop||document.body.scrollTop)/(h.scrollHeight-h.clientHeight)*100;
  if(p) p.style.width=pct+'%';
});
</script>"""

_ALL_GUIDES = [
    ("/guida/differenza-mercato-libero-tutelato",
     "Differenza tra Mercato Libero e Tutelato",
     "Scopri le differenze tra mercato libero e tutelato, quando conviene cambiare e cosa succede dopo la fine della tutela."),
    ("/guida/come-leggere-bolletta-luce",
     "Come leggere la bolletta della luce",
     "Guida completa alle voci della bolletta elettrica: materia energia, trasporto, oneri di sistema, accise e IVA."),
    ("/guida/fasce-orarie-f1-f2-f3",
     "Fasce orarie F1, F2, F3: tutto quello che devi sapere",
     "Cosa sono le fasce orarie dell'energia elettrica, quali ore coprono e come influenzano il costo della bolletta."),
    ("/guida/come-cambiare-fornitore-energia",
     "Come cambiare fornitore di luce e gas",
     "Guida passo-passo per cambiare fornitore di energia: diritti, tempi, documenti necessari e cosa non cambia."),
    ("/guida/pun-psv-cosa-sono",
     "PUN e PSV: cosa sono e come influenzano la tua bolletta",
     "Spiegazione di PUN (Prezzo Unico Nazionale) e PSV (Punto di Scambio Virtuale): gli indici che determinano il prezzo dell'energia variabile."),
]

def _correlate_cards(current_path: str) -> str:
    cards = []
    for path, title, desc in _ALL_GUIDES:
        if path == current_path:
            continue
        cards.append(f"""<a href="{path}" class="correlate-card">
  <div class="correlate-card-cat">Guida</div>
  <div class="correlate-card-title">{title}</div>
  <div class="correlate-card-desc">{desc[:80]}...</div>
</a>""")
    return "\n".join(cards[:4])


def _page(
    path: str,
    title: str,
    desc: str,
    category: str,
    read_min: int,
    toc: list,
    body: str,
    schema_extra: str = "",
) -> str:
    today = datetime.now().strftime("%d %B %Y")
    toc_items = "\n".join(f'<li><a href="#{slug}">{label}</a></li>' for slug, label in toc)
    correlate = _correlate_cards(path)
    canonical = SITE_URL + path

    schema = f"""{{
  "@context": "https://schema.org",
  "@graph": [
    {{
      "@type": "Article",
      "@id": "{canonical}#article",
      "headline": "{title}",
      "description": "{desc}",
      "inLanguage": "it-IT",
      "author": {{"@type":"Organization","name":"Bollette Risparmio","url":"{SITE_URL}"}},
      "publisher": {{"@type":"Organization","name":"Bollette Risparmio","url":"{SITE_URL}"}},
      "dateModified": "{datetime.now().strftime('%Y-%m-%d')}",
      "mainEntityOfPage": "{canonical}"
    }},
    {{
      "@type": "BreadcrumbList",
      "itemListElement": [
        {{"@type":"ListItem","position":1,"name":"Home","item":"{SITE_URL}/"}},
        {{"@type":"ListItem","position":2,"name":"Guide","item":"{SITE_URL}/guide"}},
        {{"@type":"ListItem","position":3,"name":"{title}","item":"{canonical}"}}
      ]
    }}
    {','+schema_extra if schema_extra else ''}
  ]
}}"""

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title} — Bollette Risparmio</title>
<meta name="description" content="{desc}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="article">
<meta property="og:title" content="{title} — Bollette Risparmio">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{canonical}">
<meta property="og:locale" content="it_IT">
<meta property="og:site_name" content="Bollette Risparmio">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{title} — Bollette Risparmio">
<meta name="twitter:description" content="{desc}">
<script type="application/ld+json">{schema}</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,700;12..96,800&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>{_CSS}</style>
</head>
<body>
{_NAV}

<!-- BREADCRUMB -->
<div class="breadcrumb-bar">
  <nav class="breadcrumb" aria-label="Breadcrumb">
    <a href="/">Home</a>
    <span class="breadcrumb-sep">&#8250;</span>
    <a href="/guide">Guide</a>
    <span class="breadcrumb-sep">&#8250;</span>
    <span>{title}</span>
  </nav>
</div>

<!-- HERO -->
<div class="guide-hero">
  <div class="guide-hero-inner">
    <div class="guide-category">&#x1F4DA; {category}</div>
    <h1 class="guide-title">{title}</h1>
    <p class="guide-desc">{desc}</p>
    <div class="guide-meta">
      <span>&#x1F4C5; Aggiornato: {today}</span>
      <span>&#x23F1; {read_min} min di lettura</span>
      <span>&#x1F1EE;&#x1F1F9; Mercato energetico italiano</span>
    </div>
  </div>
</div>

<!-- CONTENT -->
<div class="guide-layout">
  <article class="article">
    {body}
  </article>

  <aside class="sidebar">
    <div class="sidebar-card">
      <div class="sidebar-title">Indice</div>
      <ul class="toc-list">
        {toc_items}
      </ul>
    </div>
    <div class="sidebar-cta">
      <h4>Scopri quanto risparmi</h4>
      <p>Carica la bolletta e confronta le offerte in 30 secondi</p>
      <a href="tel:0819131897" style="background:var(--orange);color:white;text-decoration:none;border-radius:var(--r-sm);padding:.6rem;font-weight:700;font-size:.84rem;display:block;margin-bottom:.6rem">&#128222; 081 91 31 897</a>
      <a href="/">&#9889; Analizza gratis &rarr;</a>
    </div>
  </aside>
</div>

<!-- CORRELATE -->
<section class="correlate-section">
  <div class="correlate-title">&#x1F4DA; Altre guide che potrebbero interessarti</div>
  <div class="correlate-grid">
    {correlate}
  </div>
</section>

{_FOOTER}
</body>
</html>"""


# ════════════════════════════════════════════════════════════════════════════
# GUIDA 1 — Mercato Libero vs Tutelato
# ════════════════════════════════════════════════════════════════════════════
def guida_mercato_libero() -> str:
    toc = [
        ("cosa-sono", "Cosa sono i due mercati"),
        ("differenze", "Le differenze chiave"),
        ("fine-tutela", "La fine del mercato tutelato"),
        ("clienti-vulnerabili", "I clienti vulnerabili"),
        ("quando-conviene", "Quando conviene il mercato libero"),
        ("come-scegliere", "Come scegliere l'offerta giusta"),
    ]
    body = """
<h2 id="cosa-sono">Cosa sono il mercato libero e il mercato tutelato?</h2>
<p>In Italia, per l'acquisto di energia elettrica e gas, sono coesistiti per anni due sistemi distinti: il <strong>mercato tutelato</strong> (o di maggior tutela) e il <strong>mercato libero</strong>.</p>
<p>Nel <strong>mercato tutelato</strong>, il prezzo dell'energia è fissato trimestralmente dall'ARERA (Autorità di Regolazione per Energia Reti e Ambiente) e aggiornato seguendo l'andamento dei mercati all'ingrosso. Non puoi scegliere il fornitore: vieni servito dall'operatore di maggior tutela della tua zona (solitamente Enel o un distributore locale).</p>
<p>Nel <strong>mercato libero</strong>, invece, puoi scegliere liberamente tra decine di fornitori — Enel Energia, A2A, Eni Plenitude, Sorgenia, Wekiwi e molti altri — ciascuno con le proprie offerte, prezzi e condizioni commerciali.</p>

<div class="box box-info">
  <div class="box-title">&#x2139; In breve</div>
  Tutelato = prezzo ARERA, fornitore assegnato, nessuna scelta.<br>
  Libero = prezzo contrattuale, fornitore scelto da te, piena concorrenza.
</div>

<h2 id="differenze">Le differenze chiave</h2>
<div class="data-table-wrap">
<table class="data-table">
  <thead><tr><th>Caratteristica</th><th>Mercato Tutelato</th><th>Mercato Libero</th></tr></thead>
  <tbody>
    <tr><td><strong>Prezzo</strong></td><td>Fissato da ARERA ogni trimestre</td><td>Libero o indicizzato (PUN/PSV)</td></tr>
    <tr><td><strong>Fornitore</strong></td><td>Assegnato (operatore di zona)</td><td>Scelto liberamente dal cliente</td></tr>
    <tr><td><strong>Contratto</strong></td><td>Condizioni standard ARERA</td><td>Negoziato, durata variabile</td></tr>
    <tr><td><strong>IVA domestici</strong></td><td>10%</td><td>10%</td></tr>
    <tr><td><strong>IVA PMI</strong></td><td>22%</td><td>22%</td></tr>
    <tr><td><strong>Oneri di sistema</strong></td><td>Identici per legge</td><td>Identici per legge</td></tr>
    <tr><td><strong>Recesso</strong></td><td>Libero in qualsiasi momento</td><td>Secondo condizioni contratto</td></tr>
  </tbody>
</table>
</div>
<p>È importante notare che gli <strong>oneri di sistema</strong> (oneri generali di sistema come A3, MCT, ecc.) e le <strong>accise</strong> sono identici in entrambi i mercati — sono componenti regolate che nessun fornitore può modificare. La vera differenza è solo nella <strong>componente materia energia</strong>.</p>

<h2 id="fine-tutela">La fine del mercato tutelato</h2>
<p>L'Italia ha avviato un processo graduale di chiusura del mercato tutelato, in linea con le direttive europee di liberalizzazione energetica.</p>
<p>Per le <strong>PMI e le utenze non domestiche</strong>, il servizio di maggior tutela si è concluso il <strong>1° gennaio 2024</strong>. Chi non aveva già un contratto sul mercato libero è stato automaticamente trasferito al <strong>Servizio a Tutele Graduali (STG)</strong>, un regime transitorio gestito da fornitori selezionati tramite aste ARERA.</p>
<p>Per i <strong>clienti domestici non vulnerabili</strong>, la fine della tutela è avvenuta il <strong>1° luglio 2024</strong>. Anche in questo caso, chi non aveva ancora scelto un fornitore è stato assegnato al STG.</p>

<div class="box box-warn">
  <div class="box-title">&#x26A0; Attenzione al STG</div>
  Il Servizio a Tutele Graduali non è necessariamente la scelta più conveniente. Le tariffe STG possono essere superiori a quelle del mercato libero. Se ti trovi in STG, è il momento di confrontare le offerte disponibili.
</div>

<h2 id="clienti-vulnerabili">I clienti vulnerabili: la tutela continua</h2>
<p>Esistono categorie di clienti che mantengono il diritto al <strong>Servizio di Tutela della Vulnerabilità (STV)</strong>, erogato da Enel Servizio Elettrico (o dal distributore locale) a condizioni regolate da ARERA.</p>
<p>Sono considerati vulnerabili i clienti che:</p>
<ul>
  <li>Hanno più di 75 anni</li>
  <li>Si trovano in condizioni di disagio economico (bonus energia)</li>
  <li>Sono affetti da gravi malattie che richiedono apparecchiature medico-terapeutiche alimentate elettricamente</li>
  <li>Risiedono in isole minori non interconnesse</li>
  <li>Sono in condizioni di disabilità (Legge 104/1992)</li>
</ul>
<p>Se ricadi in una di queste categorie, puoi restare nel STV indipendentemente dalla liberalizzazione del mercato.</p>

<h2 id="quando-conviene">Quando conviene davvero il mercato libero?</h2>
<p>Il mercato libero conviene quasi sempre rispetto al STG, ma non è detto che convenga rispetto al vecchio servizio di tutela ARERA. Dipende da tre fattori:</p>
<ul>
  <li><strong>Il tipo di offerta:</strong> un'offerta a prezzo fisso ti protegge dall'oscillazione del PUN; un'offerta variabile può essere più conveniente quando i prezzi scendono, ma rischiosa quando salgono.</li>
  <li><strong>Il tuo profilo di consumo:</strong> se usi molta energia nelle ore di punta (F1), un'offerta monoraria può essere svantaggiosa rispetto a una tariffazione multioraria.</li>
  <li><strong>Le clausole contrattuali:</strong> verifica sempre la durata del contratto, le penali di recesso e la trasparenza sulle eventuali variazioni di prezzo.</li>
</ul>

<div class="inline-cta">
  <h4>Scopri se il tuo fornitore attuale è competitivo</h4>
  <p>Carica la bolletta: l'AI estrae i tuoi dati e confronta automaticamente le offerte disponibili per il tuo profilo.</p>
  <a href="/">&#x1F50D; Analizza la tua bolletta gratis</a>
</div>

<h2 id="come-scegliere">Come scegliere l'offerta giusta sul mercato libero</h2>
<p>Prima di sottoscrivere un contratto sul mercato libero, verifica sempre questi elementi:</p>
<ol>
  <li><strong>Tipo di prezzo:</strong> fisso (proteggi dal rialzo), variabile indicizzato al PUN/PSV (segui il mercato), o misto.</li>
  <li><strong>Durata e rinnovo:</strong> quanto dura il prezzo bloccato? Si rinnova automaticamente? Con quale preavviso puoi recedere?</li>
  <li><strong>Quota fissa:</strong> molte offerte hanno una quota fissa mensile (commercializzazione) che incide molto su consumi bassi.</li>
  <li><strong>Sconto bifuel:</strong> se attivi luce e gas con lo stesso fornitore, puoi ottenere sconti dal 3% al 5%.</li>
  <li><strong>Servizio clienti:</strong> verifica la disponibilità e i canali di assistenza prima di firmare.</li>
</ol>
<p>Il <strong>Portale Offerte ARERA</strong> (<a href="https://www.ilportaleofferte.it" target="_blank" rel="noopener">ilportaleofferte.it</a>) è lo strumento ufficiale del governo per confrontare le offerte standardizzate dei fornitori. È un ottimo punto di partenza, ma considera che molte offerte promozionali non vengono caricate lì.</p>
"""
    return _page(
        path="/guida/differenza-mercato-libero-tutelato",
        title="Differenza tra Mercato Libero e Tutelato",
        desc="Scopri le differenze tra mercato libero e tutelato, quando conviene cambiare e cosa è successo con la fine della tutela nel 2024.",
        category="Mercato Energetico",
        read_min=6,
        toc=toc,
        body=body,
    )


# ════════════════════════════════════════════════════════════════════════════
# GUIDA 2 — Come leggere la bolletta della luce
# ════════════════════════════════════════════════════════════════════════════
def guida_bolletta_luce() -> str:
    toc = [
        ("sezioni", "Le sezioni della bolletta"),
        ("dati-anagrafici", "Dati anagrafici e tecnici"),
        ("materia-energia", "Spesa materia energia"),
        ("trasporto", "Trasporto e gestione contatore"),
        ("oneri-sistema", "Oneri di sistema"),
        ("imposte", "Imposte, accise e IVA"),
        ("totale", "Come si calcola il totale"),
        ("anomalie", "Segnali di anomalia"),
    ]
    body = """
<h2 id="sezioni">Le sezioni principali di una bolletta elettrica</h2>
<p>Una bolletta elettrica italiana è strutturata in modo standardizzato da ARERA. Può sembrare complessa, ma una volta compresa la logica diventa leggibile in pochi minuti. Le sezioni principali sono quattro:</p>
<ol>
  <li><strong>Dati anagrafici e tecnici</strong> — chi sei, dove sei, il tuo POD</li>
  <li><strong>Periodo e importi</strong> — quanto hai consumato e quanto devi pagare</li>
  <li><strong>Dettaglio costi</strong> — le quattro macro-voci della bolletta</li>
  <li><strong>Informazioni commerciali</strong> — contratto, fornitore, scadenze</li>
</ol>

<div class="box box-info">
  <div class="box-title">&#x2139; POD: il tuo "codice fiscale" elettrico</div>
  Il POD (Point of Delivery) è il codice univoco che identifica il tuo contatore elettrico. Ha il formato <strong>IT001E...</strong> e ti serve per qualsiasi operazione: cambiare fornitore, fare reclami, verificare i consumi storici.
</div>

<h2 id="dati-anagrafici">Dati anagrafici e tecnici</h2>
<p>Nella prima parte della bolletta trovi:</p>
<ul>
  <li><strong>Intestatario del contratto</strong> — nome/ragione sociale</li>
  <li><strong>Indirizzo di fornitura</strong> — dove si trova il contatore</li>
  <li><strong>Codice POD</strong> — identificativo univoco del punto di prelievo</li>
  <li><strong>Potenza impegnata</strong> — in kW, la potenza massima che puoi prelevare senza scattare il limitatore. Per usi domestici standard è 3 kW; per PMI può arrivare a 10, 15, 30 kW o oltre.</li>
  <li><strong>Tensione di fornitura</strong> — bassa tensione (BT) per utenze standard, media tensione (MT) per grandi industrie.</li>
  <li><strong>Periodo di fatturazione</strong> — le date di inizio e fine del periodo fatturato.</li>
  <li><strong>Tipo lettura</strong> — reale (lettura effettiva del contatore) o stimata (calcolo basato sui consumi storici). Le letture stimate vengono conguagliate nelle bollette successive.</li>
</ul>

<h2 id="materia-energia">Spesa per la materia energia</h2>
<p>Questa è la componente "pura" del costo dell'energia: quanto paghi per i kWh consumati. È l'unica voce su cui i fornitori del mercato libero competono.</p>
<p>Si divide in:</p>
<ul>
  <li><strong>Quota energia</strong> — il costo per kWh consumato, suddiviso per fasce orarie (F1, F2, F3) o in tariffa monoraria. Su questo agisce il prezzo del tuo contratto.</li>
  <li><strong>Perdite di rete</strong> — una piccola percentuale (circa 6-8%) che copre le dispersioni fisiche nella trasmissione dell'energia dalla centrale al tuo contatore.</li>
  <li><strong>Dispacciamento</strong> — costo per il bilanciamento della rete elettrica in tempo reale, gestito da Terna.</li>
</ul>
<p>Sul mercato libero, il prezzo della materia energia può essere <strong>fisso</strong> (bloccato per la durata del contratto), <strong>variabile indicizzato al PUN</strong> (segue il Prezzo Unico Nazionale mensile) o <strong>misto</strong>.</p>

<h2 id="trasporto">Trasporto e gestione del contatore</h2>
<p>Questa componente copre i costi dell'infrastruttura di rete — cavi, cabine, trasformatori — e la gestione del tuo contatore. È <strong>identica per tutti i fornitori</strong> della stessa zona: non puoi risparmiare su questa voce cambiando operatore.</p>
<p>Si compone di:</p>
<ul>
  <li><strong>Quota fissa</strong> — importo fisso al giorno o al mese, indipendente dai consumi</li>
  <li><strong>Quota potenza</strong> — proporzionale alla potenza impegnata (€/kW al mese)</li>
  <li><strong>Quota energia</strong> — proporzionale ai kWh consumati</li>
</ul>

<div class="box box-tip">
  <div class="box-title">&#x1F4A1; Consiglio pratico</div>
  Se i tuoi consumi sono bassi (meno di 100 kWh al mese), la quota fissa e la quota potenza incidono in modo sproporzionato sul costo totale. In questo caso, offerte con quota fissa bassa o zero sono preferibili anche se il prezzo per kWh è leggermente superiore.
</div>

<h2 id="oneri-sistema">Oneri generali di sistema</h2>
<p>Gli oneri di sistema sono costi collettivi che tutti gli utenti della rete elettrica italiana devono sostenere. Sono fissati da legge e non variano tra fornitori. Finanziano:</p>
<ul>
  <li><strong>A3</strong> — incentivi alle fonti rinnovabili (FER) e all'efficienza energetica. Storicamente la componente più pesante.</li>
  <li><strong>MCT</strong> — misure di compensazione territoriale per le zone dove si trovano impianti nucleari dismessi o depositi di scorie.</li>
  <li><strong>A2</strong> — rimborsi per le imprese "energivore" esentate dagli oneri.</li>
  <li><strong>ASOS/ARIM</strong> — sostegno alle fonti rinnovabili e agli impianti CIP6.</li>
</ul>
<p>Gli oneri di sistema hanno subito forti oscillazioni negli ultimi anni: ARERA li ha azzerati o ridotti drasticamente durante il caro-energia del 2022-2023 come misura di contenimento, per poi ripristinarli gradualmente.</p>

<h2 id="imposte">Imposte, accise e IVA</h2>
<p>L'ultima macro-voce raggruppa le imposte erariali.</p>
<ul>
  <li><strong>Accise sull'energia elettrica</strong> — imposte statali proporzionate ai consumi (€/kWh). Variano in base all'uso (domestico, industriale) e alla fascia di consumo annuo. Le prime 1.800 kWh/anno per usi domestici beneficiano di un'aliquota ridotta.</li>
  <li><strong>Addizionale provinciale</strong> — in alcune province si aggiunge un'ulteriore imposta locale.</li>
  <li><strong>Canone RAI</strong> — se sei un cliente domestico, dal 2016 il canone RAI da 90 €/anno è addebitato sulla bolletta della luce (7,50 €/mese).</li>
  <li><strong>IVA</strong> — si applica su tutte le voci precedenti:
    <ul>
      <li>10% per utenze domestiche (D2 residenti, D3 non residenti, CDO condomini)</li>
      <li>22% per PMI e uso non domestico (BTA)</li>
    </ul>
  </li>
</ul>

<h2 id="totale">Come si calcola il totale della bolletta</h2>
<p>Il totale si ottiene sommando le quattro macro-voci <strong>al lordo dell'IVA</strong>:</p>
<pre style="background:var(--bg);padding:1rem;border-radius:var(--r-sm);font-size:.88rem;overflow-x:auto;line-height:1.8">
Totale = (Materia Energia + Trasporto + Oneri di Sistema + Accise) × (1 + aliquota IVA)
</pre>
<p>Per controllare il costo unitario effettivo della tua bolletta, dividi la <strong>sola spesa materia energia</strong> (al lordo IVA) per i kWh consumati nel periodo.</p>

<div class="inline-cta">
  <h4>Lascia fare il calcolo all'AI</h4>
  <p>Carica la bolletta: Bollette Risparmio estrae ogni voce automaticamente e calcola il tuo costo unitario reale.</p>
  <a href="/">&#x1F4CA; Analizza la bolletta gratis</a>
</div>

<h2 id="anomalie">Segnali di anomalia da verificare</h2>
<p>Ecco i casi più comuni in cui una bolletta potrebbe contenere errori o addebiti ingiustificati:</p>
<ul>
  <li><strong>Molte letture stimate consecutive:</strong> se il contatore non viene letto per mesi, i consumi stimati possono non riflettere quelli reali. Il conguaglio successivo può essere molto alto.</li>
  <li><strong>Potenza impegnata errata:</strong> se la potenza indicata è superiore a quella realmente contrattualizzata, stai pagando la quota potenza su una base errata.</li>
  <li><strong>IVA al 22% su utenza domestica:</strong> un errore di classificazione del profilo può far applicare l'aliquota IVA sbagliata.</li>
  <li><strong>Canone RAI addebitato su seconda casa:</strong> il canone RAI spetta una sola volta per nucleo familiare. Se hai più utenze intestate allo stesso soggetto, solo una dovrebbe avere il canone.</li>
  <li><strong>Scadenza non aggiornata dopo il cambio fornitore:</strong> possono verificarsi doppi addebiti nel periodo di switching.</li>
</ul>
"""
    return _page(
        path="/guida/come-leggere-bolletta-luce",
        title="Come leggere la bolletta della luce",
        desc="Guida completa alle voci della bolletta elettrica italiana: materia energia, trasporto, oneri di sistema, accise e IVA. Impara a verificare i costi e identificare anomalie.",
        category="Bolletta Elettrica",
        read_min=7,
        toc=toc,
        body=body,
    )


# ════════════════════════════════════════════════════════════════════════════
# GUIDA 3 — Fasce orarie F1, F2, F3
# ════════════════════════════════════════════════════════════════════════════
def guida_fasce_orarie() -> str:
    toc = [
        ("cosa-sono", "Cosa sono le fasce orarie"),
        ("orari", "Gli orari delle fasce"),
        ("biorario", "Tariffazione bioraria F1/F23"),
        ("monorario", "Tariffazione monoraria"),
        ("chi-usa", "Chi usa quale tariffa"),
        ("ottimizzare", "Come ottimizzare i consumi"),
        ("contatori", "Contatori intelligenti e fasce"),
    ]
    body = """
<h2 id="cosa-sono">Cosa sono le fasce orarie dell'energia elettrica?</h2>
<p>Le <strong>fasce orarie</strong> sono una suddivisione delle ore della settimana in base al livello di domanda di energia elettrica sulla rete. L'idea è semplice: l'energia consumata nei momenti di picco (quando tutti accendono tutto) costa di più di quella consumata di notte o nel weekend, quando la rete è scarica.</p>
<p>In Italia, il sistema di fasce orarie è definito da ARERA e divide la settimana in tre fasce: <strong>F1, F2 e F3</strong>. Il sistema è stato introdotto per incentivare lo spostamento dei consumi verso le ore a minor carico di rete, riducendo il picco di domanda e abbassando i costi di bilanciamento del sistema elettrico nazionale.</p>

<div class="fascia-grid">
  <div class="fascia-card fascia-f1">
    <div class="fascia-label">F1</div>
    <div class="fascia-name">Picco</div>
    <div class="fascia-hours">Lun–Ven<br>08:00–19:00</div>
  </div>
  <div class="fascia-card fascia-f2">
    <div class="fascia-label">F2</div>
    <div class="fascia-name">Intermedia</div>
    <div class="fascia-hours">Lun–Ven 07–08 e 19–23<br>Sabato 07:00–23:00</div>
  </div>
  <div class="fascia-card fascia-f3">
    <div class="fascia-label">F3</div>
    <div class="fascia-name">Fuori Picco</div>
    <div class="fascia-hours">Lun–Sab 23–07<br>Domenica e festivi: tutto il giorno</div>
  </div>
</div>

<h2 id="orari">Gli orari esatti delle fasce</h2>
<p>Ecco la ripartizione precisa delle fasce orarie nel corso della settimana:</p>
<div class="data-table-wrap">
<table class="data-table">
  <thead><tr><th>Fascia</th><th>Giorni</th><th>Ore</th><th>Costo relativo</th></tr></thead>
  <tbody>
    <tr><td><strong>F1 — Picco</strong></td><td>Lunedì–Venerdì</td><td>08:00–19:00</td><td>Più alto</td></tr>
    <tr><td><strong>F2 — Intermedia</strong></td><td>Lun–Ven + Sabato</td><td>07:00–08:00 e 19:00–23:00 (Lun-Ven)<br>07:00–23:00 (Sabato)</td><td>Medio</td></tr>
    <tr><td><strong>F3 — Fuori picco</strong></td><td>Tutti i giorni</td><td>23:00–07:00 (Lun-Sab)<br>Tutto il giorno domenica e festivi</td><td>Più basso</td></tr>
  </tbody>
</table>
</div>
<p>I <strong>festivi nazionali</strong> (Capodanno, Pasquetta, Festa della Repubblica, Ferragosto, ecc.) seguono lo stesso schema della domenica: rientrano integralmente nella fascia F3.</p>

<div class="box box-info">
  <div class="box-title">&#x2139; Le ore si riferiscono all'ora legale/solare?</div>
  Sì, le fasce si basano sull'<strong>ora locale italiana</strong>: cambiano con l'ora legale in estate e quella solare in inverno. I contatori intelligenti (smart meter) applicano automaticamente il cambio d'ora.
</div>

<h2 id="biorario">Tariffazione bioraria F1/F23</h2>
<p>La maggior parte delle offerte domestiche non applica una distinzione tra F2 e F3, ma usa la cosiddetta <strong>tariffazione bioraria</strong>, che raggruppa F2 e F3 in un'unica fascia chiamata <strong>F23</strong> (o "fuori picco").</p>
<p>In una tariffa bioraria vedrai quindi solo due prezzi in bolletta:</p>
<ul>
  <li><strong>Prezzo F1</strong> — per i kWh consumati nelle ore di picco (lun-ven 8-19)</li>
  <li><strong>Prezzo F23</strong> — per tutti gli altri kWh (serate, notti, weekend)</li>
</ul>
<p>La differenza tra F1 e F23 varia a seconda del fornitore, ma tipicamente F1 costa tra il 15% e il 30% in più di F23.</p>

<h2 id="monorario">Tariffazione monoraria</h2>
<p>Alcune offerte applicano un <strong>unico prezzo</strong> per tutti i kWh consumati, indipendentemente dall'ora. Si parla di tariffa <strong>monoraria</strong> o <strong>flat</strong>.</p>
<p>La tariffa monoraria è conveniente se:</p>
<ul>
  <li>I tuoi consumi sono molto concentrati nelle ore di punta (lavori da casa di giorno)</li>
  <li>Non vuoi preoccuparti di spostare i carichi in orari particolari</li>
  <li>Il prezzo monorario offerto è competitivo rispetto alla media ponderata delle fasce</li>
</ul>
<p>È meno conveniente se usi molto l'energia di notte o nel weekend (lavatrice, lavastoviglie, ricarica auto elettrica): in questi casi una tariffa bioraria o trioraria ti permette di sfruttare il prezzo F3 più basso.</p>

<h2 id="chi-usa">Chi usa quale tariffazione?</h2>
<div class="data-table-wrap">
<table class="data-table">
  <thead><tr><th>Profilo</th><th>Tariffazione tipica</th><th>Note</th></tr></thead>
  <tbody>
    <tr><td><strong>D2 Domestico Residente</strong></td><td>Bioraria F1/F23 o Monoraria</td><td>La più comune per le famiglie</td></tr>
    <tr><td><strong>D3 Non Residente</strong></td><td>Bioraria F1/F23</td><td>Seconda casa, uso saltuario</td></tr>
    <tr><td><strong>BTA – PMI</strong></td><td>Trioraria F1/F2/F3</td><td>Uffici e negozi usano le ore di picco</td></tr>
    <tr><td><strong>CDO – Condominio</strong></td><td>Bioraria o Trioraria</td><td>Parti comuni: ascensori, luci scala</td></tr>
  </tbody>
</table>
</div>

<h2 id="ottimizzare">Come ottimizzare i consumi in base alle fasce</h2>
<p>Spostare i grandi carichi nelle ore F3 (notti e domeniche) può generare un risparmio reale, specialmente se hai carichi ad alta potenza come:</p>

<ul class="step-list">
  <li>
    <div class="step-num">&#x1F9FA;</div>
    <div class="step-content"><strong>Lavatrice e lavastoviglie</strong><br>
    Programma i lavaggi notturni (dopo le 23:00) o domenicali. Molti elettrodomestici moderni hanno un timer integrato. Il risparmio rispetto a lavaggi in orario F1 può essere del 20-30% sulla quota energia.</div>
  </li>
  <li>
    <div class="step-num">&#x1F697;</div>
    <div class="step-content"><strong>Ricarica auto elettrica</strong><br>
    La ricarica di un'auto elettrica può consumare 10-20 kWh per ciclo. Caricarla di notte (F3) invece che il pomeriggio (F1) può fare una differenza significativa in bolletta su base mensile.</div>
  </li>
  <li>
    <div class="step-num">&#x1F321;</div>
    <div class="step-content"><strong>Scaldacqua elettrico</strong><br>
    Se hai uno scaldacqua a resistenza, programmare il riscaldamento nelle ore notturne può portare risparmi consistenti.</div>
  </li>
  <li>
    <div class="step-num">&#x26A1;</div>
    <div class="step-content"><strong>Impianto fotovoltaico</strong><br>
    Con il fotovoltaico produci energia nelle ore F1 (ore di picco diurno). Se hai anche un sistema di accumulo, puoi immagazzinare l'energia prodotta e usarla la sera in F2, riducendo ulteriormente i prelievi in F1.</div>
  </li>
</ul>

<div class="box box-ok">
  <div class="box-title">&#x2705; Regola pratica</div>
  Se lavori fuori casa di giorno, i tuoi consumi sono naturalmente spostati verso F2/F3 (serate e weekend). In questo caso una tariffa bioraria o trioraria è quasi sempre più conveniente di una monoraria.
</div>

<div class="inline-cta">
  <h4>Qual è la tariffa migliore per il tuo profilo?</h4>
  <p>Carica la bolletta: Bollette Risparmio analizza la tua ripartizione F1/F2/F3 e identifica l'offerta più conveniente in base ai tuoi consumi reali.</p>
  <a href="/">&#x26A1; Scopri la tariffa migliore per te</a>
</div>

<h2 id="contatori">Contatori intelligenti e fasce orarie</h2>
<p>I moderni <strong>contatori elettronici di seconda generazione</strong> (contatori 2G o "smart meter"), obbligatori per tutte le nuove installazioni, registrano i consumi per fascia oraria con granularità di 15 minuti. Questo significa che il distributore ha una visione precisa di quando consumi energia.</p>
<p>Grazie agli smart meter puoi:</p>
<ul>
  <li>Verificare online i tuoi consumi ora per ora sul portale del distributore</li>
  <li>Ricevere bollette più accurate (meno letture stimate)</li>
  <li>Attivare tariffe dinamiche in futuro, legate all'andamento del PUN in tempo reale</li>
</ul>
"""
    return _page(
        path="/guida/fasce-orarie-f1-f2-f3",
        title="Fasce orarie F1, F2, F3: tutto quello che devi sapere",
        desc="Cosa sono le fasce orarie F1, F2, F3 dell'energia elettrica, quali ore coprono e come usarle per ottimizzare i consumi e risparmiare in bolletta.",
        category="Tariffe Elettriche",
        read_min=6,
        toc=toc,
        body=body,
    )


# ════════════════════════════════════════════════════════════════════════════
# GUIDA 4 — Come cambiare fornitore
# ════════════════════════════════════════════════════════════════════════════
def guida_cambiare_fornitore() -> str:
    toc = [
        ("diritto", "Hai il diritto di cambiare"),
        ("prima-di-cambiare", "Prima di cambiare"),
        ("procedura", "La procedura passo per passo"),
        ("tempi", "I tempi dello switching"),
        ("cosa-non-cambia", "Cosa non cambia"),
        ("debiti-bollette", "Debiti e bollette vecchie"),
        ("errori-comuni", "Errori da evitare"),
    ]
    body = """
<h2 id="diritto">Hai il diritto di cambiare fornitore in qualsiasi momento</h2>
<p>Cambiare fornitore di luce o gas è un diritto sancito dalla normativa italiana ed europea. Non ci sono penali per il recesso se sei ancora nel periodo di tutela o se il tuo contratto sul mercato libero non prevede penali specifiche.</p>
<p>La procedura è gratuita: non paghi nulla per il cambio. La rete fisica — i cavi, i tubi del gas, i contatori — resta identica. Cambia solo chi ti vende l'energia.</p>

<div class="box box-ok">
  <div class="box-title">&#x2705; Il cambio non interrompe mai la fornitura</div>
  Cambiare fornitore non comporta interruzioni di corrente o gas. La fornitura è continua — è solo la fatturazione che passa da un operatore all'altro.
</div>

<h2 id="prima-di-cambiare">Cosa fare prima di cambiare</h2>
<p>Prima di sottoscrivere un nuovo contratto, fai queste verifiche:</p>

<ul class="step-list">
  <li>
    <div class="step-num">1</div>
    <div class="step-content"><strong>Recupera il codice POD (luce) o PDR (gas)</strong><br>
    Questi codici identificano il tuo punto di fornitura e sono indispensabili per il nuovo contratto. Li trovi sulla bolletta attuale, in evidenza nella prima pagina.</div>
  </li>
  <li>
    <div class="step-num">2</div>
    <div class="step-content"><strong>Verifica le condizioni di recesso del contratto attuale</strong><br>
    Se sei sul mercato libero, controlla se il tuo contratto prevede penali di recesso anticipato o un preavviso minimo (di solito 30 giorni). Se sei in tutela o STG, il recesso è libero senza penali.</div>
  </li>
  <li>
    <div class="step-num">3</div>
    <div class="step-content"><strong>Confronta le offerte tenendo conto dei tuoi consumi reali</strong><br>
    Usa i dati dell'ultima bolletta: consumo in kWh (luce) o Smc (gas), fasce orarie, profilo utenza. Un risparmio teorico calcolato su consumi medi può non rispecchiare la tua situazione.</div>
  </li>
  <li>
    <div class="step-num">4</div>
    <div class="step-content"><strong>Leggi le condizioni generali di fornitura</strong><br>
    Verifica durata del prezzo fisso, modalità di rinnovo, preavviso per il recesso, canali di assistenza clienti e modalità di pagamento disponibili.</div>
  </li>
</ul>

<h2 id="procedura">La procedura passo per passo</h2>
<p>Una volta scelto il nuovo fornitore, la procedura è standardizzata a livello nazionale:</p>

<ul class="step-list">
  <li>
    <div class="step-num">1</div>
    <div class="step-content"><strong>Sottoscrivi il contratto con il nuovo fornitore</strong><br>
    Puoi farlo online, per telefono o in un punto vendita. Avrai bisogno di: codice fiscale/P.IVA, codice POD o PDR, IBAN per il pagamento con domiciliazione.</div>
  </li>
  <li>
    <div class="step-num">2</div>
    <div class="step-content"><strong>Diritto di ripensamento (10 giorni)</strong><br>
    Hai 10 giorni lavorativi dalla firma del contratto per recedere senza costi se hai stipulato fuori dai locali commerciali (online, telefono, porta a porta). Questo è il cosiddetto "jus poenitendi" del Codice del Consumo.</div>
  </li>
  <li>
    <div class="step-num">3</div>
    <div class="step-content"><strong>Il nuovo fornitore gestisce tutto il resto</strong><br>
    Il processo di switching è gestito automaticamente attraverso i sistemi informativi del distributore locale (SNAM per il gas, E-Distribuzione/distributore locale per la luce). Non devi contattare il vecchio fornitore.</div>
  </li>
  <li>
    <div class="step-num">4</div>
    <div class="step-content"><strong>Ricevi la bolletta di chiusura dal vecchio fornitore</strong><br>
    Il vecchio fornitore emetterà una bolletta finale per il periodo di consumo non ancora fatturato. Questa può essere basata su una lettura reale del contatore o stimata, con successivo conguaglio.</div>
  </li>
  <li>
    <div class="step-num">5</div>
    <div class="step-content"><strong>Inizia a ricevere le bollette dal nuovo fornitore</strong><br>
    La prima bolletta del nuovo fornitore coprirà il periodo a partire dalla data di switching.</div>
  </li>
</ul>

<h2 id="tempi">I tempi dello switching</h2>
<p>I tempi massimi di switching sono regolati da ARERA:</p>
<div class="data-table-wrap">
<table class="data-table">
  <thead><tr><th>Tipo di fornitura</th><th>Tempo massimo switching</th><th>Note</th></tr></thead>
  <tbody>
    <tr><td><strong>Energia Elettrica</strong></td><td>4 settimane (dal 2024)</td><td>Prima erano 3 mesi, ridotti per accelerare la concorrenza</td></tr>
    <tr><td><strong>Gas Naturale</strong></td><td>4 settimane (dal 2024)</td><td>Allineato alla luce con la direttiva europea</td></tr>
  </tbody>
</table>
</div>
<p>In pratica, dalla firma del contratto all'attivazione effettiva passano generalmente 2-4 settimane. Il nuovo fornitore ti comunicherà la data esatta di decorrenza del nuovo contratto.</p>

<div class="box box-warn">
  <div class="box-title">&#x26A0; Attenzione alle offerte con "sconto immediato"</div>
  Alcune campagne commerciali promettono sconti che si applicano solo dal secondo o terzo mese. Verifica sempre da quando decorre effettivamente l'offerta promozionata.
</div>

<h2 id="cosa-non-cambia">Cosa non cambia con il cambio fornitore</h2>
<p>Molti clienti hanno paura di cambiare fornitore per timore di complicazioni. Ecco cosa rimane assolutamente invariato:</p>
<ul>
  <li>&#9989; La <strong>qualità dell'energia</strong> erogata (è sempre la stessa rete)</li>
  <li>&#9989; Il <strong>contatore</strong> e l'infrastruttura fisica</li>
  <li>&#9989; Il numero di emergenza del distributore (guasti, blackout)</li>
  <li>&#9989; Le <strong>letture dei consumi</strong> e la loro continuità</li>
  <li>&#9989; I <strong>bonus sociali</strong> (bonus energia, bonus gas): seguono il cliente, non il fornitore</li>
  <li>&#9989; La <strong>potenza impegnata</strong> contrattualizzata</li>
</ul>

<h2 id="debiti-bollette">Debiti e bollette arretrate con il vecchio fornitore</h2>
<p>Se hai bollette insolute con il vecchio fornitore, <strong>non puoi cambiare fornitore finché non le saldi</strong>. Il sistema informatico del distributore blocca il processo di switching in presenza di morosità accertata.</p>
<p>Se sei in contestazione su una bolletta (la ritieni errata o gonfiata), puoi comunque avviare il cambio mentre la contestazione è in corso, a condizione di aver pagato la parte non contestata. Per contestare una bolletta, rivolgiti all'ufficio reclami del tuo fornitore e, in caso di mancata risposta entro 40 giorni, allo Sportello del Consumatore di ARERA.</p>

<div class="inline-cta">
  <h4>Qual è l'offerta migliore per te?</h4>
  <p>Carica la bolletta attuale: in 30 secondi Bollette Risparmio confronta le offerte e ti dice quanto potresti risparmiare cambiando fornitore.</p>
  <a href="/">&#x1F4B0; Scopri quanto risparmi</a>
</div>

<h2 id="errori-comuni">Errori comuni da evitare</h2>
<ul>
  <li><strong>Confrontare solo il prezzo del kWh</strong> senza considerare la quota fissa mensile e gli oneri di trasporto inclusi o esclusi dall'offerta.</li>
  <li><strong>Ignorare la durata del prezzo fisso:</strong> un prezzo conveniente oggi può salire dopo 12 mesi se il contratto non viene rinnovato manualmente.</li>
  <li><strong>Firmare contratti porta a porta senza leggere:</strong> i venditori a domicilio usano spesso tecniche di pressione. Hai sempre 10 giorni per recedere, ma meglio non firmare in fretta.</li>
  <li><strong>Dimenticarsi di comunicare l'IBAN:</strong> alcuni fornitori non attivano la domiciliazione bancaria automaticamente; senza di essa potresti ricevere bollette con metodi di pagamento più costosi.</li>
  <li><strong>Non autodenunciare i consumi al momento del passaggio:</strong> fotografa il contatore il giorno dello switching per avere una prova in caso di dispute sulla lettura iniziale.</li>
</ul>
"""
    return _page(
        path="/guida/come-cambiare-fornitore-energia",
        title="Come cambiare fornitore di luce e gas",
        desc="Guida completa per cambiare fornitore di energia in Italia: diritti, tempi, procedura passo per passo, cosa non cambia e gli errori da evitare.",
        category="Cambio Fornitore",
        read_min=7,
        toc=toc,
        body=body,
    )


# ════════════════════════════════════════════════════════════════════════════
# GUIDA 5 — PUN e PSV
# ════════════════════════════════════════════════════════════════════════════
def guida_pun_psv() -> str:
    toc = [
        ("cos-e-il-pun", "Cos'è il PUN"),
        ("come-si-forma", "Come si forma il prezzo"),
        ("pun-in-bolletta", "Il PUN nella tua bolletta"),
        ("cos-e-il-psv", "Cos'è il PSV"),
        ("fisso-variabile", "Fisso o variabile: quale scegliere"),
        ("dove-trovare", "Dove trovare i valori aggiornati"),
    ]
    body = """
<h2 id="cos-e-il-pun">Cos'è il PUN (Prezzo Unico Nazionale)?</h2>
<p>Il <strong>PUN</strong> — acronimo di <strong>Prezzo Unico Nazionale</strong> — è il prezzo medio all'ingrosso dell'energia elettrica in Italia. È il prezzo al quale i produttori e gli importatori vendono l'energia agli operatori di mercato sulla <strong>Borsa Elettrica Italiana (GME)</strong>, gestita dal Gestore dei Mercati Energetici.</p>
<p>Il PUN viene calcolato come <strong>media ponderata dei prezzi zonali</strong> orari (Italia Nord, Centro-Nord, Centro-Sud, Sud, Sicilia, Sardegna), ponderata per i volumi scambiati in ogni ora. Viene pubblicato quotidianamente e aggregato su base mensile da ARERA.</p>
<p>Il PUN si misura in <strong>€/MWh</strong> (o equivalentemente in c€/kWh), il che significa che indica il costo per ogni megawattora di energia acquistata sul mercato all'ingrosso.</p>

<div class="box box-info">
  <div class="box-title">&#x2139; PUN: cifre recenti</div>
  Dopo i picchi del 2022 (oltre 300 €/MWh), il PUN si è normalizzato: nel 2025-2026 si è stabilizzato tra 100 e 135 €/MWh (circa 10-13,5 c€/kWh). I valori storici mensili sono pubblicati da ARERA sul Portale Offerte.
</div>

<h2 id="come-si-forma">Come si forma il prezzo dell'energia elettrica?</h2>
<p>Sul Mercato del Giorno Prima (MGP) — il principale mercato della Borsa Elettrica — produttori e acquirenti presentano le loro offerte di vendita e acquisto per ogni ora del giorno successivo. L'incrocio tra domanda e offerta determina il prezzo zonale per ogni ora.</p>
<p>Fattori che influenzano il PUN:</p>
<ul>
  <li><strong>Produzione da fonti rinnovabili:</strong> quando sole e vento producono molto, l'offerta aumenta e il prezzo scende. Per questo il PUN è tipicamente più basso nei mesi primaverili (molto fotovoltaico).</li>
  <li><strong>Prezzo del gas naturale:</strong> in Italia molte centrali termoelettriche bruciano gas. Quando il gas è caro, lo è anche l'energia elettrica.</li>
  <li><strong>Domanda stagionale:</strong> picchi in estate (aria condizionata) e in inverno (riscaldamento con pompe di calore).</li>
  <li><strong>Interconnessioni europee:</strong> importazioni da Francia (nucleare), Austria e Svizzera (idro) influenzano il prezzo nazionale.</li>
  <li><strong>Prezzo del CO₂:</strong> i permessi di emissione ETS europei incidono sul costo di produzione delle centrali fossili.</li>
</ul>

<h2 id="pun-in-bolletta">Come il PUN influenza la tua bolletta</h2>
<p>Il PUN entra direttamente in bolletta solo se hai un'<strong>offerta a prezzo variabile indicizzato al PUN</strong>. In questo caso, il prezzo che paghi per ogni kWh consumato è calcolato come:</p>
<pre style="background:var(--bg);padding:1rem;border-radius:var(--r-sm);font-size:.9rem;overflow-x:auto;line-height:1.8">
Prezzo per kWh = PUN mensile (€/kWh) + Spread del fornitore (€/kWh)
</pre>
<p>Lo <strong>spread</strong> è il margine commerciale del fornitore, fisso per tutta la durata del contratto. È la remunerazione del fornitore per il servizio di approvvigionamento e commercializzazione.</p>
<p>Esempio pratico: se il PUN di gennaio 2026 è 0,1327 €/kWh e il tuo contratto ha spread 0,018 €/kWh, pagherai 0,1507 €/kWh per ogni kWh in F1 consumato a gennaio.</p>

<div class="data-table-wrap">
<table class="data-table">
  <thead><tr><th>Tipo offerta</th><th>Come si calcola il prezzo</th><th>Rischio</th></tr></thead>
  <tbody>
    <tr><td><strong>Fisso</strong></td><td>Prezzo bloccato per la durata del contratto</td><td>Basso: sai sempre quanto paghi</td></tr>
    <tr><td><strong>Variabile PUN</strong></td><td>PUN mensile + spread fisso</td><td>Medio-alto: segue il mercato</td></tr>
    <tr><td><strong>Tutelato (storico)</strong></td><td>Prezzo ARERA aggiornato ogni trimestre</td><td>Medio: aggiornamento ritardato</td></tr>
  </tbody>
</table>
</div>

<h2 id="cos-e-il-psv">Cos'è il PSV (Punto di Scambio Virtuale)?</h2>
<p>Il <strong>PSV</strong> — <strong>Punto di Scambio Virtuale</strong> — è l'equivalente del PUN per il <strong>gas naturale</strong>. È il prezzo all'ingrosso del gas sulla piattaforma di bilanciamento italiana gestita da Snam.</p>
<p>Il PSV si misura in <strong>€/MWh termico</strong> o in <strong>€/Smc</strong> (euro per metro cubo standard). Le offerte gas indicizzate al PSV funzionano con la stessa logica delle offerte luce indicizzate al PUN:</p>
<pre style="background:var(--bg);padding:1rem;border-radius:var(--r-sm);font-size:.9rem;overflow-x:auto;line-height:1.8">
Prezzo per Smc = PSV mensile (€/Smc) + Spread del fornitore (€/Smc)
</pre>
<p>Il PSV è influenzato dal prezzo internazionale del gas (TTF europeo, prezzi LNG), dalla stagionalità (picco invernale per il riscaldamento), dalle riserve negli stoccaggi nazionali e dalla disponibilità delle infrastrutture di importazione.</p>

<div class="box box-warn">
  <div class="box-title">&#x26A0; Volatilità del PSV nel 2022</div>
  Durante la crisi energetica del 2022, il PSV ha raggiunto picchi di oltre 3 €/Smc (contro i tipici 0,3–0,5 €/Smc). Chi aveva offerte indicizzate al PSV ha visto moltiplicare la bolletta. Chi aveva un fisso era protetto, ma spesso il fisso era stato stipulato prima della crisi a prezzi già elevati.
</div>

<h2 id="fisso-variabile">Fisso o variabile: quale conviene?</h2>
<p>Non esiste una risposta universale. La scelta dipende dalla tua propensione al rischio e dalle aspettative sui prezzi futuri.</p>
<p><strong>Il prezzo fisso conviene quando:</strong></p>
<ul>
  <li>I prezzi di mercato sono bassi e ti aspetti che risalgano (blocchi il vantaggio)</li>
  <li>Vuoi certezza sulla spesa futura (budget familiare o aziendale)</li>
  <li>Il differenziale fisso/variabile è contenuto (spread basso)</li>
</ul>
<p><strong>Il prezzo variabile conviene quando:</strong></p>
<ul>
  <li>I prezzi di mercato sono alti e prevedi una discesa</li>
  <li>Lo spread del fornitore è molto basso (meno di 1 c€/kWh)</li>
  <li>Puoi monitorare il mercato e cambiare contratto rapidamente se i prezzi salgono</li>
</ul>

<div class="box box-tip">
  <div class="box-title">&#x1F4A1; La strategia mista</div>
  Alcune PMI con consumi elevati optano per una strategia mista: fissano il prezzo per una parte dei consumi prevedibili (base load) e lasciano variabile la parte residua. Questa tecnica richiede però un monitoraggio attivo del mercato.
</div>

<div class="inline-cta">
  <h4>Vuoi sapere qual è il PUN attuale?</h4>
  <p>Bollette Risparmio aggiorna mensilmente gli indici PUN e PSV da ARERA e li usa per calcolare le offerte variabili più convenienti per il tuo profilo.</p>
  <a href="/">&#x1F4C8; Confronta le offerte indicizzate</a>
</div>

<h2 id="dove-trovare">Dove trovare i valori aggiornati di PUN e PSV</h2>
<p>I valori mensili di PUN e PSV sono pubblicati da fonti ufficiali:</p>
<ul>
  <li><strong>ARERA — Portale Offerte:</strong> <a href="https://www.ilportaleofferte.it/portaleOfferte/it/open-data.page" target="_blank" rel="noopener">ilportaleofferte.it</a> pubblica i prezzi storici mensili usati come riferimento per le offerte indicizzate.</li>
  <li><strong>GME (Gestore Mercati Energetici):</strong> <a href="https://www.mercatoelettrico.org" target="_blank" rel="noopener">mercatoelettrico.org</a> pubblica i prezzi zonali orari dell'elettricità in tempo reale.</li>
  <li><strong>Snam Rete Gas:</strong> pubblica i prezzi PSV giornalieri sulla piattaforma di bilanciamento.</li>
  <li><strong>Bollette Risparmio:</strong> il pannello admin aggiorna automaticamente gli indici mensili ARERA per il calcolo delle offerte variabili.</li>
</ul>
"""
    return _page(
        path="/guida/pun-psv-cosa-sono",
        title="PUN e PSV: cosa sono e come influenzano la bolletta",
        desc="Spiegazione di PUN (Prezzo Unico Nazionale) e PSV (Punto di Scambio Virtuale): gli indici del mercato all'ingrosso dell'energia che determinano il prezzo delle offerte variabili.",
        category="Indici di Mercato",
        read_min=7,
        toc=toc,
        body=body,
    )


# ════════════════════════════════════════════════════════════════════════════
# PAGINA INDICE GUIDE
# ════════════════════════════════════════════════════════════════════════════
def guida_index() -> str:
    today = datetime.now().strftime("%d %B %Y")
    cards_html = ""
    icons = ["&#x1F4CA;", "&#x1F4C4;", "&#x23F1;", "&#x1F504;", "&#x1F4C8;"]
    mins = [6, 7, 6, 7, 7]
    for i, (path, title, desc) in enumerate(_ALL_GUIDES):
        cards_html += f"""
<a href="{path}" style="background:white;border:1.5px solid var(--border);border-radius:var(--r);padding:1.5rem;text-decoration:none;display:block;transition:all var(--t)" onmouseover="this.style.boxShadow='0 8px 24px rgba(13,27,42,.12)';this.style.transform='translateY(-2px)'" onmouseout="this.style.boxShadow='none';this.style.transform='none'">
  <div style="font-size:1.6rem;margin-bottom:.75rem">{icons[i]}</div>
  <div style="font-family:'Bricolage Grotesque',sans-serif;font-weight:800;font-size:1rem;color:var(--navy);margin-bottom:.4rem">{title}</div>
  <div style="font-size:.84rem;color:var(--muted);line-height:1.6;margin-bottom:.75rem">{desc}</div>
  <div style="font-size:.75rem;color:var(--blue);font-weight:600">Leggi la guida ({mins[i]} min) &#x2192;</div>
</a>"""

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Guide al risparmio energia — Bollette Risparmio</title>
<meta name="description" content="Guide pratiche e aggiornate su bollette luce e gas, mercato libero, fasce orarie, come cambiare fornitore e indici PUN e PSV.">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{SITE_URL}/guide">
<meta property="og:title" content="Guide energia — Bollette Risparmio">
<meta property="og:description" content="Guide pratiche su bollette luce e gas, mercato libero, fasce orarie e risparmio energetico.">
<meta property="og:url" content="{SITE_URL}/guide">
<meta property="og:locale" content="it_IT">
<script type="application/ld+json">{{
  "@context": "https://schema.org",
  "@type": "CollectionPage",
  "name": "Guide al risparmio energia",
  "url": "{SITE_URL}/guide",
  "description": "Guide pratiche su bollette luce e gas per famiglie e PMI italiane",
  "publisher": {{"@type":"Organization","name":"Bollette Risparmio","url":"{SITE_URL}"}}
}}</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,700;12..96,800&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>{_CSS}</style>
</head>
<body>
{_NAV}

<div style="background:linear-gradient(160deg,#f0f6ff,#e8f4f8);padding:4rem 1.5rem 3rem;border-bottom:1px solid var(--border)">
  <div style="max-width:860px;margin:0 auto;text-align:center">
    <div style="display:inline-block;background:var(--blue-l);color:var(--blue);font-size:.72rem;font-weight:700;padding:4px 14px;border-radius:100px;letter-spacing:.5px;text-transform:uppercase;margin-bottom:1rem">Guide Gratuite</div>
    <h1 style="font-family:'Bricolage Grotesque',sans-serif;font-size:clamp(1.8rem,4vw,2.6rem);font-weight:800;color:var(--navy);letter-spacing:-1px;margin-bottom:.75rem">Tutto quello che devi sapere su luce e gas</h1>
    <p style="font-size:1rem;color:var(--muted);max-width:520px;margin:0 auto;line-height:1.7">Guide pratiche, aggiornate e scritte in italiano chiaro. Niente tecnicismi inutili.</p>
  </div>
</div>

<div style="max-width:1000px;margin:3rem auto;padding:0 1.5rem 5rem">
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem">
    {cards_html}
  </div>

  <div style="background:linear-gradient(135deg,var(--navy),#1e3a5f);border-radius:var(--r);padding:2.5rem;text-align:center;margin-top:3rem;color:white">
    <h2 style="font-family:'Bricolage Grotesque',sans-serif;font-weight:800;font-size:1.3rem;margin-bottom:.5rem">Pronto ad analizzare la tua bolletta?</h2>
    <p style="font-size:.9rem;opacity:.7;margin-bottom:1.25rem">Carica il PDF: in 30 secondi scopri quanto stai pagando e quanto potresti risparmiare.</p>
    <a href="/" style="display:inline-flex;align-items:center;gap:.4rem;background:white;color:var(--navy);text-decoration:none;border-radius:var(--r-sm);padding:.85rem 2rem;font-family:'Bricolage Grotesque',sans-serif;font-weight:800;font-size:.95rem;transition:all var(--t)">&#x1F50D; Analizza gratis &#x2192;</a>
  </div>
</div>

{_FOOTER}
</body>
</html>"""
