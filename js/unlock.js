/* ═══ SBLOCCO EMAIL BWI ═══ */
// Bottone "🔓 Sblocca Email" in header (solo layer importatori — vedi switchLayer in js/init.js).
// L'anteprima (quanti contatti, quanti crediti) è calcolata qui, client-side, con la STESSA
// logica di filtro/priorità dello script server-side (target_contacts()/best_person() in
// scripts/unlock_leads_bulk.py, che riusa lo stesso JOB_PRIORITY di getPriorityScore() già in
// js/email.js) — per non mostrare un numero diverso da quello che poi lo sblocco reale produce.
// Endpoint BWI (unlockLead/) scoperto il 22/9/2026 ispezionando il Network tab del browser.

// Aziende candidate: matchano raccomandato+stelle, hanno almeno una persona in scheda
// (c.contacts[]) ma NESSUNA con email già nota (mai sbloccata prima — non rispende crediti).
function _unlockCandidati(raccomandato, stelleSet){
  return db.contacts.filter(c=>{
    const r=c.research;
    if(!r || r.raccomandato!==raccomandato) return false;
    if(!stelleSet.has(r.affidabilita)) return false;
    const persone=c.contacts||[];
    if(!persone.length) return false;
    if(persone.some(p=>(p.email||'').trim()||(p.emailSospetta||'').trim())) return false;
    // Già pagato una volta ma BWI non ha l'email (LOG_SENZA_EMAIL in scripts/unlock_leads_bulk.py): non ritentare.
    if((c.log||[]).some(l=>(l.msg||'').includes('🔓 Sblocco BWI senza email'))) return false;
    return true;
  });
}

function apriSbloccaEmail(){
  if(isClienti()){ toast('Disponibile solo per Importatori'); return; }
  showModal(`
    <div class="mt">🔓 Sblocca email BWI</div>
    <div style="font-size:12px;color:var(--text2);margin-bottom:14px">Sblocca l'email del contatto con la priorità di ruolo più alta (buyer &gt; sales &gt; direttore &gt; proprietario) per ogni azienda che matcha i filtri sotto. 1 credito BWI per sblocco.</div>
    <div class="fg">
      <label>Categoria</label>
      <select id="unlk-racc" onchange="aggiornaAnteprimaSblocca()">
        <option value="si">✅ Raccomandati (si)</option>
        <option value="forse">❓ Forse</option>
      </select>
    </div>
    <div class="fg">
      <label>Stelle</label>
      <div style="display:flex;gap:12px;flex-wrap:wrap">
        ${[1,2,3,4,5].map(s=>`<label style="display:flex;align-items:center;gap:4px;font-size:13px;cursor:pointer">
          <input type="checkbox" class="unlk-stelle" value="${s}" onchange="aggiornaAnteprimaSblocca()" ${s>=4?'checked':''}> ${s}⭐
        </label>`).join('')}
      </div>
    </div>
    <div class="fg">
      <label>Massimo crediti da spendere</label>
      <input type="number" id="unlk-max" min="1" step="1" placeholder="tutti" oninput="aggiornaAnteprimaSblocca()" style="width:140px">
      <div style="font-size:11px;color:var(--text3);margin-top:4px">Vuoto = tutti quelli trovati. Con un tetto si parte dalle aziende con più stelle.</div>
    </div>
    <div id="unlk-preview" style="padding:10px 12px;border-radius:var(--r);background:var(--bg2);font-size:13px;margin:4px 0 14px"></div>
    <div style="display:flex;gap:8px">
      <button class="btn btp bts" id="unlk-btn-avvia" onclick="avviaSbloccaEmail()">🔓 Avvia sblocco</button>
      <button class="btn btg bts" onclick="closeModal()">Annulla</button>
    </div>
  `);
  aggiornaAnteprimaSblocca();
}

// Tetto crediti scelto nel popup: vuoto/0/non valido = nessun tetto (tutti i candidati).
function _unlockTetto(n){
  const v=parseInt(document.getElementById('unlk-max')?.value,10);
  return (v>0) ? Math.min(v,n) : n;
}

function aggiornaAnteprimaSblocca(){
  const racc=document.getElementById('unlk-racc')?.value;
  const stelleSet=new Set([...document.querySelectorAll('.unlk-stelle:checked')].map(el=>parseInt(el.value,10)));
  const el=document.getElementById('unlk-preview');
  const btn=document.getElementById('unlk-btn-avvia');
  if(!racc || !stelleSet.size){
    if(el) el.innerHTML='Seleziona almeno una fascia di stelle.';
    if(btn) btn.disabled=true;
    return;
  }
  const n=_unlockCandidati(racc, stelleSet).length;
  const tetto=_unlockTetto(n);
  if(el) el.innerHTML = !n
    ? `Nessun contatto trovato con questi filtri (o hanno già tutti l'email nota).`
    : tetto<n
      ? `📊 <strong>${n}</strong> contatti trovati — ne sblocchi <strong>${tetto}</strong> (i più stellati), costo massimo <strong>${tetto} crediti</strong> BWI.`
      : `📊 <strong>${n}</strong> contatti da sbloccare — costo stimato <strong>${n} crediti</strong> BWI (1 a testa).`;
  if(btn) btn.disabled = (n===0);
}

async function avviaSbloccaEmail(){
  const racc=document.getElementById('unlk-racc')?.value;
  const stelleSet=new Set([...document.querySelectorAll('.unlk-stelle:checked')].map(el=>parseInt(el.value,10)));
  const n=_unlockCandidati(racc, stelleSet).length;
  if(!n){ toast('Nessun contatto da sbloccare con questi filtri'); return; }
  const tetto=_unlockTetto(n);
  if(!confirm(`Confermi lo sblocco di ${tetto} contatti${tetto<n?` (su ${n} trovati)`:''} — massimo ${tetto} crediti BWI? Parte su GitHub Actions, può richiedere tempo — puoi chiudere la pagina, prosegue comunque sul server.`)) return;

  const job={ raccomandato:racc, stelle:[...stelleSet], maxCredits:tetto, status:'pending', createdAt:Date.now() };
  try{
    await pushUnlockJob(job);
  }catch(e){ toast('⚠ Salvataggio job fallito: '+e.message); return; }

  const ok=await triggerUnlockWorkflow();
  if(!ok){ toast('⚠ Avvio workflow fallito'); return; }

  closeModal();
  toast(`🔓 Sblocco avviato (max ${tetto} contatti) — ti avviso quando finisce`);

  const finalJob=await pollUnlockWorkflow();
  if(finalJob && finalJob.result){
    const {unlocked, failed, skipped, stopReason}=finalJob.result;
    toast(`✅ Sblocco completato: ${unlocked} sbloccate, ${failed} fallite, ${skipped} saltate${stopReason?' — '+stopReason:''}`);
    if(typeof loadFromGH==='function') loadFromGH();  // ricarica per vedere le nuove email
  } else {
    toast('⏱ Sblocco ancora in corso o monitoraggio scaduto — controlla su GitHub Actions o riapri il CRM tra qualche minuto');
  }
}
