/* ═══ REMINDERS ═══ */

const REM_PATH = 'data/email-reminders-templates.json';

const REMINDER_SCHEDULE = [
  { type: 'order_received', label: 'Conferma ricezione ordine', days: null, types: ['standard','express'], trigger: 'Ordine importato da Gmail (entro 7gg)' },
  { type: 'day0',       label: 'Conferma spedizione',           days: 0,    types: ['standard','express'], trigger: 'Data spedizione impostata da Fieramente/MBE' },
  { type: 'day10',      label: 'Reminder 10 giorni',            days: 10,   types: ['standard','express'], trigger: '10 giorni dalla data di spedizione' },
  { type: 'day20',      label: 'Reminder 20 giorni',            days: 20,   types: ['standard'],           trigger: '20 giorni dalla spedizione — solo Standard' },
  { type: 'in_consegna',label: 'In consegna — dogana superata', days: null, types: ['standard','express'], trigger: 'Fieramente status → From US warehouse / Picked up by UPS (4/9)' },
  { type: 'consegnato', label: 'Ordine consegnato',             days: null, types: ['standard','express'], trigger: 'Fieramente status → Delivered (5)' },
  { type: 'dogana',     label: 'In dogana',                     days: null, types: ['standard','express'], trigger: 'Fieramente status → Customs clearance (3/8)' },
  { type: 'problema',   label: 'Problema spedizione',           days: null, types: ['standard','express'], trigger: 'Fieramente/MBE status → Problema' },
];

/* ─ Carica template da GitHub ─ */
async function loadReminderTemplates(){
  const{token,owner,repo}=ghs;
  if(!token||!owner||!repo) return;
  const url=`https://api.github.com/repos/${owner}/${repo}/contents/${REM_PATH}`;
  try{
    const r=await fetch(url,{headers:{'Authorization':`token ${token}`,'Accept':'application/vnd.github.v3+json'}});
    if(r.status===404) return;
    if(!r.ok) return;
    const d=await r.json();
    ghSha.reminders=d.sha;
    const raw=d.content.replace(/\n/g,'');
    dbRemT=JSON.parse(decodeURIComponent(Array.from(atob(raw),c=>'%'+c.charCodeAt(0).toString(16).padStart(2,'0')).join('')));
  }catch(e){ console.warn('loadReminderTemplates:',e); }
}

/* ─ Salva template su GitHub ─ */
async function saveReminderTemplates(){
  const{token,owner,repo}=ghs;
  if(!token||!owner||!repo){ toast('⚙ Configura GitHub nelle Impostazioni'); return; }
  const url=`https://api.github.com/repos/${owner}/${repo}/contents/${REM_PATH}`;
  const hd={'Authorization':`token ${token}`,'Content-Type':'application/json','Accept':'application/vnd.github.v3+json'};
  try{
    if(!ghSha.reminders){
      const r=await fetch(url,{headers:hd});
      if(r.ok) ghSha.reminders=(await r.json()).sha;
    }
    const jsonStr=JSON.stringify(dbRemT,null,2);
    const bytes=new TextEncoder().encode(jsonStr);
    const b64=btoa(Array.from(bytes,b=>String.fromCharCode(b)).join(''));
    const body={message:`Template reminder aggiornati — ${new Date().toLocaleString('it-IT')}`,content:b64};
    if(ghSha.reminders) body.sha=ghSha.reminders;
    const res=await fetch(url,{method:'PUT',headers:hd,body:JSON.stringify(body)});
    if(res.ok){
      ghSha.reminders=(await res.json()).content.sha;
      toast('✓ Template salvati su GitHub');
    } else {
      toast('⚠ Errore salvataggio: '+res.status);
    }
  }catch(e){ toast('⚠ '+e.message); }
}

/* ─ Stato reminder per un ordine (chiamata da openOrdineDetail) ─ */
function getReminderStatusHtml(order){
  const sentMap={};
  for(const e of (order.emailsSent||[])){
    if(!sentMap[e.type]) sentMap[e.type]=e;
  }

  const stype=order.shippingType;
  const sd=order.shippingDate;
  const daysSince=sd?(Date.now()-sd)/86400000:null;
  const status=order.status||'';

  const rows=REMINDER_SCHEDULE.map(r=>{
    if(sentMap[r.type]){
      const d=new Date(sentMap[r.type].sentAt).toLocaleDateString('it-IT',{day:'numeric',month:'short'});
      return _remRow(r.label,`✓ ${d}`,r.trigger,'var(--green)');
    }

    if(r.type==='order_received'){
      return _remRow(r.label,'prossima esecuzione script',r.trigger,'var(--amber)');
    }

    if(r.type==='day0'){
      if(!sd) return _remRow(r.label,'in attesa spedizione',r.trigger,'var(--text3)');
      return _remRow(r.label,'prossima esecuzione script',r.trigger,'var(--amber)');
    }

    if(r.days===null){
      if(['consegnato','annullato'].includes(status)) return _remRow(r.label,'non applicabile',r.trigger,'var(--text3)');
      return _remRow(r.label,'al cambio stato',r.trigger,'var(--text3)');
    }

    if(['consegnato','annullato'].includes(status)) return _remRow(r.label,'non necessaria',r.trigger,'var(--text3)');
    if(!stype) return _remRow(r.label,'⚠ tipo spedizione mancante',r.trigger,'var(--red)');
    if(!r.types.includes(stype)) return _remRow(r.label,`solo Standard (questo: ${stype})`,r.trigger,'var(--text3)');
    if(!sd) return _remRow(r.label,'in attesa spedizione',r.trigger,'var(--text3)');
    const rem=r.days-daysSince;
    if(rem<=0) return _remRow(r.label,'prossima esecuzione script',r.trigger,'var(--amber)');
    return _remRow(r.label,`tra ${Math.ceil(rem)} giorni`,r.trigger,'var(--text3)');
  }).join('');

  return `<div class="divhr"></div>
    <div style="font-size:11px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Reminder email</div>
    <div style="background:var(--bg2);border-radius:var(--r);padding:10px 14px">${rows}</div>`;
}

function _remRow(label,status,trigger,color){
  return `<div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid var(--brd2)">
    <div>
      <div style="font-size:12px;color:var(--text2)">${label}</div>
      <div style="font-size:10px;color:var(--text3);font-style:italic">${trigger}</div>
    </div>
    <span style="font-size:11px;color:${color};white-space:nowrap;margin-left:8px">${status}</span>
  </div>`;
}

/* ─ Panel template nella sezione ordini ─ */
function renderReminderTemplatesPanel(){
  const el=document.getElementById('reminder-templates-panel');
  if(!el) return;

  const content=REMINDER_SCHEDULE.map((t,i)=>{
    const tpl=dbRemT[t.type]||{};
    return `<div style="${i>0?'margin-top:16px':''}">
      <div style="display:flex;align-items:baseline;gap:8px;margin-bottom:2px">
        <div style="font-size:12px;font-weight:700;color:var(--text)">📧 ${esc(t.label)}</div>
        <div style="font-size:10px;color:var(--text3);font-style:italic">Trigger: ${esc(t.trigger)}</div>
      </div>
      <div class="fg fgf">
        <label style="font-size:11px;color:var(--text2)">Oggetto</label>
        <input id="rtpl-sub-${t.type}" value="${esc(tpl.subject||'')}" style="font-size:12px">
      </div>
      <div class="fg fgf" style="margin-top:4px">
        <label style="font-size:11px;color:var(--text2)">Corpo email <span style="font-weight:400">— placeholder: {nome}, {tracking_line}</span></label>
        <textarea id="rtpl-body-${t.type}" rows="5" style="font-size:12px;width:100%;padding:8px 10px;border:0.5px solid var(--brd2);border-radius:var(--r);background:var(--bg);color:var(--text);font-family:monospace;resize:vertical;line-height:1.5">${esc(tpl.body||'')}</textarea>
      </div>
    </div>`;
  }).join('<div class="divhr" style="margin:14px 0"></div>');

  el.innerHTML=`<div>
    ${content}
    <div style="display:flex;justify-content:flex-end;margin-top:16px">
      <button class="btn btp bts" onclick="doSaveReminderTemplates()">💾 Salva template su GitHub</button>
    </div>
  </div>`;
}

async function doSaveReminderTemplates(){
  for(const t of REMINDER_SCHEDULE){
    const sub =document.getElementById(`rtpl-sub-${t.type}`)?.value||'';
    const body=document.getElementById(`rtpl-body-${t.type}`)?.value||'';
    if(!dbRemT[t.type]) dbRemT[t.type]={};
    dbRemT[t.type].subject=sub;
    dbRemT[t.type].body=body;
  }
  await saveReminderTemplates();
}
