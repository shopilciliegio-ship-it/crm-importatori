"""
Invio reminder email temporizzati — Il Ciliegio CRM
Eseguito dopo fetch_mbe_tracking.py nel workflow import_ordini.yml

Logica reminder:
  day0  → Conferma spedizione (tutti, appena shippingDate impostata)
  day10 → Reminder 10 giorni (Standard + Express)
  day20 → Reminder 20 giorni (solo Standard)

Notifiche immediate su cambio stato MBE:
  consegnato / dogana / problema → email appena compare, senza aspettare

Se shippingType mancante → skip day10/day20 con warning nel log.
"""

import base64
import html
import json
import os
from datetime import datetime, timezone

import requests

# ── Config ───────────────────────────────────────────────────────────────────
BREVO_API_KEY = os.environ['BREVO_API_KEY']
GH_TOKEN      = os.environ['GH_TOKEN']
GH_REPO       = os.environ['GH_REPO']

DATA_PATH      = 'data/ordini.json'
TEMPLATES_PATH = 'data/email-reminders-templates.json'
LOG_PATH       = 'data/email-log.json'

BCC_EMAIL = 'lucapattaro75@virgilio.it'

SENDER_NAME  = 'Il Ciliegio — Azienda Agricola'
SENDER_EMAIL = 'export@ilciliegio.com'
LOGO_URL     = 'https://shopilciliegio-ship-it.github.io/crm-importatori/assets/logo_ciliegio.png'
ACCENT       = '#B8941A'
BG           = '#2c2c2c'
WEBSITE      = 'www.ilciliegio.com'
PHONE        = '+39 331 1347899'
TAGLINE      = 'Vini artigianali toscani di eccellenza'

DAY_MS          = 24 * 3600 * 1000
STATI_TERMINALI = {'consegnato', 'annullato'}

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
    r   = requests.get(url, headers=_GH_HEADERS)
    if r.status_code == 404:
        return {}, None
    r.raise_for_status()
    data    = r.json()
    content = base64.b64decode(data['content']).decode('utf-8')
    return json.loads(content), data['sha']


def gh_put(path: str, data: dict, sha: str | None, message: str) -> None:
    url     = f'https://api.github.com/repos/{GH_REPO}/contents/{path}'
    content = base64.b64encode(
        json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    ).decode('utf-8')
    body = {'message': message, 'content': content}
    if sha:
        body['sha'] = sha
    requests.put(url, headers=_GH_HEADERS, json=body).raise_for_status()


# ── Template rendering ────────────────────────────────────────────────────────

def render_template(tpl: dict, order: dict) -> tuple[str, str]:
    nome     = (order.get('customerName') or '').split()[0] or order.get('customerName', '')
    tracking = order.get('trackingNumber', '') or ''
    tracking_line = f'Numero tracking: {tracking}\n' if tracking else ''

    ctx = {
        'nome':          nome,
        'tracking':      tracking,
        'tracking_line': tracking_line,
    }

    subject = tpl.get('subject', '')
    body    = tpl.get('body', '')
    for k, v in ctx.items():
        subject = subject.replace('{' + k + '}', str(v))
        body    = body.replace('{' + k + '}', str(v))

    return subject, body


# ── Email HTML builder ────────────────────────────────────────────────────────

def _body_to_html(plain: str) -> str:
    paras = [p.strip() for p in plain.split('\n\n') if p.strip()]
    parts = []
    for p in paras:
        escaped = html.escape(p).replace('\n', '<br>')
        parts.append(
            f'<p style="margin:0 0 16px;color:#333;font-size:15px;line-height:1.7">{escaped}</p>'
        )
    return ''.join(parts)


def build_html_email(body_text: str) -> str:
    body_html = _body_to_html(body_text)
    return f"""<!DOCTYPE html>
<html lang="it">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f0;font-family:Georgia,'Times New Roman',serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f0;padding:32px 16px">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
  <tr><td style="background:{BG};border-radius:12px 12px 0 0;padding:32px;text-align:center">
    <img src="{LOGO_URL}" width="180" alt="Il Ciliegio" style="display:block;margin:0 auto;max-width:180px">
  </td></tr>
  <tr><td style="background:{ACCENT};height:4px;font-size:0">&nbsp;</td></tr>
  <tr><td style="background:#ffffff;padding:40px 48px">{body_html}</td></tr>
  <tr><td style="background:{ACCENT};height:3px;font-size:0">&nbsp;</td></tr>
  <tr><td style="background:{BG};border-radius:0 0 12px 12px;padding:28px 40px;text-align:center">
    <p style="margin:0 0 8px;color:#ffffff;font-size:13px;font-weight:bold;letter-spacing:1px;text-transform:uppercase">Il Ciliegio</p>
    <p style="margin:0 0 12px;color:{ACCENT};font-size:12px;font-style:italic">{TAGLINE}</p>
    <p style="margin:0;font-size:12px;color:#999;line-height:1.8">
      <span style="color:#ccc">{WEBSITE}</span>&nbsp;|&nbsp;<span style="color:#999">{PHONE}</span>
    </p>
  </td></tr>
</table>
</td></tr>
</table>
</body></html>"""


# ── Brevo send ────────────────────────────────────────────────────────────────

def send_email(order: dict, reminder_type: str, subject: str, body_text: str,
               test_mode: bool = False) -> str | None:
    to_email = (order.get('customerEmail') or '').strip()
    if not to_email:
        print(f'    ⚠ {order.get("customerName","?")} — email cliente mancante, skip')
        return None

    if test_mode:
        actual_to   = BCC_EMAIL
        actual_subj = f'[TEST → {to_email}] {subject}'
        actual_bcc  = []
        print(f'    🧪 TEST "{reminder_type}" → {BCC_EMAIL} (reale: {to_email})')
    else:
        actual_to   = to_email
        actual_subj = subject
        actual_bcc  = [{'email': BCC_EMAIL}]
        print(f'    ✓ "{reminder_type}" → {to_email}')

    payload = {
        'sender':      {'name': SENDER_NAME, 'email': SENDER_EMAIL},
        'to':          [{'email': actual_to, 'name': order.get('customerName', '')}],
        'subject':     actual_subj,
        'textContent': body_text,
        'htmlContent': build_html_email(body_text),
        'tags':        ['wine-crm', 'ordini', reminder_type] + (['test'] if test_mode else []),
        'headers':     {'X-CRM-OrderId': order['id']},
    }
    if actual_bcc:
        payload['bcc'] = actual_bcc

    r = requests.post('https://api.brevo.com/v3/smtp/email', headers=_BREVO_HEADERS, json=payload)
    if r.ok:
        return r.json().get('messageId', '')
    print(f'    ✗ Brevo {r.status_code}: {r.text[:120]}')
    return None


# ── Logica reminder ───────────────────────────────────────────────────────────

def to_ms(value) -> int:
    """Converte shippingDate in millisecondi — accetta int, float, stringa numerica o 'YYYY-MM-DD'."""
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    try:
        return int(s)
    except ValueError:
        return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp() * 1000)


def sent_types(order: dict) -> set[str]:
    return {e.get('type', '') for e in (order.get('emailsSent') or [])}


def should_send(order: dict, reminder_type: str, now_ms: int) -> tuple[bool, str]:
    """Restituisce (va_inviato, motivo_skip)."""
    already       = sent_types(order)
    status        = order.get('status', '')
    shipping_type = order.get('shippingType')
    shipping_date = order.get('shippingDate')

    if reminder_type in already:
        return False, 'già inviata'

    if reminder_type == 'order_received':
        if status in STATI_TERMINALI or status == 'annullato':
            return False, f'ordine terminato ({status})'
        # Usa orderDate (data reale ordine), non createdAt (data import nel CRM)
        order_date = int(order.get('orderDate') or order.get('createdAt') or 0)
        days_old = (now_ms - order_date) / DAY_MS
        if days_old > 7:
            return False, f'ordine vecchio ({days_old:.0f}gg) — skip welcome'
        return True, ''

    if reminder_type == 'day0':
        if not shipping_date:
            return False, 'shippingDate mancante'
        return True, ''

    if reminder_type in ('day10', 'day20'):
        if status in STATI_TERMINALI or status == 'in_consegna':
            return False, f'già in consegna/terminato ({status}) — skip reminder temporizzato'
        if not shipping_date:
            return False, 'shippingDate mancante'

        days_since = (now_ms - to_ms(shipping_date)) / DAY_MS

        if shipping_type is None:
            return False, 'shippingType mancante — inserire nel CRM'

        threshold = 10 if reminder_type == 'day10' else 20
        if days_since < threshold:
            return False, f'troppo presto ({days_since:.1f}gg < {threshold}gg)'

        if reminder_type == 'day20' and shipping_type != 'standard':
            return False, f'day20 solo Standard (questo: {shipping_type})'

        return True, ''

    if reminder_type == 'consegnato':
        if status != 'consegnato':
            return False, f'status attuale è {status}'
        # Non inviare per spedizioni antecedenti al 13/05/2026
        ship_ms = to_ms(order.get('shippingDate') or order.get('orderDate'))
        cutoff  = 1747094400000  # 2026-05-13 00:00 UTC in ms
        if ship_ms and ship_ms < cutoff:
            return False, 'spedizione precedente al 13/05/2026 — skip'
        return True, ''

    if reminder_type in ('in_consegna', 'dogana', 'problema'):
        if status != reminder_type:
            return False, f'status attuale è {status}'
        return True, ''

    return False, 'tipo sconosciuto'


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print('=== Send Reminders — Il Ciliegio ===')

    settings, _ = gh_get('data/crm-settings.json')
    if not settings.get('emailAutoSend', False):
        print('⏸ Invio automatico email disabilitato (toggle OFF nel CRM). Nessuna email inviata.')
        return

    test_mode = settings.get('testMode', True)
    if test_mode:
        print(f'🧪 TEST MODE — email a {BCC_EMAIL}, niente salvato in emailsSent')
    else:
        print('👥 Produzione — email ai clienti reali, tutto registrato')

    db,        sha_db = gh_get(DATA_PATH)
    templates, _      = gh_get(TEMPLATES_PATH)

    if not templates:
        print('✗ Template non trovati in ' + TEMPLATES_PATH)
        print('  Salva i template dal CRM prima di eseguire questo script.')
        return

    orders  = db.get('orders') or []
    now_ms  = int(datetime.now(timezone.utc).timestamp() * 1000)

    # In test mode: pulisce entry order_received salvate erroneamente da run precedenti
    if test_mode:
        for o in orders:
            before = len(o.get('emailsSent') or [])
            o['emailsSent'] = [e for e in (o.get('emailsSent') or []) if e.get('type') != 'order_received']
            if len(o['emailsSent']) < before:
                o['updatedAt'] = now_ms

    active = [o for o in orders if o.get('status') not in ('ricevuto', 'preparazione', 'annullato')]
    print(f'Ordini attivi: {len(active)} / {len(orders)}')

    sent   = 0
    log_new = []

    def _record_send(order, rtype, to_email, subject, msg_id):
        """Salva in emailsSent solo in modalità produzione."""
        nonlocal sent
        entry = {
            'type':      rtype,
            'to':        to_email,
            'subject':   subject,
            'sentAt':    now_ms,
            'messageId': msg_id,
        }
        if not test_mode:
            order.setdefault('emailsSent', []).append(entry)
            order['updatedAt'] = now_ms
        sent += 1
        log_new.append({'orderId': order['id'], 'customerName': order.get('customerName', ''), **entry})

    # ── order_received: tutti gli ordini non annullati ────────────────────────
    for order in [o for o in orders if o.get('status') != 'annullato']:
        ok, reason = should_send(order, 'order_received', now_ms)
        if not ok:
            continue
        tpl = templates.get('order_received')
        if not tpl:
            continue
        subject, body = render_template(tpl, order)
        to_email = (order.get('customerEmail') or '').strip()
        msg_id = send_email(order, 'order_received', subject, body, test_mode)
        if msg_id:
            _record_send(order, 'order_received', to_email, subject, msg_id)

    # ── Reminder temporizzati e notifiche stato ───────────────────────────────
    for order in active:
        name   = order.get('customerName', '?')
        status = order.get('status', '')
        stype  = order.get('shippingType') or '?'
        print(f'\n  {name} | status={status} | type={stype}')

        for rtype in ['day0', 'day10', 'day20', 'in_consegna', 'consegnato', 'dogana', 'problema']:
            ok, reason = should_send(order, rtype, now_ms)
            if not ok:
                if reason != 'già inviata':
                    print(f'    {rtype}: skip — {reason}')
                continue
            tpl = templates.get(rtype)
            if not tpl:
                print(f'    {rtype}: template mancante')
                continue
            subject, body = render_template(tpl, order)
            to_email = (order.get('customerEmail') or '').strip()
            msg_id = send_email(order, rtype, subject, body, test_mode)
            if msg_id:
                _record_send(order, rtype, to_email, subject, msg_id)

    now_str = datetime.now().strftime('%d/%m/%Y %H:%M')

    if test_mode:
        print(f'\n🧪 Test completato: {sent} email inviate a {BCC_EMAIL}. Nessuna modifica a ordini.json.')
    else:
        if sent > 0:
            db['orders'] = orders
            gh_put(DATA_PATH, db, sha_db, f'Reminder email — {sent} inviate — {now_str}')
            log_data, log_sha = gh_get(LOG_PATH)
            existing = log_data.get('log', []) if isinstance(log_data, dict) else []
            gh_put(LOG_PATH, {'log': existing + log_new}, log_sha,
                   f'Email log — {len(log_new)} entries — {now_str}')
            print(f'\n✓ {sent} email inviate, ordini.json aggiornato.')
        else:
            print('\nNessuna email da inviare.')
        print(f'✓ email-log.json aggiornato ({len(log_new)} nuove righe).')
    else:
        print('\nNessuna email da inviare.')


if __name__ == '__main__':
    main()
