/* ═══ TEMPLATES ═══ */

function _migrateTemplatesIfNeeded(){
  // Controlla importatori
  const oldSignals = ['Proposta partnership','Best Wine Importers','Vini italiani',
    'Listino prezzi e disponibilità','One partner. One invoice','piqued your interest']; // forza aggiornamento
  const hasOld = db.templates.some(t =>
    oldSignals.some(s => (t.subject||'').includes(s) || (t.body||'').includes(s))
  );
  // Forza aggiornamento se mancano le CTA nei template
  const missingCTA = db.templates.length > 0 &&
    !db.templates.some(t => (t.body||'').includes('know_well'));
  if(hasOld || missingCTA){
    // Imposta default solo se non caricati da GitHub
    if(!ghSha.templates) db.templates = defTplImportatori();
    saveDB();
    console.log('Template importatori migrati ai nuovi Siena Wine');
  }
}

function defTpl(){
  return isClienti()?defTplClienti():defTplImportatori();
}

function defTplImportatori(){return[

  {id:'t1', name:'#1 — First Contact',
   subject:"Have you ever heard of Small Vineyards International? Not yet?",
   body:`{{dear}}

Importing Italian wines has become increasingly complex: too many producers, too many contacts, too many invoices — too much of everything.

{{know_well}}

Siena Wine, through Small Vineyards International, simplifies all of this.

A curated portfolio of family-run Italian wineries — from Chianti to Brunello, from Barolo to Nero d'Avola — built on over 20 years of proven success in the US market with August Imports.

One partner. One invoice. All the best products from Italy.

Have we piqued your interest?

Discover more about us and the portfolio: www.sienawine.it/smallvineyardsinternational

Best regards,
Luca Pattaro
Siena Wine | Small Vineyards International
luca@sienawine.it | +39 331 1347899`},

  {id:'t2a', name:'#2a — Follow-up opened (day 7)',
   subject:"{{azienda}} — a few more reasons to consider us",
   body:`{{dear}}

Thank you for taking a look at our previous email.

I wanted to share a bit more about what makes Small Vineyards International different.

Our portfolio already performs in the US market — these are not unknown names. They are producers with a track record, selected over 20 years by August Imports. We are now bringing the same model internationally.

For {{azienda}}, the practical benefits are clear:

• One contact for orders, documents and logistics
• Consolidated invoicing across the entire portfolio
• Flexible quantities — no need to commit to large volumes upfront
• Full technical support and marketing materials included

Download our brochure and full portfolio: www.sienawine.it/brochure

Would you like me to send you the current price list as well?

Best,
Luca Pattaro
Siena Wine | Small Vineyards International
luca@sienawine.it | +39 331 1347899`},

  {id:'t2b', name:'#2b — Follow-up not opened (day 7)',
   subject:"Still importing Italian wines the hard way?",
   body:`{{dear}}

I reached out last week about Small Vineyards International — I am not sure my email found its way to you, so I wanted to try once more.

We represent a curated portfolio of Italian family wineries, built on 20+ years of proven success in the US market. One partner, one invoice, all of Italy.

If simplifying your Italian wine sourcing is something worth 2 minutes of your time, everything is here: www.sienawine.it/smallvineyardsinternational

Best,
Luca Pattaro
Siena Wine | Small Vineyards International
luca@sienawine.it | +39 331 1347899`},

  {id:'t3', name:'#3 — Follow-up (day 21)',
   subject:"One contact. One invoice. All of Italy.",
   body:`{{dear}}

Working with multiple small Italian producers means multiple contacts, invoices, shipments and conversations. We solve that.

Through Siena Wine, {{azienda}} gets:

• A single point of contact for the entire portfolio
• Consolidated orders and shipments
• Full documentation support
• A selection proven to sell — validated by years of US market success

We are not asking you to take a risk on unknown producers. These wines have a track record.

Book a 20-minute call at your convenience: calendly.com/luca-sienawine/30min

Best,
Luca Pattaro
Siena Wine | Small Vineyards International
luca@sienawine.it | +39 331 1347899`},

  {id:'t4', name:'#4 — Break-up (day 35)',
   subject:"Closing the loop — {{azienda}}",
   body:`{{dear}}

I have reached out a few times without hearing back — I completely understand, timing is everything in this business.

I will not send further emails, but wanted to leave you with one thought: if you are ever looking to add a curated Italian portfolio with a proven US track record, a single operational contact, and wineries that genuinely over-deliver for their price point — we are here.

Our portfolio is always available at: www.sienawine.it/smallvineyardsinternational

Wishing {{azienda}} continued success.

Luca Pattaro
Siena Wine | Small Vineyards International
luca@sienawine.it | +39 331 1347899`}

];}

function defTplClienti(){return[
  {id:'c1',name:'Benvenuto — Offerta speciale',
   subject:'Un pensiero speciale per te da Il Ciliegio 🍷',
   body:"Caro {{contatto}},\n\nTi scriviamo dall'Azienda Agricola Il Ciliegio per ringraziarti di far parte della nostra comunità di appassionati.\n\nAbbiamo preparato per te una selezione esclusiva delle nostre migliori etichette, disponibile a condizioni speciali riservate ai nostri clienti più affezionati.\n\nScopri la nostra proposta su www.ilciliegio.com oppure contattaci direttamente — saremo felici di guidarti nella scelta.\n\nA presto,\nIl team de Il Ciliegio\nAzienda Agricola"},
  {id:'c2',name:'Offerta stagionale',
   subject:'La nuova annata è arrivata — riservata a te ✨',
   body:"Caro {{contatto}},\n\nSiamo entusiasti di annunciarti l'arrivo della nuova annata de Il Ciliegio.\n\nCome nostro cliente, hai accesso in anteprima alla nuova selezione, con la possibilità di acquistare a prezzi dedicati prima dell'apertura al pubblico.\n\nI quantitativi sono limitati. Visita www.ilciliegio.com o rispondi a questa email per prenotare la tua selezione.\n\nTi aspettiamo!\nIl Ciliegio — Azienda Agricola"},
  {id:'c3',name:'Follow-up 1 (7 gg)',
   subject:"Hai avuto modo di dare un'occhiata? — Il Ciliegio",
   body:"Caro {{contatto}},\n\nTi scrivo brevemente per assicurarmi che tu abbia ricevuto la nostra proposta di qualche giorno fa.\n\nSe hai domande sulla selezione o desideri ricevere ulteriori informazioni, sono qui per aiutarti.\n\nUn caro saluto,\nIl Ciliegio — Azienda Agricola"},
  {id:'c4',name:'Follow-up 2 — Ultimi pezzi',
   subject:"Ultimi pezzi disponibili — non perdere l'occasione",
   body:"Caro {{contatto}},\n\nTi scrivo perché le scorte della selezione che ti avevo proposto si stanno esaurendo rapidamente.\n\nSe desideri approfittare dell'offerta riservata, ti chiedo di farmi sapere entro i prossimi giorni.\n\nSarò felice di gestire personalmente il tuo ordine.\n\nCon i migliori saluti,\nIl Ciliegio — Azienda Agricola"},
  {id:'c5',name:'Auguri e offerta festiva',
   subject:'Buone Feste da Il Ciliegio 🎄',
   body:"Caro {{contatto}},\n\nIn occasione delle feste, tutto il team de Il Ciliegio ti augura un periodo sereno e ricco di momenti speciali.\n\nAbbiamo selezionato per te le nostre etichette più eleganti, perfette per brindare o regalare a chi ami.\n\nScopri la confezione regalo Il Ciliegio su www.ilciliegio.com — consegna in tutta Europa.\n\nBuone Feste!\nIl Ciliegio — Azienda Agricola"}
];}

/* ── SAVE / GH ── */

function renderTemplates(){
  const titleEl=document.getElementById('tpl-title');
  if(titleEl) titleEl.textContent=isClienti()?'Template — Clienti Il Ciliegio':'Template — Importatori';
  const el=document.getElementById('tpl-list');
  el.innerHTML=(isClienti()?dbC:db).templates.length?(isClienti()?dbC:db).templates.map(t=>`
    <div class="card">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
        <div style="font-size:15px;font-weight:600">${esc(t.name)}</div>
        <div style="display:flex;gap:6px">
          <button class="btn bts" onclick="openAddTemplate('${t.id}')">Modifica</button>
          <button class="btn bts btd" onclick="delTpl('${t.id}')">Elimina</button>
        </div>
      </div>
      <div style="font-size:12px;color:var(--text2);margin-bottom:7px">Oggetto: <span style="color:var(--text)">${esc(t.subject)}</span></div>
      <div style="font-size:12px;background:var(--bg2);border-radius:6px;padding:10px;white-space:pre-wrap;line-height:1.6;max-height:90px;overflow:hidden;color:var(--text2)">${esc(t.body.slice(0,280))}${t.body.length>280?'…':''}</div>
    </div>`).join(''):'<div class="empty">Nessun template</div>';
}

function openAddTemplate(editId){
  const t=editId?(isClienti()?dbC:db).templates.find(x=>x.id===editId):null;
  showModal(`
    <div class="mt">${t?'Modifica':'Nuovo'} template</div>
    <div class="fg fgf"><label>Nome</label><input id="tn" value="${esc(t?.name||'')}"></div>
    <div class="fg fgf"><label>Oggetto</label><input id="ts" value="${esc(t?.subject||'')}"></div>
    <div class="fg fgf"><label>Corpo</label><textarea id="tb" style="min-height:220px">${esc(t?.body||'')}</textarea></div>
    <div class="mf">
      <button class="btn" onclick="closeModal()">Annulla</button>
      <button class="btn btp" onclick="saveTpl('${editId||''}')">Salva</button>
    </div>
  `);
}

function saveTpl(editId){
  const name=gv('tn');if(!name){toast('Nome obbligatorio');return;}
  const t={id:editId||'t'+Date.now(),name,subject:gv('ts'),body:document.getElementById('tb').value};
  if(editId){const i=(isClienti()?dbC:db).templates.findIndex(x=>x.id===editId);if(i>=0)(isClienti()?dbC:db).templates[i]=t;}
  else (isClienti()?dbC:db).templates.push(t);
  saveDB();saveTemplatesToGH();closeModal();renderTemplates();toast('Salvato ✓');
}

function delTpl(id){
  if(!confirm('Eliminare?'))return;
  (isClienti()?dbC:db).templates=(isClienti()?dbC:db).templates.filter(t=>t.id!==id);saveDB();saveTemplatesToGH();renderTemplates();
}

/* ═══════════════════════════════════════
   IMPORT XLSX — MULTI-SHEET
═══════════════════════════════════════ */
// Mappa paese → regione — copertura completa BWI
const COUNTRY_REGION = {
  // ── SUD AMERICA ──
  'Argentina':'Sud America','Bolivia':'Sud America','Brazil':'Sud America',
  'Brasil':'Sud America','Chile':'Sud America','Colombia':'Sud America',
  'Ecuador':'Sud America','El Salvador':'Sud America','Guatemala':'Sud America',
  'Honduras':'Sud America','Mexico':'Sud America','Messico':'Sud America',
  'Nicaragua':'Sud America','Panama':'Sud America','Paraguay':'Sud America',
  'Peru':'Sud America','Perù':'Sud America','Suriname':'Sud America',
  'Uruguay':'Sud America','Venezuela':'Sud America','Costa Rica':'Sud America',
  'Dominican Republic':'Sud America','Cuba':'Sud America','Haiti':'Sud America',
  'Jamaica':'Sud America','Trinidad and Tobago':'Sud America',
  'Trinidad And Tobago':'Sud America','Belize':'Sud America',
  'Guyana':'Sud America','French Guiana':'Sud America',
  'Martinique':'Sud America','Guadeloupe':'Sud America',

  // ── NORD AMERICA ──
  'United States':'Nord America','USA':'Nord America','Canada':'Nord America',

  // ── CARAIBI ──
  'Cayman Islands':'Caraibi','Isole Cayman':'Caraibi',
  'Barbados':'Caraibi','Bermuda':'Caraibi','Bahamas':'Caraibi',
  'Puerto Rico':'Caraibi','Aruba':'Caraibi','Curaçao':'Caraibi',
  'Curacao':'Caraibi','Saint Lucia':'Caraibi','Grenada':'Caraibi',
  'Antigua and Barbuda':'Caraibi','Antigua And Barbuda':'Caraibi',
  'Saint Kitts and Nevis':'Caraibi','Dominica':'Caraibi',
  'Virgin Islands':'Caraibi','Turks and Caicos Islands':'Caraibi',

  // ── EUROPA ──
  'Albania':'Europa','Andorra':'Europa','Austria':'Europa',
  'Belgium':'Europa','Belgio':'Europa',
  'Bosnia and Herzegovina':'Europa','Bosnia And Herzegovina':'Europa',
  'Bulgaria':'Europa','Croatia':'Europa','Croazia':'Europa',
  'Cyprus':'Europa','Cipro':'Europa',
  'Czech Republic':'Europa','Czechia':'Europa','Rep. Ceca':'Europa',
  'Denmark':'Europa','Danimarca':'Europa',
  'Estonia':'Europa','Finland':'Europa','Finlandia':'Europa',
  'France':'Europa','Francia':'Europa',
  'Germany':'Europa','Germania':'Europa',
  'Greece':'Europa','Grecia':'Europa',
  'Hungary':'Europa','Ungheria':'Europa',
  'Iceland':'Europa','Islanda':'Europa',
  'Ireland':'Europa','Irlanda':'Europa',
  'Italy':'Europa','Italia':'Europa',
  'Kosovo':'Europa','Latvia':'Europa','Lithuania':'Europa',
  'Luxembourg':'Europa','Lussemburgo':'Europa',
  'Malta':'Europa','Moldova':'Europa','Montenegro':'Europa',
  'Netherlands':'Europa','Paesi Bassi':'Europa',
  'North Macedonia':'Europa','Macedonia':'Europa',
  'Norway':'Europa','Norvegia':'Europa',
  'Poland':'Europa','Polonia':'Europa',
  'Portugal':'Europa','Portogallo':'Europa',
  'Romania':'Europa','Russia':'Europa',
  'Serbia':'Europa','Slovakia':'Europa','Slovacchia':'Europa',
  'Slovenia':'Europa','Spain':'Europa','Spagna':'Europa',
  'Sweden':'Europa','Svezia':'Europa',
  'Switzerland':'Europa','Svizzera':'Europa',
  'Ukraine':'Europa','Ucraina':'Europa',
  'United Kingdom':'Europa','UK':'Europa','GB':'Europa',
  'Belarus':'Europa','Liechtenstein':'Europa','Monaco':'Europa',
  'San Marino':'Europa','Vatican City':'Europa',
  'Faroe Islands':'Europa','Gibraltar':'Europa',
  'Andorra':'Europa','Kosovo':'Europa',

  // ── SCANDINAVIA ──
  // (inclusa in Europa ma separabile se preferisci)

  // ── OCEANIA ──
  'Australia':'Oceania','New Zealand':'Oceania','Nuova Zelanda':'Oceania',
  'Fiji':'Oceania','Papua New Guinea':'Oceania','Papua Nuova Guinea':'Oceania',
  'Vanuatu':'Oceania','Solomon Islands':'Oceania','Samoa':'Oceania',
  'Tonga':'Oceania','Micronesia':'Oceania','Palau':'Oceania',
  'Marshall Islands':'Oceania','Kiribati':'Oceania','Nauru':'Oceania',
  'Tuvalu':'Oceania','French Polynesia':'Oceania',
  'New Caledonia':'Oceania','Guam':'Oceania',

  // ── ASIA ──
  'China':'Asia','Cina':'Asia','Japan':'Asia','Giappone':'Asia',
  'South Korea':'Asia','Korea':'Asia','Corea del Sud':'Asia',
  'India':'Asia','Indonesia':'Asia','Malaysia':'Asia',
  'Philippines':'Asia','Filippine':'Asia',
  'Singapore':'Asia','Thailand':'Asia','Tailandia':'Asia',
  'Vietnam':'Asia','Taiwan':'Asia','Hong Kong':'Asia',
  'Bangladesh':'Asia','Sri Lanka':'Asia','Myanmar':'Asia',
  'Cambodia':'Asia','Nepal':'Asia','Pakistan':'Asia',
  'Kazakhstan':'Asia','Uzbekistan':'Asia','Mongolia':'Asia',
  'Laos':'Asia','Brunei':'Asia','Timor-Leste':'Asia',
  'Maldives':'Asia','Bhutan':'Asia','Afghanistan':'Asia',
  'Tajikistan':'Asia','Kyrgyzstan':'Asia','Turkmenistan':'Asia',
  'Azerbaijan':'Asia','Georgia':'Asia','Armenia':'Asia',

  // ── MEDIO ORIENTE ──
  'United Arab Emirates':'Medio Oriente','UAE':'Medio Oriente',
  'Emirati Arabi':'Medio Oriente',
  'Saudi Arabia':'Medio Oriente','Arabia Saudita':'Medio Oriente',
  'Israel':'Medio Oriente','Israele':'Medio Oriente',
  'Qatar':'Medio Oriente','Kuwait':'Medio Oriente',
  'Bahrain':'Medio Oriente','Oman':'Medio Oriente',
  'Jordan':'Medio Oriente','Giordania':'Medio Oriente',
  'Lebanon':'Medio Oriente','Libano':'Medio Oriente',
  'Turkey':'Medio Oriente','Turchia':'Medio Oriente',
  'Iran':'Medio Oriente','Iraq':'Medio Oriente',
  'Syria':'Medio Oriente','Yemen':'Medio Oriente',
  'Palestine':'Medio Oriente','Libya':'Medio Oriente',

  // ── AFRICA ──
  'South Africa':'Africa','Sudafrica':'Africa',
  'Kenya':'Africa','Nigeria':'Africa',
  'Ethiopia':'Africa','Etiopia':'Africa',
  'Tanzania':'Africa','Uganda':'Africa','Ghana':'Africa',
  'Senegal':'Africa','Morocco':'Africa','Marocco':'Africa',
  'Tunisia':'Africa','Algeria':'Africa',
  'Egypt':'Africa','Egitto':'Africa',
  'Angola':'Africa','Mozambique':'Africa',
  'Zimbabwe':'Africa','Zambia':'Africa',
  'Botswana':'Africa','Namibia':'Africa',
  'Cameroon':'Africa','Ivory Coast':'Africa',"Côte d'Ivoire":'Africa',
  'Madagascar':'Africa','Mauritius':'Africa',
  'Rwanda':'Africa','Malawi':'Africa','Mali':'Africa',
  'Burkina Faso':'Africa','Niger':'Africa','Chad':'Africa',
  'Sudan':'Africa','Somalia':'Africa','Eritrea':'Africa',
  'Djibouti':'Africa','Comoros':'Africa','Seychelles':'Africa',
  'Cape Verde':'Africa','São Tomé and Príncipe':'Africa',
  'Equatorial Guinea':'Africa','Gabon':'Africa',
  'Republic of the Congo':'Africa','Democratic Republic of the Congo':'Africa',
  'Central African Republic':'Africa','South Sudan':'Africa',
  'Sierra Leone':'Africa','Liberia':'Africa','Guinea':'Africa',
  'Guinea-Bissau':'Africa','Gambia':'Africa','Benin':'Africa',
  'Togo':'Africa','Lesotho':'Africa','Eswatini':'Africa',
  'Swaziland':'Africa',
};

function resetDefaultTemplates(){
  const adb=isClienti()?dbC:db;
  if(!confirm('Ripristinare i template predefiniti? I template personalizzati verranno eliminati.')) return;
  adb.templates=defTpl();
  saveDB();renderTemplates();
  toast('Template ripristinati ✓');
}

function resetToDefaultTemplates(){
  const label = isClienti() ? 'clienti Il Ciliegio' : 'importatori Siena Wine';
  if(!confirm(`Sostituire i template attuali con i default ${label}?`)) return;
  const adb = isClienti() ? dbC : db;
  adb.templates = isClienti() ? defTplClienti() : defTplImportatori();
  saveDB();
  renderTemplates();
  toast('✓ Template ripristinati');
}

/* ── TEMPLATES ── */