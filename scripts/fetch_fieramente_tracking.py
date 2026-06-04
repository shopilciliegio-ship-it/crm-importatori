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

STATUS_RANK = {s: i for i, s in enumerate([
    'ricevuto', 'preparazione', 'spedito', 'in_transito',
    'dogana', 'in_consegna', 'consegnato', 'problema', 'annullato',
])}

TERMINAL_STATUSES = {'consegnato', 'annullato'}

_GH_HEADERS = {
    'Authorization': f'token {GH_TOKEN}',
    'Accept':        'application/vnd.github.v3+json',
}


# ── GitHub helpers ─────────────────────────────────────────────────────────────

def gh_get(path):
    url = f'https://api.github.com/repos/{GH_REPO}/contents/{path}'
    r   = requests.get(url, headers=_GH_HEADERS)
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
    requests.put(url, headers=_GH_HEADERS, json=body).raise_for_status()


# ── Fieramente API ─────────────────────────────────────────────────────────────

def fieramente_login():
    r = requests.post(f'{FIERAMENTE_API}/login', json={
        'username': FIERAMENTE_USER,
        'password': FIERAMENTE_PASS,
    })
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
    )
    r.raise_for_status()
    shipments = r.json()
    print(f'✓ {len(shipments)} spedizioni ricevute da Fieramente')
    return shipments


def date_to_ms(date_str):
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(str(date_str).strip())
        return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
    except (ValueError, TypeError):
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print('=== Fetch Fieramente Tracking — Il Ciliegio ===')

    token     = fieramente_login()
    fier_list = fieramente_get_shipments(token)

    fier_by_code = {
        s['mbe_code'].strip().upper(): s
        for s in fier_list if s.get('mbe_code')
    }

    db, sha_db = gh_get(DATA_PATH)
    orders     = db.get('orders') or []
    now_ms     = int(datetime.now(timezone.utc).timestamp() * 1000)
    changed    = 0

    for order in orders:
        code = (order.get('shipmentCode') or '').strip().upper()
        if not code:
            continue
        fier = fier_by_code.get(code)
        if not fier:
            continue

        name       = order.get('customerName', '?')
        cur_status = order.get('status', 'ricevuto')
        new_status = STATUS_MAP.get(str(fier.get('status', '')))
        tracking   = (fier.get('tracking') or '').strip()
        ship_ms    = date_to_ms(fier.get('ship_date'))
        updated    = False

        if tracking and order.get('trackingNumber') != tracking:
            order['trackingNumber'] = tracking
            print(f'  {name}: tracking → {tracking}')
            updated = True

        if ship_ms and not order.get('shippingDate'):
            order['shippingDate'] = ship_ms
            print(f'  {name}: shippingDate → {fier["ship_date"]}')
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
