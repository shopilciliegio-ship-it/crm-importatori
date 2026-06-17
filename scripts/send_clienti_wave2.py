# -*- coding: utf-8 -*-
"""
send_clienti_wave2.py
=====================
Invia la wave2 di follow-up ai clienti privati già contattati con wave1.

- Filtra: waveStatus='wave1_sent', wave1 sentAt <= (ora - 120 giorni)
- Template: wave2_it (italiano) / wave2 (inglese), con fallback ai default
- Aggiorna waveStatus → 'wave2_sent'
- Invia digest a luca@ilciliegio.com

NOTA: sostituire i template placeholder nel CRM (id: 'wave2', 'wave2_it')
      prima di attivare la produzione.
"""

import html as _html
import json
import os
import re
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
BG_COLOR         = '#2c2c2c'
TAGLINE          = 'Vini artigianali toscani di eccellenza'
WEBSITE          = 'https://www.ilciliegio.com'
PHONE            = '+39 331 1347899'

BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')
GH_TOKEN      = os.environ.get('GH_TOKEN', '')
GH_OWNER      = os.environ.get('GH_OWNER', 'shopilciliegio-ship-it')
GH_REPO       = os.environ.get('GH_REPO', 'crm-importatori')

DEFAULT_BATCH_SIZE = 500

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
    raw = (c.get('country') or '').strip()
    return COUNTRY_CODE_TO_NAME.get(raw.lower(), raw)


def is_italian(c: dict) -> bool:
    raw = (c.get('country') or '').strip().lower()
    return raw in ('it', 'italia', 'italy')


def get_wave1_sent_at(c: dict) -> int | None:
    for e in c.get('emailsSent', []):
        if e.get('type') == 'wave1':
            return e.get('sentAt')
    return None


# ── DEFAULT TEMPLATE WAVE 2 (PLACEHOLDER) ────────────────────────────────────
DEFAULT_WAVE2_SUBJECT    = "[Il Ciliegio] Following up — how are you?"
DEFAULT_WAVE2_BODY       = """\
Dear {firstName},

[PLACEHOLDER — sostituire con il template wave2 nel CRM (id: wave2)]

Warm regards,
Luca Pattaro
Il Ciliegio — Azienda Agricola
Loc. Podere il Ciliegio, Siena (IT)
www.ilciliegio.com
"""

DEFAULT_WAVE2_SUBJECT_IT = "[Il Ciliegio] Come stai? Un saluto dalla Toscana"
DEFAULT_WAVE2_BODY_IT    = """\
Caro {firstName},

[SEGNAPOSTO — sostituire con il template wave2_it nel CRM (id: wave2_it)]

Cordiali saluti,
Luca Pattaro
Il Ciliegio — Azienda Agricola
Loc. Podere il Ciliegio, Siena (IT)
www.ilciliegio.com
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
    raw = d.get('content', '').replace('\n', '')
    if raw:
        import base64
        try:
            json_str = base64.b64decode(raw).decode('utf-8')
        except Exception:
            json_str = raw
    else:
        # File >1MB: GitHub non include content inline, usa download_url
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
        _, new_sha = gh_get(path)
        if new_sha:
            body['sha'] = new_sha
            r2 = requests.put(url, headers=_gh_headers(), json=body, timeout=30)
            return r2.status_code in (200, 201)
    print(f'  ✗ gh_put {path}: {r.status_code} {r.text[:120]}')
    return False


# ── EMAIL ────────────────────────────────────────────────────────────────────
def _linkify(text: str) -> str:
    # Sintassi tipo markdown [testo](url) — sostituita con un segnaposto di testo
    # semplice, altrimenti il passaggio successivo (URL nudi) ri-matcherebbe
    # l'URL già dentro l'href="" appena creato, generando HTML annidato e rotto
    placeholders = []

    def _make_md_link(m):
        label, url = m.group(1), m.group(2)
        placeholders.append(f'<a href="{url}" style="color:{ACCENT};font-weight:600;text-decoration:none">{label}</a>')
        return f'@@LINK{len(placeholders)-1}@@'
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', _make_md_link, text)

    # URL nudi rimasti — link automatico col testo dell'URL stesso
    def _make_link(m):
        url = m.group(0)
        href = url if url.startswith('http') else 'https://' + url
        return f'<a href="{href}" style="color:{ACCENT};font-weight:600;text-decoration:none">{url}</a>'
    text = re.sub(r'(https?://[^\s<]+|(?:www\.|calendly\.com/)[^\s<]+)', _make_link, text)

    return re.sub(r'@@LINK(\d+)@@', lambda m: placeholders[int(m.group(1))], text)


def build_html(text: str, subject: str) -> str:
    body_html = ''
    for para in text.strip().split('\n\n'):
        para = para.strip()
        if not para:
            continue
        if '\n•' in para or para.startswith('•'):
            items = [l.strip() for l in para.split('\n') if l.strip()]
            lis = ''.join(
                f'<li style="margin-bottom:6px;color:#333;font-size:15px;line-height:1.6">'
                f'{_linkify(_html.escape(i.lstrip("•- ")))}</li>'
                for i in items
            )
            body_html += f'<ul style="margin:0 0 16px;padding-left:20px">{lis}</ul>'
        else:
            escaped = _html.escape(para).replace('\n', '<br>')
            body_html += (
                f'<p style="margin:0 0 16px;color:#333;font-size:15px;line-height:1.7">'
                f'{_linkify(escaped)}</p>'
            )

    return f"""<!DOCTYPE html>
<html lang="it">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f0;font-family:Georgia,'Times New Roman',serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f0;padding:32px 16px">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">

  <!-- HEADER -->
  <tr><td style="background:{BG_COLOR};border-radius:12px 12px 0 0;padding:32px;text-align:center">
    <img src="{LOGO_URL}" width="180" alt="Il Ciliegio — Azienda Agricola"
      style="display:block;margin:0 auto;max-width:180px">
  </td></tr>

  <!-- DIVIDER -->
  <tr><td style="background:{ACCENT};height:4px;font-size:0">&nbsp;</td></tr>

  <!-- BODY -->
  <tr><td style="background:#ffffff;padding:40px 48px">
    {body_html}
  </td></tr>

  <!-- DIVIDER -->
  <tr><td style="background:{ACCENT};height:3px;font-size:0">&nbsp;</td></tr>

  <!-- FOOTER -->
  <tr><td style="background:{BG_COLOR};border-radius:0 0 12px 12px;padding:28px 40px;text-align:center">
    <p style="margin:0 0 8px;color:#ffffff;font-size:13px;font-weight:bold;letter-spacing:1px;text-transform:uppercase">Il Ciliegio</p>
    <p style="margin:0 0 12px;color:{ACCENT};font-size:12px;font-style:italic">{TAGLINE}</p>
    <p style="margin:0;font-size:12px;color:#999;line-height:1.8">
      <a href="{WEBSITE}" style="color:#cccccc;text-decoration:none">{WEBSITE.replace('https://','')}</a>
      &nbsp;|&nbsp;
      <span style="color:#999">{PHONE}</span>
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>"""


def send_email(to_email: str, to_name: str, subject: str, body: str,
               contact_id: str, test_mode: bool) -> str | None:
    if test_mode:
        actual_to   = BCC_EMAIL
        actual_subj = f'[TEST → {to_email}] {subject}'
        print(f'    🧪 TEST wave2 → {BCC_EMAIL} (reale: {to_email})')
    else:
        actual_to   = to_email
        actual_subj = subject
        print(f'    ✓ wave2 → {to_email}')

    payload = {
        'sender':      {'name': SENDER_NAME, 'email': SENDER_EMAIL},
        'to':          [{'email': actual_to, 'name': to_name}],
        'subject':     actual_subj,
        'textContent': body,
        'htmlContent': build_html(body, actual_subj),
        'tags':        ['wine-crm', 'clienti', 'wave2'] + (['test'] if test_mode else []),
        'headers':     {'X-CRM-ContactId': contact_id},
        'trackClicks': True,
        'trackOpens':  True,
    }

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
        for r in sent[:50]
    )
    body_html = f"""
    <div style="font-family:sans-serif;font-size:14px;color:#333;max-width:600px;margin:0 auto">
      <h2 style="color:{ACCENT}">📧 Digest clienti wave2 — {datetime.now().strftime('%d/%m/%Y')}</h2>
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
        'subject':     f'[CRM] Wave2 clienti: {len(sent)} email inviate — {datetime.now().strftime("%d/%m/%Y")}',
        'htmlContent': body_html,
        'tags':        ['wine-crm', 'digest', 'clienti', 'wave2'],
    }
    r = requests.post(
        'https://api.brevo.com/v3/smtp/email',
        headers=_BREVO_HEADERS,
        json=payload,
        timeout=20,
    )
    if r.ok:
        print(f'\n✓ Digest wave2 inviato a {DIGEST_RECIPIENT}')
    else:
        print(f'\n⚠ Digest wave2 non inviato: {r.status_code}')


# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print('=' * 50)
    print(f'send_clienti_wave2.py — {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
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

    # Filtra candidati wave2: wave1_sent + wave1 sentAt > 120 giorni fa
    excluded_countries  = set(settings.get('excludedCountriesClienti', []))
    now_ms              = int(datetime.now(timezone.utc).timestamp() * 1000)
    one_twenty_days_ms  = 120 * 24 * 3600 * 1000

    candidates = []
    for c in contacts:
        if c.get('waveStatus') != 'wave1_sent':
            continue
        if not c.get('email'):
            continue
        if c.get('blacklisted', False):
            continue
        if country_display_name(c) in excluded_countries:
            continue
        wave1_at = get_wave1_sent_at(c)
        if wave1_at is None:
            continue
        if wave1_at > (now_ms - one_twenty_days_ms):
            continue  # meno di 120 giorni fa — troppo presto
        candidates.append(c)

    # Ordina per wave1 sentAt ASC (oldest first)
    candidates.sort(key=lambda c: get_wave1_sent_at(c) or 0)

    total_remaining = len(candidates)
    batch = candidates[:batch_size]

    print(f'\nCandidati wave2 (>120gg da wave1): {total_remaining}')
    print(f'Batch questo run: {len(batch)} (max {batch_size})')
    print()

    if not batch:
        print('✓ Nessun contatto da inviare in questo batch.')
        send_digest([], 0, test_mode, batch_size, 0)
        return

    # Leggi template (dal DB o default) — IT e EN
    templates     = db.get('templates') or []
    wave2_tpl_en  = next((t for t in templates if t.get('id') == 'wave2'),    None)
    wave2_tpl_it  = next((t for t in templates if t.get('id') == 'wave2_it'), None)
    wave2_subj_en = wave2_tpl_en['subject'] if wave2_tpl_en else DEFAULT_WAVE2_SUBJECT
    wave2_body_en = wave2_tpl_en['body']    if wave2_tpl_en else DEFAULT_WAVE2_BODY
    wave2_subj_it = wave2_tpl_it['subject'] if wave2_tpl_it else DEFAULT_WAVE2_SUBJECT_IT
    wave2_body_it = wave2_tpl_it['body']    if wave2_tpl_it else DEFAULT_WAVE2_BODY_IT

    if not wave2_tpl_en:
        print('⚠ Template wave2 (EN) non trovato nel CRM — uso placeholder. Aggiungilo prima di produzione!')
    if not wave2_tpl_it:
        print('⚠ Template wave2_it (IT) non trovato nel CRM — uso placeholder. Aggiungilo prima di produzione!')

    # Mappa email → contatto per aggiornamento rapido
    contact_map = {c['email']: c for c in contacts}

    sent_log = []
    errors   = 0

    for c in batch:
        first_name = c.get('firstName') or c.get('nome') or c.get('company', '').split()[0] or 'friend'
        if is_italian(c):
            wave2_subj   = wave2_subj_it
            wave2_body_t = wave2_body_it
        else:
            wave2_subj   = wave2_subj_en
            wave2_body_t = wave2_body_en

        body = wave2_body_t.replace('{firstName}', first_name) \
                           .replace('{lastName}',  c.get('lastName', '')) \
                           .replace('{email}',     c.get('email', '')) \
                           .replace('{{nome}}',     first_name) \
                           .replace('{{name}}',     first_name) \
                           .replace('{{contatto}}', first_name)
        subj = wave2_subj.replace('{{nome}}', first_name).replace('{{name}}', first_name).replace('{{contatto}}', first_name)

        msg_id = send_email(
            to_email=c['email'],
            to_name=c.get('company', first_name),
            subject=subj,
            body=body,
            contact_id=c['id'],
            test_mode=test_mode,
        )

        if msg_id:
            sent_log.append({'name': c.get('company', ''), 'email': c['email'], 'msgId': msg_id})
            if not test_mode:
                contact_map[c['email']]['waveStatus'] = 'wave2_sent'
                if contact_map[c['email']].get('status') in (None, '', 'new', 'sent'):
                    contact_map[c['email']]['status'] = 'followup'
                es = contact_map[c['email']].get('emailsSent', [])
                if not isinstance(es, list):
                    es = []
                es.append({
                    'type':      'wave2',
                    'sentAt':    now_ms,
                    'messageId': msg_id,
                    'toEmail':   c['email'],
                })
                contact_map[c['email']]['emailsSent'] = es

                # brevoEvents: stesso formato usato da js/email.js — è da qui che
                # il Registro/Workflow, i badge e "Sync Brevo" leggono lo stato,
                # NON da emailsSent (che il resto del CRM non consulta mai).
                bev = contact_map[c['email']].get('brevoEvents', [])
                if not isinstance(bev, list):
                    bev = []
                bev.append({
                    'messageId':    msg_id,
                    'subject':      subj,
                    'sentAt':       now_ms,
                    'toEmail':      c['email'],
                    'toName':       c.get('company', first_name),
                    'brand':        'ilciliegio',
                    'sequenceStep': len(bev) + 1,
                    'delivered': False, 'opened': False, 'clicked': False,
                    'bounced': False, 'spam': False, 'unsubscribed': False, 'blocked': False,
                })
                contact_map[c['email']]['brevoEvents'] = bev
        else:
            errors += 1

        time.sleep(0.1)

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
                'module':    'clienti_wave2',
                'to':        entry['email'],
                'name':      entry['name'],
                'messageId': entry['msgId'],
            })
        gh_put(LOG_PATH, log, f'Wave2 clienti — {datetime.now().strftime("%Y-%m-%d %H:%M")} UTC')

    # Salva clienti.json aggiornato (solo in produzione)
    if not test_mode and sent_log:
        _gh_sha_cache[DATA_PATH] = db_sha
        ok = gh_put(DATA_PATH, db,
                    f'Wave2 clienti {len(sent_log)} email — {datetime.now().strftime("%Y-%m-%d %H:%M")} UTC')
        if ok:
            print('✓ clienti.json aggiornato su GitHub')
        else:
            print('⚠ Errore salvataggio clienti.json')

    if test_mode:
        print(f'\n🧪 Test: {len(sent_log)} email → {BCC_EMAIL}. Niente salvato.')

    send_digest(sent_log, errors, test_mode, batch_size, total_remaining - len(sent_log))


if __name__ == '__main__':
    main()
