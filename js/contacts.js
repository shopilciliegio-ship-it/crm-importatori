/* ═══ CONTACTS ═══ */

let _cliOffset = 0;
let _impOffset = 0;
const CLI_PAGE_SIZE = 100;
const IMP_PAGE_SIZE = 100;

const BWI_BADGE_MAX_AGE_MS = 4 * 30 * 24 * 60 * 60 * 1000; // 4 mesi

// Il badge NUOVO/AGGIORNATO scompare da solo dopo 4 mesi dall'import/aggiornamento BWI
// (non più legato all'invio della prima email)
function bwiBadgeStatus(c){
  if(c.bwiStatus==='new' && c.bwiImportedAt && (Date.now()-c.bwiImportedAt)<BWI_BADGE_MAX_AGE_MS) return 'new';
  if(c.bwiStatus==='updated' && c.bwiUpdatedAt && (Date.now()-c.bwiUpdatedAt)<BWI_BADGE_MAX_AGE_MS) return 'updated';
  return null;
}

function _loadMoreContacts(isClienti){
  const fullList = getFiltered();
  const pageSize = isClienti ? CLI_PAGE_SIZE : IMP_PAGE_SIZE;
  const offset   = isClienti ? _cliOffset : _impOffset;
  const batch    = fullList.slice(offset, offset + pageSize);
  if(isClienti) _cliOffset += batch.length; else _impOffset += batch.length;
  const cardsEl = document.getElementById('cl-cards');
  if(cardsEl) cardsEl.insertAdjacentHTML('beforeend', batch.map(c=>crow(c)).join(''));
  const newOff = isClienti ? _cliOffset : _impOffset;
  const lm = document.getElementById('load-more-wrap');
  if(lm){
    if(fullList.length > newOff){
      const fn = isClienti ? 'loadMoreClienti()' : 'loadMoreImportatori()';
      lm.innerHTML = `<button class="btn" onclick="${fn}" style="font-size:13px">
        Carica altri ${Math.min(pageSize, fullList.length-newOff)} &nbsp;·&nbsp; ${fullList.length-newOff} rimanenti
      </button>`;
    } else {
      lm.remove();
    }
  }
}

function loadMoreClienti(){    _loadMoreContacts(true);  }
function loadMoreImportatori(){ _loadMoreContacts(false); }

function updateFilters(){
  if(isClienti()){
    // ── FILTRI CLIENTI: regione / paese / verifica / situazione ──

    // Regione (stesso comportamento importatori: sr → cascade → sc)
    const sr=document.getElementById('sr');const rv=sr?.value||'';
    const regions=[...new Set(dbC.contacts.map(c=>(c.region||'').trim()).filter(Boolean))].sort();
    if(sr) sr.innerHTML='<option value="">Tutte le regioni</option>'+regions.map(r=>`<option value="${esc(r)}"${rv===r?' selected':''}>${esc(r)}</option>`).join('');

    // Nascondi prodotti, mostra verifica
    const sp=document.getElementById('sp');
    if(sp) sp.style.display='none';
    const sv=document.getElementById('sv');
    if(sv) sv.style.display='';

    updateCountryFilter();
    return;
  }

  // ── IMPORTATORI: popola Tipo, nascondi verifica ──
  const sv=document.getElementById('sv');
  if(sv) sv.style.display='none';
  const spEl=document.getElementById('sp');
  if(spEl){
    spEl.style.display='';
    const pv=spEl.value;
    // Tipi predefiniti (sempre presenti anche se non ancora nel DB)
    const DEFAULT_TYPES=[
      'Importer','Distributor','Wholesaler','Retailer',
      'Online Store','Restaurant','Hotel','Bar','Supermarket',
      'Wine Shop','Agent','Broker','Producer','Other'
    ];
    // Merge con i tipi effettivamente presenti nel DB
    const typeSet=new Set(DEFAULT_TYPES);
    db.contacts.forEach(c=>{
      (c.type||'').split(',').map(t=>t.trim()).filter(Boolean).forEach(t=>typeSet.add(t));
    });
    const types=[...typeSet].sort();
    spEl.innerHTML='<option value="">Tutti i tipi</option>'+
      types.map(t=>`<option value="${esc(t)}"${pv===t?' selected':''}>${esc(t)}</option>`).join('');
  }

  // ── FILTRI IMPORTATORI ──
  const sr=document.getElementById('sr');const rv=sr?.value||'';
  const regions=[...new Set(db.contacts.map(c=>(c.region||'').trim()).filter(Boolean))].sort();
  if(sr) sr.innerHTML='<option value="">Tutte le regioni</option>'+regions.map(r=>`<option value="${esc(r)}"${rv===r?' selected':''}>${esc(r)}</option>`).join('');
  updateCountryFilter();

}

function updateCountryFilter(){
  const sc=document.getElementById('sc');if(!sc)return;
  const cv=sc.value;
  const selectedRegion=document.getElementById('sr')?.value||'';

  // Se c'è una regione selezionata, mostra solo i paesi di quella regione
  const source = selectedRegion
    ? (isClienti()?dbC:db).contacts.filter(c=>(c.region||'').trim()===selectedRegion)
    : (isClienti()?dbC:db).contacts;

  const countries=[...new Set(
    source.map(c=>(c.country||'').trim())
      .filter(c=>c.length>0&&c.length<=50&&!/^\d/.test(c))
  )].sort();

  sc.innerHTML='<option value="">Tutti i paesi</option>'+
    countries.map(c=>`<option value="${esc(c)}"${cv===c?' selected':''}>${esc(c)}</option>`).join('');

  // Se il paese selezionato non è più disponibile, resettalo
  if(cv && !countries.includes(cv)){
    sc.value='';
    renderContacts();
  }
}


/* ── NAVIGAZIONE RAPIDA da Dashboard ── */

function goToContacts({country='',region='',status='',tipo=''}={}){
  const sc=document.getElementById('sc');
  const sr=document.getElementById('sr');
  const ss=document.getElementById('ss');
  const sp=document.getElementById('sp');
  if(sr) sr.value=region;
  updateCountryFilter();
  if(sc) sc.value=country;
  if(sp) sp.value=tipo;
  // "pending" = mostriamo sia sent che followup — usiamo la searchbox
  if(status==='pending'){
    if(ss) ss.value='';
    document.getElementById('sq').value='';
    // Filtro custom: setta un flag temporaneo
    window._pendingFilter=true;
  } else {
    if(ss) ss.value=status;
    window._pendingFilter=false;
    document.getElementById('sq').value='';
  }
  document.getElementById('sp').value='';
  showPage('contacts', document.querySelectorAll('.nb')[1]);
  renderContacts();
}

function getFiltered(){
  const q=(gv('sq')).toLowerCase();
  const country=document.getElementById('sc')?.value||'';
  const regionOrLang=document.getElementById('sr')?.value||'';
  const status=document.getElementById('ss')?.value||'';
  const product=document.getElementById('sp')?.value||'';
  const sortBy=document.getElementById('sortby')?.value||'employees';
  const adb=isClienti()?dbC:db;

  let list = adb.contacts.filter(c=>{
    if(isClienti()){
      const fn=c.firstName||c.nome||''; const ln=c.lastName||c.cognome||'';
      if(q&&!`${fn} ${ln} ${c.email||''} ${c.country||''} ${c.languageBrowser||c.lingua||''}`.toLowerCase().includes(q))return false;
      if(country&&c.country!==country)return false;
      if(regionOrLang&&c.region!==regionOrLang)return false;
      const qual=document.getElementById('squal')?.value||'';
      if(qual&&c.quality!==qual)return false;
      const ship=document.getElementById('sship')?.value||'';
      if(ship==='yes'&&!c.shippable)return false;
      if(ship==='no'&&c.shippable!==false)return false;
      const verifica=document.getElementById('sv')?.value||'';
      if(verifica&&!c.quality&&c.statoEmail!==verifica)return false;
    } else {
      if(q&&!`${c.company} ${c.brandName||''} ${c.email} ${c.country} ${c.city||''} ${(c.contacts||[]).map(x=>x.name).join(' ')}`.toLowerCase().includes(q))return false;
      if(country&&c.country!==country)return false;
      if(regionOrLang&&c.region!==regionOrLang)return false;
      if(product&&!(c.type||'').split(',').map(t=>t.trim()).includes(product))return false;
      const bwiF=document.getElementById('sbwi')?.value||'';
      if(bwiF==='new'&&bwiBadgeStatus(c)!=='new')return false;
      if(bwiF==='updated'&&bwiBadgeStatus(c)!=='updated')return false;
      if(bwiF==='bwi'&&!c.bwiCompId)return false;
      const rschF=document.getElementById('srsch')?.value||'';
      if(rschF==='any'&&!c.research)return false;
      if(rschF==='si'&&c.research?.raccomandato!=='si')return false;
      if(rschF==='forse'&&c.research?.raccomandato!=='forse')return false;
      if(rschF==='no'&&c.research?.raccomandato!=='no')return false;
      if(rschF==='5'&&(c.research?.affidabilita||0)<5)return false;
      if(rschF==='4'&&(c.research?.affidabilita||0)<4)return false;
      if(rschF==='3'&&(c.research?.affidabilita||0)<3)return false;
    }
    if(window._pendingFilter){if(c.status!=='sent'&&c.status!=='followup')return false;}
    else if(status&&c.status!==status)return false;
    return true;
  });

  // Ordina: dal più grande al più piccolo per il campo selezionato
  // I contatti senza dati (parseNumeric = -1) vanno in fondo
  if(!isClienti()){
    list.sort((a,b)=>{
      let va, vb;
      if(sortBy==='research'){
        va = a.research?.affidabilita ?? -1;
        vb = b.research?.affidabilita ?? -1;
      } else {
        va = parseNumeric(a[sortBy]);
        vb = parseNumeric(b[sortBy]);
      }
      if(va === -1 && vb === -1) return 0;
      if(va === -1) return 1;
      if(vb === -1) return -1;
      return vb - va;
    });
  }

  return list;
}

function renderContacts(){
  // Aggiorna label filtri in base al layer
  const srEl=document.querySelector('#sr option[value=""]');
  const spEl=document.querySelector('#sp option[value=""]');
  if(srEl) srEl.textContent='Tutte le regioni';
  if(spEl) spEl.style.display=isClienti()?'none':'';

  // Mostra/nascondi filtro BWI
  const bwiWrap=document.getElementById('sbwi-wrap');
  if(bwiWrap) bwiWrap.style.display=isClienti()?'none':'';

  // Mostra/nascondi filtri clienti (qualità + spedibilità)
  const qualWrap=document.getElementById('squal-wrap');
  if(qualWrap) qualWrap.style.display=isClienti()?'':'none';
  const sortbyEl=document.getElementById('sortby');
  if(sortbyEl) sortbyEl.style.display=isClienti()?'none':'';
  const srschEl=document.getElementById('srsch');
  if(srschEl) srschEl.style.display=isClienti()?'none':'';
  const svEl=document.getElementById('sv');
  if(svEl) svEl.style.display='none'; // rimpiazzato da squal per clienti

  const fullList=getFiltered();
  _cliOffset=0; _impOffset=0; // reset paginazione ad ogni re-render
  const isC=isClienti();
  const pageSize = isC ? CLI_PAGE_SIZE : IMP_PAGE_SIZE;
  const list=fullList.slice(0, pageSize);
  if(isC) _cliOffset=list.length; else _impOffset=list.length;
  const total=(isC?dbC:db).contacts.length;
  const allSelected=list.length>0&&list.every(c=>sel.has(c.id));

  // Badge BWI notifica (solo importatori)
  let bwiNotice='';
  if(!isClienti()){
    const allContacts=(db||{contacts:[]}).contacts;
    const nNew=allContacts.filter(c=>bwiBadgeStatus(c)==='new').length;
    const nUpd=allContacts.filter(c=>bwiBadgeStatus(c)==='updated').length;
    if(nNew||nUpd){
      const parts=[];
      if(nNew) parts.push(`<a href="#" onclick="event.preventDefault();document.getElementById('sbwi').value='new';renderContacts()" style="color:#2e7d32;font-weight:700;text-decoration:none">🆕 ${nNew} nuov${nNew===1?'o':'i'} da BWI</a>`);
      if(nUpd) parts.push(`<a href="#" onclick="event.preventDefault();document.getElementById('sbwi').value='updated';renderContacts()" style="color:#e65100;font-weight:700;text-decoration:none">✏️ ${nUpd} aggiornat${nUpd===1?'o':'i'}</a>`);
      bwiNotice=`<div style="font-size:12px;background:#f0faf0;border:1px solid #c3e6c3;border-radius:8px;padding:6px 12px;display:flex;gap:12px;align-items:center">${parts.join('<span style="color:#aaa">·</span>')}</div>`;
    }
  }

  // Stats bar clienti
  let clientiStats='';
  if(isC && dbC.contacts.length>0){
    const nValid  = dbC.contacts.filter(c=>c.quality==='valid'  &&c.shippable).length;
    const nSusp   = dbC.contacts.filter(c=>c.quality==='suspect'&&c.shippable).length;
    const nWave1  = dbC.contacts.filter(c=>c.waveStatus==='wave1_sent').length;
    const nInv    = dbC.contacts.filter(c=>c.quality==='invalid').length;
    clientiStats=`<div style="font-size:12px;background:#f0faf0;border:1px solid #c3e6c3;border-radius:8px;padding:6px 12px;display:flex;gap:12px;flex-wrap:wrap;margin-bottom:6px">
      <a href="#" style="color:#2e7d32;font-weight:700;text-decoration:none"
        onclick="event.preventDefault();document.getElementById('squal').value='valid';document.getElementById('sship').value='yes';renderContacts()">🟢 ${nValid} pronti</a>
      <a href="#" style="color:#e65100;font-weight:700;text-decoration:none"
        onclick="event.preventDefault();document.getElementById('squal').value='suspect';document.getElementById('sship').value='yes';renderContacts()">🟡 ${nSusp} da verificare</a>
      ${nInv?`<span style="color:#c62828;font-weight:700">🔴 ${nInv} invalidi</span>`:''}
      ${nWave1?`<span style="color:#1565c0;font-weight:700">📧 ${nWave1} wave 1 inviati</span>`:''}
    </div>`;
  }

  document.getElementById('rcnt-wrap').innerHTML=`
    ${bwiNotice}${clientiStats}
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap;${bwiNotice||clientiStats?'margin-top:4px':''}">
      <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:13px;color:var(--text2);user-select:none">
        <input type="checkbox" id="cb-all" ${allSelected&&list.length?'checked':''}
          onchange="toggleSelectAll(this.checked)"
          style="width:16px;height:16px;accent-color:var(--blue);cursor:pointer">
        Seleziona tutti
      </label>
      <span class="rcnt">${fullList.length} contatti${fullList.length!==total?' su '+total+' totali':''}${isC&&fullList.length>_cliOffset?' · mostrati '+_cliOffset:''}</span>
    </div>`;

  // Barra invio massivo (visibile solo se ci sono selezioni)
  const selInList=list.filter(c=>sel.has(c.id));
  const selBar=document.getElementById('sel-bar-wrap');
  if(sel.size>0){
    selBar.innerHTML=`
      <div class="sel-bar">
        <span class="sel-bar-info">✓ ${sel.size} contatt${sel.size===1?'o':'i'} selezionat${sel.size===1?'o':'i'}</span>
        <button class="btn btg bts" onclick="sel.clear();renderContacts()">✕ Deseleziona tutto</button>
        <button class="btn btp bts" onclick="openBulkSend()">✉ Invia a ${sel.size} contatt${sel.size===1?'o':'i'}</button>
      </div>`;
  } else {
    selBar.innerHTML='';
  }

  // Lista contatti con checkbox + paginazione (sia importatori che clienti)
  const el=document.getElementById('cl');
  const curOff = isC ? _cliOffset : _impOffset;
  const hasMore = fullList.length > curOff;
  const loadFn  = isC ? 'loadMoreClienti()' : 'loadMoreImportatori()';
  el.innerHTML=list.length
    ?`<div class="card" id="cl-cards">${list.map(c=>crow(c)).join('')}</div>`
      +(hasMore?`<div id="load-more-wrap" style="text-align:center;padding:12px">
          <button class="btn" onclick="${loadFn}" style="font-size:13px">
            Carica altri ${Math.min(pageSize,fullList.length-curOff)} &nbsp;·&nbsp; ${fullList.length-curOff} rimanenti
          </button></div>`:'')
    :'<div class="card"><div class="empty">Nessun risultato</div></div>';
}

function toggleSelectAll(checked){
  const list=getFiltered();
  if(checked) list.forEach(c=>sel.add(c.id));
  else list.forEach(c=>sel.delete(c.id));
  renderContacts();
}

function toggleSelect(id, e){
  e.stopPropagation();
  if(sel.has(id)) sel.delete(id); else sel.add(id);
  renderContacts();
}

function renderRegistro(){
  const adb=isClienti()?dbC:db;
  const sortBy=document.getElementById('reg-sort')?.value||'date';
  const filterStatus=document.getElementById('reg-filter')?.value||'';
  const stOrd={spam:0,bounced:1,blocked:2,unsubscribed:3,cold:4,client:5,replied:6,sent:7,delivered:8,opened:9,clicked:10};

  // Raggruppa per contatto
  const groups=[];
  adb.contacts.forEach(c=>{
    const evs=[...(c.brevoEvents||[])].sort((a,b)=>(a.sentAt||0)-(b.sentAt||0));
    const legacyEv=(!evs.length&&(c.status==='sent'||c.status==='followup'))
      ?{sentAt:c.lastEmailSent||0,subject:c.lastEmailSubject||'—',noTracking:true,sequenceStep:1}
      :null;
    const allEvs=legacyEv?[legacyEv]:evs;
    if(!allEvs.length) return;
    if(filterStatus&&!allEvs.some(ev=>getBrevoStatus(ev)===filterStatus)) return;
    groups.push({c,evs:allEvs});
  });

  groups.sort((a,b)=>{
    if(sortBy==='status'){
      const sa=getBrevoStatus(a.evs[a.evs.length-1]);
      const sb=getBrevoStatus(b.evs[b.evs.length-1]);
      return (stOrd[sa]??7)-(stOrd[sb]??7);
    }
    return Math.max(...b.evs.map(e=>e.sentAt||0))-Math.max(...a.evs.map(e=>e.sentAt||0));
  });

  const selBar=document.getElementById('reg-sel-bar');
  if(selBar){
    if(regSel.size>0){
      selBar.innerHTML=`<div class="sel-bar">
        <span class="sel-bar-info">✓ ${regSel.size} contatt${regSel.size===1?'o':'i'} selezionat${regSel.size===1?'o':'i'}</span>
        <button class="btn btg bts" onclick="regSel.clear();renderRegistro()">✕ Deseleziona</button>
        <button class="btn btp bts" onclick="openFollowUpFromRegistro()">✉ Follow-up a ${regSel.size}</button>
      </div>`;
    } else { selBar.innerHTML=''; }
  }

  const el=document.getElementById('fl');
  if(!groups.length){
    el.innerHTML='<div class="card"><div class="empty">Nessuna email inviata 🚀</div></div>';
    return;
  }

  el.innerHTML=`<div class="card">${groups.map(({c,evs})=>{
    const name=isClienti()?`${c.nome||''} ${c.cognome||''}`.trim():(c.company||'');
    const lastEv=evs[evs.length-1];
    const lastSt=getBrevoStatus(lastEv);
    const isTerminal=['replied','client','cold','blacklisted'].includes(lastSt);
    const sk=c.id;
    const checked=regSel.has(sk);
    const lastSk=c.id+'|'+(lastEv.messageId||evs.indexOf(lastEv));

    // Strip email steps — ogni email è un chip colorato
    const strip=evs.map((ev,idx)=>{
      const st=getBrevoStatus(ev);
      const s=BREVO_STATUS[st]||BREVO_STATUS.sent;
      const icon=STEP_ICON[st]||'📤';
      const stepN=ev.sequenceStep||(idx+1);
      const noTrackStyle=ev.noTracking?'opacity:0.6':'';
      return `<span title="${s.l} — ${fmtDate(ev.sentAt)}"
        style="display:inline-flex;align-items:center;gap:2px;padding:2px 7px;border-radius:10px;
          font-size:11px;font-weight:700;background:${s.bg};color:${s.tx};white-space:nowrap;${noTrackStyle}">
        #${stepN} ${icon} ${fmtDate(ev.sentAt)}
      </span>`;
    }).join(`<span style="color:var(--text3);font-size:10px;padding:0 1px">›</span>`);

    const fuHtml=isTerminal?'':fuIndicator(evs);
    const cur=lastEv.manualStatus||'';
    const manualSel=isTerminal?'':`
      <select onclick="event.stopPropagation()"
        onchange="setManualStatus('${c.id}','${lastSk}',this.value)"
        style="font-size:11px;padding:3px 5px;border-radius:var(--r);border:0.5px solid var(--brd2);background:var(--bg);color:var(--text);cursor:pointer">
        <option value="" ${!cur?'selected':''}>— Stato</option>
        <option value="replied"     ${cur==='replied'?'selected':''}>💬 Risposto</option>
        <option value="client"      ${cur==='client'?'selected':''}>🤝 Cliente</option>
        <option value="cold"        ${cur==='cold'?'selected':''}>❌ Non interessato</option>
        <option value="blacklisted" ${cur==='blacklisted'?'selected':''}>🚫 Blacklist</option>
      </select>`;

    const terminalBadge=(()=>{
      const s=BREVO_STATUS[lastSt];
      return s?`<span class="badge" style="background:${s.bg};color:${s.tx};font-size:11px">${s.l}</span>`:'';
    })();

    return `<div class="cr${checked&&!isTerminal?' selected':''}" onclick="openDetail('${c.id}')"
      style="${isTerminal?'opacity:0.55':''}">
      ${!isTerminal
        ?`<input type="checkbox" class="crow-cb" ${checked?'checked':''}
            onclick="regToggle('${sk}',event)" onchange="regToggle('${sk}',event)">`
        :`<div style="width:17px;flex-shrink:0"></div>`
      }
      <div class="av ${AV[hsh(name)%6]}">${ini(name)}</div>
      <div class="ci">
        <div class="cn">${esc(name)}<span style="font-size:11px;color:var(--text2);font-weight:400;margin-left:6px">${esc(c.country||'')}</span></div>
        <div style="display:flex;align-items:center;flex-wrap:wrap;gap:3px;margin-top:5px">
          ${strip}
          ${fuHtml}
        </div>
      </div>
      <div style="display:flex;flex-direction:column;align-items:flex-end;gap:5px;flex-shrink:0">
        ${isTerminal?terminalBadge:manualSel}
        ${!isTerminal?`<button class="btn bts" style="font-size:11px"
          onclick="event.stopPropagation();openEmailModal('${c.id}')">✉</button>`:''}
      </div>
    </div>`;
  }).join('')}</div>`;
}

function regToggle(sk,e){
  e.stopPropagation();
  if(regSel.has(sk)) regSel.delete(sk); else regSel.add(sk);
  renderRegistro();
}

function openFollowUpFromRegistro(){
  sel.clear();
  regSel.forEach(id=>sel.add(id));
  regSel.clear();
  openBulkSend();
}

function researchBadge(r){
  if(!r) return '';
  const REC=  {si:'#e8f5e9:#2e7d32', forse:'#fff3e0:#e65100', no:'#fce4ec:#c62828'};
  const [bg,tx]=(REC[r.raccomandato]||'var(--bg2):var(--text2)').split(':');
  const stars='★'.repeat(r.affidabilita||0);
  return `<span style="font-size:10px;background:${bg};color:${tx};padding:1px 6px;border-radius:10px;margin-left:4px;font-weight:700">${stars} ${r.raccomandato||'?'}</span>`;
}

function crow(c){
  const checked=sel.has(c.id);
  if(isClienti()){
    const fn=c.firstName||c.nome||'';
    const ln=c.lastName||c.cognome||'';

    // Quality badge — SpottyWifi (quality) o vecchio formato (statoEmail)
    const QMAP={valid:{icon:'🟢',label:'ok',tx:'#2e7d32',bg:'#e8f5e9'},suspect:{icon:'🟡',label:'sospetto',tx:'#e65100',bg:'#fff3e0'},invalid:{icon:'🔴',label:'invalido',tx:'#c62828',bg:'#ffebee'}};
    const qStyle=QMAP[c.quality];
    const SE_MAP={valido:{icon:'✓',tx:'#27500A',bg:'#EAF3DE'},non_valido:{icon:'✗',tx:'#A32D2D',bg:'#FCEBEB'},sospetta:{icon:'⚠',tx:'#633806',bg:'#FAEEDA'},da_verificare:{icon:'?',tx:'#0C447C',bg:'#E6F1FB'},sconosciuto:{icon:'—',tx:'#666',bg:'#eee'}};
    const se=SE_MAP[c.statoEmail||'sconosciuto']||SE_MAP.sconosciuto;
    const qualBadge=qStyle
      ?`<span style="font-size:10px;padding:1px 6px;border-radius:10px;font-weight:700;margin-left:4px;background:${qStyle.bg};color:${qStyle.tx}" title="${(c.qualityFlags||[]).join(', ')}">${qStyle.icon} ${qStyle.label}</span>`
      :`<span style="font-size:10px;padding:1px 6px;border-radius:10px;font-weight:700;margin-left:4px;background:${se.bg};color:${se.tx}">${se.icon} ${esc(c.statoEmail||'—')}</span>`;

    // Country badge (🚫 se non spedibile, grigio se spedibile)
    const countryBadge=c.quality!=null
      ?(c.shippable===false
        ?`<span style="font-size:10px;padding:1px 5px;border-radius:10px;margin-left:4px;background:#f5f5f5;color:#aaa">🚫 ${esc(c.country||'?')}</span>`
        :`<span style="font-size:10px;color:#aaa;margin-left:5px">${esc(c.country||'')}</span>`)
      :`<span style="font-size:10px;color:var(--text2);margin-left:4px">${esc(c.country||'')}</span>`;

    // Wave badge
    const waveLabel={wave1_sent:'📧 Wave 1',wave2_sent:'📧 Wave 2'}[c.waveStatus||'']||'';
    const waveBadge=waveLabel?`<span class="badge" style="background:#e3f2fd;color:#1565c0;font-size:10px;white-space:nowrap">${waveLabel}</span>`:'';

    // Data registrazione
    const regDate=c.registeredAt?new Date(c.registeredAt).toLocaleDateString('it-IT',{day:'2-digit',month:'short',year:'2-digit'}):'';

    return `<div class="cr${checked?' selected':''}" onclick="openDetail('${c.id}')">
      <input type="checkbox" class="crow-cb" ${checked?'checked':''}
        onclick="toggleSelect('${c.id}',event)" onchange="toggleSelect('${c.id}',event)">
      <div class="av ${AV[hsh(fn+ln)%6]}">${ini(fn+' '+ln)}</div>
      <div class="ci">
        <div class="cn">${esc(fn)} <strong>${esc(ln)}</strong>${qualBadge}${countryBadge}</div>
        <div class="cs">${esc(c.email||'')}${regDate?' · '+regDate:''}</div>
      </div>
      ${waveBadge}
    </div>`;
  }
  // ── IMPORTATORE ──
  const firstContact = c.contacts?.[0];
  const nContacts = c.contacts?.length||0;
  const _bwiBadge = bwiBadgeStatus(c);
  const bwiChip = _bwiBadge==='new'
    ? `<span style="font-size:10px;background:#e8f5e9;color:#2e7d32;padding:1px 7px;border-radius:10px;font-weight:700;margin-left:4px">🆕 NUOVO</span>`
    : _bwiBadge==='updated'
    ? `<span style="font-size:10px;background:#fff3e0;color:#e65100;padding:1px 7px;border-radius:10px;font-weight:700;margin-left:4px">✏️ AGG.</span>`
    : '';
  return `<div class="cr${checked?' selected':''}" onclick="openDetail('${c.id}')">
    <input type="checkbox" class="crow-cb" ${checked?'checked':''}
      onclick="toggleSelect('${c.id}',event)"
      onchange="toggleSelect('${c.id}',event)">
    <div class="av ${AV[hsh(c.company)%6]}">${ini(c.company)}</div>
    <div class="ci">
      <div class="cn">${esc(c.company)}${c.brandName&&c.brandName!==c.company?` <span style="font-weight:400;color:var(--text2)">· ${esc(c.brandName)}</span>`:''}${breveEventsBadge(c)}${bwiChip}${researchBadge(c.research)}
        ${nContacts>0?`<span style="font-size:10px;background:var(--blue-bg);color:var(--blue-tx);padding:1px 6px;border-radius:10px;font-weight:700;margin-left:4px">${nContacts} contatt${nContacts===1?'o':'i'}</span>`:''}
      </div>
      <div class="cs">${[c.city||c.country,c.type?.split(',')[0]].filter(Boolean).map(esc).join(' · ')}${c.prodType?' · '+esc(c.prodType.split(',').slice(0,2).join(', ')):''}
        ${(c.employees&&c.employees!=='')||c.sales?`<span style="color:var(--text3);margin-left:4px">${c.employees?'👥 '+esc(c.employees):''}${c.employees&&c.sales?' · ':''}${c.sales?'💰 '+esc(c.sales):''}</span>`:''}
      </div>
    </div>
    <span class="badge ${SM[c.status]?.c||'bn'}">${SM[c.status]?.l||''}</span>
  </div>`;
}

/* ── DETAIL ── */

function openDetail(id){
  const adb=isClienti()?dbC:db;
  const c=adb.contacts.find(x=>x.id===id);if(!c)return;

  // Log attività — usato da entrambi i blocchi
  const log=(c.log||[]).slice(-6).reverse().map(e=>`<div class="log-e"><span style="color:var(--text3);font-size:11px">${new Date(e.ts).toLocaleDateString('it-IT')}</span> — ${esc(e.msg)}</div>`).join('');

  if(isClienti()){
    // ── DETAIL CLIENTE ──
    showModal(`
      <div style="display:flex;align-items:center;gap:13px;margin-bottom:1.25rem">
        <div class="av ${AV[hsh((c.nome||'')+c.cognome)%6]}" style="width:48px;height:48px;font-size:16px">${ini((c.nome||'')+' '+(c.cognome||''))}</div>
        <div style="flex:1">
          <div style="font-size:18px;font-weight:700">${esc(c.nome||'')} ${esc(c.cognome||'')}</div>
          <div style="font-size:13px;color:var(--text2)">${esc(c.email||'')}</div>
        </div>
        <span class="badge ${SM[c.status]?.c||'bn'}">${SM[c.status]?.l||''}</span>
      </div>
      <div>
        ${dr('Email',c.email?`<a href="mailto:${esc(c.email)}">${esc(c.email)}</a>`:'—')}
        ${dr('Paese',c.country||'—')}
        ${dr('Lingua',c.lingua||'—')}
        ${dr('Verifica email',c.statoEmail||'—')}
      </div>
      ${c.notes?`<div class="divhr"></div><div style="font-size:12px;color:var(--text2);font-weight:700;margin-bottom:6px">NOTE</div><div style="font-size:13px;line-height:1.6;white-space:pre-wrap">${esc(c.notes)}</div>`:''}
      ${c.emailsSent?`<div class="divhr"></div>
        <div style="display:flex;gap:12px;font-size:13px">
          <div style="flex:1;background:var(--blue-bg);border-radius:var(--r);padding:10px 14px;text-align:center">
            <div style="font-size:20px;font-weight:700;color:var(--blue-tx)">${c.emailsSent||0}</div>
            <div style="font-size:11px;color:var(--blue-tx)">Email inviate</div>
          </div>
          ${c.lastEmailSent?`<div style="flex:2;background:var(--bg2);border-radius:var(--r);padding:10px 14px">
            <div style="font-size:11px;color:var(--text2);font-weight:700;margin-bottom:3px">ULTIMA EMAIL</div>
            <div style="font-size:12px">${new Date(c.lastEmailSent).toLocaleDateString('it-IT')}</div>
            <div style="font-size:11px;color:var(--text2);margin-top:2px">${esc(c.lastEmailSubject||'')}</div>
          </div>`:''}
        </div>`:''}
      <div class="divhr"></div>
      <div style="font-size:12px;color:var(--text2);font-weight:700;margin-bottom:8px">CAMBIA STATO</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        ${Object.entries(SM).map(([k,v2])=>`<button class="sbtn badge ${v2.c}${c.status===k?' active':''}" onclick="chStatus('${id}','${k}')">${v2.l}</button>`).join('')}
      </div>
      ${log?`<div class="divhr"></div><div style="font-size:12px;color:var(--text2);font-weight:700;margin-bottom:6px">LOG</div>${log}`:''}
      <div class="mf">
        <button class="btn btd bts" onclick="delContact('${id}')">Elimina</button>
        <button class="btn bts" onclick="openAddContact('${id}')">Modifica</button>
        <button class="btn btp bts" onclick="openEmailFromDetail('${id}')">✉ Email</button>
      </div>
    `);
    return;
  }

  // ── DETAIL IMPORTATORE ──
  showModal(`
    <div style="display:flex;align-items:center;gap:13px;margin-bottom:1.25rem">
      <div class="av ${AV[hsh(c.company)%6]}" style="width:48px;height:48px;font-size:16px">${ini(c.company)}</div>
      <div style="flex:1;min-width:0">
        <div style="font-size:18px;font-weight:700">${esc(c.company)}</div>
        ${c.brandName&&c.brandName!==c.company?`<div style="font-size:13px;color:var(--text2)">Brand: ${esc(c.brandName)}</div>`:''}
        <div style="font-size:12px;color:var(--text2);margin-top:2px">${[c.type,c.city,c.country].filter(Boolean).map(esc).join(' · ')}</div>
      </div>
      <span class="badge ${SM[c.status]?.c||'bn'}">${SM[c.status]?.l||''}</span>
    </div>

    <!-- INFO AZIENDA -->
    <div>
      ${dr('Email az.',c.email?`<a href="mailto:${esc(c.email)}">${esc(c.email)}</a>`:'—')}
      ${dr('Telefono',c.phone||'—')}
      ${dr('Sito',c.website?`<a href="${c.website.startsWith('http')?c.website:'https://'+c.website}" target="_blank">${esc(c.website)}</a>`:'—')}
      ${dr('Tipo',c.type||'—')}
      ${dr('Prodotti',c.prodType||'—')}
      ${dr('Paese',c.country||'—')}
      ${dr('Città / Prov.',[c.city,c.state].filter(Boolean).map(esc).join(', ')||'—')}
      ${c.address?dr('Indirizzo',[c.address,c.postalCode].filter(Boolean).map(esc).join(' ')):''}
      ${c.employees?dr('Dipendenti',esc(c.employees)):''}
      ${c.sales?dr('Fatturato',esc(c.sales)):''}
      ${c.founded?dr('Anno fond.',esc(c.founded)):''}
      ${c.regNumber?dr('Nr. Reg.',esc(c.regNumber)):''}
      ${c.compId?dr('ID',esc(c.compId)):''}
    </div>

    <!-- SOCIAL -->
    ${(c.linkedinCo||c.facebook||c.instagram||c.twitter||c.youtube)?`
    <div class="divhr"></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      ${c.linkedinCo?`<a href="${esc(c.linkedinCo)}" target="_blank" style="font-size:12px;padding:4px 10px;border-radius:20px;background:var(--blue-bg);color:var(--blue-tx);font-weight:600;text-decoration:none">LinkedIn</a>`:''}
      ${c.facebook?`<a href="${esc(c.facebook)}" target="_blank" style="font-size:12px;padding:4px 10px;border-radius:20px;background:var(--bg2);color:var(--text2);font-weight:600;text-decoration:none">Facebook</a>`:''}
      ${c.instagram?`<a href="${esc(c.instagram)}" target="_blank" style="font-size:12px;padding:4px 10px;border-radius:20px;background:var(--pink-bg);color:var(--pink-tx);font-weight:600;text-decoration:none">Instagram</a>`:''}
      ${c.twitter?`<a href="${esc(c.twitter)}" target="_blank" style="font-size:12px;padding:4px 10px;border-radius:20px;background:var(--bg2);color:var(--text2);font-weight:600;text-decoration:none">Twitter/X</a>`:''}
      ${c.youtube?`<a href="${esc(c.youtube)}" target="_blank" style="font-size:12px;padding:4px 10px;border-radius:20px;background:var(--coral-bg);color:var(--coral-tx);font-weight:600;text-decoration:none">YouTube</a>`:''}
    </div>`:''}

    <!-- CONTATTI INDIVIDUALI -->
    ${(c.contacts&&c.contacts.length)?`
    <div class="divhr"></div>
    <div style="font-size:12px;color:var(--text2);font-weight:700;margin-bottom:8px">CONTATTI (${c.contacts.length})</div>
    ${c.contacts.map((ct,i)=>`
      <div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:0.5px solid var(--brd);cursor:pointer" onclick="openEmailToContact('${c.id}',${i})">
        <div style="flex:1">
          <div style="font-size:13px;font-weight:600">${esc(ct.name||'—')}</div>
          <div style="font-size:12px;color:var(--text2)">${esc(ct.title||'')}${ct.email?' · <a href="mailto:'+esc(ct.email)+'" onclick="event.stopPropagation()">'+esc(ct.email)+'</a>':''}</div>
        </div>
        ${ct.linkedin?`<a href="${esc(ct.linkedin)}" target="_blank" onclick="event.stopPropagation()" style="font-size:11px;padding:3px 8px;border-radius:12px;background:var(--blue-bg);color:var(--blue-tx);font-weight:600;text-decoration:none;flex-shrink:0">in</a>`:''}
        <button class="btn bts" style="font-size:11px;flex-shrink:0" onclick="event.stopPropagation();openEmailToContact('${c.id}',${i})">✉</button>
      </div>`).join('')}`:''}

    ${c.notes?`<div class="divhr"></div><div style="font-size:12px;color:var(--text2);font-weight:700;margin-bottom:6px">NOTE</div><div style="font-size:13px;line-height:1.6;white-space:pre-wrap">${esc(c.notes)}</div>`:''}

    ${_researchDetailBlock(c)}

    ${c.emailsSent?`<div class="divhr"></div>
      <div style="display:flex;gap:12px">
        <div style="flex:1;background:var(--blue-bg);border-radius:var(--r);padding:10px;text-align:center">
          <div style="font-size:20px;font-weight:700;color:var(--blue-tx)">${c.emailsSent||0}</div>
          <div style="font-size:11px;color:var(--blue-tx)">Email inviate</div>
        </div>
        ${c.lastEmailSent?`<div style="flex:2;background:var(--bg2);border-radius:var(--r);padding:10px">
          <div style="font-size:11px;color:var(--text2);font-weight:700;margin-bottom:3px">ULTIMA EMAIL</div>
          <div style="font-size:12px">${new Date(c.lastEmailSent).toLocaleDateString('it-IT')}</div>
          <div style="font-size:11px;color:var(--text2)">${esc(c.lastEmailSubject||'')}</div>
        </div>`:''}
      </div>`:''}
    <div class="divhr"></div>
    <div style="font-size:12px;color:var(--text2);font-weight:700;margin-bottom:8px">CAMBIA STATO</div>
    <div style="display:flex;gap:6px;flex-wrap:wrap">
      ${Object.entries(SM).map(([k,v2])=>`<button class="sbtn badge ${v2.c}${c.status===k?' active':''}" onclick="chStatus('${id}','${k}')">${v2.l}</button>`).join('')}
    </div>
    ${log?`<div class="divhr"></div><div style="font-size:12px;color:var(--text2);font-weight:700;margin-bottom:6px">LOG</div>${log}`:''}
    <div class="mf">
      <button class="btn btd bts" onclick="delContact('${id}')">Elimina</button>
      <button class="btn bts" onclick="openAddContact('${id}')">Modifica</button>
      <button class="btn btp bts" onclick="openEmailFromDetail('${id}')">✉ Email</button>
    </div>
  `);
}

function _researchDetailBlock(c){
  const r = c.research;
  if(!r) return '';
  const REC_STYLE = {
    si:    'background:#e8f5e9;color:#2e7d32',
    forse: 'background:#fff3e0;color:#e65100',
    no:    'background:#fce4ec;color:#c62828'
  };
  const VINO_LABEL = {
    si:'🍷 Sì, confermato', probabile:'🍷 Probabile',
    forse:'Forse', non_risulta:'Non risulta', no:'No'
  };
  const stars = '★'.repeat(r.affidabilita||0) + '☆'.repeat(5-(r.affidabilita||0));
  const recStyle = REC_STYLE[r.raccomandato] || 'background:var(--bg2);color:var(--text2)';
  const date = r.analyzed_at ? new Date(r.analyzed_at).toLocaleDateString('it-IT',{day:'2-digit',month:'short',year:'2-digit'}) : '';
  return `<div class="divhr"></div>
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
    <div style="font-size:12px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.5px">🔬 Analisi AI</div>
    <div style="margin-left:auto;display:flex;align-items:center;gap:8px">
      ${date?`<span style="font-size:11px;color:var(--text3)">${date}${r.edited_at?' · modificato a mano':''}</span>`:''}
      <button class="btn bts" style="font-size:11px;padding:3px 10px" onclick="editResearchResult('${c.id}')">✏ Modifica</button>
    </div>
  </div>
  <div style="background:var(--bg2);border-radius:10px;padding:14px 16px">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap">
      <span style="font-size:22px;letter-spacing:-2px;color:#f59e0b">${stars}</span>
      <span style="font-size:13px;font-weight:700">${r.affidabilita||'?'}/5</span>
      <span style="padding:3px 12px;border-radius:20px;font-size:12px;font-weight:700;${recStyle}">${
        r.raccomandato==='si' ? '✅ Raccomandato' :
        r.raccomandato==='forse' ? '🟡 Da valutare' : '❌ Non idoneo'
      }</span>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px 16px;font-size:12px;margin-bottom:10px">
      <div><span style="color:var(--text3)">Vino italiano</span><br><strong>${esc(VINO_LABEL[r.vino_italiano]||r.vino_italiano||'—')}</strong></div>
      <div><span style="color:var(--text3)">Tipo business</span><br><strong>${esc(r.tipo_business||'—')}</strong></div>
      <div><span style="color:var(--text3)">Mercato target</span><br><strong>${esc(r.mercato_target||'—')}</strong></div>
    </div>
    ${r.note?`<div style="font-size:12px;color:var(--text2);line-height:1.5;border-top:0.5px solid var(--brd);padding-top:8px">${esc(r.note)}</div>`:''}
  </div>`;
}

function editResearchResult(id){
  const c=(isClienti()?dbC:db).contacts.find(x=>x.id===id);if(!c)return;
  const r=c.research||{};
  showModal(`
    <div class="mt">Modifica analisi AI</div>
    <div style="font-size:12px;color:var(--text2);line-height:1.5;margin-bottom:12px">Sovrascrivi la valutazione generata dall'AI con il tuo giudizio personale.</div>
    <div class="fg">
      <label>Affidabilità</label>
      <select id="redaff">${[1,2,3,4,5].map(n=>`<option value="${n}"${(r.affidabilita||0)===n?' selected':''}>${'★'.repeat(n)}${'☆'.repeat(5-n)} — ${n}/5</option>`).join('')}</select>
    </div>
    <div class="fg">
      <label>Raccomandazione</label>
      <select id="redrec">
        <option value="si"${r.raccomandato==='si'?' selected':''}>✅ Raccomandato</option>
        <option value="forse"${r.raccomandato==='forse'?' selected':''}>🟡 Da valutare</option>
        <option value="no"${r.raccomandato==='no'?' selected':''}>❌ Non idoneo</option>
      </select>
    </div>
    <div class="fg">
      <label>Note</label>
      <textarea id="redno">${esc(r.note||'')}</textarea>
    </div>
    <div class="mf">
      <button class="btn" onclick="closeModal()">Annulla</button>
      <button class="btn btp" onclick="saveResearchEdit('${id}')">Salva</button>
    </div>
  `);
}

function saveResearchEdit(id){
  const c=(isClienti()?dbC:db).contacts.find(x=>x.id===id);if(!c)return;
  c.research=c.research||{};
  c.research.affidabilita=parseInt(gv('redaff'),10);
  c.research.raccomandato=gv('redrec');
  c.research.note=gv('redno');
  c.research.edited_at=Date.now();
  c.log=c.log||[];c.log.push({ts:Date.now(),msg:'Analisi AI modificata manualmente'});
  saveDB();refreshAll();closeModal();openDetail(id);
}

function chStatus(id,s){
  const c=(isClienti()?dbC:db).contacts.find(x=>x.id===id);if(!c)return;
  c.status=s;c.updatedAt=Date.now();
  c.log=c.log||[];c.log.push({ts:Date.now(),msg:`Stato → ${SM[s].l}`});
  saveDB();refreshAll();closeModal();openDetail(id);
}

function delContact(id){
  if(!confirm('Eliminare questo contatto?'))return;
  (isClienti()?dbC:db).contacts=(isClienti()?dbC:db).contacts.filter(c=>c.id!==id);
  saveDB();closeModal();refreshAll();toast('Eliminato');
}

function deleteNonShippable(){
  const toDelete=dbC.contacts.filter(c=>c.shippable===false);
  if(!toDelete.length){toast('Nessun contatto non spedibile trovato');return;}
  // Raggruppa per paese
  const byCountry={};
  toDelete.forEach(c=>{const k=c.country||'?';byCountry[k]=(byCountry[k]||0)+1;});
  const rows=Object.entries(byCountry).sort((a,b)=>b[1]-a[1])
    .map(([c,n])=>`<div style="display:flex;justify-content:space-between;padding:3px 0;font-size:13px;border-bottom:0.5px solid var(--brd)">
      <span>🚫 ${esc(c)}</span><span style="font-weight:700;color:#c62828">${n}</span></div>`).join('');
  showModal(`
    <div class="mt">🗑 Elimina contatti non spedibili</div>
    <p style="font-size:13px;color:var(--text2);margin-bottom:12px">
      Verranno eliminati definitivamente <strong>${toDelete.length} contatti</strong> da paesi dove non puoi spedire vino:
    </p>
    <div style="max-height:260px;overflow-y:auto;margin-bottom:14px;border:1px solid var(--brd);border-radius:8px;padding:6px 10px">
      ${rows}
    </div>
    <p style="font-size:12px;color:var(--text3)">Questa operazione non è reversibile. I contatti verranno rimossi dal database e salvati su GitHub.</p>
    <div class="mf">
      <button class="btn" onclick="closeModal()">Annulla</button>
      <button class="btn btd" onclick="confirmDeleteNonShippable()">Elimina ${toDelete.length} contatti</button>
    </div>
  `);
}

function confirmDeleteNonShippable(){
  const before=dbC.contacts.length;
  dbC.contacts=dbC.contacts.filter(c=>c.shippable!==false);
  const deleted=before-dbC.contacts.length;
  saveDB();closeModal();refreshAll();
  toast(`✓ Eliminati ${deleted} contatti da paesi non spedibili`);
}

/* ── ADD/EDIT ── */

function openAddContact(editId){
  if(isClienti()) return openAddCliente(editId);
  const adb=db;
  const c=editId?adb.contacts.find(x=>x.id===editId):null;

  // Genera HTML per i contatti individuali
  const contactsArr = c?.contacts||[{name:'',title:'',email:'',phone:'',linkedin:''}];
  const contactRows = contactsArr.map((ct,i)=>contactRowHtml(ct,i)).join('');

  showModal(`
    <div class="mt">${c?'Modifica':'Nuovo'} importatore</div>
    <div style="font-size:12px;color:var(--text2);font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin:0 0 8px">Anagrafica azienda</div>
    <div class="fg2">
      <div class="fg"><label>Ragione sociale *</label><input id="fa" value="${esc(c?.company||'')}"></div>
      <div class="fg"><label>Brand name</label><input id="fbrand" value="${esc(c?.brandName||'')}"></div>
      <div class="fg"><label>Email aziendale</label><input id="fe" type="email" value="${esc(c?.email||'')}"></div>
      <div class="fg"><label>Telefono</label><input id="fp" value="${esc(c?.phone||'')}"></div>
      <div class="fg"><label>Sito web</label><input id="fw" value="${esc(c?.website||'')}"></div>
      <div class="fg"><label>Tipo</label><input id="ftype" placeholder="Importer, Distributor…" value="${esc(c?.type||'')}"></div>
      <div class="fg fgf"><label>Prodotti trattati</label><input id="fprod" placeholder="Wine, Beer, Spirits…" value="${esc(c?.prodType||'')}"></div>
      <div class="fg"><label>Paese</label><input id="fco" list="fcl2" value="${esc(c?.country||'')}"><datalist id="fcl2">${CLIST.map(x=>`<option value="${esc(x)}">`).join('')}</datalist></div>
      <div class="fg"><label>Città</label><input id="fci" value="${esc(c?.city||'')}"></div>
      <div class="fg"><label>Stato / Provincia</label><input id="fstate" value="${esc(c?.state||'')}"></div>
      <div class="fg"><label>Indirizzo</label><input id="faddr" value="${esc(c?.address||'')}"></div>
      <div class="fg"><label>CAP</label><input id="fzip" value="${esc(c?.postalCode||'')}"></div>
      <div class="fg"><label>Dipendenti</label><input id="femp" value="${esc(c?.employees||'')}"></div>
      <div class="fg"><label>Fatturato</label><input id="fsales" value="${esc(c?.sales||'')}"></div>
      <div class="fg"><label>Anno fondazione</label><input id="ffound" value="${esc(c?.founded||'')}"></div>
      <div class="fg"><label>Nr. Registrazione</label><input id="freg" value="${esc(c?.regNumber||'')}"></div>
      <div class="fg"><label>Regione CRM</label><input id="frg" placeholder="Oceania, Europa…" value="${esc(c?.region||'')}"></div>
      <div class="fg"><label>Situazione contatto</label>
        <select id="fst">${Object.entries(SM).map(([k,v2])=>`<option value="${k}"${(c?.status||'new')===k?' selected':''}>${v2.l}</option>`).join('')}</select>
      </div>
    </div>

    <div style="font-size:12px;color:var(--text2);font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin:12px 0 8px">Social azienda</div>
    <div class="fg2">
      <div class="fg"><label>LinkedIn azienda</label><input id="flinco" value="${esc(c?.linkedinCo||'')}"></div>
      <div class="fg"><label>Facebook</label><input id="ffb" value="${esc(c?.facebook||'')}"></div>
      <div class="fg"><label>Instagram</label><input id="finsta" value="${esc(c?.instagram||'')}"></div>
      <div class="fg"><label>Twitter / X</label><input id="ftwit" value="${esc(c?.twitter||'')}"></div>
      <div class="fg"><label>YouTube</label><input id="fyt" value="${esc(c?.youtube||'')}"></div>
    </div>

    <div style="font-size:12px;color:var(--text2);font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin:12px 0 8px">
      Contatti individuali
      <button type="button" class="btn bts" style="font-size:11px;margin-left:8px" onclick="addContactRow()">+ Aggiungi</button>
    </div>
    <div id="contacts-rows">${contactRows}</div>

    <div style="margin-top:12px">
      <div class="fg"><label>Note</label><textarea id="fno">${esc(c?.notes||'')}</textarea></div>
    </div>

    <div class="mf">
      <button class="btn" onclick="closeModal()">Annulla</button>
      <button class="btn btp" onclick="saveContact('${editId||''}')">Salva</button>
    </div>
  `);
}

function contactRowHtml(ct, i){
  return `<div class="contact-edit-row" id="crow-${i}" style="background:var(--bg2);border-radius:var(--r);padding:10px 12px;margin-bottom:8px;position:relative">
    <button type="button" onclick="removeContactRow(${i})" style="position:absolute;top:8px;right:10px;background:none;border:none;cursor:pointer;font-size:16px;color:var(--text3)" title="Rimuovi">✕</button>
    <div class="fg2">
      <div class="fg"><label>Nome</label><input class="ct-name" value="${esc(ct.name||'')}"></div>
      <div class="fg"><label>Ruolo / Job title</label><input class="ct-title" value="${esc(ct.title||'')}"></div>
      <div class="fg"><label>Email diretta</label><input class="ct-email" type="email" value="${esc(ct.email||'')}"></div>
      <div class="fg"><label>Telefono diretto</label><input class="ct-phone" value="${esc(ct.phone||'')}"></div>
      <div class="fg fgf"><label>LinkedIn personale</label><input class="ct-linkedin" value="${esc(ct.linkedin||'')}"></div>
    </div>
  </div>`;
}

let _contactRowCount = 0;

function addContactRow(){
  _contactRowCount++;
  const id = Date.now() + _contactRowCount;
  const container = document.getElementById('contacts-rows');
  if(!container) return;
  const div = document.createElement('div');
  div.innerHTML = contactRowHtml({},id);
  container.appendChild(div.firstElementChild);
}

function removeContactRow(i){
  document.getElementById(`crow-${i}`)?.remove();
}

function openAddCliente(editId){
  const c=editId?dbC.contacts.find(x=>x.id===editId):null;
  showModal(`
    <div class="mt">${c?'Modifica':'Nuovo'} cliente</div>
    <div class="fg2">
      <div class="fg"><label>Nome *</label><input id="fa" value="${esc(c?.nome||'')}"></div>
      <div class="fg"><label>Cognome *</label><input id="fcog" value="${esc(c?.cognome||'')}"></div>
      <div class="fg fgf"><label>Email *</label><input id="fe" type="email" value="${esc(c?.email||'')}"></div>
      <div class="fg"><label>Paese</label>
        <input id="fco" list="fcl2" value="${esc(c?.country||'')}">
        <datalist id="fcl2">${CLIST.map(x=>`<option value="${esc(x)}">`).join('')}</datalist>
      </div>
      <div class="fg"><label>Lingua</label>
        <select id="fling">
          ${['it','en','de','fr','es','pt','ru','zh','ja','ar','nl','pl','sv'].map(l=>`<option value="${l}"${(c?.lingua||'en')===l?' selected':''}>${l}</option>`).join('')}
        </select>
      </div>
      <div class="fg"><label>Situazione contatto</label>
        <select id="fst">${Object.entries(SM).map(([k,v2])=>`<option value="${k}"${(c?.status||'new')===k?' selected':''}>${v2.l}</option>`).join('')}</select>
      </div>
      <div class="fg fgf"><label>Note</label><textarea id="fno">${esc(c?.notes||'')}</textarea></div>
    </div>
    <div class="mf">
      <button class="btn" onclick="closeModal()">Annulla</button>
      <button class="btn btp" onclick="saveContact('${editId||''}')">Salva</button>
    </div>
  `);
}

function saveContact(editId){
  const adb = isClienti()?dbC:db;

  if(isClienti()){
    const nome=gv('fa');const cognome=gv('fcog');const email=gv('fe');
    if(!nome||!email){toast('Nome e email obbligatori');return;}
    const contact={
      id:editId||'c'+Date.now(),
      nome,cognome,email,lingua:document.getElementById('fling')?.value||'en',
      country:gv('fco'),statoEmail:gv('fsv')||'sconosciuto',
      company:(nome)+' '+(cognome),name:(nome)+' '+(cognome),
      status:document.getElementById('fst').value,
      products:[],notes:gv('fno'),
      updatedAt:Date.now(),
      createdAt:editId?(adb.contacts.find(c=>c.id===editId)?.createdAt||Date.now()):Date.now()
    };
    if(editId){const i=adb.contacts.findIndex(c=>c.id===editId);if(i>=0)adb.contacts[i]=contact;}
    else adb.contacts.push(contact);

  } else {
    // ── IMPORTATORE: salva tutti i 27 campi + contatti individuali ──
    const company=gv('fa');
    if(!company){toast('Ragione sociale obbligatoria');return;}

    // Raccogli i contatti individuali dalle righe del form
    const contactRows=[...document.querySelectorAll('.contact-edit-row')];
    const contacts=contactRows.map(row=>({
      name:  row.querySelector('.ct-name')?.value.trim()||'',
      title: row.querySelector('.ct-title')?.value.trim()||'',
      email: row.querySelector('.ct-email')?.value.trim()||'',
      phone: row.querySelector('.ct-phone')?.value.trim()||'',
      linkedin: row.querySelector('.ct-linkedin')?.value.trim()||'',
    })).filter(c=>c.name||c.email);

    const existing = editId ? adb.contacts.find(c=>c.id===editId) : null;
    const contact={
      id:        editId||'c'+Date.now(),
      compId:    existing?.compId||editId||'c'+Date.now(),
      company,
      brandName: gv('fbrand'),
      email:     gv('fe'),
      phone:     gv('fp'),
      website:   gv('fw'),
      type:      gv('ftype'),
      prodType:  gv('fprod'),
      country:   gv('fco'),
      city:      gv('fci'),
      state:     gv('fstate'),
      address:   gv('faddr'),
      postalCode:gv('fzip'),
      employees: gv('femp'),
      sales:     gv('fsales'),
      founded:   gv('ffound'),
      regNumber: gv('freg'),
      region:    gv('frg'),
      linkedinCo:gv('flinco'),
      facebook:  gv('ffb'),
      instagram: gv('finsta'),
      twitter:   gv('ftwit'),
      youtube:   gv('fyt'),
      contacts,
      // Legacy compat
      contactName:  contacts[0]?.name||'',
      contactTitle: contacts[0]?.title||'',
      contactEmail: contacts[0]?.email||'',
      name: contacts[0]?.name||'',
      status: document.getElementById('fst').value,
      products:[], notes:gv('fno'),
      emailsSent:    existing?.emailsSent||0,
      lastEmailSent: existing?.lastEmailSent||null,
      lastEmailSubject: existing?.lastEmailSubject||'',
      log: existing?.log||[],
      updatedAt: Date.now(),
      createdAt: existing?.createdAt||Date.now()
    };

    if(editId){const i=adb.contacts.findIndex(c=>c.id===editId);if(i>=0)adb.contacts[i]=contact;}
    else adb.contacts.push(contact);
  }

  saveDB();closeModal();refreshAll();toast(editId?'Aggiornato ✓':'Aggiunto ✓');
}



/* ─── SELEZIONE CONTATTO PER EMAIL ───────────────────────────
   Riceve l'array contacts[] di un importatore e restituisce:
   { primary, secondary }
   primary  = contatto a cui inviare la mail
   secondary= contatto da menzionare nell'apertura (owner/founder)
   Se nessun contatto ha priorità, usa il primo disponibile
──────────────────────────────────────────────────────────── */

// Converte valori testuali di employee/sales in numero per ordinamento
function parseNumeric(val){
  if(!val) return -1;
  const s = String(val).trim().toUpperCase()
    .replace(/[€$£¥,\s]/g,'')  // rimuovi simboli valuta e separatori
    .replace(/\.(?=\d{3})/g,''); // rimuovi punto come separatore migliaia
  let n = parseFloat(s);
  if(isNaN(n)) return -1;
  if(s.endsWith('B')) n *= 1_000_000_000;
  else if(s.endsWith('M')) n *= 1_000_000;
  else if(s.endsWith('K')) n *= 1_000;
  return n;
}

// Job title priorities
const JOB_PRIORITY = {
  1: ['sales manager', 'buyer', 'purchasing manager', 'managing partner', 'sales representative', 'sales director', 'commercial director', 'sales', 'commercial', 'commercial manager', 'wine buyer', 'senior buyer', 'purchasing', 'import manager', 'sales consultant', 'regional sales manager', 'product manager', 'area sales manager', 'marketing manager', 'purchasing director', 'wine manager', 'purchaser', 'national sales manager', 'head of sales', 'buying manager', 'wine sales specialist', 'director of sales', 'wine sales', 'purchase manager', 'director of sales', 'buying director', 'head of sales', 'general sales manager', 'wine importer'],
  2: ['managing director', 'manager', 'director', 'general manager', 'administrator', 'in charge', 'operations manager', 'wine merchant', 'representative', 'chief executive officer', 'account manager', 'executive director', 'business owner', 'co-founder', 'representative director', 'general director', 'director of operations', 'president & ceo', 'wine director', 'sales specialist', 'wine sales representative', 'director of operations', 'procurement manager', 'logistics manager', 'owner/ manager', 'co-owner', 'operation manager', 'senior brand manager', 'chief operating officer', 'regional manager', 'sales assistant', 'sales agent', 'ceo & founder', 'junior buyer', 'portfolio manager', 'area manager', 'senior sales manager', 'founder and ceo', 'business manager', 'managing director/ owner'],
  3: ['owner', 'ceo', 'president', 'founder', 'co-owner', 'sommelier', 'partner', 'co-founder', 'wine consultant', 'brand manager', 'store manager', 'business development manager', 'category manager', 'key account manager', 'wine specialist', 'vice president', 'sales associate', 'president and ceo', 'sales executive', 'administrative', 'administrative manager', 'brand ambassador', 'administrative assistant'],
};


function renderFollowups(){
  const list=(isClienti()?dbC:db).contacts
    .filter(c=>c.status==='followup'||c.status==='sent')
    .sort((a,b)=>(a.updatedAt||0)-(b.updatedAt||0));
  const el=document.getElementById('fl');
  if(!el) return;
  el.innerHTML=list.length
    ? `<div class="card">${list.map(c=>{
        const days=Math.floor((Date.now()-(c.updatedAt||Date.now()))/86400000);
        return `<div class="cr" onclick="openDetail('${c.id}')">
          <div class="av ${AV[hsh(c.company)%6]}">${ini(c.name||c.company)}</div>
          <div class="ci">
            <div class="cn">${esc(c.company)}${c.name?' · '+esc(c.name):''}</div>
            <div class="cs">${esc(c.country||'')} · ${days>0?days+' gg fa':'oggi'}</div>
          </div>
          <div style="text-align:right;flex-shrink:0;display:flex;flex-direction:column;align-items:flex-end;gap:4px">
            <span class="badge ${SM[c.status]?.c||'bn'}">${SM[c.status]?.l||''}</span>
            <button class="btn bts" style="font-size:11px" onclick="event.stopPropagation();openEmailModal('${c.id}')">✉</button>
          </div>
        </div>`;
      }).join('')}</div>`
    : '<div class="card"><div class="empty">Nessun follow-up 🎉</div></div>';
}

/* ═══ SETTINGS — toggle email importatori ═══ */

async function toggleEmailAutoSendImp(){
  dbSettings.emailAutoSendImportatori=!dbSettings.emailAutoSendImportatori;
  renderEmailToggleImp();
  await pushSettingsGH();
  toast(dbSettings.emailAutoSendImportatori?'✓ Email importatori ATTIVATE':'⏸ Email importatori DISATTIVATE');
}

async function toggleTestModeImp(){
  dbSettings.testModeImportatori=!dbSettings.testModeImportatori;
  renderEmailToggleImp();
  await pushSettingsGH();
  toast(dbSettings.testModeImportatori?'🧪 Test mode ON — email solo a te':'👥 Produzione — email ai contatti reali');
}

function renderEmailToggleImp(){
  const el=document.getElementById('email-autosend-imp-toggle');
  if(!el) return;
  const on  =dbSettings.emailAutoSendImportatori===true;
  const test=dbSettings.testModeImportatori!==false;
  const mainBtn=`<button onclick="toggleEmailAutoSendImp()" style="font-size:12px;font-weight:700;padding:7px 16px;border-radius:20px;border:none;cursor:pointer;background:${on?'#2a9d5c':'#c0392b'};color:#fff;letter-spacing:.3px">${on?'🟢 Email imp.: ON':'🔴 Email imp.: OFF'}</button>`;
  const testBtn=on?`<button onclick="toggleTestModeImp()" style="font-size:12px;font-weight:700;padding:7px 16px;border-radius:20px;border:none;cursor:pointer;background:${test?'#e67e22':'#2980b9'};color:#fff;letter-spacing:.3px">${test?'🧪 Test mode':'👥 Contatti reali'}</button>`:'';
  el.innerHTML=`<div style="display:flex;align-items:center;gap:8px">${mainBtn}${testBtn}</div>`;
}

/* ═══════════════════════════════════════════════════
   SINCRONIZZAZIONE BREVO — aperture, click, bounce
═══════════════════════════════════════════════════ */