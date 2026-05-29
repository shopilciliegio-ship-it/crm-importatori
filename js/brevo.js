/* ═══ BREVO ═══ */

const BREVO_STATUS = {
  sent:         { l:'📤 Inviata',        bg:'var(--blue-bg)',  tx:'var(--blue-tx)' },
  delivered:    { l:'✓ Consegnata',      bg:'var(--green-bg)', tx:'var(--green-tx)' },
  opened:       { l:'👁 Aperta',          bg:'var(--amber-bg)',tx:'var(--amber-tx)' },
  clicked:      { l:'🔗 Link cliccato',  bg:'var(--pink-bg)', tx:'var(--pink-tx)' },
  bounced:      { l:'⚠ Bounce',          bg:'var(--red-bg)',  tx:'var(--red-tx)' },
  spam:         { l:'🚫 Spam',           bg:'var(--red-bg)',  tx:'var(--red-tx)' },
  unsubscribed: { l:'🚫 Disiscritto',    bg:'var(--red-bg)',  tx:'var(--red-tx)' },
  blocked:      { l:'🔒 Bloccata',       bg:'var(--gray-bg)', tx:'var(--gray-tx)' },
};

function getBrevoStatus(ev){
  if(!ev) return 'sent';
  if(ev.spam)         return 'spam';
  if(ev.bounced)      return 'bounced';
  if(ev.blocked)      return 'blocked';
  if(ev.unsubscribed) return 'unsubscribed';
  if(ev.clicked)      return 'clicked';
  if(ev.opened)       return 'opened';
  if(ev.delivered)    return 'delivered';
  return 'sent';
}

function breveStatusBadge(ev){
  const s = BREVO_STATUS[getBrevoStatus(ev)] || BREVO_STATUS.sent;
  return `<span class="badge" style="background:${s.bg};color:${s.tx};font-size:11px">${s.l}</span>`;
}

// Mini-icone nella lista contatti (ultima email)
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

async function syncBrevoEvents(){
  if(!brv.apiKey){ toast('Configura prima Brevo nelle impostazioni'); return; }
  const adb = isClienti()?dbC:db;

  const toSync=[];
  adb.contacts.forEach(c=>{
    (c.brevoEvents||[]).forEach((ev,i)=>{
      if(ev.messageId) toSync.push({contact:c, evIdx:i, messageId:ev.messageId});
    });
  });

  if(!toSync.length){ toast('Nessuna email tracciata — invia prima qualche email'); return; }

  toast(`🔄 Sincronizzazione ${toSync.length} email...`);
  let updated=0;

  for(const {contact, evIdx, messageId} of toSync){
    try{
      const r=await fetch(
        `https://api.brevo.com/v3/smtp/statistics/events?messageId=${encodeURIComponent(messageId)}&limit=50`,
        {headers:{'api-key':brv.apiKey,'Accept':'application/json'}}
      );
      if(!r.ok) continue;
      const data=await r.json();
      const events=data.events||[];

      const ev=contact.brevoEvents[evIdx];
      let changed=false;

      events.forEach(e=>{
        const type=(e.event||'').toLowerCase();
        if((type==='delivered'||type==='requests')&&!ev.delivered){
          ev.delivered=true; ev.deliveredAt=e.date; changed=true;
        }
        if((type==='opened'||type==='unique_opened')&&!ev.opened){
          ev.opened=true; ev.openedAt=e.date; changed=true;
          if(!contact.log.some(l=>l.msg.includes('👁 Aperta')&&l.msg.includes((ev.subject||'').slice(0,20)))){
            contact.log.push({ts:new Date(e.date).getTime()||Date.now(),msg:`👁 Aperta: ${ev.subject||''}`});
          }
        }
        if((type==='clicks'||type==='click')&&!ev.clicked){
          ev.clicked=true; ev.clickedAt=e.date; changed=true;
          if(!contact.log.some(l=>l.msg.includes('🔗 Click'))){
            contact.log.push({ts:new Date(e.date).getTime()||Date.now(),msg:`🔗 Click: ${ev.subject||''}`});
          }
        }
        if((type==='hardbounces'||type==='softbounces'||type==='bounced')&&!ev.bounced){
          ev.bounced=true; ev.bouncedAt=e.date; changed=true;
          contact.log.push({ts:Date.now(),msg:`⚠ Bounce: ${ev.subject||''}`});
        }
        if((type==='spamreports'||type==='spam')&&!ev.spam){
          ev.spam=true; changed=true;
          contact.log.push({ts:Date.now(),msg:`🚫 Spam: ${ev.subject||''}`});
        }
        if(type==='unsubscribed'&&!ev.unsubscribed){
          ev.unsubscribed=true; changed=true;
          contact.log.push({ts:Date.now(),msg:`🚫 Disiscritto: ${ev.subject||''}`});
        }
        if((type==='blocked'||type==='invalid')&&!ev.blocked){
          ev.blocked=true; changed=true;
          contact.log.push({ts:Date.now(),msg:`🔒 Bloccata: ${ev.subject||''}`});
        }
      });

      if(changed) updated++;

    }catch(e){ console.warn('Brevo sync error:',e); }
    await new Promise(r=>setTimeout(r,120));
  }

  saveDB();
  refreshAll();
  toast(updated>0
    ?`✓ Sync Brevo: ${updated} email aggiornate su ${toSync.length}`
    :`📊 Sync OK — ${toSync.length} email verificate, nessun nuovo evento`
  );
}
