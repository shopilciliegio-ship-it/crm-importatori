/* ═══ ORDINI ═══ */

/* Timeout per polling dopo trigger import */
let _importPollTimer = null;

const ORD_STATUS = {
  ricevuto:     {l:'Ricevuto',         c:'var(--blue-bg)',   t:'var(--blue-tx)'},
  preparazione: {l:'In preparazione',  c:'var(--amber-bg)',  t:'var(--amber-tx)'},
  spedito:      {l:'Spedito',          c:'var(--teal-bg)',   t:'var(--teal-tx)'},
  in_transito:  {l:'In transito',      c:'var(--blue-bg)',   t:'var(--blue-tx)'},
  dogana:       {l:'In dogana',        c:'var(--amber-bg)',  t:'var(--amber-tx)'},
  in_consegna:  {l:'In consegna',      c:'var(--teal-bg)',   t:'var(--teal-tx)'},
  consegnato:   {l:'Consegnato',       c:'var(--green-bg)',  t:'var(--green-tx)'},
  problema:     {l:'Problema',         c:'var(--red-bg)',    t:'var(--red-tx)'},
  annullato:    {l:'Annullato',        c:'var(--gray-bg)',   t:'var(--gray-tx)'},
};

function uidOrd(){ return 'ord_'+Date.now().toString(36)+Math.random().toString(36).slice(2,6); }

/* ─ Helper: costruisce oggetto ordine completo ─ */
function _mkOrder({customerName,customerEmail='',customerPhone='',amount=0,currency='EUR',
  orderDate,emailSubject='',shipmentCode='',shippingAddress='',gmailMessageId='',numberOfCartons=null,note=''}){
  const now = Date.now();
  return {
    id: uidOrd(),
    customerName,
    customerEmail,
    customerPhone,
    amount,
    currency,
    orderDate: orderDate||now,
    emailSubject,
    shipmentCode,
    shippingAddress,
    numberOfCartons,
    gmailMessageId,
    trackingNumber: '',
    carrier: 'MBE',
    shippingType: null,
    shippingDate: null,
    status: 'ricevuto',
    statusHistory: [{status:'ricevuto', date:now, note}],
    emailsSent: [],
    notes: '',
    createdAt: now,
    updatedAt: now
  };
}

/* ─ Parsing oggetto email ─ */
function parseOrderFromSubject(subject){
  // Rimuove prefissi di forward/risposta (Gmail IT usa "I:" per inoltro)
  const s = subject.trim().replace(/^(I:|Fw:|Fwd:|R:|Re:|Inoltrato:)\s+/i,'').trim();
  const m = s.match(/New\s+Order\s*[—\-–]+\s*([^—\-–]+?)(?:\s*[—\-–]+\s*([\d.,]+)\s*(EUR|USD|GBP)?)?$/i);
  if(!m||!m[1]) return null;
  const customerName = m[1].trim();
  if(!customerName) return null;
  return {
    customerName,
    amount: m[2] ? parseFloat(m[2].replace(',','.')) : 0,
    currency: (m[3]||'EUR').toUpperCase(),
    rawSubject: s
  };
}

/* ─ Import da soggetti email incollati manualmente ─ */
function importFromSubjects(){
  const raw = document.getElementById('ord-subjects')?.value||'';
  const lines = raw.split('\n').map(l=>l.trim()).filter(Boolean);
  if(!lines.length){ toast('Nessun oggetto trovato'); return; }

  let imported=0, skipped=0;
  const now = Date.now();

  for(const line of lines){
    const parsed = parseOrderFromSubject(line);
    if(!parsed){ skipped++; continue; }
    const exists = dbO.orders.some(o => o.emailSubject === parsed.rawSubject);
    if(exists){ skipped++; continue; }
    dbO.orders.unshift(_mkOrder({
      customerName: parsed.customerName,
      amount: parsed.amount,
      currency: parsed.currency,
      emailSubject: parsed.rawSubject,
      orderDate: now,
      note: 'Importato da email'
    }));
    imported++;
  }

  if(imported>0){
    dbO.lastImportedAt = now;
    saveOrdineDB();
    renderOrdini();
    const ta = document.getElementById('ord-subjects');
    if(ta) ta.value='';
    toast(`✓ ${imported} ordini importati${skipped?' ('+skipped+' saltati)':''}`);
  } else {
    toast(`Nessun nuovo ordine (${skipped} già presenti o non riconosciuti)`);
  }
}

/* ─ GitHub: carica ordini ─ */
async function loadOrdiniFromGH(){
  const{token,owner,repo}=ghs;
  if(!token||!owner||!repo) return;
  const url=`https://api.github.com/repos/${owner}/${repo}/contents/data/ordini.json`;
  try{
    const r=await fetch(url,{headers:{'Authorization':`token ${token}`,'Accept':'application/vnd.github.v3+json'}});
    if(r.status===404) return;
    if(!r.ok) return;
    const d=await r.json();
    ghSha.ordini=d.sha;
    const raw=d.content.replace(/\n/g,'');
    let jsonStr;
    try{ jsonStr=decodeURIComponent(Array.from(atob(raw),c=>'%'+c.charCodeAt(0).toString(16).padStart(2,'0')).join('')); }
    catch(e){ jsonStr=atob(raw); }
    if(!jsonStr||jsonStr.trim()==='{}') return;
    const parsed=JSON.parse(jsonStr);
    if(parsed.orders&&Array.isArray(parsed.orders)){
      dbO=parsed;
      renderOrdini();
      console.log(`✓ ${parsed.orders.length} ordini caricati da GitHub`);
    }
  }catch(e){ console.warn('loadOrdiniFromGH error:',e); }
}

/* ─ GitHub: salva ordini ─ */
function saveOrdineDB(){
  if(!ghs.token||!ghs.owner||!ghs.repo){ updGh('error'); return; }
  clearTimeout(saveOrdTimer);
  saveOrdTimer=setTimeout(pushOrdiniGH, 2000);
  updGh('pending');
}

async function pushOrdiniGH(){
  const{token,owner,repo}=ghs;
  if(!token||!owner||!repo) return;
  const path='data/ordini.json';
  const url=`https://api.github.com/repos/${owner}/${repo}/contents/${path}`;
  const hd={'Authorization':`token ${token}`,'Content-Type':'application/json','Accept':'application/vnd.github.v3+json'};
  updGh('saving');
  try{
    if(!ghSha.ordini){
      const r=await fetch(url,{headers:hd});
      if(r.ok) ghSha.ordini=(await r.json()).sha;
    }
    const jsonStr=JSON.stringify(dbO,null,2);
    const bytes=new TextEncoder().encode(jsonStr);
    const b64=btoa(Array.from(bytes,b=>String.fromCharCode(b)).join(''));
    const body={message:`Ordini update — ${new Date().toLocaleString('it-IT')}`,content:b64};
    if(ghSha.ordini) body.sha=ghSha.ordini;
    const res=await fetch(url,{method:'PUT',headers:hd,body:JSON.stringify(body)});
    if(res.ok){
      ghSha.ordini=(await res.json()).content.sha;
      updGh('saved');
    } else if(res.status===409||res.status===422){
      ghSha.ordini=null;
      setTimeout(pushOrdiniGH,1000);
    } else {
      updGh('error');
    }
  }catch(e){ updGh('error'); console.error('pushOrdiniGH:',e); }
}

/* ─ Pallini fase email per la riga lista ─ */
function _phaseDots(order){
  const sent=new Set((order.emailsSent||[]).filter(e=>!e.manual).map(e=>e.type));
  const status=order.status;
  const isExpress=order.shippingType==='express';
  const phases=[
    {type:'order_received'},
    {type:'day0'},
    {type:'day10'},
    {type:'day20',hideExpress:true},
    {type:'dogana',sb:true},
    {type:'in_consegna',sb:true},
    {type:'consegnato',sb:true},
    {type:'problema',sb:true,warn:true},
  ];
  const dots=phases.filter(p=>!(p.hideExpress&&isExpress)).map(p=>{
    let bg;
    if(sent.has(p.type))          bg=p.warn?'#c0392b':'#2a9d5c';
    else if(p.sb&&status===p.type) bg='#e67e22';
    else                           bg='var(--brd2)';
    const sched=(typeof REMINDER_SCHEDULE!=='undefined'?REMINDER_SCHEDULE:[]).find(r=>r.type===p.type);
    return `<span title="${sched?esc(sched.label):p.type}" style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${bg}"></span>`;
  }).join('');
  return `<div style="display:flex;gap:2px;align-items:center">${dots}</div>`;
}

/* ─ Timeline unificata stati + email ─ */
function _buildTimeline(order){
  const TYPE_LABELS={order_received:'Conferma ricezione',day0:'Conferma spedizione',day10:'Reminder 10gg',day20:'Reminder 20gg',dogana:'In dogana',in_consegna:'In consegna',consegnato:'Consegnato',problema:'Problema spedizione'};
  const events=[];
  for(const h of (order.statusHistory||[])){
    const st=ORD_STATUS[h.status]||{l:h.status,c:'var(--bg2)',t:'var(--text2)'};
    events.push({date:h.date,kind:'status',label:st.l,note:h.note,c:st.c,t:st.t});
  }
  for(const e of (order.emailsSent||[])){
    if(e.manual) continue;
    events.push({date:e.sentAt,kind:'email',label:e.subject||TYPE_LABELS[e.type]||e.type,note:e.to});
  }
  events.sort((a,b)=>a.date-b.date);
  if(!events.length) return '';
  return events.map(ev=>{
    const d=new Date(ev.date).toLocaleString('it-IT',{day:'numeric',month:'short',year:'2-digit',hour:'2-digit',minute:'2-digit'});
    if(ev.kind==='email') return `<div class="log-e" style="display:flex;gap:8px;align-items:flex-start">
      <span style="font-size:13px;margin-top:1px">📧</span>
      <div style="flex:1;min-width:0">
        <div style="font-size:12px;font-weight:600">${esc(ev.label)}</div>
        ${ev.note?`<div style="font-size:11px;color:var(--text3)">→ ${esc(ev.note)}</div>`:''}
        <div style="font-size:10px;color:var(--text3)">${d}</div>
      </div></div>`;
    return `<div class="log-e" style="display:flex;gap:8px;align-items:flex-start">
      <span class="badge" style="background:${ev.c};color:${ev.t};font-size:10px;padding:2px 6px;white-space:nowrap;flex-shrink:0">${esc(ev.label)}</span>
      <div style="flex:1;min-width:0">
        ${ev.note?`<div style="font-size:11px;color:var(--text3)">${esc(ev.note)}</div>`:''}
        <div style="font-size:10px;color:var(--text3)">${d}</div>
      </div></div>`;
  }).join('');
}

/* ─ Render lista ordini ─ */
function renderOrdini(){
  renderEmailToggle();
  renderGmailStatus();

  const sq = (document.getElementById('ord-sq')?.value||'').toLowerCase();
  const sf = document.getElementById('ord-ss')?.value||'';

  let orders=[...dbO.orders].sort((a,b)=>b.orderDate-a.orderDate);
  if(sq) orders=orders.filter(o=>
    (o.customerName||'').toLowerCase().includes(sq)||
    (o.trackingNumber||'').toLowerCase().includes(sq)||
    (o.customerEmail||'').toLowerCase().includes(sq)
  );
  if(sf) orders=orders.filter(o=>o.status===sf);

  const liEl=document.getElementById('ord-last-import');
  if(liEl) liEl.textContent = dbO.lastImportedAt
    ? new Date(dbO.lastImportedAt).toLocaleDateString('it-IT',{day:'numeric',month:'long',year:'numeric'})
    : 'mai';

  const statsEl=document.getElementById('ord-stats');
  if(statsEl){
    const tot=dbO.orders.length;
    const transit=dbO.orders.filter(o=>['spedito','in_transito','dogana','in_consegna'].includes(o.status)).length;
    const cons=dbO.orders.filter(o=>o.status==='consegnato').length;
    const prob=dbO.orders.filter(o=>o.status==='problema').length;
    statsEl.innerHTML=
      `<div class="stat"><div class="sl">Totale ordini</div><div class="sv bl">${tot}</div></div>`+
      `<div class="stat"><div class="sl">In viaggio</div><div class="sv am">${transit}</div></div>`+
      `<div class="stat"><div class="sl">Consegnati</div><div class="sv gr">${cons}</div></div>`+
      `<div class="stat"><div class="sl">Problemi</div><div class="sv co">${prob}</div></div>`;
  }

  const bn=document.getElementById('ord-n');
  if(bn) bn.textContent=dbO.orders.filter(o=>!['consegnato','annullato'].includes(o.status)).length||'';

  const el=document.getElementById('ord-list');
  if(!el) return;

  if(!orders.length){
    el.innerHTML='<div class="empty">'+(dbO.orders.length?'Nessun ordine corrisponde ai filtri':'Nessun ordine — importa dalla sezione qui sopra')+'</div>';
    return;
  }

  el.innerHTML=orders.map(o=>{
    const st=ORD_STATUS[o.status]||ORD_STATUS.ricevuto;
    const date=new Date(o.orderDate).toLocaleDateString('it-IT',{day:'numeric',month:'short',year:'2-digit'});
    const hasMissingEmail = !o.customerEmail&&!['annullato'].includes(o.status);
    const hasMissingType = !o.shippingType&&['spedito','in_transito','dogana','in_consegna'].includes(o.status);
    return `<div class="cr" onclick="openOrdineDetail('${o.id}')">
      <div class="av av2" style="font-size:10px">${ini(o.customerName)}</div>
      <div class="ci">
        <div class="cn">${esc(o.customerName)}${hasMissingEmail?'<span style="color:var(--amber);font-size:10px;margin-left:5px">⚠ email</span>':''}${hasMissingType?'<span style="color:var(--amber);font-size:10px;margin-left:5px">⚠ tipo sped.</span>':''}</div>
        <div class="cs">${date} · €${o.amount.toFixed(2)} ${o.currency||'EUR'}${o.shippingType?' · <span style="font-size:10px;opacity:.7">'+o.shippingType+'</span>':''}</div>
      </div>
      <div style="display:flex;align-items:center;gap:6px;flex-shrink:0">
        ${_phaseDots(o)}
        <span class="badge" style="background:${st.c};color:${st.t}">${st.l}</span>
      </div>
    </div>`;
  }).join('');
}

/* ─ Dettaglio ordine ─ */
function openOrdineDetail(id){
  const o=dbO.orders.find(x=>x.id===id);
  if(!o) return;
  const st=ORD_STATUS[o.status]||ORD_STATUS.ricevuto;
  const date=new Date(o.orderDate).toLocaleDateString('it-IT',{day:'numeric',month:'long',year:'numeric'});

  const statusOptions=Object.entries(ORD_STATUS).map(([k,v])=>
    `<option value="${k}"${o.status===k?' selected':''}>${v.l}</option>`
  ).join('');

  const timeline=_buildTimeline(o);

  const trackingLink=o.trackingNumber&&o.carrier==='MBE'
    ?`<a href="https://www.mbeonline.it/tracking" target="_blank" style="font-size:12px">🔗 MBE tracking</a>`
    :'';

  showModal(`
    <div class="mt">📦 ${esc(o.customerName)}</div>

    ${dr('Stato', `<span class="badge" style="background:${st.c};color:${st.t}">${st.l}</span>`)}
    ${dr('Data ordine', date)}
    ${dr('Importo', `<strong>€${o.amount.toFixed(2)}</strong> ${o.currency||'EUR'}`)}
    ${o.shipmentCode?dr('Codice spedizione', `<span style="font-family:monospace;font-weight:700;font-size:15px">${esc(o.shipmentCode)}</span>`):''}
    ${dr('Email cliente', o.customerEmail?`<a href="mailto:${esc(o.customerEmail)}">${esc(o.customerEmail)}</a>`:'<span style="color:var(--amber)">⚠ mancante</span>')}
    ${o.customerPhone?dr('Telefono', `<a href="tel:${esc(o.customerPhone)}">${esc(o.customerPhone)}</a>`):''}
    ${o.trackingNumber?dr('Tracking', `<span style="font-family:monospace">${esc(o.trackingNumber)}</span> ${trackingLink}`):''}
    ${(()=>{const stl={standard:'Standard',express:'Express'};const v=o.shippingType?`<span class="badge" style="background:var(--blue-bg);color:var(--blue-tx)">${stl[o.shippingType]||o.shippingType}</span>`:'<span style="color:var(--amber);font-size:12px">⚠ tipo non specificato</span>';return dr('Tipologia spedizione',v);})()}
    ${o.shippingDate?dr('Data spedizione', new Date(o.shippingDate).toLocaleDateString('it-IT',{day:'numeric',month:'long',year:'numeric'})):''}
    ${o.shippingAddress?dr('Indirizzo spedizione', `<span style="font-size:12px;color:var(--text2)">${esc(o.shippingAddress)}</span>`):''}
    ${o.numberOfCartons?dr('Colli MBE', `<strong>${o.numberOfCartons}</strong> colli`):''}
    ${o.emailSubject?dr('Oggetto email', `<span style="font-size:11px;color:var(--text2)">${esc(o.emailSubject)}</span>`):''}
    ${o.notes?dr('Note', esc(o.notes)):''}

    <div class="divhr"></div>
    <div style="font-size:11px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Aggiorna ordine</div>
    <div class="fg2">
      <div class="fg"><label>Nuovo stato</label>
        <select id="ord-new-status">${statusOptions}</select>
      </div>
      <div class="fg"><label>Email cliente</label>
        <input id="ord-email" type="email" placeholder="email@cliente.com" value="${esc(o.customerEmail||'')}">
      </div>
      <div class="fg"><label>Telefono</label>
        <input id="ord-phone" placeholder="+39 333 1234567" value="${esc(o.customerPhone||'')}">
      </div>
      <div class="fg"><label>Tipologia spedizione</label>
        <select id="ord-shipping-type">
          <option value="">Non specificata</option>
          <option value="standard"${o.shippingType==='standard'?' selected':''}>Standard</option>
          <option value="express"${o.shippingType==='express'?' selected':''}>Express</option>
        </select>
      </div>
      <div class="fg fgf"><label>Tracking number</label>
        <input id="ord-tracking" placeholder="Es. 1Z999AA10123456784" value="${esc(o.trackingNumber||'')}">
      </div>
      <div class="fg fgf"><label>Indirizzo spedizione</label>
        <input id="ord-address" placeholder="Via Roma 1, 20100 Milano, Italy" value="${esc(o.shippingAddress||'')}">
      </div>
      <div class="fg fgf"><label>Note (opzionale)</label>
        <input id="ord-note" placeholder="Es. Pacco in dogana a Milano">
      </div>
      <div class="fg">
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:13px">
          <input type="checkbox" id="ord-send-email"${o.customerEmail?' checked':''} style="cursor:pointer;accent-color:var(--blue)">
          Invia email al cliente se lo stato cambia
        </label>
      </div>
    </div>

    ${timeline?`<div class="divhr"></div><div style="font-size:11px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Timeline</div><div>${timeline}</div>`:''}
    ${typeof getReminderStatusHtml==='function'?getReminderStatusHtml(o):''}

    <div class="mf">
      <button class="btn btd bts" onclick="deleteOrdine('${id}')">🗑 Elimina</button>
      <button class="btn" onclick="closeModal()">Chiudi</button>
      <button class="btn btp" onclick="saveOrdineUpdate('${id}')">Salva</button>
    </div>
  `);
}

async function saveOrdineUpdate(id){
  const o=dbO.orders.find(x=>x.id===id);
  if(!o) return;
  const newStatus=gv('ord-new-status')||o.status;
  const newTracking=(document.getElementById('ord-tracking')?.value||'').trim();
  const newEmail=(document.getElementById('ord-email')?.value||'').trim();
  const newPhone=(document.getElementById('ord-phone')?.value||'').trim();
  const newAddress=(document.getElementById('ord-address')?.value||'').trim();
  const newShippingType=gv('ord-shipping-type')||'';
  const note=(document.getElementById('ord-note')?.value||'').trim();
  const sendEmail=document.getElementById('ord-send-email')?.checked;

  if(newEmail) o.customerEmail=newEmail;
  if(newTracking) o.trackingNumber=newTracking;
  if(newPhone) o.customerPhone=newPhone;
  if(newAddress) o.shippingAddress=newAddress;
  o.shippingType=newShippingType||null;

  const statusChanged=newStatus!==o.status;
  if(statusChanged){
    o.status=newStatus;
    o.statusHistory=o.statusHistory||[];
    o.statusHistory.push({status:newStatus, date:Date.now(), note:note||''});
    if(newStatus==='spedito'&&!o.shippingDate) o.shippingDate=Date.now();
    if(['consegnato','annullato'].includes(newStatus)){
      const alreadySkipped=(o.emailsSent||[]).some(e=>e.type===newStatus);
      if(!alreadySkipped){
        o.emailsSent=o.emailsSent||[];
        o.emailsSent.push({type:newStatus, sentAt:Date.now(), messageId:'manual-skip', manual:true});
      }
    }
    if(sendEmail&&o.customerEmail){
      await sendOrdineStatusEmail(o);
    }
  }

  o.updatedAt=Date.now();
  saveOrdineDB();
  closeModal();
  renderOrdini();
  toast(statusChanged?`✓ Stato: ${ORD_STATUS[newStatus]?.l||newStatus}`:'✓ Ordine aggiornato');
}

function deleteOrdine(id){
  dbO.orders=dbO.orders.filter(o=>o.id!==id);
  closeModal();
  saveOrdineDB();
  renderOrdini();
  toast('Ordine eliminato');
}

/* ─ Aggiungi ordine manuale ─ */
function openAddOrdine(){
  showModal(`
    <div class="mt">📦 Nuovo ordine</div>
    <div class="fg2">
      <div class="fg fgf"><label>Nome cliente *</label>
        <input id="no-name" placeholder="Mario Rossi">
      </div>
      <div class="fg"><label>Email cliente</label>
        <input id="no-email" type="email" placeholder="mario@example.com">
      </div>
      <div class="fg"><label>Telefono</label>
        <input id="no-phone" placeholder="+39 333 1234567">
      </div>
      <div class="fg"><label>Importo (€)</label>
        <input id="no-amount" type="number" step="0.01" min="0" placeholder="150.00">
      </div>
      <div class="fg"><label>Data ordine</label>
        <input id="no-date" type="date" value="${new Date().toISOString().slice(0,10)}">
      </div>
      <div class="fg"><label>Tipologia spedizione</label>
        <select id="no-shipping-type">
          <option value="">Non specificata</option>
          <option value="standard">Standard</option>
          <option value="express">Express</option>
        </select>
      </div>
      <div class="fg fgf"><label>Indirizzo spedizione</label>
        <input id="no-address" placeholder="Via Roma 1, 20100 Milano, Italy">
      </div>
    </div>
    <div class="mf">
      <button class="btn" onclick="closeModal()">Annulla</button>
      <button class="btn btp" onclick="doAddOrdine()">Aggiungi ordine</button>
    </div>
  `);
}

function doAddOrdine(){
  const name=(document.getElementById('no-name')?.value||'').trim();
  const email=(document.getElementById('no-email')?.value||'').trim();
  const phone=(document.getElementById('no-phone')?.value||'').trim();
  const amount=parseFloat(document.getElementById('no-amount')?.value||'0')||0;
  const dateVal=document.getElementById('no-date')?.value;
  const shippingType=gv('no-shipping-type')||null;
  const address=(document.getElementById('no-address')?.value||'').trim();

  if(!name){ toast('Inserisci il nome del cliente'); return; }

  const newOrd=_mkOrder({
    customerName: name,
    customerEmail: email,
    customerPhone: phone,
    amount,
    orderDate: dateVal ? new Date(dateVal).getTime() : Date.now(),
    shippingAddress: address,
    note: 'Aggiunto manualmente'
  });
  newOrd.shippingType=shippingType||null;
  dbO.orders.unshift(newOrd);

  closeModal();
  saveOrdineDB();
  renderOrdini();
  toast(`✓ Ordine per ${name} aggiunto`);
}

/* ─ Email notifica stato spedizione ─ */
async function sendOrdineStatusEmail(o){
  if(!brv.apiKey){ toast('⚠ Configura Brevo nelle impostazioni per inviare email'); return; }
  if(!o.customerEmail){ toast('⚠ Email cliente mancante'); return; }

  const nome=o.customerName.split(/\s+/)[0]||o.customerName;
  const trackLine=o.trackingNumber?`Numero tracking: ${o.trackingNumber}\n`:'';

  let subject='', body='';

  switch(o.status){
    case 'spedito':
      subject=`Il tuo ordine è partito!${o.trackingNumber?' — Tracking: '+o.trackingNumber:''}`;
      body=`Caro ${nome},

il tuo ordine è stato spedito ed è ora in viaggio verso di te! 🍷

${trackLine}La spedizione dovrebbe arrivare entro 7-10 giorni lavorativi. Ti aggiorneremo ad ogni cambio di stato.

Grazie per aver scelto i nostri vini!

Luca Pattaro
Il Ciliegio — Azienda Agricola
export@ilciliegio.com | +39 331 1347899`;
      break;

    case 'in_transito':
      subject=`Aggiornamento spedizione — Il tuo vino è in viaggio`;
      body=`Caro ${nome},

il tuo ordine è in viaggio e procede regolarmente verso la destinazione. 📦

${trackLine}Tempi stimati: 5-10 giorni lavorativi dalla data di spedizione.

A presto!

Luca Pattaro
Il Ciliegio — Azienda Agricola
export@ilciliegio.com | +39 331 1347899`;
      break;

    case 'dogana':
      subject=`Il tuo ordine è in fase di sdoganamento`;
      body=`Caro ${nome},

il tuo ordine è attualmente in fase di sdoganamento. Questo processo richiede normalmente 2-5 giorni lavorativi.

${trackLine}Non è richiesto alcun intervento da parte tua — ti aggiorneremo appena l'ordine riparte.

Grazie per la pazienza!

Luca Pattaro
Il Ciliegio — Azienda Agricola
export@ilciliegio.com | +39 331 1347899`;
      break;

    case 'consegnato':
      subject=`Il tuo ordine è stato consegnato! 🍷 Buona degustazione!`;
      body=`Caro ${nome},

ottime notizie! Il tuo ordine è stato consegnato con successo. 🎉

Speriamo che tu possa apprezzare i vini de Il Ciliegio. Se hai domande o feedback, non esitare a contattarci — il tuo parere è prezioso per noi.

Saluti,

Luca Pattaro
Il Ciliegio — Azienda Agricola
export@ilciliegio.com | +39 331 1347899`;
      break;

    case 'problema':
      subject=`⚠ Aggiornamento importante sulla tua spedizione`;
      body=`Caro ${nome},

ti contatto riguardo al tuo ordine. Purtroppo si è verificato un problema con la spedizione che stiamo già monitorando attivamente.

Il nostro team è al lavoro per risolvere la situazione e ti terremo aggiornato il prima possibile.

${o.trackingNumber?`Tracking: ${o.trackingNumber}`:''}

Per qualsiasi domanda urgente, rispondi direttamente a questa email.

Luca Pattaro
Il Ciliegio — Azienda Agricola
export@ilciliegio.com | +39 331 1347899`;
      break;

    default:
      return;
  }

  try{
    const res=await fetch('https://api.brevo.com/v3/smtp/email',{
      method:'POST',
      headers:{'api-key':brv.apiKey,'Content-Type':'application/json','Accept':'application/json'},
      body:JSON.stringify({
        sender:{name:brv.senderName||'Il Ciliegio — Azienda Agricola', email:brv.senderEmail||'export@ilciliegio.com'},
        to:[{email:o.customerEmail, name:o.customerName}],
        subject:subject,
        htmlContent:buildHtmlEmail(body,'ciliegio',nome),
        textContent:body,
        tags:['wine-crm','ordini'],
        headers:{'X-CRM-OrderId':o.id}
      })
    });
    const data=await res.json();
    if(res.ok&&data.messageId){
      o.emailsSent=o.emailsSent||[];
      o.emailsSent.push({type:ORD_STATUS[o.status]?.l||o.status, sentAt:Date.now(), messageId:data.messageId});
      toast(`✓ Email "${ORD_STATUS[o.status]?.l}" inviata a ${o.customerEmail}`);
    } else {
      toast('⚠ Email non inviata: '+(data.message||res.status));
    }
  }catch(e){
    console.error('sendOrdineStatusEmail:',e);
    toast('⚠ Errore invio email: '+e.message);
  }
}


/* ═══ SETTINGS — email auto-send toggle ═══ */

async function loadSettingsFromGH(){
  const{token,owner,repo}=ghs;
  if(!token||!owner||!repo){ renderEmailToggle(); return; }
  const url=`https://api.github.com/repos/${owner}/${repo}/contents/data/crm-settings.json`;
  try{
    const r=await fetch(url,{headers:{'Authorization':`token ${token}`,'Accept':'application/vnd.github.v3+json'}});
    if(r.status===404){ renderEmailToggle(); return; }
    if(!r.ok) return;
    const d=await r.json();
    ghSha.settings=d.sha;
    const raw=d.content.replace(/\n/g,'');
    let jsonStr;
    try{ jsonStr=decodeURIComponent(Array.from(atob(raw),c=>'%'+c.charCodeAt(0).toString(16).padStart(2,'0')).join('')); }
    catch(e){ jsonStr=atob(raw); }
    dbSettings=JSON.parse(jsonStr);
    renderEmailToggle();
  }catch(e){ console.warn('loadSettingsFromGH:',e); }
}

async function pushSettingsGH(){
  const{token,owner,repo}=ghs;
  if(!token||!owner||!repo) return;
  const path='data/crm-settings.json';
  const url=`https://api.github.com/repos/${owner}/${repo}/contents/${path}`;
  const hd={'Authorization':`token ${token}`,'Content-Type':'application/json','Accept':'application/vnd.github.v3+json'};
  if(!ghSha.settings){
    const r=await fetch(url,{headers:hd});
    if(r.ok) ghSha.settings=(await r.json()).sha;
  }
  const bytes=new TextEncoder().encode(JSON.stringify(dbSettings,null,2));
  const b64=btoa(Array.from(bytes,b=>String.fromCharCode(b)).join(''));
  const body={message:`CRM settings — ${new Date().toLocaleString('it-IT')}`,content:b64};
  if(ghSha.settings) body.sha=ghSha.settings;
  const res=await fetch(url,{method:'PUT',headers:hd,body:JSON.stringify(body)});
  if(res.ok) ghSha.settings=(await res.json()).content.sha;
}

async function toggleEmailAutoSend(){
  dbSettings.emailAutoSend=!dbSettings.emailAutoSend;
  renderEmailToggle();
  await pushSettingsGH();
  toast(dbSettings.emailAutoSend?'✓ Invio automatico email ATTIVATO':'⏸ Invio automatico email DISATTIVATO');
}

async function toggleTestMode(){
  dbSettings.testMode=!dbSettings.testMode;
  renderEmailToggle();
  await pushSettingsGH();
  toast(dbSettings.testMode?'🧪 Test mode ON — email solo a te':'👥 Modalità produzione — email ai clienti');
}

function renderEmailToggle(){
  const el=document.getElementById('email-autosend-toggle');
  if(!el) return;
  const on=dbSettings.emailAutoSend===true;
  const test=dbSettings.testMode!==false;
  const mainBtn=`<button onclick="toggleEmailAutoSend()" style="font-size:12px;font-weight:700;padding:7px 16px;border-radius:20px;border:none;cursor:pointer;background:${on?'#2a9d5c':'#c0392b'};color:#fff;letter-spacing:.3px">${on?'🟢 Email: ON':'🔴 Email: OFF'}</button>`;
  const testBtn=on?`<button onclick="toggleTestMode()" style="font-size:12px;font-weight:700;padding:7px 16px;border-radius:20px;border:none;cursor:pointer;background:${test?'#e67e22':'#2980b9'};color:#fff;letter-spacing:.3px">${test?'🧪 Test mode':'👥 Clienti reali'}</button>`:'';
  el.innerHTML=`<div style="display:flex;align-items:center;gap:8px">${mainBtn}${testBtn}</div>`;
}


/* ═══ IMPORT ORDINI (GitHub Actions) ═══ */

/* ─ Aggiorna UI sezione import ─ */
function renderGmailStatus(){
  const el = document.getElementById('gmail-status');
  if(!el) return;
  const lastStr = dbO.lastImportedAt
    ? new Date(dbO.lastImportedAt).toLocaleString('it-IT',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})
    : 'mai';
  el.innerHTML = `<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:4px 0">
    <button class="btn btp bts" onclick="triggerGmailImport()" style="font-size:12px">⟳ Importa ora da Gmail</button>
    <span style="font-size:12px;color:var(--text2)">Automatico ogni mattina alle 7:00 · ultimo: <strong>${lastStr}</strong></span>
  </div>`;
}

/* ─ Triggera GitHub Actions workflow via API ─ */
async function triggerGmailImport(){
  const{token,owner,repo}=ghs;
  if(!token||!owner||!repo){ toast('⚙ Configura GitHub nelle Impostazioni'); return; }

  const url=`https://api.github.com/repos/${owner}/${repo}/actions/workflows/import_ordini.yml/dispatches`;
  try{
    const r = await fetch(url,{
      method:'POST',
      headers:{'Authorization':`token ${token}`,'Accept':'application/vnd.github.v3+json','Content-Type':'application/json'},
      body:JSON.stringify({ref:'main'})
    });
    if(r.ok||r.status===204){
      toast('✓ Import avviato — aggiorno tra ~60 secondi…');
      clearTimeout(_importPollTimer);
      _importPollTimer = setTimeout(async()=>{
        await loadOrdiniFromGH();
        toast('✓ Ordini aggiornati');
      }, 65000);
    } else {
      toast('⚠ Errore avvio workflow: '+r.status);
    }
  }catch(e){ toast('⚠ '+e.message); }
}
