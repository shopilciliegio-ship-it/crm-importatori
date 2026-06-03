/* ═══ INIT ═══ */

async function switchLayer(newLayer){
  if(newLayer===layer) return;
  layer=newLayer;
  sel.clear();

  const isOrd = newLayer==='ordini';

  // Toggle header buttons
  document.getElementById('layer-btn-imp').classList.toggle('active', newLayer==='importatori');
  document.getElementById('layer-btn-cli').classList.toggle('active', newLayer==='clienti');
  const btnOrd=document.getElementById('layer-btn-ord');
  if(btnOrd) btnOrd.classList.toggle('active', isOrd);

  document.getElementById('hdr-sub').textContent = isOrd
    ? 'Ordini Clienti'
    : newLayer==='clienti' ? 'Clienti Privati' : 'Importatori & Distributori';

  // Sezione ordini vs CRM normale
  const navEl  = document.querySelector('.nav');
  const ordSec = document.getElementById('section-ordini');
  if(navEl)  navEl.style.display  = isOrd ? 'none' : '';
  if(ordSec) ordSec.style.display = isOrd ? 'block' : 'none';

  if(isOrd){
    document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
    try{ if(typeof renderOrdini==='function') renderOrdini(); }catch(e){ console.warn('renderOrdini:',e); }
    try{ if(typeof renderReminderTemplatesPanel==='function') renderReminderTemplatesPanel(); }catch(e){}
    return;
  }

  // Layer importatori / clienti
  const addBtn=document.querySelector('.btn.btp[onclick="openAddContact()"]');
  if(addBtn) addBtn.textContent = newLayer==='clienti'?'+ Cliente':'+ Contatto';

  if(isClienti()&&dbC.contacts.length===0&&ghs.token){
    await loadFromGH();
  } else {
    refreshAll();
  }

  const cardImp=document.getElementById('import-card-imp');
  const cardCli=document.getElementById('import-card-cli');
  if(cardImp) cardImp.style.display = newLayer==='clienti'?'none':'block';
  if(cardCli) cardCli.style.display = newLayer==='clienti'?'block':'none';

  showPage('dashboard', document.querySelector('.nb'));
}

/* ── INIT: al caricamento pagina legge da GitHub ── */

async function init(){
  try{const r=localStorage.getItem('ghcfg');if(r)ghs=JSON.parse(r);}catch(e){}
  try{const r=localStorage.getItem('brvcfg');if(r)brv=JSON.parse(r);}catch(e){}
  if(!db.templates||!db.templates.length) db.templates=defTplImportatori();
  if(!dbC.templates||!dbC.templates.length) dbC.templates=defTplClienti();
  if(ghs.token&&ghs.owner&&ghs.repo){
    await loadTemplatesFromGH();
    await loadFromGH();
    // loadOrdiniFromGH è opzionale — presente solo se js/ordini.js è caricato
    if(typeof loadOrdiniFromGH==='function'){
      try{ await loadOrdiniFromGH(); }catch(e){ console.warn('loadOrdiniFromGH:',e); }
    }
    if(typeof loadReminderTemplates==='function'){
      try{ await loadReminderTemplates(); }catch(e){ console.warn('loadReminderTemplates:',e); }
    }
  } else {
    updGh('idle');refreshAll();
  }
  _migrateTemplatesIfNeeded();
}

function refreshAll(){
  renderStats();renderContacts();renderRegistro();renderFollowups();
  renderTemplates();renderRegionChart();renderCCChart();renderPipeline();
  updateBadges();updateFilters();
  try{ if(typeof renderOrdini==='function') renderOrdini(); }catch(e){ console.warn('renderOrdini:',e); }
}

function saveDB(){
  if(!ghs.token||!ghs.owner||!ghs.repo){updGh('error');return;}
  clearTimeout(saveTimer);
  saveTimer=setTimeout(pushGH,2000);
  updGh('pending');
}

function confirmDeleteAll(){
  showModal(`
    <div class="mt" style="color:var(--red)">🗑 Cancella tutto il database</div>
    <div class="danger-box">
      <p style="font-size:14px;font-weight:600;margin-bottom:8px">Attenzione — operazione irreversibile</p>
      <p style="font-size:13px;line-height:1.6">Verranno eliminati <strong>${(isClienti()?dbC:db).contacts.length} contatti</strong>. Questa azione aggiorna anche GitHub al prossimo salvataggio automatico.</p>
    </div>
    <p style="font-size:13px;margin-bottom:12px">Scrivi <strong>CANCELLA</strong> per confermare:</p>
    <div class="fg fgf"><input id="del-c" placeholder="CANCELLA" oninput="document.getElementById('del-b').disabled=this.value!=='CANCELLA'"></div>
    <div class="mf">
      <button class="btn" onclick="closeModal()">Annulla</button>
      <button class="btn btd" id="del-b" disabled onclick="doDeleteAll()">Cancella tutto</button>
    </div>
  `);
}

function doDeleteAll(){
  (isClienti()?dbC:db).contacts=[];
  closeModal();refreshAll();
  clearTimeout(saveTimer);
  pushGH().then(()=>toast('Database svuotato e sincronizzato ✓'));
}

// Avvia app
init(); // script in fondo al body, DOM già pronto
