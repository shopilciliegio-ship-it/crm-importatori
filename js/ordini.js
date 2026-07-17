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
  consegna_fallita: {l:'Mancata consegna', c:'var(--amber-bg)', t:'var(--amber-tx)'},
  consegnato:   {l:'Consegnato',       c:'var(--green-bg)',  t:'var(--green-tx)'},
  problema:     {l:'Problema',         c:'var(--red-bg)',    t:'var(--red-tx)'},
  annullato:    {l:'Annullato',        c:'var(--gray-bg)',   t:'var(--gray-tx)'},
};

// Ordine "fase spedizione" per il filtro Ordina per (vs il default per data ordine):
// preparazione → transito → dogana → problema → in consegna → mancata consegna → consegnato.
// ricevuto/spedito esclusi apposta: non si verificano mai nella pipeline reale
// (gli ordini partono già da "preparazione" in import_ordini.py, e "spedito" è
// troppo transitorio per essere osservato tra un polling e l'altro).
const ORD_PHASE_RANK = {
  preparazione:1, in_transito:3, dogana:4,
  problema:5, in_consegna:6, consegna_fallita:7, consegnato:8, annullato:9,
};

/* ─ Paese di destinazione: dedotto dall'indirizzo, o impostato a mano ─ */
// Gli ordini non hanno un campo "paese" strutturato — solo shippingAddress (testo
// libero). Fieramente/Shop di solito riportano stato/paese per esteso; MBE spesso
// riporta solo "via, città" senza alcun indizio geografico (impossibile da dedurre).
// o.destCountry (ISO2), se impostato a mano dall'utente, ha sempre la precedenza.
const COUNTRY_NAME_TO_ISO2 = {
  'united states':'US','united states of america':'US','usa':'US','u.s.a':'US','u.s.a.':'US',
  'italy':'IT','italia':'IT',
  'united kingdom':'GB','great britain':'GB','england':'GB','scotland':'GB','wales':'GB','uk':'GB',
  'canada':'CA','germany':'DE','germania':'DE','france':'FR','francia':'FR',
  'spain':'ES','spagna':'ES','portugal':'PT','portogallo':'PT',
  'switzerland':'CH','svizzera':'CH','netherlands':'NL','olanda':'NL','paesi bassi':'NL',
  'belgium':'BE','belgio':'BE','austria':'AT','ireland':'IE','irlanda':'IE',
  'poland':'PL','polonia':'PL','sweden':'SE','svezia':'SE','norway':'NO','norvegia':'NO',
  'denmark':'DK','danimarca':'DK','finland':'FI','finlandia':'FI',
  'greece':'GR','grecia':'GR','czech republic':'CZ','czechia':'CZ',
  'hungary':'HU','ungheria':'HU','romania':'RO','bulgaria':'BG',
  'croatia':'HR','croazia':'HR','slovenia':'SI','slovakia':'SK','slovacchia':'SK',
  'luxembourg':'LU','lussemburgo':'LU','malta':'MT','cyprus':'CY','cipro':'CY',
  'estonia':'EE','latvia':'LV','lithuania':'LT','iceland':'IS','islanda':'IS',
  'australia':'AU','new zealand':'NZ','nuova zelanda':'NZ',
  'japan':'JP','giappone':'JP','china':'CN','cina':'CN',
  'south korea':'KR','singapore':'SG','hong kong':'HK','taiwan':'TW',
  'brazil':'BR','brasile':'BR','argentina':'AR','chile':'CL','cile':'CL',
  'colombia':'CO','peru':'PE','perù':'PE','uruguay':'UY',
  'south africa':'ZA','sudafrica':'ZA','israel':'IL','israele':'IL',
  'united arab emirates':'AE','uae':'AE','emirati arabi':'AE',
  'russia':'RU','ukraine':'UA','ucraina':'UA','turkey':'TR','turchia':'TR',
};
// Molti indirizzi Fieramente/MBE riportano lo stato USA o la regione italiana per
// esteso senza scrivere il paese ("United States"/"Italy") — usati come fallback,
// controllati PRIMA dei nomi paese in guessCountryFromAddress() per evitare conflitti
// tipo "New Mexico" (stato USA) letto come paese "Mexico".
const US_STATE_TO_ISO2 = {
  'alabama':'US','alaska':'US','arizona':'US','arkansas':'US','california':'US',
  'colorado':'US','connecticut':'US','delaware':'US','florida':'US','georgia':'US',
  'hawaii':'US','idaho':'US','illinois':'US','indiana':'US','iowa':'US','kansas':'US',
  'kentucky':'US','louisiana':'US','maine':'US','maryland':'US','massachusetts':'US',
  'michigan':'US','minnesota':'US','mississippi':'US','missouri':'US','montana':'US',
  'nebraska':'US','nevada':'US','new hampshire':'US','new jersey':'US','new mexico':'US',
  'new york':'US','north carolina':'US','north dakota':'US','ohio':'US','oklahoma':'US',
  'oregon':'US','pennsylvania':'US','rhode island':'US','south carolina':'US','south dakota':'US',
  'tennessee':'US','texas':'US','utah':'US','vermont':'US','virginia':'US','washington':'US',
  'west virginia':'US','wisconsin':'US','wyoming':'US','district of columbia':'US',
};
const IT_REGION_TO_ISO2 = {
  'lombardy':'IT','lombardia':'IT','tuscany':'IT','toscana':'IT','piedmont':'IT','piemonte':'IT',
  'veneto':'IT','sicily':'IT','sicilia':'IT','sardinia':'IT','sardegna':'IT','apulia':'IT','puglia':'IT',
  'campania':'IT','emilia-romagna':'IT','emilia romagna':'IT','liguria':'IT','marche':'IT',
  'abruzzo':'IT','umbria':'IT','calabria':'IT','basilicata':'IT','molise':'IT',
  'friuli-venezia giulia':'IT','friuli venezia giulia':'IT','trentino-alto adige':'IT',
  'trentino alto adige':'IT','aosta valley':'IT',"valle d'aosta":'IT','lazio':'IT',
};
// Lista per il menu a tendina "Paese" nella scheda ordine — etichette in italiano.
const ORDER_COUNTRIES = [
  {iso2:'IT',label:'Italia'},{iso2:'US',label:'Stati Uniti'},{iso2:'GB',label:'Regno Unito'},
  {iso2:'CA',label:'Canada'},{iso2:'DE',label:'Germania'},{iso2:'FR',label:'Francia'},
  {iso2:'ES',label:'Spagna'},{iso2:'PT',label:'Portogallo'},{iso2:'CH',label:'Svizzera'},
  {iso2:'NL',label:'Paesi Bassi'},{iso2:'BE',label:'Belgio'},{iso2:'AT',label:'Austria'},
  {iso2:'IE',label:'Irlanda'},{iso2:'PL',label:'Polonia'},{iso2:'SE',label:'Svezia'},
  {iso2:'NO',label:'Norvegia'},{iso2:'DK',label:'Danimarca'},{iso2:'FI',label:'Finlandia'},
  {iso2:'GR',label:'Grecia'},{iso2:'CZ',label:'Rep. Ceca'},{iso2:'HU',label:'Ungheria'},
  {iso2:'RO',label:'Romania'},{iso2:'BG',label:'Bulgaria'},{iso2:'HR',label:'Croazia'},
  {iso2:'SI',label:'Slovenia'},{iso2:'SK',label:'Slovacchia'},{iso2:'LU',label:'Lussemburgo'},
  {iso2:'MT',label:'Malta'},{iso2:'CY',label:'Cipro'},{iso2:'EE',label:'Estonia'},
  {iso2:'LV',label:'Lettonia'},{iso2:'LT',label:'Lituania'},{iso2:'IS',label:'Islanda'},
  {iso2:'AU',label:'Australia'},{iso2:'NZ',label:'Nuova Zelanda'},{iso2:'JP',label:'Giappone'},
  {iso2:'CN',label:'Cina'},{iso2:'KR',label:'Corea del Sud'},{iso2:'SG',label:'Singapore'},
  {iso2:'HK',label:'Hong Kong'},{iso2:'TW',label:'Taiwan'},{iso2:'BR',label:'Brasile'},
  {iso2:'AR',label:'Argentina'},{iso2:'CL',label:'Cile'},{iso2:'CO',label:'Colombia'},
  {iso2:'PE',label:'Perù'},{iso2:'UY',label:'Uruguay'},{iso2:'MX',label:'Messico'},
  {iso2:'ZA',label:'Sudafrica'},{iso2:'IL',label:'Israele'},{iso2:'AE',label:'Emirati Arabi'},
  {iso2:'RU',label:'Russia'},{iso2:'UA',label:'Ucraina'},{iso2:'TR',label:'Turchia'},
].sort((a,b)=>a.label.localeCompare(b.label,'it'));

function guessCountryFromAddress(address){
  if(!address) return null;
  const addr=' '+address.toLowerCase().replace(/[.,()]/g,' ')+' ';
  const esc_=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  // Stati USA/regioni italiane per esteso prima dei nomi paese: evita che "new mexico"
  // (indirizzo USA) venga scambiato per il paese "Mexico" (non presente in
  // COUNTRY_NAME_TO_ISO2 per questo stesso motivo — la base clienti è a stragrande
  // maggioranza statunitense).
  const subCountry = {...US_STATE_TO_ISO2, ...IT_REGION_TO_ISO2};
  for(const name of Object.keys(subCountry).sort((a,b)=>b.length-a.length)){
    if(new RegExp('\\b'+esc_(name)+'\\b').test(addr)) return subCountry[name];
  }
  for(const name of Object.keys(COUNTRY_NAME_TO_ISO2).sort((a,b)=>b.length-a.length)){
    if(new RegExp('\\b'+esc_(name)+'\\b').test(addr)) return COUNTRY_NAME_TO_ISO2[name];
  }
  return null;
}

function orderDestCountry(o){
  return o.destCountry || guessCountryFromAddress(o.shippingAddress);
}

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
    trackingUrl: '',
    carrier: 'MBE',
    language: 'en',
    shippingType: null,
    shippingDate: null,
    destCountry: null,
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

/* ─ Sync silenzioso eventi Brevo per ordini (bounce detection) ─ */
async function syncOrdiniBrevoEventsQuiet(){
  if(!brv.apiKey) return;
  const cutoff=Date.now()-14*86400000; // ultime 2 settimane
  const toSync=[];
  (dbO.orders||[]).forEach(o=>{
    (o.emailsSent||[]).forEach((e,i)=>{
      if(e.messageId&&e.messageId!=='manual-skip'&&!e.bounced&&(e.sentAt||0)>cutoff)
        toSync.push({order:o, evIdx:i, messageId:e.messageId});
    });
  });
  if(!toSync.length) return;
  let newBounces=0;
  for(const {order,evIdx,messageId} of toSync){
    try{
      const r=await fetch(
        `https://api.brevo.com/v3/smtp/statistics/events?messageId=${encodeURIComponent(messageId)}&limit=50`,
        {headers:{'api-key':brv.apiKey,'Accept':'application/json'}}
      );
      if(!r.ok) continue;
      const data=await r.json();
      const ev=order.emailsSent[evIdx];
      (data.events||[]).forEach(e=>{
        const type=(e.event||'').toLowerCase();
        if(!ev.delivered&&(type==='delivered'||type==='requests')){ev.delivered=true;ev.deliveredAt=e.date;}
        if(!ev.bounced&&(type==='hardbounces'||type==='softbounces'||type==='bounced')){
          ev.bounced=true;ev.bouncedAt=e.date;
          order.statusHistory=order.statusHistory||[];
          order.statusHistory.push({status:'problema',date:Date.now(),
            note:`⚠ Email bounce (${ev.type||''}): ${order.customerEmail||''}`});
          newBounces++;
        }
      });
    }catch(e){ console.warn('Brevo ordini sync:',e); }
    await new Promise(r=>setTimeout(r,150));
  }
  if(newBounces>0){ saveOrdineDB(); renderOrdini(); toast(`⚠ ${newBounces} bounce email ordini — controlla i destinatari`); }
}

function _fmtDM(ms){
  return ms?new Date(ms).toLocaleDateString('it-IT',{day:'2-digit',month:'2-digit'}):'';
}

/* ─ Pallini fase email per la riga lista ─ */
function _phaseDots(order){
  const sent=new Set((order.emailsSent||[]).filter(e=>!e.manual).map(e=>e.type));
  const bounced=new Set((order.emailsSent||[]).filter(e=>!e.manual&&e.bounced).map(e=>e.type));
  const status=order.status;
  const isExpress=order.shippingType==='express';
  const isStandard=order.shippingType==='standard';
  const now=Date.now();
  const sd=order.shippingDate?+order.shippingDate:null;
  const daysSince=sd?(now-sd)/86400000:null;
  const daysOld=(now-(order.orderDate||0))/86400000;

  const phases=[
    {type:'order_received'},
    {type:'day0'},
    {type:'day10'},
    {type:'day20',hideExpress:true},
    {type:'dogana',sb:true},
    {type:'in_consegna',sb:true},
    {type:'consegna_fallita',sb:true,warn:true},
    {type:'consegnato',sb:true},
    {type:'problema',sb:true,warn:true},
  ];

  function _isPending(p){
    if(p.type==='order_received') return ['ricevuto','preparazione'].includes(status);
    if(p.type==='day0')  return sd&&daysSince<=3;
    if(p.type==='day10') return sd&&daysSince>=10&&daysSince<=13&&!['consegnato','annullato','dogana','in_consegna','consegna_fallita'].includes(status);
    if(p.type==='day20') return sd&&isStandard&&daysSince>=20&&daysSince<=23&&!['consegnato','annullato','dogana','in_consegna','consegna_fallita'].includes(status);
    return false;
  }

  const dots=phases.filter(p=>!(p.hideExpress&&isExpress)).map(p=>{
    let bg, title='', dateLabel='';
    const sched=(typeof REMINDER_SCHEDULE!=='undefined'?REMINDER_SCHEDULE:[]).find(r=>r.type===p.type);
    const sentEntry=(order.emailsSent||[]).find(e=>e.type===p.type&&!e.manual);
    if(bounced.has(p.type)){
      bg='#e74c3c'; title=(sched?.label||p.type)+' — ⚠ BOUNCE';
      dateLabel=_fmtDM(sentEntry?.sentAt);
    } else if(sent.has(p.type)) {
      bg=p.warn?'#c0392b':'#2a9d5c'; title=sched?.label||p.type;
      dateLabel=_fmtDM(sentEntry?.sentAt);
    } else if(p.sb&&status===p.type){
      bg='#e67e22'; title=sched?.label||p.type;
    } else if(_isPending(p)){
      bg='#e67e22'; title=sched?.label||p.type;
      if(sd&&sched?.days!=null) dateLabel=_fmtDM(sd+sched.days*86400000);
    } else {
      bg='var(--brd2)'; title=sched?.label||p.type;
      if(sd&&sched?.days!=null){
        const target=sd+sched.days*86400000;
        dateLabel=_fmtDM(target);
        if(target<now) title+=' — ⚠ finestra scaduta';
      }
    }
    return `<div style="display:flex;flex-direction:column;align-items:center;gap:1px;min-width:16px">
      <span style="font-size:8px;color:var(--text3);line-height:1">${dateLabel||'&nbsp;'}</span>
      <span title="${esc(title)}" style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${bg}"></span>
    </div>`;
  }).join('');
  return `<div style="display:flex;gap:1px;align-items:center">${dots}</div>`;
}

/* ─ Timeline unificata stati + email ─ */
function _buildTimeline(order){
  const TYPE_LABELS={order_received:'Conferma ricezione',day0:'Conferma spedizione',day10:'Reminder 10gg',day20:'Reminder 20gg',dogana:'In dogana',in_consegna:'In consegna',consegna_fallita:'Mancata consegna',consegnato:'Consegnato',problema:'Problema spedizione'};
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
  const sortMode = document.getElementById('ord-sort')?.value||'date';

  let orders=[...dbO.orders].sort(sortMode==='phase'
    ? (a,b)=>{
        const ra=ORD_PHASE_RANK[a.status]??99, rb=ORD_PHASE_RANK[b.status]??99;
        return ra!==rb ? ra-rb : b.orderDate-a.orderDate;
      }
    : (a,b)=>b.orderDate-a.orderDate);
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
    const destCountry = orderDestCountry(o);
    // Su Windows le bandiere emoji spesso NON vengono disegnate come icona colorata
    // (limite noto del font di sistema, a differenza di macOS/iOS) — il glifo da solo
    // degrada a testo grigio minuscolo che si perde nello sfondo. Un badge con
    // sfondo garantisce che il paese si veda sempre, con o senza rendering emoji.
    const countryBadge = destCountry
      ?`<span class="badge" style="background:var(--blue-bg);color:var(--blue-tx);font-size:10px" title="${esc(destCountry)}">${esc(destCountry)}</span> · `
      :'';
    return `<div class="cr" onclick="openOrdineDetail('${o.id}')">
      <div class="av av2" style="font-size:10px">${ini(o.customerName)}</div>
      <div class="ci">
        <div class="cn">${esc(o.customerName)}${o.source==='shop'?'<span class="badge" style="background:var(--teal-bg);color:var(--teal-tx);font-size:9px;margin-left:5px">🛒 Shop Online</span>':''}${hasMissingEmail?'<span style="color:var(--amber);font-size:10px;margin-left:5px">⚠ email</span>':''}${hasMissingType&&o.source!=='shop'?'<span style="color:var(--amber);font-size:10px;margin-left:5px">⚠ tipo sped.</span>':''}</div>
        <div class="cs">${countryBadge}${date} · €${o.amount.toFixed(2)} ${o.currency||'EUR'}${o.shippingType?' · <span style="font-size:10px;opacity:.7">'+o.shippingType+'</span>':''}</div>
      </div>
      <div style="display:flex;align-items:center;gap:6px;flex-shrink:0">
        ${_phaseDots(o)}
        <span class="badge" style="background:${st.c};color:${st.t};min-width:104px;text-align:center">${st.l}</span>
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

  const trackingLink=o.trackingUrl
    ?`<a href="${esc(o.trackingUrl)}" target="_blank" style="font-size:12px">🔗 Traccia spedizione</a>`
    :(o.trackingNumber
      ?`<a href="https://t.17track.net/en#nums=${encodeURIComponent(o.trackingNumber)}" target="_blank" style="font-size:12px">🔗 17Track</a>`
      :'');

  const spedireproSearchBtn=o.trackingUrl?'':
    `<button id="spedirepro-sync-btn" class="btn" style="font-size:12px;padding:4px 10px" onclick="triggerSpedireproSync()">🔄 Cerca su SpedirePro</button>`;

  showModal(`
    <div class="mt">📦 ${esc(o.customerName)}${o.source==='shop'?' <span class="badge" style="background:var(--teal-bg);color:var(--teal-tx);font-size:11px;vertical-align:middle">🛒 Shop Online</span>':''}</div>

    ${dr('Stato', `<span class="badge" style="background:${st.c};color:${st.t}">${st.l}</span>`)}
    ${o.orderNumber?dr('Nr. ordine', `<span style="font-family:monospace;font-weight:700">${esc(o.orderNumber)}</span>`):''}
    ${dr('Data ordine', date)}
    ${o.paymentType?dr('Pagamento', esc(o.paymentType)):''}
    ${o.shipmentCode?dr('Codice spedizione', `<span style="font-family:monospace;font-weight:700;font-size:15px">${esc(o.shipmentCode)}</span>`):''}
    ${o.carrier?dr('Corriere', esc(o.carrier)):''}
    ${dr('Email cliente', o.customerEmail?`<a href="mailto:${esc(o.customerEmail)}">${esc(o.customerEmail)}</a>`:'<span style="color:var(--amber)">⚠ mancante</span>')}
    ${o.customerPhone?dr('Telefono', `<a href="tel:${esc(o.customerPhone)}">${esc(o.customerPhone)}</a>`):''}
    ${o.trackingNumber?dr('Tracking', `<span style="font-family:monospace">${esc(o.trackingNumber)}</span> ${trackingLink}`):(trackingLink?dr('Tracking', trackingLink):'')}
    ${spedireproSearchBtn?dr('SpedirePro', spedireproSearchBtn):''}
    ${(()=>{const stl={standard:'Standard',express:'Express'};const v=o.shippingType?`<span class="badge" style="background:var(--blue-bg);color:var(--blue-tx)">${stl[o.shippingType]||o.shippingType}</span>`:'<span style="color:var(--amber);font-size:12px">⚠ tipo non specificato</span>';return dr('Tipologia spedizione',v);})()}
    ${o.shippingDate?dr('Data spedizione', new Date(o.shippingDate).toLocaleDateString('it-IT',{day:'numeric',month:'long',year:'numeric'})):''}
    ${(()=>{const dc=orderDestCountry(o);const label=dc?(ORDER_COUNTRIES.find(c=>c.iso2===dc)?.label||dc):'';const v=dc?`<span class="badge" style="background:var(--blue-bg);color:var(--blue-tx)">${esc(dc)}</span> ${esc(label)}${!o.destCountry?' <span style="color:var(--text3);font-size:11px">(dedotto dall\'indirizzo)</span>':''}`:'<span style="color:var(--amber);font-size:12px">⚠ non rilevabile dall\'indirizzo — impostalo qui sotto</span>';return dr('Paese di destinazione',v);})()}
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
      <div class="fg"><label>Importo</label>
        <input id="ord-amount" type="number" step="0.01" min="0" placeholder="0.00" value="${o.amount!=null?o.amount:''}">
      </div>
      <div class="fg"><label>Valuta</label>
        <input id="ord-currency" placeholder="EUR" value="${esc(o.currency||'EUR')}">
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
      <div class="fg"><label>Paese di destinazione</label>
        <select id="ord-dest-country">
          <option value=""${!orderDestCountry(o)?' selected':''}>Auto (nessun paese dedotto)</option>
          ${ORDER_COUNTRIES.map(c=>`<option value="${c.iso2}"${orderDestCountry(o)===c.iso2?' selected':''}>${esc(c.label)} (${c.iso2})</option>`).join('')}
        </select>
      </div>
      <div class="fg"><label>Corriere</label>
        <input id="ord-carrier" placeholder="Es. MBE, BRT, GLS, Spedire.com" value="${esc(o.carrier||'')}">
      </div>
      <div class="fg"><label>Tracking number</label>
        <input id="ord-tracking" placeholder="Es. 1Z999AA10123456784" value="${esc(o.trackingNumber||'')}">
      </div>
      <div class="fg"><label>Codice spedizione Fieramente</label>
        <input id="ord-shipment-code" placeholder="Es. COLEA" value="${esc(o.shipmentCode||'')}" style="text-transform:uppercase">
      </div>
      <div class="fg fgf"><label>Link tracciamento</label>
        <input id="ord-tracking-url" placeholder="Es. https://www.spedire.com/tracking/3UW1D56044876" value="${esc(o.trackingUrl||'')}">
      </div>
      <div class="fg"><label>Lingua email cliente</label>
        <select id="ord-language">
          <option value="en"${(o.language||'en')==='en'?' selected':''}>🇬🇧 Inglese</option>
          <option value="it"${o.language==='it'?' selected':''}>🇮🇹 Italiano</option>
        </select>
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
  const newCarrier=(document.getElementById('ord-carrier')?.value||'').trim();
  const newTracking=(document.getElementById('ord-tracking')?.value||'').trim();
  const newTrackingUrl=(document.getElementById('ord-tracking-url')?.value||'').trim();
  const newEmail=(document.getElementById('ord-email')?.value||'').trim();
  const newPhone=(document.getElementById('ord-phone')?.value||'').trim();
  const newAddress=(document.getElementById('ord-address')?.value||'').trim();
  const newShippingType=gv('ord-shipping-type')||'';
  const newDestCountry=gv('ord-dest-country')||'';
  const newLanguage=gv('ord-language')||'en';
  const newShipmentCode=(document.getElementById('ord-shipment-code')?.value||'').trim().toUpperCase();
  const newAmount=(document.getElementById('ord-amount')?.value||'').trim();
  const newCurrency=(document.getElementById('ord-currency')?.value||'').trim();
  const note=(document.getElementById('ord-note')?.value||'').trim();
  const sendEmail=document.getElementById('ord-send-email')?.checked;

  if(newAmount!==''&&!isNaN(parseFloat(newAmount))) o.amount=parseFloat(newAmount);
  if(newCurrency) o.currency=newCurrency.toUpperCase();
  if(newEmail) o.customerEmail=newEmail;
  o.carrier=newCarrier||'';
  if(newTracking&&!o.trackingNumber){
    o.trackingNumber=newTracking;
    if(!o.shippingDate) o.shippingDate=Date.now();
  } else if(newTracking){
    o.trackingNumber=newTracking;
  }
  o.trackingUrl=newTrackingUrl||'';
  o.language=newLanguage;
  if(newPhone) o.customerPhone=newPhone;
  if(newAddress) o.shippingAddress=newAddress;
  o.shippingType=newShippingType||null;
  o.destCountry=newDestCountry||null;
  if(newShipmentCode) o.shipmentCode=newShipmentCode;

  const statusChanged=newStatus!==o.status;
  if(statusChanged){
    o.status=newStatus;
    o.statusHistory=o.statusHistory||[];
    o.statusHistory.push({status:newStatus, date:Date.now(), note:note||''});
    if(['spedito','in_transito'].includes(newStatus)&&!o.shippingDate) o.shippingDate=Date.now();
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

  const isIt=(o.language||'en')==='it';
  const nome=o.customerName.split(/\s+/)[0]||o.customerName;
  const track17Url=o.trackingNumber?`https://t.17track.net/en#nums=${encodeURIComponent(o.trackingNumber)}`:'';
  const trackRef=o.trackingNumber?(track17Url?`${o.trackingNumber} — ${track17Url}`:o.trackingNumber):'';
  const trackLineIt=trackRef?`Numero tracking: ${trackRef}${o.trackingUrl?`\nTraccia la spedizione: ${o.trackingUrl}`:''}\n`:(o.trackingUrl?`Traccia la spedizione: ${o.trackingUrl}\n`:'');
  const trackLineEn=trackRef?`Tracking number: ${trackRef}${o.trackingUrl?`\nTrack your shipment: ${o.trackingUrl}`:''}\n`:(o.trackingUrl?`Track your shipment: ${o.trackingUrl}\n`:'');
  const trackLine=isIt?trackLineIt:trackLineEn;
  const sig=`Luca Pattaro\nIl Ciliegio — Azienda Agricola\nexport@ilciliegio.com | +39 331 1347899`;

  let subject='', body='';

  switch(o.status){
    case 'spedito':
      if(isIt){
        subject=`Il tuo ordine è partito!${o.trackingNumber?' — Tracking: '+o.trackingNumber:''}`;
        body=`Caro ${nome},\n\nil tuo ordine è stato spedito ed è ora in viaggio verso di te! 🍷\n\n${trackLine}La spedizione dovrebbe arrivare entro 7-10 giorni lavorativi. Ti aggiorneremo ad ogni cambio di stato.\n\nGrazie per aver scelto i nostri vini!\n\n${sig}`;
      } else {
        subject=`Your order has shipped!${o.trackingNumber?' — Tracking: '+o.trackingNumber:''}`;
        body=`Dear ${nome},\n\nyour order has been shipped and is now on its way to you! 🍷\n\n${trackLine}Estimated delivery: 7–10 business days. We'll keep you updated at every status change.\n\nThank you for choosing our wines!\n\n${sig}`;
      }
      break;

    case 'in_transito':
      if(isIt){
        subject=`Aggiornamento spedizione — Il tuo vino è in viaggio`;
        body=`Caro ${nome},\n\nil tuo ordine è in viaggio e procede regolarmente verso la destinazione. 📦\n\n${trackLine}Tempi stimati: 5-10 giorni lavorativi dalla data di spedizione.\n\nA presto!\n\n${sig}`;
      } else {
        subject=`Shipping update — Your wine is on its way`;
        body=`Dear ${nome},\n\nyour order is in transit and on its way to you. 📦\n\n${trackLine}Estimated delivery: 5–10 business days from the shipping date.\n\nSpeak soon!\n\n${sig}`;
      }
      break;

    case 'dogana':
      if(isIt){
        subject=`Il tuo ordine è in fase di sdoganamento`;
        body=`Caro ${nome},\n\nil tuo ordine è attualmente in fase di sdoganamento. Questo processo richiede normalmente 2-5 giorni lavorativi.\n\n${trackLine}Non è richiesto alcun intervento da parte tua — ti aggiorneremo appena l'ordine riparte.\n\nGrazie per la pazienza!\n\n${sig}`;
      } else {
        subject=`Your order is clearing customs`;
        body=`Dear ${nome},\n\nyour order is currently going through customs clearance. This process normally takes 2–5 business days.\n\n${trackLine}No action is required from you — we'll update you as soon as it's on the move again.\n\nThank you for your patience!\n\n${sig}`;
      }
      break;

    case 'consegnato':
      if(isIt){
        subject=`Il tuo ordine è stato consegnato! 🍷 Buona degustazione!`;
        body=`Caro ${nome},\n\nottime notizie! Il tuo ordine è stato consegnato con successo. 🎉\n\nSperiamo che tu possa apprezzare i vini de Il Ciliegio. Se hai domande o feedback, non esitare a contattarci.\n\nSaluti,\n\n${sig}`;
      } else {
        subject=`Your order has been delivered! 🍷 Enjoy!`;
        body=`Dear ${nome},\n\ngreat news! Your order has been successfully delivered. 🎉\n\nWe hope you enjoy the wines from Il Ciliegio. If you have any questions or feedback, don't hesitate to reach out.\n\nBest regards,\n\n${sig}`;
      }
      break;

    case 'problema':
      if(isIt){
        subject=`⚠ Aggiornamento importante sulla tua spedizione`;
        body=`Caro ${nome},\n\nti contatto riguardo al tuo ordine. Purtroppo si è verificato un problema con la spedizione che stiamo già monitorando attivamente.\n\nIl nostro team è al lavoro per risolvere la situazione e ti terremo aggiornato il prima possibile.\n\n${trackLine}\nPer qualsiasi domanda urgente, rispondi direttamente a questa email.\n\n${sig}`;
      } else {
        subject=`⚠ Important update about your shipment`;
        body=`Dear ${nome},\n\nI'm reaching out regarding your order. Unfortunately, an issue has occurred with the shipment and we are actively monitoring the situation.\n\nOur team is working to resolve it and we'll keep you informed as soon as possible.\n\n${trackLine}\nFor any urgent questions, please reply directly to this email.\n\n${sig}`;
      }
      break;

    case 'consegna_fallita':
      if(isIt){
        subject=`⚠ Tentativo di consegna non riuscito — potrebbe servire un'azione`;
        body=`Caro ${nome},\n\nil corriere ha provato a consegnare il tuo ordine, ma la consegna non è andata a buon fine (ricorda che per le spedizioni di vino è richiesta la firma di un adulto maggiorenne).\n\n${trackLine}Normalmente il corriere riproverà automaticamente. Se preferisci, puoi anche riprogrammare la consegna o ritirare il pacco presso un punto UPS vicino a te direttamente dal link di tracking qui sopra.\n\nSe il pacco non viene consegnato dopo alcuni tentativi, potrebbe essere reso al mittente — ti consigliamo quindi di agire il prima possibile.\n\n${sig}`;
      } else {
        subject=`⚠ Delivery attempt unsuccessful — action may be needed`;
        body=`Dear ${nome},\n\nthe carrier attempted to deliver your order, but the delivery was not completed (please remember that a signature from an adult aged 21+ is required for wine shipments).\n\n${trackLine}The carrier will normally attempt delivery again automatically. If you prefer, you can also reschedule the delivery or arrange pickup at a nearby UPS access point directly through the tracking link above.\n\nIf the package is not delivered after a few attempts, it may be returned to us — so we recommend acting soon if possible.\n\n${sig}`;
      }
      break;

    default:
      return;
  }

  try{
    const res=await fetch('https://api.brevo.com/v3/smtp/email',{
      method:'POST',
      headers:{'api-key':brv.apiKey,'Content-Type':'application/json','Accept':'application/json'},
      body:JSON.stringify({
        sender:{name:brv.senderName||'Il Ciliegio — Azienda Agricola', email:brv.senderEmail||'luca@sienawine.it'},
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
