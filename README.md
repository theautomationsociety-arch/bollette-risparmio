# Bollette Risparmio — Bibbia della Conoscenza

> Documentazione completa del progetto: architettura, logiche, servizi esterni e guida al deploy.

---

## Indice

1. [Panoramica del progetto](#1-panoramica-del-progetto)
2. [Architettura tecnica](#2-architettura-tecnica)
3. [Struttura del codice](#3-struttura-del-codice)
4. [Database — schema e logiche](#4-database--schema-e-logiche)
5. [Backend — API e logiche](#5-backend--api-e-logiche)
6. [Frontend — UI e flusso utente](#6-frontend--ui-e-flusso-utente)
7. [Analisi AI con Gemini](#7-analisi-ai-con-gemini)
8. [Servizi esterni](#8-servizi-esterni)
9. [Pagine del sito](#9-pagine-del-sito)
10. [Sistema di persistenza analisi](#10-sistema-di-persistenza-analisi)
11. [Rate limiting](#11-rate-limiting)
12. [Autenticazione admin](#12-autenticazione-admin)
13. [Variabili d'ambiente](#13-variabili-dambiente)
14. [Deploy su Railway](#14-deploy-su-railway)
15. [Checklist pre-launch](#15-checklist-pre-launch)

---

## 1. Panoramica del progetto

**Bollette Risparmio** è un comparatore di tariffe energetiche italiano che permette agli utenti di:
- Caricare la propria bolletta PDF/immagine e ricevere un'analisi AI in ~30 secondi
- Confrontare le offerte del mercato libero calibrate sui propri consumi reali
- Richiedere una consulenza gratuita con esperti del settore

L'applicazione è costruita come **single-page app + backend FastAPI** servito da un unico server Python. Non ci sono framework frontend complessi: HTML/CSS/JS puri.

**Stack:** Python 3.11+ · FastAPI · SQLite · Google Gemini AI · Resend (email) · Vanilla JS/CSS

---

## 2. Architettura tecnica

```
┌─────────────────────────────────────────┐
│              Browser (client)           │
│  index.html + app.js + style.css        │
│  ↕ fetch() alle API                     │
└────────────────┬────────────────────────┘
                 │ HTTP
┌────────────────▼────────────────────────┐
│         FastAPI (backend/main.py)       │
│                                         │
│  Static files → /static/*               │
│  HTML pages  → /, /guide, /offerte...   │
│  Public API  → /api/*                   │
│  Admin API   → /api/admin/* (token)     │
└──────┬─────────────┬────────────────────┘
       │             │
       ▼             ▼
   SQLite DB    Google Gemini API
   data/db.sqlite   (analisi bollette)
                     │
                     ▼
                Resend (email leads)
```

Il server serve sia le pagine HTML (SSR server-side render) sia le API. Non c'è separazione tra frontend e backend server.

---

## 3. Struttura del codice

```
bollette-risparmio/
├── backend/
│   ├── main.py           ← FastAPI app principale (API + routing pagine)
│   ├── guide_pages.py    ← HTML SSR per guide, pagine interne e legali
│   └── email_utils.py    ← Template email e invio via Resend
├── frontend/
│   ├── index.html        ← Homepage (analizzatore + risultati)
│   ├── app.js            ← Logica JS client (analisi, confronto, modali)
│   ├── style.css         ← Stili brand (palette ufficiale Bollette Risparmio)
│   └── admin.html        ← Dashboard amministrativa
├── data/
│   ├── db.sqlite         ← Database SQLite (creato automaticamente)
│   └── app.log           ← Log applicazione
├── requirements.txt      ← Dipendenze Python
└── README.md             ← Questo file
```

---

## 4. Database — schema e logiche

Il database SQLite viene inizializzato automaticamente all'avvio (`init_db()`). WAL mode attivo per performance migliori in ambienti multi-request.

### Tabelle

#### `bollette`
Ogni bolletta analizzata (PDF o manuale) genera un record.

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `id` | TEXT PK | UUID v4 — usato anche come ID condivisibile |
| `tipo` | TEXT | `luce` o `gas` |
| `profilo` | TEXT | `D2`, `D3`, `CDO` |
| `totale` | REAL | Totale fattura in € |
| `consumo` | REAL | kWh (luce) o Smc (gas) |
| `costo_unit` | REAL | Costo unitario €/kWh o €/Smc |
| `dati_json` | TEXT | JSON completo estratto dall'AI |
| `data_upload` | TEXT | Timestamp ISO |

#### `offerte_luce` / `offerte_gas`
Offerte del mercato libero inserite dall'admin.

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `id` | TEXT PK | UUID v4 |
| `fornitore` | TEXT | Nome fornitore (es. "Enel Energia") |
| `nome` | TEXT | Nome commerciale offerta |
| `tipo` | TEXT | `FISSO`, `INDICIZZATO`, `MISTO` |
| `profili` | TEXT | CSV dei profili compatibili (es. "D2,D3,CDO") |
| `prezzo_f1/f2/f3` | REAL | Prezzi per fascia oraria (€/kWh) |
| `prezzo_mono` | REAL | Prezzo monorario (€/kWh) |
| `spread_pun` | REAL | Spread sul PUN per offerte indicizzate |
| `quota_fissa` | REAL | Quota fissa mensile (€/mese) |
| `valida_fino` | TEXT | Data scadenza offerta |
| `attiva` | INTEGER | 1 = attiva, 0 = disattivata |

#### `leads`
Contatti degli utenti che richiedono consulenza o confronto.

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `id` | TEXT PK | UUID v4 |
| `nome`, `cognome` | TEXT | Dati anagrafici |
| `email`, `telefono` | TEXT | Contatti |
| `tipo_richiesta` | TEXT | `consulente`, `comparazione` |
| `bolletta_id` | TEXT | Riferimento alla bolletta analizzata |
| `stato` | TEXT | `nuovo`, `in_lavorazione`, `chiuso` |
| `consenso_privacy` | INTEGER | Booleano GDPR |

#### `indici`
Indici energetici PUN (luce) e PSV (gas) aggiornati periodicamente.

#### `comparazioni`
Risultati dei confronti effettuati, collegati a bolletta e lead.

---

## 5. Backend — API e logiche

### Route statiche (pagine HTML)

| URL | Handler | Note |
|-----|---------|-------|
| `GET /` | `root()` | Serve `frontend/index.html` |
| `GET /admin` | `admin_page()` | Serve `frontend/admin.html` |
| `GET /offerte` | `pagina_offerte_route()` | Pagina SSR offerte |
| `GET /come-funziona` | `pagina_come_funziona_route()` | Pagina SSR how-it-works |
| `GET /chi-siamo` | `pagina_chi_siamo_route()` | Pagina SSR about |
| `GET /guide` | `guida_index()` | Indice guide SEO |
| `GET /guida/*` | varie | 5 guide SEO complete |
| `GET /privacy` | `pagina_privacy_route()` | Privacy policy |
| `GET /termini` | `pagina_termini_route()` | T&C / Condizioni generali |
| `GET /condizioni-generali` | (alias termini) | Stesso handler |
| `GET /risultati/{id}` | `risultati_condivisibili()` | Link condivisibile analisi |

### API pubblica

#### `POST /api/analizza/{tipo}`
Analizza una bolletta caricata.
- **Input:** `FormData` con `file` (PDF/JPG/PNG) + query param `profilo`
- **Processo:**
  1. Salva file temporaneo
  2. Invia a Gemini API con prompt strutturato
  3. Estrae dati JSON (totale, consumi, fornitore, anomalie, suggerimenti)
  4. Calcola costo unitario e confronta con indici PUN/PSV
  5. Salva in DB e restituisce `bolletta_id`
- **Output:** JSON con `bolletta_id`, `dati`, `costo_unitario`, `tipo`

#### `GET /api/analisi/{bolletta_id}`
Recupera un'analisi già effettuata (per link condivisibili).

#### `POST /api/compara/{bolletta_id}`
Confronta l'offerta attuale con il database offerte.
- **Logica:** Calcola `costo_annuo` per ogni offerta attiva compatibile con il profilo, ordina per risparmio decrescente
- **Output:** Lista offerte ordinate con `risparmio_annuo` stimato

#### `POST /api/leads`
Salva un contatto/lead. Opzionalmente invia email di notifica via Resend.

#### `GET /api/offerte/{tipo}` e `GET /api/indici`
Endpoint pubblici per recuperare offerte e indici correnti.

### API admin (token Bearer)

Tutte le route `/api/admin/*` richiedono l'header `Authorization: Bearer <ADMIN_TOKEN>`.

| Endpoint | Funzione |
|----------|----------|
| `GET /api/admin/stats` | Dashboard stats (conteggi, medie) |
| `GET /api/admin/leads` | Lista lead con filtri |
| `PATCH /api/admin/leads/{id}` | Aggiorna stato lead |
| `GET /api/admin/bollette` | Lista bollette |
| `DELETE /api/admin/bollette/{id}` | Elimina bolletta |
| `POST /api/admin/offerte/estrai-pdf` | Estrai offerta da PDF con AI |
| `POST /api/admin/offerte/estrai-url` | Estrai offerta da URL con AI |
| `POST /api/admin/offerte/{tipo}` | Crea nuova offerta |
| `DELETE /api/admin/offerte/{tipo}/{id}` | Elimina offerta |
| `POST /api/admin/indici/aggiorna` | Fetch automatico PUN/PSV |
| `POST /api/admin/indici/manuale` | Aggiorna indici manualmente |
| `GET /api/admin/export/bollette` | Export CSV bollette |
| `GET /api/admin/export/leads` | Export CSV leads |

---

## 6. Frontend — UI e flusso utente

### Flusso principale (caricamento bolletta)

```
1. Utente sceglie tipo (Luce/Gas) + profilo (Residente/Non Residente/Condominio)
2. Trascina/carica PDF → file validato (max 10MB, PDF/JPG/PNG)
3. Click "Analizza con AI" → POST /api/analizza/{tipo}
4. Loading spinner → risposta JSON con risultati
5. Visualizzazione risultati:
   - Stat box: totale €, consumo, costo unitario, fornitore
   - AI box anomalie (se presenti)
   - AI box suggerimenti
6. Sezione confronto:
   - Form nome/cognome/email/telefono
   - Click "Confronta" → POST /api/leads + POST /api/compara/{id}
7. Lista offerte ordinate per risparmio
   - Se offerta attuale già ottima → box congratulatorio 🏆
8. 2 CTA: "Richiedi consulenza" (modale) + "Chiama ora" (tel:)
```

### Flusso inserimento manuale

```
1. Click "Non hai il PDF? Inserisci i dati manualmente"
2. Si apre modale overlay con form dettagliato:
   - Tipo utenza + profilo contrattuale
   - Fornitore attuale + tipo mercato
   - Consumi: spesa mensile €, kWh/anno, Smc/anno
   - Potenza impegnata + fascia oraria
   - Abitazione: n° persone, superficie, riscaldamento
   - Elettrodomestici intensivi (checkbox)
   - Abitudini d'uso + fotovoltaico + priorità
3. Submit → POST /api/analizza-manuale
4. Modale si chiude → risultati come da analisi PDF
```

### Profili tariffari

| Codice | Nome | IVA | Note |
|--------|------|-----|------|
| D2 | Domestico Residente | 10% | Residenti — agevolazioni ARERA |
| D3 | Domestico Non Residente | 10% | Seconda casa, uffici |
| CDO | Condominio | 10% | Parti comuni condominiali |

> **BTA (PMI) è stato rimosso dall'interfaccia pubblica** — mantenuto solo nell'admin per gestire offerte storiche.

### Selezione profilo — radio buttons

Il campo "Tipo di utenza" usa radio button invece di un dropdown, per migliorare la chiarezza visiva. I profili disponibili sono: Residente (D2), Non Residente (D3), Condominio (CDO). L'opzione Condominio viene nascosta automaticamente quando si seleziona "Gas" (non applicabile).

### Sistema modale

Il sito usa 2 overlay modali con pattern identico:
- **Contact overlay** (`#contact-overlay`) — aperto da `openContact()`
- **Manual modal** (`#manual-modal-overlay`) — aperto da `openManualModal()`

Entrambi: chiusura con ESC, click fuori, o pulsante X. Blocco scroll del body (`overflow:hidden`).

### Logica "offerta già ottima"

Quando il confronto offerte viene completato e nessuna alternativa fa risparmiare (tutti i `risparmio_annuo <= 0`), viene mostrato un box verde con messaggio congratulatorio. L'utente viene comunque invitato a chiamare per valutare bundle o soluzioni fotovoltaico.

---

## 7. Analisi AI con Gemini

### Modello utilizzato
`gemini-2.0-flash-exp` (configurabile) — ottimizzato per velocità su task strutturati.

### Prompt struttura (versione TO-BE — aggiornata marzo 2026)

Tutti e tre i prompt (`P_LUCE`, `P_GAS`, `P_OFFERTA`) seguono la stessa struttura:

1. **Blocco RUOLO** — fornisce contesto al modello: sa che i dati estratti serviranno per calcoli economici e comparazioni. Questo migliora la precisione sui campi critici (consumi per fascia, prezzi unitari).
2. **Blocco ISTRUZIONI** — regole esplicite: usare `null` per valori mancanti (mai inventare), analizzare tutte le pagine, verificare coerenza dei totali, gestire conversioni (mc→Smc, quota mensile→annuale).
3. **Schema JSON commentato** — struttura con valori di default `null`. Il modello compila i campi trovati nel documento.

#### Nuovi campi estratti rispetto alla versione precedente

| Campo | Prompt | Uso nel backend |
|---|---|---|
| `prezzo_medio_kwh` | P_LUCE | Fallback per `costo_unitario` quando mancano i prezzi per fascia |
| `prezzo_medio_smc` | P_GAS | Fallback per `costo_unitario` gas |
| `potenza_disponibile` | P_LUCE | Salvata in `bollette.potenza_disponibile` |
| `zona_climatica` | P_GAS | Salvata in `bollette.zona_climatica` |
| `bonus_sociale` | P_LUCE, P_GAS | Salvato in `bollette.bonus_sociale` |
| `confidence_score` | P_LUCE, P_GAS | 0–100; permette di identificare analisi poco affidabili |
| `campi_incerti` | P_LUCE, P_GAS | Lista campi con possibili errori di lettura |
| `prezzo_mono_eur_kwh` | P_OFFERTA | Mappato su `offerte_luce.prezzo_mono` |
| `oneri_trasporto_eur_kwh` | P_OFFERTA | Mappato su `offerte_luce.oneri_trasp` |
| `quota_variabile_smc` | P_OFFERTA | Mappato su `offerte_gas.quota_var` |
| `durata_contratto_mesi` | P_OFFERTA | Informativo (non usato nel calcolo) |
| `prezzi_lordi_o_netti` | P_OFFERTA | Flag di qualità dati per il team admin |

#### Razionale delle scelte di design

- **`null` invece di `0.0` come default**: permette al backend di distinguere "il valore è zero" da "il dato non era leggibile", evitando che zeri errati si propaghino nei calcoli senza essere rilevati.
- **`prezzo_medio_kwh` come fallback**: molte bollette italiane riportano solo un prezzo medio senza ripartizione per fasce. Il backend ora usa `prezzo_medio_kwh or (spesa_energia / consumo)` come costo unitario.
- **Quota fissa annuale in P_OFFERTA**: le CTE la indicano spesso in euro/mese. Il prompt istruisce il modello a convertire (×12) prima di restituirla. Se non convertita, il costo annuo risultante sarebbe sottostimato dell'~92%.
- **`tipo_prezzo: 'MISTO'`**: supporta offerte ibride (componente fissa + spread su PUN/PSV), già gestite dal DB ma non estraibili con il vecchio prompt.

### Costo unitario
Dopo l'estrazione, il backend calcola con questa priorità:
```python
# Preferisce il prezzo medio estratto dal modello (più preciso)
# Fallback al calcolo derivato spesa/consumo
costo_unitario = prezzo_medio_kwh or (spesa_energia / consumo_totale if consumo > 0 else None)
```
E confronta con l'ultimo indice PUN/PSV salvato in DB per rilevare se il prezzo è superiore al mercato.

---

## 8. Servizi esterni

### Google Gemini AI
- **Uso:** Analisi bollette (estrazione dati strutturati) + estrazione offerte da PDF/URL (admin)
- **Variabile:** `GEMINI_API_KEY`
- **SDK:** `google-genai` (pacchetto ufficiale Google)
- **Documentazione:** https://ai.google.dev/

### Resend (email transazionale)
- **Uso:** Notifica admin su nuovo lead + email di conferma all'utente
- **Variabile:** `RESEND_API_KEY`, `FROM_EMAIL`, `ADMIN_EMAIL`
- **Opzionale:** Se `RESEND_API_KEY` non configurato, le email vengono silenziosamente ignorate
- **Documentazione:** https://resend.com/docs

### iubenda (privacy/cookie)
- **Uso:** Privacy policy e cookie policy esternalizzata (GDPR compliant)
- **ID policy:** `30631851`
- **Non richiede configurazione backend** — link diretti nel frontend

### Google Fonts
- **Uso:** Font `Sora` (display/heading) e `DM Sans` (body)
- **Non richiede API key** — caricamento via CDN

---

## 9. Pagine del sito

| URL | Tipo | Generata da |
|-----|------|-------------|
| `/` | FileResponse | `frontend/index.html` |
| `/offerte` | HTML SSR | `guide_pages.pagina_offerte()` |
| `/come-funziona` | HTML SSR | `guide_pages.pagina_come_funziona()` |
| `/chi-siamo` | HTML SSR | `guide_pages.pagina_chi_siamo()` |
| `/guide` | HTML SSR | `guide_pages.guida_index()` |
| `/guida/differenza-mercato-libero-tutelato` | HTML SSR | `guide_pages.guida_mercato_libero()` |
| `/guida/come-leggere-bolletta-luce` | HTML SSR | `guide_pages.guida_bolletta_luce()` |
| `/guida/fasce-orarie-f1-f2-f3` | HTML SSR | `guide_pages.guida_fasce_orarie()` |
| `/guida/come-cambiare-fornitore-energia` | HTML SSR | `guide_pages.guida_cambiare_fornitore()` |
| `/guida/pun-psv-cosa-sono` | HTML SSR | `guide_pages.guida_pun_psv()` |
| `/privacy` | HTML SSR | `guide_pages.pagina_privacy()` |
| `/termini` | HTML SSR | `guide_pages.pagina_condizioni_generali()` |
| `/condizioni-generali` | HTML SSR | (alias `/termini`) |
| `/risultati/{id}` | HTML SSR | `index.html` + meta tag iniettati |
| `/admin` | FileResponse | `frontend/admin.html` |

---

## 10. Sistema di persistenza analisi

Le analisi sono condivisibili e recuperabili grazie a due meccanismi:

### Link condivisibile (`/risultati/{bolletta_id}`)
1. Dopo l'analisi, l'URL del browser cambia in `/risultati/{uuid}`
2. Se l'URL viene condiviso/rivisitato, il server inietta meta tag nella risposta HTML:
   ```html
   <meta name="br-risultati-id" content="{uuid}">
   <meta name="br-risultati-tipo" content="luce">
   ```
3. Il JS li legge e chiama `GET /api/analisi/{uuid}` per ricaricare i dati

### SessionStorage (navigazione interna)
I dati dell'analisi vengono salvati in `sessionStorage` con chiave `br_analisi_v1`:
- Scadenza: 2 ore
- Contenuto: dati analisi + tipo + bolletta_id + offerte confrontate
- All'apertura della homepage, `autoRestore()` controlla se c'è una sessione attiva

---

## 11. Rate limiting

Implementato in-memory (non persistente tra riavvii) per proteggere l'endpoint di analisi:
- **Default:** max 10 richieste per IP per ora (finestra scorrevole)
- **Configurabile** via env: `RATE_LIMIT_MAX` e `RATE_LIMIT_WINDOW`
- **Risposta 429** con header `Retry-After` in secondi
- **Non si applica** alle route admin (l'autenticazione token è protezione sufficiente)

---

## 12. Autenticazione admin

L'area admin (`/admin`) e tutte le API `/api/admin/*` richiedono:
```
Authorization: Bearer <ADMIN_TOKEN>
```

Il token viene verificato in `require_admin()`. Se il token è debole (< 16 caratteri, o tra quelli comuni) viene loggato un warning all'avvio.

**In produzione:** impostare sempre `ADMIN_TOKEN` con una stringa casuale di almeno 32 caratteri.

---

## 13. Variabili d'ambiente

| Variabile | Default | Obbligatoria | Descrizione |
|-----------|---------|--------------|-------------|
| `GEMINI_API_KEY` | `""` | **Sì** | Chiave Google Gemini AI |
| `ADMIN_TOKEN` | `admin123` | **Sì (prod)** | Token autenticazione admin |
| `RESEND_API_KEY` | `""` | No | Chiave Resend per email |
| `FROM_EMAIL` | `onboarding@resend.dev` | No | Mittente email |
| `ADMIN_EMAIL` | `""` | No | Email notifiche admin |
| `SITE_URL` | `https://www.bolletterisparmio.it` | No | URL canonico sito |
| `ALLOWED_ORIGINS` | `*` | No (prod: restringere) | CORS origins |
| `RATE_LIMIT_MAX` | `10` | No | Max richieste analisi per IP/ora |
| `RATE_LIMIT_WINDOW` | `3600` | No | Finestra rate limit in secondi |

---

## 14. Deploy su Railway

Railway è una piattaforma PaaS che supporta Python/FastAPI nativamente.

### Prerequisiti
- Account Railway (railway.app)
- Repository GitHub del progetto

### Passo 1 — Prepara il file di avvio

Crea un file `Procfile` nella root del progetto:
```
web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

### Passo 2 — Verifica requirements.txt

Assicurati che contenga tutte le dipendenze:
```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
python-multipart
httpx
google-genai
resend
```

### Passo 3 — Deploy da GitHub

1. Vai su [railway.app](https://railway.app) → **New Project**
2. Seleziona **Deploy from GitHub repo**
3. Autorizza Railway e scegli il tuo repository
4. Railway rileva automaticamente Python e usa il `Procfile`

### Passo 4 — Configurazione variabili d'ambiente

Dashboard Railway → tab **Variables**, aggiungi:
```
GEMINI_API_KEY=AIza...
ADMIN_TOKEN=<stringa-casuale-min-32-char>
RESEND_API_KEY=re_...
FROM_EMAIL=Bollette Risparmio <info@bolletterisparmio.it>
ADMIN_EMAIL=info@bolletterisparmio.it
SITE_URL=https://www.bolletterisparmio.it
ALLOWED_ORIGINS=https://www.bolletterisparmio.it
```

### Passo 5 — Volume per la persistenza del database

> Il filesystem Railway è effimero: il DB SQLite viene perso ad ogni deploy senza volume.

1. Tab **Volumes** → **Add Volume**
2. Mount path: `/app/data`
3. Il database viene ora scritto su volume persistente tra i deploy

### Passo 6 — Dominio personalizzato

1. Tab **Settings** → **Domains** → **Add Custom Domain**
2. Inserisci `www.bolletterisparmio.it`
3. Copia il CNAME fornito da Railway
4. Nel DNS del dominio, aggiungi:
   ```
   www  CNAME  <progetto>.up.railway.app
   ```
5. Attendi propagazione DNS (5-30 min)
6. Railway abilita HTTPS automaticamente (Let's Encrypt)

### Passo 7 — Verifica deploy

```bash
# Log in tempo reale
railway logs

# Health check
curl https://www.bolletterisparmio.it/api/health
```

### Aggiornamenti continui

Ogni push su `main` triggera automaticamente un nuovo deploy.

### Schema deploy

```
GitHub push
    ↓
Railway Build (pip install + uvicorn)
    ↓
Container avviato su porta $PORT
    ↓
Volume /app/data  ←→  db.sqlite (persistente)
    ↓
Custom Domain + HTTPS (Let's Encrypt)
```

---

## 15. Checklist pre-launch

- [ ] `GEMINI_API_KEY` configurata e testata con una bolletta reale
- [ ] `ADMIN_TOKEN` impostato con stringa casuale (min 32 caratteri)
- [ ] `RESEND_API_KEY` configurata e testata invio email
- [ ] `ALLOWED_ORIGINS` ristretto al dominio di produzione
- [ ] Volume Railway configurato e testato su `/app/data`
- [ ] Dominio personalizzato e HTTPS attivi
- [ ] Almeno 5 offerte luce e 5 offerte gas inserite nell'admin
- [ ] Indici PUN e PSV aggiornati dall'admin
- [ ] `sitemap.xml` aggiornato con URL definitivi
- [ ] Test analisi bolletta PDF end-to-end
- [ ] Test inserimento manuale end-to-end
- [ ] Test confronto offerte e salvataggio lead
- [ ] Test link condivisibile `/risultati/{id}`
- [ ] Test invio lead e ricezione email notifica
- [ ] Verifica pagine: /offerte, /come-funziona, /chi-siamo, /guide, /privacy, /termini

---

*Bollette Risparmio — walktotalk.srl · Via Cesario Console 3, 80132 Napoli · info@bolletterisparmio.it*
