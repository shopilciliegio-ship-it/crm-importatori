/* ═══ IMPORT ═══ */

function detectRegion(fname){
  const f=(fname||'').toLowerCase();
  if(/south.?am|sud.?am|latin|latam|argentina|brazil|chile|colombia|peru|ecuador|uruguay|paraguay|venezuela|bolivia|suriname/.test(f)) return 'Sud America';
  if(/cayman|caribbean|caraibi|barbados|bahamas|jamaica|trinidad|cuba|haiti/.test(f)) return 'Caraibi';
  if(/oceania|pacific|australia|new.?zeal|fiji/.test(f)) return 'Oceania';
  if(/africa|kenya|nigeria|ethiopia|tanzania|egypt|ghana|south.?afr/.test(f)) return 'Africa';
  if(/europe|europa/.test(f)) return 'Europa';
  if(/asia|china|japan|korea|india|vietnam|thailand|singapore|taiwan|hong.?kong/.test(f)) return 'Asia';
  if(/north.?am|usa|canada/.test(f)) return 'Nord America';
  if(/middle.?east|mena|uae|saudi|gulf/.test(f)) return 'Medio Oriente';
  if(/scandinav|nordic|sweden|norway|denmark|finland/.test(f)) return 'Scandinavia';
  return '';
}

// Assegna regione da paese se la regione non è stata rilevata dal nome file

function regionFromCountry(country){
  if(!country) return '';
  return COUNTRY_REGION[country] || COUNTRY_REGION[country.trim()] || 'Altro';
}

function parseXlsx(wb, filename){
  if(isClienti()) return parseXlsxClienti(wb, filename);
  return parseXlsxImportatori(wb, filename);
}

function parseXlsxClienti(wb, filename){
  const contacts=[];
  const seen=new Set();

  wb.SheetNames.forEach(sheetName=>{
    const ws=wb.Sheets[sheetName];
    if(!ws) return;
    const rows=XLSX.utils.sheet_to_json(ws,{header:1,defval:'',raw:false});
    if(!rows||rows.length<1) return;

    // Rileva header
    const hdr=rows[0].map(h=>String(h||'').trim().toLowerCase());
    const hi=(names,fb)=>{
      for(const n of names){const i=hdr.indexOf(n);if(i>=0)return i;}
      return fb;
    };
    const hasHeader=hdr.some(h=>['nome','cognome','email','name','firstname','surname'].includes(h));
    const IDX={
      nome:    hi(['nome','name','firstname','first_name'],0),
      cognome: hi(['cognome','surname','lastname','last_name'],1),
      email:   hi(['email','e-mail','mail'],2),
      lingua:  hi(['lingua','language','lang'],3),
      browser: hi(['linguabrowser','browser','browserlang'],4),
      country: hi(['paese','country','nazione'],5),
      valido:  hi(['valido','valid','stato'],6),
    };
    const dataRows=hasHeader?rows.slice(1):rows;

    dataRows.forEach(row=>{
      const g=i=>String(row[i]||'').trim();
      const nome=g(IDX.nome);
      const cognome=g(IDX.cognome);
      const email=g(IDX.email).toLowerCase();
      const lingua=g(IDX.lingua)||g(IDX.browser).split('-')[0]||'en';
      const country=g(IDX.country);
      const valido=g(IDX.valido); // Valido / Non Valido / Sospetta / Da verificare / Sconosciuto

      // Salta solo righe senza email o senza @
      if(!email||!email.includes('@')) return;
      if(seen.has(email)) return;
      seen.add(email);

      // Normalizza lo stato email
      const vLow=(valido||'').toLowerCase();
      let statoEmail='sconosciuto';
      if(vLow==='valido') statoEmail='valido';
      else if(vLow==='non valido') statoEmail='non_valido';
      else if(vLow==='sospetta') statoEmail='sospetta';
      else if(vLow==='da verificare'||vLow==='sconosciuto') statoEmail='da_verificare';

      contacts.push({nome,cognome,email,lingua,country,statoEmail,
        company:nome+' '+cognome, name:nome+' '+cognome});
    });
  });
  return contacts;
}

function parseXlsxImportatori(wb, filename){
  const region = detectRegion(filename);
  const allContacts = [];

  wb.SheetNames.forEach(sheetName => {
    const ws = wb.Sheets[sheetName];
    if(!ws) return;
    const rows = XLSX.utils.sheet_to_json(ws, {header:1, defval:'', raw:false});
    if(!rows || rows.length < 1) return;

    const firstRow = rows[0].map(h => String(h||'').trim());

    // ── FORMATO NUOVO (27 colonne con header: CompanyName, CompId, …) ──
    const isNewFormat = firstRow.some(h =>
      ['companyname','compid','company_email','contact_name'].includes(h.toLowerCase())
    );

    if(isNewFormat){
      const col = name => firstRow.findIndex(h => h.toLowerCase() === name.toLowerCase());
      const C = {
        companyName:     col('CompanyName'),
        brandName:       col('BrandName'),
        compId:          col('CompId'),
        country:         col('Country'),
        city:            col('City'),
        state:           col('State'),
        address:         col('StreetAddress'),
        postalCode:      col('PostalCode'),
        website:         col('Website'),
        type:            col('Type'),
        prodType:        col('ProdType'),
        employees:       col('Employee'),
        sales:           col('Sales'),
        companyEmail:    col('Company_Email'),
        phone:           col('Phone'),
        founded:         col('Founded'),
        regNumber:       col('RegistrationNumber'),
        linkedinCompany: col('Linkedin'),
        facebook:        col('Facebook'),
        instagram:       col('Instagram'),
        twitter:         col('Twitter'),
        youtube:         col('Youtube'),
        contactName:     col('Contact_Name'),
        contactTitle:    col('Contact_Title'),
        contactEmail:    col('Contact_Email'),
        contactPhone:    col('Contact_Phone'),
        contactLinkedin: col('Contact_Linkedin'),
      };
      const g = (row, idx) => idx >= 0 ? String(row[idx]||'').trim().replace(/^None$/i,'') : '';

      // Raggruppa per CompId (o CompanyName se mancante)
      const groups = {};
      rows.slice(1).forEach(row => {
        const compId = g(row, C.compId) || g(row, C.companyName);
        if(!compId) return;
        if(!groups[compId]) groups[compId] = [];
        groups[compId].push(row);
      });

      Object.entries(groups).forEach(([compId, rowList]) => {
        const r = rowList[0];
        const contacts = rowList
          .map(row => ({
            name:     g(row, C.contactName),
            title:    g(row, C.contactTitle),
            email:    g(row, C.contactEmail),
            phone:    g(row, C.contactPhone),
            linkedin: g(row, C.contactLinkedin),
          }))
          .filter(c => c.name || c.email);

        allContacts.push({
          compId,
          company:     g(r, C.companyName),
          brandName:   g(r, C.brandName),
          country:     g(r, C.country) || sheetName,
          city:        g(r, C.city),
          state:       g(r, C.state),
          address:     g(r, C.address),
          postalCode:  g(r, C.postalCode),
          website:     g(r, C.website),
          type:        g(r, C.type),
          prodType:    g(r, C.prodType),
          employees:   g(r, C.employees),
          sales:       g(r, C.sales),
          email:       g(r, C.companyEmail),
          phone:       g(r, C.phone),
          founded:     g(r, C.founded),
          regNumber:   g(r, C.regNumber),
          linkedinCo:  g(r, C.linkedinCompany),
          facebook:    g(r, C.facebook),
          instagram:   g(r, C.instagram),
          twitter:     g(r, C.twitter),
          youtube:     g(r, C.youtube),
          region:      (()=>{
            const VALID=['Sud America','Oceania','Europa','Africa','Asia','Nord America','Medio Oriente','Scandinavia','Caraibi'];
            const r1=region;
            const r2=regionFromCountry(g(r, C.country));
            const r3=regionFromCountry(sheetName);
            // Usa la prima che è una regione valida
            return [r1,r2,r3].find(x=>x&&VALID.includes(x)) || r2 || r3 || sheetName;
          })(),
          contacts,
          contactName:  contacts[0]?.name  || '',
          contactTitle: contacts[0]?.title || '',
          contactEmail: contacts[0]?.email || '',
        });
      });

    } else {
      // ── FORMATO VECCHIO (BWI originale: nessun header, col fisse) ──
      // Col 0=Paese, 1=Azienda, 2=Tel, 3=Email az., 4=Dipendenti,
      // 5=Fatturato, 6=Sito, poi coppie label/valore: Name:/Nome, Job Title:/Ruolo, E-Mail:/EmailPersonale
      const g = (row, i) => i < row.length ? String(row[i]||'').trim().replace(/^-$|^None$/i,'') : '';

      const seen = new Set();
      rows.forEach(row => {
        const country  = g(row, 0) || sheetName;
        const company  = g(row, 1);
        if(!company || company.length < 2) return;
        if(company.toLowerCase() === country.toLowerCase()) return;

        const email = g(row, 3);
        const key   = email ? email.toLowerCase() : `${company.toLowerCase()}|${country.toLowerCase()}`;
        if(seen.has(key)) return;
        seen.add(key);

        // Cerca le label nella parte destra della riga (col 7 in poi)
        let cName='', cTitle='', cEmail='';
        for(let i = 7; i < row.length - 1; i++){
          const cell = String(row[i]||'').trim();
          const next = String(row[i+1]||'').trim();
          if(cell === 'Name:'      && next) cName  = next;
          if(cell === 'Job Title:' && next) cTitle = next;
          if(cell === 'E-Mail:'   && next) cEmail = next;
        }

        // Costruisce array contacts (anche se email personale è vuota)
        const contacts = (cName || cEmail) ? [{
          name:     cName,
          title:    cTitle,
          email:    cEmail,   // ← email personale preziosa
          phone:    '',
          linkedin: '',
        }] : [];

        allContacts.push({
          compId:    '',
          company,
          country,
          region:    (()=>{
            const VALID=['Sud America','Oceania','Europa','Africa','Asia','Nord America','Medio Oriente','Scandinavia','Caraibi'];
            return [region, regionFromCountry(country), regionFromCountry(sheetName)]
              .find(x=>x&&VALID.includes(x)) || regionFromCountry(country) || sheetName;
          })(),
          phone:     g(row, 2),
          email,           // email aziendale
          employees: g(row, 4),
          sales:     g(row, 5),
          website:   g(row, 6),
          contacts,
          // Legacy
          contactName:  cName,
          contactTitle: cTitle,
          contactEmail: cEmail,
        });
      });
    }
  });

  return allContacts;
}

function dedupVsDB(incoming){
  const adb = isClienti() ? dbC : db;

  const UPD_IMP = ['email','phone','website','employees','sales','contacts',
                   'type','prodType','city','state','address','postalCode',
                   'brandName','facebook','instagram','twitter','linkedinCo',
                   'youtube','founded','regNumber'];
  const UPD_CLI = ['email','country','lingua','statoEmail'];
  const UPDATE_FIELDS = isClienti() ? UPD_CLI : UPD_IMP;

  // ── Trova un record esistente nel DB che corrisponde al contatto in arrivo ──
  // Per importatori: cerca prima per compId, poi fallback su company+country
  // Questo gestisce sia i record nuovi (con compId) che i vecchi (senza)
  const findExisting = c => {
    if(isClienti()){
      const ek = (c.email||'').toLowerCase();
      return ek ? adb.contacts.find(x=>(x.email||'').toLowerCase()===ek) : null;
    }
    const inCompId  = String(c.compId||'').trim().toLowerCase();
    const inCompKey = `${(c.company||'').toLowerCase()}|${(c.country||'').toLowerCase()}`;
    return adb.contacts.find(x=>{
      // 1. Match esatto per compId (record nuovo vs nuovo)
      const xCompId = String(x.compId||'').trim().toLowerCase();
      if(inCompId && xCompId && inCompId === xCompId) return true;
      // 2. Fallback: company+country (record nuovo vs vecchio senza compId)
      const xCompKey = `${(x.company||'').toLowerCase()}|${(x.country||'').toLowerCase()}`;
      return inCompKey === xCompKey;
    });
  };

  // Chiave locale per dedup interno al file (evita doppioni nello stesso XLSX)
  const localKey = c => isClienti()
    ? (c.email||'').toLowerCase()
    : (String(c.compId||'').trim() ||
       `${(c.company||'').toLowerCase()}|${(c.country||'').toLowerCase()}`);

  const newOnes = [], updates = [], identical = [];
  const localKeys = new Set();

  incoming.forEach(c => {
    const lk = localKey(c);
    if(!lk || localKeys.has(lk)) return;
    localKeys.add(lk);

    const existing = findExisting(c);
    if(!existing){
      newOnes.push(c);
    } else {
      const changed = UPDATE_FIELDS.some(f => {
        if(f === 'contacts'){
          const inNames = new Set((c.contacts||[]).map(x=>(x.name||'').toLowerCase()).filter(Boolean));
          const exNames = new Set((existing.contacts||[]).map(x=>(x.name||'').toLowerCase()).filter(Boolean));
          return [...inNames].some(n => !exNames.has(n));
        }
        const iv = (c[f]||'').toString().trim();
        const ev = (existing[f]||'').toString().trim();
        return iv && iv !== ev;
      });
      if(changed) updates.push({...c, _existingId: existing.id});
      else identical.push(c);
    }
  });
  return {newOnes, updates, identical};
}

function showPreview(incoming,filename){
  const{newOnes,updates,identical}=dedupVsDB(incoming);
  pending={newOnes,updates};

  // Distribuzione per paese (nuovi + aggiornati)
  const byCountry={};
  [...newOnes,...updates].forEach(c=>{byCountry[c.country]=(byCountry[c.country]||0)+1;});
  const rows=Object.entries(byCountry).sort((a,b)=>b[1]-a[1])
    .map(([c,n])=>`<tr><td>${esc(c)}</td><td style="text-align:right;font-weight:700;padding-right:12px">${n}</td></tr>`).join('');

  const byRegion={};
  newOnes.forEach(c=>{byRegion[c.region]=(byRegion[c.region]||0)+1;});
  const rrows=Object.entries(byRegion)
    .map(([r,n])=>`<span style="background:var(--blue-bg);color:var(--blue-tx);padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600">${esc(r)}: ${n}</span>`).join(' ');

  const hasAction=newOnes.length||updates.length;

  document.getElementById('imp-prev').innerHTML=`
    <div style="margin-top:14px">
      <div class="imp-pills">
        <span class="ip ip-n">✓ ${newOnes.length} nuovi</span>
        ${updates.length?`<span class="ip" style="background:var(--blue-bg);color:var(--blue-tx)">↑ ${updates.length} da aggiornare</span>`:''}
        <span class="ip ip-d">= ${identical.length} già aggiornati</span>
        <span class="ip ip-f">📂 ${esc(filename)}</span>
      </div>
      ${rrows?`<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px">${rrows}</div>`:''}
      ${hasAction?`
        <div style="font-size:13px;font-weight:600;margin-bottom:6px">Distribuzione per paese:</div>
        <div class="imp-wrap">
          <table class="imp-tbl">
            <thead><tr><th>Paese</th><th style="text-align:right;padding-right:12px">Contatti</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn btp" onclick="confirmImport()">
            ✓ ${newOnes.length?`Aggiungi ${newOnes.length}`:''}${newOnes.length&&updates.length?' + ':''}${updates.length?`Aggiorna ${updates.length}`:''}
          </button>
          <button class="btn btg" onclick="pending=null;document.getElementById('imp-prev').innerHTML=''">Annulla</button>
        </div>`
      :'<p style="margin-top:10px;font-size:13px;color:var(--green-tx);font-weight:500">✓ Tutti i contatti sono già aggiornati.</p>'}
    </div>`;
}

function confirmImport(){
  if(!pending) return;
  const{newOnes,updates}=pending;
  const now=Date.now();
  let addedCount=0, updatedCount=0;

  // 1. Aggiungi nuovi contatti
  if(newOnes?.length){
    const mapped=newOnes.map(c=>{
      if(isClienti()){
        return {
          id:'c'+now+Math.random().toString(36).slice(2,8),
          nome:c.nome||'',cognome:c.cognome||'',
          email:c.email||'',lingua:c.lingua||'en',
          country:c.country||'',statoEmail:c.statoEmail||'sconosciuto',
          company:(c.nome||'')+' '+(c.cognome||''),
          name:(c.nome||'')+' '+(c.cognome||''),
          status:'new',products:[],notes:'',
          createdAt:now,updatedAt:now,
          log:[{ts:now,msg:'Importato da XLSX'}]
        };
      }
      return {
        id:       'c'+now+Math.random().toString(36).slice(2,8),
        compId:   c.compId||'',
        company:  c.company||'',
        brandName:c.brandName||'',
        email:    c.email||'',
        phone:    c.phone||'',
        country:  c.country||'',
        region:   c.region||'',
        city:     c.city||'',
        state:    c.state||'',
        address:  c.address||'',
        postalCode:c.postalCode||'',
        website:  c.website||'',
        type:     c.type||'',
        prodType: c.prodType||'',
        employees:c.employees||'',
        sales:    c.sales||'',
        founded:  c.founded||'',
        regNumber:c.regNumber||'',
        linkedinCo:c.linkedinCo||'',
        facebook: c.facebook||'',
        instagram:c.instagram||'',
        twitter:  c.twitter||'',
        youtube:  c.youtube||'',
        contacts: c.contacts||[],
        // Legacy compat per email modal
        contactName:  c.contacts?.[0]?.name  || '',
        contactTitle: c.contacts?.[0]?.title || '',
        contactEmail: c.contacts?.[0]?.email || '',
        name: c.contacts?.[0]?.name || '',
        status:'new', products:[], notes:'',
        createdAt:now, updatedAt:now,
        log:[{ts:now, msg:`Importato da XLSX (${c.contacts?.length||0} contatti)`}]
      };
    });
    (isClienti()?dbC:db).contacts=[...(isClienti()?dbC:db).contacts,...mapped];
    addedCount=mapped.length;
  }

  // 2. Aggiorna contatti esistenti (solo i campi che sono cambiati)
  const UPDATE_FIELDS=['email','phone','website','contactName','contactTitle','contactEmail','employees','sales'];
  if(updates?.length){
    updates.forEach(c=>{
      const idx=db.contacts.findIndex(x=>x.id===c._existingId);
      if(idx<0) return;
      const existing=db.contacts[idx];
      const changes=[];
      UPDATE_FIELDS.forEach(f=>{
        const v=(c[f]||'').toString().trim();
        if(v&&v!==(existing[f]||'').toString().trim()){
          changes.push(`${f}: "${existing[f]||''}" → "${v}"`);
          existing[f]=v;
        }
      });
      if(changes.length){
        existing.updatedAt=now;
        existing.log=existing.log||[];
        existing.log.push({ts:now,msg:'Aggiornato da XLSX: '+changes.join(', ')});
        updatedCount++;
      }
    });
  }

  saveDB();refreshAll();
  document.getElementById('imp-prev').innerHTML='';
  pending=null;
  const msg=`✓ ${addedCount? addedCount+' aggiunti':''}${addedCount&&updatedCount?' + ':''}${updatedCount?updatedCount+' aggiornati':''}`;
  toast(msg||'Nessuna modifica');
  showPage('contacts',document.querySelectorAll('.nb')[1]);
}

/* ── DRAG & DROP ── */

function dzO(e){e.preventDefault();document.getElementById('dz').classList.add('over');}

function dzL(){document.getElementById('dz').classList.remove('over');}

function dzD(e){e.preventDefault();dzL();processFile(e.dataTransfer.files[0]);}

function handleFile(input){processFile(input.files[0]);input.value='';}

function processFile(file){
  if(!file) return;
  const ext=file.name.split('.').pop().toLowerCase();
  if(ext==='json'){
    const r=new FileReader();
    r.onload=e=>{
      try{
        const d=JSON.parse(e.target.result);
        const arr=d.contacts||d;
        if(!Array.isArray(arr))throw new Error('Formato non valido');
        showPreview(arr,file.name);
      }catch(err){toast('JSON non valido: '+err.message);}
    };
    r.readAsText(file);
  } else if(ext==='xlsx'||ext==='xls'){
    const r=new FileReader();
    r.onload=e=>{
      try{
        const wb=XLSX.read(e.target.result,{type:'array'});
        const contacts=parseXlsx(wb,file.name);
        if(!contacts.length){toast('Nessun contatto trovato nel file');return;}
        toast(`📊 ${contacts.length} contatti trovati in ${wb.SheetNames.length} fogli (${wb.SheetNames.join(', ')})`);
        showPreview(contacts,file.name);
      }catch(err){toast('Errore: '+err.message);console.error(err);}
    };
    r.readAsArrayBuffer(file);
  } else {
    toast('Usa .xlsx o .json');
  }
}

/* ── EXPORT ── */