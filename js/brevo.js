/* ═══ BREVO ═══ */

const BREVO_STATUS = {
  sent:         { l:'📤 Inviata',         bg:'var(--blue-bg)',  tx:'var(--blue-tx)' },
  delivered:    { l:'✓ Consegnata',       bg:'var(--green-bg)', tx:'var(--green-tx)' },
  opened:       { l:'👁 Aperta',           bg:'var(--amber-bg)',tx:'var(--amber-tx)' },
  clicked:      { l:'🔗 Link cliccato',   bg:'var(--pink-bg)', tx:'var(--pink-tx)' },
  bounced:      { l:'⚠ Bounce',           bg:'var(--red-bg)',  tx:'var(--red-tx)' },
  spam:         { l:'🚫 Spam',            bg:'var(--red-bg)',  tx:'var(--red-tx)' },
  unsubscribed: { l:'🚫 Disiscritto',     bg:'var(--red-bg)',  tx:'var(--red-tx)' },
  blocked:      { l:'🔒 Bloccata',        bg:'var(--gray-bg)', tx:'var(--gray-tx)' },
  replied:      { l:'💬 Risposto',        bg:'var(--teal-bg)', tx:'var(--teal-tx)' },
  client:       { l:'🤝 Cliente',         bg:'var(--green-bg)',tx:'var(--green-tx)' },
  cold:         { l:'❌ Non interessato', bg:'var(--gray-bg)', tx:'var(--gray-tx)' },
  blacklisted:  { l:'🚫 Blacklist',       bg:'var(--red-bg)',  tx:'var(--red-tx)' },
};

const STEP_ICON = {
  sent:'📤', delivered:'✓', opened:'👁', clicked:'🔗',
  bounced:'⚠', spam:'🚫', unsubscribed:'🚫', blocked:'🔒',
  replied:'💬', client:'🤝', cold:'❌', blacklisted:'🚫',
};

function getBrevoStatus(ev){
  if(!ev) return 'sent';
  if(ev.manualStatus) return ev.manualStatus;
  if(ev.spam)         return 'spam';
  if(ev.bounced)      return 'bounced';
  if(ev.blocked)      return 'blocked';
  if(ev.unsubscribed) return 'unsubscribed';
  if(ev.clicked)      return 'clicked';
  if(ev.opened)       return 'opened';
  if(ev.delivered)    return 'delivered';
  return 'sent';
}

function breveStatusBadge(ev){
  const s = BREVO_STATUS[getBrevoStatus(ev)] || BREVO_STATUS.sent;
  return `<span class="badge" style="background:${s.bg};color:${s.tx};font-size:11px">${s.l}</span>`;
}

function breveEventsBadge(c){
  const evs = c.brevoEvents||[];
  if(!evs.length) return '';
  const last = evs[evs.length-1];
  const icons = [];
  if(last.delivered) icons.push('<span title="Consegnata" style="color:#27ae60">✓</span>');
  if(last.opened)    icons.push('<span title="Aperta" style="color:#2980b9">👁</span>');
  if(last.clicked)   icons.push('<span title="Link cliccato" style="color:#8e44ad">🔗</span>');
  if(last.bounced)   icons.push('<span title="Bounce" style="color:#e74c3c">⚠</span>');
  if(last.spam)      icons.push('<span title="Spam" style="color:#e74c3c">🚫</span>');
  return icons.length ? `<span style="font-size:14px;margin-left:6px">${icons.join('')}</span>` : '';
}

function fmtDate(ts){
  if(!ts) return '—';
  return new Date(ts).toLocaleDateString('it-IT',{day:'numeric',month:'short'});
}

// Scadenzario: FU#2=giorno 7, FU#3=giorno 21, FU finale=giorno 35 (da step1)
// Le wave clienti (send_clienti_wave.py/wave2.py) seguono una cadenza diversa
// e gestita altrove (wave2 a 120gg da wave1, via GitHub Action) — qui mostriamo
// il countdown coerente con quella cadenza invece del generico giorno7/21/35,
// che per le wave non corrisponde a nessun invio reale.
function fuIndicator(evs, c){
  if(!evs||!evs.length) return '';
  const step1 = evs.find(e=>(e.sequenceStep||1)===1) || evs[0];
  if(!step1) return '';
  const lastEv = evs[evs.length-1];
  const lastSt = getBrevoStatus(lastEv);
  if(['replied','client','cold','blacklisted','bounced','spam','unsubscribed','blocked'].includes(lastSt)) return '';

  if(isClienti() && c?.waveStatus){
    if(c.waveStatus==='wave2_sent')
      return `<span style="font-size:11px;color:var(--text3);padding:2px 6px">Wave completa</span>`;
    const days = Math.floor((Date.now()-(step1.sentAt||0))/86400000);
    const rem = 120 - days;
    let bg, tx, txt;
    if(rem>2){        bg='var(--bg2)';     tx='var(--text2)';   txt=`Wave 2 tra ${rem} gg`; }
    else if(rem>=0){  bg='var(--amber-bg)';tx='var(--amber-tx)'; txt=rem===0?'Wave 2 oggi!':'Wave 2 domani!'; }
    else{             bg='var(--red-bg)';  tx='var(--red-tx)';   txt=`Wave 2 in ritardo di ${Math.abs(rem)} gg`; }
    return `<span style="font-size:11px;padding:2px 8px;border-radius:10px;background:${bg};color:${tx};white-space:nowrap;font-weight:600">${txt}</span>`;
  }

  const days = Math.floor((Date.now()-(step1.sentAt||0))/86400000);
  const nSteps = evs.length;
  let label, dueDay;
  if(nSteps<2){      label='FU #2';     dueDay=7;  }
  else if(nSteps<3){ label='FU #3';     dueDay=21; }
  else if(nSteps<4){ label='FU finale'; dueDay=35; }
  else return `<span style="font-size:11px;color:var(--text3);padding:2px 6px">Seq. completa</span>`;
  const rem = dueDay - days;
  let bg, tx, txt;
  if(rem>2){        bg='var(--bg2)';     tx='var(--text2)';   txt=`${label} tra ${rem} gg`; }
  else if(rem>=0){  bg='var(--amber-bg)';tx='var(--amber-tx)'; txt=rem===0?`${label} oggi!`:`${label} domani!`; }
  else{             bg='var(--red-bg)';  tx='var(--red-tx)';   txt=`${label} −${Math.abs(rem)} gg`; }
  return `<span style="font-size:11px;padding:2px 8px;border-radius:10px;background:${bg};color:${tx};white-space:nowrap;font-weight:600">${txt}</span>`;
}

function setManualStatus(contactId, sk, status){
  const adb = isClienti()?dbC:db;
  const c = adb.contacts.find(x=>x.id===contactId);
  if(!c) return;
  const messageId = sk.split('|')[1];
  const ev = (c.brevoEvents||[]).find(e=>(e.messageId||'')===messageId);
  if(!ev) return;
  ev.manualStatus = status||null;
  if(status==='replied')          c.status='replied';
  else if(status==='client')      c.status='client';
  else if(status==='cold')        c.status='cold';
  else if(status==='blacklisted') c.status='blacklisted';
  c.log = c.log||[];
  if(status){
    const s = BREVO_STATUS[status]||{l:status};
    c.log.push({ts:Date.now(), msg:`${s.l}: aggiornato manualmente`});
    toast(`${s.l} ✓`);
  } else {
    c.log.push({ts:Date.now(), msg:'Stato manuale rimosso'});
    toast('Stato rimosso ✓');
  }
  saveDB();
  renderRegistro();
}

/* ── AUTO FOLLOW-UP ── */

async function processAutoFollowUps(){
  const adb = isClienti()?dbC:db;
  const tpls = adb.templates;
  const findTpl = (...ids) => ids.map(id=>tpls.find(t=>t.id===id)).find(Boolean);

  const toSend = [];

  adb.contacts.forEach(c=>{
    if(['replied','client','cold','blacklisted'].includes(c.status)) return;
    const evs = [...(c.brevoEvents||[])].sort((a,b)=>(a.sentAt||0)-(b.sentAt||0));
    if(!evs.length) return;
    // Salta se l'ultima email ha uno stato terminale manuale
    const lastEv = evs[evs.length-1];
    if(['replied','client','cold','blacklisted'].includes(lastEv.manualStatus)) return;

    const step1 = evs.find(e=>(e.sequenceStep||1)===1)||evs[0];
    const daysSince1 = Math.floor((Date.now()-(step1.sentAt||0))/86400000);
    const nSteps = evs.length;

    if(nSteps===1 && daysSince1>=7){
      // Invia FU giorno 7
      const tpl = findTpl(step1.opened?'t2a':'t2b','t2b','t2a');
      if(tpl) toSend.push({c, tpl, nextStep:2, label:'FU giorno 7'});
    } else if(nSteps===2 && daysSince1>=21){
      // Invia FU giorno 21
      const step2 = evs.find(e=>(e.sequenceStep||0)===2)||evs[1];
      const tpl = findTpl(step2?.opened?'t3a':'t3b');
      if(tpl) toSend.push({c, tpl, nextStep:3, label:'FU giorno 21'});
    } else if(nSteps===3 && daysSince1>=35){
      // Invia FU giorno 35
      const step3 = evs.find(e=>(e.sequenceStep||0)===3)||evs[2];
      const tpl = findTpl(step3?.opened?'t4a':'t4b');
      if(tpl) toSend.push({c, tpl, nextStep:4, label:'FU giorno 35'});
    }
  });

  if(!toSend.length) return 0;

  let sent=0;
  for(const {c, tpl, nextStep, label} of toSend){
    const {primary} = (c.contacts?.length)?selectBestContact(c.contacts):{primary:null};
    const toEmail = primary?.email||c.contactEmail||c.email;
    const toName  = primary?.name ||c.contactName ||c.name||'';
    if(!toEmail) continue;
    const subj = fillTplForContact(tpl.subject, c);
    const body = fillTplForContact(tpl.body, c);
    const brand = (c.brevoEvents?.[0]?.brand)||'sienawine';
    const result = await sendViaBrevo(c.id, toEmail, toName, subj, body, brand);
    if(result?.ok){
      c.log = c.log||[];
      c.log.push({ts:Date.now(), msg:`⚡ Auto FU: ${label} — "${tpl.name}"`});
      sent++;
    }
    await new Promise(r=>setTimeout(r,600));
  }

  if(sent>0){ saveDB(); refreshAll(); }
  return sent;
}

async function runAutoFollowUp(){
  if(!brv.apiKey){ toast('Configura prima Brevo nelle impostazioni'); openSettings(); return; }
  toast('⏳ Analisi follow-up automatici...');
  const n = await processAutoFollowUps();
  toast(n>0 ? `⚡ ${n} follow-up automatici inviati` : '✓ Nessun follow-up da inviare');
}

/* ── SYNC BREVO ── */

// Le stringhe esatte del campo "event" di Brevo non sono consistenti tra le
// pagine della loro documentazione (es. "click" vs "clicks", "hardBounce" vs
// "hardBounces") — invece di un match esatto (che ha già sbagliato: i bounce
// non venivano mai rilevati), classifichiamo per sottostringa case-insensitive.
function classifyBrevoEventType(type){
  const e=(type||'').toLowerCase();
  if(e.includes('bounce'))                       return 'bounced';
  if(e.includes('click'))                         return 'clicked';
  if(e.includes('unsub'))                         return 'unsubscribed';
  if(e.includes('spam'))                          return 'spam';
  if(e==='blocked'||e==='invalid')                return 'blocked';
  if(e.includes('open'))                          return 'opened';
  if(e==='delivered'||e==='request'||e==='requests'||e==='sent') return 'delivered';
  return null;
}

const _BREVO_EVENT_LOG_MSG={
  opened:      ev=>`👁 Aperta: ${ev.subject||''}`,
  clicked:     ev=>`🔗 Click: ${ev.subject||''}`,
  bounced:     ev=>`⚠ Bounce: ${ev.subject||''}`,
  spam:        ev=>`🚫 Spam: ${ev.subject||''}`,
  unsubscribed:ev=>`🚫 Disiscritto: ${ev.subject||''}`,
  blocked:     ev=>`🔒 Bloccata: ${ev.subject||''}`,
};

// Applica gli eventi Brevo grezzi a un singolo brevoEvents[i]. Ritorna true se qualcosa è cambiato.
function _applyBrevoEvents(contact, ev, events){
  contact.log = contact.log||[];
  let changed=false;
  events.forEach(e=>{
    const kind=classifyBrevoEventType(e.event);
    if(!kind||ev[kind]) return;
    ev[kind]=true; ev[kind+'At']=e.date; changed=true;
    if(_BREVO_EVENT_LOG_MSG[kind]) contact.log.push({ts:new Date(e.date).getTime()||Date.now(),msg:_BREVO_EVENT_LOG_MSG[kind](ev)});
  });
  // Fuori dal forEach: vale anche per eventi spam/unsub/blocked già marcati in
  // run precedenti, non solo quelli appena rilevati ora.
  if((ev.spam||ev.unsubscribed||ev.blocked)&&!contact.blacklisted){
    contact.blacklisted=true; changed=true;
    contact.log.push({ts:Date.now(),msg:'🚫 Contatto inserito in blacklist (spam/disiscrizione/bloccata)'});
  }
  return changed;
}

// Versione silenziosa: gira in background all'avvio, toast solo se trova eventi nuovi
async function syncBrevoEventsQuiet(){
  if(!brv.apiKey) return;
  const cutoff = Date.now() - 14*86400000; // solo ultime 2 settimane
  const toSync = [];
  [...db.contacts, ...dbC.contacts].forEach(c=>{
    (c.brevoEvents||[]).forEach((ev,i)=>{
      if(ev.messageId && (ev.sentAt||0)>cutoff
        && !ev.bounced && !ev.spam && !ev.unsubscribed && !ev.blocked)
        toSync.push({contact:c, evIdx:i, messageId:ev.messageId});
    });
  });
  if(!toSync.length) return;
  let updated=0;
  for(const {contact,evIdx,messageId} of toSync){
    try{
      const r=await fetch(
        `https://api.brevo.com/v3/smtp/statistics/events?messageId=${encodeURIComponent(messageId)}&limit=50`,
        {headers:{'api-key':brv.apiKey,'Accept':'application/json'}}
      );
      if(!r.ok) continue;
      const data=await r.json();
      if(_applyBrevoEvents(contact, contact.brevoEvents[evIdx], data.events||[])) updated++;
    }catch(e){ console.warn('Brevo quiet sync:',e); }
    await new Promise(r=>setTimeout(r,150));
  }
  if(updated>0){ saveDB(); refreshAll(); toast(`⚠ Sync Brevo: ${updated} nuovi eventi rilevati`); }
}

async function syncBrevoEvents(){
  if(!brv.apiKey){ toast('Configura prima Brevo nelle impostazioni'); return; }
  const adb = isClienti()?dbC:db;

  const toSync = [];
  adb.contacts.forEach(c=>{
    (c.brevoEvents||[]).forEach((ev,i)=>{
      if(ev.messageId) toSync.push({contact:c, evIdx:i, messageId:ev.messageId});
    });
  });

  if(!toSync.length){ toast('Nessuna email tracciata — invia prima qualche email'); return; }

  toast(`🔄 Sincronizzazione ${toSync.length} email...`);
  let updated=0;

  for(const {contact,evIdx,messageId} of toSync){
    try{
      const r = await fetch(
        `https://api.brevo.com/v3/smtp/statistics/events?messageId=${encodeURIComponent(messageId)}&limit=50`,
        {headers:{'api-key':brv.apiKey,'Accept':'application/json'}}
      );
      if(!r.ok) continue;
      const data = await r.json();
      if(_applyBrevoEvents(contact, contact.brevoEvents[evIdx], data.events||[])) updated++;
    }catch(e){ console.warn('Brevo sync error:',e); }
    await new Promise(r=>setTimeout(r,120));
  }

  saveDB();
  refreshAll();
  toast(updated>0
    ?`✓ Sync Brevo: ${updated} email aggiornate su ${toSync.length}`
    :`📊 Sync OK — ${toSync.length} verificate, nessun nuovo evento`
  );
}
