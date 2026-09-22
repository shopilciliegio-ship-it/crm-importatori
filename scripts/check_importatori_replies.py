"""
Controllo risposte importatori — Il Ciliegio CRM
Eseguito ogni giorno da .github/workflows/check_importatori_replies.yml (gira come reserve
schedule GitHub: a differenza dei post social qui il timing non è critico, un check "qualche
ora dopo" va benissimo, quindi niente timer Cloudflare per questo job).

Logica (riscritta il 22/9/2026 — v1 filtrava per indirizzo esatto e scartava in silenzio tutto
il resto: perdeva le risposte arrivate da un indirizzo diverso da quello a cui avevamo scritto,
persona diversa in azienda o casella generica che risponde al posto della persona contattata):
  - Legge data/inbox-risposte.json (lastUid processato, pending in attesa di revisione, risolte
    passate).
  - Si collega in sola lettura (readonly) alla casella luca@sienawine.it via IMAP e scarica TUTTE
    le email arrivate dal 18/9/2026 (inizio campagna) in poi, non ancora viste (UID > lastUid).
  - Per OGNI email (non solo quelle che matchano un indirizzo noto): prova ad agganciarla a un
    contatto importatore in due modi, in ordine di affidabilità — (1) header di threading
    (In-Reply-To/References contro i Message-ID delle nostre email inviate: sopravvive a risposte
    da un indirizzo diverso da quello a cui abbiamo scritto), (2) indirizzo del mittente contro
    brevoEvents[].toEmail. Se nessuno dei due matcha, l'email resta comunque in coda — segnata
    "non collegata a un contatto" — invece di sparire senza che nessuno la veda.
  - OGNI email (collegata o no, bounce tecnico a parte) viene letta e riassunta da Claude: chi
    scrive, se è una risposta diretta alla campagna, cosa dice (tradotto in italiano se serve),
    categoria proposta. Niente più scorciatoie che saltano la lettura vera.
  - Aggiunge tutto a "pending" (il CRM lo mostra a Luca una alla volta in un popup di revisione —
    vedi js/risposte.js). NON tocca mai lo status dei contatti: quello lo fa solo il CRM quando
    Luca conferma/corregge, riusando setManualStatus() già esistente.

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

CONTATTI_PATH       = 'data/contatti.json'
OVERRIDES_PATH       = 'data/contatti-overrides.json'
INBOX_RISPOSTE_PATH  = 'data/inbox-risposte.json'

# Fisso, non una finestra mobile: inizio vero della campagna (primi invii 18/9/2026). Una finestra
# mobile "ultimi 30 giorni" finirebbe per perdere l'inizio campagna col passare delle settimane.
CAMPAIGN_START = '18-Sep-2026'

MAX_EMAIL_PER_RUN = 150  # margine di sicurezza, non un limite tecnico — vedi timeout-minutes:20 del job.

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


def extract_display_name(from_header):
    name, addr = email.utils.parseaddr(from_header or '')
    return decode_header(name) or addr or ''


def extract_msgids(header_val):
    """In-Reply-To/References possono contenere uno o più Message-ID tra '<' '>'."""
    if not header_val:
        return []
    return re.findall(r'<[^<>]+>', header_val)


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


CLASSIFY_SYSTEM_PROMPT = """Sei l'assistente che legge e riassume in italiano le email ricevute nella casella di
Il Ciliegio / Siena Wine (azienda vinicola italiana), usata anche per contattare importatori di vino esteri e
raccoglierne le risposte.

Per OGNI email che ti viene mostrata, rispondi SOLO con un oggetto JSON valido (niente testo fuori, niente
blocco markdown):

{
  "riassunto": "1-3 frasi in italiano: chi scrive (persona/ruolo/azienda se si capisce) e cosa dice — se
                l'email è in un'altra lingua, traduci il contenuto essenziale, non lasciarlo nella lingua originale",
  "risposta_diretta": true o false,
  "categoria": "bounce" | "non_interessato" | "risposta" | "cliente" | "fuori_sede" | "incerto" | "non_pertinente",
  "motivo": "una frase breve in italiano che spiega la categoria scelta",
  "data_rientro": "YYYY-MM-DD oppure null — SOLO se categoria è fuori_sede e c'è una data di rientro esplicita",
  "email_alternativa": "un indirizzo email ESPLICITAMENTE scritto nel testo come contatto alternativo a cui
                         scrivere (es. risposta automatica di instradamento tipo 'per acquisti scrivi a
                         orders@azienda.com'), oppure null se il testo non scrive nessun indirizzo email
                         alternativo (anche se nomina persone o reparti SENZA email, metti null: non inventare
                         un indirizzo che non è scritto per esteso nel testo)"
}

CONTESTO: prima del testo dell'email ti dico se è già tecnicamente risultata collegata (stesso thread o stesso
indirizzo) a un'email che abbiamo mandato noi per proporre la distribuzione dei vini Il Ciliegio/Siena Wine a un
importatore estero. Se il contesto dice che è collegata, "risposta_diretta" deve essere true. Se dice che NON è
collegata a nessun invio nostro, giudica tu dal contenuto: sembra comunque una reazione (anche indiretta, es.
girata da un collega) a quella proposta commerciale? Se l'email non c'entra nulla (newsletter, notifiche di
servizio, spam non collegabile) → "risposta_diretta": false, "categoria": "non_pertinente".

Criteri per "categoria":
- "bounce": errore di consegna tecnico (mailbox piena, indirizzo inesistente, dominio non risolvibile) — non è una persona che scrive.
- "fuori_sede": risposta automatica che dice che la persona è assente/in ferie/in viaggio, SENZA esprimere interesse o disinteresse. Include risposte "automatic reply"/"out of office" anche se il testo è formulato in modo insolito (es. sembra un errore di consegna ma è chiaramente scritto da/per una persona che tornerà, non un errore SMTP).
- "non_interessato": la persona risponde dicendo esplicitamente che non è interessata, ha già un fornitore, non serve, "no grazie", chiede di essere rimossa dalla lista, ecc.
- "cliente": la persona vuole ESPLICITAMENTE avviare un rapporto commerciale, fare un ordine, diventare distributore, chiede un listino/contratto per procedere subito — un impegno concreto, non solo curiosità.
- "risposta": qualunque altra risposta genuina di una persona pertinente alla proposta (fa domande, chiede più informazioni, è vagamente interessata ma non si impegna, risposta neutra).
- "incerto": è collegata/pertinente ma non riesci a classificarla con sicurezza in nessuna delle precedenti.
- "non_pertinente": non ha niente a che fare con la campagna vino (newsletter, notifica di servizio, spam).

Rispondi SEMPRE e SOLO con l'oggetto JSON."""


class FatalAPIError(Exception):
    pass


def claude_classify(subject, body, contesto):
    prompt = f"CONTESTO: {contesto}\n\nOggetto: {subject}\n\nCorpo:\n{body or '(vuoto)'}"
    req_body = {
        'model':       'claude-haiku-4-5',
        'system':      CLASSIFY_SYSTEM_PROMPT,
        'messages':    [{'role': 'user', 'content': prompt}],
        'temperature': 0.1,
        'max_tokens':  500,
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
    'non_pertinente':   None,
}


def build_indices(contatti, overrides):
    """(email_index, msgid_index, by_id).
    email_index: indirizzo (lower) -> contactId, da brevoEvents[].toEmail (fonte affidabile di "a
    chi abbiamo scritto davvero") + fallback su contactEmail/email del contatto base.
    msgid_index: Message-ID (con <>, come registrato da Brevo) -> contactId — usato per riconoscere
    una risposta dal thread (In-Reply-To/References) anche se arriva da UN INDIRIZZO DIVERSO da
    quello a cui avevamo scritto (persona diversa in azienda, casella generica che risponde, ecc.)."""
    by_id = {c['id']: c for c in contatti.get('contacts', [])}
    email_index, msgid_index = {}, {}
    for cid, ov in overrides.items():
        for ev in (ov.get('brevoEvents') or []):
            to = (ev.get('toEmail') or '').strip().lower()
            if to:
                email_index[to] = cid
            mid = (ev.get('messageId') or '').strip()
            if mid:
                msgid_index[mid] = cid
    for cid, c in by_id.items():
        for field in ('contactEmail', 'email'):
            addr = (c.get(field) or '').strip().lower()
            if addr and addr not in email_index:
                email_index[addr] = cid
    return email_index, msgid_index, by_id


def company_for(contact_id, by_id):
    c = by_id.get(contact_id) or {}
    return c.get('company') or c.get('brandName') or contact_id


def rebuild_pattern(risolte):
    """Un mittente rivisto in passato con esito SEMPRE coerente diventa una nota informativa per
    le prossime volte (mostrata nel popup, non usata più per saltare la lettura — vedi nota 22/9)."""
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
    email_index, msgid_index, by_id = build_indices(contatti, overrides)
    print(f'📇 {len(email_index)} indirizzi noti, {len(msgid_index)} Message-ID di nostre email inviate.')

    print(f'📡 Mi collego a {IMAP_HOST}:{IMAP_PORT} come {IMAP_USER}...')
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(IMAP_USER, IMAP_PASSWORD)
    mail.select('INBOX', readonly=True)

    last_uid = int(data.get('lastUid') or 0)
    typ, res = mail.uid('search', None, f'(SINCE {CAMPAIGN_START}) UID {last_uid + 1}:*')
    uids = [int(u) for u in (res[0] or b'').split()]
    uids = [u for u in uids if u > last_uid]  # '*' può ripetere l'ultimo UID esistente se non ce ne sono di nuovi
    print(f'📬 {len(uids)} email nuove da UID {last_uid + 1} in poi (dal {CAMPAIGN_START}).')

    if len(uids) > MAX_EMAIL_PER_RUN:
        print(f'⚠ Troppe email nuove ({len(uids)}) — elaboro solo le prime {MAX_EMAIL_PER_RUN}, il resto al prossimo run.')
        uids = uids[:MAX_EMAIL_PER_RUN]

    max_uid_seen = last_uid
    nuove_pending = 0
    non_collegate = 0

    for uid in uids:
        max_uid_seen = max(max_uid_seen, uid)
        typ, msg_data = mail.uid('fetch', str(uid), '(RFC822)')
        if typ != 'OK' or not msg_data or not msg_data[0]:
            continue
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        # Già in pending per questo stesso UID? (rilancio manuale ravvicinato) — non duplicare.
        if any(p.get('uid') == uid for p in data['pending']):
            continue

        from_addr = extract_addr(msg.get('From'))
        from_name = extract_display_name(msg.get('From'))
        subject   = decode_header(msg.get('Subject'))
        date_hdr  = msg.get('Date')
        try:
            date_iso = email.utils.parsedate_to_datetime(date_hdr).astimezone(timezone.utc).isoformat()
        except Exception:
            date_iso = datetime.now(timezone.utc).isoformat()

        # 1) Aggancio per thread (sopravvive a una risposta arrivata da un indirizzo diverso da
        #    quello a cui abbiamo scritto) — più affidabile dell'indirizzo. 2) fallback per indirizzo.
        contact_id, header_match = None, False
        for mid in extract_msgids(msg.get('In-Reply-To')) + extract_msgids(msg.get('References')):
            if mid in msgid_index:
                contact_id, header_match = msgid_index[mid], True
                break
        if not contact_id:
            contact_id = email_index.get(from_addr)
        collegato = contact_id is not None

        if collegato:
            company = company_for(contact_id, by_id)
            contesto = (f'Collegata (via {"thread/risposta diretta" if header_match else "stesso indirizzo a cui abbiamo scritto"}) '
                        f'a una nostra email inviata al contatto "{company}".')
        else:
            company = from_name or from_addr or '(mittente sconosciuto)'
            contesto = 'NON risulta collegata tecnicamente a nessuna email che abbiamo inviato — giudica dal contenuto.'
            non_collegate += 1

        print(f'  ✉ UID {uid}  {from_addr}  "{subject[:60]}"  {"🔗" if collegato else "❓non collegata"}')

        body = extract_body_text(msg)
        suggested_status, reason, riassunto, data_rientro, email_alt = None, '', '', None, None
        risposta_diretta = True if header_match else (None if collegato else False)

        if BOUNCE_SENDER_RE.search(from_addr):
            suggested_status = 'blacklisted' if collegato else None
            reason = 'Mittente tecnico di bounce (mailer-daemon/postmaster).'
            riassunto = 'Notifica automatica di mancata consegna (errore tecnico del server email).'
            confidence = 'regola'
        else:
            confidence = 'ai'
            try:
                result = claude_classify(subject, body, contesto)
            except FatalAPIError as e:
                print(f'❌ {e} — interrompo (le altre email restano da fare al prossimo run).')
                break
            if result:
                categoria = result.get('categoria')
                suggested_status = CATEGORIA_TO_STATUS.get(categoria) if collegato else None
                reason = result.get('motivo') or categoria
                riassunto = result.get('riassunto') or ''
                data_rientro = result.get('data_rientro')
                email_alt = (result.get('email_alternativa') or '').strip() or None
                if header_match is False:  # non già determinato dal thread: usa il giudizio AI
                    risposta_diretta = bool(result.get('risposta_diretta'))
            else:
                reason = 'Classificazione AI non riuscita — controlla a mano.'
                riassunto = body[:200]

        data['pending'].append({
            'id': f'ir_{uid}',
            'uid': uid,
            'contactId': contact_id,
            'nonCollegato': not collegato,
            'company': company,
            'from': from_addr,
            'mittenteNome': from_name,
            'subject': subject,
            'date': date_iso,
            'snippet': body[:400],
            'riassunto': riassunto,
            'rispostaDiretta': risposta_diretta,
            'suggestedStatus': suggested_status,
            'reason': reason,
            'confidence': confidence,
            'dataRientro': data_rientro,
            'emailAlternativa': email_alt,
        })
        nuove_pending += 1

    mail.logout()

    data['lastUid'] = max_uid_seen
    data['pattern'] = rebuild_pattern(data['risolte'])

    sha = gh_put(INBOX_RISPOSTE_PATH, data, sha, f'Controllo risposte importatori — {nuove_pending} nuove, {non_collegate} non collegate ({datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")} UTC)')
    print(f'\n✅ Fatto. {nuove_pending} nuove email in coda ({non_collegate} non collegate a un contatto), {len(data["pending"])} totali in attesa. lastUid={max_uid_seen}.')


if __name__ == '__main__':
    main()
