"""
Fetch MBE Public Tracking — Il Ciliegio CRM
Scraping della pagina pubblica mbe.it/IT/tracking (nessun login richiesto).
Aggiorna status ordini in ordini.json per tutti gli ordini con mbeTrackingNumber.

Mapping eventi MBE → status CRM:
  "Shipment delivered to final destination"            → consegnato
  "Shipment in transit to reach its final destination" → in_consegna

URL controllato: https://www.mbe.it/IT/tracking?c={mbeTrackingNumber}-01
Il suffisso -01 identifica il primo collo — rappresentativo di tutta la spedizione
anche quando ci sono più colli (-02, -03, …).

Nota: se la pagina è JS-rendered (risposta HTML senza eventi), lo step viene
saltato silenziosamente — in quel caso attivare Playwright (già in requirements).
"""

import base64
import json
import os
import re
from datetime import datetime, timezone
from html import unescape

import requests

# ── Config ────────────────────────────────────────────────────────────────────
GH_TOKEN  = os.environ['GH_TOKEN']
GH_REPO   = os.environ['GH_REPO']
DATA_PATH = 'data/ordini.json'

MBE_TRACKING_URL = 'https://www.mbe.it/IT/tracking?c={code}-01'

# Keyword matching su descrizione evento (case-insensitive, partial match)
# Ordine: più specifico prima — si ferma al primo match per riga
EVENT_STATUS_MAP = [
    ('delivered to final destination',            'consegnato'),
    ('in transit to reach its final destination', 'in_consegna'),
]

STATUS_RANK = {s: i for i, s in enumerate([
    'ricevuto', 'preparazione', 'spedito', 'in_transito',
    'dogana', 'in_consegna', 'consegnato', 'problema', 'annullato',
])}

TERMINAL_STATUSES = {'consegnato', 'annullato'}

_GH_HEADERS = {
    'Authorization': f'token {GH_TOKEN}',
    'Accept':        'application/vnd.github.v3+json',
}

_HTTP_HEADERS = {
    'User-Agent':      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept':          'text/html,application/xhtml+xml',
    'Accept-Language': 'it-IT,it;q=0.9,en;q=0.8',
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


# ── MBE page scraping ──────────────────────────────────────────────────────────

def fetch_mbe_events(mbe_code: str) -> list[tuple[str, str]]:
    """Legge la pagina pubblica MBE e ritorna lista di (data, descrizione)."""
    url = MBE_TRACKING_URL.format(code=mbe_code)
    try:
        r = requests.get(url, headers=_HTTP_HEADERS, timeout=20)
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f'    ⚠ HTTP error per {mbe_code}: {e}')
        return []

    html_text = r.text

    # Estrai tutte le righe <tr> e cerca celle <td> con data + descrizione
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html_text, re.DOTALL | re.IGNORECASE)
    events = []
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
        if len(cells) >= 2:
            date_txt = unescape(re.sub(r'<[^>]+>', '', cells[0])).strip()
            desc_txt = unescape(re.sub(r'<[^>]+>', '', cells[1])).strip()
            if date_txt and desc_txt:
                events.append((date_txt, desc_txt))

    return events


def best_status_from_events(events: list[tuple[str, str]]) -> str | None:
    """Ritorna lo status CRM più avanzato (rank più alto) trovato tra tutti gli eventi."""
    best_rank   = -1
    best_status = None
    for _date, desc in events:
        desc_lower = desc.lower()
        for keyword, status in EVENT_STATUS_MAP:
            if keyword in desc_lower:
                rank = STATUS_RANK.get(status, -1)
                if rank > best_rank:
                    best_rank   = rank
                    best_status = status
                break
    return best_status


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print('=== Fetch MBE Public Tracking — Il Ciliegio ===')

    db, sha = gh_get(DATA_PATH)
    orders  = db.get('orders') or []
    now_ms  = int(datetime.now(timezone.utc).timestamp() * 1000)
    changed = 0

    candidates = [
        o for o in orders
        if o.get('mbeTrackingNumber') and o.get('status') not in TERMINAL_STATUSES
    ]
    print(f'Ordini da controllare: {len(candidates)}')

    if not candidates:
        print('Nessun ordine attivo con mbeTrackingNumber — skip.')
        return

    for order in candidates:
        mbe_code   = order['mbeTrackingNumber']
        cur_status = order.get('status', 'ricevuto')
        name       = order.get('customerName', '?')

        events = fetch_mbe_events(mbe_code)

        if not events:
            print(f'  {name} ({mbe_code}): nessun evento ricevuto '
                  f'(pagina vuota o JS-rendered — valutare Playwright)')
            continue

        print(f'  {name} ({mbe_code}): {len(events)} eventi')
        for date, desc in events:
            print(f'    {date}: {desc}')

        new_status = best_status_from_events(events)
        if not new_status:
            print(f'    → nessun evento mappabile (status corrente: {cur_status})')
            continue

        cur_rank = STATUS_RANK.get(cur_status, 0)
        new_rank = STATUS_RANK.get(new_status, 0)

        # consegnato può sovrascrivere problema: se il pacco è arrivato
        # nonostante un problema precedente, non deve restare bloccato
        force = (new_status == 'consegnato' and cur_status == 'problema')

        if new_rank > cur_rank or force:
            order.setdefault('statusHistory', []).append({
                'status': new_status,
                'date':   now_ms,
                'note':   f'Auto MBE tracking (era: {cur_status})',
            })
            order['status']    = new_status
            order['updatedAt'] = now_ms
            print(f'    → {cur_status} → {new_status} ✓')
            changed += 1
        else:
            print(f'    → {new_status} (rank {new_rank} ≤ {cur_rank}, no update)')

    if changed > 0:
        db['orders'] = orders
        now_str = datetime.now().strftime('%d/%m/%Y %H:%M')
        gh_put(DATA_PATH, db, sha,
               f'MBE public tracking — {changed} ordini aggiornati — {now_str}')
        print(f'\n✓ {changed} ordini aggiornati, ordini.json salvato.')
    else:
        print('\nNessun aggiornamento da MBE.')


if __name__ == '__main__':
    main()
