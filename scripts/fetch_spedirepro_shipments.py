"""
Fetch SpedirePro Shipments — Il Ciliegio CRM
Login via requests puro (sessione cookie Laravel + CSRF, area privata
spedirepro.com — nessun browser headless necessario), recupera l'elenco
spedizioni e le collega agli ordini CRM tramite il codice "Riferimento
ordine di vendita" (COGNOME + INIZIALE NOME), impostato a mano dall'operatore
in fase di creazione spedizione su SpedirePro.

Popola trackingUrl/carrier/status/shippingDate sull'ordine — non gestisce
la lettera di vettura (non richiesta).
"""

import base64
import json
import os
import re
import time
import urllib.parse
from datetime import datetime, timezone

import requests

# ── Config da env (GitHub Secrets) ──────────────────────────────────────────
SPEDIREPRO_EMAIL    = os.environ['SPEDIREPRO_EMAIL']
SPEDIREPRO_PASSWORD = os.environ['SPEDIREPRO_PASSWORD']
GH_TOKEN            = os.environ['GH_TOKEN']
GH_REPO             = os.environ['GH_REPO']
DATA_PATH           = 'data/ordini.json'

LOGIN_PAGE_URL  = 'https://www.spedirepro.com/login'
LOGIN_API_URL   = 'https://www.spedirepro.com/api/auth/login'
# Due bucket separati lato SpedirePro: le spedizioni già ritirate dal corriere
# vivono su SHIPMENTS_URL, quelle appena create e ancora in attesa di ritiro
# su PICKUP_URL — un ordine appena spedito può restare lì per giorni prima di
# spostarsi, quindi vanno interrogati entrambi.
SHIPMENTS_URL   = 'https://www.spedirepro.com/api/user/shipments'
PICKUP_URL      = 'https://www.spedirepro.com/api/user/shipments/pickup'
SHIPMENTS_LIMIT = 100
MAX_PAGES       = 10

_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'

# Stessa mappatura/rank di scripts/fetch_spedire_tracking.py — stessa piattaforma Alsendo
STATUS_MAP = {
    'N': 'spedito', 'O': 'spedito',
    'B': 'in_transito', 'T': 'in_transito', 'S': 'in_transito',
    'G': 'in_transito', 'L': 'in_transito',
    'Y': 'in_consegna',
    'D': 'consegnato', 'P': 'consegnato',
    'E': 'problema', 'X': 'problema',
}

STATUS_RANK = {s: i for i, s in enumerate([
    'ricevuto', 'preparazione', 'spedito', 'in_transito', 'dogana',
    'in_consegna', 'consegna_fallita', 'consegnato', 'problema', 'annullato',
])}

TERMINAL_STATUSES = {'consegnato', 'annullato'}


# ── Auth + fetch via requests (sessione cookie Laravel + CSRF) ───────────────

def _xsrf_header(session: requests.Session) -> str:
    cookie = session.cookies.get('XSRF-TOKEN')
    if not cookie:
        raise RuntimeError('Cookie XSRF-TOKEN non trovato — la pagina SpedirePro potrebbe essere cambiata.')
    return urllib.parse.unquote(cookie)


def login() -> requests.Session:
    session = requests.Session()
    session.headers.update({'User-Agent': _UA})

    r = session.get(LOGIN_PAGE_URL, timeout=20)
    r.raise_for_status()

    m = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', r.text)
    if not m:
        raise RuntimeError(
            'Meta tag csrf-token non trovato nella pagina di login — '
            'SpedirePro potrebbe aver cambiato struttura.'
        )
    csrf_token = m.group(1)

    headers = {
        'accept':           'application/json, text/plain, */*',
        'content-type':     'application/json',
        'x-csrf-token':     csrf_token,
        'x-xsrf-token':     _xsrf_header(session),
        'x-requested-with': 'XMLHttpRequest',
        'referer':          LOGIN_PAGE_URL,
        'origin':           'https://www.spedirepro.com',
    }

    r = session.post(
        LOGIN_API_URL, json={'email': SPEDIREPRO_EMAIL, 'password': SPEDIREPRO_PASSWORD},
        headers=headers, timeout=20,
    )
    if r.status_code != 200:
        raise RuntimeError(
            f'Login SpedirePro fallito — HTTP {r.status_code}: {r.text[:300]}\n'
            'Verificare SPEDIREPRO_EMAIL/SPEDIREPRO_PASSWORD nei GitHub Secrets.'
        )

    print('  Login SpedirePro: OK')
    return session


def fetch_shipments() -> list[dict]:
    session = login()

    headers = {
        'accept':           'application/json, text/plain, */*',
        'content-type':     'application/json',
        'x-xsrf-token':     _xsrf_header(session),
        'x-requested-with': 'XMLHttpRequest',
        'referer':          'https://www.spedirepro.com/le-tue-spedizioni',
        'origin':           'https://www.spedirepro.com',
    }

    all_shipments: list[dict] = []

    for url, query, label in (
        (SHIPMENTS_URL, {'is_returning': False, 'archived': False}, 'monitorate'),
        (PICKUP_URL,    {},                                         'da ritirare'),
    ):
        for pg in range(1, MAX_PAGES + 1):
            payload = {'query': query, 'limit': SHIPMENTS_LIMIT, 'ascending': 0, 'page': pg, 'byColumn': 1}
            r = session.post(url, json=payload, headers=headers, timeout=20)
            if not r.ok:
                print(f'  [{label}] pagina {pg}: risposta HTTP {r.status_code}, mi fermo.')
                break
            data  = r.json()
            items = data.get('data') or data.get('shipments') or (data if isinstance(data, list) else [])
            all_shipments.extend(items)
            print(f'  [{label}] pagina {pg}: {len(items)} spedizioni')
            if len(items) < SHIPMENTS_LIMIT:
                break

    # Dedup per reference (codice univoco SpedirePro) — in teoria i due bucket
    # sono disgiunti, ma meglio non fidarsi ciecamente per evitare falsi
    # conflitti nel matching se una spedizione risultasse in entrambi.
    seen: set[str] = set()
    deduped: list[dict] = []
    for s in all_shipments:
        key = s.get('reference') or s.get('tracker') or id(s)
        if key not in seen:
            seen.add(key)
            deduped.append(s)

    print(f'Totale spedizioni SpedirePro: {len(deduped)}')
    return deduped


# ── GitHub (stesso pattern di fetch_spedire_tracking.py) ─────────────────────

_GH_HEADERS = {
    'Authorization': f'token {GH_TOKEN}',
    'Accept':        'application/vnd.github.v3+json',
}


def _gh_request(method, url, **kwargs):
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


# ── Matching ordine ↔ spedizione ──────────────────────────────────────────────

def customer_code(name: str) -> str:
    """COGNOME (tutto tranne la prima parola) + INIZIALE NOME, es. 'SUSAN RUSCIANO' → 'RUSCIANOS'."""
    words = re.sub(r'[^A-Za-z\s]', '', (name or '')).upper().split()
    if len(words) < 2:
        return ''
    nome      = words[0]
    cognome   = ''.join(words[1:])
    return cognome + nome[0]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print('=== Fetch SpedirePro Shipments — Il Ciliegio ===')

    shipments = fetch_shipments()

    # Raggruppa spedizioni per merchant_reference — il "Riferimento ordine di
    # vendita" impostato a mano dall'operatore (da NON confondere con
    # "reference", codice generato automaticamente da SpedirePro, es.
    # "AN2407263J7CO", che non ha alcuna relazione col codice cliente).
    # Se un merchant_reference compare più di una volta lato SpedirePro, è
    # ambiguo quanto un doppione lato CRM.
    by_reference: dict[str, list[dict]] = {}
    for s in shipments:
        ref = (s.get('merchant_reference') or (s.get('data') or {}).get('merchant_reference') or '').strip().upper()
        if ref:
            by_reference.setdefault(ref, []).append(s)

    db, sha_db = gh_get(DATA_PATH)
    orders     = db.get('orders') or []
    now_ms     = int(datetime.now(timezone.utc).timestamp() * 1000)

    # Ordini CRM ancora da collegare, raggruppati per codice calcolato — serve
    # per rilevare conflitti anche lato CRM (due ordini con lo stesso codice).
    # NB: un ordine con trackingUrl già impostato NON va escluso qui — va
    # ricontrollato a ogni run finché non raggiunge uno stato terminale, altrimenti
    # resta congelato al primo status visto (es. "spedito") e non arriva mai a
    # "consegnato" anche se la spedizione nel frattempo è stata recapitata.
    pending_by_code: dict[str, list[dict]] = {}
    for o in orders:
        if o.get('status') in TERMINAL_STATUSES:
            continue
        code = customer_code(o.get('customerName', ''))
        if code:
            pending_by_code.setdefault(code, []).append(o)

    unmatched_crm = sorted(c for c in pending_by_code if c not in by_reference)
    if unmatched_crm:
        print(f'  [diagnostica] {len(unmatched_crm)} ordini CRM in attesa senza spedizione SpedirePro corrispondente:')
        for code in unmatched_crm:
            names = ', '.join(o.get('customerName', '?') for o in pending_by_code[code])
            print(f'    CRM "{code}" ({names}) — nessuna spedizione con questo riferimento su SpedirePro')
        print(f'  [diagnostica] {len(by_reference)} riferimenti distinti trovati su SpedirePro: {sorted(by_reference.keys())}')

    changed = 0

    for code, crm_matches in pending_by_code.items():
        spedire_matches = by_reference.get(code)
        if not spedire_matches:
            continue

        if len(crm_matches) > 1 or len(spedire_matches) > 1:
            note = (
                f'⚠ Conflitto SpedirePro: codice "{code}" condiviso tra '
                f'{len(crm_matches)} ordine/i CRM e {len(spedire_matches)} spedizione/i — '
                'verificare manualmente.'
            )
            for o in crm_matches:
                if note not in (o.get('notes') or ''):
                    o['notes']     = (note + '\n' + (o.get('notes') or '')).strip()
                    o['updatedAt'] = now_ms
                    changed += 1
                    print(f'  ! {o.get("customerName")}: {note}')
            continue

        order    = crm_matches[0]
        shipment = spedire_matches[0]

        tracking_url = shipment.get('tracking_url', '')
        if not tracking_url:
            continue

        last_status = shipment.get('last_status', '')
        new_status  = STATUS_MAP.get(last_status, 'spedito')
        cur_status  = order.get('status', 'ricevuto')
        if STATUS_RANK.get(new_status, 0) < STATUS_RANK.get(cur_status, 0):
            new_status = cur_status

        is_new_link    = not order.get('trackingUrl')
        status_changed = new_status != cur_status

        # Niente di nuovo per questo ordine rispetto all'ultimo run: non tocco
        # nulla — altrimenti, ora che gli ordini già agganciati vengono
        # ricontrollati a ogni run (necessario per far avanzare lo stato fino a
        # "consegnato"), finiremmo per aggiungere una riga di statusHistory
        # identica ogni 4 ore all'infinito anche quando non è successo nulla.
        if not is_new_link and not status_changed:
            continue

        order['trackingUrl'] = tracking_url
        order['carrier']     = (shipment.get('data') or {}).get('courier', {}).get('courier_name') \
            or order.get('carrier') or 'Spedire.com'
        order['spedireproReference'] = code

        if not order.get('shippingDate'):
            order['shippingDate'] = now_ms

        if status_changed:
            order.setdefault('statusHistory', []).append({
                'status': new_status,
                'date':   now_ms,
                'note':   f'Auto SpedirePro: aggiornamento stato (rif. {code})',
            })
            order['status'] = new_status
        elif is_new_link:
            order.setdefault('statusHistory', []).append({
                'status': cur_status,
                'date':   now_ms,
                'note':   f'Auto SpedirePro: trovato tracking (rif. {code})',
            })

        order['updatedAt'] = now_ms
        changed += 1
        print(f'  ✓ {order.get("customerName")}: {"nuovo tracking" if is_new_link else "stato " + new_status} ({code}) → {tracking_url}')

    if changed > 0:
        db['orders'] = orders
        now_str = datetime.now().strftime('%d/%m/%Y %H:%M')
        gh_put(DATA_PATH, db, sha_db, f'SpedirePro shipments — {changed} ordini aggiornati — {now_str}')
        print(f'\n✓ {changed} ordini aggiornati, ordini.json salvato.')
    else:
        print('\nNessun aggiornamento da SpedirePro.')


if __name__ == '__main__':
    main()
