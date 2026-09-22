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

const IR_STATUS_LABEL = { replied:'💬 Risposto', client:'🤝 Cliente', cold:'❌ Non interessato', blacklisted:'🚫 Blacklist', snoozed:'⏸ Standby (già visto altre volte)' };
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
  // Riprende da dove Luca aveva lasciato (es. dopo aver aperto la scheda di un contatto per
  // cercare un'altra email — vedi vediSchedaContatto()), non sempre da capo.
  if(_irIndex>=_irData.pending.length) _irIndex=0;
  mostraItemRevisione();
}

// Apre la scheda completa del contatto (stessa vista di "Contatti", con tutti i nomi/titoli/
// telefoni/LinkedIn anche senza email) — per quando il campo libero della "casella sbagliata"
// non basta perché Luca non sa a memoria un indirizzo alternativo e vuole cercarlo lui nella
// scheda. Chiude il popup di revisione (stesso overlay, showModal() ne tiene solo uno alla
// volta); riapri con "Rivedi" nel banner per tornare esattamente al punto dov'eri.
function vediSchedaContatto(contactId){
  if(!contactId) return;
  closeModal();
  openDetail(contactId);
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

  const rdMap = {true:{t:'✅ Sì',c:'var(--green-tx)'}, false:{t:'❌ No',c:'var(--red-tx)'}};
  const rd = rdMap[it.rispostaDiretta] || {t:'❓ Incerta', c:'var(--text2)'};

  const nonCollegatoBox = it.nonCollegato ? `
    <div style="margin-bottom:10px;padding:8px 12px;border-radius:var(--r);background:var(--amber-bg);color:var(--amber-tx);font-size:12px;font-weight:600">
      ⚠ Non collegata a nessun contatto del CRM — solo consultabile, nessuna azione sullo stato possibile.
    </div>` : '';

  // Casella sbagliata/non monitorata: SEMPRE disponibile quando c'è un contatto collegato — non
  // solo se il CRM ha già un'altra email in archivio. Luca spesso sa (dalla scheda del contatto,
  // dal sito, da fuori) un indirizzo che il sistema non può conoscere da solo; se il CRM ha altre
  // caselle già note le propone in più, come scorciatoia, ma non è una condizione per mostrare il
  // pulsante. Precompilato con l'indirizzo alternativo se la risposta automatica ne scriveva uno
  // esplicito (email_alternativa, da check_importatori_replies.py).
  const contattoDb=it.contactId?db.contacts.find(x=>x.id===it.contactId):null;
  const badEmail=(contattoDb&&_ultimoToEmail(contattoDb))||it.from;
  const alternative=contattoDb?_altreCaselle(contattoDb, badEmail):[];
  const casellaBox = contattoDb ? `
    <div style="margin-bottom:8px;padding:10px 12px;border-radius:var(--r);border:0.5px dashed var(--brd2)">
      <div style="font-size:12px;color:var(--text2);margin-bottom:6px">📭 Casella "${esc(badEmail)}" sbagliata o non monitorata? Rimetti da contattare con un'altra:</div>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        ${alternative.length?`<select onchange="document.getElementById('ir-alt-email').value=this.value" style="padding:6px 8px;border-radius:var(--r);border:0.5px solid var(--brd2);background:var(--bg);color:var(--text);font-size:13px">
          <option value="">— caselle già note —</option>
          ${alternative.map(e=>`<option value="${esc(e)}">${esc(e)}</option>`).join('')}
        </select>`:''}
        <input type="email" id="ir-alt-email" placeholder="oppure scrivi un'email" value="${esc(it.emailAlternativa||'')}" style="padding:6px 8px;border-radius:var(--r);border:0.5px solid var(--brd2);background:var(--bg);color:var(--text);font-size:13px;flex:1;min-width:200px">
        <button class="btn btp bts" onclick="provaAltraCasella('${esc(badEmail)}')">↻ Rimetti da contattare con questa</button>
      </div>
      <div style="margin-top:6px">
        <button class="btn btg bts" onclick="vediSchedaContatto('${esc(it.contactId)}')">🔍 Vedi scheda contatto — cerca altri nomi/email</button>
      </div>
    </div>` : '';
  // Fuori sede (o comunque "nessuno stato proposto", incluso un pattern imparato da uno standby
  // precedente): offri lo standby, non solo il dismiss secco — altrimenti il conteggio dei
  // follow-up (7/21/35gg) continua come se non fosse successo niente.
  const standbyBox = (!it.suggestedStatus || it.suggestedStatus==='snoozed') ? `
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap">
      <input type="date" id="ir-standby-date" value="${esc(it.dataRientro||'')}" style="padding:6px 8px;border-radius:var(--r);border:0.5px solid var(--brd2);background:var(--bg);color:var(--text);font-size:13px">
      <button class="btn btp bts" onclick="risolviStandby()">⏸ Standby fino a qui</button>
    </div>` : '';

  const azioniStato = it.nonCollegato ? '' : `
    <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px">
      <button class="btn btp bts" onclick="risolviRevisione('replied')">💬 Risposto</button>
      <button class="btn btp bts" onclick="risolviRevisione('client')">🤝 Cliente</button>
      <button class="btn btp bts" onclick="risolviRevisione('cold')">❌ Non interessato</button>
      <button class="btn btd bts" onclick="risolviRevisione('blacklisted')">🚫 Blacklist</button>
    </div>
    ${standbyBox}
    ${casellaBox}`;

  showModal(`
    <div class="mt">📬 Revisione risposte — ${_irIndex+1} di ${pending.length}</div>
    ${nonCollegatoBox}
    <div class="card" style="padding:12px 14px;margin-bottom:12px;background:var(--bg2)">
      <div style="font-weight:700">${esc(it.company||'')}</div>
      <div style="font-size:12px;color:var(--text2);margin-top:2px">👤 ${esc(it.mittenteNome||it.from||'')}${it.mittenteNome?` — ${esc(it.from||'')}`:''} · ${fmtDate(new Date(it.date).getTime())}</div>
      <div style="font-weight:600;margin-top:10px">${esc(it.subject||'(senza oggetto)')}</div>
      <div style="font-size:13px;margin-top:8px;padding:8px 10px;border-radius:var(--r);background:var(--bg);color:var(--text)">📝 ${esc(it.riassunto||'(nessun riassunto disponibile)')}</div>
      <details style="margin-top:6px"><summary style="font-size:11px;color:var(--text3);cursor:pointer">Testo originale</summary>
        <div style="font-size:12px;color:var(--text2);margin-top:4px;white-space:pre-wrap;max-height:150px;overflow:auto">${esc(it.snippet||'')}</div>
      </details>
    </div>
    <div style="margin-bottom:12px;font-size:13px">
      <div><strong>Risposta diretta a una nostra email:</strong> <span style="color:${rd.c};font-weight:600">${rd.t}</span></div>
      <div style="margin-top:4px"><strong>Proposta:</strong> ${esc(suggestedLabel)}
        ${confLabel?`<span style="font-size:11px;color:var(--text3);margin-left:6px">${confLabel}</span>`:''}
      </div>
      <div style="color:var(--text2);margin-top:2px">${esc(it.reason||'')}</div>
      ${rientro}
    </div>
    ${azioniStato}
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

// L'indirizzo a cui abbiamo scritto per davvero l'ultima volta (non necessariamente c.contactEmail,
// che potrebbe essere stato cambiato dopo l'invio) — quello da bloccare se risulta sbagliato.
function _ultimoToEmail(c){
  const evs=[...(c.brevoEvents||[])].sort((a,b)=>(a.sentAt||0)-(b.sentAt||0));
  const lastEv=evs[evs.length-1];
  return (lastEv&&lastEv.toEmail)||'';
}

// Altri indirizzi già noti per l'azienda (c.contacts[], più c.email/c.contactEmail), esclusi quello
// appena usato e quelli già bloccati in passato — per il pulsante "casella sbagliata, prova un'altra".
function _altreCaselle(c, escludi){
  const bloccate=new Set((c.emailBloccate||[]).map(e=>(e||'').trim().toLowerCase()));
  const esc=(escludi||'').trim().toLowerCase();
  const cand=new Set();
  (c.contacts||[]).forEach(p=>{ const e=(p.email||'').trim().toLowerCase(); if(e) cand.add(e); });
  if(c.email) cand.add(c.email.trim().toLowerCase());
  if(c.contactEmail) cand.add(c.contactEmail.trim().toLowerCase());
  cand.delete(esc);
  bloccate.forEach(e=>cand.delete(e));
  return [...cand];
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

// Casella sbagliata/non monitorata: rimette il contatto "da contattare" con un'altra email già
// nota per l'azienda, blocca quella vecchia (non verrà più selezionata per nessun invio futuro —
// vedi select_contact() in scripts/send_importatori_followup.py, che rispetta emailBloccate) e
// chiude la revisione di questa email.
async function provaAltraCasella(badEmail){
  const it=(_irData.pending||[])[_irIndex];
  if(!it) return;
  const nuovaEmail=document.getElementById('ir-alt-email')?.value;
  if(!nuovaEmail){ toast('Nessuna casella alternativa selezionata'); return; }

  const c=db.contacts.find(x=>x.id===it.contactId);
  if(!c){ toast('⚠ Contatto non trovato nel CRM'); return; }

  c.emailBloccate=c.emailBloccate||[];
  const badLower=(badEmail||'').trim().toLowerCase();
  if(badLower && !c.emailBloccate.includes(badLower)) c.emailBloccate.push(badLower);
  c.contactEmail=nuovaEmail;
  c.status='new';
  c.log=c.log||[];
  c.log.push({ts:Date.now(), msg:`📭 Casella "${badEmail}" sbagliata/non monitorata — sostituita con "${nuovaEmail}", rimesso "da contattare"`});
  saveDB();
  toast(`📭 Rimesso "da contattare" con ${nuovaEmail} ✓`);

  _irData.pending.splice(_irIndex,1);
  _irData.risolte=_irData.risolte||[];
  _irData.risolte.push({contactId:it.contactId, from:it.from, subject:it.subject, suggestedStatus:it.suggestedStatus, finalStatus:'altra_casella', at:Date.now()});
  try{
    await pushInboxRisposte(_irData, `Revisione risposta — ${it.company||it.from} → altra casella (${nuovaEmail})`);
  }catch(e){
    console.warn('pushInboxRisposte:',e);
    toast('⚠ Coda risposte non salvata (il contatto è comunque aggiornato)');
  }

  mostraItemRevisione();
}

// Fuori sede: congela il conteggio dei follow-up automatici (7/21/35gg, vedi
// should_send_followup() in scripts/send_importatori_followup.py e fuIndicator() in js/brevo.js)
// finché non passa la data di rientro, invece di lasciarlo correre come se niente fosse successo.
async function risolviStandby(){
  const it=(_irData.pending||[])[_irIndex];
  if(!it) return;
  const dateStr=document.getElementById('ir-standby-date')?.value;
  if(!dateStr){ toast('Scegli una data prima di mettere in standby'); return; }
  const ts=new Date(dateStr+'T12:00:00').getTime();
  if(!ts||isNaN(ts)){ toast('Data non valida'); return; }

  const c=db.contacts.find(x=>x.id===it.contactId);
  if(c){
    c.snoozeUntil=ts;
    c.log=c.log||[];
    c.log.push({ts:Date.now(), msg:`⏸ Standby fino al ${new Date(ts).toLocaleDateString('it-IT')} (${it.reason||'fuori sede'})`});
    saveDB();
    toast(`⏸ Standby fino al ${new Date(ts).toLocaleDateString('it-IT')} ✓`);
  } else {
    toast('⚠ Contatto non trovato nel CRM — standby non impostato');
  }

  _irData.pending.splice(_irIndex,1);
  _irData.risolte=_irData.risolte||[];
  _irData.risolte.push({contactId:it.contactId, from:it.from, subject:it.subject, suggestedStatus:it.suggestedStatus, finalStatus:'snoozed', at:Date.now()});
  try{
    await pushInboxRisposte(_irData, `Revisione risposta — ${it.company||it.from} → standby fino al ${dateStr}`);
  }catch(e){
    console.warn('pushInboxRisposte:',e);
    toast('⚠ Coda risposte non salvata (lo standby è comunque impostato sul contatto)');
  }

  mostraItemRevisione();
}
