/* ═══ RESEARCH AGENT (browser) ═══ */

let _researchRunning = false;
let _researchCancel  = false;

const RESEARCH_SYSTEM_PROMPT = `Sei un analista specializzato nel mercato del vino italiano.
Analizza le informazioni sull'azienda e rispondi SOLO con un oggetto JSON valido (niente testo fuori dal JSON):

{
  "affidabilita": <1-5>,
  "vino_italiano": "<si|probabile|forse|non_risulta|no>",
  "tipo_business": "<importatore|distributore|retailer|horeca|online|misto|sconosciuto>",
  "mercato_target": "<horeca|retail|online|misto|sconosciuto>",
  "raccomandato": "<si|forse|no>",
  "note": "<max 2 righe: punti chiave per decidere se contattare>"
}

Criteri di valutazione:
- affidabilita: 5=azienda solida con sito professionale e storia consolidata; 4=buoni segnali; 3=info parziali; 2=dati scarsi; 1=nessuna info o segnali negativi
- vino_italiano: si=citano esplicitamente vini italiani; probabile=portafoglio mediterraneo/europeo; forse=importatori generici di vino; non_risulta=nessuna info trovata; no=solo birra/spirits/cibo
- raccomandato: si=contattare con priorità; forse=vale la pena verificare; no=non pertinente o inaffidabile
- Considera dipendenti, fatturato, tipologia cliente (horeca vs retail) per valutare dimensione e fit`;

/* ── API CALLS ── */

async function _rschSearch(company, country) {
  if (!rsch.serperKey) return '';
  try {
    const r = await fetch('https://google.serper.dev/search', {
      method: 'POST',
      headers: { 'X-API-KEY': rsch.serperKey, 'Content-Type': 'application/json' },
      body: JSON.stringify({ q: `"${company}" wine importer ${country}`, num: 6, gl: 'us', hl: 'en' })
    });
    if (!r.ok) return '';
    const data = await r.json();
    const parts = [];
    if (data.knowledgeGraph) {
      const kg = data.knowledgeGraph;
      parts.push(`[Knowledge Graph] ${kg.title||''} — ${kg.description||''} (${kg.website||''})`);
    }
    (data.organic || []).slice(0, 5).forEach(i =>
      parts.push(`[${i.title||''}] ${i.snippet||''} (${i.link||''})`)
    );
    return parts.join('\n');
  } catch(e) { console.warn('Serper error:', e); return ''; }
}

async function _rschFetchWebsite(url) {
  if (!url || !url.startsWith('http')) return '';
  try {
    const proxy = `https://api.allorigins.win/raw?url=${encodeURIComponent(url)}`;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 9000);
    const r = await fetch(proxy, { signal: ctrl.signal });
    clearTimeout(timer);
    if (!r.ok) return '';
    const html = await r.text();
    // Strip HTML tags, collapse whitespace, return first 2500 chars
    return html.replace(/<style[\s\S]*?<\/style>/gi,'')
               .replace(/<script[\s\S]*?<\/script>/gi,'')
               .replace(/<[^>]+>/g,' ')
               .replace(/\s+/g,' ').trim()
               .slice(0, 2500);
  } catch { return ''; }
}

async function _rschAnalyze(c, searchText, webText) {
  if (!rsch.groqKey) return {};
  const prompt = `Azienda: ${c.company||''}
Paese: ${c.country||''} | Città: ${c.city||''}
Tipo (BWI): ${c.type||''} | Prodotti: ${c.prodType||''}
Dipendenti: ${c.employees||'?'} | Fatturato: ${c.sales||'?'}
Sito dichiarato: ${c.website||'(nessuno)'}

--- RISULTATI GOOGLE ---
${searchText || '(nessun risultato trovato)'}

--- TESTO DAL SITO WEB ---
${webText ? webText.slice(0, 1800) : '(non disponibile o irraggiungibile)'}`;

  try {
    const r = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${rsch.groqKey}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'llama-3.3-70b-versatile',
        messages: [
          { role: 'system', content: RESEARCH_SYSTEM_PROMPT },
          { role: 'user',   content: prompt }
        ],
        temperature: 0.1,
        max_tokens: 450
      })
    });
    if (!r.ok) { console.warn('Groq error:', r.status); return {}; }
    const content = (await r.json()).choices?.[0]?.message?.content?.trim() || '';
    const m = content.match(/\{[\s\S]*\}/);
    if (m) return JSON.parse(m[0]);
    return {};
  } catch(e) { console.warn('Groq exception:', e); return {}; }
}

/* ── MODAL ── */

function openResearchModal(country, forceAll) {
  if (!rsch.serperKey || !rsch.groqKey) {
    toast('Configura le API key Serper e Groq nelle Impostazioni');
    openSettings();
    return;
  }
  const allContacts = db.contacts.filter(c => c.country === country);
  if (!allContacts.length) { toast('Nessun contatto per ' + country); return; }

  const alreadyDone = allContacts.filter(c => c.research).length;
  const toAnalyze   = forceAll ? allContacts : allContacts.filter(c => !c.research);
  const skipped     = allContacts.length - toAnalyze.length;

  // Se sono tutti già analizzati e non forceAll, proponi scelta
  if (!forceAll && alreadyDone > 0 && toAnalyze.length === 0) {
    showModal(`
      <div class="mt">🔬 Analisi AI — ${esc(country)}</div>
      <div style="font-size:13px;color:var(--text2);margin-bottom:16px">
        Tutti i ${allContacts.length} contatti sono già stati analizzati.
      </div>
      <div class="mf">
        <button class="btn" onclick="closeModal()">Annulla</button>
        <button class="btn btp" onclick="closeModal();openResearchModal('${esc(country)}',true)">Ri-analizza tutti</button>
      </div>
    `);
    return;
  }

  const skipNote = skipped > 0
    ? `<div style="font-size:12px;color:var(--green-tx);background:var(--green-bg);padding:4px 10px;border-radius:20px;display:inline-block">✓ ${skipped} già analizzati — saltati</div>`
    : '';

  showModal(`
    <div class="mt">🔬 Analisi AI — ${esc(country)}</div>
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap">
      <span style="font-size:13px;color:var(--text2)">${toAnalyze.length} da analizzare</span>
      ${skipNote}
    </div>

    <div style="background:var(--bg2);border-radius:8px;padding:12px;margin:4px 0 10px">
      <div style="display:flex;justify-content:space-between;align-items:center;font-size:12px;color:var(--text2);margin-bottom:7px">
        <span id="rsch-lbl" style="font-style:italic">In attesa di avvio...</span>
        <span id="rsch-cnt" style="font-weight:700;color:var(--text1)">0 / ${toAnalyze.length}</span>
      </div>
      <div style="background:var(--brd);border-radius:4px;height:7px;overflow:hidden">
        <div id="rsch-bar" style="width:0%;height:100%;background:var(--accent);transition:width .25s;border-radius:4px"></div>
      </div>
    </div>

    <div id="rsch-results" style="max-height:320px;overflow-y:auto;display:flex;flex-direction:column;gap:6px;padding-right:2px"></div>
    <div id="rsch-summary" style="display:none;background:var(--bg2);border-radius:8px;padding:12px;margin-top:12px;font-size:13px;line-height:1.7"></div>

    <div class="mf" style="margin-top:14px">
      <button id="rsch-cancel" class="btn" onclick="cancelResearch()">Annulla</button>
      <button id="rsch-done"   class="btn btp" style="display:none" onclick="closeModal()">Chiudi</button>
    </div>
  `);

  _researchCancel = false;
  _runResearch(toAnalyze, country);
}

async function _runResearch(contacts, country) {
  _researchRunning = true;
  const total = contacts.length;
  let done = 0, errors = 0;
  const stats = { si:0, forse:0, no:0, vino:0 };

  for (const c of contacts) {
    if (_researchCancel) break;

    const lbl = document.getElementById('rsch-lbl');
    if (lbl) lbl.textContent = `Analizzando: ${(c.company||'').slice(0,45)}`;

    // 1. Google search via Serper
    const searchText = await _rschSearch(c.company, country);

    // 2. Visita sito web (via proxy CORS)
    const webText = c.website ? await _rschFetchWebsite(c.website) : '';

    // 3. Analisi AI via Groq
    const analysis = await _rschAnalyze(c, searchText, webText);

    // Salva risultato nel contatto
    if (Object.keys(analysis).length) {
      c.research = { ...analysis, analyzed_at: new Date().toISOString() };
      const rec = analysis.raccomandato;
      if (rec === 'si')    stats.si++;
      else if (rec === 'forse') stats.forse++;
      else if (rec === 'no')   stats.no++;
      if (['si','probabile'].includes(analysis.vino_italiano)) stats.vino++;
      _appendResearchCard(c.company, analysis);
    } else {
      errors++;
    }

    done++;
    const pct = Math.round(done / total * 100);
    const bar = document.getElementById('rsch-bar');
    const cnt = document.getElementById('rsch-cnt');
    if (bar) bar.style.width = pct + '%';
    if (cnt) cnt.textContent = `${done} / ${total}`;

    // Rate limit: ~1.1s/contatto (Serper: 2500 ricerche/mese gratis)
    await new Promise(res => setTimeout(res, 700));
  }

  _researchRunning = false;

  // Persisti su GitHub
  saveDB();

  // Aggiorna UI
  const lbl = document.getElementById('rsch-lbl');
  if (lbl) lbl.textContent = _researchCancel ? 'Interrotto' : 'Completato ✓';
  document.getElementById('rsch-cancel')?.style.setProperty('display','none');
  const doneBtn = document.getElementById('rsch-done');
  if (doneBtn) doneBtn.style.display = '';

  const summary = document.getElementById('rsch-summary');
  if (summary) {
    summary.style.display = 'block';
    summary.innerHTML = _researchCancel
      ? `<strong>Analisi interrotta</strong> — ${done} / ${total} analizzati`
      : `<strong>Analisi completata</strong> — ${done} contatti analizzati<br>
         <span style="color:#2e7d32">✅ Raccomandati: <strong>${stats.si}</strong></span> &nbsp;·&nbsp;
         <span style="color:#e65100">🟡 Forse: <strong>${stats.forse}</strong></span> &nbsp;·&nbsp;
         <span style="color:#c62828">❌ No: <strong>${stats.no}</strong></span><br>
         🍷 Vino italiano confermato/probabile: <strong>${stats.vino}</strong>
         ${errors ? `<br><span style="color:var(--text3)">⚠ ${errors} senza risposta API</span>` : ''}`;
  }

  renderDashboard();
}

function _appendResearchCard(company, r) {
  const el = document.getElementById('rsch-results');
  if (!el) return;
  const REC = { si:'#e8f5e9:#2e7d32', forse:'#fff3e0:#e65100', no:'#fce4ec:#c62828' };
  const [bg,tx] = (REC[r.raccomandato] || 'var(--bg2):var(--text2)').split(':');
  const stars = '★'.repeat(r.affidabilita||0) + '☆'.repeat(5-(r.affidabilita||0));
  el.insertAdjacentHTML('beforeend', `
    <div style="border:1px solid var(--brd);border-radius:8px;padding:9px 12px;font-size:12px">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;flex-wrap:wrap">
        <strong style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(company)}</strong>
        <span style="color:#f59e0b;letter-spacing:-1px;font-size:13px">${stars}</span>
        <span style="padding:1px 8px;border-radius:10px;font-size:11px;font-weight:700;background:${bg};color:${tx}">${r.raccomandato||'?'}</span>
        <span style="color:var(--text3);font-size:11px;white-space:nowrap">${esc(r.tipo_business||'')}</span>
      </div>
      <div style="color:var(--text2);line-height:1.4">${esc(r.note||'')}</div>
    </div>`);
  el.scrollTop = el.scrollHeight;
}

function cancelResearch() {
  _researchCancel = true;
  const lbl = document.getElementById('rsch-lbl');
  if (lbl) lbl.textContent = 'Annullo dopo il contatto corrente...';
}

/* ── BADGE IN LISTA CONTATTI ── */

function researchBadge(r) {
  if (!r) return '';
  const REC = { si:'#e8f5e9:#2e7d32', forse:'#fff3e0:#e65100', no:'#fce4ec:#c62828' };
  const [bg,tx] = (REC[r.raccomandato] || 'var(--bg2):var(--text2)').split(':');
  const stars = '★'.repeat(r.affidabilita||0);
  return `<span style="font-size:10px;background:${bg};color:${tx};padding:1px 6px;border-radius:10px;margin-left:4px;font-weight:700">${stars} ${r.raccomandato||'?'}</span>`;
}
