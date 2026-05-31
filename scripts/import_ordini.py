"""
Import Ordini da Gmail — Il Ciliegio CRM
Legge email con soggetto "New Order", scarica allegato PDF Fieramente,
parsa i campi e aggiorna data/ordini.json su GitHub.
"""

import imaplib
import email
import email.header
import json
import os
import re
import base64
import io
import random
import string
from datetime import datetime, timedelta, timezone

import pdfplumber
import requests

# ── Config da env (GitHub Secrets) ──────────────────────────────────────────
GMAIL_USER         = os.environ['GMAIL_USER']          # shop.ilciliegio@gmail.com
GMAIL_APP_PASSWORD = os.environ['GMAIL_APP_PASSWORD']
GH_TOKEN           = os.environ['GH_TOKEN']
GH_REPO            = os.environ['GH_REPO']             # owner/repo
DATA_PATH          = 'data/ordini.json'

SKIP_EMAILS = {'ilciliegio', 'shop@', 'noreply', 'no-reply', 'fieramente',
               'sienawine', 'mailer-daemon', 'bounce', 'notification'}


# ── IMAP ────────────────────────────────────────────────────────────────────

def fetch_new_emails(since_date: datetime) -> list[dict]:
    """Connette a Gmail via IMAP, restituisce lista ordini grezzi."""
    since_str = since_date.strftime('%d-%b-%Y')   # es. "01-May-2026"

    mail = imaplib.IMAP4_SSL('imap.gmail.com')
    mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    mail.select('inbox')

    criteria = f'(SINCE {since_str} SUBJECT "New Order")'
    _, nums = mail.search(None, criteria)

    orders = []
    for num in (nums[0] or b'').split():
        _, data = mail.fetch(num, '(RFC822)')
        raw = data[0][1]
        msg = email.message_from_bytes(raw)
        order = _parse_email(msg)
        if order:
            orders.append(order)
            print(f'  Trovato: {order["customerName"]} — {order.get("shipmentCode","?")} — €{order["amount"]}')

    mail.logout()
    return orders


def _decode_header(raw: str) -> str:
    parts = email.header.decode_header(raw or '')
    out = ''
    for part, enc in parts:
        if isinstance(part, bytes):
            out += part.decode(enc or 'utf-8', errors='replace')
        else:
            out += part
    return out


def _parse_email(msg) -> dict | None:
    subject_raw = _decode_header(msg.get('Subject', ''))
    date_raw    = msg.get('Date', '')
    msg_id      = msg.get('Message-ID', '').strip()

    # Rimuove prefisso forward
    subject = re.sub(r'^(I:|Fw:|Fwd:|R:|Re:|Inoltrato:)\s+', '', subject_raw, flags=re.I).strip()

    # Pattern: "🍷 New Order — NOME COGNOME — 294.05 EUR"
    m = re.search(
        r'New\s+Order\s*[—\-–]+\s*(.+?)\s*[—\-–]+\s*([\d.,]+)\s*(EUR|USD|GBP)?',
        subject, re.I
    )
    if not m:
        return None

    customer_name = m.group(1).strip()
    amount        = float(m.group(2).replace(',', '.'))
    currency      = (m.group(3) or 'EUR').upper()

    # Data ordine
    try:
        from email.utils import parsedate_to_datetime
        order_date = int(parsedate_to_datetime(date_raw).timestamp() * 1000)
    except Exception:
        order_date = int(datetime.now(timezone.utc).timestamp() * 1000)

    # Cerca allegato PDF
    pdf_bytes = None
    for part in msg.walk():
        if part.get_content_type() == 'application/pdf':
            pdf_bytes = part.get_payload(decode=True)
            break

    order = {
        'customerName':    customer_name,
        'amount':          amount,
        'currency':        currency,
        'orderDate':       order_date,
        'emailSubject':    subject,
        'gmailMessageId':  msg_id,
        'customerEmail':   '',
        'customerPhone':   '',
        'shipmentCode':    '',
        'shippingAddress': '',
        'numberOfCartons': None,
    }

    if pdf_bytes:
        pdf_fields = parse_fieramente_pdf(pdf_bytes)
        order.update({k: v for k, v in pdf_fields.items() if v is not None})
    else:
        print(f'    ⚠ Nessun PDF allegato per {customer_name}')

    return order


# ── PDF parsing (Fieramente Merchant Order Sheet) ───────────────────────────

def parse_fieramente_pdf(pdf_bytes: bytes) -> dict:
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            page = pdf.pages[0]
            text = page.extract_text(x_tolerance=3, y_tolerance=3) or ''
    except Exception as e:
        print(f'    ⚠ Errore lettura PDF: {e}')
        return {}

    def after(label: str) -> str:
        """Valore sulla riga successiva all'etichetta."""
        pattern = label.replace(' ', r'\s+') + r'\s*\n\s*([^\n]+)'
        m = re.search(pattern, text, re.I)
        return m.group(1).strip() if m else ''

    def inline(label: str) -> str:
        """Valore sulla stessa riga dell'etichetta (dopo spazio)."""
        pattern = label.replace(' ', r'\s+') + r'\s+([^\n]+)'
        m = re.search(pattern, text, re.I)
        return m.group(1).strip() if m else ''

    # SHIPMENT CODE (potrebbe essere sulla stessa riga o sulla successiva)
    shipment_code = after('SHIPMENT CODE') or inline('SHIPMENT CODE')
    # Rimuove testo spurio: deve essere solo lettere maiuscole
    if shipment_code:
        m = re.match(r'^([A-Z]+)', shipment_code)
        shipment_code = m.group(1) if m else ''

    # EMAIL: prima email non di sistema
    all_emails = re.findall(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,6}\b', text)
    customer_email = next(
        (e for e in all_emails if not any(s in e.lower() for s in SKIP_EMAILS)),
        ''
    )

    # PHONE
    customer_phone = after('PHONE') or inline('PHONE')
    # Normalizza: mantieni solo cifre e +
    if customer_phone:
        customer_phone = re.sub(r'[^\d+]', '', customer_phone)

    # INDIRIZZO COMPLETO
    address = after('ADDRESS')
    city    = after('CITY')
    zip_code = after('ZIP CODE') or after('ZIP')
    state   = after('STATE / COUNTRY') or after('STATE/COUNTRY') or after('STATE')
    shipping_address = ', '.join(filter(None, [address, city, zip_code, state]))

    # NUMBER OF CARTONS
    m = re.search(r'NUMBER\s+OF\s+CARTONS\s*[\n\s]+(\d+)', text, re.I)
    number_of_cartons = int(m.group(1)) if m else None

    result = {
        'shipmentCode':    shipment_code,
        'customerEmail':   customer_email,
        'customerPhone':   customer_phone,
        'shippingAddress': shipping_address,
        'numberOfCartons': number_of_cartons,
    }
    print(f'    PDF → code={shipment_code} email={customer_email} colli={number_of_cartons}')
    return result


# ── GitHub: leggi / scrivi ordini.json ──────────────────────────────────────

_GH_HEADERS = {
    'Authorization': f'token {GH_TOKEN}',
    'Accept':        'application/vnd.github.v3+json',
}


def load_ordini() -> tuple[dict, str | None]:
    url = f'https://api.github.com/repos/{GH_REPO}/contents/{DATA_PATH}'
    r = requests.get(url, headers=_GH_HEADERS)
    if r.status_code == 404:
        return {'orders': [], 'lastImportedAt': None}, None
    r.raise_for_status()
    data = r.json()
    content = base64.b64decode(data['content']).decode('utf-8')
    return json.loads(content), data['sha']


def save_ordini(db: dict, sha: str | None) -> None:
    url     = f'https://api.github.com/repos/{GH_REPO}/contents/{DATA_PATH}'
    content = base64.b64encode(
        json.dumps(db, ensure_ascii=False, indent=2).encode('utf-8')
    ).decode('utf-8')
    now_str = datetime.now().strftime('%d/%m/%Y %H:%M')
    body    = {'message': f'Import ordini — {now_str}', 'content': content}
    if sha:
        body['sha'] = sha
    r = requests.put(url, headers=_GH_HEADERS, json=body)
    r.raise_for_status()


# ── ID univoco ordine ────────────────────────────────────────────────────────

def uid_ord() -> str:
    ts   = int(datetime.now(timezone.utc).timestamp() * 1000)
    b36  = ''
    n    = ts
    chars = '0123456789abcdefghijklmnopqrstuvwxyz'
    while n:
        b36 = chars[n % 36] + b36
        n //= 36
    rnd = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f'ord_{b36}{rnd}'


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print('=== Import Ordini da Gmail ===')

    # Carica ordini esistenti
    db, sha = load_ordini()
    existing = db.get('orders', [])
    print(f'Ordini esistenti: {len(existing)}')

    # Data di partenza: lastImportedAt - 1 giorno, o ultimi 30 giorni
    if db.get('lastImportedAt'):
        from_dt = datetime.fromtimestamp(db['lastImportedAt'] / 1000, tz=timezone.utc) - timedelta(days=1)
    else:
        from_dt = datetime.now(timezone.utc) - timedelta(days=30)

    print(f'Cerco email dal: {from_dt.strftime("%d/%m/%Y")}')

    # Fetch da Gmail
    new_orders_raw = fetch_new_emails(from_dt)
    print(f'Email trovate: {len(new_orders_raw)}')

    # Dedup e costruzione record
    imported = 0
    now_ms   = int(datetime.now(timezone.utc).timestamp() * 1000)

    for o in new_orders_raw:
        already = any(
            (ex.get('gmailMessageId') and ex['gmailMessageId'] == o['gmailMessageId'])
            or ex.get('emailSubject') == o.get('emailSubject')
            for ex in existing
        )
        if already:
            print(f'  Skip (già presente): {o["customerName"]}')
            continue

        record = {
            'id':              uid_ord(),
            'customerName':    o['customerName'],
            'customerEmail':   o.get('customerEmail', ''),
            'customerPhone':   o.get('customerPhone', ''),
            'amount':          o['amount'],
            'currency':        o['currency'],
            'orderDate':       o['orderDate'],
            'emailSubject':    o.get('emailSubject', ''),
            'shipmentCode':    o.get('shipmentCode', ''),
            'shippingAddress': o.get('shippingAddress', ''),
            'numberOfCartons': o.get('numberOfCartons'),
            'gmailMessageId':  o.get('gmailMessageId', ''),
            'trackingNumber':  '',
            'carrier':         'MBE',
            'shippingDate':    None,
            'status':          'ricevuto',
            'statusHistory':   [{'status': 'ricevuto', 'date': now_ms,
                                  'note': 'Importato da Gmail (GitHub Actions)'}],
            'emailsSent':      [],
            'notes':           '',
            'createdAt':       now_ms,
            'updatedAt':       now_ms,
        }
        existing.insert(0, record)
        imported += 1
        print(f'  + {o["customerName"]} — {o.get("shipmentCode","?")} — €{o["amount"]}')

    if imported > 0:
        db['orders']         = existing
        db['lastImportedAt'] = now_ms
        save_ordini(db, sha)
        print(f'\n✓ {imported} ordini importati e salvati.')
    else:
        print('\nNessun nuovo ordine da importare.')


if __name__ == '__main__':
    main()
