"""
Controllo risposte importatori — Il Ciliegio CRM
Eseguito ogni giorno da .github/workflows/check_importatori_replies.yml (gira come reserve
schedule GitHub: a differenza dei post social qui il timing non è critico, un check "qualche
ora dopo" va benissimo, quindi niente timer Cloudflare per questo job).

Logica:
  - Legge data/inbox-risposte.json (lastUid processato, pending in attesa di revisione, risolte
    passate, pattern imparati dalle correzioni di Luca nel CRM).
  - Si collega in sola lettura (readonly) alla casella luca@sienawine.it via IMAP e scarica solo
    le email arrivate DOPO lastUid (mai le stesse due volte).
  - Per ogni email nuova, controlla se il mittente corrisponde a un indirizzo a cui abbiamo
    scritto (brevoEvents[].toEmail nei contatti importatori) — se non corrisponde a nessuno, la
    ignora (non è una risposta a una nostra email).
  - Classifica ogni corrispondenza: prima controlla data/inbox-risposte.json["pattern"] (mittenti
    già rivisti in passato da Luca — nessuna chiamata AI, istantaneo), poi regole semplici per i
    bounce tecnici inequivocabili (mailer-daemon/postmaster), infine Claude per tutto il resto
    (legge il corpo, non solo l'oggetto — un oggetto tipo "Delivery attempt unsuccessful" può
    benissimo essere un fuori sede vero scritto da una persona, non un bounce tecnico).
  - Aggiunge le corrispondenze nuove a "pending" (il CRM le mostra a Luca una alla volta in un
    popup di revisione — vedi js/risposte.js). NON tocca mai lo status dei contatti: quello lo fa
    solo il CRM quando Luca conferma/corregge, riusando setManualStatus() già esistente.
  - Ricostruisce "pattern" dalle "risolte": un mittente rivisto in passato con esito sempre
    coerente diventa una regola automatica per le prossime volte.

Nessuna dipendenza npm/pip oltre a requests (già in requirements.txt) e la libreria email di
Python (stdlib).
"""

import base64
import email
import email.header
import email.utils
import imaplib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

# ── Config ───────────────────────────────────────────────────────────────────
IMAP_HOST     = os.environ['SIENAWINE_IMAP_HOST']
IMAP_PORT     = int(os.environ.get('SIENAWINE_IMAP_PORT') or 993)
IMAP_USER     = os.environ['SIENAWINE_IMAP_USER']
IMAP_PASSWORD = os.environ['SIENAWINE_IMAP_PASSWORD']
CLAUDE_API_KEY = os.environ['CLAUDE_API_KEY']
GH_TOKEN       = os.environ['GH_TOKEN']
GH_REPO        = os.environ['GH_REPO']

CONTATTI_PATH      = 'data/contatti.json'
OVERRIDES_PATH      = 'data/contatti-overrides.json'
INBOX_RISPOSTE_PATH = 'data/inbox-risposte.json'

MAX_EMAIL_PER_RUN = 40  # margine di sicurezza: non elaborare centinaia di email in un run solo

_GH_HEADERS = {
    'Authorization': f'token {GH_TOKEN}',
    'Accept':        'application/vnd.github.v3+json',
}

DEFAULT_DATA = {'lastUid': 0, 'pending': [], 'risolte': [], 'pattern': {}}

# Mittenti tecnici di bounce: nessuna AI necessaria, è sempre e solo un indirizzo non recapitabile.
BOUNCE_SENDER_RE = re.compile(r'(mailer-daemon|postmaster|mail delivery subsystem|mail delivery system)', re.I)


def gh_get(path):
    url = f'https://api.github.com/repos/{GH_REPO}/contents/{path}'
    r = requests.get(url, headers=_GH_HEADERS, timeout=30)
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    d = r.json()
    raw = (d.get('content') or '').replace('\n', '')
    if raw:
        content = base64.b64decode(raw).decode('utf-8')
    else:
        rr = requests.get(d['download_url'], timeout=30)
        rr.raise_for_status()
        content = rr.text
    return json.loads(content), d['sha']


def gh_put(path, data, sha, message):
    url = f'https://api.github.com/repos/{GH_REPO}/contents/{path}'
    content = base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')).decode('utf-8')
    body = {'message': message, 'content': content}
    if sha:
        body['sha'] = sha
    r = requests.put(url, headers=_GH_HEADERS, json=body, timeout=30)
    r.raise_for_status()
    return r.json()['content']['sha']


def decode_header(raw):
    if not raw:
        return ''
    parts = email.header.decode_header(raw)
    out = ''
    for part, enc in parts:
        out += part.decode(enc or 'utf-8', errors='replace') if isinstance(part, bytes) else part
    return out


def extract_addr(from_header):
    name, addr = email.utils.parseaddr(from_header or '')
    return (addr or '').strip().lower()


def extract_body_text(msg, max_chars=2500):
    """Preferisce text/plain; se non c'è, spoglia l'HTML dai tag. Ignora allegati."""
    def strip_html(html):
        html = re.sub(r'<(script|style)[\s\S]*?</\1>', '', html, flags=re.I)
        html = re.sub(r'<br\s*/?>|</p>|</div>', '\n', html, flags=re.I)
        html = re.sub(r'<[^>]+>', ' ', html)
        html = re.sub(r'[ \t]+', ' ', html)
        html = re.sub(r'\n{3,}', '\n\n', html)
        return html.strip()

    plain, html = '', ''
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get('Content-Disposition') or '')
            if 'attachment' in disp:
                continue
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or 'utf-8'
                text = payload.decode(charset, errors='replace')
            except Exception:
                continue
            if ctype == 'text/plain' and not plain:
                plain = text
            elif ctype == 'text/html' and not html:
                html = text
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or 'utf-8'
            text = payload.decode(charset, errors='replace') if payload else ''
        except Exception:
            text = ''
        if msg.get_content_type() == 'text/html':
            html = text
        else:
            plain = text

    body = plain.strip() or strip_html(html)
    return body[:max_chars]


CLASSIFY_SYSTEM_PROMPT = """Sei l'assistente che classifica le risposte ricevute dagli importatori di vino contattati
da Il Ciliegio / Siena Wine (azienda vinicola italiana che cerca distributori esteri).

Leggi l'email (oggetto + corpo) e classificala in UNA di queste categorie, rispondendo SOLO con un
oggetto JSON valido (niente testo fuori, niente blocco markdown):

{
  "categoria": "bounce" | "non_interessato" | "risposta" | "cliente" | "fuori_sede" | "incerto",
  "motivo": "una frase breve in italiano che spiega la classificazione",
  "data_rientro": "YYYY-MM-DD oppure null — SOLO se categoria è fuori_sede e c'è una data di rientro esplicita"
}

Criteri:
- "bounce": è un errore di consegna tecnico (mailbox piena, indirizzo inesistente, dominio non risolvibile) — non è una persona che scrive.
- "fuori_sede": risposta automatica che dice che la persona è assente/in ferie/in viaggio, SENZA esprimere interesse o disinteresse (torna dopo, verrà letta al ritorno). Include anche risposte "automatic reply"/"out of office" anche se il testo è formulato in modo insolito (es. sembra un errore di consegna ma è chiaramente scritto da/per una persona che tornerà, non un errore SMTP).
- "non_interessato": la persona risponde dicendo esplicitamente che non è interessata, ha già un fornitore, non serve, "no grazie", chiede di essere rimossa dalla lista, ecc.
- "cliente": la persona vuole ESPLICITAMENTE avviare un rapporto commerciale, fare un ordine, diventare distributore, chiede un listino/contratto per procedere subito — un impegno concreto, non solo curiosità.
- "risposta": qualunque altra risposta genuina di una persona (fa domande, chiede più informazioni, è vagamente interessata ma non si impegna, risposta neutra) — è la categoria di default per un vero essere umano che ha scritto qualcosa di pertinente.
- "incerto": non riesci a classificarla con sicurezza in nessuna delle precedenti (es. email non pertinente, spam, contenuto ambiguo).

Rispondi SEMPRE e SOLO con l'oggetto JSON."""


class FatalAPIError(Exception):
    pass


def claude_classify(subject, body):
    prompt = f"Oggetto: {subject}\n\nCorpo:\n{body or '(vuoto)'}"
    req_body = {
        'model':       'claude-haiku-4-5',
        'system':      CLASSIFY_SYSTEM_PROMPT,
        'messages':    [{'role': 'user', 'content': prompt}],
        'temperature': 0.1,
        'max_tokens':  300,
    }
    headers = {
        'x-api-key':         CLAUDE_API_KEY,
        'anthropic-version': '2023-06-01',
        'Content-Type':      'application/json',
    }
    for attempt in range(4):
        try:
            r = requests.post('https://api.anthropic.com/v1/messages', headers=headers, json=req_body, timeout=60)
            if r.status_code == 429:
                wait = int(r.headers.get('retry-after', 0) or 0) or [15, 30, 60][min(attempt, 2)]
                print(f'  ⏳ Rate limit Claude — attendo {wait}s')
                time.sleep(wait)
                continue
            if r.status_code in (401, 403):
                raise FatalAPIError(f'Claude {r.status_code}: chiave non valida/revocata')
            if not r.ok:
                print(f'  ⚠ Claude {r.status_code}: {r.text[:200]}')
                return None
            data = r.json()
            text = ''.join(b.get('text', '') for b in data.get('content', []) if b.get('type') == 'text').strip()
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'```\s*$', '', text).strip()
            return json.loads(text)
        except FatalAPIError:
            raise
        except Exception as e:
            print(f'  ⚠ Errore classificazione Claude: {e}')
            if attempt == 3:
                return None
            time.sleep(5)
    return None


CATEGORIA_TO_STATUS = {
    'bounce':          'blacklisted',
    'non_interessato': 'cold',
    'risposta':        'replied',
    'cliente':         'client',
    'fuori_sede':       None,  # solo informativo, nessun cambio di stato proposto
    'incerto':          None,
}


def build_email_index(contatti, overrides):
    """email (lower) -> contactId, da brevoEvents[].toEmail (unica fonte affidabile di 'a chi
    abbiamo scritto davvero') + fallback su contactEmail/email del contatto base."""
    by_id = {c['id']: c for c in contatti.get('contacts', [])}
    index = {}
    for cid, ov in overrides.items():
        for ev in (ov.get('brevoEvents') or []):
            to = (ev.get('toEmail') or '').strip().lower()
            if to:
                index[to] = cid
    for cid, c in by_id.items():
        for field in ('contactEmail', 'email'):
            addr = (c.get(field) or '').strip().lower()
            if addr and addr not in index:
                index[addr] = cid
    return index, by_id


def company_for(contact_id, by_id, overrides):
    c = by_id.get(contact_id) or {}
    return c.get('company') or c.get('brandName') or contact_id


def rebuild_pattern(risolte):
    """Un mittente rivisto in passato con esito SEMPRE coerente diventa una regola automatica.
    Se in passato è stato corretto in modi diversi, non ci si fida più del pattern — meglio
    richiedere di nuovo l'AI/la revisione umana che sbagliare in automatico."""
    by_sender = {}
    for r in risolte:
        sender = (r.get('from') or '').strip().lower()
        if not sender:
            continue
        by_sender.setdefault(sender, set()).add(r.get('finalStatus'))
    return {s: list(v)[0] for s, v in by_sender.items() if len(v) == 1}


def main():
    data, sha = gh_get(INBOX_RISPOSTE_PATH)
    if data is None:
        data = dict(DEFAULT_DATA)
    for k, v in DEFAULT_DATA.items():
        data.setdefault(k, v)

    contatti, _ = gh_get(CONTATTI_PATH)
    overrides, _ = gh_get(OVERRIDES_PATH)
    overrides = overrides or {}
    email_index, by_id = build_email_index(contatti, overrides)
    print(f'📇 {len(email_index)} indirizzi a cui abbiamo scritto (da brevoEvents + contatti base).')

    print(f'📡 Mi collego a {IMAP_HOST}:{IMAP_PORT} come {IMAP_USER}...')
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(IMAP_USER, IMAP_PASSWORD)
    mail.select('INBOX', readonly=True)

    last_uid = int(data.get('lastUid') or 0)
    # SINCE oltre a UID: senza, il primo run (lastUid=0, visto il 22/9/2026 — 425 email trovate,
    # quasi tutte vecchie e non pertinenti) macina TUTTA la cronologia della casella 40 alla volta
    # invece della posta recente. 30 giorni coprono comodamente l'intera campagna (iniziata il
    # 18/9/2026) e lasciano indietro per sempre solo email più vecchie della campagna stessa.
    since_str = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%d-%b-%Y')
    typ, res = mail.uid('search', None, f'(SINCE {since_str}) UID {last_uid + 1}:*')
    uids = [int(u) for u in (res[0] or b'').split()]
    uids = [u for u in uids if u > last_uid]  # '*' può ripetere l'ultimo UID esistente se non ce ne sono di nuovi
    print(f'📬 {len(uids)} email nuove da UID {last_uid + 1} in poi (ultimi 30 giorni).')

    if len(uids) > MAX_EMAIL_PER_RUN:
        print(f'⚠ Troppe email nuove ({len(uids)}) — elaboro solo le prime {MAX_EMAIL_PER_RUN}, il resto al prossimo run.')
        uids = uids[:MAX_EMAIL_PER_RUN]

    max_uid_seen = last_uid
    nuove_pending = 0

    for uid in uids:
        max_uid_seen = max(max_uid_seen, uid)
        typ, msg_data = mail.uid('fetch', str(uid), '(RFC822)')
        if typ != 'OK' or not msg_data or not msg_data[0]:
            continue
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        from_addr = extract_addr(msg.get('From'))
        contact_id = email_index.get(from_addr)
        if not contact_id:
            continue  # non è una risposta a una nostra email

        subject = decode_header(msg.get('Subject'))
        date_hdr = msg.get('Date')
        try:
            date_iso = email.utils.parsedate_to_datetime(date_hdr).astimezone(timezone.utc).isoformat()
        except Exception:
            date_iso = datetime.now(timezone.utc).isoformat()

        # Già in pending o già risolta per questo stesso UID? Non dovrebbe succedere (lastUid
        # avanza sempre), ma per sicurezza non duplicare.
        if any(p.get('uid') == uid for p in data['pending']):
            continue

        print(f'  ✉ UID {uid}  {from_addr}  "{subject[:60]}"')

        body = extract_body_text(msg)
        suggested_status, reason, confidence, data_rientro = None, '', 'ai', None

        if BOUNCE_SENDER_RE.search(from_addr):
            suggested_status, reason, confidence = 'blacklisted', 'Mittente tecnico di bounce (mailer-daemon/postmaster).', 'regola'
        elif from_addr in data['pattern']:
            suggested_status = data['pattern'][from_addr]
            reason = 'Classificato in automatico: stesso mittente di una risposta già rivista in passato.'
            confidence = 'pattern'
        else:
            try:
                result = claude_classify(subject, body)
            except FatalAPIError as e:
                print(f'❌ {e} — interrompo (le altre email restano da fare al prossimo run).')
                break
            if result:
                categoria = result.get('categoria')
                suggested_status = CATEGORIA_TO_STATUS.get(categoria)
                reason = result.get('motivo') or categoria
                data_rientro = result.get('data_rientro')
            else:
                reason = 'Classificazione AI non riuscita — controlla a mano.'

        data['pending'].append({
            'id': f'ir_{uid}',
            'uid': uid,
            'contactId': contact_id,
            'company': company_for(contact_id, by_id, overrides),
            'from': from_addr,
            'subject': subject,
            'date': date_iso,
            'snippet': body[:400],
            'suggestedStatus': suggested_status,
            'reason': reason,
            'confidence': confidence,
            'dataRientro': data_rientro,
        })
        nuove_pending += 1

    mail.logout()

    data['lastUid'] = max_uid_seen
    data['pattern'] = rebuild_pattern(data['risolte'])

    sha = gh_put(INBOX_RISPOSTE_PATH, data, sha, f'Controllo risposte importatori — {nuove_pending} nuove ({datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")} UTC)')
    print(f'\n✅ Fatto. {nuove_pending} nuove email in coda di revisione ({len(data["pending"])} totali in attesa). lastUid={max_uid_seen}.')


if __name__ == '__main__':
    main()
