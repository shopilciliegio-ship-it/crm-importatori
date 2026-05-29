/* ═══ EMAIL ═══ */

function getPriorityScore(title){
  if(!title) return 99;
  const t = title.toLowerCase();
  for(const [p, titles] of Object.entries(JOB_PRIORITY)){
    if(titles.some(pt => t.includes(pt) || pt.includes(t))) return parseInt(p);
  }
  return 98; // ha un titolo ma non è nella lista → usa comunque
}

function selectBestContact(contacts){
  if(!contacts || !contacts.length) return {primary:null, secondary:null};

  // Assegna punteggio a ogni contatto
  const scored = contacts
    .filter(c => c.name || c.email)
    .map(c => ({...c, score: getPriorityScore(c.title)}))
    .sort((a,b) => a.score - b.score);

  if(!scored.length) return {primary:null, secondary:null};

  const primary = scored[0];

  // Secondary: cerca il contatto con priorità più alta DIVERSO dal primary
  // Logica:
  // - Se primary è P1 → secondary è il primo P2 o P3 (owner/manager da menzionare)
  // - Se primary è P2 → secondary è il primo P3 (owner da menzionare)
  // - Se primary è P3 → nessun secondary (owner scrive a se stesso)
  let secondary = null;
  if(primary.score <= 1){
    // Primary è P1 → cerca P2 o P3 come secondary
    secondary = scored.find(c => c !== primary && c.score >= 2) || null;
  } else if(primary.score <= 2){
    // Primary è P2 → cerca P3 come secondary
    secondary = scored.find(c => c !== primary && c.score >= 3) || null;
  }

  return {primary, secondary};
}

// Estrae solo il PRIMO NOME da un nome completo

function firstName(fullName){
  if(!fullName) return '';
  const parts = fullName.trim().split(/\s+/);
  return parts[0] || '';
}

// Costruisce la riga di apertura personalizzata
// No contact  → Esteemed [Company] Team,
// 1+ contacts → Dear [Name] from [Company],

function buildDearLine(primary, secondary, companyName){
  if(!primary || !primary.name){
    return `Esteemed ${companyName||''} Team,`;
  }
  const fn = firstName(primary.name);
  return `Dear ${fn} from ${companyName||''},`;
}

// Costruisce la menzione dell'owner/secondary nell'apertura

function buildOwnerMention(secondary){
  if(!secondary || !secondary.name) return '';
  const fn = firstName(secondary.name);
  return ` — and after seeing what you and ${fn} have built`;
}

// Costruisce la riga "This is something you [and NAME] know very well."

function buildKnowWell(secondary){
  if(!secondary || !secondary.name){
    return 'This is something you know very well.';
  }
  const fn = firstName(secondary.name);
  return `This is something you and ${fn} know very well.`;
}

/* ═══════════════════════════════════════════════════
   BREVO — INVIO EMAIL
═══════════════════════════════════════════════════ */

const BRANDS = {
  sienawine: {
    name: 'Siena Wine',
    senderEmail: 'luca@sienawine.it',
    senderName: 'Luca Pattaro | Siena Wine Srl',
    logoUrl: 'https://shopilciliegio-ship-it.github.io/crm-importatori/assets/logo_sienawine.png',
    logoAlt: 'Siena Wine',
    logoWidth: '160',
    accentColor: '#8B1A1A',
    bgColor: '#1a1a1a',
    website: 'https://www.sienawine.it',
    phone: '+39 331 1347899',
    tagline: 'Siena Wine: Pleasure in a bottle',
  },
  ciliegio: {
    name: 'Il Ciliegio',
    senderEmail: 'export@ilciliegio.com',
    senderName: 'Il Ciliegio — Azienda Agricola',
    logoUrl: 'https://shopilciliegio-ship-it.github.io/crm-importatori/assets/logo_ciliegio.png',
    logoAlt: 'Il Ciliegio — Azienda Agricola',
    logoWidth: '180',
    accentColor: '#B8941A',
    bgColor: '#2c2c2c',
    website: 'https://www.ilciliegio.com',
    phone: '+39 331 1347899',
    tagline: 'Vini artigianali toscani di eccellenza',
  }
};

function buildHtmlEmail(body, brand, contactName){
  try{
  const b = BRANDS[brand] || BRANDS.sienawine;
  // Nota: il greeting è già nel body via {{dear}} — non lo aggiungiamo due volte
  // Converti testo plain in paragrafi HTML
  const bodyHtml = body
    .split('\n\n')
    .map(para => para.trim())
    .filter(Boolean)
    .map(para => {
      // Lista puntata
      if(para.includes('\n•') || para.startsWith('•')){
        const items = para.split('\n').map(l=>l.trim()).filter(Boolean);
        return '<ul style="margin:0 0 16px;padding-left:20px">'+
          items.map(i=>`<li style="margin-bottom:6px;color:#333;font-size:15px;line-height:1.6">${esc(i.replace(/^[•\-]\s*/,''))}</li>`).join('')+
          '</ul>';
      }
      return `<p style="margin:0 0 16px;color:#333;font-size:15px;line-height:1.7">${esc(para).replace(/\n/g,'<br>')}</p>`;
    }).join('');

  const _html=`<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f0;font-family:Georgia,'Times New Roman',serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f0;padding:32px 16px">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">

  <!-- HEADER -->
  <tr><td style="background:${b.bgColor};border-radius:12px 12px 0 0;padding:32px;text-align:center">
    <img src="${b.logoUrl}" width="${b.logoWidth}" alt="${b.logoAlt}" style="display:block;margin:0 auto;max-width:${b.logoWidth}px">
  </td></tr>

  <!-- GOLD DIVIDER -->
  <tr><td style="background:${b.accentColor};height:4px;font-size:0">&nbsp;</td></tr>

  <!-- BODY -->
  <tr><td style="background:#ffffff;padding:40px 48px">
    ${bodyHtml}
  </td></tr>

  <!-- GOLD DIVIDER -->
  <tr><td style="background:${b.accentColor};height:3px;font-size:0">&nbsp;</td></tr>

  <!-- FOOTER -->
  <tr><td style="background:${b.bgColor};border-radius:0 0 12px 12px;padding:28px 40px;text-align:center">
    <p style="margin:0 0 8px;color:#ffffff;font-size:13px;font-weight:bold;letter-spacing:1px;text-transform:uppercase">${b.name}</p>
    <p style="margin:0 0 12px;color:${b.accentColor};font-size:12px;font-style:italic">${b.tagline}</p>
    <p style="margin:0;font-size:12px;color:#999;line-height:1.8">
      <span style="color:#cccccc">${b.website.replace('https://','')}</span>
      &nbsp;|&nbsp;
      <span style="color:#999">${b.phone}</span>
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>`;
  return _html;
  }catch(e){
    console.error('buildHtmlEmail error:',e);
    return '<html><body style="font-family:serif;padding:40px;color:#333"><p>'+
      (body||'').replace(/\n/g,'<br>')+
      '</p></body></html>';
  }
}

async function sendViaBrevo(contactId, toEmail, toName, subject, bodyText, brand){
  if(!brv.apiKey){
    toast('⚠ Configura prima Brevo nelle impostazioni');
    openSettings();
    return false;
  }
  const b = BRANDS[brand] || BRANDS.sienawine;
  const htmlContent = buildHtmlEmail(bodyText, brand, toName);

  try{
    const res = await fetch('https://api.brevo.com/v3/smtp/email',{
      method: 'POST',
      headers: {
        'api-key': brv.apiKey,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({
        sender: {
          name: brv.senderName || b.senderName,
          email: brv.senderEmail || b.senderEmail
        },
        to: [{ email: toEmail, name: toName||toEmail||'' }],
        subject: subject,
        htmlContent: htmlContent,
        textContent: bodyText.replace(/\{\{[^}]+\}\}/g,'').trim(),
        tags: ['wine-crm', brand],
        headers: { 'X-CRM-ContactId': contactId }
      })
    });

    const data = await res.json();

    if(res.ok && data.messageId){
      // Aggiorna stato contatto
      const c = (isClienti()?dbC:db).contacts.find(x=>x.id===contactId);
      if(c){
        const wasNew = c.status==='new';
        if(wasNew || c.status==='followup') c.status='sent';
        c.updatedAt = Date.now();
        c.log = c.log||[];
        c.log.push({
          ts: Date.now(),
          msg: `📧 Email inviata via Brevo — "${subject}" (ID: ${data.messageId})`
        });
        c.lastEmailSent = Date.now();
        c.lastEmailSubject = subject;
        c.emailsSent = (c.emailsSent||0) + 1;
        c.brevoEvents = c.brevoEvents||[];
        c.brevoEvents.push({
          messageId: data.messageId,
          subject,
          sentAt: Date.now(),
          toEmail,
          toName,
          brand,
          sequenceStep: c.brevoEvents.length + 1,
          delivered:false,opened:false,clicked:false,
          bounced:false,spam:false,unsubscribed:false,blocked:false
        });
        saveDB();
        refreshAll();
      }
      return {ok:true, messageId: data.messageId};
    } else {
      const errMsg = data.message || JSON.stringify(data);
      throw new Error(errMsg);
    }
  } catch(e){
    console.error('Brevo error:', e);
    toast('✗ Errore invio: '+e.message);
    return {ok:false, error:e.message};
  }
}

/* ── EMAIL ── */

function openEmailFromDetail(id){ openEmailModal(id); }

function openEmailModal(id, overrideEmail, overrideName, contactIdx){
  const adb = isClienti()?dbC:db;
  const c = adb.contacts.find(x=>x.id===id);
  if(!c) return;

  let toEmail, toName, bestPrimary=null, bestSecondary=null;

  if(isClienti()){
    toEmail = overrideEmail || c.email || '';
    toName  = overrideName  || ((c.nome||'')+' '+(c.cognome||'')).trim();
  } else {
    const {primary, secondary} = selectBestContact(c.contacts||[]);
    bestPrimary   = primary;
    bestSecondary = secondary;
    toEmail = overrideEmail || primary?.email || c.contactEmail || c.email || '';
    toName  = overrideName  || primary?.name  || c.contactName  || c.name  || '';
  }

  // Rendi disponibili per applyTpl
  window._emailCtx = { primary: bestPrimary, secondary: bestSecondary, contact: c };

  showModal(`
    <div class="mt">✉ Email — ${esc(isClienti()?(c.nome+' '+c.cognome):c.company)}</div>

    ${(!isClienti()&&c.contacts&&c.contacts.length>1)?`
    <div style="margin-bottom:12px">
      <div style="font-size:12px;color:var(--text2);font-weight:700;margin-bottom:6px">SELEZIONA DESTINATARIO</div>
      <select id="contact-sel" onchange="switchEmailContact('${c.id}')"
        style="width:100%;font-size:13px;padding:8px;border-radius:var(--r);border:.5px solid var(--brd2);background:var(--bg);color:var(--text)">
        <option value="-1">— Email aziendale (${esc(c.email||'nessuna')})</option>
        ${(c.contacts||[]).map((ct,i)=>`<option value="${i}"${bestPrimary&&ct.name===bestPrimary.name?' selected':''}>${esc(ct.name||'—')} · ${esc(ct.title||'')}${ct.email?' ('+esc(ct.email)+')':''}</option>`).join('')}
      </select>
    </div>`:''}

    <div class="fg2">
      <div class="fg fgf"><label>A</label><input id="em-to" value="${esc(toEmail)}"></div>
      <div class="fg"><label>Nome destinatario</label><input id="em-toname" value="${esc(toName)}"></div>
    </div>
    <div class="fg" style="margin-bottom:8px"><label>Template</label>
      <select id="tsel" onchange="applyTpl('${id}')">${adb.templates.map((t,i)=>`<option value="${i}">${esc(t.name)}</option>`).join('')}</select>
    </div>
    <div style="display:flex;gap:8px;margin-bottom:10px">
      <button id="bulk-sw" onclick="selectBrand('sienawine','${id}')"
        style="flex:1;padding:10px;border-radius:var(--r);border:2px solid #8B1A1A;background:#1a1a1a;color:#fff;cursor:pointer;font-size:12px;font-weight:700">
        🍷 Siena Wine
      </button>
      <button id="bulk-cil" onclick="selectBrand('ciliegio','${id}')"
        style="flex:1;padding:10px;border-radius:var(--r);border:2px solid var(--brd2);background:var(--bg2);color:var(--text);cursor:pointer;font-size:12px;font-weight:700">
        ☀ Il Ciliegio
      </button>
    </div>
    <input type="hidden" id="em-brand" value="sienawine">
    <div class="fg" style="margin-bottom:8px"><label>Oggetto</label><input id="esu"></div>
    <div class="fg" style="margin-bottom:8px"><label>Testo email</label>
      <textarea id="ebo" style="min-height:200px;font-size:13px;line-height:1.6;font-family:inherit"></textarea>
    </div>
    <div style="margin-bottom:10px">
      <button class="btn btg bts" onclick="togglePreview('${id}')" id="prev-btn">👁 Anteprima HTML</button>
    </div>
    <div id="email-preview-wrap" style="display:none;border:0.5px solid var(--brd2);border-radius:var(--r);overflow:auto;max-height:400px;margin-bottom:12px"><div id="email-preview"></div></div>
    <div class="mf">
      <button class="btn" onclick="closeModal()">Annulla</button>
      <button class="btn btg" onclick="copyEmailText()">Copia testo</button>
      <button class="btn btp" id="send-btn" onclick="doSendEmail('${id}')">
        ${brv.apiKey?'✉ Invia con Brevo':'✉ Apri client email'}
      </button>
    </div>
  `);
  applyTpl(id);
  // Apri preview automaticamente dopo aver compilato il template
  setTimeout(()=>togglePreview(id, true), 80);
}

function togglePreview(id, forceRefresh){
  const wrap=document.getElementById('email-preview-wrap');
  const btn=document.getElementById('prev-btn');
  if(!wrap) return;
  if(wrap.style.display==='none'||forceRefresh){
    const brand=document.getElementById('em-brand')?.value||'sienawine';
    const body=document.getElementById('ebo')?.value||'';
    const b=BRANDS[brand]||BRANDS.sienawine;
    const el=document.getElementById('email-preview');
    if(el && body){
      const paras=body.split('\n\n').filter(p=>p.trim());
      const bh=paras.map(p=>{
        if(p.startsWith('\u2022')||p.includes('\n\u2022')){
          return '<ul style="margin:0 0 12px;padding-left:20px">'+
            p.split('\n').filter(l=>l.trim()).map(l=>
              '<li style="margin-bottom:4px">'+esc(l.replace(/^[\u2022\-]\s*/,''))+'</li>'
            ).join('')+'</ul>';
        }
        return '<p style="margin:0 0 12px;line-height:1.7">'+
          esc(p).replace(/\n/g,'<br>')+'</p>';
      }).join('');
      el.innerHTML=
        '<div style="background:#f4f4f0;padding:20px;font-family:Georgia,serif">'+
        '<div style="max-width:540px;margin:0 auto">'+
        '<div style="background:'+b.bgColor+';padding:18px;text-align:center;border-radius:8px 8px 0 0">'+
        '<img src="'+b.logoUrl+'" height="45" alt="'+b.name+'" style="max-height:45px" '+
        'onerror="this.style.display=\'none\'">'+
        '</div>'+
        '<div style="background:'+b.accentColor+';height:3px"></div>'+
        '<div style="background:#fff;padding:28px 32px;color:#333;font-size:14px">'+bh+'</div>'+
        '<div style="background:'+b.accentColor+';height:2px"></div>'+
        '<div style="background:'+b.bgColor+';padding:14px;text-align:center;border-radius:0 0 8px 8px">'+
        '<span style="color:#fff;font-size:11px">'+b.name+'</span>'+
        '</div></div></div>';
    }
    wrap.style.display='block';
    if(btn) btn.textContent='\uD83D\uDC41 Nascondi';
  } else {
    wrap.style.display='none';
    if(btn) btn.textContent='\uD83D\uDC41 Anteprima';
  }
}

function selectBrand(brand, id){
  const brandEl=document.getElementById('em-brand');
  if(brandEl) brandEl.value=brand;
  // IDs corretti dal modal HTML
  const sw =document.getElementById('bulk-sw');
  const cil=document.getElementById('bulk-cil');
  if(sw&&cil){
    if(brand==='sienawine'){
      sw.style.cssText ='flex:1;padding:10px;border-radius:8px;border:2px solid #8B1A1A;background:#1a1a1a;color:#fff;cursor:pointer;font-size:12px;font-weight:700';
      cil.style.cssText='flex:1;padding:10px;border-radius:8px;border:2px solid var(--brd2);background:var(--bg2);color:var(--text);cursor:pointer;font-size:12px;font-weight:700';
    } else {
      cil.style.cssText='flex:1;padding:10px;border-radius:8px;border:2px solid #B8941A;background:#2c2c2c;color:#fff;cursor:pointer;font-size:12px;font-weight:700';
      sw.style.cssText ='flex:1;padding:10px;border-radius:8px;border:2px solid var(--brd2);background:var(--bg2);color:var(--text);cursor:pointer;font-size:12px;font-weight:700';
    }
  }
  const wrap=document.getElementById('email-preview-wrap');
  if(wrap&&wrap.style.display!=='none') togglePreview(id,true);
}

async function doSendEmail(id){
  const c = (isClienti()?dbC:db).contacts.find(x=>x.id===id);if(!c) return;
  const toEmail = gv('em-to');
  const toName  = gv('em-toname');
  const subject = gv('esu');
  const body    = document.getElementById('ebo').value;
  const brand   = document.getElementById('em-brand')?.value||'sienawine';

  if(!toEmail){toast('Inserisci un indirizzo email');return;}
  if(!subject){toast('Inserisci un oggetto');return;}

  if(brv.apiKey){
    // Invio via Brevo
    const btn = document.getElementById('send-btn');
    if(btn){btn.disabled=true;btn.textContent='Invio in corso…';}
    const result = await sendViaBrevo(id, toEmail, toName, subject, body, brand);
    if(result.ok){
      closeModal();
      toast(`✓ Email inviata a ${toEmail}`);
    } else {
      if(btn){btn.disabled=false;btn.textContent='✉ Invia con Brevo';}
    }
  } else {
    // Fallback: apri client email
    window.location.href=`mailto:${encodeURIComponent(toEmail)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
    if(c&&c.status==='new'){
      c.status='sent';c.updatedAt=Date.now();
      c.log=c.log||[];c.log.push({ts:Date.now(),msg:'Email aperta nel client'});
      saveDB();refreshAll();
    }
    closeModal();
  }
}

function applyTpl(id){
  const adb=isClienti()?dbC:db;
  const c=adb.contacts.find(x=>x.id===id);
  const tIdx=parseInt(document.getElementById('tsel')?.value||'0');
  const t=adb.templates[tIdx];
  if(!t||!c){return;}

  // Contesto email (impostato in openEmailModal)
  const ctx=window._emailCtx||{};
  const prim=ctx.primary||null;
  const sec=ctx.secondary||null;

  const dearLine    =buildDearLine(prim,sec,c.company);
  const ownerMention=buildOwnerMention(sec);
  const knowWell    =buildKnowWell(sec);
  const primaryName =firstName(prim?.name||c.contactName||'');
  const primaryTitle=prim?.title||c.contactTitle||'';
  const secName     =firstName(sec?.name||'');

  const f=s=>String(s||'')
    .replace(/\{\{dear\}\}/g,          dearLine)
    .replace(/\{\{owner_mention\}\}/g,  ownerMention)
    .replace(/\{\{know_well\}\}/g,      knowWell)
    .replace(/\{\{owner\}\}/g,          secName)
    .replace(/\{\{contatto\}\}/g,       primaryName||c.contactName||'')
    .replace(/\{\{nome\}\}/g,           primaryName||c.name||'')
    .replace(/\{\{job\}\}/g,            primaryTitle)
    .replace(/\{\{azienda\}\}/g,        c.company||'')
    .replace(/\{\{paese\}\}/g,          c.country||'')
    .replace(/\{\{citta\}\}/g,          c.city||'')
    .replace(/\{\{prodotti\}\}/g,       (c.products||[]).join(', ')||'');

  const subjEl=document.getElementById('esu');
  const bodyEl=document.getElementById('ebo');
  if(subjEl) subjEl.value=f(t.subject);
  if(bodyEl) bodyEl.value=f(t.body);
}

function copyEmailText(){
  const subj=gv('esu');
  const body=document.getElementById('ebo')?.value||'';
  navigator.clipboard?.writeText(`Oggetto: ${subj}\n\n${body}`).then(()=>toast('Testo copiato ✓'));
}



// Corregge le regioni sbagliate nei contatti già importati
// (es. region='Suriname' → region='Sud America')

function switchEmailContact(contactId){
  const c = (isClienti()?dbC:db).contacts.find(x=>x.id===contactId);
  if(!c) return;
  const sel = document.getElementById('contact-sel');
  if(!sel) return;
  const idx = parseInt(sel.value);
  const ct = idx >= 0 ? c.contacts[idx] : null;
  const toEl = document.getElementById('em-to');
  const nameEl = document.getElementById('em-toname');
  if(toEl) toEl.value = ct?.email || c.email || '';
  if(nameEl) nameEl.value = ct?.name || c.contactName || '';
}

function openEmailToContact(contactId, contactIdx){
  const c = (isClienti()?dbC:db).contacts.find(x=>x.id===contactId);
  if(!c) return;
  const ct = c.contacts?.[contactIdx] || {};
  closeModal();
  // Apri email modal preimpostato su quel contatto
  openEmailModal(contactId, ct.email||c.email, (ct.name||c.contactName), contactIdx);
}

function fillTplForContact(body, c){
  // Selezione contatto ottimale per variabili personalizzate
  const {primary, secondary} = (c.contacts&&c.contacts.length)
    ? selectBestContact(c.contacts)
    : {primary:null, secondary:null};

  const dearLine     = buildDearLine(primary, secondary, c.company);
  const ownerMention = buildOwnerMention(secondary);
  const primaryName  = firstName(primary?.name || c.contactName || '');
  const primaryTitle = primary?.title || c.contactTitle || '';

  return body
    .replace(/\{\{dear\}\}/g,          dearLine)
    .replace(/\{\{owner_mention\}\}/g,  ownerMention)
    .replace(/\{\{know_well\}\}/g,      buildKnowWell(secondary))
    .replace(/\{\{owner\}\}/g,          firstName(secondary?.name||''))
    .replace(/\{\{contatto\}\}/g,       primaryName || c.contactName || '')
    .replace(/\{\{nome\}\}/g,           primaryName || c.name || '')
    .replace(/\{\{job\}\}/g,            primaryTitle)
    .replace(/\{\{azienda\}\}/g,        c.company||'')
    .replace(/\{\{paese\}\}/g,          c.country||'')
    .replace(/\{\{citta\}\}/g,          c.city||'')
    .replace(/\{\{prodotti\}\}/g,       (c.products||[]).join(', ')||'');
}