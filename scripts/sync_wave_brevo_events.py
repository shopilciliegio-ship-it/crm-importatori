# -*- coding: utf-8 -*-
"""
sync_wave_brevo_events.py
==========================
Le wave email (send_clienti_wave.py / send_clienti_wave2.py) registravano lo
storico di invio solo in `emailsSent`, un campo che il resto del CRM (Registro/
Workflow, badge apertura/click/bounce, pulsante "Sync Brevo") non legge mai —
quel codice guarda esclusivamente `brevoEvents`. Risultato: le wave inviate non
comparivano da nessuna parte nel tracking, anche se Brevo le tracciava
normalmente.

Questo script:
1. BACKFILL — per ogni voce in `emailsSent` (type wave1/wave2) senza una voce
   `brevoEvents` corrispondente (stesso messageId), la crea (nessuna chiamata
   API, è gratis).
2. SYNC — per ogni voce `brevoEvents` non ancora in stato terminale (non bounced/
   spam/unsubscribed/blocked) e inviata negli ultimi WAVE_SYNC_CUTOFF_DAYS giorni,
   interroga l'API eventi di Brevo per quel messageId e aggiorna
   delivered/opened/clicked/bounced/spam/unsubscribed/blocked — stessa logica di
   syncBrevoEvents() in js/brevo.js, cosi badge e Registro restano consistenti
   sia che la sincronizzazione avvenga da browser sia da qui.

Da eseguire via GitHub Actions (richiede BREVO_API_KEY + GH_TOKEN come secrets).
"""

import base64
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

DATA_PATH = 'data/clienti.json'

BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')
GH_TOKEN      = os.environ.get('GH_TOKEN', '')
GH_OWNER      = os.environ.get('GH_OWNER', 'shopilciliegio-ship-it')
GH_REPO       = os.environ.get('GH_REPO', 'crm-importatori')

WAVE_SYNC_CUTOFF_DAYS = 30  # non richiamare l'API per email più vecchie di così

WAVE_SUBJECT_LABEL = {'wave1': 'Wave 1', 'wave2': 'Wave 2'}

_BREVO_HEADERS = {'api-key': BREVO_API_KEY, 'Accept': 'application/json'}


# ── GITHUB API (gestisce anche clienti.json >1MB, content inline assente) ──────
_gh_sha_cache: dict[str, str] = {}


def _gh_headers():
    return {
        'Authorization': f'token {GH_TOKEN}',
        'Accept': 'application/vnd.github.v3+json',
    }


def gh_get(path: str):
    url = f'https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{path}'
    r = requests.get(url, headers=_gh_headers(), timeout=20)
    if r.status_code == 404:
        return {}, None
    r.raise_for_status()
    d = r.json()
    sha = d.get('sha')
    raw = d.get('content', '').replace('\n', '')
    if raw:
        json_str = base64.b64decode(raw).decode('utf-8')
    else:
        dl = d.get('download_url')
        if not dl:
            print(f'  ✗ gh_get {path}: content vuoto e nessun download_url')
            return {}, sha
        r2 = requests.get(dl, timeout=60)
        r2.raise_for_status()
        json_str = r2.text
    _gh_sha_cache[path] = sha
    return json.loads(json_str), sha


def gh_put(path: str, data, message: str):
    url = f'https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{path}'
    content = base64.b64encode(
        json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    ).decode()
    body = {'message': message, 'content': content}
    sha = _gh_sha_cache.get(path)
    if sha:
        body['sha'] = sha

    r = requests.put(url, headers=_gh_headers(), json=body, timeout=30)
    if r.status_code in (200, 201):
        _gh_sha_cache[path] = r.json()['content']['sha']
        return True
    if r.status_code in (409, 422):
        _, new_sha = gh_get(path)
        if new_sha:
            body['sha'] = new_sha
            r2 = requests.put(url, headers=_gh_headers(), json=body, timeout=30)
            return r2.status_code in (200, 201)
    print(f'  ✗ gh_put {path}: {r.status_code} {r.text[:200]}')
    return False


# ── BACKFILL ────────────────────────────────────────────────────────────────
# Stessa logica di status applicata da send_clienti_wave.py/wave2.py ad ogni
# invio (status 'new'→'sent'→'followup') — qui la riapplichiamo retroattivamente
# ai contatti già in wave PRIMA che quel fix esistesse, altrimenti Dashboard e
# Pipeline (che contano solo su `status`) restano sbagliate per sempre.
def _bump_status_for_wave(c: dict, wtype: str) -> None:
    st = c.get('status')
    if wtype == 'wave1' and st in (None, '', 'new'):
        c['status'] = 'sent'
    elif wtype == 'wave2' and st in (None, '', 'new', 'sent'):
        c['status'] = 'followup'


def backfill_brevo_events(contacts) -> int:
    created = 0
    for c in contacts:
        es = c.get('emailsSent')
        if not isinstance(es, list) or not es:
            continue
        for entry in es:
            if entry.get('type') in ('wave1', 'wave2'):
                _bump_status_for_wave(c, entry['type'])
        bev = c.get('brevoEvents')
        if not isinstance(bev, list):
            bev = []
        known_ids = {e.get('messageId') for e in bev if e.get('messageId')}
        added = 0

        for entry in es:
            wtype = entry.get('type')
            mid = entry.get('messageId')
            if wtype not in ('wave1', 'wave2') or not mid or mid in known_ids:
                continue
            bev.append({
                'messageId':    mid,
                'subject':      WAVE_SUBJECT_LABEL.get(wtype, wtype),
                'sentAt':       entry.get('sentAt'),
                'toEmail':      entry.get('toEmail') or c.get('email'),
                'toName':       c.get('company') or c.get('firstName') or '',
                'brand':        'ilciliegio',
                'sequenceStep': len(bev) + 1,
                'delivered': False, 'opened': False, 'clicked': False,
                'bounced': False, 'spam': False, 'unsubscribed': False, 'blocked': False,
            })
            known_ids.add(mid)
            added += 1

        if added:
            c['brevoEvents'] = bev
            created += added
    return created


# ── BREVO EVENTS — fetch bulk per intervallo di date ────────────────────────
# Niente chiamate 1-per-messaggio: con migliaia di email quel pattern rischia
# di sbattere contro un rate-limit dell'endpoint statistiche e fallire in
# silenzio. Una manciata di chiamate per intervallo date è molto più robusta.
#
# NB: avevo provato a filtrare anche per tags=wave1/wave2 lato server, ma la
# serializzazione esatta che Brevo si aspetta per quel parametro non è
# verificabile senza accesso diretto alla loro API — il filtro tornava 0
# eventi sempre, silenziosamente (nessun errore HTTP). Niente di documentato
# in modo affidabile su cui contare due volte: scarichiamo tutto l'intervallo
# di date (che invece sappiamo funzionare, l'unico errore visto finora è
# stato sulla validazione di endDate) e filtriamo lato nostro per messageId,
# che è un dato che controlliamo al 100%.
#
# Le stringhe esatte del campo "event" restituito da Brevo non sono
# consistenti tra le varie pagine della loro documentazione (es. "click" vs
# "clicks", "hardBounce" vs "hardBounces") — invece di scommettere su una
# forma esatta (e rischiare di sbagliarla di nuovo), classifichiamo per
# sottostringa case-insensitive: copre qualunque variante singolare/plurale o
# di maiuscole.
def _classify_event(etype: str) -> str | None:
    e = (etype or '').lower()
    if 'bounce' in e:
        return 'bounced'
    if 'click' in e:
        return 'clicked'
    if 'unsub' in e:
        return 'unsubscribed'
    if 'spam' in e:
        return 'spam'
    if e in ('blocked', 'invalid'):
        return 'blocked'
    if 'open' in e:
        return 'opened'
    if e in ('delivered', 'request', 'requests', 'sent'):
        return 'delivered'
    return None


def fetch_events_for_range(start_date: str, end_date: str) -> list:
    events = []
    offset = 0
    page_size = 2500
    while True:
        try:
            r = requests.get(
                'https://api.brevo.com/v3/smtp/statistics/events',
                headers=_BREVO_HEADERS,
                params={
                    'startDate': start_date,
                    'endDate': end_date,
                    'limit': page_size,
                    'offset': offset,
                    'sort': 'asc',
                },
                timeout=30,
            )
        except requests.exceptions.RequestException as e:
            print(f'  ⚠ Brevo events error (offset={offset}): {e}')
            break
        if not r.ok:
            print(f'  ⚠ Brevo events HTTP {r.status_code} (offset={offset}): {r.text[:200]}')
            break
        body = r.json() or {}
        page = body.get('events') or []
        if offset == 0:
            print(f'  Brevo risposta grezza (primi 300 char): {json.dumps(body)[:300]}')
        events.extend(page)
        if not page:
            break
        offset += len(page)
        if len(page) < page_size:
            break
        time.sleep(0.3)
    return events


def _norm_mid(mid: str) -> str:
    return (mid or '').strip().strip('<>')


# ── SYNC ────────────────────────────────────────────────────────────────────
def sync_contact_events(contacts, start_date: str, end_date: str) -> tuple[int, dict]:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    # Indice messageId → (contact, evento) per ogni voce brevoEvents non terminale
    index = {}
    for c in contacts:
        for ev in (c.get('brevoEvents') or []):
            if ev.get('bounced') or ev.get('spam') or ev.get('unsubscribed') or ev.get('blocked'):
                continue  # stato terminale, niente da aggiornare
            mid = _norm_mid(ev.get('messageId'))
            if mid:
                index[mid] = (c, ev)

    counts = {'delivered': 0, 'opened': 0, 'clicked': 0, 'bounced': 0, 'spam': 0, 'unsubscribed': 0, 'blocked': 0}
    changed_contacts = set()

    raw_events = fetch_events_for_range(start_date, end_date)
    seen_types = sorted({e.get('event') for e in raw_events if e.get('event')})
    matched = sum(1 for e in raw_events if _norm_mid(e.get('messageId')) in index)
    print(f'  Brevo: {len(raw_events)} eventi totali nel periodo, {matched} corrispondono a email wave note')
    if seen_types:
        print(f'  Tipi di evento visti: {", ".join(seen_types)}')

    for e in raw_events:
        mid = _norm_mid(e.get('messageId'))
        hit = index.get(mid)
        if not hit:
            continue
        c, ev = hit
        kind = _classify_event(e.get('event'))
        if not kind or ev.get(kind):
            continue

        ev[kind] = True
        ev[kind + 'At'] = e.get('date')
        counts[kind] += 1
        changed_contacts.add(id(c))

        if kind in ('opened', 'clicked', 'bounced', 'spam', 'unsubscribed', 'blocked'):
            log = c.get('log')
            if not isinstance(log, list):
                log = []
            subj = ev.get('subject') or ''
            msg = {
                'opened':       f'👁 Aperta: {subj}',
                'clicked':      f'🔗 Click: {subj}',
                'bounced':      f'⚠ Bounce: {subj}',
                'spam':         f'🚫 Spam: {subj}',
                'unsubscribed': f'🚫 Disiscritto: {subj}',
                'blocked':      f'🔒 Bloccata: {subj}',
            }[kind]
            log.append({'ts': now_ms, 'msg': msg})
            c['log'] = log

        if kind in ('unsubscribed', 'blocked') and not c.get('blacklisted'):
            c['blacklisted'] = True
            c.setdefault('log', []).append(
                {'ts': now_ms, 'msg': '🚫 Contatto inserito in blacklist (disiscrizione/bloccata)'})

    return len(changed_contacts), counts


# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print('=' * 50)
    print(f'sync_wave_brevo_events.py — {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 50)

    if not BREVO_API_KEY:
        print('✗ BREVO_API_KEY non trovata')
        sys.exit(1)

    db, db_sha = gh_get(DATA_PATH)
    contacts = db.get('contacts') or []
    print(f'Contatti totali: {len(contacts)}')

    created = backfill_brevo_events(contacts)
    print(f'Backfill: {created} voci brevoEvents create da emailsSent')

    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=WAVE_SYNC_CUTOFF_DAYS)).strftime('%Y-%m-%d')
    end_date = now.strftime('%Y-%m-%d')  # Brevo rifiuta endDate > oggi

    updated, counts = sync_contact_events(contacts, start_date, end_date)
    print(f'Sync Brevo ({start_date}..{end_date}): {updated} contatti con nuovi eventi')
    print(f'  delivered={counts["delivered"]} opened={counts["opened"]} clicked={counts["clicked"]} '
          f'bounced={counts["bounced"]} spam={counts["spam"]} unsubscribed={counts["unsubscribed"]} '
          f'blocked={counts["blocked"]}')

    if created or updated:
        _gh_sha_cache[DATA_PATH] = db_sha
        ok = gh_put(DATA_PATH, db,
                    f'Sync wave tracking Brevo — {datetime.now().strftime("%Y-%m-%d %H:%M")} UTC '
                    f'({created} backfill, {updated} aggiornati)')
        if ok:
            print('✓ clienti.json aggiornato su GitHub')
        else:
            print('⚠ Errore salvataggio clienti.json')
            sys.exit(1)
    else:
        print('✓ Nessuna modifica da salvare.')


if __name__ == '__main__':
    main()
