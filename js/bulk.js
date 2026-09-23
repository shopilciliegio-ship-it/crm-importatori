/* ═══ BULK ═══ */

function openBulkSend(){
  if(!sel.size){toast('Nessun contatto selezionato');return;}
  const contacts=(isClienti()?dbC:db).contacts.filter(c=>sel.has(c.id));
  // Clienti Privati: invia sempre prima ai registrati più vecchi
  if(isClienti()) contacts.sort((a,b)=>(a.registeredAt||0)-(b.registeredAt||0));
  const withEmail=contacts.filter(c=>c.contactEmail||c.email);
  const noEmail=contacts.filter(c=>!c.contactEmail&&!c.email);

  // Esempio per anteprima: primo contatto con email
  const example=withEmail[0];

  showModal(`
    <div class="mt">✉ Invio massivo — ${contacts.length} contatti</div>

    <div style="display:flex;gap:8px;margin-bottom:14px">
      <div style="flex:1;background:var(--green-bg);border-radius:var(--r);padding:10px;text-align:center">
        <div style="font-size:22px;font-weight:700;color:var(--green-tx)">${withEmail.length}</div>
        <div style="font-size:11px;color:var(--green-tx);font-weight:600">Con email</div>
      </div>
      ${noEmail.length?`<div style="flex:1;background:var(--amber-bg);border-radius:var(--r);padding:10px;text-align:center">
        <div style="font-size:22px;font-weight:700;color:var(--amber-tx)">${noEmail.length}</div>
        <div style="font-size:11px;color:var(--amber-tx);font-weight:600">Senza email (saltati)</div>
      </div>`:''}
    </div>

    <!-- BRAND -->
    ${!isClienti()?`<div style="display:flex;gap:8px;margin-bottom:14px">
      <button id="bulk-sw" onclick="bulkSelectBrand('sienawine')"
        style="flex:1;padding:10px;border-radius:var(--r);border:2px solid #8B1A1A;background:#1a1a1a;color:#fff;cursor:pointer;font-size:12px;font-weight:700">
        🍷 Siena Wine
      </button>
      <button id="bulk-cil" onclick="bulkSelectBrand('ciliegio')"
        style="flex:1;padding:10px;border-radius:var(--r);border:2px solid var(--brd2);background:var(--bg2);color:var(--text);cursor:pointer;font-size:12px;font-weight:700">
        ☀ Il Ciliegio
      </button>
    </div>`:''}
    <input type="hidden" id="bulk-brand" value="${isClienti()?'ciliegio':'sienawine'}">

    <!-- TEMPLATE -->
    <div class="fg" style="margin-bottom:8px"><label>Template</label>
      <select id="bulk-tpl" onchange="updateBulkPreview()">
        ${(isClienti()?dbC:db).templates.map((t,i)=>`<option value="${i}">${esc(t.name)}</option>`).join('')}
      </select>
    </div>

    <div class="fg" style="margin-bottom:8px"><label>Oggetto</label>
      <input id="bulk-subj" value="${esc((isClienti()?dbC:db).templates[0]?.subject||'')}">
    </div>

    <!-- DELAY -->
    <div class="fg" style="margin-bottom:12px">
      <label>Delay tra email (secondi) — aspetto casuale tra 1 e 2 sec</label>
      <div style="display:flex;align-items:center;gap:8px;font-size:13px;color:var(--text2)">
        <span>Min:</span>
        <input id="bulk-dmin" type="number" value="1" min="0.5" max="5" step="0.5" style="width:70px">
        <span>Max:</span>
        <input id="bulk-dmax" type="number" value="2" min="1" max="10" step="0.5" style="width:70px">
        <span>secondi</span>
      </div>
    </div>

    ${example?`
    <!-- ANTEPRIMA -->
    <div style="font-size:12px;color:var(--text2);margin-bottom:6px;font-weight:600">
      ANTEPRIMA (su: ${esc(example.company)})
    </div>
    <div style="border:0.5px solid var(--brd2);border-radius:var(--r);overflow:auto;max-height:320px;margin-bottom:12px">
      <div id="bulk-preview" style="min-height:200px;overflow:auto"></div>
    </div>`:''}

    <div class="mf">
      <button class="btn" onclick="closeModal()">Annulla</button>
      <button class="btn btp" onclick="confirmBulkSend()" ${!withEmail.length?'disabled':''}>
        ✉ Invia a ${withEmail.length} contatti
      </button>
    </div>
  `);

  // Popola anteprima dopo render
  setTimeout(()=>updateBulkPreview(), 100);
}

function bulkSelectBrand(brand){
  document.getElementById('bulk-brand').value=brand;
  const sw=document.getElementById('bulk-sw');
  const cil=document.getElementById('bulk-cil');
  if(brand==='sienawine'){
    sw.style.cssText='flex:1;padding:10px;border-radius:8px;border:2px solid #8B1A1A;background:#1a1a1a;color:#fff;cursor:pointer;font-size:12px;font-weight:700';
    cil.style.cssText='flex:1;padding:10px;border-radius:8px;border:2px solid var(--brd2);background:var(--bg2);color:var(--text);cursor:pointer;font-size:12px;font-weight:700';
  } else {
    cil.style.cssText='flex:1;padding:10px;border-radius:8px;border:2px solid #B8941A;background:#2c2c2c;color:#fff;cursor:pointer;font-size:12px;font-weight:700';
    sw.style.cssText='flex:1;padding:10px;border-radius:8px;border:2px solid var(--brd2);background:var(--bg2);color:var(--text);cursor:pointer;font-size:12px;font-weight:700';
  }
  updateBulkPreview();
}

function updateBulkPreview(){
  const tplIdx=parseInt(document.getElementById('bulk-tpl')?.value||'0');
  const brand=document.getElementById('bulk-brand')?.value||'sienawine';
  const t=(isClienti()?dbC:db).templates[tplIdx];
  if(!t) return;

  // Aggiorna oggetto
  const subjEl=document.getElementById('bulk-subj');
  if(subjEl&&!subjEl.dataset.edited) subjEl.value=t.subject;

  // Aggiorna anteprima con primo contatto disponibile
  const adb2=isClienti()?dbC:db;
  const example=
    adb2.contacts.find(c=>sel.has(c.id)&&(c.contactEmail||c.email||c.contacts?.length))||
    adb2.contacts.find(c=>c.company&&(c.contactEmail||c.email||c.contacts?.length))||
    adb2.contacts[0];
  const prevDiv=document.getElementById('bulk-preview');
  if(!prevDiv||!example) return;
  const filled=fillTplForContact(t.body, example);
  const b3=BRANDS[brand]||BRANDS.sienawine;
  const paras3=filled.split('\n\n').filter(p=>p.trim());
  const bh3=paras3.map(p=>'<p style="margin:0 0 10px;line-height:1.6;color:#333;font-size:13px">'+
    esc(p).replace(/\n/g,'<br>')+'</p>').join('');
  prevDiv.innerHTML=
    '<div style="background:#f4f4f0;padding:14px;font-family:Georgia,serif">'+
    '<div style="background:'+b3.bgColor+';padding:14px;text-align:center;border-radius:6px 6px 0 0">'+
    '<img src="'+b3.logoUrl+'" height="36" alt="'+b3.name+'" style="max-height:36px" onerror="this.style.display=\'none\'">'+
    '</div>'+
    '<div style="background:'+b3.accentColor+';height:2px"></div>'+
    '<div style="background:#fff;padding:20px 24px">'+bh3+'</div>'+
    '</div>';
}

async function confirmBulkSend(){
  if(!brv.apiKey){toast('Configura prima Brevo nelle impostazioni');openSettings();return;}
  const tplIdx=parseInt(document.getElementById('bulk-tpl')?.value||'0');
  const brand=document.getElementById('bulk-brand')?.value||'sienawine';
  const subjTemplate=document.getElementById('bulk-subj')?.value||(isClienti()?dbC:db).templates[tplIdx]?.subject||'';
  const bodyTemplate=(isClienti()?dbC:db).templates[tplIdx]?.body||'';
  const dMin=parseFloat(document.getElementById('bulk-dmin')?.value||'1')*1000;
  const dMax=parseFloat(document.getElementById('bulk-dmax')?.value||'2')*1000;

  const contacts=(isClienti()?dbC:db).contacts.filter(c=>sel.has(c.id));
  // Clienti Privati: invia sempre prima ai registrati più vecchi
  if(isClienti()) contacts.sort((a,b)=>(a.registeredAt||0)-(b.registeredAt||0));
  const withEmail=contacts.filter(c=>c.contactEmail||c.email);
  const noEmail=contacts.filter(c=>!c.contactEmail&&!c.email);

  closeModal();

  // Importatori: invio lato server (GitHub Actions) — niente loop nel browser.
  // Il tab può essere chiuso subito dopo l'avvio: lo script gira comunque e
  // salva lo stato progressivamente, invece di dipendere da un salvataggio
  // "debounced" nel browser che si perde se la sessione si interrompe
  // (vedi incidente 18-19/09/2026: 1230 invii reali mai salvati nel CRM).
  if(!isClienti()){
    if(!withEmail.length){ toast('Nessun contatto con email da inviare'); sel.clear(); refreshAll(); return; }
    await startImportatoriBulkSend({
      contactIds: withEmail.map(c=>c.id),
      templateIndex: tplIdx,
      subject: subjTemplate,
      brand,
      delayMin: dMin/1000,
      delayMax: dMax/1000,
    }, noEmail.length);
    sel.clear();
    refreshAll();
    return;
  }

  // Clienti: invio dal browser (comportamento invariato)
  // Mostra progress overlay
  const prog=document.createElement('div');
  prog.className='send-prog';
  prog.id='bulk-prog';
  prog.innerHTML=`
    <div class="send-prog-box">
      <div style="font-size:16px;font-weight:700;margin-bottom:8px">Invio in corso…</div>
      <div style="font-size:13px;color:var(--text2)" id="prog-status">Preparazione…</div>
      <div class="prog-bar-track"><div class="prog-bar-fill" id="prog-fill" style="width:0%"></div></div>
      <div style="font-size:12px;color:var(--text3)" id="prog-counter">0 / ${withEmail.length}</div>
      <button class="btn btd bts" style="margin-top:16px" onclick="window._stopBulk=true">✕ Interrompi</button>
    </div>`;
  document.body.appendChild(prog);
  window._stopBulk=false;

  const results={sent:[],failed:[],skipped:noEmail};

  for(let i=0;i<withEmail.length;i++){
    if(window._stopBulk) break;

    const c=withEmail[i];
    const toEmail=c.contactEmail||c.email;
    const toName=c.contactName||c.name||'';
    const subject=fillTplForContact(subjTemplate,c,toEmail);
    const body=fillTplForContact(bodyTemplate,c,toEmail);

    // Aggiorna UI
    document.getElementById('prog-status').textContent=
      `Invio a ${esc(c.company)} (${esc(toEmail)})…`;
    document.getElementById('prog-fill').style.width=`${Math.round(i/withEmail.length*100)}%`;
    document.getElementById('prog-counter').textContent=`${i} / ${withEmail.length}`;

    const result=await sendViaBrevo(c.id, toEmail, toName, subject, body, brand);
    if(result?.ok) results.sent.push({c, email:toEmail});
    else results.failed.push({c, email:toEmail, error:result?.error});

    // Delay casuale tra min e max
    if(i < withEmail.length-1 && !window._stopBulk){
      const delay=dMin+Math.random()*(dMax-dMin);
      await new Promise(r=>setTimeout(r,delay));
    }
  }

  // Rimuovi progress overlay
  document.getElementById('bulk-prog')?.remove();
  sel.clear();
  refreshAll();
  showBulkReport(results, window._stopBulk);
}

/* ── BULK IMPORTATORI — invio server-side (GitHub Actions) ── */

async function startImportatoriBulkSend(job, skippedCount){
  const total=job.contactIds.length;
  const prog=document.createElement('div');
  prog.className='send-prog';
  prog.id='bulk-prog';
  prog.innerHTML=`
    <div class="send-prog-box">
      <div style="font-size:16px;font-weight:700;margin-bottom:8px">Invio massivo sul server</div>
      <div style="font-size:13px;color:var(--text2)" id="prog-status">Avvio del workflow…</div>
      <div class="prog-bar-track"><div class="prog-bar-fill" id="prog-fill" style="width:0%"></div></div>
      <div style="font-size:12px;color:var(--text3)" id="prog-counter">0 / ${total}</div>
      <div style="font-size:11px;color:var(--text3);margin-top:10px;line-height:1.5">
        L'invio gira su GitHub Actions, non nel browser — puoi chiudere<br>questa pagina in qualsiasi momento, l'invio continua comunque.
      </div>
    </div>`;
  document.body.appendChild(prog);

  const setStatus=(msg)=>{ const el=document.getElementById('prog-status'); if(el) el.textContent=msg; };
  const setProgress=(sent,failed,tot)=>{
    const done=sent+failed;
    const fill=document.getElementById('prog-fill');
    const cnt=document.getElementById('prog-counter');
    if(fill) fill.style.width=`${Math.round(done/tot*100)}%`;
    if(cnt) cnt.textContent=`${done} / ${tot}`;
  };

  try{
    setStatus('Salvo il job su GitHub…');
    await pushBulkJobImportatori(job);

    setStatus('Avvio il workflow GitHub Actions…');
    const dispatched=await triggerImportatoriBulkWorkflow();
    if(!dispatched){
      document.getElementById('bulk-prog')?.remove();
      toast('⚠ Errore avvio workflow — controlla token/permessi GitHub');
      return;
    }

    setStatus('In corso sul server…');
    const finalJob=await pollImportatoriBulkWorkflow((p)=>{
      if(p) setProgress(p.sent||0, p.failed||0, p.total||total);
    });

    document.getElementById('bulk-prog')?.remove();
    showBulkReportServer(finalJob, total, skippedCount);
  }catch(e){
    document.getElementById('bulk-prog')?.remove();
    toast('⚠ '+e.message);
    console.error('startImportatoriBulkSend:',e);
  }
}

function showBulkReportServer(finalJob, total, skippedCount){
  if(!finalJob){
    showModal(`
      <div class="mt">⏱ Invio ancora in corso</div>
      <p style="font-size:13px;color:var(--text2);line-height:1.6">
        Il workflow sta ancora girando sul server (batch grande, o GitHub Actions
        più lento del solito). Non è un problema: puoi chiudere questa finestra
        tranquillamente — riceverai un'email di resoconto a fine invio, e potrai
        anche solo ricaricare il CRM più tardi.
      </p>
      <div class="mf"><button class="btn btp" onclick="closeModal()">Ho capito</button></div>
    `);
    return;
  }
  const p=finalJob.progress||{};
  const sent=p.sent||0, failed=p.failed||0, skipped=(p.skipped||0)+ (skippedCount||0);
  const errored=finalJob.status==='error';

  showModal(`
    <div class="mt">${errored?'✗ Invio terminato con errore':'✓ Invio completato'}</div>
    ${errored?`<p style="font-size:13px;color:var(--red-tx);margin-bottom:12px">${esc(finalJob.error||'Errore sconosciuto')}</p>`:''}
    <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
      <div style="flex:1;min-width:80px;background:var(--green-bg);border-radius:var(--r);padding:12px;text-align:center">
        <div style="font-size:26px;font-weight:700;color:var(--green-tx)">${sent}</div>
        <div style="font-size:11px;color:var(--green-tx);font-weight:600">Inviate</div>
      </div>
      ${failed?`<div style="flex:1;min-width:80px;background:var(--red-bg);border-radius:var(--r);padding:12px;text-align:center">
        <div style="font-size:26px;font-weight:700;color:var(--red-tx)">${failed}</div>
        <div style="font-size:11px;color:var(--red-tx);font-weight:600">Fallite</div>
      </div>`:''}
      ${skipped?`<div style="flex:1;min-width:80px;background:var(--amber-bg);border-radius:var(--r);padding:12px;text-align:center">
        <div style="font-size:26px;font-weight:700;color:var(--amber-tx)">${skipped}</div>
        <div style="font-size:11px;color:var(--amber-tx);font-weight:600">Saltati/mancanti</div>
      </div>`:''}
    </div>
    <p style="font-size:12px;color:var(--text3);line-height:1.5">
      Riceverai anche un'email di resoconto a ${esc(finalJob.digestRecipient||'luca@ilciliegio.com')}.
      Ricarica i contatti (↻) per vedere gli stati aggiornati.
    </p>
    <div class="mf"><button class="btn btp" onclick="closeModal()">Chiudi</button></div>
  `);
}

function showBulkReport(results, interrupted){
  const {sent, failed, skipped}=results;
  const sentRows=sent.slice(0,50).map(({c,email})=>`
    <tr><td>✓</td><td>${esc(c.company)}</td><td style="color:var(--text2)">${esc(email)}</td></tr>`).join('');
  const failRows=failed.map(({c,email,error})=>`
    <tr><td style="color:var(--red)">✗</td><td>${esc(c.company)}</td><td style="color:var(--red-tx);font-size:11px">${esc(error||'')}</td></tr>`).join('');
  const skipRows=skipped.map(c=>`
    <tr><td style="color:var(--amber)">—</td><td>${esc(c.company)}</td><td style="color:var(--text3)">email mancante</td></tr>`).join('');

  showModal(`
    <div class="mt">${interrupted?'⚠ Invio interrotto':'✓ Invio completato'}</div>
    <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
      <div style="flex:1;min-width:80px;background:var(--green-bg);border-radius:var(--r);padding:12px;text-align:center">
        <div style="font-size:26px;font-weight:700;color:var(--green-tx)">${sent.length}</div>
        <div style="font-size:11px;color:var(--green-tx);font-weight:600">Inviate</div>
      </div>
      ${failed.length?`<div style="flex:1;min-width:80px;background:var(--red-bg);border-radius:var(--r);padding:12px;text-align:center">
        <div style="font-size:26px;font-weight:700;color:var(--red-tx)">${failed.length}</div>
        <div style="font-size:11px;color:var(--red-tx);font-weight:600">Fallite</div>
      </div>`:''}
      ${skipped.length?`<div style="flex:1;min-width:80px;background:var(--amber-bg);border-radius:var(--r);padding:12px;text-align:center">
        <div style="font-size:26px;font-weight:700;color:var(--amber-tx)">${skipped.length}</div>
        <div style="font-size:11px;color:var(--amber-tx);font-weight:600">Saltati</div>
      </div>`:''}
    </div>

    ${sent.length||failed.length||skipped.length?`
    <div style="max-height:280px;overflow-y:auto;border-radius:var(--r);border:0.5px solid var(--brd)">
      <table style="width:100%;font-size:12px;border-collapse:collapse">
        <thead><tr style="background:var(--bg2)">
          <th style="padding:6px 8px;text-align:left;width:24px"></th>
          <th style="padding:6px 8px;text-align:left">Azienda</th>
          <th style="padding:6px 8px;text-align:left">Email / Nota</th>
        </tr></thead>
        <tbody>
          ${sentRows}${failRows}${skipRows}
          ${sent.length>50?`<tr><td colspan="3" style="padding:8px;text-align:center;color:var(--text2)">…e altri ${sent.length-50} inviati</td></tr>`:''}
        </tbody>
      </table>
    </div>`:''}

    <div class="mf">
      <button class="btn btp" onclick="closeModal()">Chiudi</button>
    </div>
  `);
}