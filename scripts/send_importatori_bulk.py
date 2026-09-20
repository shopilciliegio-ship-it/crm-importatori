"""
Invio massivo (bulk) email — Importatori & Distributori — LATO SERVER
Siena Wine / Small Vineyards International

Sostituisce il vecchio invio massivo fatto dal browser (js/bulk.js), che girava
per tutta la durata del batch nel tab del browser: se il tab veniva chiuso (o
il laptop andava in sleep) prima che il salvataggio "debounced" su GitHub
scattasse, gli invii Brevo (già partiti, irreversibili) restavano senza
traccia nel CRM — vedi incidente 18-19/09/2026 (1230 email inviate e mai
salvate, recuperate a mano incrociando gli eventi Brevo).

Flusso:
  1. Il browser (confirmBulkSend in js/bulk.js) scrive data/bulk-job-importatori.json
     con {contactIds, templateIndex, subject, brand, delayMin, delayMax, status:'pending'}
     e lancia questo workflow via workflow_dispatch — poi può chiudersi tranquillamente.
  2. Questo script gira interamente su GitHub Actions: legge il job, invia le
     email una per una con lo stesso identico rendering del template usato dal
     browser (fillTplForContact / buildHtmlEmail in js/email.js, replicato qui),
     e salva lo stato progressivamente (ogni CHECKPOINT_EVERY invii, non solo a
     fine batch) — un crash a metà perde al massimo l'ultimo checkpoint, mai
     tutto il lavoro fatto fino a quel momento.
  3. A fine invio manda un'email di resoconto e marca il job come 'done'.
"""

import base64
import html
import json
import os
import random
import re
import time
from datetime import datetime, timezone

import requests

# ── Config ────────────────────────────────────────────────────────────────────
BREVO_API_KEY = os.environ['BREVO_API_KEY']
GH_TOKEN      = os.environ['GH_TOKEN']
GH_REPO       = os.environ['GH_REPO']

BASE_PATH      = 'data/contatti.json'
OVERRIDES_PATH = 'data/contatti-overrides.json'
TEMPLATES_PATH = 'data/templates.json'
SETTINGS_PATH  = 'data/crm-settings.json'
JOB_PATH       = 'data/bulk-job-importatori.json'

BCC_EMAIL        = 'hokutazzo@gmail.com'
DIGEST_RECIPIENT = 'luca@ilciliegio.com'

CHECKPOINT_EVERY = 25  # invii tra un salvataggio incrementale e l'altro

_GH_HEADERS = {
    'Authorization': f'token {GH_TOKEN}',
    'Accept':        'application/vnd.github.v3+json',
}
_BREVO_HEADERS = {
    'api-key':      BREVO_API_KEY,
    'Content-Type': 'application/json',
    'Accept':       'application/json',
}

# ── Job title priority — stesso identico dizionario di JOB_PRIORITY in js/contacts.js ──
JOB_PRIORITY = {
    1: ['sales manager', 'buyer', 'purchasing manager', 'managing partner', 'sales representative', 'sales director', 'commercial director', 'sales', 'commercial', 'commercial manager', 'wine buyer', 'senior buyer', 'purchasing', 'import manager', 'sales consultant', 'regional sales manager', 'product manager', 'area sales manager', 'marketing manager', 'purchasing director', 'wine manager', 'purchaser', 'national sales manager', 'head of sales', 'buying manager', 'wine sales specialist', 'director of sales', 'wine sales', 'purchase manager', 'buying director', 'general sales manager', 'wine importer'],
    2: ['managing director', 'manager', 'director', 'general manager', 'administrator', 'in charge', 'operations manager', 'wine merchant', 'representative', 'chief executive officer', 'account manager', 'executive director', 'business owner', 'co-founder', 'representative director', 'general director', 'director of operations', 'president & ceo', 'wine director', 'sales specialist', 'wine sales representative', 'procurement manager', 'logistics manager', 'owner/ manager', 'co-owner', 'operation manager', 'senior brand manager', 'chief operating officer', 'regional manager', 'sales assistant', 'sales agent', 'ceo & founder', 'junior buyer', 'portfolio manager', 'area manager', 'senior sales manager', 'founder and ceo', 'business manager', 'managing director/ owner'],
    3: ['owner', 'ceo', 'president', 'founder', 'co-owner', 'sommelier', 'partner', 'co-founder', 'wine consultant', 'brand manager', 'store manager', 'business development manager', 'category manager', 'key account manager', 'wine specialist', 'vice president', 'sales associate', 'president and ceo', 'sales executive', 'administrative', 'administrative manager', 'brand ambassador', 'administrative assistant'],
}

BRANDS = {
    'sienawine': {
        'name': 'Siena Wine', 'senderEmail': 'luca@sienawine.it',
        'senderName': 'Luca Pattaro | Siena Wine Srl',
        'logoUrl': 'https://shopilciliegio-ship-it.github.io/crm-importatori/assets/logo_sienawine.png',
        'logoAlt': 'Siena Wine', 'logoWidth': '160',
        'accentColor': '#8B1A1A', 'bgColor': '#1a1a1a',
        'website': 'https://www.sienawine.it', 'phone': '+39 331 1347899',
        'tagline': 'Siena Wine: Pleasure in a bottle',
    },
    'ciliegio': {
        'name': 'Il Ciliegio', 'senderEmail': 'luca@sienawine.it',
        'senderName': 'Il Ciliegio — Azienda Agricola',
        'logoUrl': 'https://shopilciliegio-ship-it.github.io/crm-importatori/assets/logo_ciliegio.png',
        'logoAlt': 'Il Ciliegio — Azienda Agricola', 'logoWidth': '180',
        'accentColor': '#B8941A', 'bgColor': '#2c2c2c',
        'website': 'https://www.ilciliegio.com', 'phone': '+39 331 1347899',
        'tagline': 'Vini artigianali toscani di eccellenza',
    },
}


# ── GitHub helpers (stesso pattern di send_importatori_followup.py) ───────────

def _gh_request(method: str, url: str, **kwargs):
    for attempt in range(3):
        r = requests.request(method, url, **kwargs)
        if r.status_code in (502, 503, 504) and attempt < 2:
            time.sleep(2 ** attempt)
            continue
        return r


def gh_get(path: str):
    url = f'https://api.github.com/repos/{GH_REPO}/contents/{path}'
    r = _gh_request('GET', url, headers=_GH_HEADERS)
    if r.status_code == 404:
        return {}, None
    r.raise_for_status()
    data = r.json()
    sha  = data['sha']
    raw  = data.get('content') or ''
    if not raw and data.get('download_url'):
        rr = _gh_request('GET', data['download_url'])
        rr.raise_for_status()
        return rr.json(), sha
    if not raw:
        return {}, sha
    return json.loads(base64.b64decode(raw).decode('utf-8')), sha


def gh_put(path: str, data, sha, message: str):
    url     = f'https://api.github.com/repos/{GH_REPO}/contents/{path}'
    content = base64.b64encode(
        json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    ).decode('utf-8')
    body = {'message': message, 'content': content}
    if sha:
        body['sha'] = sha
    r = _gh_request('PUT', url, headers=_GH_HEADERS, json=body)
    r.raise_for_status()
    return r.json()['content']['sha']


def get_sha(path: str):
    r = _gh_request('GET', f'https://api.github.com/repos/{GH_REPO}/contents/{path}',
                     headers=_GH_HEADERS)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()['sha']


def load_contacts_with_overrides():
    base_raw, _ = gh_get(BASE_PATH)
    contacts = base_raw.get('contacts', []) if isinstance(base_raw, dict) else base_raw

    base_snap = {}
    for c in contacts:
        base_snap[c['id']] = {
            'status':      c.get('status') or '',
            'notes':       c.get('notes') or '',
            'log':         json.dumps(c.get('log') or [], ensure_ascii=False),
            'brevoEvents': json.dumps(c.get('brevoEvents') or [], ensure_ascii=False),
            'research':    json.dumps(c.get('research'), ensure_ascii=False),
        }

    overrides, _ = gh_get(OVERRIDES_PATH)
    if not isinstance(overrides, dict):
        overrides = {}
    by_id = {c['id']: c for c in contacts}
    for cid, changes in overrides.items():
        if cid in by_id:
            by_id[cid].update(changes)

    return contacts, by_id, base_snap


def build_overrides_diff(contacts, base_snap):
    new_ov = {}
    for c in contacts:
        snap = base_snap.get(c['id'])
        if not snap:
            continue
        diff = {}
        if (c.get('status') or '') != snap['status']:
            diff['status'] = c.get('status')
        if (c.get('notes') or '') != snap['notes']:
            diff['notes'] = c.get('notes')
        if json.dumps(c.get('log') or [], ensure_ascii=False) != snap['log']:
            diff['log'] = c.get('log') or []
        if json.dumps(c.get('brevoEvents') or [], ensure_ascii=False) != snap['brevoEvents']:
            diff['brevoEvents'] = c.get('brevoEvents') or []
        if json.dumps(c.get('research'), ensure_ascii=False) != snap['research']:
            diff['research'] = c.get('research')
        if diff:
            new_ov[c['id']] = diff
    return new_ov


def save_overrides_checkpoint(contacts, base_snap, overrides_loaded_count, label):
    new_overrides = build_overrides_diff(contacts, base_snap)
    new_count     = len(new_overrides)
    if overrides_loaded_count >= 10 and new_count < overrides_loaded_count * 0.5:
        print(f'    ✗ Crollo sospetto override: {overrides_loaded_count} → {new_count}. '
              f'Checkpoint "{label}" NON salvato per sicurezza.')
        return False
    fresh_sha = get_sha(OVERRIDES_PATH)
    gh_put(OVERRIDES_PATH, new_overrides, fresh_sha, f'Bulk importatori — checkpoint {label}')
    print(f'    ✓ Checkpoint "{label}" salvato ({new_count} contatti con override)')
    return True


def save_job(job):
    sha = get_sha(JOB_PATH)
    gh_put(JOB_PATH, job, sha, f'Bulk importatori — job {job.get("status")}')


# ── Rendering — replica esatta di selectBestContact/fillTplForContact/buildHtmlEmail (js/email.js) ──

def _priority_score(title: str) -> int:
    if not title:
        return 99
    t = title.lower()
    for p, titles in JOB_PRIORITY.items():
        if any(pt in t or t in pt for pt in titles):
            return p
    return 98


def select_best_contact(contacts):
    scored = sorted(
        ({**c, 'score': _priority_score(c.get('title'))} for c in (contacts or []) if c.get('name') or c.get('email')),
        key=lambda c: c['score']
    )
    if not scored:
        return None, None
    primary = scored[0]
    secondary = None
    if primary['score'] <= 1:
        secondary = next((c for c in scored if c is not primary and c['score'] >= 2), None)
    elif primary['score'] <= 2:
        secondary = next((c for c in scored if c is not primary and c['score'] >= 3), None)
    return primary, secondary


def first_name(full: str) -> str:
    return (full or '').strip().split()[0] if (full or '').strip() else ''


def fill_tpl_for_contact(body: str, c: dict) -> str:
    primary, secondary = select_best_contact(c.get('contacts'))
    dear_line = (f"Esteemed {c.get('company','')} Team,"
                 if not primary or not primary.get('name')
                 else f"Dear {first_name(primary['name'])} from {c.get('company','')},")
    owner_mention = (f" — and after seeing what you and {first_name(secondary['name'])} have built"
                      if secondary and secondary.get('name') else '')
    know_well = (f"This is something you and {first_name(secondary['name'])} know very well."
                  if secondary and secondary.get('name') else 'This is something you know very well.')
    primary_name  = first_name(primary.get('name') or c.get('contactName') or '') if primary else ''
    primary_title = (primary.get('title') if primary else '') or c.get('contactTitle') or ''
    owner_fn      = first_name(secondary.get('name','')) if secondary else ''
    clienti_first = c.get('nome') or first_name(c.get('name') or '')

    ctx = {
        'dear': dear_line, 'owner_mention': owner_mention, 'know_well': know_well,
        'owner': owner_fn,
        'contatto': primary_name or c.get('contactName') or clienti_first,
        'nome': primary_name or c.get('name') or clienti_first,
        'name': clienti_first or primary_name or c.get('name') or '',
        'firstName': clienti_first or primary_name or '',
        'job': primary_title,
        'azienda': c.get('company') or '',
        'paese': c.get('country') or '',
        'citta': c.get('city') or '',
        'prodotti': ', '.join(c.get('products') or []),
    }
    out = body or ''
    for k, v in ctx.items():
        out = out.replace('{{' + k + '}}', str(v))
    return out


_LABELED_URL_RE = re.compile(r'\[([^\]]+)\]\((https?://[^\s)]+)\)')
_URL_RE         = re.compile(r'(https?://[^\s<]+|(?:www\.|calendly\.com/)[^\s<]+)')
_BULLET_RE      = re.compile(r'^[•\-]\s*')


def _linkify(text: str, accent: str) -> str:
    placeholders = []

    def _repl_labeled(m):
        label, url = m.group(1), m.group(2)
        placeholders.append(f'<a href="{url}" style="color:{accent};font-weight:600;text-decoration:none">{label}</a>')
        return f'@@LINK{len(placeholders)-1}@@'
    text = _LABELED_URL_RE.sub(_repl_labeled, text)

    def _repl_bare(m):
        url = m.group(1)
        href = url if url.startswith('http') else 'https://' + url
        return f'<a href="{href}" style="color:{accent};font-weight:600;text-decoration:none">{url}</a>'
    text = _URL_RE.sub(_repl_bare, text)
    return re.sub(r'@@LINK(\d+)@@', lambda m: placeholders[int(m.group(1))], text)


def build_html_email(body: str, brand: str) -> str:
    b = BRANDS.get(brand, BRANDS['sienawine'])
    paras = [p.strip() for p in body.split('\n\n') if p.strip()]
    parts = []
    for p in paras:
        lines = p.split('\n')
        if p.startswith('•') or '\n•' in p:
            items = [l.strip() for l in lines if l.strip()]
            accent = b['accentColor']
            lis = ''.join(
                '<li style="margin-bottom:6px;color:#333;font-size:15px;line-height:1.6">'
                f'{_linkify(html.escape(_BULLET_RE.sub("", i)), accent)}</li>'
                for i in items
            )
            parts.append(f'<ul style="margin:0 0 16px;padding-left:20px">{lis}</ul>')
        else:
            esc = _linkify(html.escape(p), b['accentColor']).replace('\n', '<br>')
            parts.append(f'<p style="margin:0 0 16px;color:#333;font-size:15px;line-height:1.7">{esc}</p>')
    body_html = ''.join(parts)
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f0;font-family:Georgia,'Times New Roman',serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f0;padding:32px 16px">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
  <tr><td style="background:{b['bgColor']};border-radius:12px 12px 0 0;padding:32px;text-align:center">
    <img src="{b['logoUrl']}" width="{b['logoWidth']}" alt="{b['logoAlt']}" style="display:block;margin:0 auto;max-width:{b['logoWidth']}px">
  </td></tr>
  <tr><td style="background:{b['accentColor']};height:4px;font-size:0">&nbsp;</td></tr>
  <tr><td style="background:#ffffff;padding:40px 48px">{body_html}</td></tr>
  <tr><td style="background:{b['accentColor']};height:3px;font-size:0">&nbsp;</td></tr>
  <tr><td style="background:{b['bgColor']};border-radius:0 0 12px 12px;padding:28px 40px;text-align:center">
    <p style="margin:0 0 8px;color:#ffffff;font-size:13px;font-weight:bold;letter-spacing:1px;text-transform:uppercase">{b['name']}</p>
    <p style="margin:0 0 12px;color:{b['accentColor']};font-size:12px;font-style:italic">{b['tagline']}</p>
    <p style="margin:0;font-size:12px;color:#999;line-height:1.8">
      <a href="{b['website']}" style="color:#ccc;text-decoration:none">{b['website'].replace('https://','')}</a>&nbsp;|&nbsp;<span style="color:#999">{b['phone']}</span>
    </p>
  </td></tr>
</table>
</td></tr>
</table>
</body></html>"""


# ── Brevo send ────────────────────────────────────────────────────────────────

def send_via_brevo(contact_id: str, to_email: str, to_name: str, subject: str,
                    body_text: str, brand: str, test_mode: bool):
    b = BRANDS.get(brand, BRANDS['sienawine'])
    actual_to      = BCC_EMAIL if test_mode else to_email
    actual_to_name = 'Hokutazzo (test)' if test_mode else (to_name or to_email or '')
    actual_subject = f'[TEST → {to_email}] {subject}' if test_mode else subject

    payload = {
        'sender':      {'name': b['senderName'], 'email': b['senderEmail']},
        'to':          [{'email': actual_to, 'name': actual_to_name}],
        'subject':     actual_subject,
        'htmlContent': build_html_email(body_text, brand),
        'textContent': body_text,
        'tags':        ['wine-crm', brand] + (['test'] if test_mode else []),
        'headers':     {'X-CRM-ContactId': contact_id},
    }
    r = requests.post('https://api.brevo.com/v3/smtp/email', headers=_BREVO_HEADERS, json=payload)
    if r.ok:
        return r.json().get('messageId')
    print(f'    ✗ Brevo {r.status_code}: {r.text[:150]}')
    return None


# ── Digest finale ──────────────────────────────────────────────────────────────

def send_completion_digest(job, sent, failed, skipped):
    now_str = datetime.now().strftime('%d/%m/%Y %H:%M')
    total = job.get('progress', {}).get('total', sent + failed + skipped)
    html_content = f"""<!DOCTYPE html><html lang="it">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f4f0;font-family:Georgia,'Times New Roman',serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f0;padding:32px 16px">
<tr><td align="center"><table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
  <tr><td style="background:#2c2c2c;padding:20px 32px;text-align:center">
    <span style="color:#fff;font-size:16px;font-weight:700">Invio massivo Importatori</span>
  </td></tr>
  <tr><td style="background:#8B1A1A;height:4px;font-size:0">&nbsp;</td></tr>
  <tr><td style="background:#fff;padding:32px 40px">
    <p style="margin:0 0 4px;color:#999;font-size:12px">{now_str}</p>
    <h2 style="margin:0 0 20px;color:#222;font-size:20px">✓ Invio completato — eseguito interamente sul server</h2>
    <table style="border-collapse:collapse">
      <tr><td style="padding:4px 12px 4px 0;color:#555">Totale contatti</td><td style="font-weight:bold">{total}</td></tr>
      <tr><td style="padding:4px 12px 4px 0;color:#555">✓ Inviate</td><td style="font-weight:bold;color:#27ae60">{sent}</td></tr>
      <tr><td style="padding:4px 12px 4px 0;color:#555">✗ Fallite</td><td style="font-weight:bold;color:#c0392b">{failed}</td></tr>
      <tr><td style="padding:4px 12px 4px 0;color:#555">— Saltate (email mancante)</td><td style="font-weight:bold">{skipped}</td></tr>
    </table>
  </td></tr>
</table></td></tr></table>
</body></html>"""
    requests.post('https://api.brevo.com/v3/smtp/email', headers=_BREVO_HEADERS, json={
        'sender':      {'name': 'Siena Wine CRM', 'email': 'luca@sienawine.it'},
        'to':          [{'email': DIGEST_RECIPIENT, 'name': 'Luca'}],
        'subject':     f'✓ Invio massivo importatori completato — {sent}/{total}',
        'htmlContent': html_content,
        'textContent': f'Invio massivo importatori: {sent} inviate, {failed} fallite, {skipped} saltate su {total}.',
        'tags':        ['wine-crm', 'importatori-bulk-digest'],
    })


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print('=== Invio massivo Importatori — lato server ===')

    job, job_sha = gh_get(JOB_PATH)
    if not job or not isinstance(job, dict) or not job.get('contactIds'):
        print('Nessun job pendente in data/bulk-job-importatori.json — esco.')
        return

    if job.get('status') == 'done':
        print('Job già completato in precedenza — esco (evito doppio invio).')
        return
    if job.get('status') == 'running':
        started = job.get('startedAt') or 0
        age_min = (int(datetime.now(timezone.utc).timestamp() * 1000) - started) / 60000
        if age_min < 120:
            print(f'Job già "running" da {age_min:.0f} min — probabile esecuzione concorrente, esco per sicurezza.')
            return
        print(f'Job "running" da {age_min:.0f} min (>2h, probabile esecuzione interrotta) — riprendo.')

    settings, _ = gh_get(SETTINGS_PATH)
    # Il job può forzare il test mode indipendentemente dall'impostazione globale
    # (usato per verificare l'infrastruttura senza toccare i contatti reali)
    test_mode = bool(job['testMode']) if 'testMode' in job else settings.get('testModeImportatori', True)
    print('🧪 TEST MODE' if test_mode else '👥 Produzione — email reali')

    contacts, by_id, base_snap = load_contacts_with_overrides()
    overrides_loaded_count = len(build_overrides_diff(contacts, base_snap))  # baseline, non usato per il guard iniziale

    tpls_raw, _ = gh_get(TEMPLATES_PATH)
    templates = tpls_raw if isinstance(tpls_raw, list) else []
    tpl = templates[job.get('templateIndex', 0)] if templates else None
    if not tpl:
        print('✗ Template non trovato — esco.')
        job['status'] = 'error'
        job['error'] = 'template non trovato'
        save_job(job)
        return

    subject_tpl = job.get('subject') or tpl.get('subject', '')
    body_tpl    = tpl.get('body', '')
    brand       = job.get('brand', 'sienawine')
    delay_min   = float(job.get('delayMin', 1))
    delay_max   = float(job.get('delayMax', 2))

    target_ids = [cid for cid in job['contactIds'] if cid in by_id]
    total = len(target_ids)
    print(f'Contatti nel job: {len(job["contactIds"])} (validi: {total})')

    job['status']    = 'running'
    job['startedAt'] = int(datetime.now(timezone.utc).timestamp() * 1000)
    job.setdefault('progress', {})
    job['progress'].update({'sent': 0, 'failed': 0, 'skipped': 0, 'total': total})
    save_job(job)

    # base_snap va ricalcolato DOPO aver marcato il job 'running' (nessun contatto
    # tocco ancora, va bene riusare quello di load_contacts_with_overrides sopra)
    overrides_current, _ = gh_get(OVERRIDES_PATH)
    overrides_loaded_count = len(overrides_current) if isinstance(overrides_current, dict) else 0

    sent = failed = skipped = 0
    since_checkpoint = 0

    for i, cid in enumerate(target_ids):
        c = by_id[cid]
        to_email = (c.get('contactEmail') or c.get('email') or '').strip()
        to_name  = c.get('contactName') or c.get('name') or ''
        if not to_email:
            skipped += 1
            continue

        subject = fill_tpl_for_contact(subject_tpl, c)
        body    = fill_tpl_for_contact(body_tpl, c)
        msg_id  = send_via_brevo(cid, to_email, to_name, subject, body, brand, test_mode)

        if msg_id:
            if not test_mode:
                was_new = c.get('status') in (None, '', 'new')
                if was_new or c.get('status') == 'followup':
                    c['status'] = 'sent'
                c['updatedAt'] = int(datetime.now(timezone.utc).timestamp() * 1000)
                c.setdefault('log', []).append({
                    'ts': c['updatedAt'],
                    'msg': f'📧 Email inviata via Brevo (bulk server) — "{subject}" (ID: {msg_id})',
                })
                c['emailsSent'] = (c.get('emailsSent') or 0) + 1
                c.setdefault('brevoEvents', []).append({
                    'messageId': msg_id, 'subject': subject, 'sentAt': c['updatedAt'],
                    'toEmail': to_email, 'toName': to_name, 'brand': brand,
                    'sequenceStep': len(c.get('brevoEvents', [])) + 1,
                    'delivered': False, 'opened': False, 'clicked': False,
                    'bounced': False, 'spam': False, 'unsubscribed': False, 'blocked': False,
                })
            sent += 1
        else:
            failed += 1

        since_checkpoint += 1
        print(f'  [{i+1}/{total}] {c.get("company","?")} → {"✓" if msg_id else "✗"}')

        if since_checkpoint >= CHECKPOINT_EVERY:
            save_overrides_checkpoint(contacts, base_snap, overrides_loaded_count,
                                       label=f'{i+1}/{total}')
            job['progress'].update({'sent': sent, 'failed': failed, 'skipped': skipped})
            save_job(job)
            since_checkpoint = 0

        if i < total - 1:
            time.sleep(random.uniform(delay_min, delay_max))

    # Checkpoint finale
    if not test_mode:
        save_overrides_checkpoint(contacts, base_snap, overrides_loaded_count, label='finale')

    job['status']     = 'done'
    job['finishedAt'] = int(datetime.now(timezone.utc).timestamp() * 1000)
    job['progress']   = {'sent': sent, 'failed': failed, 'skipped': skipped, 'total': total}
    save_job(job)

    print(f'\n✓ Completato: {sent} inviate, {failed} fallite, {skipped} saltate (su {total})')
    send_completion_digest(job, sent, failed, skipped)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'✗ Errore fatale: {e}')
        try:
            job, _ = gh_get(JOB_PATH)
            if isinstance(job, dict):
                job['status'] = 'error'
                job['error']  = str(e)
                save_job(job)
        except Exception:
            pass
        raise
