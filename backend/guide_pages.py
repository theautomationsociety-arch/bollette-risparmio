"""
Bollette Risparmio — Guide SEO e pagine statiche.
Usa Jinja2 per il rendering; l'HTML di layout vive in /templates/.
"""

from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

SITE_URL = "https://www.bolletterisparmio.it"

_BASE = Path(__file__).parent.parent
_env  = Environment(
    loader=FileSystemLoader(str(_BASE / "templates")),
    autoescape=select_autoescape(["html"]),
)

# ── Guide metadata ──────────────────────────────────────────────────────────
_ALL_GUIDES = [
    ("/guida/differenza-mercato-libero-tutelato",
     "Differenza tra Mercato Libero e Tutelato",
     "Scopri le differenze tra mercato libero e tutelato, quando conviene cambiare e cosa succede dopo la fine della tutela.",
     "📊", 6),
    ("/guida/come-leggere-bolletta-luce",
     "Come leggere la bolletta della luce",
     "Guida completa alle voci della bolletta elettrica: materia energia, trasporto, oneri di sistema, accise e IVA.",
     "📄", 7),
    ("/guida/fasce-orarie-f1-f2-f3",
     "Fasce orarie F1, F2, F3: tutto quello che devi sapere",
     "Cosa sono le fasce orarie dell'energia elettrica, quali ore coprono e come influenzano il costo della bolletta.",
     "⏱", 6),
    ("/guida/come-cambiare-fornitore-energia",
     "Come cambiare fornitore di luce e gas",
     "Guida passo-passo per cambiare fornitore di energia: diritti, tempi, documenti necessari e cosa non cambia.",
     "🔄", 7),
    ("/guida/pun-psv-cosa-sono",
     "PUN e PSV: cosa sono e come influenzano la tua bolletta",
     "Spiegazione di PUN (Prezzo Unico Nazionale) e PSV (Punto di Scambio Virtuale): gli indici che determinano il prezzo dell'energia variabile.",
     "📈", 7),
]


def _correlate_cards(current_path: str) -> str:
    cards = []
    for path, title, desc, _, _ in _ALL_GUIDES:
        if path == current_path:
            continue
        cards.append(
            f'<a href="{path}" class="correlate-card">'
            f'<div class="correlate-card-cat">Guida</div>'
            f'<div class="correlate-card-title">{title}</div>'
            f'<div class="correlate-card-desc">{desc[:80]}…</div>'
            f'</a>'
        )
    return "\n".join(cards[:4])


def _render_guide(
    path: str,
    title: str,
    desc: str,
    category: str,
    read_min: int,
    toc: list[tuple[str, str]],
    body: str,
    schema_extra: str = "",
) -> str:
    today    = datetime.now().strftime("%d %B %Y")
    date_iso = datetime.now().strftime("%Y-%m-%d")
    return _env.get_template("guide.html").render(
        site_url     = SITE_URL,
        canonical    = SITE_URL + path,
        title        = title,
        desc         = desc,
        category     = category,
        read_min     = read_min,
        toc          = toc,
        body         = body,
        correlate    = _correlate_cards(path),
        today        = today,
        date_iso     = date_iso,
        schema_extra = schema_extra,
    )


# ════════════════════════════════════════════════════════════════════════════
# GUIDA 1 — Mercato Libero vs Tutelato
# ════════════════════════════════════════════════════════════════════════════
def guida_mercato_libero() -> str:
    toc = [
        ("cosa-sono",        "Cosa sono i due mercati"),
        ("differenze",       "Le differenze chiave"),
        ("fine-tutela",      "La fine del mercato tutelato"),
        ("clienti-vulnerabili", "I clienti vulnerabili"),
        ("quando-conviene",  "Quando conviene il mercato libero"),
        ("come-scegliere",   "Come scegliere l'offerta giusta"),
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
<p>È importante notare che gli <strong>oneri di sistema</strong> e le <strong>accise</strong> sono identici in entrambi i mercati — sono componenti regolate che nessun fornitore può modificare. La vera differenza è solo nella <strong>componente materia energia</strong>.</p>

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
<p>Il <strong>Portale Offerte ARERA</strong> (<a href="https://www.ilportaleofferte.it" target="_blank" rel="noopener noreferrer">ilportaleofferte.it</a>) è lo strumento ufficiale del governo per confrontare le offerte standardizzate dei fornitori. È un ottimo punto di partenza, ma considera che molte offerte promozionali non vengono caricate lì.</p>
"""
    return _render_guide(
        path      = "/guida/differenza-mercato-libero-tutelato",
        title     = "Differenza tra Mercato Libero e Tutelato",
        desc      = "Scopri le differenze tra mercato libero e tutelato, quando conviene cambiare e cosa è successo con la fine della tutela nel 2024.",
        category  = "Mercato Energetico",
        read_min  = 6,
        toc       = toc,
        body      = body,
    )


# ════════════════════════════════════════════════════════════════════════════
# GUIDA 2 — Come leggere la bolletta della luce
# ════════════════════════════════════════════════════════════════════════════
def guida_bolletta_luce() -> str:
    toc = [
        ("sezioni",        "Le sezioni della bolletta"),
        ("dati-anagrafici","Dati anagrafici e tecnici"),
        ("materia-energia","Spesa materia energia"),
        ("trasporto",      "Trasporto e gestione contatore"),
        ("oneri-sistema",  "Oneri di sistema"),
        ("imposte",        "Imposte, accise e IVA"),
        ("totale",         "Come si calcola il totale"),
        ("anomalie",       "Segnali di anomalia"),
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
  Il POD (Point of Delivery) è il codice univoco che identifica il tuo contatore elettrico. Ha il formato <strong>IT001E…</strong> e ti serve per qualsiasi operazione: cambiare fornitore, fare reclami, verificare i consumi storici.
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
  <li><strong>Perdite di rete</strong> — una piccola percentuale (circa 6–8%) che copre le dispersioni fisiche nella trasmissione dell'energia dalla centrale al tuo contatore.</li>
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
<p>Gli oneri di sistema hanno subito forti oscillazioni negli ultimi anni: ARERA li ha azzerati o ridotti drasticamente durante il caro-energia del 2022–2023 come misura di contenimento, per poi ripristinarli gradualmente.</p>

<h2 id="imposte">Imposte, accise e IVA</h2>
<p>L'ultima macro-voce raggruppa le imposte erariali.</p>
<ul>
  <li><strong>Accise sull'energia elettrica</strong> — imposte statali proporzionate ai consumi (€/kWh). Le prime 1.800 kWh/anno per usi domestici beneficiano di un'aliquota ridotta.</li>
  <li><strong>Addizionale provinciale</strong> — in alcune province si aggiunge un'ulteriore imposta locale.</li>
  <li><strong>Canone RAI</strong> — se sei un cliente domestico, il canone RAI da 90 €/anno è addebitato sulla bolletta della luce (7,50 €/mese).</li>
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
  <li><strong>Canone RAI addebitato su seconda casa:</strong> il canone RAI spetta una sola volta per nucleo familiare.</li>
  <li><strong>Scadenza non aggiornata dopo il cambio fornitore:</strong> possono verificarsi doppi addebiti nel periodo di switching.</li>
</ul>
"""
    return _render_guide(
        path     = "/guida/come-leggere-bolletta-luce",
        title    = "Come leggere la bolletta della luce",
        desc     = "Guida completa alle voci della bolletta elettrica italiana: materia energia, trasporto, oneri di sistema, accise e IVA. Impara a verificare i costi e identificare anomalie.",
        category = "Bolletta Elettrica",
        read_min = 7,
        toc      = toc,
        body     = body,
    )


# ════════════════════════════════════════════════════════════════════════════
# GUIDA 3 — Fasce orarie F1, F2, F3
# ════════════════════════════════════════════════════════════════════════════
def guida_fasce_orarie() -> str:
    toc = [
        ("cosa-sono",   "Cosa sono le fasce orarie"),
        ("orari",       "Gli orari delle fasce"),
        ("biorario",    "Tariffazione bioraria F1/F23"),
        ("monorario",   "Tariffazione monoraria"),
        ("chi-usa",     "Chi usa quale tariffa"),
        ("ottimizzare", "Come ottimizzare i consumi"),
        ("contatori",   "Contatori intelligenti e fasce"),
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
<p>È meno conveniente se usi molto l'energia di notte o nel weekend: in questi casi una tariffa bioraria o trioraria ti permette di sfruttare il prezzo F3 più basso.</p>

<h2 id="chi-usa">Chi usa quale tariffazione?</h2>
<div class="data-table-wrap">
<table class="data-table">
  <thead><tr><th>Profilo</th><th>Tariffazione tipica</th><th>Note</th></tr></thead>
  <tbody>
    <tr><td><strong>D2 Domestico Residente</strong></td><td>Bioraria F1/F23 o Monoraria</td><td>La più comune per le famiglie</td></tr>
    <tr><td><strong>D3 Non Residente</strong></td><td>Bioraria F1/F23</td><td>Seconda casa, uso saltuario</td></tr>
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
    Programma i lavaggi notturni (dopo le 23:00) o domenicali. Molti elettrodomestici moderni hanno un timer integrato. Il risparmio rispetto a lavaggi in orario F1 può essere del 20–30% sulla quota energia.</div>
  </li>
  <li>
    <div class="step-num">&#x1F697;</div>
    <div class="step-content"><strong>Ricarica auto elettrica</strong><br>
    La ricarica di un'auto elettrica può consumare 10–20 kWh per ciclo. Caricarla di notte (F3) invece che il pomeriggio (F1) può fare una differenza significativa in bolletta su base mensile.</div>
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
    return _render_guide(
        path     = "/guida/fasce-orarie-f1-f2-f3",
        title    = "Fasce orarie F1, F2, F3: tutto quello che devi sapere",
        desc     = "Cosa sono le fasce orarie F1, F2, F3 dell'energia elettrica, quali ore coprono e come usarle per ottimizzare i consumi e risparmiare in bolletta.",
        category = "Tariffe Elettriche",
        read_min = 6,
        toc      = toc,
        body     = body,
    )


# ════════════════════════════════════════════════════════════════════════════
# GUIDA 4 — Come cambiare fornitore
# ════════════════════════════════════════════════════════════════════════════
def guida_cambiare_fornitore() -> str:
    toc = [
        ("diritto",         "Hai il diritto di cambiare"),
        ("prima-di-cambiare","Prima di cambiare"),
        ("procedura",       "La procedura passo per passo"),
        ("tempi",           "I tempi dello switching"),
        ("cosa-non-cambia", "Cosa non cambia"),
        ("debiti-bollette", "Debiti e bollette vecchie"),
        ("errori-comuni",   "Errori da evitare"),
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
<p>In pratica, dalla firma del contratto all'attivazione effettiva passano generalmente 2–4 settimane. Il nuovo fornitore ti comunicherà la data esatta di decorrenza del nuovo contratto.</p>

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
<p>Se sei in contestazione su una bolletta, puoi comunque avviare il cambio mentre la contestazione è in corso, a condizione di aver pagato la parte non contestata. Per contestare una bolletta, rivolgiti all'ufficio reclami del tuo fornitore e, in caso di mancata risposta entro 40 giorni, allo Sportello del Consumatore di ARERA.</p>

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
    return _render_guide(
        path     = "/guida/come-cambiare-fornitore-energia",
        title    = "Come cambiare fornitore di luce e gas",
        desc     = "Guida completa per cambiare fornitore di energia in Italia: diritti, tempi, procedura passo per passo, cosa non cambia e gli errori da evitare.",
        category = "Cambio Fornitore",
        read_min = 7,
        toc      = toc,
        body     = body,
    )


# ════════════════════════════════════════════════════════════════════════════
# GUIDA 5 — PUN e PSV
# ════════════════════════════════════════════════════════════════════════════
def guida_pun_psv() -> str:
    toc = [
        ("cos-e-il-pun",  "Cos'è il PUN"),
        ("come-si-forma", "Come si forma il prezzo"),
        ("pun-in-bolletta","Il PUN nella tua bolletta"),
        ("cos-e-il-psv",  "Cos'è il PSV"),
        ("fisso-variabile","Fisso o variabile: quale scegliere"),
        ("dove-trovare",  "Dove trovare i valori aggiornati"),
    ]
    body = """
<h2 id="cos-e-il-pun">Cos'è il PUN (Prezzo Unico Nazionale)?</h2>
<p>Il <strong>PUN</strong> — acronimo di <strong>Prezzo Unico Nazionale</strong> — è il prezzo medio all'ingrosso dell'energia elettrica in Italia. È il prezzo al quale i produttori e gli importatori vendono l'energia agli operatori di mercato sulla <strong>Borsa Elettrica Italiana (GME)</strong>, gestita dal Gestore dei Mercati Energetici.</p>
<p>Il PUN viene calcolato come <strong>media ponderata dei prezzi zonali</strong> orari (Italia Nord, Centro-Nord, Centro-Sud, Sud, Sicilia, Sardegna), ponderata per i volumi scambiati in ogni ora. Viene pubblicato quotidianamente e aggregato su base mensile da ARERA.</p>
<p>Il PUN si misura in <strong>€/MWh</strong> (o equivalentemente in c€/kWh), il che significa che indica il costo per ogni megawattora di energia acquistata sul mercato all'ingrosso.</p>

<div class="box box-info">
  <div class="box-title">&#x2139; PUN: cifre recenti</div>
  Dopo i picchi del 2022 (oltre 300 €/MWh), il PUN si è normalizzato: nel 2025–2026 si è stabilizzato tra 100 e 135 €/MWh (circa 10–13,5 c€/kWh). I valori storici mensili sono pubblicati da ARERA sul Portale Offerte.
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
  <li><strong>ARERA — Portale Offerte:</strong> <a href="https://www.ilportaleofferte.it/portaleOfferte/it/open-data.page" target="_blank" rel="noopener noreferrer">ilportaleofferte.it</a> pubblica i prezzi storici mensili usati come riferimento per le offerte indicizzate.</li>
  <li><strong>GME (Gestore Mercati Energetici):</strong> <a href="https://www.mercatoelettrico.org" target="_blank" rel="noopener noreferrer">mercatoelettrico.org</a> pubblica i prezzi zonali orari dell'elettricità in tempo reale.</li>
  <li><strong>Snam Rete Gas:</strong> pubblica i prezzi PSV giornalieri sulla piattaforma di bilanciamento.</li>
  <li><strong>Bollette Risparmio:</strong> il pannello admin aggiorna automaticamente gli indici mensili ARERA per il calcolo delle offerte variabili.</li>
</ul>
"""
    return _render_guide(
        path     = "/guida/pun-psv-cosa-sono",
        title    = "PUN e PSV: cosa sono e come influenzano la bolletta",
        desc     = "Spiegazione di PUN (Prezzo Unico Nazionale) e PSV (Punto di Scambio Virtuale): gli indici del mercato all'ingrosso dell'energia che determinano il prezzo delle offerte variabili.",
        category = "Indici di Mercato",
        read_min = 7,
        toc      = toc,
        body     = body,
    )


# ════════════════════════════════════════════════════════════════════════════
# PAGINA INDICE GUIDE
# ════════════════════════════════════════════════════════════════════════════
def guida_index() -> str:
    return _env.get_template("guide_index.html").render(
        site_url = SITE_URL,
        guides   = _ALL_GUIDES,
    )


# ════════════════════════════════════════════════════════════════════════════
# PAGINE INTERNE (Offerte, Come Funziona, Chi Siamo)
# ════════════════════════════════════════════════════════════════════════════
def pagina_offerte() -> str:
    return _env.get_template("offerte.html").render(site_url=SITE_URL)


def pagina_come_funziona() -> str:
    return _env.get_template("come_funziona.html").render(site_url=SITE_URL)


def pagina_chi_siamo() -> str:
    return _env.get_template("chi_siamo.html").render(site_url=SITE_URL)


# ════════════════════════════════════════════════════════════════════════════
# PAGINE LEGALI
# ════════════════════════════════════════════════════════════════════════════
def pagina_privacy() -> str:
    return _env.get_template("privacy.html").render(site_url=SITE_URL)


def pagina_termini() -> str:
    return _env.get_template("termini.html").render(site_url=SITE_URL)
