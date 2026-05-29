/* ═══ INIT ═══ */

async function switchLayer(newLayer){
  if(newLayer===layer) return;
  layer=newLayer;
  sel.clear();
  // Aggiorna UI toggle
  document.getElementById('layer-btn-imp').classList.toggle('active', newLayer==='importatori');
  document.getElementById('layer-btn-cli').classList.toggle('active', newLayer==='clienti');
  document.getElementById('hdr-sub').textContent = newLayer==='clienti'
    ?'Clienti Privati':'Importatori & Distributori';
  // Aggiorna bottone +
  document.querySelector('.btn.btp[onclick="openAddContact()"]').textContent =
    newLayer==='clienti'?'+ Cliente':'+ Contatto';
  // Carica dati del layer se non ancora caricati
  if(isClienti()&&dbC.contacts.length===0&&ghs.token){
    await loadFromGH();
  } else {
    refreshAll();
  }
  // Mostra card import corretta
  const cardImp = document.getElementById('import-card-imp');
  const cardCli = document.getElementById('import-card-cli');
  if(cardImp) cardImp.style.display = newLayer==='clienti'?'none':'block';
  if(cardCli) cardCli.style.display = newLayer==='clienti'?'block':'none';
  // Torna alla dashboard
  showPage('dashboard', document.querySelector('.nb'));
}

/* ── INIT: al caricamento pagina legge da GitHub ── */

async function init(){
  try{const r=localStorage.getItem('ghcfg');if(r)ghs=JSON.parse(r);}catch(e){}
  try{const r=localStorage.getItem('brvcfg');if(r)brv=JSON.parse(r);}catch(e){}
  // Inizializza template per entrambi i layer indipendentemente da quello attivo
  if(!db.templates||!db.templates.length) db.templates=defTplImportatori();
  if(!dbC.templates||!dbC.templates.length) dbC.templates=defTplClienti();
  if(ghs.token&&ghs.owner&&ghs.repo){
    await loadTemplatesFromGH(); // carica template prima dei contatti
    await loadFromGH();
  } else {
    updGh('idle');refreshAll();
  }
  // Migrazione template: se i template caricati sono quelli vecchi, aggiorna
  _migrateTemplatesIfNeeded();
}

function refreshAll(){
  renderStats();renderContacts();renderFollowups();
  renderTemplates();renderRegionChart();renderCCChart();renderPipeline();
  updateBadges();updateFilters();
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
  // Push immediato su GitHub
  clearTimeout(saveTimer);
  pushGH().then(()=>toast('Database svuotato e sincronizzato ✓'));
}

// Avvia app
init(); // script in fondo al body, DOM già pronto
