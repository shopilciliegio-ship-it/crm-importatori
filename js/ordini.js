/* ═══ ORDINI ═══ */

const ORD_STATUS = {
  ricevuto:     {l:'Ricevuto',         c:'var(--blue-bg)',   t:'var(--blue-tx)'},
  preparazione: {l:'In preparazione',  c:'var(--amber-bg)',  t:'var(--amber-tx)'},
  spedito:      {l:'Spedito',          c:'var(--teal-bg)',   t:'var(--teal-tx)'},
  in_transito:  {l:'In transito',      c:'var(--blue-bg)',   t:'var(--blue-tx)'},
  dogana:       {l:'In dogana',        c:'var(--amber-bg)',  t:'var(--amber-tx)'},
  consegnato:   {l:'Consegnato',       c:'var(--green-bg)',  t:'var(--green-tx)'},
  problema:     {l:'Problema',         c:'var(--red-bg)',    t:'var(--red-tx)'},
  annullato:    {l:'Annullato',        c:'var(--gray-bg)',   t:'var(--gray-tx)'},
};

function uidOrd(){ return 'ord_'+Date.now().toString(36)+Math.random().toString(36).slice(2,6); }

/* ─ Parsing oggetto email ─ */
function parseOrderFromSubject(subject){
  // Pattern atteso: 🍷 New Order — NOME COGNOME — 294.05 EUR
  // Il prezzo è opzionale (può mancare o variare nel formato)
  const s = subject.trim();

  // Estrai nome: tutto ciò che sta tra il primo — e il secondo — (o fine stringa)
  const m = s.match(/New\s+Order\s*[—\-–]+\s*([^—\-–]+?)(?:\s*[—\-–]+\s*([\d.,]+)\s*(EUR|USD|GBP)?)?$/i);
  if(!m || !m[1]) return null;

  const customerName = m[1].trim();
  if(!customerName) return null;

  return {
    customerName,
    amount: m[2] ? parseFloat(m[2].replace(',','.')) : 0,
    currency: (m[3]||'EUR').toUpperCase(),
    rawSubject: s
  };
}

/* ─ Import da soggetti email incollati ─ */
function importFromSubjects(){
  const raw = document.getElementById('ord-subjects')?.value||'';
  const lines = raw.split('\n').map(l=>l.trim()).filter(Boolean);
  if(!lines.length){ toast('Nessun oggetto trovato'); return; }

  let imported=0, skipped=0;
  const now = Date.now();

  for(const line of lines){
    const parsed = parseOrderFromSubject(line);
    if(!parsed){ skipped++; continue; }

    // Dedup: stesso oggetto email esatto → stesso ordine
    const exists = dbO.orders.some(o => o.emailSubject === parsed.rawSubject);
    if(exists){ skipped++; continue; }

    dbO.orders.unshift({
      id: uidOrd(),
      customerName: parsed.customerName,
      customerEmail: '',
      amount: parsed.amount,
      currency: parsed.currency,
      orderDate: now,
      emailSubject: parsed.rawSubject,
      trackingNumber: '',
      carrier: 'MBE',
      shippingDate: null,
      status: 'ricevuto',
      statusHistory: [{status:'ricevuto', date:now, note:'Importato da email'}],
      emailsSent: [],
      notes: '',
      createdAt: now,
      updatedAt: now
    });
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

/* ─ Render lista ordini ─ */
function renderOrdini(){
  const sq = (document.getElementById('ord-sq')?.value||'').toLowerCase();
  const sf = document.getElementById('ord-ss')?.value||'';

  let orders=[...dbO.orders].sort((a,b)=>b.orderDate-a.orderDate);
  if(sq) orders=orders.filter(o=>
    (o.customerName||'').toLowerCase().includes(sq)||
    (o.trackingNumber||'').toLowerCase().includes(sq)||
    (o.customerEmail||'').toLowerCase().includes(sq)
  );
  if(sf) orders=orders.filter(o=>o.status===sf);

  // Aggiorna data ultimo import
  const liEl=document.getElementById('ord-last-import');
  if(liEl) liEl.textContent = dbO.lastImportedAt
    ? new Date(dbO.lastImportedAt).toLocaleDateString('it-IT',{day:'numeric',month:'long',year:'numeric'})
    : 'mai';

  // Stats
  const statsEl=document.getElementById('ord-stats');
  if(statsEl){
    const tot=dbO.orders.length;
    const transit=dbO.orders.filter(o=>['spedito','in_transito','dogana'].includes(o.status)).length;
    const cons=dbO.orders.filter(o=>o.status==='consegnato').length;
    const prob=dbO.orders.filter(o=>o.status==='problema').length;
    statsEl.innerHTML=
      `<div class="stat"><div class="sl">Totale ordini</div><div class="sv bl">${tot}</div></div>`+
      `<div class="stat"><div class="sl">In viaggio</div><div class="sv am">${transit}</div></div>`+
      `<div class="stat"><div class="sl">Consegnati</div><div class="sv gr">${cons}</div></div>`+
      `<div class="stat"><div class="sl">Problemi</div><div class="sv co">${prob}</div></div>`;
  }

  // Badge tab
  const bn=document.getElementById('ord-n');
  if(bn) bn.textContent=dbO.orders.filter(o=>!['consegnato','annullato'].includes(o.status)).length||'';

  // Lista
  const el=document.getElementById('ord-list');
  if(!el) return;

  if(!orders.length){
    el.innerHTML='<div class="empty">'+(dbO.orders.length?'Nessun ordine corrisponde ai filtri':'Nessun ordine — importa dalla sezione qui sopra')+'</div>';
    return;
  }

  el.innerHTML=orders.map(o=>{
    const st=ORD_STATUS[o.status]||ORD_STATUS.ricevuto;
    const date=new Date(o.orderDate).toLocaleDateString('it-IT',{day:'numeric',month:'short',year:'2-digit'});
    const tracking=o.trackingNumber
      ?`<span style="font-size:11px;font-family:monospace;background:var(--bg2);padding:2px 6px;border-radius:4px;margin-right:6px">${esc(o.trackingNumber)}</span>`
      :'';
    const hasMissingEmail = !o.customerEmail&&!['annullato'].includes(o.status);
    return `<div class="cr" onclick="openOrdineDetail('${o.id}')">
      <div class="av av2" style="font-size:10px">${ini(o.customerName)}</div>
      <div class="ci">
        <div class="cn">${esc(o.customerName)}${hasMissingEmail?'<span style="color:var(--amber);font-size:10px;margin-left:5px">⚠ email mancante</span>':''}</div>
        <div class="cs">${date} · €${o.amount.toFixed(2)} ${o.currency||'EUR'}</div>
      </div>
      <div style="display:flex;align-items:center;gap:4px;flex-shrink:0">
        ${tracking}
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

  const history=(o.statusHistory||[]).slice().reverse().map(h=>{
    const d=new Date(h.date).toLocaleString('it-IT',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
    const hs=ORD_STATUS[h.status]||{l:h.status};
    return `<div class="log-e"><strong>${hs.l}</strong> — ${d}${h.note?'<br><span style="color:var(--text3);font-size:11px">'+esc(h.note)+'</span>':''}</div>`;
  }).join('');

  const emailsSent=(o.emailsSent||[]).slice().reverse().map(e=>{
    const d=new Date(e.sentAt).toLocaleString('it-IT',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
    return `<div class="log-e">📧 ${esc(e.type)} — ${d}</div>`;
  }).join('');

  const trackingLink=o.trackingNumber
    ?`<a href="https://www.17track.net/en/track?nums=${encodeURIComponent(o.trackingNumber)}" target="_blank" style="font-size:12px">🔗 17track</a>`
     +(o.carrier==='MBE'?` &nbsp;<a href="https://www.mbeonline.it/tracking" target="_blank" style="font-size:12px">MBE</a>`:'')
    :'';

  showModal(`
    <div class="mt">📦 ${esc(o.customerName)}</div>

    ${dr('Stato', `<span class="badge" style="background:${st.c};color:${st.t}">${st.l}</span>`)}
    ${dr('Data ordine', date)}
    ${dr('Importo', `<strong>€${o.amount.toFixed(2)}</strong> ${o.currency||'EUR'}`)}
    ${dr('Email cliente', o.customerEmail?`<a href="mailto:${esc(o.customerEmail)}">${esc(o.customerEmail)}</a>`:'<span style="color:var(--amber)">⚠ mancante</span>')}
    ${o.trackingNumber?dr('Tracking', `<span style="font-family:monospace">${esc(o.trackingNumber)}</span> ${trackingLink}`):''}
    ${o.shippingDate?dr('Data spedizione', new Date(o.shippingDate).toLocaleDateString('it-IT',{day:'numeric',month:'long',year:'numeric'})):''}
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
      <div class="fg fgf"><label>Tracking number</label>
        <input id="ord-tracking" placeholder="Es. 1Z999AA10123456784" value="${esc(o.trackingNumber||'')}">
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

    ${history?`<div class="divhr"></div><div style="font-size:11px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Storico stati</div><div>${history}</div>`:''}
    ${emailsSent?`<div class="divhr"></div><div style="font-size:11px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Email inviate</div><div>${emailsSent}</div>`:''}

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
  const note=(document.getElementById('ord-note')?.value||'').trim();
  const sendEmail=document.getElementById('ord-send-email')?.checked;

  if(newEmail) o.customerEmail=newEmail;
  if(newTracking) o.trackingNumber=newTracking;

  const statusChanged=newStatus!==o.status;
  if(statusChanged){
    o.status=newStatus;
    o.statusHistory=o.statusHistory||[];
    o.statusHistory.push({status:newStatus, date:Date.now(), note:note||''});
    if(newStatus==='spedito'&&!o.shippingDate) o.shippingDate=Date.now();

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
      <div class="fg"><label>Importo (€)</label>
        <input id="no-amount" type="number" step="0.01" min="0" placeholder="150.00">
      </div>
      <div class="fg"><label>Data ordine</label>
        <input id="no-date" type="date" value="${new Date().toISOString().slice(0,10)}">
      </div>
      <div class="fg fgf"><label>Oggetto email originale (opzionale)</label>
        <input id="no-subject" placeholder="🍷 New Order — Mario Rossi — 150.00 EUR">
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
  const amount=parseFloat(document.getElementById('no-amount')?.value||'0')||0;
  const dateVal=document.getElementById('no-date')?.value;
  const subject=(document.getElementById('no-subject')?.value||'').trim();

  if(!name){ toast('Inserisci il nome del cliente'); return; }

  const orderDate=dateVal?new Date(dateVal).getTime():Date.now();
  const now=Date.now();

  dbO.orders.unshift({
    id:uidOrd(),
    customerName:name,
    customerEmail:email,
    amount:amount,
    currency:'EUR',
    orderDate:orderDate,
    emailSubject:subject,
    trackingNumber:'',
    carrier:'MBE',
    shippingDate:null,
    status:'ricevuto',
    statusHistory:[{status:'ricevuto',date:now,note:'Aggiunto manualmente'}],
    emailsSent:[],
    notes:'',
    createdAt:now,
    updatedAt:now
  });

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
  const trackUrl=o.trackingNumber
    ?`https://www.17track.net/en/track?nums=${encodeURIComponent(o.trackingNumber)}`
    :'';

  let subject='', body='';

  switch(o.status){
    case 'spedito':
      subject=`Il tuo ordine è partito!${o.trackingNumber?' — Tracking: '+o.trackingNumber:''}`;
      body=`Caro ${nome},

il tuo ordine è stato spedito ed è ora in viaggio verso di te! 🍷

${o.trackingNumber?`Numero di tracking: ${o.trackingNumber}\nSeguilo in tempo reale: ${trackUrl}\n`:''}
La spedizione dovrebbe arrivare entro 7-10 giorni lavorativi. Ti aggiorneremo ad ogni cambio di stato.

Grazie per aver scelto i nostri vini!

Luca Pattaro
Il Ciliegio — Azienda Agricola
export@ilciliegio.com | +39 331 1347899`;
      break;

    case 'in_transito':
      subject=`Aggiornamento spedizione — Il tuo vino è in viaggio`;
      body=`Caro ${nome},

il tuo ordine è in viaggio e procede regolarmente verso la destinazione. 📦

${o.trackingNumber?`Tracking: ${o.trackingNumber}\nAggiornamenti: ${trackUrl}\n`:''}
Tempi stimati: 5-10 giorni lavorativi dalla data di spedizione.

A presto!

Luca Pattaro
Il Ciliegio — Azienda Agricola
export@ilciliegio.com | +39 331 1347899`;
      break;

    case 'dogana':
      subject=`Il tuo ordine è in fase di sdoganamento`;
      body=`Caro ${nome},

il tuo ordine è attualmente in fase di sdoganamento. Questo processo richiede normalmente 2-5 giorni lavorativi.

${o.trackingNumber?`Puoi seguire l'avanzamento su: ${trackUrl}\n`:''}
Non è richiesto alcun intervento da parte tua — ti aggiorneremo appena l'ordine riparte.

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
