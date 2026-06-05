/* ═══ DASHBOARD ═══ */

function renderStats(){
  const s={total:0,new:0,sent:0,followup:0,replied:0,client:0};
  (isClienti()?dbC:db).contacts.forEach(c=>{s.total++;s[c.status]=(s[c.status]||0)+1;});
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
  const adb=isClienti()?dbC:db;
  const map={};
  adb.contacts.forEach(c=>{
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
  const adb=isClienti()?dbC:db;
  const map={};
  adb.contacts.filter(c=>(c.region||'').trim()===region).forEach(c=>{
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
        <button class="btn" style="font-size:11px;padding:2px 8px;flex-shrink:0;margin-left:4px" onclick="event.stopPropagation();openResearchModal('${esc(c)}')" title="Analisi AI importatori">🔬</button>
      </div>`).join('')
    : '<div class="empty" style="font-size:12px">Nessun paese</div>';
}

function renderCCChart(){
  const map={};
  (isClienti()?dbC:db).contacts.forEach(c=>{if(c.country)map[c.country]=(map[c.country]||0)+1;});
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
      <button class="btn" style="font-size:11px;padding:2px 8px;flex-shrink:0;margin-left:4px" onclick="event.stopPropagation();openResearchModal('${esc(c)}')" title="Analisi AI importatori">🔬</button>
    </div>`).join('')
    :'<div class="empty" style="font-size:12px">Nessun dato</div>';
}

function renderPipeline(){
  const order=['new','sent','followup','replied','client','cold'];
  const cm={new:'blue-bg blue-tx',sent:'amber-bg amber-tx',followup:'pink-bg pink-tx',
    replied:'green-bg green-tx',client:'teal-bg teal-tx',cold:'gray-bg gray-tx'};
  const map={};(isClienti()?dbC:db).contacts.forEach(c=>{map[c.status]=(map[c.status]||0)+1;});
  const tot=(isClienti()?dbC:db).contacts.length||1;
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

/* ── CONTACTS LIST ── */

// Converte stringhe come "1,234" o "$27.64M" o "42" in numero per il sort

function updateBadges(){
  document.getElementById('ct-n').textContent=(isClienti()?dbC:db).contacts.length;
  const adb=isClienti()?dbC:db;
  let emailCount=0;
  adb.contacts.forEach(c=>{
    if(c.brevoEvents?.length) emailCount+=c.brevoEvents.length;
    else if(c.status==='sent'||c.status==='followup') emailCount++;
  });
  document.getElementById('fu-n').textContent=emailCount;
}