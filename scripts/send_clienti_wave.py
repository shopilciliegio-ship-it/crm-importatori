# -*- coding: utf-8 -*-
"""
send_clienti_wave.py
====================
Invia la prossima wave di email ai clienti privati (WiFi registrations).

- Legge data/clienti.json da GitHub
- Filtra: quality='valid', shippable=True, blacklisted=False, waveStatus=None
- Ordina per registeredAt ASC (oldest first)
- Invia al prossimo batch (default 500)
- Aggiorna waveStatus + emailsSent (solo in produzione)
- Invia digest a luca@ilciliegio.com
- Salva clienti.json su GitHub

Test mode  → tutte le email vanno a hokutazzo@gmail.com, niente salvato
Produzione → email ai clienti reali + BCC a hokutazzo@gmail.com
"""

import json
import os
import sys
import time
import requests
from datetime import datetime, timezone

# ── PATHS ────────────────────────────────────────────────────────────────────
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT     = os.path.dirname(SCRIPT_DIR)
DATA_PATH     = 'data/clienti.json'
SETTINGS_PATH = 'data/crm-settings.json'
LOG_PATH      = 'data/email-log.json'

# ── COSTANTI ─────────────────────────────────────────────────────────────────
BCC_EMAIL        = 'hokutazzo@gmail.com'
DIGEST_RECIPIENT = 'luca@ilciliegio.com'
SENDER_NAME      = 'Il Ciliegio — Azienda Agricola'
SENDER_EMAIL     = 'luca@sienawine.it'
LOGO_URL         = 'https://shopilciliegio-ship-it.github.io/crm-importatori/assets/logo_ciliegio.png'
ACCENT           = '#B8941A'

BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')
GH_TOKEN      = os.environ.get('GH_TOKEN', '')
GH_OWNER      = os.environ.get('GH_OWNER', 'shopilciliegio-ship-it')
GH_REPO       = os.environ.get('GH_REPO', 'crm-importatori')

DEFAULT_BATCH_SIZE = 500

# Mappa codice ISO2 (minuscolo) → nome leggibile, come usato dal CRM (js/templates.js ISO2NAME)
# Serve per confrontare c['country'] con la lista excludedCountriesClienti scelta nel CRM,
# che mostra i nomi leggibili dei paesi presenti in dbC.contacts.
COUNTRY_CODE_TO_NAME = {
    'it':'Italia','de':'Germania','be':'Belgio','nl':'Paesi Bassi','lu':'Lussemburgo',
    'fr':'Francia','dk':'Danimarca','at':'Austria','es':'Spagna','pt':'Portogallo',
    'se':'Svezia','ie':'Irlanda','si':'Slovenia','fi':'Finlandia','hr':'Croazia',
    'gr':'Grecia','pl':'Polonia','cz':'Rep. Ceca','sk':'Slovacchia','hu':'Ungheria',
    'bg':'Bulgaria','ee':'Estonia','lv':'Lettonia','lt':'Lituania','ro':'Romania',
    'cy':'Cipro','mt':'Malta','us':'USA','ca':'Canada','gb':'Gran Bretagna',
    'ch':'Svizzera','no':'Norvegia',
}


def country_display_name(c: dict) -> str:
    """Nome paese come mostrato nel CRM (per confronto con excludedCountriesClienti)."""
    raw = (c.get('country') or '').strip()
    return COUNTRY_CODE_TO_NAME.get(raw.lower(), raw)

# ── DEFAULT TEMPLATE WAVE 1 ──────────────────────────────────────────────────
DEFAULT_WAVE1_SUBJECT = "We met at Il Ciliegio Winery — Welcome!"
DEFAULT_WAVE1_BODY = """\
Dear {firstName},

Thank you for visiting Il Ciliegio Winery during your stay in Tuscany!

We hope you enjoyed your time with us and had a chance to taste our wines.
We'd love to stay in touch and share our latest news, seasonal releases, and exclusive offers with you.

🍷 Discover our wines and order online:
https://www.ciliegioshop.it

You're receiving this email because you connected to our WiFi during your visit.
If you'd like to unsubscribe, simply reply to this email.

Warm regards,
Luca Pattaro
Il Ciliegio — Azienda Agricola
Loc. Podere il Ciliegio, Siena (IT)
www.sienawine.it
"""

# ── GITHUB API ───────────────────────────────────────────────────────────────
_gh_sha_cache: dict[str, str] = {}
_BREVO_HEADERS = {
    'api-key': BREVO_API_KEY,
    'Content-Type': 'application/json',
    'Accept': 'application/json',
}


def _gh_headers():
    return {
        'Authorization': f'token {GH_TOKEN}',
        'Accept': 'application/vnd.github.v3+json',
    }


def gh_get(path: str) -> tuple[dict | list, str | None]:
    if not GH_TOKEN:
        # Fallback: leggi da file locale
        local = os.path.join(REPO_ROOT, path)
        if os.path.exists(local):
            with open(local, encoding='utf-8') as f:
                return json.load(f), None
        return {}, None

    url = f'https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{path}'
    r = requests.get(url, headers=_gh_headers(), timeout=20)
    if r.status_code == 404:
        return {}, None
    r.raise_for_status()
    d = r.json()
    sha = d.get('sha')
    raw = d['content'].replace('\n', '')
    try:
        import base64
        json_str = base64.b64decode(raw).decode('utf-8')
    except Exception:
        json_str = raw
    _gh_sha_cache[path] = sha
    return json.loads(json_str), sha


def gh_put(path: str, data, message: str):
    if not GH_TOKEN:
        local = os.path.join(REPO_ROOT, path)
        with open(local, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True

    import base64
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
        # Conflitto SHA — rileggi e riprova
        _, new_sha = gh_get(path)
        if new_sha:
            body['sha'] = new_sha
            r2 = requests.put(url, headers=_gh_headers(), json=body, timeout=30)
            return r2.status_code in (200, 201)
    print(f'  ✗ gh_put {path}: {r.status_code} {r.text[:120]}')
    return False


# ── EMAIL ────────────────────────────────────────────────────────────────────
def build_html(text: str, subject: str) -> str:
    paragraphs = ''.join(
        f'<p style="margin:0 0 14px 0;line-height:1.7">{p.strip()}</p>'
        for p in text.strip().split('\n\n') if p.strip()
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#f5f5f0;font-family:'Georgia',serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f0;padding:32px 16px">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0"
  style="background:#fff;border-radius:8px;overflow:hidden;max-width:600px">
  <tr>
    <td style="background:{ACCENT};padding:24px 32px;text-align:center">
      <img src="{LOGO_URL}" alt="Il Ciliegio" height="48"
        style="max-height:48px;filter:brightness(0)invert(1)" onerror="this.style.display='none'">
      <div style="color:#fff;font-size:13px;letter-spacing:2px;
                  text-transform:uppercase;margin-top:8px;opacity:.9">
        Azienda Agricola · Siena
      </div>
    </td>
  </tr>
  <tr>
    <td style="padding:32px;color:#333;font-size:15px">
      {paragraphs}
    </td>
  </tr>
  <tr>
    <td style="background:#f9f6ee;padding:20px 32px;border-top:1px solid #e8e0cc">
      <p style="margin:0;font-size:12px;color:#888;line-height:1.6;text-align:center">
        Il Ciliegio — Azienda Agricola<br>
        Loc. Podere il Ciliegio, Siena (SI) · Italy<br>
        <a href="https://www.sienawine.it"
           style="color:#888;text-decoration:none">www.sienawine.it</a>
        &nbsp;·&nbsp;
        <a href="mailto:luca@sienawine.it"
           style="color:#888;text-decoration:none">luca@sienawine.it</a>
      </p>
    </td>
  </tr>
</table>
</td></tr></table>
</body></html>"""


def send_email(to_email: str, to_name: str, subject: str, body: str,
               contact_id: str, test_mode: bool) -> str | None:
    if test_mode:
        actual_to   = BCC_EMAIL
        actual_subj = f'[TEST → {to_email}] {subject}'
        actual_bcc  = []
        print(f'    🧪 TEST wave1 → {BCC_EMAIL} (reale: {to_email})')
    else:
        actual_to   = to_email
        actual_subj = subject
        actual_bcc  = [{'email': BCC_EMAIL}]
        print(f'    ✓ wave1 → {to_email}')

    payload = {
        'sender':      {'name': SENDER_NAME, 'email': SENDER_EMAIL},
        'to':          [{'email': actual_to, 'name': to_name}],
        'subject':     actual_subj,
        'textContent': body,
        'htmlContent': build_html(body, actual_subj),
        'tags':        ['wine-crm', 'clienti', 'wave1'] + (['test'] if test_mode else []),
        'headers':     {'X-CRM-ContactId': contact_id},
        'trackClicks': True,
        'trackOpens':  True,
    }
    if actual_bcc:
        payload['bcc'] = actual_bcc

    r = requests.post(
        'https://api.brevo.com/v3/smtp/email',
        headers=_BREVO_HEADERS,
        json=payload,
        timeout=20,
    )
    if r.ok:
        return r.json().get('messageId', '')
    print(f'    ✗ Brevo {r.status_code}: {r.text[:120]}')
    return None


def send_digest(sent: list, errors: int, test_mode: bool, batch_size: int,
                total_remaining: int):
    if not sent and errors == 0:
        return
    mode_badge = (
        '<span style="background:#ff9800;color:#fff;padding:2px 8px;'
        'border-radius:4px;font-size:11px;font-weight:bold">TEST MODE</span>'
        if test_mode else
        '<span style="background:#4caf50;color:#fff;padding:2px 8px;'
        'border-radius:4px;font-size:11px;font-weight:bold">PRODUZIONE</span>'
    )
    rows = ''.join(
        f'<tr style="border-bottom:1px solid #eee">'
        f'<td style="padding:6px 8px">{r["name"]}</td>'
        f'<td style="padding:6px 8px;color:#666;font-size:12px">{r["email"]}</td>'
        f'<td style="padding:6px 8px;color:#2e7d32;font-size:12px">✓ {r["msgId"][:20]}…</td>'
        f'</tr>'
        for r in sent[:50]  # max 50 righe
    )
    body_html = f"""
    <div style="font-family:sans-serif;font-size:14px;color:#333;max-width:600px;margin:0 auto">
      <h2 style="color:{ACCENT}">📧 Digest clienti wave — {datetime.now().strftime('%d/%m/%Y')}</h2>
      <p>{mode_badge} &nbsp; Batch: {len(sent)}/{batch_size} inviati &nbsp;|&nbsp;
         Errori: {errors} &nbsp;|&nbsp; Rimanenti in coda: {total_remaining}</p>
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border:1px solid #ddd;border-radius:4px;border-collapse:collapse;font-size:13px">
        <thead>
          <tr style="background:#f5f5f0">
            <th align="left" style="padding:8px">Nome</th>
            <th align="left" style="padding:8px">Email</th>
            <th align="left" style="padding:8px">Status</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      {'<p style="color:#888;font-size:12px">…e altri '+(str(len(sent)-50))+' non mostrati</p>' if len(sent)>50 else ''}
    </div>"""

    payload = {
        'sender':      {'name': SENDER_NAME, 'email': SENDER_EMAIL},
        'to':          [{'email': DIGEST_RECIPIENT, 'name': 'Luca'}],
        'subject':     f'[CRM] Wave clienti: {len(sent)} email inviate — {datetime.now().strftime("%d/%m/%Y")}',
        'htmlContent': body_html,
        'tags':        ['wine-crm', 'digest', 'clienti'],
    }
    r = requests.post(
        'https://api.brevo.com/v3/smtp/email',
        headers=_BREVO_HEADERS,
        json=payload,
        timeout=20,
    )
    if r.ok:
        print(f'\n✓ Digest inviato a {DIGEST_RECIPIENT}')
    else:
        print(f'\n⚠ Digest non inviato: {r.status_code}')


# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print('=' * 50)
    print(f'send_clienti_wave.py — {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 50)

    # Leggi settings
    settings, _ = gh_get(SETTINGS_PATH)
    if not settings.get('emailAutoSendClienti', False):
        print('⏸ Invio clienti disabilitato (toggle OFF nel CRM). Nessuna email inviata.')
        return

    test_mode  = settings.get('testModeClienti', True)
    batch_size = settings.get('waveBatchSize', DEFAULT_BATCH_SIZE)

    if test_mode:
        print(f'🧪 TEST MODE — email a {BCC_EMAIL}, niente salvato in emailsSent')
    else:
        print(f'👥 PRODUZIONE — email ai clienti reali, tutto registrato')

    if not BREVO_API_KEY:
        print('✗ BREVO_API_KEY non trovata')
        sys.exit(1)

    # Carica clienti.json
    db, db_sha = gh_get(DATA_PATH)
    contacts = db.get('contacts') or []

    # Filtra candidati wave1
    excluded_countries = set(settings.get('excludedCountriesClienti', []))
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    candidates = [
        c for c in contacts
        if c.get('quality') in ('valid',)        # solo verdi (sospetti: review manuale)
        and c.get('shippable', False)
        and not c.get('blacklisted', False)
        and not c.get('waveStatus')               # non ancora contattati
        and c.get('email')
        and country_display_name(c) not in excluded_countries
    ]

    # Ordina per registeredAt ASC (oldest first)
    candidates.sort(key=lambda c: c.get('registeredAt') or 0)

    total_remaining = len(candidates)
    batch = candidates[:batch_size]

    print(f'\nCandidati wave1: {total_remaining}')
    print(f'Batch questo run: {len(batch)} (max {batch_size})')
    print()

    if not batch:
        print('✓ Nessun contatto da inviare in questo batch.')
        send_digest([], 0, test_mode, batch_size, 0)
        return

    # Leggi template (dal DB o default)
    templates    = db.get('templates') or []
    wave1_tpl    = next((t for t in templates if t.get('id') == 'wave1'), None)
    wave1_subj   = wave1_tpl['subject'] if wave1_tpl else DEFAULT_WAVE1_SUBJECT
    wave1_body_t = wave1_tpl['body']    if wave1_tpl else DEFAULT_WAVE1_BODY

    # Mappa email → contatto per aggiornamento rapido
    contact_map = {c['email']: c for c in contacts}

    sent_log = []
    errors   = 0

    for c in batch:
        first_name = c.get('firstName') or c.get('nome') or c.get('company', '').split()[0] or 'friend'
        body = wave1_body_t.replace('{firstName}', first_name) \
                           .replace('{lastName}',  c.get('lastName', '')) \
                           .replace('{email}',     c.get('email', '')) \
                           .replace('{{nome}}',     first_name) \
                           .replace('{{contatto}}', first_name)
        subj = wave1_subj.replace('{{nome}}', first_name).replace('{{contatto}}', first_name)

        msg_id = send_email(
            to_email=c['email'],
            to_name=c.get('company', first_name),
            subject=subj,
            body=body,
            contact_id=c['id'],
            test_mode=test_mode,
        )

        if msg_id:
            sent_log.append({'name': c.get('company',''), 'email': c['email'], 'msgId': msg_id})
            if not test_mode:
                contact_map[c['email']]['waveStatus'] = 'wave1_sent'
                contact_map[c['email']].setdefault('emailsSent', []).append({
                    'type':      'wave1',
                    'sentAt':    now_ms,
                    'messageId': msg_id,
                    'toEmail':   c['email'],
                })
        else:
            errors += 1

        time.sleep(0.1)  # rate-limit gentile su Brevo

    print(f'\n{"─"*40}')
    print(f'Inviati:  {len(sent_log)}')
    print(f'Errori:   {errors}')
    print(f'Rimanenti dopo questo batch: {total_remaining - len(sent_log)}')

    # Aggiorna email-log
    if sent_log and not test_mode:
        log, _ = gh_get(LOG_PATH)
        if not isinstance(log, list):
            log = []
        for entry in sent_log:
            log.append({
                'date':      datetime.now(timezone.utc).isoformat(),
                'module':    'clienti_wave1',
                'to':        entry['email'],
                'name':      entry['name'],
                'messageId': entry['msgId'],
            })
        gh_put(LOG_PATH, log, f'Wave clienti — {datetime.now().strftime("%Y-%m-%d %H:%M")} UTC')

    # Salva clienti.json aggiornato (solo in produzione)
    if not test_mode and sent_log:
        _gh_sha_cache[DATA_PATH] = db_sha
        ok = gh_put(DATA_PATH, db,
                    f'Wave clienti {len(sent_log)} email — {datetime.now().strftime("%Y-%m-%d %H:%M")} UTC')
        if ok:
            print('✓ clienti.json aggiornato su GitHub')
        else:
            print('⚠ Errore salvataggio clienti.json')

    if test_mode:
        print(f'\n🧪 Test: {len(sent_log)} email → {BCC_EMAIL}. Niente salvato.')

    send_digest(sent_log, errors, test_mode, batch_size, total_remaining - len(sent_log))


if __name__ == '__main__':
    main()
