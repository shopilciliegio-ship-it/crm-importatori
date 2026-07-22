"""
Fetch Fieramente Tracking — Il Ciliegio CRM
REST API su track.fieramente.biz — nessun Playwright necessario.
Token JWT rigenerato ad ogni run (scade in 24h, workflow gira ogni 24h).

Mapping status Fieramente → CRM:
  0 Not yet active          → ricevuto
  1 Label created           → preparazione
  2 Shipped, in transit     → in_transito
  3 Under customs (US)      → dogana
  4 From US warehouse       → in_consegna
  5 Delivered               → consegnato
  6 Not yet active          → ricevuto
  7 Picked up by carrier    → spedito
  8 Pending customs         → dogana
  9 Picked up by UPS        → in_transito
"""

import base64
import json
import os
import re
import time
from datetime import datetime, timezone

import requests

# ── Config ────────────────────────────────────────────────────────────────────
FIERAMENTE_USER = os.environ.get('FIERAMENTE_USER', 'ILCILIEGIO')
FIERAMENTE_PASS = os.environ.get('FIERAMENTE_PASS', 'ILCILIEGIO1')
GH_TOKEN        = os.environ['GH_TOKEN']
GH_REPO         = os.environ['GH_REPO']
DATA_PATH       = 'data/ordini.json'
FIERAMENTE_API  = 'https://track.fieramente.biz/api'

STATUS_MAP = {
    '0': 'ricevuto',
    '1': 'preparazione',
    '2': 'in_transito',
    '3': 'dogana',
    '4': 'in_consegna',
    '5': 'consegnato',
    '6': 'ricevuto',
    '7': 'spedito',
    '8': 'dogana',
    '9': 'in_consegna',
}

def derive_candidate_code(customer_name: str) -> str | None:
    """Deriva il codice MBE atteso da un nome cliente: COGNOME + iniziale nome
    (es. 'ELIZABETH CONTI' → 'CONTIE'), lo stesso schema usato da Fieramente/MBE.
    Richiede almeno nome e cognome; assume che l'ultima parola sia il cognome."""
    parts = (customer_name or '').strip().split()
    if len(parts) < 2:
        return None
    first, last = parts[0], parts[-1]
    last_clean     = re.sub(r'[^A-Za-z]', '', last).upper()
    first_initial  = re.sub(r'[^A-Za-z]', '', first).upper()[:1]
    if not last_clean or not first_initial:
        return None
    return last_clean + first_initial


STATUS_RANK = {s: i for i, s in enumerate([
    'ricevuto', 'preparazione', 'spedito', 'in_transito', 'dogana',
    'in_consegna', 'consegna_fallita', 'consegnato', 'problema', 'annullato',
])}

TERMINAL_STATUSES = {'consegnato', 'annullato'}

_GH_HEADERS = {
    'Authorization': f'token {GH_TOKEN}',
    'Accept':        'application/vnd.github.v3+json',
}


# ── GitHub helpers ─────────────────────────────────────────────────────────────

def _gh_request(method, url, **kwargs):
    """Ritenta su 502/503/504 (errori transitori dei server GitHub) — max 3 tentativi."""
    for attempt in range(3):
        r = requests.request(method, url, **kwargs)
        if r.status_code in (502, 503, 504) and attempt < 2:
            time.sleep(2 ** attempt)
            continue
        return r


def gh_get(path):
    url = f'https://api.github.com/repos/{GH_REPO}/contents/{path}'
    r   = _gh_request('GET', url, headers=_GH_HEADERS)
    if r.status_code == 404:
        return {}, None
    r.raise_for_status()
    data    = r.json()
    content = base64.b64decode(data['content']).decode('utf-8')
    return json.loads(content), data['sha']


def gh_put(path, data, sha, message):
    url     = f'https://api.github.com/repos/{GH_REPO}/contents/{path}'
    content = base64.b64encode(
        json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    ).decode('utf-8')
    body = {'message': message, 'content': content}
    if sha:
        body['sha'] = sha
    _gh_request('PUT', url, headers=_GH_HEADERS, json=body).raise_for_status()


# ── Fieramente API ─────────────────────────────────────────────────────────────

def fieramente_login():
    r = requests.post(f'{FIERAMENTE_API}/login', json={
        'username': FIERAMENTE_USER,
        'password': FIERAMENTE_PASS,
    }, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get('success'):
        raise RuntimeError(f'Login Fieramente fallito: {data}')
    print('✓ Login Fieramente OK')
    return data['data']['token']


def fieramente_get_shipments(token):
    r = requests.get(
        f'{FIERAMENTE_API}/shipments/{FIERAMENTE_USER}',
        headers={'Authorization': f'Bearer {token}'},
        timeout=30,
    )
    r.raise_for_status()
    shipments = r.json()
    print(f'✓ {len(shipments)} spedizioni ricevute da Fieramente')
    return shipments


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print('=== Fetch Fieramente Tracking — Il Ciliegio ===')

    try:
        token     = fieramente_login()
        fier_list = fieramente_get_shipments(token)
    except requests.exceptions.RequestException as e:
        print(f'⚠ Fieramente non raggiungibile, salto questo step: {e}')
        return

    # Debug: stampa tutti i campi della prima spedizione per mappatura futura
    if fier_list:
        print(f'  [debug] campi spedizione Fieramente: {sorted(fier_list[0].keys())}')

    fier_by_code = {
        s['mbe_code'].strip().upper(): s
        for s in fier_list if s.get('mbe_code')
    }

    # Fallback per email: esclude email ambigue (stesso cliente, più ordini attivi)
    from collections import Counter
    email_counts = Counter(
        s['customer_email'].strip().lower()
        for s in fier_list if s.get('customer_email')
    )
    fier_by_email = {
        s['customer_email'].strip().lower(): s
        for s in fier_list
        if s.get('customer_email') and email_counts[s['customer_email'].strip().lower()] == 1
    }

    def fier_by_derived_name(customer_name: str):
        """Fallback quando shipmentCode ed email non combaciano (es. refuso email
        tipo Elizabeth/Elisabeth): cerca per COGNOME+iniziale derivato dal nome,
        incluso un eventuale suffisso numerico che Fieramente aggiunge in caso di
        omonimi (es. CONTIE, CONTIE2). Ritorna None se zero o più match (ambiguo)."""
        candidate = derive_candidate_code(customer_name)
        if not candidate:
            return None
        matches = [
            s for s in fier_list
            if (code := (s.get('mbe_code') or '').strip().upper())
            and (code == candidate or (code.startswith(candidate) and code[len(candidate):].isdigit()))
        ]
        return matches[0] if len(matches) == 1 else None

    db, sha_db = gh_get(DATA_PATH)
    orders     = db.get('orders') or []
    now_ms     = int(datetime.now(timezone.utc).timestamp() * 1000)
    changed    = 0

    for order in orders:
        code = (order.get('shipmentCode') or '').strip().upper()
        fier = fier_by_code.get(code) if code else None

        if not fier:
            email = (order.get('customerEmail') or '').strip().lower()
            fier  = fier_by_email.get(email) if email else None
            if fier:
                # Salva il codice per i prossimi run (evita lookup per email)
                mbe_code = (fier.get('mbe_code') or '').strip()
                if mbe_code and not order.get('shipmentCode'):
                    order['shipmentCode'] = mbe_code
                    print(f'  {order.get("customerName","?")}: shipmentCode → {mbe_code} (match email)')

        if not fier:
            # Ultimo fallback: codice derivato dal nome (COGNOME+iniziale). Copre i
            # casi in cui email diverse tra ordine e Fieramente (refusi tipo
            # Elizabeth/Elisabeth) impediscono il match per email.
            fier = fier_by_derived_name(order.get('customerName', ''))
            if fier:
                mbe_code = (fier.get('mbe_code') or '').strip()
                if mbe_code and not order.get('shipmentCode'):
                    order['shipmentCode'] = mbe_code
                    print(f'  {order.get("customerName","?")}: shipmentCode → {mbe_code} (match nome derivato)')

        if not fier:
            continue

        name       = order.get('customerName', '?')
        cur_status = order.get('status', 'ricevuto')
        new_status = STATUS_MAP.get(str(fier.get('status', '')))
        tracking   = (fier.get('tracking') or '').strip()
        updated    = False

        if tracking and order.get('trackingNumber') != tracking:
            order['trackingNumber'] = tracking
            print(f'  {name}: tracking → {tracking}')
            updated = True

        # shippingDate = giorno in cui rileviamo il tracking number, non il
        # ship_date di Fieramente (poco affidabile: arriva in ritardo o non
        # arriva affatto, e la finestra del reminder day0 è di soli 3 giorni).
        if tracking and not order.get('shippingDate'):
            order['shippingDate'] = now_ms
            print(f'  {name}: shippingDate → oggi (tracking number rilevato)')
            updated = True

        if new_status and cur_status not in TERMINAL_STATUSES:
            cur_rank = STATUS_RANK.get(cur_status, 0)
            new_rank = STATUS_RANK.get(new_status, 0)
            if new_rank > cur_rank:
                order.setdefault('statusHistory', []).append({
                    'status': new_status,
                    'date':   now_ms,
                    'note':   f'Auto Fieramente (era: {cur_status})',
                })
                order['status'] = new_status
                print(f'  {name}: {cur_status} → {new_status}')
                updated = True

        if updated:
            order['updatedAt'] = now_ms
            changed += 1

    if changed > 0:
        db['orders'] = orders
        now_str = datetime.now().strftime('%d/%m/%Y %H:%M')
        gh_put(DATA_PATH, db, sha_db,
               f'Fieramente tracking — {changed} ordini aggiornati — {now_str}')
        print(f'\n✓ {changed} ordini aggiornati, ordini.json salvato.')
    else:
        print('\nNessun aggiornamento da Fieramente.')


if __name__ == '__main__':
    main()
