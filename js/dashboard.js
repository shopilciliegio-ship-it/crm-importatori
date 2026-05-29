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

  // Colori per regione
  const rColors={
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

  el.innerHTML = entries.map(([r,n])=>{
    const [bg,tx]=rColors[r]||['var(--bg2)','var(--text2)'];
    const pct=Math.round(n/max*100);
    return `<div class="brow" style="cursor:pointer" onclick="goToContacts({region:'${r.replace(/'/g,"\'")}'})" title="Filtra per ${r}">
      <div class="blbl" style="color:${tx};font-weight:600">${esc(r)}</div>
      <div class="btrk">
        <div style="height:100%;width:${pct}%;background:${bg};border-radius:4px;
          display:flex;align-items:center;padding-left:6px;
          font-size:11px;font-weight:700;color:${tx}">${n}</div>
      </div>
    </div>`;
  }).join('');
}

function renderCCChart(){
  const map={};
  (isClienti()?dbC:db).contacts.forEach(c=>{if(c.country)map[c.country]=(map[c.country]||0)+1;});
  // Tutti i paesi, ordinati per numero di contatti
  const entries=Object.entries(map).sort((a,b)=>b[1]-a[1]);
  const max=entries[0]?.[1]||1;
  const el=document.getElementById('cc');
  el.innerHTML=entries.length?entries.map(([c,n])=>`
    <div class="brow">
      <div class="blbl country-link" onclick="goToContacts({country:'${esc(c)}'})" title="Filtra per ${esc(c)}">${esc(c)}</div>
      <div class="btrk"><div class="bfll" style="width:${Math.round(n/max*100)}%">${n}</div></div>
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