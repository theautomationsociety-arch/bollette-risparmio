const API = window.location.origin;
let currentTipo = 'luce';
let currentBollettaId = null;
let selectedFile = null;
let personalData = null; // { nome, cognome, telefono, email }

// ── Contact Center configuration ──────────────────────────────────────────────
const CONTACT_CENTER_PHONE        = '0819131897';
const CONTACT_CENTER_PHONE_DISPLAY = '081 91 31 897';
const CONTACT_CENTER_HOURS = { start: 9, end: 18, days: [1, 2, 3, 4, 5] }; // lun-ven 9-18

function isContactCenterOpen() {
  const now  = new Date();
  const day  = now.getDay();
  const hour = now.getHours();
  return CONTACT_CENTER_HOURS.days.includes(day) &&
         hour >= CONTACT_CENTER_HOURS.start &&
         hour < CONTACT_CENTER_HOURS.end;
}

// Current offer selected for modals
let _currentOfferName      = '';
let _currentOfferFornitore = '';

// Escape a string for safe use in an HTML attribute value (double-quoted)
function _escAttr(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
}

// ══════════════════════════════════════════════════════════════════════════════
// PERSISTENZA — salva/ripristina lo stato dell'analisi in sessionStorage
// Sopravvive alla navigazione tra pagine della stessa sessione browser
// ══════════════════════════════════════════════════════════════════════════════
const STORAGE_KEY = 'br_analisi_v1';

function salvaPersistenza(datiAnalisi, tipo, bollettaId, offerte) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      dati: datiAnalisi,
      tipo,
      bollettaId,
      offerte: offerte || null,
      ts: Date.now()
    }));
  } catch(e) { /* sessionStorage piena o disabilitata */ }
}

function caricaPersistenza() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw);
    // Scade dopo 2 ore
    if (Date.now() - s.ts > 2 * 60 * 60 * 1000) {
      sessionStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return s;
  } catch(e) { return null; }
}

function cancellaPersistenza() {
  sessionStorage.removeItem(STORAGE_KEY);
}

// ── Personal data gate
function submitPersonalData() {
  const nome = document.getElementById('pd-nome').value.trim();
  const cognome = document.getElementById('pd-cognome').value.trim();
  const telefono = document.getElementById('pd-telefono').value.trim();
  const email = document.getElementById('pd-email').value.trim();
  if (!nome || !cognome || !telefono) {
    showToast('Compila nome, cognome e telefono', 'error');
    return;
  }
  // Validate required consents
  const requiredBoxes = document.querySelectorAll('input[name="consent-required"]');
  const allChecked = [...requiredBoxes].every(cb => cb.checked);
  if (!allChecked) {
    showToast('Accetta i consensi obbligatori per procedere', 'error');
    const box = document.getElementById('consent-box');
    box.classList.add('consent-error');
    setTimeout(() => box.classList.remove('consent-error'), 500);
    return;
  }
  personalData = {
    nome, cognome, telefono, email,
    consenso_privacy: true,
    consenso_termini: true,
    consenso_preventivi: true,
    consenso_cessione: document.getElementById('consent-cessione').checked,
    consenso_marketing: document.getElementById('consent-marketing').checked,
    consenso_profilazione: document.getElementById('consent-profilazione').checked,
    consenso_marketing_terzi: document.getElementById('consent-marketing-terzi').checked,
  };
  document.getElementById('personal-data-view').style.display = 'none';
  document.getElementById('upload-view').style.display = 'block';
}

// ── Consent helpers
function toggleAcceptAll(el) {
  const checked = el.checked;
  document.querySelectorAll('#consent-box input[type="checkbox"]').forEach(cb => cb.checked = checked);
}

function syncAcceptAll() {
  const all = [...document.querySelectorAll('#consent-box input[type="checkbox"]:not(#consent-accept-all)')];
  document.getElementById('consent-accept-all').checked = all.every(cb => cb.checked);
}

function toggleRecipientList(e) {
  e.preventDefault();
  const list = document.getElementById('consent-recipient-list');
  list.style.display = list.style.display === 'none' ? 'block' : 'none';
}

// ── Tipo tabs
function setTipo(t, el) {
  currentTipo = t;
  document.querySelectorAll('.tipo-tab').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  // CDO (Condominio) non si applica al gas
  const cdoOpt = document.querySelector('.profilo-cdo-opt');
  if (cdoOpt) {
    cdoOpt.style.display = t === 'gas' ? 'none' : '';
    if (t === 'gas') {
      const cdoInput = cdoOpt.querySelector('input');
      if (cdoInput && cdoInput.checked) {
        document.querySelector('input[name="profilo-sel"][value="D2"]').checked = true;
      }
    }
  }
}

// ── File handling
function onDrag(e, enter) {
  e.preventDefault();
  document.getElementById('dropzone').classList.toggle('drag', enter);
}
function onDrop(e) {
  e.preventDefault();
  document.getElementById('dropzone').classList.remove('drag');
  const f = e.dataTransfer.files[0];
  const ok = f && (f.type === 'application/pdf' || f.type.startsWith('image/'));
  if (ok) setFile(f);
  else showToast('Carica PDF, JPG o PNG', 'error');
}
function onFile(input) { if (input.files[0]) setFile(input.files[0]); }
function setFile(f) {
  if (f.size > 10*1024*1024) { showToast('File troppo grande (max 10 MB)', 'error'); return; }
  selectedFile = f;
  document.getElementById('file-name').textContent = f.name;
  document.getElementById('file-preview').style.display = 'flex';
  document.getElementById('btn-analyze').disabled = false;
}
function clearFile() {
  selectedFile = null;
  document.getElementById('file-input').value = '';
  document.getElementById('file-preview').style.display = 'none';
  document.getElementById('btn-analyze').disabled = true;
}

// ── Progress view helpers ──
const _STEP_DELAYS = [0, 2000, 5000, 9000, 13000, 17000];
let _stepTimers = [];

function _activateStep(i) {
  const steps = document.querySelectorAll('.analysis-step');
  if (i > 0) {
    steps[i - 1].classList.remove('active');
    steps[i - 1].classList.add('done');
  }
  steps[i].classList.add('visible', 'active');
}

function startProgress() {
  document.getElementById('upload-view').style.display = 'none';
  const pv = document.getElementById('progress-view');
  pv.style.display = 'block';
  // Reset all steps
  document.querySelectorAll('.analysis-step').forEach(el => {
    el.classList.remove('active', 'done', 'visible', 'error');
  });
  const oldBtn = document.getElementById('analysis-steps').querySelector('.progress-retry-btn');
  if (oldBtn) oldBtn.remove();
  // Schedule step activations
  _stepTimers.forEach(t => clearTimeout(t));
  _stepTimers = _STEP_DELAYS.map((delay, i) => setTimeout(() => _activateStep(i), delay));
}

function completeProgress(callback) {
  _stepTimers.forEach(t => clearTimeout(t));
  _stepTimers = [];
  const steps = document.querySelectorAll('.analysis-step');
  steps.forEach(s => { s.classList.remove('active'); s.classList.add('done', 'visible'); });
  steps[steps.length - 1].querySelector('.step-text').textContent = 'Analisi completata!';
  setTimeout(() => {
    document.getElementById('progress-view').style.display = 'none';
    callback();
  }, 500);
}

function errorProgress(message) {
  _stepTimers.forEach(t => clearTimeout(t));
  _stepTimers = [];
  const steps = document.querySelectorAll('.analysis-step');
  let activeIdx = -1;
  steps.forEach((s, i) => { if (s.classList.contains('active')) activeIdx = i; });
  if (activeIdx === -1) activeIdx = 0;
  for (let i = 0; i < activeIdx; i++) {
    steps[i].classList.remove('active');
    steps[i].classList.add('done', 'visible');
  }
  const errStep = steps[activeIdx];
  errStep.classList.remove('active');
  errStep.classList.add('visible', 'error');
  errStep.querySelector('.step-icon').textContent = '❌';
  errStep.querySelector('.step-text').textContent = message;
  const retryBtn = document.createElement('button');
  retryBtn.className = 'progress-retry-btn';
  retryBtn.textContent = 'Riprova';
  retryBtn.onclick = () => {
    document.getElementById('progress-view').style.display = 'none';
    document.getElementById('upload-view').style.display = 'block';
    const btn = document.getElementById('btn-analyze');
    btn.disabled = false;
    btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/></svg> Analizza con AI';
  };
  document.getElementById('analysis-steps').appendChild(retryBtn);
}

// ── Analisi
async function analizza() {
  if (!selectedFile) return;
  const btn = document.getElementById('btn-analyze');
  btn.disabled = true;
  const profilo = (document.querySelector('input[name="profilo-sel"]:checked') || {}).value || 'D2';
  const fd = new FormData();
  fd.append('file', selectedFile);
  startProgress();
  try {
    const r = await fetch(`${API}/api/analizza/${currentTipo}?profilo=${profilo}`, {method:'POST', body:fd});
    if (!r.ok) { const err = await r.json().catch(()=>({})); throw new Error(err.detail || `Errore ${r.status}`); }
    const d = await r.json();
    currentBollettaId = d.bolletta_id;
    salvaPersistenza(d, currentTipo, currentBollettaId, null);
    completeProgress(() => {
      showResult(d);
      history.replaceState(null, '', `/risultati/${currentBollettaId}`);
    });
  } catch(e) {
    errorProgress(e.message);
  }
}

function showResult(d, offerteSalvate) {
  document.getElementById('upload-view').style.display = 'none';
  document.getElementById('personal-data-view').style.display = 'none';
  document.querySelector('.hero').style.display = 'none';
  const fullscreen = document.getElementById('results-fullscreen');
  fullscreen.style.display = 'block';
  const panel = document.getElementById('result-panel');
  panel.classList.add('visible');

  const dg  = d.dati?.dati_generali          || {};
  const lc  = d.dati?.letture_e_consumi      || {};
  const ai  = d.dati?.analisi_ai             || {};
  const tipo   = d.tipo    || currentTipo;
  const unita  = d.unita   || (tipo === 'gas' ? 'Smc' : 'kWh');
  const totale = dg.totale_fattura;
  const consumo = lc.consumo_totale_periodo ?? lc.consumo_totale_smc;
  const fornitore = dg.fornitore || '—';
  const costoU = d.costo_unitario;

  document.getElementById('result-stats').innerHTML = `
    <div class="stat-box highlight"><div class="val">${totale != null ? totale.toFixed(2)+'€' : '—'}</div><div class="lbl">Totale bolletta</div></div>
    <div class="stat-box"><div class="val">${consumo != null ? consumo+' '+unita : '—'}</div><div class="lbl">Consumo</div></div>
    <div class="stat-box"><div class="val">${costoU != null ? costoU.toFixed(4)+'€' : '—'}</div><div class="lbl">Costo unitario</div></div>
    <div class="stat-box"><div class="val" style="font-size:.95rem">${fornitore}</div><div class="lbl">Fornitore</div></div>
  `;

  const anom = ai.anomalie_rilevate || [];
  const sugg = ai.suggerimenti || [];
  const anomEl = document.getElementById('ai-anomalie');
  anomEl.style.display = anom.length ? 'block' : 'none';
  if (anom.length) document.getElementById('anomalie-list').innerHTML = anom.map(x => `<span class="anomaly-tag">⚠ ${x}</span>`).join('');
  document.getElementById('suggerimenti-list').innerHTML = sugg.length
    ? sugg.map(s => `<div class="suggestion-item">${s}</div>`).join('')
    : '<div class="suggestion-item">Nessuna anomalia critica rilevata. Buona gestione dei consumi!</div>';

  // Mostra il link condivisibile
  if (currentBollettaId) mostraLinkCondivisibile(currentBollettaId);

  // Se c'erano offerte già salvate (ripristino sessione), mostrare direttamente
  if (offerteSalvate && offerteSalvate.length) {
    showOfferte(offerteSalvate);
  }

  fullscreen.scrollIntoView({behavior:'smooth', block:'start'});
}

// ── Link condivisibile
function mostraLinkCondivisibile(bollettaId) {
  const existing = document.getElementById('share-banner');
  if (existing) existing.remove();
  const url = `${window.location.origin}/risultati/${bollettaId}`;
  const banner = document.createElement('div');
  banner.id = 'share-banner';
  banner.className = 'share-banner';
  banner.innerHTML = `
    <div class="share-banner-text">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
      Questa analisi è salvata — condividila o riaprila in seguito
    </div>
    <button class="share-btn" onclick="copiaLink('${url}')">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
      Copia link
    </button>
  `;
  const panel = document.getElementById('result-panel');
  panel.insertBefore(banner, panel.firstChild);
}

function copiaLink(url) {
  navigator.clipboard.writeText(url).then(() => {
    showToast('Link copiato! Incollalo dove vuoi.', 'success');
  }).catch(() => {
    prompt('Copia questo link:', url);
  });
}

function resetAnalyzer() {
  document.querySelector('.hero').style.display = '';
  document.getElementById('results-fullscreen').style.display = 'none';
  document.getElementById('personal-data-view').style.display = personalData ? 'none' : 'block';
  document.getElementById('upload-view').style.display = personalData ? 'block' : 'none';
  document.getElementById('progress-view').style.display = 'none';
  document.getElementById('result-panel').classList.remove('visible');
  document.getElementById('offerte-list').style.display = 'none';
  const ctasEl = document.getElementById('offerte-ctas');
  if (ctasEl) ctasEl.style.display = 'none';
  const bestBox = document.getElementById('offerta-best-already');
  if (bestBox) { bestBox.style.display = 'none'; bestBox.innerHTML = ''; }
  const sb = document.getElementById('share-banner');
  if (sb) sb.remove();
  clearFile();
  currentBollettaId = null;
  cancellaPersistenza();
  history.replaceState(null, '', '/');
}

// ── Confronta
async function confronta() {
  if (!personalData) { showToast('Inserisci prima i tuoi dati', 'error'); return; }
  if (!currentBollettaId) { showToast('Analizza prima la bolletta', 'error'); return; }
  const btn = document.getElementById('btn-compare');
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner"></div> Confronto in corso…';
  try {
    const lead = {
      nome: personalData.nome,
      cognome: personalData.cognome,
      email: personalData.email,
      telefono: personalData.telefono,
      bolletta_id: currentBollettaId,
      tipo_richiesta: 'comparazione',
      consenso_privacy: personalData.consenso_privacy,
      consenso_marketing: personalData.consenso_marketing,
      consenso_cessione: personalData.consenso_cessione,
      consenso_profilazione: personalData.consenso_profilazione,
      consenso_marketing_terzi: personalData.consenso_marketing_terzi,
    };
    const lr = await fetch(`${API}/api/leads`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(lead)});
    if (!lr.ok) { const e = await lr.json().catch(()=>({})); throw new Error(e.detail || 'Errore salvataggio contatti'); }
    const cr = await fetch(`${API}/api/compara/${currentBollettaId}`, {method:'POST',
      headers:{'Content-Type':'application/json'}, body: JSON.stringify({})});
    if (!cr.ok) { const e = await cr.json().catch(()=>({})); throw new Error(e.detail || 'Errore confronto'); }
    const cd = await cr.json();
    const offerte = cd.offerte || [];
    // Salva offerte nella persistenza
    const stato = caricaPersistenza();
    if (stato) salvaPersistenza(stato.dati, stato.tipo, stato.bollettaId, offerte);
    showOfferte(offerte, cd.ultimo_aggiornamento_offerte);
  } catch(e) {
    showToast(e.message, 'error');
    btn.disabled = false;
    btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg> Confronta le Offerte';
  }
}

function _offerCtaHtml(offertaNome, fornitore) {
  const isOpen = isContactCenterOpen();
  // Use data-* attributes to avoid double-quote conflicts inside onclick="..."
  const dn = _escAttr(offertaNome);
  const df = _escAttr(fornitore);
  const rcBtn = `data-nome="${dn}" data-for="${df}" onclick="openRicontattoModal(this.dataset.nome,this.dataset.for)"`;
  const emBtn = `data-nome="${dn}" data-for="${df}" onclick="openEmailModal(this.dataset.nome,this.dataset.for)"`;
  if (isOpen) {
    return `<div class="offer-cta-wrap">
      <a href="tel:${CONTACT_CENTER_PHONE}" class="btn-offer-call">📞 Chiama ora — Attiva questa offerta</a>
      <button class="offer-cta-secondary" ${rcBtn}>Preferisci essere ricontattato? Lascia il tuo numero →</button>
    </div>`;
  }
  return `<div class="offer-cta-wrap offer-cta-closed">
    <button class="btn-offer-callback" ${rcBtn}>📅 Richiedi ricontatto telefonico</button>
    <button class="btn-offer-email" ${emBtn}>✉️ Contattaci via email</button>
    <p class="offer-cta-hours-note">Il nostro contact center è attivo lun–ven dalle 9:00 alle 18:00. Ti richiameremo al prossimo orario disponibile.</p>
  </div>`;
}

function _injectOfferBanner(hasSavings) {
  const existing = document.getElementById('offer-top-banner');
  if (existing) existing.remove();
  if (!hasSavings) return;
  const banner = document.createElement('div');
  banner.id = 'offer-top-banner';
  if (isContactCenterOpen()) {
    banner.className = 'offer-top-banner offer-top-banner-open';
    banner.innerHTML = `
      <div class="offer-top-banner-text"><strong>🟢 Siamo operativi!</strong> Chiama subito per attivare la miglior offerta con il supporto di un consulente.</div>
      <a href="tel:${CONTACT_CENTER_PHONE}" class="btn-offer-call btn-offer-call-sm">📞 ${CONTACT_CENTER_PHONE_DISPLAY}</a>`;
  } else {
    banner.className = 'offer-top-banner offer-top-banner-closed';
    banner.innerHTML = `
      <div class="offer-top-banner-text"><strong>🔴 Fuori orario</strong> — Il contact center riapre lun–ven 9:00–18:00. Lascia i tuoi dati e ti richiamiamo.</div>
      <button class="btn-offer-callback btn-offer-callback-sm" onclick="openRicontattoModal('','')">📅 Richiedi ricontatto</button>`;
  }
  const list = document.getElementById('offerte-list');
  list.parentElement.insertBefore(banner, list);
}

function showOfferte(offerte, ultimoAggiornamento) {
  const agg = document.getElementById('offerte-aggiornamento');
  if (agg) {
    if (ultimoAggiornamento) {
      const d = new Date(ultimoAggiornamento);
      agg.textContent = `Offerte aggiornate al ${d.toLocaleDateString('it-IT', {day:'2-digit',month:'long',year:'numeric'})}`;
      agg.style.display = 'block';
    } else {
      agg.style.display = 'none';
    }
  }

  const list    = document.getElementById('offerte-list');
  const bestBox = document.getElementById('offerta-best-already');
  const ctasEl  = document.getElementById('offerte-ctas');
  list.style.display = 'flex';

  if (!offerte.length) {
    list.innerHTML = '<p style="font-size:.88rem;color:var(--gray-400);text-align:center;padding:1rem">Nessuna offerta trovata per il tuo profilo.</p>';
    if (ctasEl) ctasEl.style.display = 'block';
    return;
  }

  const sorted     = [...offerte].sort((a,b) => (a.costo_annuo||999) - (b.costo_annuo||999));
  const bestSaving = sorted[0].risparmio_annuo || 0;

  // Se l'offerta attuale è già la più economica (risparmio <= 0)
  if (bestSaving <= 0 && bestBox) {
    bestBox.style.display = 'block';
    bestBox.innerHTML = `
      <div class="best-already-icon">🏆</div>
      <div class="best-already-text">
        <strong>Ottimo fiuto! La tua offerta attuale è già competitiva.</strong>
        <p>Abbiamo confrontato la tua bolletta con tutte le offerte del mercato libero e non abbiamo trovato un'alternativa che ti farebbe risparmiare in modo significativo. Significa che hai già scelto bene.</p>
        <p style="margin-top:.4rem;font-size:.82rem;color:var(--gray-400)">Vuoi comunque parlare con un consulente per valutare offerte bundle o soluzioni fotovoltaico?</p>
      </div>`;
  }

  _injectOfferBanner(bestSaving > 0);

  list.innerHTML = sorted.map((o, i) => {
    const best   = i === 0;
    const saving = o.risparmio_annuo;
    const dn = _escAttr(o.nome || '');
    const df = _escAttr(o.fornitore || '');
    return `<div class="offerta-card${best?' best':''}">
      <div class="offerta-card-top">
        ${best ? '<span class="offerta-badge">Miglior offerta</span>' : ''}
        <div style="flex:1;min-width:0">
          <div class="offerta-name">${o.nome||'—'}</div>
          <div class="offerta-fornitore">${o.fornitore||'—'} · ${o.tipo||''}</div>
        </div>
        <div>
          <div class="offerta-price">${o.costo_annuo ? o.costo_annuo.toFixed(0)+'€/anno' : '—'}</div>
          ${saving && saving > 0 ? `<div class="offerta-saving">risparmi ${saving.toFixed(0)}€/anno</div>` : saving < 0 ? '<div class="offerta-saving" style="color:var(--gray-400)">già conveniente</div>' : ''}
        </div>
      </div>
      <button class="btn-dettagli" data-nome="${dn}" data-for="${df}" onclick="openOfferDetail(this.dataset.nome,this.dataset.for)">Dettagli</button>
    </div>`;
  }).join('');

  if (ctasEl) ctasEl.style.display = 'block';
}

// ── Open offer detail → contact modal
function openOfferDetail(offertaNome, fornitore) {
  // Pre-fill contact form with personal data and offer info
  if (personalData) {
    document.getElementById('c-nome').value = personalData.nome || '';
    document.getElementById('c-cognome').value = personalData.cognome || '';
    document.getElementById('c-email').value = personalData.email || '';
    document.getElementById('c-tel').value = personalData.telefono || '';
  }
  // Set the offer type
  const offerSelect = document.getElementById('c-offerta');
  if (offertaNome) {
    // Try to match an option, fallback to first relevant
    const tipo = currentTipo === 'gas' ? 'gas' : 'luce';
    offerSelect.value = tipo;
  }
  // Update modal title to show offer name
  const formBox = document.querySelector('.contact-form-box h3');
  if (offertaNome) {
    formBox.textContent = `📋 ${offertaNome} — ${fornitore}`;
  }
  openContact();
}

// ── Contact form
async function submitContact() {
  const nome = document.getElementById('c-nome').value.trim();
  const email = document.getElementById('c-email').value.trim();
  const tel = document.getElementById('c-tel').value.trim();
  if (!nome || !email || !tel) { showToast('Compila tutti i campi obbligatori', 'error'); return; }
  try {
    const lead = {
      nome,
      cognome: document.getElementById('c-cognome').value.trim(),
      email, telefono: tel,
      tipo_richiesta: 'consulente',
      consenso_privacy: true,
      consenso_marketing: false,
      note: document.getElementById('c-offerta').value
    };
    const r = await fetch(`${API}/api/leads`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(lead)});
    if (!r.ok) throw new Error('Errore invio');
    ['c-nome','c-cognome','c-email','c-tel'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('c-offerta').value = '';
    document.getElementById('contact-success').classList.add('show');
    showToast('Richiesta inviata! Ti contatteremo presto.', 'success');
  } catch(e) {
    showToast('Errore nell\'invio. Riprova o chiamaci al 081 91 31 897.', 'error');
  }
}

function scrollToContact() { openContact(); }
function openContact() {
  document.getElementById('contact-overlay').classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeContact() {
  document.getElementById('contact-overlay').classList.remove('open');
  document.body.style.overflow = '';
}

// ── FAQ accordion
function toggleFaq(el) {
  const item = el.parentElement;
  const isOpen = item.classList.contains('open');
  document.querySelectorAll('.faq-item.open').forEach(i => i.classList.remove('open'));
  if (!isOpen) item.classList.add('open');
}

// ── Toast
function showToast(msg, type='') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show' + (type ? ' '+type : '');
  setTimeout(() => t.classList.remove('show'), 4000);
}

// ══════════════════════════════════════════════════════════════════════════════
// AUTO-RESTORE — ripristina analisi al ritorno sulla pagina
// Fonti in ordine di priorità:
//   1. Meta tag iniettato da /risultati/{id} (link condivisibile)
//   2. sessionStorage (navigazione interna: guida → home)
// ══════════════════════════════════════════════════════════════════════════════
async function autoRestore() {
  // Fonte 1: link condivisibile (/risultati/{id})
  const metaId = document.querySelector('meta[name="br-risultati-id"]')?.content;
  const metaTipo = document.querySelector('meta[name="br-risultati-tipo"]')?.content;
  if (metaId) {
    currentBollettaId = metaId;
    if (metaTipo) currentTipo = metaTipo;
    // Mostra banner "ripristino in corso"
    showBannerRipristino('Carico la tua analisi salvata…');
    try {
      // Richiede i dati dal backend (già elaborati, non rianalizza il file)
      const r = await fetch(`${API}/api/analisi/${metaId}`);
      if (r.ok) {
        const d = await r.json();
        nascondiBannerRipristino();
        salvaPersistenza(d, currentTipo, currentBollettaId, null);
        showResult(d);
        // Scroll fluido ai risultati
        setTimeout(() => document.getElementById('results-fullscreen').scrollIntoView({behavior:'smooth', block:'start'}), 300);
        return;
      }
    } catch(e) {}
    nascondiBannerRipristino();
    showToast('Analisi non trovata o scaduta', 'error');
    history.replaceState(null, '', '/');
    return;
  }

  // Fonte 2: sessionStorage (navigazione interna)
  const stato = caricaPersistenza();
  if (stato) {
    currentBollettaId = stato.bollettaId;
    currentTipo = stato.tipo || 'luce';
    showBannerRipristino('Analisi precedente ripristinata — puoi continuare da dove eri rimasto');
    showResult(stato.dati, stato.offerte);
    setTimeout(nascondiBannerRipristino, 4000);
    history.replaceState(null, '', `/risultati/${currentBollettaId}`);
  }
}

function showBannerRipristino(msg) {
  let b = document.getElementById('restore-banner');
  if (!b) {
    b = document.createElement('div');
    b.id = 'restore-banner';
    b.className = 'restore-banner';
    const target = document.getElementById('result-panel') || document.getElementById('analyzer');
    target.prepend(b);
  }
  b.textContent = msg;
  b.style.display = 'block';
}
function nascondiBannerRipristino() {
  const b = document.getElementById('restore-banner');
  if (b) b.style.display = 'none';
}

// Avvio all'apertura della pagina
window.addEventListener('DOMContentLoaded', autoRestore);

// ── MODALE INPUT MANUALE ──
function openManualModal() {
  document.getElementById('manual-modal-overlay').classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeManualModal() {
  document.getElementById('manual-modal-overlay').classList.remove('open');
  document.body.style.overflow = '';
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeContact(); closeManualModal(); closeFab(); closeRicontattoModal(); closeEmailModal(); } });

// ── FAB ──────────────────────────────────────────────────────────────────────
function toggleFab() {
  document.getElementById('fab-container').classList.toggle('open');
}
function closeFab() {
  document.getElementById('fab-container')?.classList.remove('open');
}
document.addEventListener('click', e => {
  const fab = document.getElementById('fab-container');
  if (fab && fab.classList.contains('open') && !fab.contains(e.target)) closeFab();
});

async function analizzaManuale(e) {
  e.preventDefault();
  const getVal = id => { const el = document.getElementById(id); return el ? el.value : ''; };
  const getChecked = name => [...document.querySelectorAll(`input[name="${name}"]:checked`)].map(el => el.value);

  const dati = {
    tipo: getVal('m-tipo'),
    profilo: getVal('m-profilo'),
    fornitore: getVal('m-fornitore'),
    mercato: getVal('m-mercato'),
    spesa_mensile: getVal('m-spesa'),
    kwh_anno: getVal('m-kwh'),
    smc_anno: getVal('m-smc'),
    potenza_kw: getVal('m-potenza'),
    fascia: getVal('m-fascia'),
    persone: getVal('m-persone'),
    mq: getVal('m-mq'),
    riscaldamento: getVal('m-riscaldamento'),
    applianze: getChecked('applianze'),
    orario_uso: getVal('m-orario'),
    fotovoltaico: getVal('m-fotovoltaico'),
    priorita: getVal('m-priorita'),
  };

  // Chiudi modale e passa al result panel
  closeManualModal();
  currentTipo = dati.tipo.includes('gas') && !dati.tipo.includes('luce') ? 'gas' : 'luce';
  document.getElementById('upload-view').style.display = 'none';
  document.getElementById('personal-data-view').style.display = 'none';
  document.querySelector('.hero').style.display = 'none';
  document.getElementById('results-fullscreen').style.display = 'block';
  document.getElementById('result-panel').classList.add('visible');

  // Mostra stats sintetici dai dati inseriti
  const statsEl = document.getElementById('result-stats');
  statsEl.innerHTML = '';
  if (dati.spesa_mensile) statsEl.innerHTML += `<div class="result-stat"><div class="stat-val">€${dati.spesa_mensile}/mese</div><div class="stat-lbl">Spesa dichiarata</div></div>`;
  if (dati.kwh_anno) statsEl.innerHTML += `<div class="result-stat"><div class="stat-val">${parseInt(dati.kwh_anno).toLocaleString('it')} kWh</div><div class="stat-lbl">Consumo luce/anno</div></div>`;
  if (dati.smc_anno) statsEl.innerHTML += `<div class="result-stat"><div class="stat-val">${parseInt(dati.smc_anno).toLocaleString('it')} Smc</div><div class="stat-lbl">Consumo gas/anno</div></div>`;
  if (dati.persone) statsEl.innerHTML += `<div class="result-stat"><div class="stat-val">${dati.persone}</div><div class="stat-lbl">Persone in casa</div></div>`;

  // Chiama backend con i dati manuali
  try {
    const resp = await fetch('/api/analizza-manuale', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(dati)
    });
    if (!resp.ok) throw new Error('Errore server');
    const res = await resp.json();
    if (res.suggerimenti?.length) {
      document.getElementById('ai-suggerimenti').style.display = 'block';
      document.getElementById('suggerimenti-list').innerHTML = res.suggerimenti.map(s => `<div class="sug-item">${s}</div>`).join('');
    }
    if (res.anomalie?.length) {
      document.getElementById('ai-anomalie').style.display = 'block';
      document.getElementById('anomalie-list').innerHTML = res.anomalie.map(a => `<div class="anom-item">${a}</div>`).join('');
    }
  } catch {
    // Mostra sezione confronto direttamente
  }
  document.getElementById('compare-section').style.display = 'block';
}

// ── MODALE RICONTATTO TELEFONICO ──────────────────────────────────────────────
function openRicontattoModal(offertaNome, fornitore) {
  // Arguments may come from dataset (HTML-decoded by browser) or from inline calls
  _currentOfferName      = offertaNome || '';
  _currentOfferFornitore = fornitore   || '';
  const infoEl = document.getElementById('ricontatto-offerta-info');
  if (offertaNome) {
    infoEl.textContent = `Offerta: ${offertaNome}${fornitore ? ' — ' + fornitore : ''}`;
    infoEl.style.display = 'block';
  } else {
    infoEl.style.display = 'none';
  }
  document.getElementById('ricontatto-form').reset();
  document.getElementById('ricontatto-form').style.display = '';
  document.getElementById('rc-success').style.display = 'none';
  document.getElementById('ricontatto-modal-overlay').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeRicontattoModal() {
  document.getElementById('ricontatto-modal-overlay').classList.remove('open');
  document.body.style.overflow = '';
}

async function submitRicontatto(e) {
  e.preventDefault();
  const telefono = document.getElementById('rc-telefono').value.trim();
  // Validate Italian phone
  if (!/^(\+39|0039)?[\s]?3[0-9]{8,9}$/.test(telefono.replace(/[\s\-]/g, ''))) {
    showToast('Inserisci un numero di cellulare italiano valido (es. 333 1234567)', 'error');
    return;
  }
  const btn = document.getElementById('rc-submit');
  btn.disabled = true;
  btn.textContent = 'Invio in corso…';
  try {
    const r = await fetch(`${API}/api/leads`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        nome:                    document.getElementById('rc-nome').value.trim(),
        cognome:                 document.getElementById('rc-cognome').value.trim(),
        telefono,
        tipo_richiesta:          'ricontatto',
        offerta_richiesta:       _currentOfferName || null,
        fascia_oraria_preferita: document.getElementById('rc-fascia').value,
        bolletta_id:             currentBollettaId,
        consenso_privacy:        true,
      })
    });
    if (!r.ok) throw new Error('Errore server');
    document.getElementById('ricontatto-form').style.display = 'none';
    document.getElementById('rc-success').style.display = 'block';
  } catch {
    showToast('Errore nell\'invio. Riprova o chiamaci al ' + CONTACT_CENTER_PHONE_DISPLAY + '.', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Invia richiesta di ricontatto';
  }
}

// ── MODALE CONTATTO VIA EMAIL ─────────────────────────────────────────────────
function openEmailModal(offertaNome, fornitore) {
  _currentOfferName      = offertaNome || '';
  _currentOfferFornitore = fornitore   || '';
  const infoEl = document.getElementById('email-offerta-info');
  if (offertaNome) {
    infoEl.textContent = `Offerta: ${offertaNome}${fornitore ? ' — ' + fornitore : ''}`;
    infoEl.style.display = 'block';
  } else {
    infoEl.style.display = 'none';
  }
  // Reset then pre-fill message
  document.getElementById('email-offerta-form').reset();
  document.getElementById('email-offerta-form').style.display = '';
  document.getElementById('eo-success').style.display = 'none';
  if (offertaNome) {
    document.getElementById('eo-messaggio').value =
      `Sono interessato/a all'offerta ${offertaNome} di ${fornitore}. Vorrei maggiori informazioni.`;
  }
  document.getElementById('email-offerta-modal-overlay').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeEmailModal() {
  document.getElementById('email-offerta-modal-overlay').classList.remove('open');
  document.body.style.overflow = '';
}

async function submitEmailOfferta(e) {
  e.preventDefault();
  const email = document.getElementById('eo-email').value.trim();
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    showToast('Inserisci un indirizzo email valido', 'error');
    return;
  }
  const btn = document.getElementById('eo-submit');
  btn.disabled = true;
  btn.textContent = 'Invio in corso…';
  try {
    const r = await fetch(`${API}/api/leads`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        nome:              document.getElementById('eo-nome').value.trim(),
        email,
        note:              document.getElementById('eo-messaggio').value.trim(),
        tipo_richiesta:    'email',
        offerta_richiesta: _currentOfferName || null,
        bolletta_id:       currentBollettaId,
        consenso_privacy:  true,
      })
    });
    if (!r.ok) throw new Error('Errore server');
    document.getElementById('email-offerta-form').style.display = 'none';
    document.getElementById('eo-success').style.display = 'block';
  } catch {
    showToast('Errore nell\'invio. Riprova.', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Invia richiesta';
  }
}
