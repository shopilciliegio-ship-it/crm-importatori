/* ═══ BREVO ═══ */

async function syncBrevoEvents(){
  if(!brv.apiKey){ toast('Configura prima Brevo nelle impostazioni'); return; }
  const adb = isClienti()?dbC:db;

  // Raccogli tutti i messageId da sincronizzare
  const toSync = [];
  adb.contacts.forEach(c=>{
    (c.brevoEvents||[]).forEach((ev,i)=>{
      if(ev.messageId) toSync.push({contact:c, evIdx:i, messageId:ev.messageId});
    });
  });

  if(!toSync.length){ toast('Nessuna email da sincronizzare'); return; }

  toast(`🔄 Sincronizzazione ${toSync.length} email...`);
  let updated=0;

  for(const {contact, evIdx, messageId} of toSync){
    try{
      // Recupera eventi per questo messageId
      // Prima prova con messageId diretto
      const r=await fetch(
        `https://api.brevo.com/v3/smtp/emails/${encodeURIComponent(messageId)}`,
        {headers:{'api-key':brv.apiKey,'Accept':'application/json'}}
      );
      if(!r.ok) continue;
      const emailData=await r.json();
      // Brevo restituisce eventi come array "events" o come campi diretti
      const events=emailData.events||[];
      // Aggiorna anche da campi diretti se presenti
      if(emailData.status) events.push({event: emailData.status, date: emailData.date});

      const ev=contact.brevoEvents[evIdx];
      let changed=false;

      events.forEach(e=>{
        const type=(e.event||e.eventType||e.type||'').toLowerCase();
        if((type==='delivered'||type==='request')&&!ev.delivered){ ev.delivered=true; ev.deliveredAt=e.date; changed=true; }
        if((type==='opened'||type==='unique_opened')&&!ev.opened){ ev.opened=true; ev.openedAt=e.date; changed=true;
          // Prima apertura → aggiorna log
          if(!contact.log.some(l=>l.msg.includes('👁 Aperta')&&l.msg.includes(ev.subject?.slice(0,20)||''))){
            contact.log.push({ts:new Date(e.date).getTime()||Date.now(), msg:`👁 Aperta: ${ev.subject||''}`});
          }
        }
        if(type==='clicks'||type==='click') { ev.clicked=true; ev.clickedAt=e.date; changed=true;
          if(!contact.log.some(l=>l.msg.includes('🔗 Click'))){
            contact.log.push({ts:new Date(e.date).getTime()||Date.now(), msg:`🔗 Click: ${ev.subject||''}`});
          }
        }
        if(type==='bounced'||type==='hardBounce'||type==='softBounce'){
          ev.bounced=true; ev.bouncedAt=e.date; changed=true;
          contact.log.push({ts:Date.now(), msg:`⚠ Bounce: ${ev.subject||''}`});
        }
        if(type==='spam'){ ev.spam=true; changed=true;
          contact.log.push({ts:Date.now(), msg:`🚫 Spam: ${ev.subject||''}`});
        }
      });

      if(changed) updated++;

    } catch(e){ console.warn('Brevo sync error:', e); }

    // Piccola pausa per non saturare l'API
    await new Promise(r=>setTimeout(r,150));
  }

  saveDB();
  refreshAll();
  if(updated>0){
    toast(`✓ Sync Brevo: ${updated} email con nuovi eventi`);
  } else if(toSync.length>0){
    toast(`📊 Sync OK — ${toSync.length} email verificate, nessun nuovo evento`);
  } else {
    toast('ℹ Nessuna email tracciata — invia prima qualche email');
  }
}

// Badge eventi Brevo nella scheda contatto

function breveEventsBadge(c){
  const evs=c.brevoEvents||[];
  if(!evs.length) return '';
  const last=evs[evs.length-1];
  const icons=[];
  if(last.delivered) icons.push('<span title="Consegnata" style="color:#27ae60">✓</span>');
  if(last.opened)    icons.push('<span title="Aperta" style="color:#2980b9">👁</span>');
  if(last.clicked)   icons.push('<span title="Link cliccato" style="color:#8e44ad">🔗</span>');
  if(last.bounced)   icons.push('<span title="Bounce" style="color:#e74c3c">⚠</span>');
  if(last.spam)      icons.push('<span title="Spam" style="color:#e74c3c">🚫</span>');
  return icons.length
    ? `<span style="font-size:14px;margin-left:6px">${icons.join('')}</span>`
    : '';
}

/* ═══════════════════════════════════════════════════
   INVIO MASSIVO
═══════════════════════════════════════════════════ */