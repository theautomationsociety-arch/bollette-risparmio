const API = window.location.origin;
let currentTipo = 'luce';
let currentBollettaId = null;
let selectedFile = null;

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

// ── Tipo tabs
function setTipo(t, el) {
  currentTipo = t;
  document.querySelectorAll('.tipo-tab').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  const sel = document.getElementById('profilo-sel');
  sel.innerHTML = t === 'luce'
    ? '<option value="D2">D2 – Uso domestico residente</option><option value="D3">D3 – Uso domestico non residente</option><option value="BTA">BTA – Piccola impresa</option><option value="CDO">CDO – Condominio</option>'
    : '<option value="D2">D2 – Uso domestico residente</option><option value="D3">D3 – Uso domestico non residente</option><option value="BTA">BTA – Piccola impresa</option>';
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

// ── Analisi
async function analizza() {
  if (!selectedFile) return;
  const btn = document.getElementById('btn-analyze');
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner"></div> Analisi in corso…';
  const profilo = document.getElementById('profilo-sel').value;
  const fd = new FormData();
  fd.append('file', selectedFile);
  try {
    const r = await fetch(`${API}/api/analizza/${currentTipo}?profilo=${profilo}`, {method:'POST', body:fd});
    if (!r.ok) { const err = await r.json().catch(()=>({})); throw new Error(err.detail || `Errore ${r.status}`); }
    const d = await r.json();
    currentBollettaId = d.bolletta_id;
    salvaPersistenza(d, currentTipo, currentBollettaId, null);
    showResult(d);
    // Aggiorna URL per condivisione senza reload
    history.replaceState(null, '', `/risultati/${currentBollettaId}`);
  } catch(e) {
    showToast(e.message, 'error');
    btn.disabled = false;
    btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/></svg> Analizza con AI';
  }
}

function showResult(d, offerteSalvate) {
  document.getElementById('upload-view').style.display = 'none';
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
    document.getElementById('lead-form').style.display = 'none';
    showOfferte(offerteSalvate);
  }

  panel.scrollIntoView({behavior:'smooth', block:'nearest'});
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
  document.getElementById('upload-view').style.display = 'block';
  document.getElementById('result-panel').classList.remove('visible');
  document.getElementById('offerte-list').style.display = 'none';
  document.getElementById('lead-form').style.display = 'flex';
  const sb = document.getElementById('share-banner');
  if (sb) sb.remove();
  clearFile();
  currentBollettaId = null;
  cancellaPersistenza();
  history.replaceState(null, '', '/');
}

// ── Confronta
async function confronta() {
  const nome = document.getElementById('lead-nome').value.trim();
  const cognome = document.getElementById('lead-cognome').value.trim();
  if (!nome || !cognome) { showToast('Nome e cognome obbligatori', 'error'); return; }
  if (!currentBollettaId) { showToast('Analizza prima la bolletta', 'error'); return; }
  const btn = document.getElementById('btn-compare');
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner"></div> Confronto in corso…';
  try {
    const lead = {nome, cognome,
      email: document.getElementById('lead-email').value.trim(),
      telefono: document.getElementById('lead-telefono').value.trim(),
      bolletta_id: currentBollettaId,
      tipo_richiesta: 'comparazione',
      consenso_privacy: true,
      consenso_marketing: false
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

function showOfferte(offerte, ultimoAggiornamento) {
  document.getElementById('lead-form').style.display = 'none';
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
  const list = document.getElementById('offerte-list');
  list.style.display = 'flex';
  if (!offerte.length) { list.innerHTML = '<p style="font-size:.88rem;color:var(--gray-400);text-align:center;padding:1rem">Nessuna offerta trovata per il tuo profilo.</p>'; return; }
  const sorted = [...offerte].sort((a,b) => (a.costo_annuo||999) - (b.costo_annuo||999));
  list.innerHTML = sorted.map((o, i) => {
    const best = i === 0;
    const saving = o.risparmio_annuo;
    return `<div class="offerta-card${best?' best':''}">
      ${best?'<span class="offerta-badge">Miglior offerta</span>':''}
      <div style="flex:1">
        <div class="offerta-name">${o.nome||'—'}</div>
        <div class="offerta-fornitore">${o.fornitore||'—'} · ${o.tipo||''}</div>
      </div>
      <div>
        <div class="offerta-price">${o.costo_annuo ? o.costo_annuo.toFixed(0)+'€/anno' : '—'}</div>
        ${saving && saving > 0 ? `<div class="offerta-saving">risparmi ${saving.toFixed(0)}€/anno</div>` : ''}
      </div>
    </div>`;
  }).join('');
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

function scrollToContact() { document.getElementById('contatti').scrollIntoView({behavior:'smooth'}); }

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
        // Scroll fluido all'analisi
        setTimeout(() => document.getElementById('analyzer').scrollIntoView({behavior:'smooth', block:'start'}), 300);
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
    document.getElementById('analyzer').prepend(b);
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
