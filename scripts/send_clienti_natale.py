# -*- coding: utf-8 -*-
"""
send_clienti_natale.py
======================
Campagna di Natale (Ciliegio Selection) ai clienti privati (WiFi registrations).

Chi riceve la mail (decisione di Luca, 14/11/2026):
  - quality='valid', shippable=True, non blacklisted, con email, paese non in excludedCountriesClienti
  - ultimo contatto (qualsiasi mail) di almeno 120 giorni fa, oppure mai contattato
  - registrati da almeno 120 giorni ("sono passati da noi da almeno 4 mesi")
  - non ha gia' ricevuto questa campagna (data/natale-invii.json + emailsSent type 'natale')
Italia -> template 'natale_it' (italiano), altri -> 'natale' (inglese). I template stanno in data/clienti.json (templates).
Ordine di invio: prima l'Italia, poi gli altri dal contatto piu' vecchio.

Uso:
  python scripts/send_clienti_natale.py --prova              solo conteggi, non invia niente
  python scripts/send_clienti_natale.py --test               2 mail di prova (1 IT + 1 EN) a hokutazzo@gmail.com, niente salvato
  python scripts/send_clienti_natale.py --limit 500          invio vero di un blocco (riprende da dove era rimasto)
  python scripts/send_clienti_natale.py --limit 500 --solo-italia

Sicurezza: ogni 25 invii salva un file piccolo (data/natale-invii.json), cosi' un blocco interrotto non genera doppioni;
a fine blocco riporta le voci in clienti.json RILEGGENDOLO fresco (non sovrascrive mai modifiche fatte da altri nel frattempo).
"""
import argparse
import base64
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import send_clienti_wave2 as w   # noqa: E402  (riuso: GitHub API, build_html, mappa paesi, intestazioni Brevo)

SENT_PATH = 'data/natale-invii.json'
TAG = 'natale'
LOGO_NERO_URL = 'https://shopilciliegio-ship-it.github.io/crm-importatori/assets/logo_ciliegio_fondo_nero.png'
FOUR_MONTHS_MS = 120 * 24 * 3600 * 1000
CHECKPOINT_EVERY = 25
MAX_CONSECUTIVE_ERRORS = 5


def ts_ms(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def last_contact(c):
    best = 0
    for e in (c.get('emailsSent') or []):
        best = max(best, ts_ms(e.get('sentAt')) or 0)
    for e in (c.get('brevoEvents') or []):
        best = max(best, ts_ms(e.get('sentAt')) or 0)
    return best


def clean_name(c):
    raw = (c.get('firstName') or c.get('nome') or (c.get('company') or '').split(' ')[0] or '').strip()
    if len(raw) < 2 or re.search(r'[\d@_]', raw):
        return ''
    if raw.isupper() or raw.islower():
        raw = raw.title()
    return raw


def fill(text, name):
    for ph in ('{{nome}}', '{{name}}', '{{contatto}}'):
        text = text.replace(ph, '{firstName}')
    if not name:
        text = text.replace(' {firstName}', '').replace('{firstName}', '')
    return text.replace('{firstName}', name)


def candidates(contacts, settings, already, only_italy, now_ms):
    excluded = set(settings.get('excludedCountriesClienti', []))
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'natale-escludi.json'), encoding='utf-8') as f:
            skip = {x.lower() for x in json.load(f)}
    except Exception:
        skip = set()
    out = []
    for c in contacts:
        if not c.get('email') or c.get('quality') != 'valid' or c.get('shippable') is not True:
            continue
        if c.get('blacklisted') or c['email'].strip().lower() in skip:
            continue
        if w.country_display_name(c) in excluded:
            continue
        if c['id'] in already or any(e.get('type') == TAG for e in (c.get('emailsSent') or [])):
            continue
        lc = last_contact(c)
        if lc and lc > now_ms - FOUR_MONTHS_MS:
            continue
        reg = ts_ms(c.get('registeredAt'))
        if reg and reg > now_ms - FOUR_MONTHS_MS:
            continue
        if only_italy and not w.is_italian(c):
            continue
        out.append(c)
    out.sort(key=lambda c: (0 if w.is_italian(c) else (1 if w.country_display_name(c) in ('United States', 'USA', 'United States of America') else 2), last_contact(c) or ts_ms(c.get('registeredAt')) or 0))
    return out


def add_footer_links(html, lang):
    """Sito cliccabile e ben visibile + link di disiscrizione Brevo ({{ unsubscribe }}) nel piede della mail."""
    html = html.replace('color:#cccccc;text-decoration:none', f'color:{w.ACCENT};text-decoration:underline')
    html = html.replace(w.LOGO_URL, LOGO_NERO_URL)
    link = 'style="color:#cccccc;text-decoration:underline"'
    if lang == 'it':
        txt = f"Non vuoi più ricevere le nostre email? <a href=\"{{{{ unsubscribe }}}}\" {link}>Annulla l'iscrizione</a>"
    else:
        txt = f"Don't want to receive our emails anymore? <a href=\"{{{{ unsubscribe }}}}\" {link}>Unsubscribe</a>"
    nl = chr(10)
    marker = w.PHONE + '</span>' + nl + '    </p>'
    assert marker in html, 'footer non trovato'
    extra = nl + '    <p style="margin:14px 0 0;font-size:11px;color:#999">' + txt + '</p>'
    return html.replace(marker, marker + extra, 1)


def send_one(to_email, to_name, subject, body, contact_id, test_mode, lang):
    actual_to = w.BCC_EMAIL if test_mode else to_email
    actual_subj = f'[TEST → {to_email}] {subject}' if test_mode else subject
    html = w.build_html(body, actual_subj).replace('<html lang="it">', f'<html lang="{lang}">')
    html = add_footer_links(html, lang)
    payload = {
        'sender': {'name': w.SENDER_NAME, 'email': w.SENDER_EMAIL},
        'to': [{'email': actual_to, **({'name': to_name.strip()} if (to_name or '').strip() else {})}],
        'subject': actual_subj,
        'textContent': body,
        'htmlContent': html,
        'tags': ['wine-crm', 'clienti', TAG] + (['test'] if test_mode else []),
        'headers': {'X-CRM-ContactId': contact_id},
        'trackClicks': True,
        'trackOpens': True,
    }
    r = requests.post('https://api.brevo.com/v3/smtp/email', headers=w._BREVO_HEADERS, json=payload, timeout=20)
    if r.ok:
        return r.json().get('messageId', ''), None
    return None, f'{r.status_code} {r.text[:140]}'


def merge_into_clienti(sent_entries, subj_by_lang, now_ms):
    """Riporta gli invii in clienti.json rileggendolo fresco (mai sovrascrivere modifiche altrui)."""
    for attempt in range(4):
        db, sha = w.gh_get(w.DATA_PATH)
        if not db.get('contacts'):
            return False
        by_id = {c['id']: c for c in db['contacts']}
        n = 0
        for s in sent_entries:
            c = by_id.get(s['id'])
            if not c or any(e.get('messageId') == s['msgId'] for e in (c.get('emailsSent') or [])):
                continue
            es = c.get('emailsSent') if isinstance(c.get('emailsSent'), list) else []
            es.append({'type': TAG, 'sentAt': s['sentAt'], 'messageId': s['msgId'], 'toEmail': s['email']})
            c['emailsSent'] = es
            bev = c.get('brevoEvents') if isinstance(c.get('brevoEvents'), list) else []
            bev.append({'messageId': s['msgId'], 'subject': s['subject'], 'sentAt': s['sentAt'], 'toEmail': s['email'],
                        'toName': s.get('name', ''), 'brand': 'ilciliegio', 'sequenceStep': len(bev) + 1,
                        'delivered': False, 'opened': False, 'clicked': False, 'bounced': False,
                        'spam': False, 'unsubscribed': False, 'blocked': False})
            c['brevoEvents'] = bev
            n += 1
        w._gh_sha_cache[w.DATA_PATH] = sha
        if w.gh_put(w.DATA_PATH, db, f'Campagna Natale clienti: {n} email — {datetime.now().strftime("%Y-%m-%d %H:%M")} UTC'):
            print(f'✓ clienti.json aggiornato ({n} voci riportate)')
            return True
        time.sleep(3 * (attempt + 1))
    print('⚠ clienti.json NON aggiornato (le voci restano in data/natale-invii.json e verranno riportate al prossimo blocco)')
    return False


def save_sent_file(entries):
    ok = w.gh_put(SENT_PATH, entries, f'Natale clienti: checkpoint {len(entries)} invii')
    if not ok:
        print('⚠ checkpoint natale-invii.json non salvato')
    return ok


def digest(sent, errors, remaining, test_mode):
    rows = ''.join(f'<tr><td style="padding:4px 8px">{s["name"]}</td><td style="padding:4px 8px;color:#666">{s["email"]}</td></tr>' for s in sent[:40])
    html = (f'<div style="font-family:sans-serif;font-size:14px;color:#333"><h2 style="color:{w.ACCENT}">📧 Campagna Natale clienti — {datetime.now().strftime("%d/%m/%Y %H:%M")}</h2>'
            f'<p>{"TEST" if test_mode else "PRODUZIONE"} · inviati {len(sent)} · errori {errors} · ancora in coda {remaining}</p>'
            f'<table style="font-size:13px;border-collapse:collapse">{rows}</table></div>')
    r = requests.post('https://api.brevo.com/v3/smtp/email', headers=w._BREVO_HEADERS, timeout=20, json={
        'sender': {'name': w.SENDER_NAME, 'email': w.SENDER_EMAIL}, 'to': [{'email': w.DIGEST_RECIPIENT, 'name': 'Luca'}],
        'subject': f'[CRM] Natale clienti: {len(sent)} email inviate — {datetime.now().strftime("%d/%m/%Y %H:%M")}',
        'htmlContent': html, 'tags': ['wine-crm', 'digest', 'clienti', TAG]})
    print('✓ digest inviato' if r.ok else f'⚠ digest non inviato ({r.status_code})')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=500)
    ap.add_argument('--solo-italia', action='store_true')
    ap.add_argument('--test', action='store_true')
    ap.add_argument('--prova', action='store_true')
    ap.add_argument('--eventi', default='', help='mostra gli eventi Brevo (ultimi 2 giorni) per gli indirizzi dati, separati da virgola')
    ap.add_argument('--reale-a', default='', help='invio REALE a indirizzi dati: lingua:email:Nome,lingua:email:Nome (nessun salvataggio nel CRM)')
    a = ap.parse_args()

    print('=' * 56)
    print(f'send_clienti_natale.py — {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 56)
    if a.eventi:
        for em in a.eventi.split(','):
            r = requests.get('https://api.brevo.com/v3/smtp/statistics/events', headers=w._BREVO_HEADERS, timeout=20,
                             params={'email': em.strip(), 'days': 2, 'limit': 20, 'sort': 'desc'})
            print(em, r.status_code)
            for e in (r.json().get('events') or []) if r.ok else []:
                print('   ', e.get('date'), e.get('event'), (e.get('subject') or '')[:50], e.get('reason') or '')
        return
    settings, _ = w.gh_get(w.SETTINGS_PATH)
    if not settings.get('emailAutoSendClienti', False):
        print('⏸ Invio clienti disabilitato (toggle OFF nel CRM). Nessuna email inviata.')
        return
    if not a.prova and not w.BREVO_API_KEY:
        print('✗ BREVO_API_KEY non trovata')
        sys.exit(1)

    db, _ = w.gh_get(w.DATA_PATH)
    contacts = db.get('contacts') or []
    templates = db.get('templates') or []
    tpl_en = next((t for t in templates if t.get('id') == 'natale'), None)
    tpl_it = next((t for t in templates if t.get('id') == 'natale_it'), None)
    if not (tpl_en and tpl_it):
        print('✗ Template "natale" e/o "natale_it" non trovati in clienti.json: non invio niente.')
        sys.exit(1)

    if a.reale_a:
        for item in a.reale_a.split(','):
            lang, email, name = (item.strip().split(':') + [''])[:3]
            tpl = tpl_it if lang == 'it' else tpl_en
            msg_id, err = send_one(email, name, fill(tpl['subject'], name), fill(tpl['body'], name), 'reale-prova', False, lang)
            print(f'    {"✓" if msg_id else "✗"} REALE {lang} -> {email} {err or msg_id}')
        return

    prev, _ = w.gh_get(SENT_PATH)
    prev = prev if isinstance(prev, list) else []
    already = {p['id'] for p in prev}
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    cand = candidates(contacts, settings, already, a.solo_italia, now_ms)
    n_it = sum(1 for c in cand if w.is_italian(c))
    print(f'Candidati: {len(cand)} (Italia {n_it}, estero {len(cand) - n_it}) — gia\' inviati in precedenza: {len(already)}')
    if a.prova:
        for c in cand[:5]:
            print('  ·', c.get('email'), '|', w.country_display_name(c), '|', clean_name(c) or '(senza nome)')
        print('(prova: non e\' stato inviato niente)')
        return

    if a.test:
        it1 = next((c for c in cand if w.is_italian(c)), None)
        en1 = next((c for c in cand if not w.is_italian(c)), None)
        batch = [c for c in (it1, en1) if c]
    else:
        batch = cand[:a.limit]
    test_mode = a.test
    print(('🧪 TEST — ' if test_mode else '👥 PRODUZIONE — ') + f'blocco di {len(batch)} email')

    sent, errors, consecutive = [], 0, 0
    for c in batch:
        it = w.is_italian(c)
        tpl = tpl_it if it else tpl_en
        name = clean_name(c)
        subject = fill(tpl['subject'], name)
        body = fill(tpl['body'], name)
        msg_id, err = send_one(c['email'], c.get('company') or name, subject, body, c['id'], test_mode, 'it' if it else 'en')
        if msg_id:
            consecutive = 0
            sent.append({'id': c['id'], 'email': c['email'], 'name': c.get('company') or name, 'msgId': msg_id,
                         'sentAt': int(time.time() * 1000), 'lang': 'it' if it else 'en', 'subject': subject})
            print(f'    ✓ {"TEST → " + w.BCC_EMAIL if test_mode else c["email"]}')
            if not test_mode and len(sent) % CHECKPOINT_EVERY == 0:
                save_sent_file(prev + sent)
        else:
            errors += 1
            consecutive += 1
            print(f'    ✗ {c["email"]}: {err}')
            if consecutive >= MAX_CONSECUTIVE_ERRORS or (err and err[:3] in ('401', '402', '429')):
                print('🚨 Mi fermo: troppi errori di fila o limite/credenziali Brevo.')
                break
        time.sleep(0.1)

    print(f'\nInviati {len(sent)} · errori {errors}')
    if not test_mode and sent:
        save_sent_file(prev + sent)
        merge_into_clienti(prev + sent if prev else sent, None, now_ms)
        log, _ = w.gh_get(w.LOG_PATH)
        if isinstance(log, list):
            for s in sent:
                log.append({'date': datetime.now(timezone.utc).isoformat(), 'module': 'clienti_natale', 'to': s['email'],
                            'name': s['name'], 'messageId': s['msgId']})
            w.gh_put(w.LOG_PATH, log, f'Natale clienti — {datetime.now().strftime("%Y-%m-%d %H:%M")} UTC')
    remaining = len(cand) - len(sent) if not test_mode else len(cand)
    digest(sent, errors, remaining, test_mode)
    print(f'Ancora in coda: {remaining}')


if __name__ == '__main__':
    main()
