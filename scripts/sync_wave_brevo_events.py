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
from datetime import datetime, timezone

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
def backfill_brevo_events(contacts) -> int:
    created = 0
    for c in contacts:
        es = c.get('emailsSent')
        if not isinstance(es, list) or not es:
            continue
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


# ── SYNC ────────────────────────────────────────────────────────────────────
def sync_contact_events(contacts) -> int:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    cutoff_ms = now_ms - WAVE_SYNC_CUTOFF_DAYS * 24 * 3600 * 1000

    updated = 0
    for c in contacts:
        bev = c.get('brevoEvents')
        if not isinstance(bev, list):
            continue

        contact_changed = False
        for ev in bev:
            if ev.get('bounced') or ev.get('spam') or ev.get('unsubscribed') or ev.get('blocked'):
                continue  # stato terminale, non richiamare più l'API
            if not ev.get('messageId') or (ev.get('sentAt') or 0) < cutoff_ms:
                continue

            try:
                r = requests.get(
                    'https://api.brevo.com/v3/smtp/statistics/events',
                    headers=_BREVO_HEADERS,
                    params={'messageId': ev['messageId'], 'limit': 50},
                    timeout=20,
                )
                if not r.ok:
                    continue
                events = (r.json() or {}).get('events') or []
            except requests.exceptions.RequestException as e:
                print(f'  ⚠ Brevo events error per {ev["messageId"]}: {e}')
                continue

            log = c.get('log')
            if not isinstance(log, list):
                log = []

            for e in events:
                etype = (e.get('event') or '').lower()
                subj = ev.get('subject') or ''
                if etype in ('delivered', 'requests') and not ev.get('delivered'):
                    ev['delivered'] = True
                    ev['deliveredAt'] = e.get('date')
                    contact_changed = True
                if etype in ('opened', 'unique_opened') and not ev.get('opened'):
                    ev['opened'] = True
                    ev['openedAt'] = e.get('date')
                    contact_changed = True
                    log.append({'ts': now_ms, 'msg': f'👁 Aperta: {subj}'})
                if etype in ('clicks', 'click') and not ev.get('clicked'):
                    ev['clicked'] = True
                    ev['clickedAt'] = e.get('date')
                    contact_changed = True
                    log.append({'ts': now_ms, 'msg': f'🔗 Click: {subj}'})
                if etype in ('hardbounces', 'softbounces', 'bounced') and not ev.get('bounced'):
                    ev['bounced'] = True
                    ev['bouncedAt'] = e.get('date')
                    contact_changed = True
                    log.append({'ts': now_ms, 'msg': f'⚠ Bounce: {subj}'})
                if etype in ('spamreports', 'spam') and not ev.get('spam'):
                    ev['spam'] = True
                    contact_changed = True
                    log.append({'ts': now_ms, 'msg': f'🚫 Spam: {subj}'})
                if etype == 'unsubscribed' and not ev.get('unsubscribed'):
                    ev['unsubscribed'] = True
                    contact_changed = True
                    log.append({'ts': now_ms, 'msg': f'🚫 Disiscritto: {subj}'})
                if etype in ('blocked', 'invalid') and not ev.get('blocked'):
                    ev['blocked'] = True
                    contact_changed = True
                    log.append({'ts': now_ms, 'msg': f'🔒 Bloccata: {subj}'})

            if (ev.get('unsubscribed') or ev.get('blocked')) and not c.get('blacklisted'):
                c['blacklisted'] = True
                contact_changed = True
                log.append({'ts': now_ms, 'msg': '🚫 Contatto inserito in blacklist (disiscrizione/bloccata)'})

            if log:
                c['log'] = log

            time.sleep(0.12)  # rate-limit gentile su Brevo, come il sync da browser

        if contact_changed:
            updated += 1

    return updated


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

    updated = sync_contact_events(contacts)
    print(f'Sync Brevo: {updated} contatti con nuovi eventi (apertura/click/bounce)')

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
