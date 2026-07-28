/*
Genera il MOS Fieramente per gli ordini "Shop Online" (Passepartout/PASSWEB,
subject "Invio Ordine Azienda Agricola Il Ciliegio ..."), che non passano
dall'app CiliegioShop e quindi non hanno mai un MOS allegato.

Riusa esattamente la stessa logica di compilazione PDF dell'app
(netlify/functions/create-notification.js -> buildMosPdf), copiata qui
per garantire un risultato identico: stesso template (mos-template.js),
stessi campi, stesso font-shrink-to-fit, stessa regola di sconto sul
trasporto (-5€ per 3 o 6 bottiglie, -10€ altrimenti).

Deduplica il codice spedizione controllando i codici già presenti in
data/ordini.json (non l'archivio Netlify Blobs dell'app: nessun secret
aggiuntivo richiesto — vedi commit per la scelta).

Un ordine è considerato "in attesa di MOS" se source === 'shop' e non ha
ancora uno shipmentCode assegnato; dopo l'invio riuscito lo shipmentCode
viene scritto sull'ordine, che così non verrà rielaborato nei run successivi.
*/

const https = require('https');
const { PDFDocument, StandardFonts, PDFName } = require('pdf-lib');
const mosTemplateBase64 = require('./mos-template');

const GH_TOKEN       = process.env.GH_TOKEN;
const GH_REPO        = process.env.GH_REPO;
const BREVO_API_KEY  = process.env.BREVO_API_KEY;
const DATA_PATH      = 'data/ordini.json';

// Non generare MOS per ordini precedenti all'attivazione di questa feature
// (2026-07-28 00:00 UTC): altrimenti al primo run partirebbero i MOS anche
// per tutti gli ordini "shop" storici già in archivio senza shipmentCode
// (es. quelli del backfill), inviando email per spedizioni di mesi fa.
const FEATURE_CUTOFF_MS = 1785196800000; // 2026-07-28 00:00 UTC

// ── GitHub: leggi / scrivi ordini.json ──────────────────────────────────────

function ghRequest(method, path, body) {
  return new Promise((resolve, reject) => {
    const data = body ? JSON.stringify(body) : null;
    const options = {
      hostname: 'api.github.com',
      path: `/repos/${GH_REPO}/${path}`,
      method,
      headers: Object.assign(
        {
          'Authorization': `token ${GH_TOKEN}`,
          'Accept':        'application/vnd.github.v3+json',
          'User-Agent':    'crm-importatori-generate-mos-shop',
        },
        data ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } : {}
      ),
    };
    const req = https.request(options, (res) => {
      let d = '';
      res.on('data', (c) => { d += c; });
      res.on('end', () => {
        if (res.statusCode >= 400 && res.statusCode !== 404) {
          reject(new Error(`GitHub API ${method} ${path} -> ${res.statusCode}: ${d}`));
        } else {
          resolve({ status: res.statusCode, body: d ? JSON.parse(d) : null });
        }
      });
    });
    req.on('error', reject);
    if (data) req.write(data);
    req.end();
  });
}

async function loadOrdini() {
  const r = await ghRequest('GET', `contents/${DATA_PATH}`);
  if (r.status === 404) return { db: { orders: [] }, sha: null };
  const content = Buffer.from(r.body.content, 'base64').toString('utf-8');
  return { db: JSON.parse(content), sha: r.body.sha };
}

async function saveOrdini(db, sha) {
  const content = Buffer.from(JSON.stringify(db, null, 2), 'utf-8').toString('base64');
  const now = new Date().toLocaleString('it-IT');
  const body = { message: `MOS Shop Online — ${now}`, content };
  if (sha) body.sha = sha;
  await ghRequest('PUT', `contents/${DATA_PATH}`, body);
}

// ── PDF (identico a create-notification.js -> buildMosPdf) ─────────────────

function safeText(s) {
  return String(s || '')
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^\x20-\x7E€]/g, '?');
}

function uniqueShipmentCode(baseCode, usedCodes) {
  let code = baseCode;
  let n = 2;
  while (usedCodes.has(code)) { code = baseCode + n; n++; }
  return code;
}

async function buildMosPdf(customerName, customerEmail, customerPhone, customerAddress, products, shippingType, shippingCostCustomer, shipmentCode) {
  const nameParts = customerName.trim().split(/\s+/);
  const lastName  = nameParts.length > 1 ? nameParts[nameParts.length - 1] : nameParts[0];
  const firstName = nameParts.length > 1 ? nameParts.slice(0, -1).join(' ') : '';

  // Address: "Via Roma 1, 53100 Siena, Italy" o "Via Roma 1, 53100 Siena, Italy (SI)"
  let street = '', zip = '', city = '', stateCountry = '';
  if (customerAddress) {
    const parts = customerAddress.split(/,\s*/);
    street = parts[0] || '';
    if (parts.length >= 2) {
      const m = parts[1].trim().match(/^(\d[\d-]*\d|\d)\s+(.+)$/);
      if (m) { zip = m[1]; city = m[2]; }
      else   { city = parts[1].trim(); }
    }
    if (parts.length >= 3) stateCountry = parts.slice(2).join(', ').trim();
  }

  const totalBottles = products.reduce((s, p) => s + p.qty, 0);
  const cartons       = Math.max(1, Math.ceil(totalBottles / 6));

  // Sconto trasporto per il MOS: -5€ per 3 o 6 bottiglie, -10€ per le altre quantità
  const shippingDeduction = (totalBottles === 3 || totalBottles === 6) ? 5 : 10;
  const shippingCost       = Math.max(0, (shippingCostCustomer || 0) - shippingDeduction).toFixed(2);
  const shippingTypeLabel  = shippingType === 'express' ? 'EXPRESS 30' : 'STANDARD';

  const pdfDoc      = await PDFDocument.load(Buffer.from(mosTemplateBase64, 'base64'));
  const measureFont = await pdfDoc.embedFont(StandardFonts.Helvetica);
  const form        = pdfDoc.getForm();

  const setTxt = function (fieldName, value, size) {
    const field = form.getTextField(fieldName);
    const text  = safeText(value || '');
    const maxW  = field.acroField.getWidgets()[0].getRectangle().width - 6;
    let fontSize = size || 9;
    while (fontSize > 5 && measureFont.widthOfTextAtSize(text, fontSize) > maxW) fontSize -= 0.5;
    field.setFontSize(fontSize);
    field.setText(text);
    field.acroField.getWidgets().forEach(function (w) { w.dict.delete(PDFName.of('DA')); });
  };
  const setChk = function (fieldName, checked) {
    const field = form.getCheckBox(fieldName);
    if (checked) field.check(); else field.uncheck();
  };

  setTxt('text_2othq', shipmentCode, 12);                                    // SHIPMENT CODE
  setTxt('text_4ezat', (firstName + ' ' + lastName).trim().toUpperCase());   // NAME
  setTxt('text_6daor', street.toUpperCase());                                // ADDRESS
  setTxt('text_7ktyf', city.toUpperCase());                                  // CITY
  setTxt('text_8iwze', zip);                                                 // ZIP CODE
  setTxt('text_9wqbl', stateCountry.toUpperCase());                          // STATE / COUNTRY
  setTxt('text_10cfnx', customerPhone);                                      // PHONE
  setTxt('text_11idhv', customerEmail);                                      // EMAIL

  // Righe prodotto: il template ha 8 righe fisse (qty / descrizione / valore ciascuna)
  const rowFields = [
    ['text_12bmpo', 'text_13aijv', 'text_14tbmq'],
    ['text_15rbv',  'text_16uqhq', 'text_17hwko'],
    ['text_18oigy', 'text_19wznr', 'text_20cepq'],
    ['text_21mjuv', 'text_22sjlf', 'text_23ojur'],
    ['text_24koai', 'text_25nqpu', 'text_26ygjl'],
    ['text_27gutj', 'text_28gjvu', 'text_29tixe'],
    ['text_30tpqc', 'text_31fnze', 'text_32ayuh'],
    ['text_33otru', 'text_35udmd', 'text_36ktod'],
  ];
  const rows = products.slice(0, rowFields.length - 1).map(function (p) {
    return { qty: p.qty, name: p.description, lineValue: Number(p.value) || 0 };
  });
  if (products.length > rowFields.length - 1) {
    const overflow = products.slice(rowFields.length - 1);
    rows.push({
      qty: overflow.reduce(function (s, p) { return s + p.qty; }, 0),
      name: overflow.map(function (p) { return p.qty + 'x ' + p.description; }).join('; '),
      lineValue: overflow.reduce(function (s, p) { return s + (Number(p.value) || 0); }, 0),
    });
  }
  rows.forEach(function (p, i) {
    const qf = rowFields[i][0], df = rowFields[i][1], vf = rowFields[i][2];
    setTxt(qf, String(p.qty));
    setTxt(df, p.name.toUpperCase());
    if (p.lineValue > 0) setTxt(vf, '€ ' + p.lineValue.toFixed(2));
  });

  setChk('checkbox_39nucj', true);                                 // INVOICE TO SENDER/WINERY
  setChk('checkbox_69dycu', shippingTypeLabel === 'STANDARD');      // STANDARD
  setChk('checkbox_70pzpv', shippingTypeLabel === 'EXPRESS 30');    // EXPRESS 30
  setTxt('text_75yffy', '€ ' + shippingCost);                       // TOTAL SHIPPING CHARGES
  setTxt('text_76wlyk', String(cartons));                          // NUMBER OF CARTONS

  const pdfBytes = await pdfDoc.save();
  return {
    content:          Buffer.from(pdfBytes).toString('base64'),
    name:             shipmentCode + '.pdf',
    shippingCostMos:  parseFloat(shippingCost),
    cartons:          cartons,
  };
}

// ── Email (Brevo) ────────────────────────────────────────────────────────────

function sendEmail(toEmail, toName, subject, html, attachment) {
  return new Promise(function (resolve) {
    const data = {
      sender:      { name: 'Il Ciliegio Shop', email: 'luca@sienawine.it' },
      to:          [{ email: toEmail, name: toName }],
      subject:     subject,
      htmlContent: html,
      attachment:  [attachment],
    };
    const payload = JSON.stringify(data);
    const options = {
      hostname: 'api.brevo.com',
      path:     '/v3/smtp/email',
      method:   'POST',
      headers:  { 'api-key': BREVO_API_KEY, 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) },
    };
    const req = https.request(options, function (res) {
      let d = '';
      res.on('data', function (c) { d += c; });
      res.on('end', function () {
        console.log('  Email MOS a', toEmail, ':', res.statusCode);
        resolve(res.statusCode < 300);
      });
    });
    req.on('error', function (e) { console.error('  Errore invio email:', e.message); resolve(false); });
    req.write(payload);
    req.end();
  });
}

function buildNotificationHtml(order, shipmentCode) {
  const gold = '#D4AF37';
  const productRows = (order.products || []).map(function (p) {
    return '<tr><td style="padding:7px 12px;font-size:13px;border-bottom:1px solid #f5f5f5">'
      + p.qty + 'x ' + p.description + ' (€' + Number(p.value).toFixed(2) + ')</td></tr>';
  }).join('');
  return '<div style="max-width:600px;margin:0 auto;border:1px solid #ddd;border-radius:4px;overflow:hidden;font-family:Arial,sans-serif">'
    + '<div style="background:#111;padding:24px 20px;text-align:center">'
    + '<div style="color:' + gold + ';font-size:24px;font-weight:bold;letter-spacing:3px;font-family:Georgia,serif">IL CILIEGIO</div>'
    + '<div style="color:#888;font-size:11px;letter-spacing:4px;margin-top:4px">AZIENDA AGRICOLA</div></div>'
    + '<div style="padding:24px 20px">'
    + '<h2 style="color:' + gold + ';font-size:18px;margin:0 0 4px 0">🍷 Nuovo ordine Shop Online — ' + shipmentCode + '</h2>'
    + '<p style="color:#666;font-size:12px;margin:0 0 20px 0">Ordine ' + (order.orderNumber || '') + ' — ' + order.customerName + '. MOS Fieramente in allegato.</p>'
    + '<table style="width:100%;border-collapse:collapse;border:1px solid #eee">' + productRows + '</table></div>'
    + '<div style="background:#f5f5f5;padding:12px;text-align:center;font-size:11px;color:#888;border-top:2px solid ' + gold + '">Il Ciliegio — Azienda Agricola</div></div>';
}

// ── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  console.log('=== Genera MOS ordini Shop Online ===');
  const { db, sha } = await loadOrdini();
  const orders = db.orders || [];
  const usedCodes = new Set(orders.map(function (o) { return (o.shipmentCode || '').toUpperCase(); }).filter(Boolean));

  const pending = orders.filter(function (o) {
    return o.source === 'shop' && !o.shipmentCode && o.products && o.products.length > 0
      && (o.orderDate || 0) >= FEATURE_CUTOFF_MS;
  });
  console.log(`Ordini Shop Online in attesa di MOS: ${pending.length}`);

  let done = 0;
  for (const order of pending) {
    try {
      const nameParts  = order.customerName.trim().split(/\s+/);
      const lastName   = nameParts.length > 1 ? nameParts[nameParts.length - 1] : nameParts[0];
      const firstName  = nameParts.length > 1 ? nameParts.slice(0, -1).join(' ') : '';
      const baseCode   = (lastName + (firstName ? firstName[0] : '')).toUpperCase().replace(/[^A-Z0-9]/g, '');
      const shipmentCode = uniqueShipmentCode(baseCode, usedCodes);

      const mos = await buildMosPdf(
        order.customerName, order.customerEmail, order.customerPhone, order.shippingAddress,
        order.products, order.shippingType, order.shippingCostCustomer, shipmentCode
      );

      const html    = buildNotificationHtml(order, shipmentCode);
      const subject = `🍷 MOS Shop Online — ${order.customerName} — ${shipmentCode}`;
      const attachment = { content: mos.content, name: mos.name };

      const ok1 = await sendEmail('shop@ilciliegio.com', 'Il Ciliegio', subject, html, attachment);
      const ok2 = await sendEmail('shop.ilciliegio@gmail.com', 'Il Ciliegio CRM', subject, html, attachment);

      if (ok1 || ok2) {
        order.shipmentCode     = shipmentCode;
        order.shippingCostMos  = mos.shippingCostMos;
        order.numberOfCartons  = order.numberOfCartons != null ? order.numberOfCartons : mos.cartons;
        order.updatedAt        = Date.now();
        usedCodes.add(shipmentCode.toUpperCase());
        done++;
        console.log(`  + MOS generato e inviato: ${order.customerName} — ${shipmentCode}`);
      } else {
        console.log(`  ⚠ Invio fallito per entrambi i destinatari, riprovo al prossimo giro: ${order.customerName}`);
      }
    } catch (e) {
      console.error(`  ⚠ Errore su ${order.customerName}:`, e.message);
    }
  }

  if (done > 0) {
    await saveOrdini(db, sha);
    console.log(`\n✓ ${done} MOS generati e salvati.`);
  } else {
    console.log('\nNessun MOS da generare.');
  }
}

if (require.main === module) {
  main().catch(function (e) { console.error(e); process.exit(1); });
}

module.exports = { buildMosPdf, uniqueShipmentCode, safeText };
