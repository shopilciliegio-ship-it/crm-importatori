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
  AvailableForPickup   → consegna_fallita (il corriere non ce l'ha fatta a consegnare
                          a casa, il pacco resta fermo in un Access Point in attesa
                          del cliente — stessa urgenza di un tentativo fallito)
  OutForDelivery       → in_consegna
  DeliveryFailure      → consegna_fallita
  Delivered            → consegnato
  Exception            → problema

Un tentativo di consegna fallito NON alza affidabilmente lo status a
DeliveryFailure — verificato in produzione (2°/3° tentativo UPS restano
"OutForDelivery"). Il segnale vero è nel testo libero delle singole
description degli eventi (es. "Second Delivery Attempted, We missed you
again.", "We were unable to deliver your package") — vedi
FAILED_ATTEMPT_KEYWORDS e failed_attempt_events().

Il controllo scorre TUTTO lo storico eventi restituito da 17Track (non solo
latest_event), altrimenti un tentativo fallito "superato" da un evento più
recente nella stessa finestra di poll (4h) passerebbe inosservato — caso
reale: KLOTZ, "impossibile consegnare" (08/07) seguito il giorno dopo da
"in attesa ritiro Access Point" prima del run successivo.
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
    'AvailableForPickup': 'consegna_fallita',
    'OutForDelivery':     'in_consegna',
    'DeliveryFailure':    'consegna_fallita',
    'Delivered':          'consegnato',
    'Exception':          'problema',
}

# 17Track/UPS non alza mai lo status a DeliveryFailure per un tentativo
# intermedio — resta genericamente OutForDelivery anche al 2°/3° tentativo
# (verificato in produzione: JENNIFER STEVENS, 2° tentativo, status ancora
# "OutForDelivery"/"OutForDelivery_Other"). L'unico posto dove compare il
# dettaglio è il testo libero di latest_event.description, es. "Second
# Delivery Attempted, We missed you again." — va quindi cercato per keyword.
FAILED_ATTEMPT_KEYWORDS = (
    'missed you', 'delivery attempted', 'attempted delivery',
    'unable to deliver', 'delivery exception', 'no one available',
)

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
    """Descrizione dell'ultimo evento, per il campo 'note' dello storico."""
    ev   = track_info.get('latest_event') or {}
    desc = ev.get('description') or ''
    loc  = ev.get('location') or ''
    return f'{loc} — {desc}'.strip(' —') if loc else desc


def failed_attempt_events(track_info: dict) -> list[dict]:
    """Tutti gli eventi (non solo l'ultimo) la cui descrizione indica un
    tentativo di consegna fallito. Serve lo storico completo — un tentativo
    fallito viene spesso "superato" da un evento più recente (es. passaggio
    a un Access Point) prima del prossimo poll, e leggere solo latest_event
    lo farebbe sparire senza mai essere notificato."""
    out = []
    for provider in (track_info.get('tracking') or {}).get('providers') or []:
        for ev in provider.get('events') or []:
            desc = (ev.get('description') or '').lower()
            if any(kw in desc for kw in FAILED_ATTEMPT_KEYWORDS):
                out.append(ev)
    return out


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
            event_desc    = latest_event_note(info)
            print(f'    {name} ({num}): raw_status={raw_status!r} sub_status={sub_status!r} '
                  f'ultimo evento: {event_desc or "(nessuno)"}')

            mapped_status = STATUS_MAP.get(raw_status)

            # Un tentativo di consegna fallito NON alza affidabilmente lo status
            # a DeliveryFailure (resta OutForDelivery anche al 2°/3° tentativo) —
            # va cercato nel testo di TUTTI gli eventi, non solo l'ultimo.
            # Ma va promosso a consegna_fallita SOLO se lo stato mappato dal
            # raw_status attuale non è già più avanzato/severo di lui: un evento
            # "unable to deliver" può comparire anche nel testo di un reso al
            # mittente ormai definitivo (Exception → problema, rank più alto) —
            # in quel caso "vai a ritirarlo" sarebbe un messaggio sbagliato.
            # Bug reale del 10/07/2026: ANDREW WAYRYNEN e FAITH JENKINS, entrambi
            # già Exception_Returned (pacco reso al mittente), sono stati
            # riportati indietro a consegna_fallita e hanno ricevuto l'email
            # "vai a ritirarlo" per errore.
            mapped_rank         = STATUS_RANK.get(mapped_status, -1) if mapped_status else -1
            can_flag_as_failed  = mapped_status is not None and mapped_rank <= STATUS_RANK['consegna_fallita']
            all_failed_events   = failed_attempt_events(info) if can_flag_as_failed else []
            has_failed_attempt  = bool(all_failed_events)

            new_status = 'consegna_fallita' if has_failed_attempt else mapped_status
            if not new_status:
                print(f'  {name} ({num}): status "{raw_status}" — nessun aggiornamento')
                continue

            cur_status = order.get('status', 'ricevuto')
            cur_rank   = STATUS_RANK.get(cur_status, 0)
            new_rank   = STATUS_RANK.get(new_status, 0)

            # consegnato può sovrascrivere problema: il pacco arriva comunque
            force = (new_status == 'consegnato' and cur_status == 'problema')

            # Nuovi tentativi falliti non ancora notificati (per timestamp evento,
            # confrontato con l'ultimo già visto) — ognuno genera una email in più
            # in send_reminders.py, anche se lo stato resta consegna_fallita
            # (stesso rank del tentativo precedente → il confronto rank da solo
            # non lo rileverebbe).
            last_seen  = order.get('lastDeliveryFailureEventAt') or ''
            new_events = sorted(
                (ev for ev in all_failed_events
                 if (ev.get('time_utc') or ev.get('time_iso') or '') > last_seen),
                key=lambda ev: ev.get('time_utc') or ev.get('time_iso') or ''
            )
            is_new_failure = bool(new_events)
            if is_new_failure:
                order['deliveryFailureCount']       = order.get('deliveryFailureCount', 0) + len(new_events)
                order['lastDeliveryFailureEventAt'] = new_events[-1].get('time_utc') or new_events[-1].get('time_iso')

            if new_rank > cur_rank or force or is_new_failure:
                if new_events:
                    note = new_events[-1].get('description') or f'Auto 17Track ({raw_status})'
                else:
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
