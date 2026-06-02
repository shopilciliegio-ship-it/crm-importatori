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
MBE_EMAIL    = os.environ['MBE_EMAIL']
MBE_PASSWORD = os.environ['MBE_PASSWORD']
GH_TOKEN     = os.environ['GH_TOKEN']
GH_REPO      = os.environ['GH_REPO']
DATA_PATH    = 'data/ordini.json'

MBE_API_BASE  = 'https://api.mbeonline.it'
CUSTOMER_ID   = 2173924

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


# ── Auth via Playwright (browser headless) ───────────────────────────────────

_SCREENSHOT_DIR = '/tmp'
_OTP_SELECTOR   = '#otp, input[name="otp"], input[autocomplete="one-time-code"]'


def _find_token_in_storage(page) -> dict | None:
    for store in ('localStorage', 'sessionStorage'):
        entries = page.evaluate(f"Object.entries({store})")
        for key, raw in entries:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict) and parsed.get('access_token'):
                    print(f'  Token trovato in {store}["{key}"]')
                    return parsed
            except Exception:
                pass
    return None


def _debug_page(page, label: str) -> None:
    page.screenshot(path=f'{_SCREENSHOT_DIR}/mbe_{label}.png')
    print(f'  [{label}] URL: {page.url}')
    # Stampa tutti gli <input> visibili per identificare i selettori
    inputs = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('input')).map(el => ({
            id: el.id, name: el.name, type: el.type,
            autocomplete: el.autocomplete, placeholder: el.placeholder
        }));
    }""")
    print(f'  [{label}] inputs: {inputs}')


def get_token() -> str:
    import pyotp
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    MBE_TOTP_SECRET = os.environ.get('MBE_TOTP_SECRET', '')

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page    = browser.new_page()

        print('  Apertura MBEonline...')
        page.goto('https://www.mbeonline.it', timeout=30_000)

        page.wait_for_selector('#username', timeout=15_000)
        page.fill('#username', MBE_EMAIL)
        page.fill('#password', MBE_PASSWORD)
        page.click('[type=submit]')

        try:
            page.wait_for_load_state('networkidle', timeout=15_000)
        except Exception:
            pass

        _debug_page(page, '01_after_credentials')

        # Schermata scelta metodo 2FA — rilevata tramite count() (funziona con hidden input)
        if page.locator('[name="secondFactorChoiceGoogle"]').count() > 0:
            print('  Schermata scelta 2FA rilevata — scelgo Google Authenticator...')

            # Debug: mostra button e link presenti sulla pagina
            elements = page.evaluate("""() => Array.from(
                document.querySelectorAll('button, input[type=submit], a')
            ).map(el => ({
                tag: el.tagName, name: el.getAttribute('name') || '',
                type: el.getAttribute('type') || '',
                text: el.textContent.trim().substring(0, 50)
            }))""")
            print(f'  clickable elements: {elements}')

            # Clicca via JS — gestisce sia <button name=...> che <input type=hidden name=...>
            clicked = page.evaluate("""() => {
                const sel = '[name="secondFactorChoiceGoogle"]';
                const el = document.querySelector('button' + sel)
                        || document.querySelector(sel);
                if (el) { el.click(); return el.tagName + '[' + el.type + ']'; }
                return null;
            }""")
            print(f'  Elemento cliccato: {clicked}')

            try:
                page.wait_for_load_state('networkidle', timeout=10_000)
            except Exception:
                pass
            _debug_page(page, '02_after_google_choice')
        else:
            print('  Nessuna schermata di scelta 2FA.')

        # Schermata OTP: 6 input[type=text] separati (una cifra ciascuno) + submit #kc-login
        # Il campo #otp è hidden (aggregatore JS) — non usarlo direttamente
        digit_inputs = page.locator('input[type="text"]').all()
        if digit_inputs:
            print(f'  Schermata OTP — {len(digit_inputs)} digit fields, inserimento TOTP...')
            if not MBE_TOTP_SECRET:
                raise RuntimeError(
                    'MBE richiede 2FA TOTP ma MBE_TOTP_SECRET non è impostato nei GitHub Secrets.'
                )
            code = pyotp.TOTP(MBE_TOTP_SECRET).now()
            for i, inp in enumerate(digit_inputs[:6]):
                inp.fill(code[i])
            page.click('#kc-login')
            print('  OTP inviato, attendo login...')
            try:
                page.wait_for_load_state('networkidle', timeout=30_000)
            except Exception:
                pass
            _debug_page(page, '03_after_otp')
        else:
            print('  Nessuna schermata OTP.')

        token_data = _find_token_in_storage(page)
        if not token_data:
            page.wait_for_timeout(5_000)
            token_data = _find_token_in_storage(page)

        browser.close()

    access_token = (token_data or {}).get('access_token', '')
    if not access_token:
        raise RuntimeError(
            'Login MBE fallito — nessun access_token trovato.\n'
            'Verifica MBE_EMAIL, MBE_PASSWORD e MBE_TOTP_SECRET nei GitHub Secrets.'
        )
    print('  Login MBE via browser: OK')
    return access_token


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


def fmt_address(addr: dict) -> str:
    parts = [
        addr.get('address') or addr.get('street') or addr.get('streetAddress', ''),
        addr.get('city', ''),
        addr.get('zip') or addr.get('postalCode', ''),
        addr.get('stateOrProvince') or addr.get('state', ''),
        addr.get('country', ''),
    ]
    return ', '.join(p for p in parts if p)


def enrich_from_mbe(order: dict, mbe: dict) -> bool:
    """Arricchisce campi vuoti dell'ordine con dati da addressTo MBE. Ritorna True se cambiato."""
    addr    = mbe.get('addressTo', {})
    changed = False

    if not order.get('customerEmail') and addr.get('email'):
        order['customerEmail'] = addr['email']
        print(f'    + email: {addr["email"]}')
        changed = True

    if not order.get('customerPhone') and addr.get('phone'):
        order['customerPhone'] = addr['phone']
        print(f'    + telefono: {addr["phone"]}')
        changed = True

    if not order.get('shippingAddress'):
        addr_str = fmt_address(addr)
        if addr_str:
            order['shippingAddress'] = addr_str
            print(f'    + indirizzo: {addr_str}')
            changed = True

    return changed


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

    # Debug: mostra campi addressTo del primo risultato (utile per verificare email/telefono)
    if shipments:
        print(f'  [debug] addressTo keys: {list(shipments[0].get("addressTo", {}).keys())}')

    for order in orders:
        mbe = lookup.get(norm(order.get('customerName', '')))
        if not mbe:
            continue

        changed = False

        # Arricchimento dati anagrafici (email, telefono, indirizzo) — sempre, anche per terminal
        if enrich_from_mbe(order, mbe):
            changed = True

        # Aggiornamento tracking e status (solo ordini non terminal)
        if order.get('status') not in TERMINAL_STATUSES:
            packages     = mbe.get('shipmentPackages', [])
            tracking_num = mbe.get('shipmentTrackingNumber', '')
            mbe_tracking = mbe.get('mbeTracking', '')
            courier      = mbe.get('courierName', 'UPS')
            ship_date    = mbe.get('shipmentDate')
            new_status   = crm_status_from_mbe(mbe)
            status_label = (packages[0].get('trackingLastStatusMbeName', '') if packages else '')

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
                print(f'  ✓ {order["customerName"]} → {tracking_num} [{new_status}]')
            else:
                print(f'  = {order["customerName"]} (nessuna variazione)')

        if changed:
            order['updatedAt'] = now_ms
            updated += 1

    # ── Import inverso: spedizioni MBE senza ordine corrispondente ────────────
    matched_names = {norm(o.get('customerName', '')) for o in orders}
    created = 0

    for s in shipments:
        name = norm(s.get('addressTo', {}).get('companyName', ''))
        if not name or name in matched_names:
            continue

        addr         = s.get('addressTo', {})
        new_status   = crm_status_from_mbe(s)
        packages     = s.get('shipmentPackages', [])
        status_label = (packages[0].get('trackingLastStatusMbeName', '') if packages else '')
        mbe_id       = (s.get('mbeTracking') or '').replace('/', '-').replace(' ', '_')
        order_id     = f'ord_mbe_{mbe_id}' if mbe_id else f'ord_mbe_{now_ms}_{created}'

        stub = {
            'id':                order_id,
            'customerName':      addr.get('companyName', ''),
            'customerEmail':     addr.get('email', ''),
            'customerPhone':     addr.get('phone', ''),
            'shippingAddress':   fmt_address(addr),
            'amount':            0.0,
            'currency':          'EUR',
            'orderDate':         now_ms,
            'emailSubject':      '',
            'shopifyOrderId':    '',
            'gmailMessageId':    '',
            'trackingNumber':    s.get('shipmentTrackingNumber', ''),
            'mbeTrackingNumber': s.get('mbeTracking', ''),
            'carrier':           s.get('courierName', 'MBE'),
            'shippingDate':      s.get('shipmentDate'),
            'status':            new_status,
            'statusHistory': [{
                'status': new_status,
                'date':   now_ms,
                'note':   f'Importato da MBE — {status_label}' if status_label else 'Importato da MBE',
            }],
            'emailsSent': [],
            'notes':      '',
            'source':     'mbe',
            'createdAt':  now_ms,
            'updatedAt':  now_ms,
        }
        orders.append(stub)
        matched_names.add(name)   # evita duplicati se companyName appare due volte
        created += 1
        print(f'  + Nuovo da MBE: {addr.get("companyName")} [{new_status}] {s.get("shipmentTrackingNumber","")}')

    if updated > 0 or created > 0:
        db['orders'] = orders
        save_ordini(db, sha)
        print(f'\n✓ {updated} aggiornati, {created} nuovi ordini da MBE.')
    else:
        print('\nNessuna variazione da salvare.')


if __name__ == '__main__':
    main()
