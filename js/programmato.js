/* ═══ PROGRAMMATO — coda e calendario dei follow-up importatori + approvazione giornaliera ═══
   Il piano (data/piano-invii.json) lo calcola lo script server-side a ogni giro (scripts/send_importatori_followup.py --piano).
   Qui lo si legge e basta. L'unica scrittura è data/piano-approvato.json: senza approvazione valida per OGGI
   (data italiana) il passo follow-up non invia nulla. */

const PIANO_PATH='data/piano-invii.json';
const APPROVAZIONE_PATH='data/piano-approvato.json';
let pianoInvii=null, pianoApprovazione=null, pianoApprovazioneSha=null;

function _pianoOggiIT(){ return new Date().toLocaleDateString('sv-SE',{timeZone:'Europe/Rome'}); } // YYYY-MM-DD

async function _ghLeggiJson(path){
  const{token,owner,repo}=ghs;
  if(!token||!owner||!repo) return {data:null,sha:null};
  const r=await fetch(`https://api.github.com/repos/${owner}/${repo}/contents/${path}?t=${Date.now()}`,
    {headers:{'Authorization':`token ${token}`,'Accept':'application/vnd.github.v3+json'}});
  if(r.status===404) return {data:null,sha:null};
  if(!r.ok) throw new Error(`GitHub ${r.status}`);
  const d=await r.json();
  const raw=(d.content||'').replace(/\n/g,'');
  if(!raw) return {data:null,sha:d.sha};
  const txt=decodeURIComponent(Array.from(atob(raw),c=>'%'+c.charCodeAt(0).toString(16).padStart(2,'0')).join(''));
  return {data:JSON.parse(txt),sha:d.sha};
}

async function loadPianoInvii(){
  try{
    const [p,a]=await Promise.all([_ghLeggiJson(PIANO_PATH),_ghLeggiJson(APPROVAZIONE_PATH)]);
    pianoInvii=p.data;
    pianoApprovazione=(a.data&&a.data.date===_pianoOggiIT())?a.data:null;
    pianoApprovazioneSha=a.sha;
  }catch(e){ console.warn('loadPianoInvii:',e); pianoInvii=pianoInvii||null; }
  renderProgrammato();
}

async function approvaPianoOggi(){
  const inp=document.getElementById('prog-limite');
  const limite=parseInt(inp&&inp.value,10);
  if(!(limite>0)){ toast('Inserisci un limite maggiore di 0'); return; }
  const{token,owner,repo}=ghs;
  if(!token||!owner||!repo){ toast('GitHub non configurato'); return; }
  const dati={date:_pianoOggiIT(),limit:limite,approvedAt:Date.now()};
  const bytes=new TextEncoder().encode(JSON.stringify(dati,null,2));
  let bin=''; bytes.forEach(b=>bin+=String.fromCharCode(b));
  const body={message:`Approvato piano follow-up ${dati.date} — limite ${limite}`,content:btoa(bin)};
  // rilegge lo sha: il file del giorno prima esiste già e va sovrascritto
  try{ const cur=await _ghLeggiJson(APPROVAZIONE_PATH); if(cur.sha) body.sha=cur.sha; }catch(e){}
  const res=await fetch(`https://api.github.com/repos/${owner}/${repo}/contents/${APPROVAZIONE_PATH}`,
    {method:'PUT',headers:{'Authorization':`token ${token}`,'Content-Type':'application/json','Accept':'application/vnd.github.v3+json'},body:JSON.stringify(body)});
  if(!res.ok){ toast('✗ Approvazione non salvata ('+res.status+')'); return; }
  pianoApprovazione=dati; pianoApprovazioneSha=(await res.json()).content.sha;
  toast('✓ Piano di oggi approvato');
  renderProgrammato();
}

async function revocaApprovazione(){
  if(!confirm('Revocare l\'approvazione di oggi? I prossimi giri non invieranno nulla.')) return;
  const{token,owner,repo}=ghs;
  const dati={date:'revocato',limit:0,approvedAt:Date.now()};
  const bytes=new TextEncoder().encode(JSON.stringify(dati,null,2));
  let bin=''; bytes.forEach(b=>bin+=String.fromCharCode(b));
  const cur=await _ghLeggiJson(APPROVAZIONE_PATH);
  const res=await fetch(`https://api.github.com/repos/${owner}/${repo}/contents/${APPROVAZIONE_PATH}`,
    {method:'PUT',headers:{'Authorization':`token ${token}`,'Content-Type':'application/json','Accept':'application/vnd.github.v3+json'},
     body:JSON.stringify({message:'Revocata approvazione piano follow-up',content:btoa(bin),sha:cur.sha})});
  if(!res.ok){ toast('✗ Revoca non salvata ('+res.status+')'); return; }
  pianoApprovazione=null; toast('Approvazione revocata'); renderProgrammato();
}

function _fmtDataIT(iso){ const [y,m,d]=iso.split('-'); return `${d}/${m}`; }

function renderProgrammato(){
  const el=document.getElementById('prog-body'); if(!el) return;
  const badge=document.getElementById('prog-n');
  if(!pianoInvii){
    el.innerHTML='<div class="card" style="color:var(--text2);font-size:13px">Piano non ancora disponibile: viene calcolato ad ogni giro automatico (ogni 6 ore). Se hai appena fatto il deploy, attendi il prossimo giro.</div>';
    if(badge) badge.style.display='none';
    return;
  }
  const p=pianoInvii, attivo=p.followupPassoAttivo, appr=pianoApprovazione;
  const g=p.giorni||[];
  const oggi=g[0]||{daInviare:0};
  const limiteDef=appr?appr.limit:(p.oggi&&p.oggi.limiteProposto)||p.tetto.perGiorno;
  const maxGiorno=Math.max(1,...g.map(x=>x.daInviare));
  const crediti=(p.crediti&&p.crediti.email!=null)?Number(p.crediti.email).toLocaleString('it-IT'):'—';
  const eta=Math.round((Date.now()-p.generatoAt)/3600000);

  // Stato / approvazione
  let stato;
  if(!attivo){
    stato=`<div style="display:flex;align-items:center;gap:10px"><span style="font-size:22px">⏸</span>
      <div><b>Follow-up automatico SPENTO</b><div style="font-size:12px;color:var(--text2)">Nessuna mail parte, qualunque cosa tu approvi. Riattivarlo richiede il mio intervento sul workflow (decidi tu quando).</div></div></div>`;
  } else if(appr){
    stato=`<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap"><span style="font-size:22px">✅</span>
      <div style="flex:1"><b>Piano di oggi approvato</b> — fino a ${appr.limit} mail, alle ${new Date(appr.approvedAt).toLocaleTimeString('it-IT',{hour:'2-digit',minute:'2-digit'})}
      <div style="font-size:12px;color:var(--text2)">Già inviate oggi (all'ultimo aggiornamento): ${p.oggi.inviate}</div></div>
      <button class="btn btd" onclick="revocaApprovazione()">Revoca</button></div>`;
  } else {
    stato=`<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap"><span style="font-size:22px">🛑</span>
      <div style="flex:1"><b>Piano di oggi NON approvato — non parte nessuna mail</b>
      <div style="font-size:12px;color:var(--text2)">Oggi con il tetto attuale partirebbero circa ${oggi.daInviare} follow-up.</div></div>
      <label style="font-size:12px;color:var(--text2)">Limite oggi <input id="prog-limite" type="number" min="1" value="${limiteDef}" style="width:80px;font-size:13px;padding:5px 7px;border-radius:var(--r);border:0.5px solid var(--brd2);background:var(--bg);color:var(--text)"></label>
      <button class="btn btp" onclick="approvaPianoOggi()">Approva il piano di oggi</button></div>`;
  }
  if(badge){ badge.style.display=(attivo&&!appr&&p.pronteOra.totale>0)?'inline-block':'none'; }

  const righe=g.map(x=>{
    const w=Math.round(x.daInviare/maxGiorno*100);
    const dettaglio=[x.day7?`${x.day7} day7`:'',x.day21?`${x.day21} day21`:'',x.day35?`${x.day35} day35`:''].filter(Boolean).join(' · ')||'—';
    const flag=x.scadonoSenzaInvio?` <span style="color:var(--red-tx);font-weight:600">⚠ ${x.scadonoSenzaInvio} scadono senza invio</span>`:'';
    return `<tr><td style="padding:5px 8px;white-space:nowrap;font-weight:500">${x.giorno} ${_fmtDataIT(x.data)}</td>
      <td style="padding:5px 8px;width:42%"><div style="background:var(--bg2);border-radius:4px;height:14px"><div style="width:${w}%;background:var(--blue,#378ADD);height:14px;border-radius:4px"></div></div></td>
      <td style="padding:5px 8px;text-align:right;font-weight:600">${x.daInviare}</td>
      <td style="padding:5px 8px;font-size:12px;color:var(--text2)">${dettaglio}${flag}</td></tr>`;
  }).join('');

  const reg=Object.keys(p.registro7Giorni||{}).sort().reverse().map(d=>{
    const t=p.registro7Giorni[d]; const tot=Object.values(t).reduce((a,b)=>a+b,0);
    return `<tr><td style="padding:4px 8px">${_fmtDataIT(d)}</td><td style="padding:4px 8px;text-align:right;font-weight:600">${tot}</td>
      <td style="padding:4px 8px;font-size:12px;color:var(--text2)">${Object.entries(t).map(([k,v])=>`${v} ${k}`).join(' · ')}</td></tr>`;
  }).join('')||'<tr><td colspan="3" style="padding:6px 8px;color:var(--text2)">Nessun invio registrato</td></tr>';

  el.innerHTML=`
    <div class="card">${stato}</div>
    <div class="sgrid">
      <div class="stat"><div style="font-size:11px;color:var(--text2)">Pronti ora</div><div style="font-size:24px;font-weight:700">${p.pronteOra.totale}</div>
        <div style="font-size:11px;color:var(--text2)">day7 ${p.pronteOra.day7} · day21 ${p.pronteOra.day21} · day35 ${p.pronteOra.day35}</div></div>
      <div class="stat"><div style="font-size:11px;color:var(--text2)">Tetto</div><div style="font-size:24px;font-weight:700">${p.tetto.perGiorno}/giorno</div>
        <div style="font-size:11px;color:var(--text2)">${p.tetto.perGiro} per giro × ${p.tetto.giriAlGiorno} giri</div></div>
      <div class="stat"><div style="font-size:11px;color:var(--text2)">Crediti Brevo</div><div style="font-size:24px;font-weight:700">${crediti}</div>
        <div style="font-size:11px;color:var(--text2)">email inviabili</div></div>
      <div class="stat"><div style="font-size:11px;color:var(--text2)">Perse per scadenza</div><div style="font-size:24px;font-weight:700;${p.perseNelPeriodo?'color:var(--red-tx)':''}">${p.perseNelPeriodo}</div>
        <div style="font-size:11px;color:var(--text2)">nei prossimi ${g.length} giorni</div></div>
    </div>
    <div class="card"><div style="font-weight:600;margin-bottom:6px">Calendario — cosa partirebbe, giorno per giorno</div>
      <div style="font-size:12px;color:var(--text2);margin-bottom:8px">Proiezione se approvi ogni giorno. I giri partono alle 6, 12, 18 e 24; chi sta per uscire dalla finestra di invio va per primo. Dopo ogni invio il contatto passa al passo successivo (day7 → day21 → day35).</div>
      <table style="width:100%;border-collapse:collapse;font-size:13px">${righe}</table></div>
    <div class="card"><div style="font-weight:600;margin-bottom:6px">Registro — cosa è partito negli ultimi 7 giorni</div>
      <table style="width:100%;border-collapse:collapse;font-size:13px">${reg}</table>
      <div style="font-size:11px;color:var(--text2);margin-top:6px">Dal registro del CRM: gli invii dei giri andati in timeout il 26/9–1/10 non ci sono (non erano stati salvati). Il dato completo è nel log Brevo.</div></div>
    <div style="font-size:11px;color:var(--text2)">Piano calcolato il ${esc(p.generatoIl)}${eta>=7?` <b style="color:var(--red-tx)">(vecchio di ${eta} ore: il timer potrebbe essersi fermato)</b>`:''} · contatti in sequenza: ${p.contattiAttivi}
      · senza casella valida: ${p.senzaCasellaValida} · già scaduti: ${p.scaduteGia}
      <button class="btn btg" style="font-size:11px;padding:2px 8px" onclick="loadPianoInvii()">↻ Ricarica</button></div>`;
}
