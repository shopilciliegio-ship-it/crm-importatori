"""
Fetch MBE Tracking — Il Ciliegio CRM
Recupera spedizioni da MBEonline API, aggiorna trackingNumber e status in ordini.json.
"""

import base64
import json
import os
import re
from datetime import datetime, timezone

import requests

# ── Config da env (GitHub Secrets) ──────────────────────────────────────────
MBE_USERNAME = os.environ['MBE_USERNAME']   # ciliegio.it3299.mol
MBE_PASSWORD = os.environ['MBE_PASSWORD']
GH_TOKEN     = os.environ['GH_TOKEN']
GH_REPO      = os.environ['GH_REPO']
DATA_PATH    = 'data/ordini.json'

KEYCLOAK_TOKEN_URL = 'https://oauth.mbe-hub.com/realms/mbe-hub/protocol/openid-connect/token'
MBE_API_BASE       = 'https://api.mbeonline.it'
CUSTOMER_ID        = 2173924

# Endpoint per Wine USA + Wine Europa
MBE_ENDPOINTS = [
    'shipments-wine2-mol',
    'shipments-management-mol',
]

# trackingLastStatusMbeId → status CRM
STATUS_MAP = {
    36: 'in_transito',
    24: 'problema',
}
TERMINAL_STATUSES = {'consegnato', 'annullato'}


# ── Auth Keycloak (ROPC) ─────────────────────────────────────────────────────

def get_token() -> str:
    r = requests.post(
        KEYCLOAK_TOKEN_URL,
        data={
            'grant_type': 'password',
            'client_id':  'mbe-mol-fe',
            'username':   MBE_USERNAME,
            'password':   MBE_PASSWORD,
            'scope':      'openid',
        },
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(
            f'Auth MBE fallita ({r.status_code}): {r.text[:200]}\n'
            'Se il messaggio è "grant_type not allowed", il client MBE non supporta ROPC — '
            'contatta supporto o usa il refresh_token manuale.'
        )
    return r.json()['access_token']


# ── Fetch spedizioni ──────────────────────────────────────────────────────────

def fetch_all_shipments(token: str) -> list[dict]:
    headers = {
        'Authorization':     f'Bearer {token}',
        'Content-Type':      'application/json;charset=UTF-8',
        'baseurl':           'www.mbeonline.it',
        'source':            'Online',
        'x-teleport-tenant': '1',
    }
    body = {
        'and': [
            {'field': 'customerId', 'type': 'INTEGER', 'operation': '=', 'values': [CUSTOMER_ID]}
        ]
    }

    all_shipments = []
    for endpoint in MBE_ENDPOINTS:
        page = 0
        while True:
            url = (
                f'{MBE_API_BASE}/shipments/search/{endpoint}'
                f'?page={page}&pageSize=100&sortBy=creationDate+desc'
            )
            r = requests.post(url, headers=headers, json=body, timeout=30)
            r.raise_for_status()
            data    = r.json()
            content = data.get('content', [])
            all_shipments.extend(content)
            print(f'  [{endpoint}] pagina {page}: {len(content)} spedizioni')
            if data.get('last', True):
                break
            page += 1

    print(f'Totale spedizioni MBE: {len(all_shipments)}')
    return all_shipments


# ── GitHub ────────────────────────────────────────────────────────────────────

_GH_HEADERS = {
    'Authorization': f'token {GH_TOKEN}',
    'Accept':        'application/vnd.github.v3+json',
}


def load_ordini() -> tuple[dict, str | None]:
    url = f'https://api.github.com/repos/{GH_REPO}/contents/{DATA_PATH}'
    r   = requests.get(url, headers=_GH_HEADERS)
    if r.status_code == 404:
        return {'orders': [], 'lastImportedAt': None}, None
    r.raise_for_status()
    data    = r.json()
    content = base64.b64decode(data['content']).decode('utf-8')
    return json.loads(content), data['sha']


def save_ordini(db: dict, sha: str | None) -> None:
    url     = f'https://api.github.com/repos/{GH_REPO}/contents/{DATA_PATH}'
    content = base64.b64encode(
        json.dumps(db, ensure_ascii=False, indent=2).encode('utf-8')
    ).decode('utf-8')
    now_str = datetime.now().strftime('%d/%m/%Y %H:%M')
    body    = {'message': f'MBE tracking sync — {now_str}', 'content': content}
    if sha:
        body['sha'] = sha
    requests.put(url, headers=_GH_HEADERS, json=body).raise_for_status()


# ── Helpers ───────────────────────────────────────────────────────────────────

def norm(name: str) -> str:
    return re.sub(r'\s+', ' ', (name or '').upper().strip())


def crm_status_from_mbe(mbe_shipment: dict) -> str:
    if mbe_shipment.get('delivered'):
        return 'consegnato'
    packages   = mbe_shipment.get('shipmentPackages', [])
    status_id  = packages[0].get('trackingLastStatusMbeId') if packages else None
    return STATUS_MAP.get(status_id, 'spedito')


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print('=== Fetch MBE Tracking ===')

    token     = get_token()
    print('Token Keycloak OK')

    shipments = fetch_all_shipments(token)

    # Lookup per nome normalizzato (più recente prima, già sorted desc)
    lookup: dict[str, dict] = {}
    for s in shipments:
        name = norm(s.get('addressTo', {}).get('companyName', ''))
        if name and name not in lookup:
            lookup[name] = s

    db, sha = load_ordini()
    orders  = db.get('orders', [])
    print(f'Ordini nel DB: {len(orders)}')

    now_ms  = int(datetime.now(timezone.utc).timestamp() * 1000)
    updated = 0

    for order in orders:
        if order.get('status') in TERMINAL_STATUSES:
            continue

        mbe = lookup.get(norm(order.get('customerName', '')))
        if not mbe:
            continue

        packages       = mbe.get('shipmentPackages', [])
        tracking_num   = mbe.get('shipmentTrackingNumber', '')
        mbe_tracking   = mbe.get('mbeTracking', '')
        courier        = mbe.get('courierName', 'UPS')
        ship_date      = mbe.get('shipmentDate')          # "YYYY-MM-DD"
        new_status     = crm_status_from_mbe(mbe)
        status_label   = (packages[0].get('trackingLastStatusMbeName', '') if packages else '')

        changed = False

        if tracking_num and order.get('trackingNumber') != tracking_num:
            order['trackingNumber']    = tracking_num
            order['mbeTrackingNumber'] = mbe_tracking
            order['carrier']           = courier
            changed = True

        if ship_date and not order.get('shippingDate'):
            order['shippingDate'] = ship_date
            changed = True

        if new_status != order.get('status'):
            order['status'] = new_status
            order.setdefault('statusHistory', []).append({
                'status': new_status,
                'date':   now_ms,
                'note':   f'MBE: {status_label}' if status_label else 'Aggiornato da MBE',
            })
            changed = True

        if changed:
            order['updatedAt'] = now_ms
            updated += 1
            print(f'  ✓ {order["customerName"]} → {tracking_num} [{new_status}]')
        else:
            print(f'  = {order["customerName"]} (nessuna variazione)')

    if updated > 0:
        db['orders'] = orders
        save_ordini(db, sha)
        print(f'\n✓ {updated} ordini aggiornati e salvati.')
    else:
        print('\nNessuna variazione da salvare.')


if __name__ == '__main__':
    main()
