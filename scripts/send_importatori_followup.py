"""
Invio follow-up email automatici — Importatori & Distributori
Siena Wine / Small Vineyards International

Sequenza:
  step1 = day0   → Template t1  (First Contact — inviato manualmente dal CRM)
  step2 = day7   → t2a (email #1 aperta) / t2b (non aperta)
  step3 = day21  → t3  (email #2 aperta) / t3b (non aperta)
  step4 = day35  → t4a (email #3 aperta) / t4b (non aperta) → status → cold
"""

import base64
import html
import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone

import requests

# ── Config ────────────────────────────────────────────────────────────────────
BREVO_API_KEY = os.environ['BREVO_API_KEY']
GH_TOKEN      = os.environ['GH_TOKEN']
GH_REPO       = os.environ['GH_REPO']

CRM_PATH       = 'data/crm.json'
TEMPLATES_PATH = 'data/templates.json'
SETTINGS_PATH  = 'data/crm-settings.json'
LOG_PATH       = 'data/email-log-importatori.json'

BCC_EMAIL        = 'hokutazzo@gmail.com'
DIGEST_RECIPIENT = 'luca@ilciliegio.com'

SENDER_NAME  = 'Luca Pattaro — Siena Wine'
SENDER_EMAIL = 'luca@sienawine.it'
LOGO_URL     = 'https://shopilciliegio-ship-it.github.io/crm-importatori/assets/logo_sienawine.png'
ACCENT       = '#8B1A1A'
BG           = '#2c2c2c'
WEBSITE      = 'www.sienawine.it'
PHONE        = '+39 331 1347899'

DAY_MS            = 24 * 3600 * 1000
ACTIVE_STATUSES   = {'sent', 'followup'}
TERMINAL_STATUSES = {'replied', 'client', 'cold', 'blacklisted'}

# Job title → priority (lower = more relevant as email target)
JOB_PRIORITY = {
    'buyer': 1, 'purchasing': 1, 'import manager': 1, 'wine buyer': 1,
    'sales': 2, 'account': 2, 'commercial': 2, 'export': 2,
    'director': 3, 'manager': 3, 'head': 3, 'vp': 3,
    'owner': 4, 'founder': 4, 'ceo': 4, 'president': 4, 'partner': 4,
}

_GH_HEADERS = {
    'Authorization': f'token {GH_TOKEN}',
    'Accept':        'application/vnd.github.v3+json',
}
_BREVO_HEADERS = {
    'api-key':      BREVO_API_KEY,
    'Content-Type': 'application/json',
    'Accept':       'application/json',
}


# ── GitHub helpers ────────────────────────────────────────────────────────────

def gh_get(path: str) -> tuple[dict | list, str | None]:
    url = f'https://api.github.com/repos/{GH_REPO}/contents/{path}'
    r = requests.get(url, headers=_GH_HEADERS)
    if r.status_code == 404:
        return {}, None
    r.raise_for_status()
    data    = r.json()
    content = base64.b64decode(data['content']).decode('utf-8')
    return json.loads(content), data['sha']


def gh_put(path: str, data, sha: str | None, message: str) -> None:
    url     = f'https://api.github.com/repos/{GH_REPO}/contents/{path}'
    content = base64.b64encode(
        json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    ).decode('utf-8')
    body = {'message': message, 'content': content}
    if sha:
        body['sha'] = sha
    requests.put(url, headers=_GH_HEADERS, json=body).raise_for_status()


# ── Contact helpers ────────────────────────────────────────────────────────────

def select_contact(c: dict) -> tuple[str, str]:
    """Returns (email, full_name) of the best contact for this company."""
    contacts = c.get('contacts') or []
    best, best_score = None, 999
    for ct in contacts:
        title = (ct.get('title') or '').lower()
        score = 99
        for kw, pri in JOB_PRIORITY.items():
            if kw in title:
                score = min(score, pri)
        if score < best_score and ct.get('email'):
            best_score, best = score, ct
    if best:
        return best['email'], best.get('name', '')
    return (c.get('contactEmail') or c.get('email', '')), (c.get('contactName') or c.get('name', ''))


def get_owner(c: dict, primary_email: str) -> str | None:
    """Returns owner first name if distinct from the primary contact."""
    for ct in (c.get('contacts') or []):
        title = (ct.get('title') or '').lower()
        if any(k in title for k in ('owner', 'founder', 'ceo', 'president', 'partner')):
            if ct.get('email') != primary_email:
                name = ct.get('name', '')
                return name.split()[0] if name else None
    return None


def first_name(full: str) -> str:
    return (full or '').strip().split()[0] if full else ''


# ── Template helpers ──────────────────────────────────────────────────────────

def find_tpl(templates: list, *ids, name_hint: str = '') -> dict | None:
    for id_ in ids:
        t = next((t for t in templates if t.get('id') == id_), None)
        if t:
            return t
    if name_hint:
        nh = name_hint.lower()
        t = next((t for t in templates if nh in (t.get('name') or '').lower()), None)
        if t:
            return t
    return None


def render_template(tpl: dict, c: dict) -> tuple[str, str]:
    to_email, to_name = select_contact(c)
    contact_fn = first_name(to_name)
    company    = c.get('company', '')
    owner_fn   = get_owner(c, to_email)

    if contact_fn:
        dear = f'Dear {contact_fn} from {company},' if company else f'Dear {contact_fn},'
    else:
        dear = f'Dear {company} team,' if company else 'Dear Sir/Madam,'

    know_well      = (f'This is something you and {owner_fn} know very well.' if owner_fn else '')
    owner_mention  = (f' — and after seeing what you and {owner_fn} have built' if owner_fn else '')
    prodotti       = c.get('prodType') or ', '.join(c.get('products') or [])

    ctx = {
        'dear': dear, 'know_well': know_well, 'owner_mention': owner_mention,
        'owner': owner_fn or '', 'contatto': contact_fn,
        'azienda': company, 'paese': c.get('country', ''), 'citta': c.get('city', ''),
        'prodotti': prodotti,
    }

    subject = tpl.get('subject', '')
    body    = tpl.get('body', '')
    for k, v in ctx.items():
        subject = subject.replace('{{' + k + '}}', str(v))
        body    = body.replace('{{' + k + '}}', str(v))

    return subject, body


# ── HTML email builder ────────────────────────────────────────────────────────

def _body_to_html(plain: str) -> str:
    paras = [p.strip() for p in plain.split('\n\n') if p.strip()]
    parts = []
    for p in paras:
        lines  = p.split('\n')
        bulls  = [l for l in lines if l.strip().startswith('•')]
        others = [l for l in lines if not l.strip().startswith('•')]
        if bulls and len(bulls) >= len(others):
            if others:
                intro = html.escape(' '.join(others))
                parts.append(f'<p style="margin:0 0 8px;color:#333;font-size:15px;line-height:1.7">{intro}</p>')
            items = ''.join(
                f'<li style="color:#333;font-size:14px;line-height:1.8;padding:1px 0">'
                f'{html.escape(l.lstrip("• ").strip())}</li>'
                for l in bulls
            )
            parts.append(f'<ul style="margin:0 0 16px;padding-left:20px">{items}</ul>')
        else:
            escaped = html.escape(p).replace('\n', '<br>')
            parts.append(
                f'<p style="margin:0 0 16px;color:#333;font-size:15px;line-height:1.7">{escaped}</p>'
            )
    return ''.join(parts)


def build_html_email(body_text: str) -> str:
    body_html = _body_to_html(body_text)
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f0;font-family:Georgia,'Times New Roman',serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f0;padding:32px 16px">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
  <tr><td style="background:{BG};border-radius:12px 12px 0 0;padding:32px;text-align:center">
    <img src="{LOGO_URL}" width="180" alt="Siena Wine" style="display:block;margin:0 auto;max-width:180px">
  </td></tr>
  <tr><td style="background:{ACCENT};height:4px;font-size:0">&nbsp;</td></tr>
  <tr><td style="background:#ffffff;padding:40px 48px">{body_html}</td></tr>
  <tr><td style="background:{ACCENT};height:3px;font-size:0">&nbsp;</td></tr>
  <tr><td style="background:{BG};border-radius:0 0 12px 12px;padding:28px 40px;text-align:center">
    <p style="margin:0 0 8px;color:#ffffff;font-size:13px;font-weight:bold;letter-spacing:1px;text-transform:uppercase">Siena Wine</p>
    <p style="margin:0 0 12px;color:{ACCENT};font-size:12px;font-style:italic">Small Vineyards International</p>
    <p style="margin:0;font-size:12px;color:#999;line-height:1.8">
      <span style="color:#ccc">{WEBSITE}</span>&nbsp;|&nbsp;<span style="color:#999">{PHONE}</span>
    </p>
  </td></tr>
</table>
</td></tr>
</table>
</body></html>"""


# ── Brevo send ────────────────────────────────────────────────────────────────

def send_email(to_email: str, to_name: str, subject: str, body_text: str,
               contact_id: str, step: int, test_mode: bool = False) -> dict | None:
    if not to_email:
        print('    ⚠ email mancante, skip')
        return None

    if test_mode:
        actual_to   = BCC_EMAIL
        actual_subj = f'[TEST → {to_email}] {subject}'
        actual_bcc  = []
        print(f'    🧪 TEST step{step} → {BCC_EMAIL} (reale: {to_email})')
    else:
        actual_to   = to_email
        actual_subj = subject
        actual_bcc  = [{'email': BCC_EMAIL}]
        print(f'    ✓ step{step} → {to_email}')

    payload = {
        'sender':      {'name': SENDER_NAME, 'email': SENDER_EMAIL},
        'to':          [{'email': actual_to, 'name': to_name}],
        'subject':     actual_subj,
        'textContent': body_text,
        'htmlContent': build_html_email(body_text),
        'tags':        ['wine-crm', 'importatori', f'step{step}'] + (['test'] if test_mode else []),
        'headers':     {'X-CRM-ContactId': contact_id},
        'trackClicks': False,
        'trackOpens':  False,
    }
    if actual_bcc:
        payload['bcc'] = actual_bcc

    r = requests.post('https://api.brevo.com/v3/smtp/email', headers=_BREVO_HEADERS, json=payload)
    if r.ok:
        return r.json()
    print(f'    ✗ Brevo {r.status_code}: {r.text[:120]}')
    return None


# ── Brevo events sync ─────────────────────────────────────────────────────────

def sync_brevo_events(contacts: list, now_ms: int) -> int:
    updated = 0
    for c in contacts:
        for ev in (c.get('brevoEvents') or []):
            msg_id = ev.get('messageId')
            if not msg_id:
                continue
            if ev.get('bounced') or ev.get('spam') or ev.get('blocked') or ev.get('unsubscribed'):
                continue
            try:
                r = requests.get(
                    f'https://api.brevo.com/v3/smtp/statistics/events'
                    f'?messageId={requests.utils.quote(msg_id)}&limit=50',
                    headers=_BREVO_HEADERS, timeout=10,
                )
                if not r.ok:
                    continue
                changed = False
                for e in r.json().get('events', []):
                    etype = (e.get('event') or '').lower()
                    date  = e.get('date', '')
                    if etype in ('delivered', 'requests') and not ev.get('delivered'):
                        ev['delivered'] = True; ev['deliveredAt'] = date; changed = True
                    elif etype in ('opened', 'unique_opened') and not ev.get('opened'):
                        ev['opened'] = True; ev['openedAt'] = date; changed = True
                        c.setdefault('log', []).append({'ts': now_ms, 'msg': f'👁 Aperta: {ev.get("subject","")}'})
                    elif etype in ('clicks', 'click') and not ev.get('clicked'):
                        ev['clicked'] = True; ev['clickedAt'] = date; changed = True
                        c.setdefault('log', []).append({'ts': now_ms, 'msg': f'🔗 Click: {ev.get("subject","")}'})
                    elif etype in ('hardbounces', 'softbounces', 'bounced') and not ev.get('bounced'):
                        ev['bounced'] = True; ev['bouncedAt'] = date; changed = True
                    elif etype in ('spamreports', 'spam') and not ev.get('spam'):
                        ev['spam'] = True; changed = True
                    elif etype == 'unsubscribed' and not ev.get('unsubscribed'):
                        ev['unsubscribed'] = True; changed = True
                    elif etype in ('blocked', 'invalid') and not ev.get('blocked'):
                        ev['blocked'] = True; changed = True
                if changed:
                    updated += 1
                time.sleep(0.12)
            except Exception as e:
                print(f'    ⚠ sync error: {e}')
    return updated


# ── Follow-up logic ───────────────────────────────────────────────────────────

def get_ev_status(ev: dict) -> str:
    if not ev: return 'sent'
    if ev.get('manualStatus'): return ev['manualStatus']
    if ev.get('spam'):         return 'spam'
    if ev.get('bounced'):      return 'bounced'
    if ev.get('blocked'):      return 'blocked'
    if ev.get('unsubscribed'): return 'unsubscribed'
    if ev.get('clicked'):      return 'clicked'
    if ev.get('opened'):       return 'opened'
    if ev.get('delivered'):    return 'delivered'
    return 'sent'


def should_send_followup(c: dict, templates: list, now_ms: int) -> tuple[str | None, dict | None, int]:
    """Returns (step_label, template, next_step_number) or (None, None, 0)."""
    if c.get('status') in TERMINAL_STATUSES:
        return None, None, 0

    evs = sorted(c.get('brevoEvents') or [], key=lambda e: e.get('sentAt', 0))
    if not evs:
        return None, None, 0

    last_st = get_ev_status(evs[-1])
    if last_st in ('bounced', 'spam', 'unsubscribed', 'blocked') or \
       (evs[-1].get('manualStatus') in TERMINAL_STATUSES):
        return None, None, 0

    step1     = next((e for e in evs if (e.get('sequenceStep') or 1) == 1), evs[0])
    n_steps   = len(evs)
    days      = (now_ms - (step1.get('sentAt') or 0)) / DAY_MS

    if n_steps == 1 and days >= 7:
        if days > 14:
            print(f'    skip day7 — finestra scaduta ({days:.0f}gg)')
            return None, None, 0
        opened = step1.get('opened', False)
        tpl = find_tpl(templates, 't2a' if opened else 't2b')
        return 'day7', tpl, 2

    elif n_steps == 2 and days >= 21:
        if days > 31:
            print(f'    skip day21 — finestra scaduta ({days:.0f}gg)')
            return None, None, 0
        step2  = next((e for e in evs if (e.get('sequenceStep') or 0) == 2), evs[1])
        opened = step2.get('opened', False)
        tpl = find_tpl(templates, 't3a' if opened else 't3b')
        return 'day21', tpl, 3

    elif n_steps == 3 and days >= 35:
        if days > 50:
            print(f'    skip day35 — finestra scaduta ({days:.0f}gg)')
            return None, None, 0
        step3  = next((e for e in evs if (e.get('sequenceStep') or 0) == 3), evs[2])
        opened = step3.get('opened', False)
        tpl = find_tpl(templates, 't4a' if opened else 't4b')
        return 'day35', tpl, 4

    return None, None, 0


# ── Daily digest ──────────────────────────────────────────────────────────────

def send_daily_digest(contacts: list, log_new: list, now_ms: int,
                      test_mode: bool, sync_count: int) -> None:
    now_str   = datetime.now().strftime('%d/%m/%Y %H:%M')
    non_new   = [c for c in contacts if c.get('status') != 'new']
    counts    = Counter(c.get('status', '?') for c in non_new)
    STATUS_ORD = ['sent','followup','replied','client','cold','blacklisted']
    STATUS_EMJ = {'sent':'📤','followup':'🔄','replied':'💬','client':'🤝','cold':'❌','blacklisted':'🚫'}

    mode_badge = (
        '<span style="background:#e67e00;color:#fff;padding:2px 8px;border-radius:10px;'
        'font-size:11px;font-weight:bold">TEST MODE</span>' if test_mode else
        '<span style="background:#27ae60;color:#fff;padding:2px 8px;border-radius:10px;'
        'font-size:11px;font-weight:bold">PRODUZIONE</span>'
    )

    def _section(title: str, rows: list) -> str:
        if not rows:
            return (f'<h3 style="margin:24px 0 8px;color:#555;font-size:13px;'
                    f'text-transform:uppercase;letter-spacing:1px">{title}</h3>'
                    f'<p style="color:#999;font-size:13px;margin:0">Nessuno</p>')
        items = ''.join(f'<li style="padding:3px 0;color:#333;font-size:14px">{r}</li>' for r in rows)
        return (f'<h3 style="margin:24px 0 8px;color:#555;font-size:13px;'
                f'text-transform:uppercase;letter-spacing:1px">{title}</h3>'
                f'<ul style="margin:0;padding-left:20px">{items}</ul>')

    email_rows = [
        f'<b>{e["company"]}</b> → '
        f'<code style="background:#f0f0f0;padding:1px 5px;border-radius:3px">{e["type"]}</code>'
        for e in log_new
    ]
    status_table = ''.join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#555;font-size:14px">'
        f'{STATUS_EMJ.get(s,"•")} {s}</td>'
        f'<td style="padding:4px 0;font-weight:bold;font-size:14px;color:#333">{n}</td></tr>'
        for s, n in sorted(counts.items(), key=lambda x: STATUS_ORD.index(x[0]) if x[0] in STATUS_ORD else 99)
    )

    body_html = f"""
    <p style="margin:0 0 4px;color:#999;font-size:12px">{now_str} &nbsp;{mode_badge}</p>
    <h2 style="margin:0 0 20px;color:#222;font-size:20px;font-weight:bold">Importatori — Resoconto</h2>
    {_section(f'📧 Follow-up inviati ({len(log_new)})', email_rows)}
    <h3 style="margin:24px 0 8px;color:#555;font-size:13px;text-transform:uppercase;letter-spacing:1px">🔄 Sync Brevo: {sync_count} email aggiornate</h3>
    <h3 style="margin:24px 0 8px;color:#555;font-size:13px;text-transform:uppercase;letter-spacing:1px">📦 Contatti in sequenza ({len(non_new)})</h3>
    <table style="border-collapse:collapse"><tbody>{status_table}</tbody></table>
    """

    html_content = f"""<!DOCTYPE html><html lang="it">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f4f0;font-family:Georgia,'Times New Roman',serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f0;padding:32px 16px">
<tr><td align="center"><table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
  <tr><td style="background:{BG};border-radius:12px 12px 0 0;padding:20px 32px;text-align:center">
    <img src="{LOGO_URL}" width="140" alt="Siena Wine" style="display:block;margin:0 auto">
  </td></tr>
  <tr><td style="background:{ACCENT};height:4px;font-size:0">&nbsp;</td></tr>
  <tr><td style="background:#ffffff;padding:32px 40px">{body_html}</td></tr>
  <tr><td style="background:{ACCENT};height:3px;font-size:0">&nbsp;</td></tr>
  <tr><td style="background:{BG};border-radius:0 0 12px 12px;padding:16px 32px;text-align:center">
    <p style="margin:0;color:#999;font-size:11px">Siena Wine CRM — report automatico importatori</p>
  </td></tr>
</table></td></tr></table>
</body></html>"""

    r = requests.post('https://api.brevo.com/v3/smtp/email', headers=_BREVO_HEADERS, json={
        'sender':      {'name': SENDER_NAME, 'email': SENDER_EMAIL},
        'to':          [{'email': DIGEST_RECIPIENT, 'name': 'Luca'}],
        'subject':     f'📋 Importatori CRM — {now_str}',
        'htmlContent': html_content,
        'textContent': f'Importatori {now_str} | FU: {len(log_new)} | Sync: {sync_count} | In sequenza: {len(non_new)}',
        'tags':        ['wine-crm', 'importatori-digest'],
        'trackClicks': False,
        'trackOpens':  False,
    })
    if r.ok:
        print(f'✓ Digest importatori → {DIGEST_RECIPIENT}')
    else:
        print(f'⚠ Digest fallito: {r.status_code} {r.text[:100]}')


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print('=== Follow-up Importatori — Siena Wine ===')

    settings, _ = gh_get(SETTINGS_PATH)
    auto_send   = settings.get('emailAutoSendImportatori', False)
    test_mode   = settings.get('testModeImportatori', True)

    if not auto_send:
        print('⏸ Invio automatico importatori disabilitato. Nessuna email inviata.')
        send_daily_digest([], [], 0, test_mode, 0)
        return

    if test_mode:
        print(f'🧪 TEST MODE — email a {BCC_EMAIL}')
    else:
        print('👥 Produzione — email ai contatti reali')

    crm_raw,  sha_crm = gh_get(CRM_PATH)
    tpls_raw, _       = gh_get(TEMPLATES_PATH)

    contacts  = crm_raw.get('contacts', []) if isinstance(crm_raw, dict) else crm_raw
    templates = tpls_raw if isinstance(tpls_raw, list) else []

    if not templates:
        print('✗ templates.json non trovato. Esci.')
        return

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    active = [c for c in contacts if c.get('status') in ACTIVE_STATUSES]
    print(f'Contatti attivi (sent/followup): {len(active)} / {len(contacts)}')

    # ── 1. Sync Brevo events ──────────────────────────────────────────────────
    sync_count = 0
    if active:
        print('🔄 Sync eventi Brevo...')
        sync_count = sync_brevo_events(active, now_ms)
        print(f'  {sync_count} email aggiornate')

    # ── 2. Send follow-ups ────────────────────────────────────────────────────
    sent, cold_count, log_new = 0, 0, []

    for c in active:
        name     = c.get('company') or c.get('name', '?')
        to_email, to_name = select_contact(c)
        print(f'\n  {name} | status={c.get("status")} | evs={len(c.get("brevoEvents") or [])}')

        step_label, tpl, next_step = should_send_followup(c, templates, now_ms)
        if not step_label:
            continue
        if not tpl:
            print(f'    ⚠ template mancante per {step_label}')
            continue

        print(f'    → {step_label} | tpl={tpl.get("id","?")} "{tpl.get("name","")[:40]}"')
        subject, body = render_template(tpl, c)
        result = send_email(to_email, to_name, subject, body, c['id'], next_step, test_mode)

        if result:
            msg_id = result.get('messageId', '')
            ev_entry = {
                'messageId': msg_id, 'subject': subject, 'sentAt': now_ms,
                'toEmail': to_email if not test_mode else BCC_EMAIL,
                'toName': to_name, 'brand': 'sienawine', 'sequenceStep': next_step,
                'delivered': False, 'opened': False, 'clicked': False,
                'bounced': False, 'spam': False, 'unsubscribed': False,
                'blocked': False, 'manualStatus': None,
            }
            if not test_mode:
                c.setdefault('brevoEvents', []).append(ev_entry)
                c.setdefault('log', []).append({'ts': now_ms, 'msg': f'⚡ Auto {step_label}: "{tpl.get("name","")}"'})
                c['emailsSent'] = len(c.get('brevoEvents', []))
                c['status']     = 'cold' if step_label == 'day35' else 'followup'
                c['updatedAt']  = now_ms
                if step_label == 'day35':
                    c.setdefault('log', []).append({'ts': now_ms, 'msg': '❌ Sequenza completata → cold'})
                    cold_count += 1
            sent += 1
            log_new.append({'contactId': c['id'], 'company': name, 'type': step_label,
                            'to': to_email, 'subject': subject, 'sentAt': now_ms, 'messageId': msg_id})

        time.sleep(0.6)

    now_str = datetime.now().strftime('%d/%m/%Y %H:%M')

    if test_mode:
        print(f'\n🧪 Test: {sent} email → {BCC_EMAIL}. crm.json non modificato.')
    else:
        if sent > 0 or sync_count > 0:
            if isinstance(crm_raw, dict):
                crm_raw['contacts'] = contacts
                to_save = crm_raw
            else:
                to_save = contacts
            gh_put(CRM_PATH, to_save, sha_crm,
                   f'Follow-up importatori — {sent} email — {now_str}')
            print(f'\n✓ {sent} email inviate, crm.json aggiornato.')
            if cold_count:
                print(f'  {cold_count} contatti → cold (sequenza completata)')

        if log_new:
            log_raw, log_sha = gh_get(LOG_PATH)
            existing = log_raw.get('log', []) if isinstance(log_raw, dict) else []
            gh_put(LOG_PATH, {'log': existing + log_new}, log_sha,
                   f'Email log importatori — {len(log_new)} entries — {now_str}')
        elif sent == 0:
            print('\nNessun follow-up da inviare.')

    send_daily_digest(contacts, log_new, now_ms, test_mode, sync_count)


if __name__ == '__main__':
    main()
