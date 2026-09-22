/* ═══ RISPOSTE IMPORTATORI — revisione delle email in arrivo ═══ */
// Lo script server-side (scripts/check_importatori_replies.py, gira ogni giorno via GitHub
// Actions) legge la casella luca@sienawine.it, abbina le risposte ai contatti importatori
// contattati e le classifica (bounce/non interessato/risposta/cliente/fuori sede). Qui le
// mostriamo una alla volta in un popup: Luca conferma o corregge con lo stesso stato manuale
// già usato altrove nel CRM (setManualStatus, in js/brevo.js) — non aggiungo una tassonomia
// nuova. Ogni conferma/correzione alimenta il pattern-learning del prossimo run server-side
// (vedi rebuild_pattern in check_importatori_replies.py).

let _irData = null;  // {lastUid, pending, risolte, pattern} — cache in memoria di data/inbox-risposte.json
let _irIndex = 0;

const IR_STATUS_LABEL = { replied:'💬 Risposto', client:'🤝 Cliente', cold:'❌ Non interessato', blacklisted:'🚫 Blacklist' };
const IR_CONF_LABEL   = { pattern:'🔁 stesso mittente già rivisto', regola:'⚙ bounce tecnico', ai:'🤖 lettura AI' };

async function refreshRisposteBanner(){
  const el=document.getElementById('risposte-review-banner');
  if(!el) return;
  if(isClienti()){ el.innerHTML=''; return; }
  _irData = await fetchInboxRisposte();
  renderRisposteBanner();
}

function renderRisposteBanner(){
  const el=document.getElementById('risposte-review-banner');
  if(!el) return;
  if(isClienti() || !_irData){ el.innerHTML=''; return; }
  const n=(_irData.pending||[]).length;
  if(!n){ el.innerHTML=''; return; }
  el.innerHTML=`<div class="card" style="padding:10px 16px;margin-bottom:10px;background:var(--amber-bg);cursor:pointer" onclick="apriRevisioneRisposte()">
    <div style="display:flex;align-items:center;justify-content:space-between;color:var(--amber-tx);font-size:13px;font-weight:600">
      <span>📬 ${n} risposta${n===1?'':'e'} da rivedere</span>
      <span>Rivedi →</span>
    </div>
  </div>`;
}

function apriRevisioneRisposte(){
  if(!_irData || !(_irData.pending||[]).length){ toast('Nessuna risposta da rivedere'); return; }
  _irIndex=0;
  mostraItemRevisione();
}

function mostraItemRevisione(){
  const pending=(_irData&&_irData.pending)||[];
  if(_irIndex>=pending.length){
    closeModal();
    renderRisposteBanner();
    toast('✅ Revisione completata');
    return;
  }
  const it=pending[_irIndex];
  const suggestedLabel = it.suggestedStatus ? (IR_STATUS_LABEL[it.suggestedStatus]||it.suggestedStatus) : 'Nessuno — solo informativo';
  const confLabel = IR_CONF_LABEL[it.confidence]||'';
  const rientro = it.dataRientro ? `<div style="margin-top:4px;font-size:12px;color:var(--text2)">📅 Rientro indicato: ${esc(it.dataRientro)}</div>` : '';

  showModal(`
    <div class="mt">📬 Revisione risposte — ${_irIndex+1} di ${pending.length}</div>
    <div class="card" style="padding:12px 14px;margin-bottom:12px;background:var(--bg2)">
      <div style="font-weight:700">${esc(it.company||'')}</div>
      <div style="font-size:12px;color:var(--text2);margin-top:2px">${esc(it.from||'')} · ${fmtDate(new Date(it.date).getTime())}</div>
      <div style="font-weight:600;margin-top:10px">${esc(it.subject||'(senza oggetto)')}</div>
      <div style="font-size:13px;color:var(--text2);margin-top:6px;white-space:pre-wrap;max-height:180px;overflow:auto">${esc(it.snippet||'')}</div>
    </div>
    <div style="margin-bottom:12px;font-size:13px">
      <strong>Proposta:</strong> ${esc(suggestedLabel)}
      ${confLabel?`<span style="font-size:11px;color:var(--text3);margin-left:6px">${confLabel}</span>`:''}
      <div style="color:var(--text2);margin-top:2px">${esc(it.reason||'')}</div>
      ${rientro}
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px">
      <button class="btn btp bts" onclick="risolviRevisione('replied')">💬 Risposto</button>
      <button class="btn btp bts" onclick="risolviRevisione('client')">🤝 Cliente</button>
      <button class="btn btp bts" onclick="risolviRevisione('cold')">❌ Non interessato</button>
      <button class="btn btd bts" onclick="risolviRevisione('blacklisted')">🚫 Blacklist</button>
    </div>
    <div style="display:flex;gap:8px">
      <button class="btn btg bts" onclick="risolviRevisione(null)">✔ Ok, nessun cambio di stato</button>
      <button class="btn btg bts" onclick="saltaRevisione()">⏭ Salta per ora</button>
    </div>
  `);
}

// {c, sk} dell'ultima email inviata a questo contatto — stesso identificatore ("contattoId|messageId")
// che usa già il menu a tendina manuale in js/contacts.js per chiamare setManualStatus().
function _lastSkFor(contactId){
  const c=db.contacts.find(x=>x.id===contactId);
  if(!c) return null;
  const evs=[...(c.brevoEvents||[])].sort((a,b)=>(a.sentAt||0)-(b.sentAt||0));
  const lastEv=evs[evs.length-1];
  if(!lastEv) return null;
  return {c, sk:c.id+'|'+(lastEv.messageId||evs.indexOf(lastEv))};
}

async function risolviRevisione(status){
  const it=(_irData.pending||[])[_irIndex];
  if(!it) return;

  if(status){
    const found=_lastSkFor(it.contactId);
    if(found) setManualStatus(found.c.id, found.sk, status);  // già chiama saveDB() e mostra il toast
    else toast('⚠ Contatto non trovato nel CRM — stato non aggiornato');
  } else {
    // Nessun cambio di stato (es. fuori sede): lascia comunque una traccia nel log del contatto.
    const c=db.contacts.find(x=>x.id===it.contactId);
    if(c){
      c.log=c.log||[];
      c.log.push({ts:Date.now(), msg:`ℹ️ Email ricevuta (${it.reason||'nessuna azione'}) — nessun cambio di stato`});
      saveDB();
    }
  }

  // Sposta da "pending" a "risolte": alimenta il pattern-learning del prossimo run server-side
  // (mittenti già rivisti con esito coerente vengono riconosciuti in automatico la volta dopo).
  _irData.pending.splice(_irIndex,1);
  _irData.risolte=_irData.risolte||[];
  _irData.risolte.push({contactId:it.contactId, from:it.from, subject:it.subject, suggestedStatus:it.suggestedStatus, finalStatus:status, at:Date.now()});
  try{
    await pushInboxRisposte(_irData, `Revisione risposta — ${it.company||it.from} → ${status?(IR_STATUS_LABEL[status]||status):'nessun cambio'}`);
  }catch(e){
    console.warn('pushInboxRisposte:',e);
    toast('⚠ Coda risposte non salvata (lo stato del contatto è comunque aggiornato)');
  }

  // _irIndex non avanza: l'elemento corrente è stato tolto dall'array, quindi l'indice attuale
  // punta già al prossimo (o è fuori range se era l'ultimo — gestito da mostraItemRevisione).
  mostraItemRevisione();
}

function saltaRevisione(){
  _irIndex++;
  mostraItemRevisione();
}
