"""
Controllo di accesso alla casella luca@sienawine.it (Aruba, IMAP) — usa e getta per
verificare che le credenziali funzionino e vedere cosa c'è davvero in inbox, prima di
costruire un controllo automatico delle risposte degli importatori.

Legge le credenziali da imap-sienawine-credentials.json (nella cartella del repo,
mai committato — vedi .gitignore) invece che da variabili d'ambiente, perché per ora
è un controllo manuale, non una GitHub Action.

Uso:
    python scripts/check_inbox_sienawine.py            # ultime N email di INBOX (default 20)
    python scripts/check_inbox_sienawine.py 50          # ultime 50
"""

import imaplib
import email
import email.header
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDS_PATH = os.path.join(ROOT, 'imap-sienawine-credentials.json')


def decode(raw):
    if not raw:
        return ''
    parts = email.header.decode_header(raw)
    out = ''
    for part, enc in parts:
        out += part.decode(enc or 'utf-8', errors='replace') if isinstance(part, bytes) else part
    return out


def main():
    if not os.path.exists(CREDS_PATH):
        print(f'ERRORE: manca {CREDS_PATH}')
        print('Creane uno con {"host":"imaps.aruba.it","port":993,"user":"luca@sienawine.it","password":"..."}')
        sys.exit(1)

    creds = json.load(open(CREDS_PATH, encoding='utf-8'))
    for campo in ('host', 'port', 'user', 'password'):
        if not creds.get(campo) or creds[campo] == 'INCOLLA_QUI_LA_PASSWORD':
            print(f'ERRORE: campo "{campo}" mancante o non compilato in {CREDS_PATH}')
            sys.exit(1)

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20

    print(f'Mi collego a {creds["host"]}:{creds["port"]} come {creds["user"]}...')
    try:
        mail = imaplib.IMAP4_SSL(creds['host'], creds['port'])
        mail.login(creds['user'], creds['password'])
    except Exception as e:
        print(f'ERRORE di connessione/login: {e}')
        sys.exit(1)

    print('✅ Login riuscito.\n')

    typ, folders = mail.list()
    if typ == 'OK':
        print(f'Cartelle disponibili ({len(folders)}):')
        for f in folders[:30]:
            print('   ', f.decode(errors='replace'))
        print()

    mail.select('INBOX', readonly=True)  # readonly: non segna nulla come letto, non tocca la casella
    typ, nums = mail.search(None, 'ALL')
    ids = (nums[0] or b'').split()
    print(f'INBOX: {len(ids)} email totali. Ultime {min(n, len(ids))}:\n')

    for num in ids[-n:][::-1]:  # dalla più recente
        typ, data = mail.fetch(num, '(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])')
        hdr = data[0][1].decode('utf-8', errors='replace')
        get = lambda campo: next((l[len(campo) + 2:].strip() for l in hdr.splitlines() if l.lower().startswith(campo.lower() + ':')), '')
        print(f'  • {decode(get("Date"))}')
        print(f'    Da: {decode(get("From"))}')
        print(f'    Oggetto: {decode(get("Subject"))}\n')

    mail.logout()


if __name__ == '__main__':
    main()
