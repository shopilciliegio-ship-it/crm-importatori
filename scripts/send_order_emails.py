"""
Send order status notification emails via Brevo — Il Ciliegio CRM
Runs after fetch_mbe_tracking.py. Sends one email per status change, no duplicates.
"""

import base64
import html
import json
import os
from datetime import datetime, timezone

import requests

BREVO_API_KEY = os.environ['BREVO_API_KEY']
GH_TOKEN      = os.environ['GH_TOKEN']
GH_REPO       = os.environ['GH_REPO']
DATA_PATH     = 'data/ordini.json'

SENDER_NAME   = 'Il Ciliegio — Azienda Agricola'
SENDER_EMAIL  = 'export@ilciliegio.com'
LOGO_URL      = 'https://shopilciliegio-ship-it.github.io/crm-importatori/assets/logo_ciliegio.png'
ACCENT        = '#B8941A'
BG            = '#2c2c2c'
WEBSITE       = 'www.ilciliegio.com'
PHONE         = '+39 331 1347899'
TAGLINE       = 'Vini artigianali toscani di eccellenza'

EMAIL_STATUSES = {'spedito', 'in_transito', 'dogana', 'consegnato', 'problema'}

_GH_HEADERS    = {
    'Authorization': f'token {GH_TOKEN}',
    'Accept':        'application/vnd.github.v3+json',
}
_BREVO_HEADERS = {
    'api-key':      BREVO_API_KEY,
    'Content-Type': 'application/json',
    'Accept':       'application/json',
}


# ── GitHub ────────────────────────────────────────────────────────────────────

def load_ordini() -> tuple[dict, str | None]:
    url = f'https://api.github.com/repos/{GH_REPO}/contents/{DATA_PATH}'
    r   = requests.get(url, headers=_GH_HEADERS)
    if r.status_code == 404:
        return {'orders': [], 'lastImportedAt': None}, None
    r.raise_for_status()
    data    = r.json()
    content = base64.b64decode(data['content']).decode('utf-8')
    return json.loads(content), data['sha']


def save_ordini(db: dict, sha: str | None) -> None:
    url     = f'https://api.github.com/repos/{GH_REPO}/contents/{DATA_PATH}'
    content = base64.b64encode(
        json.dumps(db, ensure_ascii=False, indent=2).encode('utf-8')
    ).decode('utf-8')
    now_str = datetime.now().strftime('%d/%m/%Y %H:%M')
    body    = {'message': f'Email status notifications — {now_str}', 'content': content}
    if sha:
        body['sha'] = sha
    requests.put(url, headers=_GH_HEADERS, json=body).raise_for_status()


# ── Email builder ─────────────────────────────────────────────────────────────

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


def build_email_content(order: dict) -> tuple[str, str] | None:
    nome     = (order.get('customerName') or '').split()[0] or order.get('customerName', '')
    status   = order.get('status', '')
    tracking = order.get('trackingNumber', '')
    track_url = f'https://www.17track.net/en/track?nums={tracking}' if tracking else ''
    track_line = f'Numero di tracking: {tracking}\nSeguilo: {track_url}\n' if tracking else ''

    if status == 'spedito':
        subject = f"Il tuo ordine è partito!{' — Tracking: ' + tracking if tracking else ''}"
        body = (
            f"Caro {nome},\n\n"
            f"il tuo ordine è stato spedito ed è ora in viaggio verso di te! 🍷\n\n"
            f"{track_line}"
            f"La spedizione dovrebbe arrivare entro 7-10 giorni lavorativi. "
            f"Ti aggiorneremo ad ogni cambio di stato.\n\n"
            f"Grazie per aver scelto i nostri vini!\n\n"
            f"Luca Pattaro\nIl Ciliegio — Azienda Agricola\nexport@ilciliegio.com | {PHONE}"
        )

    elif status == 'in_transito':
        subject = 'Aggiornamento spedizione — Il tuo vino è in viaggio'
        body = (
            f"Caro {nome},\n\n"
            f"il tuo ordine è in viaggio e procede regolarmente verso la destinazione. 📦\n\n"
            f"{track_line}"
            f"Tempi stimati: 5-10 giorni lavorativi dalla data di spedizione.\n\n"
            f"A presto!\n\n"
            f"Luca Pattaro\nIl Ciliegio — Azienda Agricola\nexport@ilciliegio.com | {PHONE}"
        )

    elif status == 'dogana':
        subject = 'Il tuo ordine è in fase di sdoganamento'
        body = (
            f"Caro {nome},\n\n"
            f"il tuo ordine è attualmente in fase di sdoganamento. "
            f"Questo processo richiede normalmente 2-5 giorni lavorativi.\n\n"
            f"{'Puoi seguire l\\'avanzamento su: ' + track_url + chr(10) if track_url else ''}"
            f"Non è richiesto alcun intervento da parte tua — "
            f"ti aggiorneremo appena l'ordine riparte.\n\n"
            f"Grazie per la pazienza!\n\n"
            f"Luca Pattaro\nIl Ciliegio — Azienda Agricola\nexport@ilciliegio.com | {PHONE}"
        )

    elif status == 'consegnato':
        subject = 'Il tuo ordine è stato consegnato! 🍷 Buona degustazione!'
        body = (
            f"Caro {nome},\n\n"
            f"ottime notizie! Il tuo ordine è stato consegnato con successo. 🎉\n\n"
            f"Speriamo che tu possa apprezzare i vini de Il Ciliegio. "
            f"Se hai domande o feedback, non esitare a contattarci — "
            f"il tuo parere è prezioso per noi.\n\n"
            f"Saluti,\n\n"
            f"Luca Pattaro\nIl Ciliegio — Azienda Agricola\nexport@ilciliegio.com | {PHONE}"
        )

    elif status == 'problema':
        subject = '⚠ Aggiornamento importante sulla tua spedizione'
        body = (
            f"Caro {nome},\n\n"
            f"ti contatto riguardo al tuo ordine. Purtroppo si è verificato un problema "
            f"con la spedizione che stiamo già monitorando attivamente.\n\n"
            f"Il nostro team è al lavoro per risolvere la situazione e "
            f"ti terremo aggiornato il prima possibile.\n\n"
            f"{'Tracking: ' + tracking + chr(10) + chr(10) if tracking else ''}"
            f"Per qualsiasi domanda urgente, rispondi direttamente a questa email.\n\n"
            f"Luca Pattaro\nIl Ciliegio — Azienda Agricola\nexport@ilciliegio.com | {PHONE}"
        )

    else:
        return None

    return subject, body


# ── Brevo send ────────────────────────────────────────────────────────────────

def send_email(order: dict) -> str | None:
    result = build_email_content(order)
    if not result:
        return None
    subject, body_text = result

    payload = {
        'sender':      {'name': SENDER_NAME, 'email': SENDER_EMAIL},
        'to':          [{'email': order['customerEmail'], 'name': order.get('customerName', '')}],
        'subject':     subject,
        'textContent': body_text,
        'htmlContent': build_html_email(body_text),
        'tags':        ['wine-crm', 'ordini'],
        'headers':     {'X-CRM-OrderId': order['id']},
    }

    r = requests.post('https://api.brevo.com/v3/smtp/email', headers=_BREVO_HEADERS, json=payload)
    if r.ok:
        return r.json().get('messageId')
    print(f'  Brevo error {r.status_code}: {r.text}')
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print('=== Send Order Status Emails ===')

    db, sha = load_ordini()
    orders  = db.get('orders', [])
    print(f'Ordini nel DB: {len(orders)}')

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    sent   = 0

    for order in orders:
        status = order.get('status', '')
        if status not in EMAIL_STATUSES:
            continue

        if not order.get('customerEmail'):
            print(f'  = {order.get("customerName", "?")} — email cliente mancante, skip')
            continue

        already = any(e.get('type') == status for e in (order.get('emailsSent') or []))
        if already:
            print(f'  = {order.get("customerName", "?")} — email "{status}" già inviata')
            continue

        name  = order.get('customerName', '?')
        email = order['customerEmail']
        print(f'  → {name} ({email}) — invio "{status}"...')

        message_id = send_email(order)
        if message_id:
            order.setdefault('emailsSent', []).append({
                'type':      status,
                'sentAt':    now_ms,
                'messageId': message_id,
            })
            order['updatedAt'] = now_ms
            sent += 1
            print(f'  ✓ Inviata — messageId: {message_id}')
        else:
            print(f'  ✗ Errore invio per {name}')

    if sent > 0:
        db['orders'] = orders
        save_ordini(db, sha)
        print(f'\n✓ {sent} email inviate, ordini.json aggiornato.')
    else:
        print('\nNessuna email da inviare.')


if __name__ == '__main__':
    main()
