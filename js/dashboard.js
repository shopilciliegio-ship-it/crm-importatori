/* ═══ DASHBOARD ═══ */

function activeContacts(){
  return isClienti() ? dbC.contacts.filter(c=>c.shippable!==false) : db.contacts;
}

function renderStats(){
  const s={total:0,new:0,sent:0,followup:0,replied:0,client:0};
  activeContacts().forEach(c=>{s.total++;s[c.status]=(s[c.status]||0)+1;});
  document.getElementById('stats').innerHTML=`
    <div class="stat" style="cursor:default"><div class="sl">Totale</div><div class="sv">${s.total}</div></div>
    <div class="stat stat-link" onclick="goToContacts({status:'new'})" title="Vai alla lista"><div class="sl">Da contattare</div><div class="sv bl">${s.new||0}</div></div>
    <div class="stat stat-link" onclick="goToContacts({status:'followup'})" title="Vai alla lista"><div class="sl">In attesa (email)</div><div class="sv am">${(s.sent||0)+(s.followup||0)}</div></div>
    <div class="stat stat-link" onclick="goToContacts({status:'replied'})" title="Vai alla lista"><div class="sl">Risposte</div><div class="sv gr">${s.replied||0}</div></div>
    <div class="stat stat-link" onclick="goToContacts({status:'client'})" title="Vai alla lista"><div class="sl">Clienti</div><div class="sv co">${s.client||0}</div></div>`;
}

const REGION_COLORS={
  'Sud America':  ['var(--amber-bg)','var(--amber-tx)'],
  'Oceania':      ['var(--teal-bg)','var(--teal-tx)'],
  'Europa':       ['var(--blue-bg)','var(--blue-tx)'],
  'Africa':       ['var(--coral-bg)','var(--coral-tx)'],
  'Asia':         ['var(--pink-bg)','var(--pink-tx)'],
  'Nord America': ['var(--green-bg)','var(--green-tx)'],
  'Medio Oriente':['var(--amber-bg)','var(--amber-tx)'],
  'Scandinavia':  ['var(--blue-bg)','var(--blue-tx)'],
  'Caraibi':      ['var(--teal-bg)','var(--teal-tx)'],
};

function renderRegionChart(){
  const el=document.getElementById('rc');
  if(!el) return;
  const map={};
  activeContacts().forEach(c=>{
    const r=(c.region||'').trim()||'—';
    map[r]=(map[r]||0)+1;
  });
  const entries=Object.entries(map).sort((a,b)=>b[1]-a[1]);
  const max=entries[0]?.[1]||1;
  if(!entries.length){el.innerHTML='<div class="empty" style="font-size:12px">Nessun dato</div>';return;}

  el.innerHTML = entries.map(([r,n])=>{
    const [bg,tx]=REGION_COLORS[r]||['var(--bg2)','var(--text2)'];
    const pct=Math.round(n/max*100);
    // Clic su regione → mostra paesi di quella regione nel pannello di destra
    return `<div class="brow" style="cursor:pointer" onclick="showCountriesForRegion('${r.replace(/'/g,"\\'")}')">
      <div class="blbl" style="color:${tx};font-weight:600">${esc(r)}</div>
      <div class="btrk">
        <div style="height:100%;width:${pct}%;background:${bg};border-radius:4px;
          display:flex;align-items:center;padding-left:6px;
          font-size:11px;font-weight:700;color:${tx}">${n}</div>
      </div>
    </div>`;
  }).join('');
}

function showCountriesForRegion(region){
  const el=document.getElementById('cc');
  if(!el) return;
  const map={};
  activeContacts().filter(c=>(c.region||'').trim()===region).forEach(c=>{
    if(c.country) map[c.country]=(map[c.country]||0)+1;
  });
  const entries=Object.entries(map).sort((a,b)=>b[1]-a[1]);
  const max=entries[0]?.[1]||1;
  const [bg,tx]=REGION_COLORS[region]||['var(--bg2)','var(--text2)'];

  // Aggiorna titolo pannello
  const titleEl=el.closest('.card')?.querySelector('.st');
  if(titleEl) titleEl.innerHTML=`<span style="cursor:pointer;color:var(--text2)" onclick="renderCCChart();this.closest('.card').querySelector('.st').textContent='Per paese'">← Paesi</span>
    &nbsp;<span style="background:${bg};color:${tx};padding:1px 8px;border-radius:10px;font-size:11px;font-weight:700">${esc(region)}</span>`;

  el.innerHTML=entries.length
    ? entries.map(([c,n])=>`
      <div class="brow">
        <div class="blbl country-link" onclick="goToContacts({country:'${esc(c)}'})" title="Apri contatti di ${esc(c)}">${esc(c)}${_countryResearchBadge(c)}</div>
        <div class="btrk"><div class="bfll" style="width:${Math.round(n/max*100)}%">${n}</div></div>
        ${_countryQueueFlag(c)}
      </div>`).join('')
    : '<div class="empty" style="font-size:12px">Nessun paese</div>';
}

function renderCCChart(){
  const map={};
  activeContacts().forEach(c=>{if(c.country)map[c.country]=(map[c.country]||0)+1;});
  const entries=Object.entries(map).sort((a,b)=>b[1]-a[1]);
  const max=entries[0]?.[1]||1;
  const el=document.getElementById('cc');
  // Ripristina titolo "Per paese" se era stato cambiato da showCountriesForRegion
  const titleEl=el.closest('.card')?.querySelector('.st');
  if(titleEl) titleEl.textContent='Per paese';
  el.innerHTML=entries.length?entries.map(([c,n])=>`
    <div class="brow">
      <div class="blbl country-link" onclick="goToContacts({country:'${esc(c)}'})" title="Apri contatti di ${esc(c)}">${esc(c)}${_countryResearchBadge(c)}</div>
      <div class="btrk"><div class="bfll" style="width:${Math.round(n/max*100)}%">${n}</div></div>
      ${_countryQueueFlag(c)}
    </div>`).join('')
    :'<div class="empty" style="font-size:12px">Nessun dato</div>';
}

function renderPipeline(){
  const order=['new','sent','followup','replied','client','cold'];
  const cm={new:'blue-bg blue-tx',sent:'amber-bg amber-tx',followup:'pink-bg pink-tx',
    replied:'green-bg green-tx',client:'teal-bg teal-tx',cold:'gray-bg gray-tx'};
  const ac=activeContacts();
  const map={};ac.forEach(c=>{map[c.status]=(map[c.status]||0)+1;});
  const tot=ac.length||1;
  document.getElementById('pipeline').innerHTML='<div style="display:flex;gap:6px;align-items:flex-end;height:70px">'+
    order.map(s=>{
      const n=map[s]||0,h=Math.max(4,Math.round(n/tot*100));
      const[bg,tx]=cm[s].split(' ');
      return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:3px">
        <div style="font-size:11px;font-weight:700;color:var(--${tx})">${n}</div>
        <div style="width:100%;height:${h}%;min-height:4px;background:var(--${bg});border-radius:4px 4px 0 0"></div>
        <div style="font-size:10px;color:var(--text2);text-align:center;line-height:1.2">${SM[s].l.replace(' ','<br>')}</div>
      </div>`;
    }).join('')+'</div>';
}

/* ── RESEARCH COUNTRY BADGE ── */

function _countryResearchBadge(country) {
  if (isClienti()) return '';
  const contacts = db.contacts.filter(c => c.country === country && c.research);
  if (!contacts.length) return '';
  const total = db.contacts.filter(c => c.country === country).length;
  const si = contacts.filter(c => c.research.raccomandato === 'si').length;
  const avgAff = Math.round(contacts.reduce((s,c) => s + (c.research.affidabilita||0), 0) / contacts.length);
  const stars = '★'.repeat(avgAff);
  const [bg,tx] = si > 0 ? ['#e8f5e9','#2e7d32'] : ['#f5f5f5','#666'];
  return `<span style="font-size:10px;background:${bg};color:${tx};padding:1px 5px;border-radius:10px;margin-left:5px;font-weight:700" title="${contacts.length}/${total} analizzati, ${si} raccomandati">${stars} ${si}✓</span>`;
}

/* ── CODA RICERCA AI AUTOMATICA (server-side, GitHub Actions) ── */
// data/research-config.json: {queue:[paesi in ordine FIFO], dailyLimit}
// Lo script scripts/research_ai.py processa un paese alla volta ogni mattina
// e salva i risultati come override — qui gestiamo solo il flag di selezione.

function _countryResearchProgress(country){
  const contacts = db.contacts.filter(c => c.country === country);
  const done = contacts.filter(c => c.research).length;
  return { done, total: contacts.length };
}

function _countryQueueFlag(country){
  if (isClienti()) return '';
  const inQueue = (rschCfg.queue||[]).includes(country);
  const { done, total } = _countryResearchProgress(country);
  const allDone = inQueue && total > 0 && done >= total;
  const icon  = !inQueue ? '⚪' : (allDone ? '🟢' : '🟡');
  const title = !inQueue
    ? 'Aggiungi alla coda di ricerca AI automatica'
    : allDone
      ? `Ricerca completata (${done}/${total}) — clic per togliere dalla coda`
      : `In coda di ricerca AI — ${done}/${total} analizzati — clic per togliere dalla coda`;
  return `<button class="btn" style="font-size:13px;padding:2px 6px;flex-shrink:0;margin-left:4px;background:none;border:none;cursor:pointer"
    onclick="event.stopPropagation();toggleResearchQueue('${esc(country)}',this)" title="${esc(title)}">${icon}</button>`;
}

async function toggleResearchQueue(country, btn){
  rschCfg.queue = rschCfg.queue || [];
  const idx = rschCfg.queue.indexOf(country);
  if (idx >= 0) {
    rschCfg.queue.splice(idx, 1);
    toast(`${country} rimosso dalla coda di ricerca AI`);
  } else {
    rschCfg.queue.push(country);
    toast(`${country} aggiunto alla coda di ricerca AI 🟡 — verrà processato automaticamente ogni mattina`);
  }
  await pushResearchConfigGH();
  if (btn) btn.outerHTML = _countryQueueFlag(country);
  renderResearchBanner();
}

async function loadResearchConfigFromGH(){
  const{token,owner,repo}=ghs;
  if(!token||!owner||!repo){ renderResearchBanner(); return; }
  const url=`https://api.github.com/repos/${owner}/${repo}/contents/data/research-config.json`;
  try{
    const r=await fetch(url,{headers:{'Authorization':`token ${token}`,'Accept':'application/vnd.github.v3+json'}});
    if(r.status===404){ renderResearchBanner(); return; }
    if(!r.ok) return;
    const d=await r.json();
    ghSha.researchConfig=d.sha;
    const raw=d.content.replace(/\n/g,'');
    let jsonStr;
    try{ jsonStr=decodeURIComponent(Array.from(atob(raw),c=>'%'+c.charCodeAt(0).toString(16).padStart(2,'0')).join('')); }
    catch(e){ jsonStr=atob(raw); }
    rschCfg=JSON.parse(jsonStr);
    if(!Array.isArray(rschCfg.queue)) rschCfg.queue=[];
    renderResearchBanner();
  }catch(e){ console.warn('loadResearchConfigFromGH:',e); }
}

async function pushResearchConfigGH(){
  const{token,owner,repo}=ghs;
  if(!token||!owner||!repo) return;
  const path='data/research-config.json';
  const url=`https://api.github.com/repos/${owner}/${repo}/contents/${path}`;
  const hd={'Authorization':`token ${token}`,'Content-Type':'application/json','Accept':'application/vnd.github.v3+json'};
  try{
    if(!ghSha.researchConfig){
      const r=await fetch(url,{headers:hd});
      if(r.ok) ghSha.researchConfig=(await r.json()).sha;
    }
    const bytes=new TextEncoder().encode(JSON.stringify(rschCfg,null,2));
    const b64=btoa(Array.from(bytes,b=>String.fromCharCode(b)).join(''));
    const body={message:`Coda ricerca AI — ${new Date().toLocaleString('it-IT')}`,content:b64};
    if(ghSha.researchConfig) body.sha=ghSha.researchConfig;
    const res=await fetch(url,{method:'PUT',headers:hd,body:JSON.stringify(body)});
    if(res.ok) ghSha.researchConfig=(await res.json()).content.sha;
  }catch(e){ console.warn('pushResearchConfigGH:',e); }
}

function renderResearchBanner(){
  const el=document.getElementById('research-queue-banner');
  if(!el) return;
  if(isClienti()){ el.innerHTML=''; return; }
  const queue=rschCfg.queue||[];
  if(!queue.length){
    el.innerHTML=`<div class="card" style="padding:10px 16px;margin-bottom:10px;background:var(--bg2);font-size:13px;color:var(--text2)">
      📭 Nessuna ricerca AI in coda — clicca la bandierina ⚪ accanto a un paese in "Per paese" per avviare ricerche automatiche giornaliere.
    </div>`;
    return;
  }
  let active=null, queuedAfter=0;
  for(const country of queue){
    const {done,total}=_countryResearchProgress(country);
    if(done<total){
      if(!active) active={country,done,total};
      else queuedAfter++;
    }
  }
  if(!active){
    el.innerHTML=`<div class="card" style="padding:10px 16px;margin-bottom:10px;background:var(--green-bg);font-size:13px;color:var(--green-tx);font-weight:600">
      ✅ Tutte le ricerche AI in coda sono complete — seleziona altri paesi per una nuova ricerca
    </div>`;
    return;
  }
  el.innerHTML=`<div class="card" style="padding:10px 16px;margin-bottom:10px;background:var(--amber-bg);font-size:13px;color:var(--amber-tx)">
    🔬 Ricerca <strong>${esc(active.country)}</strong>: ${active.done} di ${active.total} in corso
    ${queuedAfter>0?`&nbsp;·&nbsp;<strong>${queuedAfter}</strong> altre ricerche AI in coda`:''}
  </div>`;
}

/* ── CONTACTS LIST ── */

// Converte stringhe come "1,234" o "$27.64M" o "42" in numero per il sort

function updateBadges(){
  document.getElementById('ct-n').textContent=isClienti()?dbC.contacts.filter(c=>c.shippable!==false).length:db.contacts.length;
  const archEl=document.getElementById('arch-n');
  if(archEl) archEl.textContent=dbC.contacts.filter(c=>c.shippable===false).length;
  const adb=isClienti()?dbC:db;
  let emailCount=0;
  adb.contacts.forEach(c=>{
    if(c.brevoEvents?.length) emailCount+=c.brevoEvents.length;
    else if(c.status==='sent'||c.status==='followup') emailCount++;
  });
  document.getElementById('fu-n').textContent=emailCount;
}