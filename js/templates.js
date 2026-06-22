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

Discover more about us and the portfolio [here](https://www.sienawine.it/smallvineyardsinternational).

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

Download our brochure and full portfolio [here](https://www.sienawine.it/brochure).

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

If simplifying your Italian wine sourcing is something worth 2 minutes of your time, everything is [here](https://www.sienawine.it/smallvineyardsinternational).

Best,
Luca Pattaro
Siena Wine | Small Vineyards International
luca@sienawine.it | +39 331 1347899`},

  {id:'t3a', name:'#3a — Follow-up opened (day 21)',
   subject:"One contact. One invoice. All of Italy.",
   body:`{{dear}}

Working with multiple small Italian producers means multiple contacts, invoices, shipments and conversations. We solve that.

Through Siena Wine, {{azienda}} gets:

• A single point of contact for the entire portfolio
• Consolidated orders and shipments
• Full documentation support
• A selection proven to sell — validated by years of US market success

We are not asking you to take a risk on unknown producers. These wines have a track record.

Book a 20-minute call at your convenience [here](https://calendly.com/luca-sienawine/30min).

Best,
Luca Pattaro
Siena Wine | Small Vineyards International
luca@sienawine.it | +39 331 1347899`},

  {id:'t3b', name:'#3b — Follow-up not opened (day 21)',
   subject:"One contact. One invoice. All of Italy.",
   body:`{{dear}}

Working with multiple small Italian producers means multiple contacts, invoices, shipments and conversations. We solve that.

Through Siena Wine, {{azienda}} gets:

• A single point of contact for the entire portfolio
• Consolidated orders and shipments
• Full documentation support
• A selection proven to sell — validated by years of US market success

We are not asking you to take a risk on unknown producers. These wines have a track record.

Book a 20-minute call at your convenience [here](https://calendly.com/luca-sienawine/30min).

Best,
Luca Pattaro
Siena Wine | Small Vineyards International
luca@sienawine.it | +39 331 1347899`},

  {id:'t4a', name:'#4a — Break-up opened (day 35)',
   subject:"Closing the loop — {{azienda}}",
   body:`{{dear}}

I have reached out a few times without hearing back — I completely understand, timing is everything in this business.

I will not send further emails, but wanted to leave you with one thought: if you are ever looking to add a curated Italian portfolio with a proven US track record, a single operational contact, and wineries that genuinely over-deliver for their price point — we are here.

Our portfolio is always available [here](https://www.sienawine.it/smallvineyardsinternational).

Wishing {{azienda}} continued success.

Luca Pattaro
Siena Wine | Small Vineyards International
luca@sienawine.it | +39 331 1347899`},

  {id:'t4b', name:'#4b — Break-up not opened (day 35)',
   subject:"Closing the loop — {{azienda}}",
   body:`{{dear}}

I have reached out a few times without hearing back — I completely understand, timing is everything in this business.

I will not send further emails, but wanted to leave you with one thought: if you are ever looking to add a curated Italian portfolio with a proven US track record, a single operational contact, and wineries that genuinely over-deliver for their price point — we are here.

Our portfolio is always available [here](https://www.sienawine.it/smallvineyardsinternational).

Wishing {{azienda}} continued success.

Luca Pattaro
Siena Wine | Small Vineyards International
luca@sienawine.it | +39 331 1347899`}

];}

function defTplClienti(){return[
  {id:'wave1',name:'Benvenuto — Offerta speciale',
   subject:'A special thought for you from Il Ciliegio 🍷',
   body:"Dear {{nome}},\n\nWe're writing to you from Il Ciliegio Winery to thank you for being part of our community of wine lovers.\n\nWe've prepared an exclusive selection of our finest labels for you, available at special prices reserved for our most loyal customers.\n\nDiscover our selection at www.ilciliegio.com or get in touch with us directly — we'd be happy to help you choose.\n\nSee you soon,\nThe Il Ciliegio Team\nAzienda Agricola"},
  {id:'c2',name:'Offerta stagionale',
   subject:'The new vintage has arrived — just for you ✨',
   body:"Dear {{nome}},\n\nWe're excited to announce the arrival of the new vintage from Il Ciliegio.\n\nAs one of our customers, you have early access to the new selection, with the chance to purchase at special prices before it becomes available to the public.\n\nQuantities are limited. Visit www.ilciliegio.com or reply to this email to reserve your selection.\n\nWe look forward to hearing from you!\nIl Ciliegio — Azienda Agricola"}
];}

/* ── SAVE / GH ── */

function renderTemplates(){
  const titleEl=document.getElementById('tpl-title');
  if(titleEl) titleEl.textContent=isClienti()?'Template — Clienti Il Ciliegio':'Template — Importatori';
  const el=document.getElementById('tpl-list');
  el.innerHTML=(isClienti()?dbC:db).templates.length?[...(isClienti()?dbC:db).templates].sort((a,b)=>(a.name||'').localeCompare(b.name||'','it')).map(t=>`
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

// Mappa codice ISO 2 lettere → nome leggibile (usata per normalizzare clienti SpottyWifi)
const ISO2NAME = {
  'AF':'Afghanistan','AL':'Albania','DZ':'Algeria','AO':'Angola',
  'AR':'Argentina','AM':'Armenia','AU':'Australia','AT':'Austria',
  'AZ':'Azerbaigian','BS':'Bahamas','BH':'Bahrain','BD':'Bangladesh',
  'BY':'Bielorussia','BE':'Belgio','BZ':'Belize','BJ':'Benin',
  'BO':'Bolivia','BA':'Bosnia Erzegovina','BW':'Botswana','BR':'Brasile',
  'BN':'Brunei','BG':'Bulgaria','BF':'Burkina Faso','KH':'Cambogia',
  'CM':'Cameroon','CA':'Canada','CV':'Capo Verde','TD':'Ciad',
  'CL':'Cile','CN':'Cina','CO':'Colombia','KM':'Comore',
  'CG':'Congo','CD':'Congo (RDC)','KR':'Corea del Sud','CR':'Costa Rica',
  'CI':'Costa d\'Avorio','HR':'Croazia','CU':'Cuba','CY':'Cipro',
  'DK':'Danimarca','DO':'Rep. Dominicana','EC':'Ecuador','EG':'Egitto',
  'SV':'El Salvador','AE':'Emirati Arabi','ER':'Eritrea','ET':'Etiopia',
  'FI':'Finlandia','FR':'Francia','GA':'Gabon','GM':'Gambia',
  'GE':'Georgia','DE':'Germania','GH':'Ghana','JM':'Giamaica',
  'JP':'Giappone','JO':'Giordania','GR':'Grecia','GT':'Guatemala',
  'GN':'Guinea','GW':'Guinea-Bissau','GY':'Guyana','HT':'Haiti',
  'HN':'Honduras','HK':'Hong Kong','HU':'Ungheria','IN':'India',
  'ID':'Indonesia','IR':'Iran','IQ':'Iraq','IE':'Irlanda',
  'IS':'Islanda','IL':'Israele','IT':'Italia','KZ':'Kazakhstan',
  'KE':'Kenya','KG':'Kirghizistan','KW':'Kuwait','LA':'Laos',
  'LS':'Lesotho','LV':'Lettonia','LB':'Libano','LY':'Libia',
  'LI':'Liechtenstein','LT':'Lituania','LU':'Lussemburgo',
  'MO':'Macao','MK':'Macedonia del Nord','MG':'Madagascar',
  'MW':'Malawi','MY':'Malaysia','MV':'Maldive','ML':'Mali',
  'MT':'Malta','MA':'Marocco','MR':'Mauritania','MU':'Mauritius',
  'MX':'Messico','MD':'Moldavia','MC':'Monaco','MN':'Mongolia',
  'ME':'Montenegro','MZ':'Mozambico','MM':'Myanmar','NA':'Namibia',
  'NP':'Nepal','NI':'Nicaragua','NE':'Niger','NG':'Nigeria',
  'NO':'Norvegia','NZ':'Nuova Zelanda','NL':'Paesi Bassi',
  'PK':'Pakistan','PA':'Panama','PG':'Papua Nuova Guinea',
  'PY':'Paraguay','PE':'Perù','PH':'Filippine','PL':'Polonia',
  'PT':'Portogallo','QA':'Qatar','GB':'Gran Bretagna','CZ':'Rep. Ceca',
  'RO':'Romania','RW':'Ruanda','RU':'Russia','SA':'Arabia Saudita',
  'SN':'Senegal','RS':'Serbia','SL':'Sierra Leone','SG':'Singapore',
  'SK':'Slovacchia','SI':'Slovenia','SO':'Somalia','ES':'Spagna',
  'LK':'Sri Lanka','SD':'Sudan','SS':'Sudan del Sud','SR':'Suriname',
  'SE':'Svezia','CH':'Svizzera','SY':'Siria','TW':'Taiwan',
  'TJ':'Tagikistan','TZ':'Tanzania','TH':'Tailandia','TL':'Timor Est',
  'TG':'Togo','TT':'Trinidad e Tobago','TN':'Tunisia','TR':'Turchia',
  'TM':'Turkmenistan','UG':'Uganda','UA':'Ucraina','US':'USA',
  'UY':'Uruguay','UZ':'Uzbekistan','VE':'Venezuela','VN':'Vietnam',
  'YE':'Yemen','ZM':'Zambia','ZW':'Zimbabwe','XK':'Kosovo','ZA':'Sudafrica',
  'MF':'Saint Martin','SX':'Sint Maarten','GP':'Guadalupa',
  'MQ':'Martinica','GF':'Guyana Francese','PF':'Polinesia Francese',
  'NC':'Nuova Caledonia','RE':'Réunion','PM':'Saint-Pierre-et-Miquelon',
  // Alias comuni
  'UK':'Gran Bretagna','UAE':'Emirati Arabi',
};

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
  'Distrito Nacional':'Sud America',
  'Trinidad And Tobago':'Sud America','Belize':'Sud America',
  'Guyana':'Sud America','French Guiana':'Sud America',
  'Martinique':'Sud America','Guadeloupe':'Sud America',
  // Nomi italiani / etichette generiche
  'Brasile':'Sud America','Cile':'Sud America','Rep. Dominicana':'Sud America',
  'LATAM':'Sud America',

  // ── NORD AMERICA ──
  'United States':'Nord America','USA':'Nord America','US':'Nord America','Canada':'Nord America','CA':'Nord America',
  'HAW':'Nord America',

  // ── CARAIBI ──
  'Cayman Islands':'Caraibi','Isole Cayman':'Caraibi',
  'Barbados':'Caraibi','Bermuda':'Caraibi','Bahamas':'Caraibi',
  'Puerto Rico':'Caraibi','Aruba':'Caraibi','Curaçao':'Caraibi',
  'Curacao':'Caraibi','Saint Lucia':'Caraibi','Grenada':'Caraibi',
  'Antigua and Barbuda':'Caraibi','Antigua And Barbuda':'Caraibi',
  'Saint Kitts and Nevis':'Caraibi','Dominica':'Caraibi',
  'Virgin Islands':'Caraibi','Turks and Caicos Islands':'Caraibi',
  'Sint Maarten':'Caraibi','Saint Martin':'Caraibi',
  'Santo Domingo':'Caraibi','Tortola':'Caraibi',
  'Gustavia':'Caraibi','Saint-Paul':'Caraibi',
  'Kingstown':'Caraibi','Saint Thomas':'Caraibi',
  'Saint Vincent and the Grenadines':'Caraibi','Anguilla':'Caraibi',
  'Montserrat':'Caraibi','Bonaire':'Caraibi','Sint Eustatius':'Caraibi',

  // ── EUROPA ──
  'Albania':'Europa','AL':'Europa','Andorra':'Europa','AD':'Europa',
  'Austria':'Europa','AT':'Europa',
  'Belgium':'Europa','BE':'Europa','Belgio':'Europa',
  'Bosnia and Herzegovina':'Europa','Bosnia And Herzegovina':'Europa','BA':'Europa',
  'Bulgaria':'Europa','BG':'Europa',
  'Croatia':'Europa','HR':'Europa','Croazia':'Europa',
  'Cyprus':'Europa','CY':'Europa','Cipro':'Europa',
  'Czech Republic':'Europa','CZ':'Europa','Czechia':'Europa','Rep. Ceca':'Europa',
  'Denmark':'Europa','DK':'Europa','Danimarca':'Europa',
  'Estonia':'Europa','EE':'Europa',
  'Finland':'Europa','FI':'Europa','Finlandia':'Europa',
  'France':'Europa','FR':'Europa','Francia':'Europa',
  'Germany':'Europa','DE':'Europa','Germania':'Europa',
  'Greece':'Europa','GR':'Europa','Grecia':'Europa',
  'Hungary':'Europa','HU':'Europa','Ungheria':'Europa',
  'Iceland':'Europa','IS':'Europa','Islanda':'Europa',
  'Ireland':'Europa','IE':'Europa','Irlanda':'Europa',
  'Italy':'Europa','IT':'Europa','Italia':'Europa',
  'Kosovo':'Europa','XK':'Europa',
  'Latvia':'Europa','LV':'Europa',
  'Lithuania':'Europa','LT':'Europa',
  'Luxembourg':'Europa','LU':'Europa','Lussemburgo':'Europa',
  'Malta':'Europa','MT':'Europa',
  'Moldova':'Europa','MD':'Europa',
  'Montenegro':'Europa','ME':'Europa',
  'Netherlands':'Europa','NL':'Europa','Paesi Bassi':'Europa',
  'North Macedonia':'Europa','MK':'Europa','Macedonia':'Europa',
  'Norway':'Europa','NO':'Europa','Norvegia':'Europa',
  'Poland':'Europa','PL':'Europa','Polonia':'Europa',
  'Portugal':'Europa','PT':'Europa','Portogallo':'Europa',
  'Romania':'Europa','RO':'Europa',
  'Russia':'Europa','RU':'Europa',
  'Serbia':'Europa','RS':'Europa',
  'Slovakia':'Europa','SK':'Europa','Slovacchia':'Europa',
  'Slovenia':'Europa','SI':'Europa',
  'Spain':'Europa','ES':'Europa','Spagna':'Europa',
  'Sweden':'Europa','SE':'Europa','Svezia':'Europa',
  'Switzerland':'Europa','CH':'Europa','Svizzera':'Europa',
  'Ukraine':'Europa','UA':'Europa','Ucraina':'Europa',
  'United Kingdom':'Europa','UK':'Europa','GB':'Europa',
  'Belarus':'Europa','BY':'Europa',
  'Liechtenstein':'Europa','LI':'Europa',
  'Monaco':'Europa','MC':'Europa',
  'San Marino':'Europa','SM':'Europa',
  'Vatican City':'Europa','VA':'Europa',
  'Faroe Islands':'Europa','FO':'Europa',
  'Gibraltar':'Europa','GI':'Europa',
  'Bosnia (Federacija Bosanska)':'Europa','Republika Srpska':'Europa',
  'Douglas':'Europa','Isle of Man':'Europa','IM':'Europa',
  // Nomi italiani mancanti
  'Gran Bretagna':'Europa','Bielorussia':'Europa','Lituania':'Europa',
  'Macedonia del Nord':'Europa',
  'SQ':'Europa', // codice lingua "sq" (albanese) finito nel campo paese

  // ── SCANDINAVIA ──
  // (inclusa in Europa ma separabile se preferisci)

  // ── OCEANIA ──
  'Australia':'Oceania','AU':'Oceania',
  'New Zealand':'Oceania','NZ':'Oceania','Nuova Zelanda':'Oceania',
  'Fiji':'Oceania','FJ':'Oceania',
  'Papua New Guinea':'Oceania','PG':'Oceania','Papua Nuova Guinea':'Oceania',
  'Vanuatu':'Oceania','VU':'Oceania',
  'Solomon Islands':'Oceania','SB':'Oceania',
  'Samoa':'Oceania','WS':'Oceania',
  'Tonga':'Oceania','TO':'Oceania',
  'French Polynesia':'Oceania','PF':'Oceania',
  'New Caledonia':'Oceania','NC':'Oceania',
  'Guam':'Oceania','GU':'Oceania',

  // ── ASIA ──
  'China':'Asia','CN':'Asia','Cina':'Asia',
  'Japan':'Asia','JP':'Asia','Giappone':'Asia',
  'South Korea':'Asia','KR':'Asia','Korea':'Asia','Corea del Sud':'Asia',
  'India':'Asia','IN':'Asia',
  'Indonesia':'Asia','ID':'Asia',
  'Malaysia':'Asia','MY':'Asia',
  'Philippines':'Asia','PH':'Asia','Filippine':'Asia',
  'Singapore':'Asia','SG':'Asia',
  'Thailand':'Asia','TH':'Asia','Tailandia':'Asia',
  'Vietnam':'Asia','VN':'Asia',
  'Taiwan':'Asia','TW':'Asia',
  'Hong Kong':'Asia','HK':'Asia',
  'Bangladesh':'Asia','BD':'Asia',
  'Sri Lanka':'Asia','LK':'Asia',
  'Myanmar':'Asia','MM':'Asia',
  'Cambodia':'Asia','KH':'Asia',
  'Nepal':'Asia','NP':'Asia',
  'Pakistan':'Asia','PK':'Asia',
  'Kazakhstan':'Asia','KZ':'Asia',
  'Uzbekistan':'Asia','UZ':'Asia',
  'Mongolia':'Asia','MN':'Asia',
  'Laos':'Asia','LA':'Asia',
  'Brunei':'Asia','BN':'Asia',
  'Timor-Leste':'Asia','TL':'Asia',
  'Maldives':'Asia','MV':'Asia',
  'Bhutan':'Asia','BT':'Asia',
  'Afghanistan':'Asia','AF':'Asia',
  'Macao':'Asia','MO':'Asia','Macau':'Asia',
  'Tajikistan':'Asia','TJ':'Asia',
  'Kyrgyzstan':'Asia','KG':'Asia',
  'Turkmenistan':'Asia','TM':'Asia',
  'Azerbaijan':'Asia','AZ':'Asia','Azerbaigian':'Asia',
  'Georgia':'Asia','GE':'Asia',
  'Armenia':'Asia','AM':'Asia',
  'HY':'Asia', // codice lingua "hy" (armeno) finito nel campo paese

  // ── MEDIO ORIENTE ──
  'United Arab Emirates':'Medio Oriente','AE':'Medio Oriente','UAE':'Medio Oriente','Emirati Arabi':'Medio Oriente',
  'Saudi Arabia':'Medio Oriente','SA':'Medio Oriente','Arabia Saudita':'Medio Oriente',
  'Israel':'Medio Oriente','IL':'Medio Oriente','Israele':'Medio Oriente',
  'Qatar':'Medio Oriente','QA':'Medio Oriente',
  'Kuwait':'Medio Oriente','KW':'Medio Oriente',
  'Bahrain':'Medio Oriente','BH':'Medio Oriente',
  'Oman':'Medio Oriente','OM':'Medio Oriente',
  'Jordan':'Medio Oriente','JO':'Medio Oriente','Giordania':'Medio Oriente',
  'Lebanon':'Medio Oriente','LB':'Medio Oriente','Libano':'Medio Oriente',
  'Turkey':'Medio Oriente','TR':'Medio Oriente','Turchia':'Medio Oriente',
  'Iran':'Medio Oriente','IR':'Medio Oriente',
  'Iraq':'Medio Oriente','IQ':'Medio Oriente',
  'Syria':'Medio Oriente','SY':'Medio Oriente',
  'Yemen':'Medio Oriente','YE':'Medio Oriente',
  'Palestine':'Medio Oriente','PS':'Medio Oriente',
  'Libya':'Medio Oriente','LY':'Medio Oriente',

  // ── AFRICA ──
  'South Africa':'Africa','ZA':'Africa','Sudafrica':'Africa',
  'Kenya':'Africa','KE':'Africa',
  'Nigeria':'Africa','NG':'Africa',
  'Ethiopia':'Africa','ET':'Africa','Etiopia':'Africa',
  'Tanzania':'Africa','TZ':'Africa',
  'Uganda':'Africa','UG':'Africa',
  'Ghana':'Africa','GH':'Africa',
  'Senegal':'Africa','SN':'Africa',
  'Morocco':'Africa','MA':'Africa','Marocco':'Africa',
  'Tunisia':'Africa','TN':'Africa',
  'Algeria':'Africa','DZ':'Africa',
  'Egypt':'Africa','EG':'Africa','Egitto':'Africa',
  'Angola':'Africa','AO':'Africa',
  'Mozambique':'Africa','MZ':'Africa',
  'Zimbabwe':'Africa','ZW':'Africa',
  'Zambia':'Africa','ZM':'Africa',
  'Botswana':'Africa','BW':'Africa',
  'Namibia':'Africa','NA':'Africa',
  'Cameroon':'Africa','CM':'Africa',
  "Ivory Coast":'Africa',"Côte d'Ivoire":'Africa','CI':'Africa',
  'Madagascar':'Africa','MG':'Africa',
  'Mauritius':'Africa','MU':'Africa',
  'Rwanda':'Africa','RW':'Africa',
  'Malawi':'Africa','MW':'Africa',
  'Mali':'Africa','ML':'Africa',
  'Burkina Faso':'Africa','BF':'Africa',
  'Niger':'Africa','NE':'Africa',
  'Chad':'Africa','TD':'Africa',
  'Sudan':'Africa','SD':'Africa',
  'Somalia':'Africa','SO':'Africa',
  'Eritrea':'Africa','ER':'Africa',
  'Gabon':'Africa','GA':'Africa',
  'Republic of the Congo':'Africa','CG':'Africa',
  'Democratic Republic of the Congo':'Africa','CD':'Africa',
  'Sierra Leone':'Africa','SL':'Africa',
  'Liberia':'Africa','LR':'Africa',
  'Guinea':'Africa','GN':'Africa',
  'Gambia':'Africa','GM':'Africa',
  'Benin':'Africa','BJ':'Africa',
  'Togo':'Africa','TG':'Africa',
  'Lesotho':'Africa','LS':'Africa',
  'Eswatini':'Africa','SZ':'Africa','Swaziland':'Africa',
  'South Sudan':'Africa','SS':'Africa',

  // ── SUD AMERICA (codici ISO) ──
  'AR':'Sud America','BO':'Sud America','BR':'Sud America',
  'CL':'Sud America','CO':'Sud America','EC':'Sud America',
  'SV':'Sud America','GT':'Sud America','HN':'Sud America',
  'MX':'Sud America','NI':'Sud America','PA':'Sud America',
  'PY':'Sud America','PE':'Sud America','SR':'Sud America',
  'UY':'Sud America','VE':'Sud America','CR':'Sud America',
  'DO':'Sud America','CU':'Sud America','HT':'Sud America',
  'JM':'Sud America','TT':'Sud America','BZ':'Sud America',
  'GY':'Sud America','GF':'Sud America','MQ':'Sud America',
  'GP':'Sud America',

  // ── CARAIBI (codici ISO) ──
  'KY':'Caraibi','BB':'Caraibi','BM':'Caraibi','BS':'Caraibi',
  'PR':'Caraibi','AW':'Caraibi','CW':'Caraibi',
  'LC':'Caraibi','GD':'Caraibi','AG':'Caraibi',
  'KN':'Caraibi','DM':'Caraibi','VI':'Caraibi',
  'TC':'Caraibi','SX':'Caraibi','MF':'Caraibi',
  'VC':'Caraibi','AI':'Caraibi','MS':'Caraibi',
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