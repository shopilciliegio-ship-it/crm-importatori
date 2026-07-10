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
import re
import time
from datetime import datetime, timezone

import requests

# ── Config ───────────────────────────────────────────────────────────────────
BREVO_API_KEY = os.environ['BREVO_API_KEY']
GH_TOKEN      = os.environ['GH_TOKEN']
GH_REPO       = os.environ['GH_REPO']

DATA_PATH      = 'data/ordini.json'
TEMPLATES_PATH = 'data/email-reminders-templates.json'
LOG_PATH       = 'data/email-log.json'

BCC_EMAIL = 'hokutazzo@gmail.com'

SENDER_NAME  = 'Il Ciliegio — Azienda Agricola'
SENDER_EMAIL = 'luca@sienawine.it'
LOGO_URL     = 'https://shopilciliegio-ship-it.github.io/crm-importatori/assets/logo_ciliegio.png'
ACCENT       = '#B8941A'
BG           = '#2c2c2c'
WEBSITE      = 'www.ilciliegio.com'
PHONE        = '+39 331 1347899'
TAGLINE      = 'Vini artigianali toscani di eccellenza'

DAY_MS          = 24 * 3600 * 1000
STATI_TERMINALI = {'consegnato', 'annullato'}

STALE_THRESHOLD_DAYS = 7  # spedizione ferma (nessun cambio status) oltre questa soglia → alert

DIGEST_RECIPIENT = 'luca@ilciliegio.com'

# Lo script gira ogni 4h (import_ordini.yml) ma il digest deve partire una
# sola volta al giorno — solo al run delle DIGEST_HOUR_UTC:00 UTC.
DIGEST_HOUR_UTC = 8  # 10:00 in Italia (CEST)


def _is_digest_run() -> bool:
    return datetime.now(timezone.utc).hour == DIGEST_HOUR_UTC

_STATUS_ORDER = ['ricevuto','preparazione','spedito','in_transito','dogana','in_consegna','consegna_fallita','consegnato','problema','annullato']
_STATUS_EMOJI = {
    'ricevuto':    '📥', 'preparazione': '📦', 'spedito':     '🚀',
    'in_transito': '✈️',  'dogana':       '🛃', 'in_consegna': '🏠',
    'consegna_fallita': '📭',
    'consegnato':  '✅',  'problema':     '⚠️', 'annullato':   '❌',
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

def _gh_request(method: str, url: str, **kwargs):
    """Ritenta su 502/503/504 (errori transitori dei server GitHub) — max 3 tentativi."""
    for attempt in range(3):
        r = requests.request(method, url, **kwargs)
        if r.status_code in (502, 503, 504) and attempt < 2:
            time.sleep(2 ** attempt)
            continue
        return r


def gh_get(path: str) -> tuple[dict | list, str | None]:
    url = f'https://api.github.com/repos/{GH_REPO}/contents/{path}'
    r   = _gh_request('GET', url, headers=_GH_HEADERS)
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
    _gh_request('PUT', url, headers=_GH_HEADERS, json=body).raise_for_status()


# ── Template rendering ────────────────────────────────────────────────────────

def order_lang(order: dict) -> str:
    """Lingua email cliente — campo 'language' impostato all'import (da indirizzo
    di spedizione) o modificabile a mano dal CRM. Default inglese."""
    return order.get('language') or 'en'


def render_template(tpl: dict, order: dict) -> tuple[str, str]:
    lang        = order_lang(order)
    nome        = (order.get('customerName') or '').split()[0] or order.get('customerName', '')
    tracking    = order.get('trackingNumber', '') or ''
    tracking_url = order.get('trackingUrl', '') or ''
    track17_url = f'https://t.17track.net/en#nums={tracking}' if tracking else ''

    if lang == 'it':
        if tracking and tracking_url:
            tracking_line = f'Numero tracking: {tracking}\nTraccia la spedizione: {tracking_url}\n'
        elif tracking_url:
            tracking_line = f'Traccia la spedizione: {tracking_url}\n'
        elif tracking and track17_url:
            tracking_line = f'Numero tracking: {tracking} — {track17_url}\n'
        elif tracking:
            tracking_line = f'Numero tracking: {tracking}\n'
        else:
            tracking_line = ''
    else:
        if tracking and track17_url:
            tracking_line = f'Tracking number: {tracking} — {track17_url}\n'
        elif tracking:
            tracking_line = f'Tracking number: {tracking}\n'
        elif tracking_url:
            tracking_line = f'Track your shipment: {tracking_url}\n'
        else:
            tracking_line = ''

    ctx = {
        'nome':          nome,
        'tracking':      tracking,
        'tracking_line': tracking_line,
        'track17_url':   track17_url,
    }

    tpl_lang = tpl.get(lang) or tpl.get('en') or {}
    subject = tpl_lang.get('subject', '')
    body    = tpl_lang.get('body', '')
    for k, v in ctx.items():
        subject = subject.replace('{' + k + '}', str(v))
        body    = body.replace('{' + k + '}', str(v))

    return subject, body


# ── Email HTML builder ────────────────────────────────────────────────────────

_TRACK17_URL_RE = re.compile(r'(https://t\.17track\.net/en#nums=[A-Za-z0-9]+)')
_SPEDIRE_URL_RE = re.compile(r'(https://www\.spedire(?:pro)?\.com/tracking/[A-Za-z0-9]+)')

def _body_to_html(plain: str) -> str:
    paras = [p.strip() for p in plain.split('\n\n') if p.strip()]
    parts = []
    for p in paras:
        escaped = html.escape(p).replace('\n', '<br>')
        # Rende cliccabile il link 17Track (stato aggiornato in tempo reale)
        escaped = _TRACK17_URL_RE.sub(
            r'<a href="\1" style="color:#B8941A;font-weight:600;text-decoration:none">'
            r'🔗 Track your shipment live</a>',
            escaped
        )
        # Rende cliccabile il link Spedire.com tracking
        escaped = _SPEDIRE_URL_RE.sub(
            r'<a href="\1" style="color:#B8941A;font-weight:600;text-decoration:none">'
            r'🔗 Traccia la spedizione</a>',
            escaped
        )
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
        actual_bcc  = []
        print(f'    ✓ "{reminder_type}" → {to_email}')

    payload = {
        'sender':      {'name': SENDER_NAME, 'email': SENDER_EMAIL},
        'to':          [{'email': actual_to, 'name': order.get('customerName', '')}],
        'subject':     actual_subj,
        'textContent': body_text,
        'htmlContent': build_html_email(body_text),
        'tags':        ['wine-crm', 'ordini', reminder_type] + (['test'] if test_mode else []),
        'headers':     {'X-CRM-OrderId': order['id']},
        'trackClicks': False,
        'trackOpens':  False,
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


def order_fully_done(order: dict) -> bool:
    """True se l'ordine è consegnato e l'email 'consegnato' è già stata inviata:
    nessun reminder potrà mai più scattare, va escluso dal ciclo principale."""
    return order.get('status') == 'consegnato' and 'consegnato' in sent_types(order)


def should_send(order: dict, reminder_type: str, now_ms: int) -> tuple[bool, str]:
    """Restituisce (va_inviato, motivo_skip)."""
    already       = sent_types(order)
    status        = order.get('status', '')
    shipping_type = order.get('shippingType')
    shipping_date = order.get('shippingDate')

    if reminder_type in already:
        return False, 'già inviata'

    if reminder_type == 'order_received':
        if status not in ('ricevuto', 'preparazione'):
            return False, f'ordine già spedito ({status}) — skip welcome'
        order_date = int(order.get('orderDate') or order.get('createdAt') or 0)
        days_old = (now_ms - order_date) / DAY_MS
        if days_old > 7:
            return False, f'ordine vecchio ({days_old:.0f}gg) — skip welcome'
        return True, ''

    if reminder_type == 'day0':
        if not shipping_date:
            return False, 'shippingDate mancante'
        days_since = (now_ms - to_ms(shipping_date)) / DAY_MS
        if days_since > 3:
            return False, f'finestra scaduta ({days_since:.0f}gg dalla spedizione) — skip'
        return True, ''

    if reminder_type in ('day10', 'day20'):
        if status in STATI_TERMINALI or status in ('in_consegna', 'dogana', 'consegna_fallita'):
            return False, f'stato avanzato ({status}) — skip reminder temporizzato'
        if not shipping_date:
            return False, 'shippingDate mancante'

        days_since = (now_ms - to_ms(shipping_date)) / DAY_MS

        if shipping_type is None:
            return False, 'shippingType mancante — inserire nel CRM'

        threshold = 10 if reminder_type == 'day10' else 20
        if days_since < threshold:
            return False, f'troppo presto ({days_since:.1f}gg < {threshold}gg)'
        if days_since > threshold + 3:
            return False, f'finestra scaduta ({days_since:.0f}gg > {threshold+3}gg) — skip'

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


# ── Watchdog spedizioni ferme ────────────────────────────────────────────────

def last_status_change_ms(order: dict) -> int:
    """Data dell'ultimo cambio di stato noto (statusHistory), fallback a updatedAt/orderDate."""
    history = order.get('statusHistory') or []
    if history:
        return max(int(h.get('date', 0)) for h in history)
    return int(order.get('updatedAt') or order.get('orderDate') or order.get('createdAt') or 0)


def stale_info(order: dict, now_ms: int) -> tuple[int, int, int] | None:
    """Se lo stato non si muove da >= STALE_THRESHOLD_DAYS, restituisce
    (giorni_fermi, soglia_settimanale raggiunta — 7/14/21/..., last_change_ms).
    None se non bloccata (status terminale, ancora 'ricevuto', o sotto soglia)."""
    status = order.get('status', '')
    if status in STATI_TERMINALI or status == 'ricevuto':
        return None
    last_change = last_status_change_ms(order)
    if not last_change:
        return None
    days_stuck = (now_ms - last_change) / DAY_MS
    if days_stuck < STALE_THRESHOLD_DAYS:
        return None
    threshold = STALE_THRESHOLD_DAYS * int(days_stuck // STALE_THRESHOLD_DAYS)
    return int(days_stuck), threshold, last_change


def send_stale_alert(order: dict, days_stuck: int) -> str | None:
    """Alert interno a Luca (non al cliente): la spedizione non riceve aggiornamenti
    di stato da troppi giorni, va controllata a mano."""
    name     = order.get('customerName', '?')
    status   = order.get('status', '?')
    mbe_code = (order.get('shipmentCode') or '').strip()
    tracking = order.get('trackingNumber') or ''
    track17_url = f'https://t.17track.net/en#nums={tracking}' if tracking else ''

    subject = f'⚠️ Spedizione ferma da {days_stuck}gg — {name}'
    lines = [
        f'La spedizione di {name} è ferma allo stato "{status}" da {days_stuck} giorni,',
        'senza alcun aggiornamento di stato.',
        '',
        f'Codice spedizione: {mbe_code or "(mancante)"}',
        f'Tracking: {tracking or "(nessuno)"}',
    ]
    if track17_url:
        lines.append(f'Controlla su 17Track: {track17_url}')
    lines += ['', 'Verifica manualmente cosa sta succedendo con questa spedizione.']
    body_text = '\n'.join(lines)

    payload = {
        'sender':      {'name': SENDER_NAME, 'email': SENDER_EMAIL},
        'to':          [{'email': DIGEST_RECIPIENT, 'name': 'Luca'}],
        'subject':     subject,
        'textContent': body_text,
        'htmlContent': build_html_email(body_text),
        'tags':        ['wine-crm', 'ordini', 'stale-watchdog'],
        'trackClicks': False,
        'trackOpens':  False,
    }
    r = requests.post('https://api.brevo.com/v3/smtp/email', headers=_BREVO_HEADERS, json=payload)
    if r.ok:
        print(f'    🚨 Alert spedizione ferma → {DIGEST_RECIPIENT} ({name}, {days_stuck}gg)')
        return r.json().get('messageId', '')
    print(f'    ✗ Alert stale fallito {r.status_code}: {r.text[:120]}')
    return None


# ── Daily digest ─────────────────────────────────────────────────────────────

def send_daily_digest(orders: list, log_new: list, now_ms: int, test_mode: bool, stale_now: list) -> None:
    from collections import Counter

    now_str = datetime.now().strftime('%d/%m/%Y %H:%M')
    day_ago = now_ms - DAY_MS

    # Cambi stato nelle ultime 24h (da statusHistory)
    changes = []
    for o in orders:
        for h in (o.get('statusHistory') or []):
            if int(h.get('date', 0)) >= day_ago and h.get('status', '') != 'ricevuto':
                changes.append({'name': o.get('customerName','?'), 'status': h.get('status','?'), 'note': h.get('note','')})
    changes.sort(key=lambda x: x['status'])

    # Distribuzione status (esclusi annullati)
    active_orders = [o for o in orders if o.get('status') != 'annullato']
    counts = Counter(o.get('status','?') for o in active_orders)
    status_rows = sorted(counts.items(), key=lambda x: _STATUS_ORDER.index(x[0]) if x[0] in _STATUS_ORDER else 99)

    # ── HTML ─────────────────────────────────────────────────────────────────
    def _section(title: str, rows: list[str]) -> str:
        if not rows:
            return f'<h3 style="margin:24px 0 8px;color:#555;font-size:13px;text-transform:uppercase;letter-spacing:1px">{title}</h3><p style="color:#999;font-size:13px;margin:0">Nessuno</p>'
        items = ''.join(f'<li style="padding:3px 0;color:#333;font-size:14px">{r}</li>' for r in rows)
        return (f'<h3 style="margin:24px 0 8px;color:#555;font-size:13px;text-transform:uppercase;letter-spacing:1px">{title}</h3>'
                f'<ul style="margin:0;padding-left:20px">{items}</ul>')

    email_rows = [
        f'<b>{e["customerName"]}</b> → <code style="background:#f0f0f0;padding:1px 5px;border-radius:3px">{e["type"]}</code>'
        for e in log_new
    ] if log_new else []

    change_rows = [
        f'<b>{c["name"]}</b>: {_STATUS_EMOJI.get(c["status"],"•")} {c["status"]}'
        + (f' <span style="color:#999;font-size:12px">({c["note"]})</span>' if c["note"] else '')
        for c in changes
    ]

    stale_rows = [
        f'<b>{s["name"]}</b>: {_STATUS_EMOJI.get(s["status"],"•")} {s["status"]} — fermo da {s["days"]}gg'
        for s in sorted(stale_now, key=lambda x: -x['days'])
    ]

    status_table = ''.join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#555;font-size:14px">{_STATUS_EMOJI.get(s,"•")} {s}</td>'
        f'<td style="padding:4px 0;font-weight:bold;font-size:14px;color:#333">{n}</td></tr>'
        for s, n in status_rows
    )

    mode_badge = (
        '<span style="background:#e67e00;color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:bold">TEST MODE</span>'
        if test_mode else
        '<span style="background:#27ae60;color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:bold">PRODUZIONE</span>'
    )

    body_html = f"""
    <p style="margin:0 0 4px;color:#999;font-size:12px">{now_str} &nbsp;{mode_badge}</p>
    <h2 style="margin:0 0 20px;color:#222;font-size:20px;font-weight:bold">Resoconto giornaliero</h2>
    {_section(f'🚨 Spedizioni ferme ≥{STALE_THRESHOLD_DAYS}gg ({len(stale_now)})', stale_rows)}
    {_section(f'📧 Email inviate ({len(log_new)})', email_rows)}
    {_section(f'🔄 Cambi stato ultime 24h ({len(changes)})', change_rows)}
    <h3 style="margin:24px 0 8px;color:#555;font-size:13px;text-transform:uppercase;letter-spacing:1px">📦 Ordini attivi ({len(active_orders)})</h3>
    <table style="border-collapse:collapse"><tbody>{status_table}</tbody></table>
    """

    html_content = f"""<!DOCTYPE html><html lang="it">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f4f0;font-family:Georgia,'Times New Roman',serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f0;padding:32px 16px">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
  <tr><td style="background:{BG};border-radius:12px 12px 0 0;padding:20px 32px;text-align:center">
    <img src="{LOGO_URL}" width="140" alt="Il Ciliegio" style="display:block;margin:0 auto">
  </td></tr>
  <tr><td style="background:{ACCENT};height:4px;font-size:0">&nbsp;</td></tr>
  <tr><td style="background:#ffffff;padding:32px 40px">{body_html}</td></tr>
  <tr><td style="background:{ACCENT};height:3px;font-size:0">&nbsp;</td></tr>
  <tr><td style="background:{BG};border-radius:0 0 12px 12px;padding:16px 32px;text-align:center">
    <p style="margin:0;color:#999;font-size:11px">Il Ciliegio CRM — report automatico</p>
  </td></tr>
</table></td></tr></table>
</body></html>"""

    payload = {
        'sender':      {'name': SENDER_NAME, 'email': SENDER_EMAIL},
        'to':          [{'email': DIGEST_RECIPIENT, 'name': 'Luca'}],
        'subject':     f'📋 CRM Il Ciliegio — {now_str}',
        'htmlContent': html_content,
        'textContent': f'CRM Report {now_str}\nSpedizioni ferme: {len(stale_now)}\nEmail inviate: {len(log_new)}\nCambi stato: {len(changes)}\nOrdini attivi: {len(active_orders)}',
        'tags':        ['wine-crm', 'digest'],
        'trackClicks': False,
        'trackOpens':  False,
    }
    r = requests.post('https://api.brevo.com/v3/smtp/email', headers=_BREVO_HEADERS, json=payload)
    if r.ok:
        print(f'✓ Digest inviato a {DIGEST_RECIPIENT}')
    else:
        print(f'⚠ Digest fallito: {r.status_code} {r.text[:100]}')


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

    # In test mode: pulisce TUTTI gli entry non-manuali degli ordini attivi
    # (rimuove tutto ciò che fu salvato da test run precedenti, mai da produzione reale)
    if test_mode:
        cleaned = 0
        for o in orders:
            if o.get('status') in STATI_TERMINALI:
                continue  # non tocca i terminali
            before = len(o.get('emailsSent') or [])
            o['emailsSent'] = [e for e in (o.get('emailsSent') or []) if e.get('manual')]
            if len(o['emailsSent']) < before:
                o['updatedAt'] = now_ms
                cleaned += 1
        if cleaned:
            print(f'🧹 Pulizia: rimossi entry test da {cleaned} ordini attivi')

    active = [o for o in orders
              if o.get('status') not in ('ricevuto', 'preparazione', 'annullato')
              and not order_fully_done(o)]
    done = sum(1 for o in orders if order_fully_done(o))
    print(f'Ordini attivi: {len(active)} / {len(orders)} (esclusi {done} consegnati e già notificati)')

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

    # ── order_received: tutti gli ordini non annullati e non già conclusi ─────
    for order in [o for o in orders if o.get('status') != 'annullato' and not order_fully_done(o)]:
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

    # ── Mancata consegna: notifica ripetibile, una per tentativo fallito ─────
    # (a differenza degli altri reminder_type, questo NON passa da should_send:
    # lì il controllo "già inviata" è booleano — qui serve un conteggio, un
    # tentativo di consegna fallito in più deve generare una nuova email anche
    # se una precedente era già stata inviata per lo stesso ordine)
    tpl_cf = templates.get('consegna_fallita')
    for order in active:
        fail_count = order.get('deliveryFailureCount', 0)
        if not fail_count:
            continue
        if not tpl_cf:
            print(f'    {order.get("customerName","?")}: consegna_fallita — template mancante')
            continue
        already_sent = sum(1 for e in (order.get('emailsSent') or []) if e.get('type') == 'consegna_fallita')
        for _ in range(fail_count - already_sent):
            subject, body = render_template(tpl_cf, order)
            to_email = (order.get('customerEmail') or '').strip()
            msg_id = send_email(order, 'consegna_fallita', subject, body, test_mode)
            if msg_id:
                _record_send(order, 'consegna_fallita', to_email, subject, msg_id)
            else:
                break

    # ── Watchdog: spedizioni ferme (>= 7gg senza cambio di stato) ─────────────
    # Non dipende dal test_mode: lo stato tracking è reale a prescindere da
    # come vengono instradate le email al cliente, e Luca deve saperlo comunque.
    print(f'\n  Watchdog spedizioni ferme (soglia {STALE_THRESHOLD_DAYS}gg):')
    stale_changed = False
    stale_now     = []
    for order in orders:
        info = stale_info(order, now_ms)
        if not info:
            continue
        days_stuck, threshold, last_change = info
        stale_now.append({
            'name':   order.get('customerName', '?'),
            'status': order.get('status', '?'),
            'days':   days_stuck,
        })
        # Il contatore soglia è legato all'episodio corrente (last_change): se lo
        # stato si è mosso da quando fu salvato l'ultimo alert, è un nuovo episodio
        # di stallo e si riparte da zero (altrimenti una vecchia soglia alta
        # bloccherebbe l'alert su un nuovo blocco più recente ma più corto).
        already_alerted = int(order.get('staleAlertDays') or 0) \
            if order.get('staleAlertSince') == last_change else 0
        if threshold > already_alerted:
            msg_id = send_stale_alert(order, days_stuck)
            if msg_id:
                order['staleAlertDays']  = threshold
                order['staleAlertSince'] = last_change
                order['updatedAt'] = now_ms
                stale_changed = True
    if not stale_now:
        print('    nessuna spedizione ferma')

    now_str = datetime.now().strftime('%d/%m/%Y %H:%M')

    if test_mode:
        # Salva la pulizia degli entry corrotti + eventuali alert stale (ma non i nuovi invii)
        if cleaned or stale_changed:
            db['orders'] = orders
            parts = [p for p in (
                f'pulizia {cleaned} ordini' if cleaned else '',
                'alert spedizioni ferme' if stale_changed else '',
            ) if p]
            gh_put(DATA_PATH, db, sha_db, f'Test mode: {", ".join(parts)} — {now_str}')
            print(f'✓ Salvato su ordini.json ({", ".join(parts)}).')
        print(f'\n🧪 Test completato: {sent} email inviate a {BCC_EMAIL}. emailsSent non modificato.')
    else:
        if sent > 0 or stale_changed:
            db['orders'] = orders
            gh_put(DATA_PATH, db, sha_db, f'Reminder email — {sent} inviate — {now_str}')
            if sent > 0:
                log_data, log_sha = gh_get(LOG_PATH)
                existing = log_data.get('log', []) if isinstance(log_data, dict) else []
                gh_put(LOG_PATH, {'log': existing + log_new}, log_sha,
                       f'Email log — {len(log_new)} entries — {now_str}')
                print(f'\n✓ {sent} email inviate, ordini.json aggiornato.')
                print(f'✓ email-log.json aggiornato ({len(log_new)} nuove righe).')
            else:
                print(f'\n✓ ordini.json aggiornato (alert spedizioni ferme).')
        else:
            print('\nNessuna email da inviare.')

    if _is_digest_run():
        send_daily_digest(orders, log_new, now_ms, test_mode, stale_now)
    else:
        print(f'⏭ Digest skippato — parte solo al run delle {DIGEST_HOUR_UTC}:00 UTC')


if __name__ == '__main__':
    main()
