"""
Fetch 17Track Tracking — Il Ciliegio CRM
API 17Track v2.4 (https://api.17track.net/track/v2.4) per il tracking UPS.
Sostituisce il tentativo mbe.it (dormiente, mai funzionato — bloccato da Akamai WAF).

Due fasi ad ogni run:
  1. Registrazione (una tantum): ordini con trackingNumber UPS (prefisso "1Z") mai
     registrati vengono inviati a /register. Segna order['track17Registered'].
  2. Poll stato: per tutti gli ordini già registrati, /gettrackinfo restituisce lo
     stato più recente, mappato sullo stesso vocabolario CRM usato dagli altri
     fetch_*_tracking.py (STATUS_RANK, nessun downgrade).

Mapping status 17Track → CRM:
  NotFound            → (nessun aggiornamento, non ancora tracciato)
  InfoReceived         → spedito
  InTransit            → in_transito
  Expired              → problema
  AvailableForPickup   → in_consegna
  OutForDelivery       → in_consegna
  DeliveryFailure      → problema
  Delivered            → consegnato
  Exception            → problema
"""

import base64
import json
import os
import time
from datetime import datetime, timezone

import requests

# ── Config ────────────────────────────────────────────────────────────────────
TRACK17_API_KEY = os.environ['TRACK17_API_KEY']
GH_TOKEN        = os.environ['GH_TOKEN']
GH_REPO         = os.environ['GH_REPO']
DATA_PATH       = 'data/ordini.json'

API_BASE     = 'https://api.17track.net/track/v2.4'
BATCH_SIZE   = 40  # limite API per richiesta, sia per /register che /gettrackinfo

STATUS_MAP = {
    'InfoReceived':       'spedito',
    'InTransit':          'in_transito',
    'Expired':             'problema',
    'AvailableForPickup': 'in_consegna',
    'OutForDelivery':     'in_consegna',
    'DeliveryFailure':    'consegna_fallita',
    'Delivered':          'consegnato',
    'Exception':          'problema',
}

# consegna_fallita sta sotto consegnato: un tentativo fallito può ancora
# risolversi con una consegna riuscita al giro successivo, senza serve alcun
# hack "force" (a differenza di problema, che sta sopra consegnato apposta).
STATUS_RANK = {s: i for i, s in enumerate([
    'ricevuto', 'preparazione', 'spedito', 'in_transito', 'dogana',
    'in_consegna', 'consegna_fallita', 'consegnato', 'problema', 'annullato',
])}

TERMINAL_STATUSES = {'consegnato', 'annullato'}

_GH_HEADERS = {
    'Authorization': f'token {GH_TOKEN}',
    'Accept':        'application/vnd.github.v3+json',
}
_TRACK17_HEADERS = {
    '17token':      TRACK17_API_KEY,
    'Content-Type': 'application/json',
}


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


# ── 17Track API ───────────────────────────────────────────────────────────────

def _chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def register_numbers(numbers: list[str]) -> set[str]:
    """Registra i numeri non ancora tracciati. Ritorna il set di numeri accettati."""
    accepted = set()
    for batch in _chunks(numbers, BATCH_SIZE):
        body = [{'number': n} for n in batch]
        r = requests.post(f'{API_BASE}/register', headers=_TRACK17_HEADERS, json=body, timeout=30)
        r.raise_for_status()
        data = r.json().get('data') or {}
        for item in data.get('accepted') or []:
            accepted.add(item['number'])
        for item in data.get('rejected') or []:
            err = (item.get('error') or {}).get('message', '?')
            print(f'    ✗ registrazione rifiutata {item.get("number")}: {err}')
    return accepted


def fetch_track_info(numbers: list[str]) -> dict[str, dict]:
    """Ritorna {number: track_info} per i numeri con risposta valida."""
    result = {}
    for batch in _chunks(numbers, BATCH_SIZE):
        body = [{'number': n} for n in batch]
        r = requests.post(f'{API_BASE}/gettrackinfo', headers=_TRACK17_HEADERS, json=body, timeout=30)
        r.raise_for_status()
        data = r.json().get('data') or {}
        for item in data.get('accepted') or []:
            result[item['number']] = item.get('track_info') or {}
        for item in data.get('rejected') or []:
            err = (item.get('error') or {}).get('message', '?')
            print(f'    ✗ gettrackinfo rifiutato {item.get("number")}: {err}')
    return result


def latest_event_note(track_info: dict) -> str:
    """Best-effort: descrizione dell'ultimo evento, per il campo 'note' dello storico."""
    for provider in track_info.get('providers') or []:
        events = provider.get('events') or []
        if events:
            desc = events[0].get('description') or ''
            loc  = events[0].get('location') or ''
            return f'{loc} — {desc}'.strip(' —') if loc else desc
    return ''


def latest_event_time(track_info: dict) -> str:
    """Timestamp dell'ultimo evento — usato per distinguere un NUOVO tentativo
    di consegna fallito da uno già notificato in un run precedente."""
    for provider in track_info.get('providers') or []:
        events = provider.get('events') or []
        if events:
            return events[0].get('time_iso') or events[0].get('time_utc') or ''
    return ''


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print('=== Fetch 17Track Tracking (UPS) — Il Ciliegio ===')

    db, sha = gh_get(DATA_PATH)
    orders  = db.get('orders') or []
    now_ms  = int(datetime.now(timezone.utc).timestamp() * 1000)
    changed = 0

    candidates = [
        o for o in orders
        if (o.get('trackingNumber') or '').strip().upper().startswith('1Z')
        and o.get('status') not in TERMINAL_STATUSES
    ]
    print(f'Ordini UPS attivi: {len(candidates)}')

    if not candidates:
        print('Nessun ordine attivo con tracking UPS — skip.')
        return

    # ── Fase 1: registrazione una tantum ──────────────────────────────────────
    to_register = [o for o in candidates if not o.get('track17Registered')]
    freshly_registered = set()
    if to_register:
        numbers  = [o['trackingNumber'].strip().upper() for o in to_register]
        accepted = register_numbers(numbers)
        for order in to_register:
            num = order['trackingNumber'].strip().upper()
            if num in accepted:
                order['track17Registered'] = True
                order['updatedAt'] = now_ms
                changed += 1
                freshly_registered.add(num)
                print(f'  + registrato: {order.get("customerName","?")} ({num})')

    # ── Fase 2: poll stato per i registrati nei run precedenti ────────────────
    # (chi è stato appena registrato in questa Fase 1 non ha ancora dati:
    # 17Track impiega qualche minuto/ora per interrogare il corriere — verrà
    # interrogato al prossimo run)
    registered = [
        o for o in candidates
        if o.get('track17Registered') and o['trackingNumber'].strip().upper() not in freshly_registered
    ]
    if not registered:
        print('Nessun ordine ancora registrato su 17Track — solo registrazione questo run.')
    else:
        numbers    = [o['trackingNumber'].strip().upper() for o in registered]
        track_info = fetch_track_info(numbers)

        for order in registered:
            num  = order['trackingNumber'].strip().upper()
            info = track_info.get(num)
            name = order.get('customerName', '?')
            if not info:
                print(f'  {name} ({num}): nessuna risposta da gettrackinfo')
                continue

            latest_status = info.get('latest_status') or {}
            raw_status    = latest_status.get('status', '')
            sub_status    = latest_status.get('sub_status', '')
            print(f'    [debug] {name} ({num}): raw_status={raw_status!r} sub_status={sub_status!r} '
                  f'ultimo evento: {latest_event_note(info) or "(nessuno)"} @ {latest_event_time(info) or "?"}')
            print(f'    [debug-raw] {json.dumps(info, ensure_ascii=False)[:3000]}')

            new_status = STATUS_MAP.get(raw_status)
            if not new_status:
                print(f'  {name} ({num}): status "{raw_status}" — nessun aggiornamento')
                continue

            cur_status = order.get('status', 'ricevuto')
            cur_rank   = STATUS_RANK.get(cur_status, 0)
            new_rank   = STATUS_RANK.get(new_status, 0)

            # consegnato può sovrascrivere problema: il pacco arriva comunque
            force = (new_status == 'consegnato' and cur_status == 'problema')

            # Un nuovo tentativo di consegna fallito va sempre segnalato, anche
            # se lo stato è già consegna_fallita da un tentativo precedente
            # (stesso rank → il confronto rank non basterebbe da solo).
            event_time      = latest_event_time(info)
            is_new_failure  = (
                raw_status == 'DeliveryFailure'
                and event_time
                and event_time != order.get('lastDeliveryFailureEventAt')
            )
            if is_new_failure:
                order['deliveryFailureCount']       = order.get('deliveryFailureCount', 0) + 1
                order['lastDeliveryFailureEventAt'] = event_time

            if new_rank > cur_rank or force or is_new_failure:
                note = latest_event_note(info) or f'Auto 17Track ({raw_status})'
                order.setdefault('statusHistory', []).append({
                    'status': new_status,
                    'date':   now_ms,
                    'note':   f'Auto 17Track (era: {cur_status}): {note}',
                })
                order['status']    = new_status
                order['updatedAt'] = now_ms
                print(f'  {name} ({num}): {cur_status} → {new_status} ✓')
                changed += 1
            else:
                print(f'  {name} ({num}): {new_status} (rank {new_rank} ≤ {cur_rank}, no update)')

    if changed > 0:
        db['orders'] = orders
        now_str = datetime.now().strftime('%d/%m/%Y %H:%M')
        gh_put(DATA_PATH, db, sha,
               f'17Track tracking — {changed} ordini aggiornati — {now_str}')
        print(f'\n✓ {changed} ordini aggiornati, ordini.json salvato.')
    else:
        print('\nNessun aggiornamento da 17Track.')


if __name__ == '__main__':
    main()
