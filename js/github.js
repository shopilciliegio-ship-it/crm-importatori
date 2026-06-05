/* ═══ GITHUB ═══ */

// Traccia quali layer sono stati caricati da GH in questa sessione.
const _layersLoaded = new Set();

// Override architecture per importatori (file da 29 MB):
// contatti.json  = read-only base, aggiornato solo da BWI sync (GitHub Actions)
// contatti-overrides.json = solo modifiche utente (status/notes/log/brevoEvents), < 50 KB
const OVERRIDES_PATH = 'data/contatti-overrides.json';
let _baseSnap = {}; // {id: {status, notes, log_s, brevoEvents_s}} — snapshot prima degli override

function ghPathTemplates(){ return 'data/templates.json'; }

async function loadTemplatesFromGH(){
  const{token,owner,repo}=ghs;
  if(!token||!owner||!repo) return;
  const url=`https://api.github.com/repos/${owner}/${repo}/contents/${ghPathTemplates()}`;
  try{
    const r=await fetch(url,{headers:{'Authorization':`token ${token}`,'Accept':'application/vnd.github.v3+json'}});
    if(r.status===404){ return; } // file non esiste ancora — usa default
    if(!r.ok) return;
    const d=await r.json();
    ghSha.templates=d.sha;
    const raw=d.content.replace(/\n/g,'');
    let jsonStr;
    try{ jsonStr=decodeURIComponent(Array.from(atob(raw),c=>'%'+c.charCodeAt(0).toString(16).padStart(2,'0')).join('')); }
    catch(e){ jsonStr=atob(raw); }
    const parsed=JSON.parse(jsonStr);
    if(Array.isArray(parsed)&&parsed.length){
      db.templates=parsed;
      dbC.templates=parsed.filter(t=>t.id&&t.id.startsWith('c'));
      console.log(`✓ ${parsed.length} template caricati da GitHub`);
    }
  }catch(e){ console.warn('loadTemplatesFromGH error:',e); }
}

async function saveTemplatesToGH(){
  const{token,owner,repo}=ghs;
  if(!token||!owner||!repo) return;
  // Salva tutti i template (importatori + clienti) in un unico file
  const allTemplates=[...db.templates,...dbC.templates];
  const url=`https://api.github.com/repos/${owner}/${repo}/contents/${ghPathTemplates()}`;
  const hd={'Authorization':`token ${token}`,'Content-Type':'application/json','Accept':'application/vnd.github.v3+json'};
  try{
    // Recupera SHA se non ce l'abbiamo
    if(!ghSha.templates){
      const r=await fetch(url,{headers:hd});
      if(r.ok){ const d=await r.json(); ghSha.templates=d.sha; }
    }
    const jsonStr=JSON.stringify(allTemplates,null,2);
    const b64=btoa(Array.from(new TextEncoder().encode(jsonStr),b=>String.fromCharCode(b)).join(''));
    const body={message:'Update templates',content:b64};
    if(ghSha.templates) body.sha=ghSha.templates;
    const res=await fetch(url,{method:'PUT',headers:hd,body:JSON.stringify(body)});
    if(res.ok){ const d=await res.json(); ghSha.templates=d.content?.sha||ghSha.templates; toast('📁 templates.json salvato su GitHub ✓'); }
    else { const err=await res.json().catch(()=>({})); console.error('saveTemplatesToGH:',res.status,err); toast('⚠ Errore salvataggio templates: '+res.status); }
  }catch(e){ console.warn('saveTemplatesToGH error:',e); }
}

/* ── LAYER HELPERS ── */

function activeDB(){ return layer==='clienti'?dbC:db; }

function ghPath(){ return layer==='clienti'?'data/clienti.json':'data/contatti.json'; }

function isClienti(){ return layer==='clienti'; }

function getActiveDB(){ return isClienti()?dbC:db; }

function setActiveContacts(arr){ if(isClienti()) dbC.contacts=arr; else db.contacts=arr; }

function updGh(s){
  const d=document.getElementById('gh-dot'),l=document.getElementById('gh-lbl');
  if(!d)return;
  d.className='gh-dot '+s;
  const cfg=ghs.token&&ghs.owner&&ghs.repo;
  l.textContent={
    idle: cfg?`${ghs.owner}/${ghs.repo}`:'⚠ GitHub non configurato',
    pending:'Salvataggio…',
    saving:'Salvataggio…',
    saved:'✓ Salvato',
    error:'✗ Errore — verifica token'
  }[s]||s;
}

async function _loadImportatoriOverrides(token,owner,repo,contacts){
  const url=`https://api.github.com/repos/${owner}/${repo}/contents/${OVERRIDES_PATH}`;
  try{
    const r=await fetch(url,{headers:{'Authorization':`token ${token}`,'Accept':'application/vnd.github.v3+json'}});
    if(r.status===404){ghSha.overrides=null;return;} // nessun override ancora
    if(!r.ok) return;
    const d=await r.json();
    ghSha.overrides=d.sha;
    const raw=(d.content||'').replace(/\n/g,'');
    if(!raw) return;
    let jsonStr;
    try{ jsonStr=decodeURIComponent(Array.from(atob(raw),c=>'%'+c.charCodeAt(0).toString(16).padStart(2,'0')).join('')); }
    catch(e){ jsonStr=atob(raw); }
    const overrides=JSON.parse(jsonStr);
    const byId=Object.fromEntries(contacts.map(c=>[c.id,c]));
    let applied=0;
    for(const [id,changes] of Object.entries(overrides)){
      if(byId[id]){ Object.assign(byId[id],changes); applied++; }
    }
    if(applied) console.log(`Override applicati: ${applied} contatti`);
  }catch(e){ console.warn('_loadImportatoriOverrides:',e); }
}

async function pushGH(){
  const{token,owner,repo}=ghs;
  if(!token||!owner||!repo)return;
  // Guard: blocca solo se il layer NON è ancora stato caricato da GH E i contatti sono vuoti.
  const activeContacts=(isClienti()?dbC:db).contacts;
  if(!_layersLoaded.has(layer)&&(!activeContacts||activeContacts.length===0)){
    console.warn('pushGH: skip — layer non ancora caricato');
    updGh('saved');return;
  }
  // Importatori: salva solo le differenze utente in contatti-overrides.json (< 50KB invece di 29MB)
  if(!isClienti()){
    await _pushImportatoriOverrides(token,owner,repo);
    return;
  }
  // Clienti / altri layer: salva file completo
  const path=ghPath();
  const url=`https://api.github.com/repos/${owner}/${repo}/contents/${path}`;
  const hd={'Authorization':`token ${token}`,'Content-Type':'application/json','Accept':'application/vnd.github.v3+json'};
  updGh('saving');
  try{
    if(!ghSha[layer]){
      const r=await fetch(url,{headers:hd});
      if(r.ok) ghSha[layer]=(await r.json()).sha;
    }
    const jsonStr=JSON.stringify(isClienti()?dbC:db,null,2);
    const bytes=new TextEncoder().encode(jsonStr);
    const CHUNK=65536; let binary='';
    for(let i=0;i<bytes.length;i+=CHUNK)
      binary+=String.fromCharCode.apply(null,bytes.subarray(i,Math.min(i+CHUNK,bytes.length)));
    const b64=btoa(binary);
    const body={message:`CRM update — ${new Date().toLocaleString('it-IT')}`,content:b64};
    if(ghSha[layer]) body.sha=ghSha[layer];
    const res=await fetch(url,{method:'PUT',headers:hd,body:JSON.stringify(body)});
    if(res.ok){
      ghSha[layer]=(await res.json()).content.sha;
      updGh('saved');
    } else if(res.status===409||res.status===422){
      ghSha={importatori:null,clienti:null,templates:null,ordini:null,overrides:null};
      setTimeout(pushGH,1000);
    } else {
      const err=await res.json().catch(()=>({}));
      console.error('pushGH error:',res.status,err.message);
      updGh('error');
    }
  }catch(e){updGh('error');console.error('pushGH exception:',e);}
}

async function _pushImportatoriOverrides(token,owner,repo){
  updGh('saving');
  // Calcola solo le differenze rispetto al base caricato da GitHub
  const newOv={};
  for(const c of db.contacts){
    const snap=_baseSnap[c.id];
    if(!snap) continue;
    const diff={};
    if((c.status||'')!==(snap.status||''))           diff.status=c.status;
    if((c.notes||'')!==(snap.notes||''))             diff.notes=c.notes;
    if(JSON.stringify(c.log||[])!==snap.log)         diff.log=c.log||[];
    if(JSON.stringify(c.brevoEvents||[])!==snap.brevoEvents) diff.brevoEvents=c.brevoEvents||[];
    if(Object.keys(diff).length) newOv[c.id]=diff;
  }
  const url=`https://api.github.com/repos/${owner}/${repo}/contents/${OVERRIDES_PATH}`;
  const hd={'Authorization':`token ${token}`,'Content-Type':'application/json','Accept':'application/vnd.github.v3+json'};
  try{
    if(!ghSha.overrides){
      const r=await fetch(url,{headers:hd});
      if(r.ok) ghSha.overrides=(await r.json()).sha;
    }
    const jsonStr=JSON.stringify(newOv,null,2);
    const bytes=new TextEncoder().encode(jsonStr);
    const CHUNK=65536; let binary='';
    for(let i=0;i<bytes.length;i+=CHUNK)
      binary+=String.fromCharCode.apply(null,bytes.subarray(i,Math.min(i+CHUNK,bytes.length)));
    const b64=btoa(binary);
    const body={message:`CRM overrides — ${new Date().toLocaleString('it-IT')}`,content:b64};
    if(ghSha.overrides) body.sha=ghSha.overrides;
    const res=await fetch(url,{method:'PUT',headers:hd,body:JSON.stringify(body)});
    if(res.ok){
      ghSha.overrides=(await res.json()).content.sha;
      updGh('saved');
      console.log(`overrides salvati: ${Object.keys(newOv).length} contatti modificati`);
    } else if(res.status===409||res.status===422){
      ghSha.overrides=null; setTimeout(()=>_pushImportatoriOverrides(token,owner,repo),1000);
    } else {
      const err=await res.json().catch(()=>({}));
      console.error('pushGH overrides error:',res.status,err.message); updGh('error');
    }
  }catch(e){updGh('error');console.error('_pushImportatoriOverrides:',e);}
}

async function loadFromGH(){
  const{token,owner,repo}=ghs;
  if(!token||!owner||!repo){updGh('error');return;}
  const path=ghPath();
  const url=`https://api.github.com/repos/${owner}/${repo}/contents/${path}`;
  updGh('saving');
  try{
    const r=await fetch(url,{headers:{'Authorization':`token ${token}`,'Accept':'application/vnd.github.v3+json'}});
    if(r.status===404){updGh('saved');refreshAll();_layersLoaded.add(layer);toast('GitHub connesso — database vuoto, pronto per import');return;}
    if(!r.ok){
      const err=await r.json().catch(()=>({}));
      throw new Error(`GitHub API: ${r.status} — ${err.message||'errore sconosciuto'}`);
    }
    const d=await r.json();
    ghSha[layer]=d.sha;
    // File > 1 MB: GitHub Contents API restituisce content vuoto — usa download_url
    let jsonStr;
    const raw=(d.content||'').replace(/\n/g,'');
    if(!raw&&d.download_url){
      // download_url non vuole Authorization: causa CORS preflight su raw.githubusercontent.com
      // I repo privati hanno già il token embedded nella URL; i pubblici non ne hanno bisogno
      const rawR=await fetch(d.download_url);
      if(!rawR.ok) throw new Error(`Download diretto: ${rawR.status}`);
      jsonStr=await rawR.text();
    } else {
      try{
        jsonStr=decodeURIComponent(Array.from(atob(raw),c=>'%'+c.charCodeAt(0).toString(16).padStart(2,'0')).join(''));
      }catch(e){jsonStr=atob(raw);}
    }
    if(!jsonStr||!jsonStr.trim()||jsonStr.trim()==='{}'){
      updGh('saved');refreshAll();_layersLoaded.add(layer);
      toast('GitHub connesso — database vuoto, pronto per import');return;
    }
    const parsed=JSON.parse(jsonStr);
    const contacts=parsed.contacts||parsed;
    if(!Array.isArray(contacts))throw new Error('Formato contatti non valido');
    // Popola il db del layer attivo
    if(isClienti()){
      dbC.contacts=contacts;
      if(parsed.templates&&parsed.templates.length)dbC.templates=parsed.templates;
      _layersLoaded.add(layer);
      refreshAll();updGh('saved');
      toast(`✓ ${contacts.length} clienti caricati`);
    } else {
      // Importatori: snapshot base → carica override → applica
      _baseSnap={};
      for(const c of contacts){
        _baseSnap[c.id]={
          status:c.status||'',
          notes:c.notes||'',
          log:JSON.stringify(c.log||[]),
          brevoEvents:JSON.stringify(c.brevoEvents||[])
        };
      }
      db.contacts=contacts;
      if(parsed.templates&&parsed.templates.length)db.templates=parsed.templates;
      // Carica e applica override (file piccolo, < 50KB)
      await _loadImportatoriOverrides(token,owner,repo,contacts);
      _layersLoaded.add(layer);
      refreshAll();updGh('saved');
      toast(`✓ ${contacts.length} importatori caricati`);
    }
  }catch(e){
    updGh('error');toast('Errore: '+e.message);console.error('loadFromGH error:',e);refreshAll();
  }
}

/* ── BWI SYNC TRIGGER ── */

async function triggerBwiSync(){
  const{token,owner,repo}=ghs;
  if(!token||!owner||!repo){ toast('⚙ Configura GitHub nelle Impostazioni'); openSettings(); return; }

  const btn=document.getElementById('bwi-sync-btn');
  if(btn){ btn.disabled=true; btn.textContent='⏳ Avvio…'; }

  const dispatchUrl=`https://api.github.com/repos/${owner}/${repo}/actions/workflows/bwi_weekly.yml/dispatches`;
  try{
    const r=await fetch(dispatchUrl,{
      method:'POST',
      headers:{'Authorization':`token ${token}`,'Accept':'application/vnd.github.v3+json','Content-Type':'application/json'},
      body:JSON.stringify({ref:'main'})
    });
    if(r.ok||r.status===204){
      toast('🔄 BWI Sync avviato — attendo completamento…');
      _pollBwiWorkflow(btn);
    } else {
      const err=await r.json().catch(()=>({}));
      toast('⚠ Errore avvio: '+(err.message||r.status));
      if(btn){ btn.disabled=false; btn.textContent='🔄 BWI Sync'; }
    }
  }catch(e){
    toast('⚠ '+e.message);
    if(btn){ btn.disabled=false; btn.textContent='🔄 BWI Sync'; }
  }
}

async function _pollBwiWorkflow(btn, maxAttempts=20){
  const{token,owner,repo}=ghs;
  const runsUrl=`https://api.github.com/repos/${owner}/${repo}/actions/runs?workflow_id=bwi_weekly.yml&per_page=1`;
  let elapsed=0;

  for(let i=0;i<maxAttempts;i++){
    // Prima attesa (workflow ha bisogno di qualche secondo per comparire)
    const wait = i===0 ? 8000 : 30000;
    await new Promise(r=>setTimeout(r,wait));
    elapsed += wait;
    const mins = Math.floor(elapsed/60000);
    const secs = Math.floor((elapsed%60000)/1000);
    if(btn) btn.textContent=`⏳ ${mins>0?mins+'m ':''
}${secs}s…`;

    try{
      const r=await fetch(runsUrl,{
        headers:{'Authorization':`token ${token}`,'Accept':'application/vnd.github.v3+json'}
      });
      if(!r.ok) continue;
      const data=await r.json();
      const run=data.workflow_runs?.[0];
      if(!run) continue;

      if(run.status==='completed'){
        if(run.conclusion==='success'){
          toast('✓ BWI Sync completato — premi ↻ per aggiornare i contatti');
        } else {
          toast('⚠ BWI Sync terminato con errore: '+run.conclusion);
        }
        if(btn){ btn.disabled=false; btn.textContent='🔄 BWI Sync'; }
        return;
      }
    }catch(e){ console.warn('BWI poll error:',e); }
  }
  // Timeout
  toast('⏱ BWI Sync ancora in corso — ricarica manualmente tra qualche minuto');
  if(btn){ btn.disabled=false; btn.textContent='🔄 BWI Sync'; }
}

/* ── DELETE ALL ── */

function exportData(){
  const blob=new Blob([JSON.stringify(db,null,2)],{type:'application/json'});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download=`contatti-backup-${new Date().toISOString().slice(0,10)}.json`;
  a.click();toast('Export scaricato ✓');
}

/* ── MODAL ── */

function openSettings(){
  const brvOk=brv.apiKey&&brv.senderEmail;
  showModal(`
    <div class="mt">⚙ Impostazioni</div>

    <div style="font-size:13px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px">GitHub — Database</div>
    <p style="font-size:13px;color:var(--text2);margin-bottom:10px;line-height:1.6">
      I dati si caricano da GitHub all'avvio e si salvano automaticamente ad ogni modifica in <code>data/contatti.json</code>.<br>
      Token su <a href="https://github.com/settings/tokens/new" target="_blank">github.com/settings/tokens/new</a> con permesso <code>repo</code>.
    </p>
    <div class="fg2" style="margin-bottom:1.25rem">
      <div class="fg fgf"><label>Personal Access Token</label>
        <input id="gt" type="password" placeholder="ghp_xxxx…" value="${esc(ghs.token||'')}">
      </div>
      <div class="fg"><label>Owner</label>
        <input id="go" placeholder="shopilciliegio-ship-it" value="${esc(ghs.owner||'shopilciliegio-ship-it')}">
      </div>
      <div class="fg"><label>Repository</label>
        <input id="gr" placeholder="crm-importatori" value="${esc(ghs.repo||'crm-importatori')}">
      </div>
    </div>

    <div style="height:0.5px;background:var(--brd);margin:0 0 1.25rem"></div>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
      <div style="font-size:13px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.5px">Brevo — Invio Email</div>
      ${brvOk?'<span style="background:var(--green-bg);color:var(--green-tx);padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700">✓ Configurato</span>':'<span style="background:var(--amber-bg);color:var(--amber-tx);padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700">Non configurato</span>'}
    </div>
    <p style="font-size:13px;color:var(--text2);margin-bottom:10px;line-height:1.6">
      API Key su <a href="https://app.brevo.com/settings/keys/api" target="_blank">app.brevo.com → Settings → API Keys</a>.
    </p>
    <div class="fg2">
      <div class="fg fgf"><label>API Key Brevo</label>
        <input id="bk" type="password" placeholder="xkeysib-…" value="${esc(brv.apiKey||'')}">
      </div>
      <div class="fg"><label>Email mittente verificata</label>
        <input id="be" placeholder="luca@sienawine.it" value="${esc(brv.senderEmail||'luca@sienawine.it')}">
      </div>
      <div class="fg"><label>Nome mittente</label>
        <input id="bn" placeholder="Luca Pattaro | Siena Wine Srl" value="${esc(brv.senderName||'Luca Pattaro | Siena Wine Srl')}">
      </div>
    </div>

    <div class="mf">
      <button class="btn" onclick="closeModal()">Annulla</button>
      <button class="btn btp" onclick="saveSettings()">Salva e connetti</button>
    </div>
  `);
}

function saveSettings(){
  ghs={token:gv('gt'),owner:gv('go'),repo:gv('gr')};
  localStorage.setItem('ghcfg',JSON.stringify(ghs));
  brv={apiKey:gv('bk'),senderEmail:gv('be'),senderName:gv('bn')};
  localStorage.setItem('brvcfg',JSON.stringify(brv));
  ghSha={importatori:null,clienti:null,templates:null,ordini:null,overrides:null};closeModal();
  toast('Impostazioni salvate — connessione in corso…');
  loadFromGH();
}