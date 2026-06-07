/* ═══ RESEARCH AGENT (browser) ═══ */

let _researchRunning = false;
let _researchCancel  = false;

/* ── QUOTA GIORNALIERA ── */
const AI_DAILY_LIMIT = 305;

function _getUsage() {
  const today = new Date().toISOString().slice(0, 10);
  const stored = JSON.parse(localStorage.getItem('rschDailyUsage') || '{}');
  if (stored.date !== today) return { date: today, calls: 0 };
  return stored;
}

function _incrementUsage() {
  const u = _getUsage();
  u.calls++;
  localStorage.setItem('rschDailyUsage', JSON.stringify(u));
  _updateQuotaBar();
  return u.calls;
}

function getRemainingCalls() {
  return Math.max(0, AI_DAILY_LIMIT - _getUsage().calls);
}

function _updateQuotaBar() {
  const u = _getUsage();
  const pct = Math.min(100, Math.round(u.calls / AI_DAILY_LIMIT * 100));
  const rem = AI_DAILY_LIMIT - u.calls;
  const el = document.getElementById('rsch-quota-bar');
  const lbl = document.getElementById('rsch-quota-lbl');
  if (el) {
    el.style.width = pct + '%';
    el.style.background = pct > 85 ? 'var(--coral-tx)' : pct > 60 ? '#f59e0b' : 'var(--accent)';
  }
  if (lbl) lbl.textContent = `${Math.max(0, rem)} analisi disponibili oggi`;
}

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
  if (!rsch.claudeKey) return {};
  const prompt = `Azienda: ${c.company||''}
Paese: ${c.country||''} | Città: ${c.city||''}
Tipo (BWI): ${c.type||''} | Prodotti: ${c.prodType||''}
Dipendenti: ${c.employees||'?'} | Fatturato: ${c.sales||'?'}
Sito dichiarato: ${c.website||'(nessuno)'}

--- RISULTATI GOOGLE ---
${searchText || '(nessun risultato trovato)'}

--- TESTO DAL SITO WEB ---
${webText ? webText.slice(0, 1800) : '(non disponibile o irraggiungibile)'}`;

  const body = JSON.stringify({
    model: 'claude-haiku-4-5',
    system: RESEARCH_SYSTEM_PROMPT,
    messages: [
      { role: 'user', content: prompt }
    ],
    temperature: 0.1,
    max_tokens: 450
  });

  // Retry con backoff su 429 (rate limit Claude — raro sui piani a pagamento)
  for (let attempt = 0; attempt < 4; attempt++) {
    try {
      const r = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
          'x-api-key':                              rsch.claudeKey,
          'anthropic-version':                      '2023-06-01',
          'anthropic-dangerous-direct-browser-access': 'true',
          'Content-Type':                           'application/json'
        },
        body
      });

      if (r.status === 429) {
        // Rate limit: non conta sul budget giornaliero, aspetta e riprova
        const retryAfter = parseInt(r.headers.get('retry-after') || '0') || 0;
        const wait = retryAfter > 0 ? retryAfter * 1000 : [15000, 30000, 60000][attempt] || 60000;
        const lbl = document.getElementById('rsch-lbl');
        if (lbl) lbl.textContent = `⏳ Rate limit Claude — attendo ${Math.round(wait/1000)}s (tentativo ${attempt+1}/4)...`;
        await new Promise(res => setTimeout(res, wait));
        continue;
      }

      // Chiamata reale ricevuta (successo o errore): conta sul budget giornaliero
      _incrementUsage();

      if (!r.ok) { console.warn('Claude error:', r.status, await r.text().catch(()=>'')); return {}; }

      const data    = await r.json();
      const content = (data.content?.[0]?.text || '').trim();
      const m = content.match(/\{[\s\S]*\}/);
      if (m) return JSON.parse(m[0]);
      return {};
    } catch(e) {
      console.warn('Claude exception:', e);
      if (attempt < 3) await new Promise(res => setTimeout(res, 5000));
    }
  }
  return {};
}

/* ── MODAL ── */

function openResearchModal(country, forceAll) {
  if (!rsch.serperKey || !rsch.claudeKey) {
    toast('Configura le API key Serper e Claude nelle Impostazioni');
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

  const remaining = getRemainingCalls();
  const canAnalyze = Math.min(toAnalyze.length, remaining);

  // Quota esaurita
  if (remaining === 0) {
    const u = _getUsage();
    showModal(`
      <div class="mt">🔬 Analisi AI — ${esc(country)}</div>
      <div style="background:#fce4ec;border-radius:10px;padding:16px;text-align:center;margin-bottom:16px">
        <div style="font-size:32px;margin-bottom:8px">📊</div>
        <div style="font-size:15px;font-weight:700;color:#c62828;margin-bottom:4px">Quota giornaliera esaurita</div>
        <div style="font-size:13px;color:#c62828">${u.calls} / ${AI_DAILY_LIMIT} analisi usate oggi</div>
        <div style="font-size:12px;color:var(--text2);margin-top:8px">La quota si resetta a mezzanotte.</div>
      </div>
      <div class="mf"><button class="btn btp" onclick="closeModal()">OK</button></div>
    `);
    return;
  }

  const u = _getUsage();
  const usedPct = Math.min(100, Math.round(u.calls / AI_DAILY_LIMIT * 100));
  const barColor = usedPct > 85 ? 'var(--coral-tx)' : usedPct > 60 ? '#f59e0b' : 'var(--accent)';

  const skipNote = skipped > 0
    ? `<span style="font-size:12px;color:var(--green-tx);background:var(--green-bg);padding:3px 9px;border-radius:20px">✓ ${skipped} già analizzati — saltati</span>`
    : '';
  const capNote = canAnalyze < toAnalyze.length
    ? `<span style="font-size:12px;color:#e65100;background:#fff3e0;padding:3px 9px;border-radius:20px">⚠ quota: solo ${canAnalyze} analizzabili oggi</span>`
    : '';

  showModal(`
    <div class="mt">🔬 Analisi AI — ${esc(country)}</div>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap">
      <span style="font-size:13px;color:var(--text2)">${canAnalyze} da analizzare</span>
      ${skipNote}${capNote}
    </div>

    <!-- Quota bar -->
    <div style="background:var(--bg2);border-radius:8px;padding:10px 12px;margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text2);margin-bottom:5px">
        <span id="rsch-quota-lbl">${remaining} analisi disponibili oggi</span>
        <span style="color:var(--text3)">${u.calls} / ${AI_DAILY_LIMIT} usate</span>
      </div>
      <div style="background:var(--brd);border-radius:4px;height:5px;overflow:hidden">
        <div id="rsch-quota-bar" style="width:${usedPct}%;height:100%;background:${barColor};border-radius:4px;transition:width .3s"></div>
      </div>
    </div>

    <!-- Progresso analisi -->
    <div style="background:var(--bg2);border-radius:8px;padding:12px;margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;align-items:center;font-size:12px;color:var(--text2);margin-bottom:7px">
        <span id="rsch-lbl" style="font-style:italic">In attesa di avvio...</span>
        <span id="rsch-cnt" style="font-weight:700;color:var(--text1)">0 / ${canAnalyze}</span>
      </div>
      <div style="background:var(--brd);border-radius:4px;height:7px;overflow:hidden">
        <div id="rsch-bar" style="width:0%;height:100%;background:var(--accent);transition:width .25s;border-radius:4px"></div>
      </div>
    </div>

    <div id="rsch-results" style="max-height:280px;overflow-y:auto;display:flex;flex-direction:column;gap:6px;padding-right:2px"></div>
    <div id="rsch-summary" style="display:none;background:var(--bg2);border-radius:8px;padding:12px;margin-top:12px;font-size:13px;line-height:1.7"></div>

    <div class="mf" style="margin-top:14px">
      <button id="rsch-cancel" class="btn" onclick="cancelResearch()">Annulla</button>
      <button id="rsch-done"   class="btn btp" style="display:none" onclick="closeModal()">Chiudi</button>
    </div>
  `);

  _researchCancel = false;
  _runResearch(toAnalyze.slice(0, canAnalyze), country);
}

async function _runResearch(contacts, country) {
  _researchRunning = true;
  const total = contacts.length;
  let done = 0, errors = 0;
  const stats = { si:0, forse:0, no:0, vino:0 };

  for (const c of contacts) {
    if (_researchCancel) break;

    // Controlla quota prima di ogni contatto
    if (getRemainingCalls() <= 0) {
      _researchCancel = true;
      const lbl = document.getElementById('rsch-lbl');
      if (lbl) lbl.textContent = '📊 Quota giornaliera esaurita';
      break;
    }

    const lbl = document.getElementById('rsch-lbl');
    if (lbl) lbl.textContent = `Analizzando: ${(c.company||'').slice(0,45)}`;

    // 1. Google search via Serper
    const searchText = await _rschSearch(c.company, country);

    // 2. Visita sito web (via proxy CORS)
    const webText = c.website ? await _rschFetchWebsite(c.website) : '';

    // 3. Analisi AI via Claude
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

    // 2.5s tra contatti — i rate limit di Claude (piano a pagamento) sono ben più
    // alti di quelli del piano gratuito Groq, questo ritmo è solo per UX/leggibilità
    await new Promise(res => setTimeout(res, 2500));
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
    const quotaLeft = getRemainingCalls();
    const quotaLine = `<br><span style="color:var(--text3)">📊 Quota rimanente oggi: <strong>${quotaLeft}</strong> / ${AI_DAILY_LIMIT}</span>`;
    const quotaExhausted = quotaLeft === 0
      ? `<br><span style="color:#c62828;font-weight:700">⚠ Quota giornaliera esaurita — riprova domani</span>` : '';
    summary.innerHTML = _researchCancel
      ? `<strong>Analisi interrotta</strong> — ${done} / ${total} analizzati${quotaLine}${quotaExhausted}`
      : `<strong>Analisi completata</strong> — ${done} contatti analizzati<br>
         <span style="color:#2e7d32">✅ Raccomandati: <strong>${stats.si}</strong></span> &nbsp;·&nbsp;
         <span style="color:#e65100">🟡 Forse: <strong>${stats.forse}</strong></span> &nbsp;·&nbsp;
         <span style="color:#c62828">❌ No: <strong>${stats.no}</strong></span><br>
         🍷 Vino italiano confermato/probabile: <strong>${stats.vino}</strong>
         ${errors ? `<br><span style="color:var(--text3)">⚠ ${errors} senza risposta API</span>` : ''}
         ${quotaLine}${quotaExhausted}`;
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
