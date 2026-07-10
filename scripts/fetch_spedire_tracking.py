"""
Fetch Spedire.com/Alsendo Tracking — Il Ciliegio CRM
API pubblica non autenticata, usata dalla pagina di tracking pubblica
(es. https://www.spedire.com/tracking/3UW1D56044876).
Prova prima spedirepro.com (spedizioni "Pro"), poi spedire.com come fallback.

Mapping last_status Alsendo → CRM:
  N, O          → spedito       (spedizione creata / in lavorazione)
  B, T, S, G, L → in_transito
  Y             → in_consegna
  D, P          → consegnato
  E, X          → problema (eccezione), salvo exception_code 5 → in_transito
"""

import base64
import json
import os
import re
import time
from datetime import datetime, timezone

import requests

# ── Config ────────────────────────────────────────────────────────────────────
GH_TOKEN  = os.environ['GH_TOKEN']
GH_REPO   = os.environ['GH_REPO']
DATA_PATH = 'data/ordini.json'

TRACKING_URL_RE = re.compile(r'spedire(?:pro)?\.com/tracking/([A-Za-z0-9]+)', re.IGNORECASE)

API_ENDPOINTS = [
    'https://www.spedirepro.com/api/public/tracking',
    'https://www.spedire.com/api/public/tracking',
]

STATUS_MAP = {
    'N': 'spedito', 'O': 'spedito',
    'B': 'in_transito', 'T': 'in_transito', 'S': 'in_transito',
    'G': 'in_transito', 'L': 'in_transito',
    'Y': 'in_consegna',
    'D': 'consegnato', 'P': 'consegnato',
    'E': 'problema', 'X': 'problema',
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
_UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}


# ── GitHub helpers ────────────────────────────────────────────────────────────

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


# ── Spedire API ───────────────────────────────────────────────────────────────

def fetch_tracking(code: str) -> dict | None:
    for url in API_ENDPOINTS:
        try:
            r = requests.post(url, json={'code': code}, headers=_UA, timeout=20)
            data = r.json()
        except (requests.RequestException, ValueError):
            continue
        if data.get('success'):
            return data
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print('=== Fetch Spedire.com Tracking — Il Ciliegio ===')

    db, sha_db = gh_get(DATA_PATH)
    orders     = db.get('orders') or []
    now_ms     = int(datetime.now(timezone.utc).timestamp() * 1000)
    changed    = 0

    for order in orders:
        name       = order.get('customerName', '?')
        cur_status = order.get('status', 'ricevuto')

        if cur_status in TERMINAL_STATUSES:
            continue

        m = TRACKING_URL_RE.search(order.get('trackingUrl') or '')
        if not m:
            continue
        code = m.group(1)

        data = fetch_tracking(code)
        if not data:
            print(f'  {name}: nessuna risposta valida per codice {code}')
            continue

        shipment    = data.get('shipment') or {}
        last_status = shipment.get('last_status', '')
        events      = data.get('tracking') or []
        last_event  = events[0] if events else {}

        new_status = STATUS_MAP.get(last_status)
        if last_status in ('E', 'X') and shipment.get('exception_code') == 5:
            new_status = 'in_transito'

        if not new_status:
            print(f'  {name}: status sconosciuto "{last_status}" — skip')
            continue

        cur_rank = STATUS_RANK.get(cur_status, 0)
        new_rank = STATUS_RANK.get(new_status, 0)
        if new_rank <= cur_rank:
            continue

        note = last_event.get('status', '') or f'Auto Spedire ({last_status})'
        order.setdefault('statusHistory', []).append({
            'status': new_status,
            'date':   now_ms,
            'note':   f'Auto Spedire: {note}',
        })
        order['status']    = new_status
        order['updatedAt'] = now_ms
        changed += 1
        print(f'  {name}: {cur_status} → {new_status} ({note})')

    if changed > 0:
        db['orders'] = orders
        now_str = datetime.now().strftime('%d/%m/%Y %H:%M')
        gh_put(DATA_PATH, db, sha_db,
               f'Spedire tracking — {changed} ordini aggiornati — {now_str}')
        print(f'\n✓ {changed} ordini aggiornati, ordini.json salvato.')
    else:
        print('\nNessun aggiornamento da Spedire.')


if __name__ == '__main__':
    main()
