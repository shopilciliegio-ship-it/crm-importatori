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
  // Riprende da dove Luca aveva lasciato l'ultima volta, non sempre da capo.
  if(_irIndex>=_irData.pending.length) _irIndex=0;
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
  // Persone note in azienda, ANCHE senza email (solo nome/ruolo/LinkedIn) — mostrate qui inline,
  // non in una scheda separata: aprire un secondo popup chiudeva questo (showModal ne tiene uno
  // solo alla volta) e si perdeva il filo della revisione. Serve anche a spiegare perché la
  // tendina sopra è vuota: se qui non c'è nessuna email, non è un bug, è che BWI non l'ha trovata.
  const tuttePersone=contattoDb?(contattoDb.contacts||[]):[];
  const personeBox = tuttePersone.length ? `
    <details style="margin-top:8px">
      <summary style="font-size:12px;color:var(--text3);cursor:pointer">👥 Persone note in azienda (${tuttePersone.length}) — anche senza email</summary>
      <div style="margin-top:6px">
        ${tuttePersone.map(p=>`
          <div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:0.5px solid var(--brd);font-size:12px">
            <div style="flex:1;min-width:0">
              <div style="font-weight:600">${esc(p.name||'—')}</div>
              <div style="color:var(--text2)">${esc(p.title||'')}${p.email?` · ${esc(p.email)}`:' · nessuna email nota'}</div>
            </div>
            ${p.linkedin?`<a href="${esc(p.linkedin)}" target="_blank" style="font-size:11px;padding:3px 8px;border-radius:12px;background:var(--blue-bg);color:var(--blue-tx);font-weight:600;text-decoration:none;flex-shrink:0">LinkedIn ↗</a>`:''}
          </div>`).join('')}
      </div>
    </details>` : '';
  // Sblocco BWI di TUTTE le persone di questa scheda (tipico: casella generica non monitorata,
  // in scheda ci sono persone senza email). Vedi unlock_single_company() in scripts/unlock_leads_bulk.py.
  const senzaEmail=tuttePersone.filter(p=>!(p.email||'').trim()&&!(p.emailSospetta||'').trim()).length;
  const sbloccaBox = (contattoDb && contattoDb.bwiCompId) ? `
    <div id="ir-sblocca-box" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:8px;font-size:12px;color:var(--text2)">
      <button class="btn btp bts" id="ir-sblocca-btn" onclick="sbloccaEmailScheda()">🔓 Sblocca le email di questa scheda (BWI)</button>
      <span>${senzaEmail?`${senzaEmail} person${senzaEmail===1?'a':'e'} senza email in scheda · `:''}1 credito per ogni email bloccata su BWI (max ${IR_UNLOCK_MAX})</span>
    </div>` : '';
  const casellaBox = contattoDb ? `
    <div style="margin-bottom:8px;padding:10px 12px;border-radius:var(--r);border:0.5px dashed var(--brd2)">
      <div style="font-size:12px;color:var(--text2);margin-bottom:6px">📭 Casella "${esc(badEmail)}" sbagliata o non monitorata? Rimetti da contattare con un'altra:</div>
      ${alternative.length?`
      <select onchange="const o=this.selectedOptions[0];document.getElementById('ir-alt-email').value=o?o.dataset.email||'':'';document.getElementById('ir-alt-name').value=o?o.dataset.name||'':'';" style="width:100%;padding:6px 8px;border-radius:var(--r);border:0.5px solid var(--brd2);background:var(--bg);color:var(--text);font-size:13px;margin-bottom:6px">
        <option value="">— scegli tra i contatti già noti in azienda —</option>
        ${alternative.map(a=>`<option data-email="${esc(a.email)}" data-name="${esc(a.name)}">${esc(a.name||'(nome sconosciuto)')}${a.title?` — ${esc(a.title)}`:''} · ${esc(a.email)}</option>`).join('')}
      </select>`:`<div style="font-size:12px;color:var(--text3);margin-bottom:6px">Nessuna email nota in archivio per questa azienda oltre a quella appena usata — guarda "Persone note" qui sotto per cercarle su LinkedIn, o scrivi tu i dati.</div>`}
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <input type="text" id="ir-alt-name" placeholder="nome (facoltativo)" style="padding:6px 8px;border-radius:var(--r);border:0.5px solid var(--brd2);background:var(--bg);color:var(--text);font-size:13px;width:140px">
        <input type="email" id="ir-alt-email" placeholder="email" value="${esc(it.emailAlternativa||'')}" style="padding:6px 8px;border-radius:var(--r);border:0.5px solid var(--brd2);background:var(--bg);color:var(--text);font-size:13px;flex:1;min-width:180px">
        <button class="btn btp bts" onclick="provaAltraCasella('${esc(badEmail)}')">↻ Rimetti da contattare con questa</button>
      </div>
      ${sbloccaBox}
      ${personeBox}
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

// Altre PERSONE già note per l'azienda (c.contacts[], più c.contactEmail/c.email), esclusa quella
// appena usata e quelle già bloccate in passato — con nome/ruolo, non solo l'indirizzo nudo: senza
// un nome il template di invio non sa chi salutare (vedi provaAltraCasella).
function _altreCaselle(c, escludi){
  const bloccate=new Set((c.emailBloccate||[]).map(e=>(e||'').trim().toLowerCase()));
  const escLower=(escludi||'').trim().toLowerCase();
  const visti=new Set();
  const out=[];
  const add=(email, name, title)=>{
    const e=(email||'').trim().toLowerCase();
    if(!e || e===escLower || bloccate.has(e) || visti.has(e)) return;
    visti.add(e);
    out.push({email:e, name:(name||'').trim(), title:(title||'').trim()});
  };
  (c.contacts||[]).forEach(p=>add(p.email, p.name, p.title));
  add(c.contactEmail, c.contactName, c.contactTitle);
  add(c.email, '', '');
  return out;
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

// Casella sbagliata/non monitorata: rimette il contatto "da contattare" con un'altra email (+nome,
// se noto — senza un nome il template saluta genericamente l'azienda, vedi render_template() in
// scripts/send_importatori_followup.py) già nota per l'azienda o scritta a mano, blocca quella
// vecchia (non verrà più selezionata per nessun invio futuro — vedi select_contact() in
// scripts/send_importatori_followup.py, che rispetta emailBloccate) e chiude la revisione.
async function provaAltraCasella(badEmail){
  const it=(_irData.pending||[])[_irIndex];
  if(!it) return;
  const nuovaEmail=document.getElementById('ir-alt-email')?.value?.trim();
  const nuovoNome=document.getElementById('ir-alt-name')?.value?.trim()||'';
  if(!nuovaEmail){ toast('Scegli o scrivi un\'email prima di continuare'); return; }

  const c=db.contacts.find(x=>x.id===it.contactId);
  if(!c){ toast('⚠ Contatto non trovato nel CRM'); return; }

  c.emailBloccate=c.emailBloccate||[];
  const badLower=(badEmail||'').trim().toLowerCase();
  if(badLower && !c.emailBloccate.includes(badLower)) c.emailBloccate.push(badLower);
  c.contactEmail=nuovaEmail;
  c.contactName=nuovoNome;  // vuoto se non noto: meglio un saluto generico che il nome sbagliato di prima
  // La persona scelta diventa il destinatario degli invii: gli script (select_send_email,
  // select_contact, select_best_contact) mettono sempre per prima la persona con "sbloccato",
  // a prescindere dal ruolo — senza questo, dopo uno sblocco di più persone l'invio sceglierebbe
  // per ruolo e non quella scelta qui.
  const nuovaLower=nuovaEmail.toLowerCase();
  c.contacts=(c.contacts||[]).map(p=>{
    const q={...p};
    if((q.email||'').trim().toLowerCase()===nuovaLower){ q.sbloccato=true; if(!q.name&&nuovoNome) q.name=nuovoNome; }
    else delete q.sbloccato;
    return q;
  });
  if(!c.contacts.some(p=>(p.email||'').trim().toLowerCase()===nuovaLower)){
    c.contacts.push({name:nuovoNome, title:'', email:nuovaEmail, sbloccato:true});
  }
  c.status='new';
  c.log=c.log||[];
  c.log.push({ts:Date.now(), msg:`📭 Casella "${badEmail}" sbagliata/non monitorata — sostituita con "${nuovoNome?nuovoNome+' <'+nuovaEmail+'>':nuovaEmail}", rimesso "da contattare"`});
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

// ── Sblocco email BWI di una sola scheda (dal popup di revisione) ──
// Riusa job + workflow dello sblocco massivo (js/unlock.js, unlock_leads_bulk.yml) con companyId:
// lo script sblocca tutte le persone con email bloccata di quell'azienda e le aggiunge a
// contacts[] senza cambiare il destinatario. A fine giro ricarica il CRM e ridisegna questo stesso
// popup: le email nuove compaiono nella tendina "scegli tra i contatti già noti".
const IR_UNLOCK_MAX = 10;
async function sbloccaEmailScheda(){
  const it=(_irData.pending||[])[_irIndex];
  const c=it&&db.contacts.find(x=>x.id===it.contactId);
  if(!c||!c.bwiCompId){ toast('⚠ Scheda senza ID BWI: sblocco non possibile'); return; }
  const prev=await _fetchUnlockJob();
  if(prev && (prev.status==='pending'||prev.status==='running') && Date.now()-(prev.createdAt||0)<30*60*1000){
    toast("⏳ C'è già uno sblocco BWI in corso: riprova tra qualche minuto"); return;
  }
  if(!confirm(`Sbloccare le email delle persone di ${c.company} su BWI? 1 credito per ogni email bloccata, massimo ${IR_UNLOCK_MAX}. Le email già in chiaro sono gratis.`)) return;

  const btn=document.getElementById('ir-sblocca-btn');
  const box=document.getElementById('ir-sblocca-box');
  if(btn) btn.disabled=true;
  const stato=msg=>{ if(box) box.innerHTML=`<span style="font-size:12px;color:var(--text2)">${msg}</span>`; };
  stato('⏳ Avvio sblocco…');
  const job={companyId:c.id, company:c.company||'', maxCredits:IR_UNLOCK_MAX, status:'pending', createdAt:Date.now()};
  try{ await pushUnlockJob(job); }catch(e){ stato('⚠ '+esc(e.message)); if(btn) btn.disabled=false; return; }
  if(!await triggerUnlockWorkflow()){ stato('⚠ Avvio del workflow fallito'); return; }
  stato('⏳ Sblocco in corso su BWI (di solito 1-2 minuti). Puoi restare qui.');

  // Aspetta il job di QUESTA scheda (non l'ultimo run qualsiasi): controllo ogni 10 s, fino a ~8 minuti.
  let fin=null;
  for(let i=0;i<48&&!fin;i++){
    await new Promise(r=>setTimeout(r,10000));
    const j=await _fetchUnlockJob().catch(()=>null);
    if(j&&j.companyId===c.id&&j.createdAt===job.createdAt&&j.status==='done') fin=j;
  }
  if(!fin||!fin.result){ stato("⏱ Non ho ancora l'esito: riapri la revisione tra qualche minuto."); return; }
  const {unlocked, spent, stopReason}=fin.result;
  toast(`🔓 ${c.company}: ${unlocked} email nuove, ${spent} crediti spesi${stopReason?' — '+stopReason:''}`);
  await loadFromGH();
  // Ridisegna il popup solo se Luca è ancora sulla stessa risposta.
  const cur=(_irData.pending||[])[_irIndex];
  if(cur&&cur.contactId===c.id) mostraItemRevisione();
}
