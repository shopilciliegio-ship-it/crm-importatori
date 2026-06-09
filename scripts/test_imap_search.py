"""
Diagnostica IMAP — script usa e getta per capire perché la ricerca Gmail
non trova le email "Invio Ordine Azienda Agricola Il Ciliegio ...".
Prova diverse formulazioni del criteria di ricerca e mostra quante email
trova ciascuna, coi relativi oggetti.

Uso:
    set GMAIL_USER=shop.ilciliegio@gmail.com
    set GMAIL_APP_PASSWORD=...
    python scripts/test_imap_search.py
"""

import imaplib
import email
import email.header
import os
from datetime import datetime, timedelta, timezone

GMAIL_USER         = os.environ['GMAIL_USER']
GMAIL_APP_PASSWORD = os.environ['GMAIL_APP_PASSWORD']


def decode(raw):
    parts = email.header.decode_header(raw or '')
    out = ''
    for part, enc in parts:
        out += part.decode(enc or 'utf-8', errors='replace') if isinstance(part, bytes) else part
    return out


def run(mail, label, criteria):
    print(f'\n--- {label} ---')
    print(f'    criteria: {criteria}')
    try:
        typ, nums = mail.search(None, criteria)
        ids = (nums[0] or b'').split()
        print(f'    risposta: {typ}  —  {len(ids)} email trovate')
        for num in ids:
            _, data = mail.fetch(num, '(BODY[HEADER.FIELDS (SUBJECT DATE)])')
            hdr = data[0][1].decode('utf-8', errors='replace')
            subj_line = next((l for l in hdr.splitlines() if l.lower().startswith('subject:')), '')
            print(f'      • {decode(subj_line[8:].strip())}')
    except Exception as e:
        print(f'    ERRORE: {e}')


def main():
    since_date = datetime.now(timezone.utc) - timedelta(days=5)
    since_str  = since_date.strftime('%d-%b-%Y')

    mail = imaplib.IMAP4_SSL('imap.gmail.com')
    mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    mail.select('inbox')

    print(f'Account: {GMAIL_USER}   |   since_str: {since_str}')

    run(mail, 'A) solo SUBJECT Invio Ordine',
        '(SUBJECT "Invio Ordine")')

    run(mail, 'B) SINCE + SUBJECT Invio Ordine (no OR)',
        f'(SINCE {since_str} SUBJECT "Invio Ordine")')

    run(mail, 'C) criteria attuale dello script (OR annidato)',
        f'(SINCE {since_str} OR (OR SUBJECT "New Order" SUBJECT "New Paid Order") SUBJECT "Invio Ordine")')

    run(mail, 'D) OR semplice a due rami: SINCE-vecchio OR SUBJECT-nuovo',
        f'(OR (SINCE {since_str}) (SUBJECT "Invio Ordine"))')

    run(mail, 'E) Gmail X-GM-RAW (sintassi ricerca Gmail nativa)',
        f'(X-GM-RAW "in:inbox subject:\\"Invio Ordine\\"")')

    mail.logout()


if __name__ == '__main__':
    main()
