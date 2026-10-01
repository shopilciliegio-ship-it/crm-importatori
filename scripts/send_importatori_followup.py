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
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

# ── Config ────────────────────────────────────────────────────────────────────
BREVO_API_KEY = os.environ['BREVO_API_KEY']
GH_TOKEN      = os.environ['GH_TOKEN']
GH_REPO       = os.environ['GH_REPO']

# Architettura override per importatori (stesso pattern di js/github.js):
# contatti.json           = base read-only, aggiornata solo dal sync BWI settimanale
# contatti-overrides.json = solo le differenze utente (status/notes/log/brevoEvents/research)
BASE_PATH      = 'data/contatti.json'
OVERRIDES_PATH = 'data/contatti-overrides.json'
TEMPLATES_PATH = 'data/templates.json'
SETTINGS_PATH  = 'data/crm-settings.json'
LOG_PATH       = 'data/email-log-importatori.json'

BCC_EMAIL        = 'hokutazzo@gmail.com'
DIGEST_RECIPIENT = 'luca@ilciliegio.com'

# Lo script gira ogni 4h (import_ordini.yml) ma il digest deve partire una
# sola volta al giorno — solo al run delle DIGEST_HOUR_UTC:00 UTC.
DIGEST_HOUR_UTC = 8  # 10:00 in Italia (CEST)


def _is_digest_run() -> bool:
    return datetime.now(timezone.utc).hour == DIGEST_HOUR_UTC

SENDER_NAME  = 'Luca Pattaro — Siena Wine'
SENDER_EMAIL = 'luca@sienawine.it'
LOGO_URL     = 'https://shopilciliegio-ship-it.github.io/crm-importatori/assets/logo_sienawine.png'
ACCENT       = '#8B1A1A'
BG           = '#2c2c2c'
WEBSITE      = 'www.sienawine.it'
PHONE        = '+39 331 1347899'

DAY_MS            = 24 * 3600 * 1000

# Protezione contro gli invii in loop (incidente 26/9-1/10/2026: il passo andava in timeout prima di
# salvare, e al giro dopo rimandava le stesse email, ~8.000 invii). Tre regole:
#  1) tetto di invii per giro, 2) budget di tempo, così il salvataggio finale parte sempre prima
#  del timeout del workflow, 3) salvataggio a blocchi: lo stato è su GitHub ogni SAVE_EVERY invii,
#  e se un salvataggio fallisce si smette subito di inviare.
MAX_SENDS_PER_RUN = int(os.environ.get('FOLLOWUP_MAX_PER_RUN', '100'))
TIME_BUDGET_S     = int(os.environ.get('FOLLOWUP_TIME_BUDGET_S', '360'))
SAVE_EVERY        = int(os.environ.get('FOLLOWUP_SAVE_EVERY', '20'))
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
    r = _gh_request('GET', url, headers=_GH_HEADERS)
    if r.status_code == 404:
        return {}, None
    r.raise_for_status()
    data = r.json()
    sha  = data['sha']
    raw  = data.get('content') or ''
    if not raw and data.get('download_url'):
        # File > 1 MB: l'API Contents restituisce content vuoto — scarica diretto
        # (stesso fix v164 applicato in js/github.js per contatti-overrides.json)
        rr = _gh_request('GET', data['download_url'])
        rr.raise_for_status()
        return rr.json(), sha
    if not raw:
        return {}, sha
    content = base64.b64decode(raw).decode('utf-8')
    return json.loads(content), sha


def gh_get_overrides() -> tuple[dict, str | None, bool]:
    """Carica contatti-overrides.json. Ritorna (overrides, sha, ok).
    ok=False su qualunque errore di rete/HTTP/parsing — il chiamante NON deve
    calcolare/salvare un diff in quel caso, altrimenti rischia di azzerare gli
    override esistenti (vedi incident 21-22/06/2026)."""
    url = f'https://api.github.com/repos/{GH_REPO}/contents/{OVERRIDES_PATH}'
    try:
        r = _gh_request('GET', url, headers=_GH_HEADERS)
        if r.status_code == 404:
            return {}, None, True  # nessun override ancora — caso legittimo
        r.raise_for_status()
        data = r.json()
        sha  = data['sha']
        raw  = data.get('content') or ''
        if not raw and data.get('download_url'):
            rr = _gh_request('GET', data['download_url'])
            rr.raise_for_status()
            return rr.json(), sha, True
        if not raw:
            return {}, sha, True  # file davvero vuoto
        return json.loads(base64.b64decode(raw).decode('utf-8')), sha, True
    except Exception as e:
        print(f'    ⚠ gh_get_overrides error: {e}')
        return {}, None, False


def get_sha(path: str) -> str | None:
    r = _gh_request('GET', f'https://api.github.com/repos/{GH_REPO}/contents/{path}',
                     headers=_GH_HEADERS)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()['sha']


# Campi scritti negli override da ALTRI punti (CRM, sblocco email BWI, revisione risposte) che questo
# script non modifica ma NON deve perdere: build_overrides_diff() ricostruisce l'intero file, e fino al
# 23/9/2026 teneva solo status/notes/log/brevoEvents/research — un invio avrebbe cancellato email
# sbloccate, standby e caselle bloccate. Ora: questi campi si aggiornano se cambiati, e qualunque altro
# campo già presente negli override viene ricopiato così com'è.
EXTRA_OV_FIELDS = ('contacts', 'contactEmail', 'contactName', 'contactTitle', 'snoozeUntil', 'emailBloccate')
TRACKED_OV_FIELDS = ('status', 'notes', 'log', 'brevoEvents', 'research')
_LOADED_OV = {}


def load_contacts_with_overrides() -> tuple[list, dict, bool, int]:
    """Mirrors js/github.js loadFromGH()+_loadImportatoriOverrides(): carica la base
    read-only data/contatti.json, applica sopra gli override utente e mantiene uno
    snapshot dei valori base (pre-override) per ogni contatto, necessario per
    calcolare poi il diff da salvare in build_overrides_diff()."""
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
            'extra':       {k: json.dumps(c.get(k), ensure_ascii=False) for k in EXTRA_OV_FIELDS},
        }

    overrides, _, overrides_ok = gh_get_overrides()
    overrides_loaded_count = len(overrides)
    _LOADED_OV.clear()
    _LOADED_OV.update(overrides)
    by_id = {c['id']: c for c in contacts}
    for cid, changes in overrides.items():
        if cid in by_id:
            by_id[cid].update(changes)

    return contacts, base_snap, overrides_ok, overrides_loaded_count


def build_overrides_diff(contacts: list, base_snap: dict) -> dict:
    """Ricalcola l'intero contatti-overrides.json a partire dai contatti correnti
    in memoria confrontati con lo snapshot base — stesso approccio di
    _pushImportatoriOverrides in js/github.js."""
    new_ov = {}
    for c in contacts:
        snap = base_snap.get(c['id'])
        if not snap:
            continue
        # Ricopia i campi di override che qui non si ricalcolano (vedi EXTRA_OV_FIELDS).
        diff = {k: v for k, v in (_LOADED_OV.get(c['id']) or {}).items() if k not in TRACKED_OV_FIELDS}
        for k in EXTRA_OV_FIELDS:
            if k in diff or json.dumps(c.get(k), ensure_ascii=False) != snap['extra'][k]:
                diff[k] = c.get(k)
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


def gh_put(path: str, data, sha: str | None, message: str) -> None:
    url     = f'https://api.github.com/repos/{GH_REPO}/contents/{path}'
    content = base64.b64encode(
        json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    ).decode('utf-8')
    body = {'message': message, 'content': content}
    if sha:
        body['sha'] = sha
    _gh_request('PUT', url, headers=_GH_HEADERS, json=body).raise_for_status()


# ── Contact helpers ────────────────────────────────────────────────────────────

def select_contact(c: dict) -> tuple[str, str]:
    """Sceglie il 'miglior' contatto per priorità di ruolo — usata SOLO come ripiego da
    step1_target() per contatti storici senza toEmail salvato in brevoEvents (da prima che questo
    tracciamento esistesse). NON va chiamata per decidere a chi mandare un follow-up: la scelta
    del destinatario si fa una volta sola, al primo invio (select_send_email() in
    send_importatori_bulk.py) — i follow-up devono continuare sullo stesso indirizzo, vedi
    step1_target(). Esclude comunque le caselle segnate sbagliate/non monitorate
    (provaAltraCasella in js/risposte.js)."""
    blocked = {(e or '').strip().lower() for e in (c.get('emailBloccate') or [])}
    contacts = c.get('contacts') or []
    best, best_score = None, 999
    for ct in contacts:
        email = (ct.get('email') or '').strip()
        if not email or email.lower() in blocked:
            continue
        title = (ct.get('title') or '').lower()
        score = 99
        for kw, pri in JOB_PRIORITY.items():
            if kw in title:
                score = min(score, pri)
        if ct.get('sbloccato'):
            score = -1  # persona sbloccata via BWI = sempre il destinatario
        if score < best_score:
            best_score, best = score, ct
    if best:
        return best['email'], best.get('name', '')
    fallback_email = (c.get('contactEmail') or c.get('email', '')).strip()
    if fallback_email.lower() in blocked:
        return '', ''
    return fallback_email, (c.get('contactName') or c.get('name', ''))


def step1_target(c: dict) -> tuple[str, str]:
    """A chi è stata mandata la prima email — i follow-up vanno SEMPRE alla stessa persona/
    indirizzo (continuità del filo: il template dice letteralmente "ti riscrivo riguardo alla mia
    email precedente", non ha senso se la riceve chi quella email non l'ha mai vista — vedi
    discussione 22/9/2026, prima veniva ri-scelto il "miglior" contatto ad ogni run). Se
    l'indirizzo bloccato nel frattempo (provaAltraCasella → emailBloccate), NON continua a
    scrivere lì: ripiega su select_contact() per trovare un'alternativa valida."""
    evs = sorted(c.get('brevoEvents') or [], key=lambda e: e.get('sentAt', 0))
    step1 = next((e for e in evs if (e.get('sequenceStep') or 1) == 1), evs[0] if evs else None)
    blocked = {(e or '').strip().lower() for e in (c.get('emailBloccate') or [])}
    if step1 and step1.get('toEmail') and step1['toEmail'].strip().lower() not in blocked:
        return step1['toEmail'].strip(), step1.get('toName', '')
    return select_contact(c)


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


def greeting_line(c: dict, to_email: str, ref_name: str) -> str:
    """Riga di saluto secondo a CHI arriva davvero la mail (regola di Luca, 23/9/2026):
      - indirizzo personale di una persona nota  -> "Dear Ken from <Azienda>,"
      - indirizzo generico, ma persona di riferimento -> "To the kind attention of Ken John,"
      - indirizzo generico e nessun nome          -> "Esteemed <Azienda> Team,"
    Stessa logica di buildGreeting() in js/email.js."""
    e = (to_email or '').strip().lower()
    company = c.get('company', '') or ''
    person = next((p for p in (c.get('contacts') or [])
                   if e and (p.get('email') or '').strip().lower() == e and (p.get('name') or '').strip()), None)
    name = (person or {}).get('name', '')
    if not name and e and e == (c.get('contactEmail') or '').strip().lower() \
            and e != (c.get('email') or '').strip().lower():
        name = c.get('contactName') or ''  # email personale importata senza scheda persona
    if name.strip():
        return f"Dear {first_name(name)} from {company}," if company else f"Dear {first_name(name)},"
    if (ref_name or '').strip():
        return f"To the kind attention of {ref_name.strip()},"
    return f"Esteemed {company} Team," if company else 'Dear Sir/Madam,'


def render_template(tpl: dict, c: dict, to_email: str, to_name: str) -> tuple[str, str]:
    contact_fn = first_name(to_name)
    company    = c.get('company', '')
    owner_fn   = get_owner(c, to_email)

    # to_name può essere il nome di riferimento anche quando to_email è generico (info@...):
    # greeting_line() decide in base a chi possiede davvero l'indirizzo.
    dear = greeting_line(c, to_email, to_name)

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

_LABELED_URL_RE = re.compile(r'\[([^\]]+)\]\((https?://[^\s)]+)\)')
_URL_RE         = re.compile(r'(https?://[^\s<]+|(?:www\.|calendly\.com/)[^\s<]+)')

def _linkify(escaped_text: str) -> str:
    """Stesso comportamento di _linkify in js/email.js: sintassi markdown
    [etichetta](url) per link con testo pulito (usata dai template per evitare
    di mostrare l'URL nudo, che dopo il click-tracking di Brevo diventerebbe
    il dominio di redirect), più auto-link per gli URL nudi rimasti."""
    placeholders: list[str] = []

    def _repl_labeled(m: re.Match) -> str:
        label, url = m.group(1), m.group(2).replace('&amp;', '&')
        placeholders.append(f'<a href="{url}" style="color:{ACCENT};font-weight:600;'
                             f'text-decoration:none">{label}</a>')
        return f'@@LINK{len(placeholders)-1}@@'

    text = _LABELED_URL_RE.sub(_repl_labeled, escaped_text)

    def _repl_bare(m: re.Match) -> str:
        url = m.group(1).replace('&amp;', '&')
        href = url if url.startswith('http') else 'https://' + url
        return (f'<a href="{href}" style="color:{ACCENT};font-weight:600;'
                f'text-decoration:none">{m.group(1)}</a>')
    text = _URL_RE.sub(_repl_bare, text)

    return re.sub(r'@@LINK(\d+)@@', lambda m: placeholders[int(m.group(1))], text)


def _body_to_html(plain: str) -> str:
    paras = [p.strip() for p in plain.split('\n\n') if p.strip()]
    parts = []
    for p in paras:
        lines  = p.split('\n')
        bulls  = [l for l in lines if l.strip().startswith('•')]
        others = [l for l in lines if not l.strip().startswith('•')]
        if bulls and len(bulls) >= len(others):
            if others:
                intro = _linkify(html.escape(' '.join(others)))
                parts.append(f'<p style="margin:0 0 8px;color:#333;font-size:15px;line-height:1.7">{intro}</p>')
            items = ''.join(
                f'<li style="color:#333;font-size:14px;line-height:1.8;padding:1px 0">'
                f'{_linkify(html.escape(l.lstrip("• ").strip()))}</li>'
                for l in bulls
            )
            parts.append(f'<ul style="margin:0 0 16px;padding-left:20px">{items}</ul>')
        else:
            escaped = _linkify(html.escape(p)).replace('\n', '<br>')
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
      <a href="https://{WEBSITE}" style="color:#ccc;text-decoration:none">{WEBSITE}</a>&nbsp;|&nbsp;<span style="color:#999">{PHONE}</span>
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
        actual_bcc  = []
        print(f'    ✓ step{step} → {to_email}')

    payload = {
        'sender':      {'name': SENDER_NAME, 'email': SENDER_EMAIL},
        # Brevo rifiuta un "name" vuoto (400 "name is missing in to", 181 follow-up persi il 25/9/2026
        # sulle caselle generiche info@/sales@ senza nome di persona): se manca, si manda solo l'email.
        'to':          [{'email': actual_to, **({'name': to_name.strip()} if (to_name or '').strip() else {})}],
        'subject':     actual_subj,
        'textContent': body_text,
        'htmlContent': build_html_email(body_text),
        'tags':        ['wine-crm', 'importatori', f'step{step}'] + (['test'] if test_mode else []),
        'headers':     {'X-CRM-ContactId': contact_id},
    }
    if actual_bcc:
        payload['bcc'] = actual_bcc

    r = requests.post('https://api.brevo.com/v3/smtp/email', headers=_BREVO_HEADERS, json=payload)
    if r.ok:
        return r.json()
    print(f'    ✗ Brevo {r.status_code}: {r.text[:120]}')
    return None


# ── Brevo events sync ─────────────────────────────────────────────────────────

SYNC_BUDGET_SECONDS = 180  # 3 minuti: lascia margine dentro il timeout di 10' del job GitHub Actions
# per la parte che conta davvero (invio follow-up, sotto) — vedi incidente 22/9/2026: Brevo in
# timeout ha fatto sforare l'intero step, e l'invio follow-up non è mai partito quel giorno perché
# il sync (una chiamata HTTP per OGNI singola email già inviata, migliaia in totale) viene prima.


def sync_brevo_events(contacts: list, now_ms: int) -> int:
    updated = 0
    t0 = time.monotonic()
    timeouts_in_a_row = 0
    for c in contacts:
        if time.monotonic() - t0 > SYNC_BUDGET_SECONDS:
            print(f'  ⏱ Budget di {SYNC_BUDGET_SECONDS}s esaurito — salto il resto del sync '
                  f'(riprende dal prossimo run, l\'invio follow-up parte comunque adesso).')
            break
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
                timeouts_in_a_row = 0
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
                # Brevo giù/degradato: tanti timeout di fila vogliono dire che aspettare 10s per
                # ognuno è solo tempo sprecato — molla subito invece di bruciare tutto il budget
                # un errore alla volta.
                timeouts_in_a_row += 1
                if timeouts_in_a_row >= 5:
                    print(f'  ⚠ {timeouts_in_a_row} errori di fila — Brevo sembra irraggiungibile, interrompo il sync.')
                    return updated
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

    # Standby (fuori sede rilevato in js/risposte.js, campo impostato dal CRM): niente follow-up
    # finché non passa la data indicata — vedi fuIndicator() in js/brevo.js per lo stesso campo
    # lato UI.
    snooze_until = c.get('snoozeUntil') or 0
    if snooze_until and now_ms < snooze_until:
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
    # Se c'è stato uno standby, il conteggio 7/21/35gg riparte da quando è finito (non resta
    # ancorato al primo invio originale): altrimenti un contatto "in pausa" da prima del giorno 7
    # si becca il follow-up quasi subito appena rientra, invece di avere una settimana piena come
    # da lì in poi — non è quello che Luca vuole quando dà tempo a qualcuno di rientrare dalle ferie.
    riferimento = max(step1.get('sentAt') or 0, snooze_until)
    days        = (now_ms - riferimento) / DAY_MS

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


# ── Piano invii (visibilità + approvazione giornaliera) ───────────────────────
# Dal 1/10/2026 (dopo l'incidente del loop): il CRM mostra cosa è in coda e quando partirà, e i
# follow-up partono SOLO se per quel giorno c'è un'approvazione (data/piano-approvato.json, scritto
# dal CRM col pulsante "Approva il piano di oggi"). Senza approvazione, nessun invio.

PLAN_PATH       = 'data/piano-invii.json'
APPROVAL_PATH   = 'data/piano-approvato.json'
RUNS_PER_DAY    = 4            # import_ordini.yml parte alle 0/6/12/18 (ora italiana) dal timer Cloudflare
PLAN_HORIZON    = 14           # giorni di calendario proiettato
FOLLOWUP_TYPES  = ('day7', 'day21', 'day35')
# label → (n_steps già inviati, giorni minimi dal riferimento, giorni massimi: oltre la finestra è scaduta)
_WINDOWS = {1: ('day7', 7, 14), 2: ('day21', 21, 31), 3: ('day35', 35, 50)}
ROME = ZoneInfo('Europe/Rome')


def followup_window(c: dict) -> dict | None:
    """Finestra del PROSSIMO follow-up di un contatto: stesse regole di should_send_followup(),
    ma in forma di date (così si può proiettare nel futuro). Ritorna None se non ne ha uno atteso."""
    if c.get('status') in TERMINAL_STATUSES:
        return None
    evs = sorted(c.get('brevoEvents') or [], key=lambda e: e.get('sentAt', 0))
    if not evs:
        return None
    last_st = get_ev_status(evs[-1])
    if last_st in ('bounced', 'spam', 'unsubscribed', 'blocked') or \
       (evs[-1].get('manualStatus') in TERMINAL_STATUSES):
        return None
    n_steps = len(evs)
    if n_steps not in _WINDOWS:
        return None
    step1 = next((e for e in evs if (e.get('sequenceStep') or 1) == 1), evs[0])
    ref   = max(step1.get('sentAt') or 0, c.get('snoozeUntil') or 0)
    label, dmin, dmax = _WINDOWS[n_steps]
    return {'label': label, 'n': n_steps, 'ref': ref,
            'due': ref + dmin * DAY_MS, 'expire': ref + dmax * DAY_MS}


def _rome_day_start_ms(d) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=ROME).timestamp() * 1000)


def _followup_step_active() -> bool:
    """Legge import_ordini.yml: il passo "Invia follow-up importatori" è acceso o disattivato (if: false)?"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.github', 'workflows', 'import_ordini.yml')
    try:
        lines = open(path, encoding='utf-8').read().splitlines()
    except OSError:
        return False
    for i, ln in enumerate(lines):
        if 'name: Invia follow-up importatori' in ln:
            for nxt in lines[i + 1:i + 6]:
                s = nxt.strip()
                if s.startswith('if:'):
                    return not re.search(r'(\$\{\{\s*)?false(\s*\}\})?', s.split('#')[0].split(':', 1)[1])
                if s.startswith('- name:'):
                    break
            return True
    return False


def _log_counts_by_day(log: list, now: datetime) -> dict:
    """{data ISO: {tipo: n}} per gli ultimi 7 giorni (ora italiana), da email-log-importatori.json."""
    out = {}
    first = (now - timedelta(days=6)).date()
    for e in log:
        ms = e.get('sentAt')
        if not ms:
            continue
        d = datetime.fromtimestamp(ms / 1000, ROME).date()
        if d < first:
            continue
        out.setdefault(d.isoformat(), {}).setdefault(e.get('type') or 'altro', 0)
        out[d.isoformat()][e.get('type') or 'altro'] += 1
    return out


def sent_today(log: list, now: datetime) -> int:
    today = now.date()
    return sum(1 for e in log if e.get('type') in FOLLOWUP_TYPES and e.get('sentAt')
               and datetime.fromtimestamp(e['sentAt'] / 1000, ROME).date() == today)


def approval_for_today(now: datetime) -> dict | None:
    """Approvazione valida OGGI (ora italiana) o None."""
    data, _ = gh_get(APPROVAL_PATH)
    if isinstance(data, dict) and data.get('date') == now.date().isoformat():
        return data
    return None


def build_plan(contacts: list, templates: list, log: list, settings: dict, now: datetime) -> dict:
    now_ms = int(now.timestamp() * 1000)
    per_giro, per_day = MAX_SENDS_PER_RUN, MAX_SENDS_PER_RUN * RUNS_PER_DAY
    active = [c for c in contacts if c.get('status') in ACTIVE_STATUSES]

    # Coda: stesse regole dell'invio reale. Verifica incrociata con should_send_followup() per i "pronti ora".
    pool, no_email = [], 0
    for c in active:
        w = followup_window(c)
        if not w:
            continue
        if not step1_target(c)[0]:
            no_email += 1
            continue
        w['id'] = c.get('id')
        pool.append(w)
    pool.sort(key=lambda w: w['expire'])   # chi sta per scadere va per primo (stesso ordine dell'invio reale)

    pronte_now = [w for w in pool if w['due'] <= now_ms <= w['expire']]
    scadute_now = [w for w in pool if w['expire'] < now_ms]
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        reali = sum(1 for c in active if should_send_followup(c, templates, now_ms)[0])

    # Proiezione giorno per giorno: ogni giorno parte al massimo per_day mail, chi scade prima va per primo;
    # dopo un invio il contatto passa alla finestra del passo successivo.
    giorni, persi = [], 0
    already = sent_today(log, now)
    active_pool = [w for w in pool if w['expire'] >= now_ms]
    for k in range(PLAN_HORIZON):
        day = (now + timedelta(days=k)).date()
        d0 = _rome_day_start_ms(day)
        d1 = d0 + DAY_MS
        cap = max(per_day - (already if k == 0 else 0), 0)
        eligible = [w for w in active_pool if w['due'] < d1 and w['expire'] >= max(d0, now_ms if k == 0 else d0)]
        eligible.sort(key=lambda w: w['expire'])
        take = eligible[:cap]
        counts = Counter(w['label'] for w in take)
        for w in take:
            active_pool.remove(w)
            nxt = _WINDOWS.get(w['n'] + 1)
            if nxt:
                active_pool.append({'label': nxt[0], 'n': w['n'] + 1, 'ref': w['ref'],
                                    'due': w['ref'] + nxt[1] * DAY_MS, 'expire': w['ref'] + nxt[2] * DAY_MS})
        lost = [w for w in active_pool if w['expire'] < d1]
        active_pool = [w for w in active_pool if w['expire'] >= d1]
        persi += len(lost)
        giorni.append({
            'data': day.isoformat(), 'giorno': ['lun', 'mar', 'mer', 'gio', 'ven', 'sab', 'dom'][day.weekday()],
            'daInviare': len(take), 'day7': counts.get('day7', 0), 'day21': counts.get('day21', 0),
            'day35': counts.get('day35', 0), 'scadonoSenzaInvio': len(lost),
            'inCodaAFineGiorno': len([w for w in active_pool if w['due'] < d1]),
        })

    today_plan = giorni[0]['daInviare'] if giorni else 0
    return {
        'generatoAt': now_ms,
        'generatoIl': now.strftime('%d/%m/%Y %H:%M'),
        'followupPassoAttivo': _followup_step_active(),
        'invioAutomatico': bool(settings.get('emailAutoSendImportatori', False)),
        'testMode': bool(settings.get('testModeImportatori', True)),
        'tetto': {'perGiro': per_giro, 'giriAlGiorno': RUNS_PER_DAY, 'perGiorno': per_day},
        'contattiAttivi': len(active),
        'pronteOra': {'totale': len(pronte_now), 'day7': sum(1 for w in pronte_now if w['label'] == 'day7'),
                      'day21': sum(1 for w in pronte_now if w['label'] == 'day21'),
                      'day35': sum(1 for w in pronte_now if w['label'] == 'day35'),
                      'verificaCodiceInvio': reali},
        'scaduteGia': len(scadute_now),
        'senzaCasellaValida': no_email,
        'giorni': giorni,
        'perseNelPeriodo': persi,
        'oggi': {'inviate': already, 'limiteProposto': already + today_plan},
        'registro7Giorni': _log_counts_by_day(log, now),
        'crediti': brevo_credits(),
    }


def brevo_credits() -> dict:
    try:
        r = requests.get('https://api.brevo.com/v3/account', headers=_BREVO_HEADERS, timeout=20)
        r.raise_for_status()
        plans = r.json().get('plan') or []
        send = [p.get('credits') for p in plans if p.get('creditsType') == 'sendLimit' and p.get('credits') is not None]
        return {'email': sum(send) if send else None}
    except Exception as e:
        print(f'⚠ Crediti Brevo non letti: {e}')
        return {'email': None}


def send_approval_reminder(plan: dict, now: datetime) -> None:
    g0 = plan['giorni'][0] if plan['giorni'] else {}
    n = g0.get('daInviare', 0)
    html_content = f"""<html><body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:20px">
<table width="560" style="background:#fff;border-radius:8px;padding:24px;margin:auto"><tr><td>
<h2 style="margin:0 0 12px;color:{ACCENT}">Piano follow-up di oggi: serve la tua approvazione</h2>
<p style="font-size:15px;line-height:1.5">Oggi sono pronti <b>{plan['pronteOra']['totale']}</b> follow-up importatori
(day7: {plan['pronteOra']['day7']}, day21: {plan['pronteOra']['day21']}, day35: {plan['pronteOra']['day35']}).<br>
Con il tetto attuale oggi ne partirebbero <b>{n}</b>.</p>
<p style="font-size:15px;line-height:1.5">Senza il tuo OK <b>non parte nessuna mail</b>. Apri il CRM, scheda <b>Programmato</b>,
e premi <b>Approva il piano di oggi</b>.</p>
<p><a href="https://shopilciliegio-ship-it.github.io/crm-importatori/" style="display:inline-block;background:{ACCENT};color:#fff;
padding:10px 18px;border-radius:6px;text-decoration:none">Apri il CRM</a></p>
<p style="color:#999;font-size:11px">Siena Wine CRM — promemoria automatico</p>
</td></tr></table></body></html>"""
    r = requests.post('https://api.brevo.com/v3/smtp/email', headers=_BREVO_HEADERS, json={
        'sender': {'name': SENDER_NAME, 'email': SENDER_EMAIL},
        'to': [{'email': DIGEST_RECIPIENT, 'name': 'Luca'}],
        'subject': f'⏰ Approva il piano follow-up di oggi ({plan["pronteOra"]["totale"]} pronti)',
        'htmlContent': html_content,
        'textContent': f'Follow-up pronti: {plan["pronteOra"]["totale"]}, oggi partirebbero {n}. '
                       f'Senza approvazione non parte nulla: CRM > Programmato > Approva il piano di oggi.',
        'tags': ['wine-crm', 'importatori-piano-promemoria'],
        'trackClicks': False, 'trackOpens': False,
    }, timeout=20)
    print('✓ Promemoria approvazione inviato' if r.ok else f'⚠ Promemoria fallito: {r.status_code} {r.text[:100]}')


def run_plan_mode() -> None:
    """--piano: calcola il piano, lo salva in data/piano-invii.json (letto dalla scheda "Programmato"
    del CRM) e, se il passo di invio è acceso e manca l'approvazione, manda il promemoria. NON invia follow-up."""
    print('=== Piano invii importatori ===')
    settings, _ = gh_get(SETTINGS_PATH)
    contacts, _snap, overrides_ok, _n = load_contacts_with_overrides()
    if not overrides_ok:
        print('✗ override non caricati: piano non aggiornato.')
        return
    tpls_raw, _ = gh_get(TEMPLATES_PATH)
    templates = tpls_raw if isinstance(tpls_raw, list) else []
    log_raw, _ = gh_get(LOG_PATH)
    log = log_raw.get('log', []) if isinstance(log_raw, dict) else []
    now = datetime.now(ROME)

    plan = build_plan(contacts, templates, log, settings, now)
    appr = approval_for_today(now)
    plan['approvazione'] = {'oggi': bool(appr), 'limite': (appr or {}).get('limit'), 'approvatoAt': (appr or {}).get('approvedAt')}
    print(f'Pronte ora: {plan["pronteOra"]["totale"]} (codice invio: {plan["pronteOra"]["verificaCodiceInvio"]}) | '
          f'oggi partirebbero {plan["giorni"][0]["daInviare"]} | approvato oggi: {bool(appr)} | passo attivo: {plan["followupPassoAttivo"]}')
    if plan['pronteOra']['totale'] != plan['pronteOra']['verificaCodiceInvio']:
        print('⚠ ATTENZIONE: il conteggio del piano e quello del codice di invio non coincidono — controllare.')
    gh_put(PLAN_PATH, plan, get_sha(PLAN_PATH), f'Piano invii — {now.strftime("%d/%m/%Y %H:%M")}')

    # Promemoria: solo se il passo di invio è davvero acceso, c'è roba da inviare e manca l'OK. Ai giri delle 6 e delle 12.
    if plan['followupPassoAttivo'] and not appr and plan['pronteOra']['totale'] > 0 and now.hour in (6, 7, 12, 13):
        send_approval_reminder(plan, now)


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

def persist_state(contacts: list, base_snap: dict, overrides_loaded_count: int,
                  log_pending: list, sent_total: int, now_str: str) -> bool:
    """Salva overrides + log email su GitHub. Ritorna True solo se tutto è stato salvato
    (se False, il chiamante deve smettere di inviare). Svuota log_pending dopo il salvataggio."""
    try:
        new_overrides = build_overrides_diff(contacts, base_snap)
        new_count = len(new_overrides)
        if overrides_loaded_count >= 10 and new_count < overrides_loaded_count * 0.5:
            print(f'✗ Crollo sospetto override: {overrides_loaded_count} → {new_count}. Salvataggio bloccato.')
            return False
        gh_put(OVERRIDES_PATH, new_overrides, get_sha(OVERRIDES_PATH),
               f'Follow-up importatori — {sent_total} email — {now_str}')
        if log_pending:
            log_raw, log_sha = gh_get(LOG_PATH)
            existing = log_raw.get('log', []) if isinstance(log_raw, dict) else []
            gh_put(LOG_PATH, {'log': existing + log_pending}, log_sha,
                   f'Email log importatori — {len(log_pending)} entries — {now_str}')
            log_pending.clear()
        print(f'  💾 stato salvato ({sent_total} email finora, {new_count} contatti con override)')
        return True
    except Exception as e:
        print(f'✗ Salvataggio stato FALLITO: {e}')
        return False


def main():
    if '--piano' in sys.argv:
        run_plan_mode()
        return
    print('=== Follow-up Importatori — Siena Wine ===')

    settings, _ = gh_get(SETTINGS_PATH)
    auto_send   = settings.get('emailAutoSendImportatori', False)
    test_mode   = settings.get('testModeImportatori', True)

    if not auto_send:
        print('⏸ Invio automatico importatori disabilitato. Nessuna email inviata.')
        if _is_digest_run():
            send_daily_digest([], [], 0, test_mode, 0)
        return

    run_cap = MAX_SENDS_PER_RUN
    if test_mode:
        print(f'🧪 TEST MODE — email a {BCC_EMAIL}')
    else:
        print('👥 Produzione — email ai contatti reali')
        # Approvazione giornaliera: senza l'OK di Luca dal CRM ("Approva il piano di oggi") non parte nulla.
        today_it = datetime.now(ROME)
        appr = approval_for_today(today_it)
        if not appr:
            print('⏸ Piano di oggi NON approvato dal CRM: nessun follow-up inviato.')
            return
        log_raw, _ = gh_get(LOG_PATH)
        done_today = sent_today(log_raw.get('log', []) if isinstance(log_raw, dict) else [], today_it)
        remaining = int(appr.get('limit') or 0) - done_today
        if remaining <= 0:
            print(f'⏹ Limite approvato per oggi ({appr.get("limit")}) già raggiunto ({done_today} inviati).')
            return
        run_cap = min(MAX_SENDS_PER_RUN, remaining)
        print(f'✅ Piano approvato: limite {appr.get("limit")}, già inviati oggi {done_today}, in questo giro al massimo {run_cap}.')

    contacts, base_snap, overrides_ok, overrides_loaded_count = load_contacts_with_overrides()
    tpls_raw, _ = gh_get(TEMPLATES_PATH)
    templates   = tpls_raw if isinstance(tpls_raw, list) else []

    if not templates:
        print('✗ templates.json non trovato. Esci.')
        return

    if not overrides_ok:
        print('✗ contatti-overrides.json non caricato correttamente in questo run — '
              'esco senza inviare email per non rischiare di salvare un diff vuoto '
              'che azzererebbe gli override esistenti.')
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
    log_pending = []          # entries del log non ancora salvate su GitHub
    stopped_early = False
    started_at = time.time()
    now_str = datetime.now().strftime('%d/%m/%Y %H:%M')

    # chi sta per uscire dalla finestra va per primo (stesso ordine usato dal piano)
    active.sort(key=lambda c: (followup_window(c) or {'expire': float('inf')})['expire'])
    for c in active:
        if not test_mode and sent >= run_cap:
            print(f'⏹ Tetto di {run_cap} invii per questo giro raggiunto: il resto al prossimo giro.')
            stopped_early = True
            break
        if time.time() - started_at > TIME_BUDGET_S:
            print(f'⏹ Budget di tempo ({TIME_BUDGET_S}s) esaurito: il resto al prossimo giro.')
            stopped_early = True
            break
        name     = c.get('company') or c.get('name', '?')
        to_email, to_name = step1_target(c)
        print(f'\n  {name} | status={c.get("status")} | evs={len(c.get("brevoEvents") or [])}')

        step_label, tpl, next_step = should_send_followup(c, templates, now_ms)
        if not step_label:
            continue
        if not tpl:
            print(f'    ⚠ template mancante per {step_label}')
            continue
        if not to_email:
            print(f'    ⚠ nessuna casella valida per {name} (tutte bloccate/mancanti) — salto')
            continue

        print(f'    → {step_label} | tpl={tpl.get("id","?")} "{tpl.get("name","")[:40]}"')
        subject, body = render_template(tpl, c, to_email, to_name)
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
            log_entry = {'contactId': c['id'], 'company': name, 'type': step_label,
                         'to': to_email, 'subject': subject, 'sentAt': now_ms, 'messageId': msg_id}
            log_new.append(log_entry)
            log_pending.append(log_entry)

            # Salvataggio a blocchi: se fallisce, STOP agli invii (niente doppioni al giro dopo).
            if not test_mode and sent % SAVE_EVERY == 0:
                if not persist_state(contacts, base_snap, overrides_loaded_count, log_pending, sent, now_str):
                    stopped_early = True
                    break

        time.sleep(0.6)

    if test_mode:
        print(f'\n🧪 Test: {sent} email → {BCC_EMAIL}. contatti-overrides.json non modificato.')
    else:
        if sent > 0 or sync_count > 0 or log_pending:
            if persist_state(contacts, base_snap, overrides_loaded_count, log_pending, sent, now_str):
                print(f'\n✓ {sent} email inviate in questo giro, stato salvato.')
            else:
                print('\n✗ Salvataggio finale fallito: i prossimi giri NON devono inviare finché non è risolto.')
                raise SystemExit(1)
            if cold_count:
                print(f'  {cold_count} contatti → cold (sequenza completata)')
        elif sent == 0:
            print('\nNessun follow-up da inviare.')
        if stopped_early:
            print('ℹ Giro interrotto in anticipo (tetto/tempo): vedi messaggi sopra.')

    if _is_digest_run():
        send_daily_digest(contacts, log_new, now_ms, test_mode, sync_count)
    else:
        print(f'⏭ Digest skippato — parte solo al run delle {DIGEST_HOUR_UTC}:00 UTC')


if __name__ == '__main__':
    main()
