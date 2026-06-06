# -*- coding: utf-8 -*-
"""
spotty_import.py
================
Legge il CSV SpottyWifi e importa i nuovi contatti in data/clienti.json.

Logica:
  - Email già presente → skip (non sovrascrive mai)
  - Email in blacklist  → skip
  - Nuovo contatto      → classifica qualità + paese + inserisce

Qualità:
  🟢 valid   — nome + cognome ok, email ok, paese spedibile
  🟡 suspect — email con typo, nome sospetto, o paese non spedibile
  🔴 invalid — email chiaramente falsa, nome incomprensibile

Uso:
    python spotty_import.py                        # usa utentiregistrati_latest.csv
    python spotty_import.py percorso/file.csv      # usa file specificato
"""

import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT   = os.path.dirname(SCRIPT_DIR)
CLIENTI_FILE = os.path.join(REPO_ROOT, "data", "clienti.json")
DEFAULT_CSV  = os.path.join(SCRIPT_DIR, "utentiregistrati_latest.csv")

# ── PAESI SPEDIBILI ──────────────────────────────────────────────────────────
SHIPPABLE_COUNTRIES = {
    'de','be','nl','lu','fr','dk','at','es','pt','se','ie','si',
    'fi','hr','gr','pl','cz','sk','hu','bg','ee','lv','lt','ro',
    'cy','mt','us','ca','gb','ch','no'
}

# Mappa lingua (senza paese) → country code ISO2
LANG_TO_COUNTRY = {
    'it':'it','fr':'fr','de':'de','es':'es','pt':'pt','en':'gb',
    'ru':'ru','zh':'cn','ja':'jp','ko':'kr','ar':'sa','tr':'tr',
    'pl':'pl','nl':'nl','sv':'se','da':'dk','fi':'fi','nb':'no',
    'cs':'cz','sk':'sk','hu':'hu','ro':'ro','bg':'bg','hr':'hr',
    'sl':'si','et':'ee','lv':'lv','lt':'lt','el':'gr','uk':'ua',
    'sr':'rs','ca':'es','he':'il','th':'th','vi':'vn','id':'id',
}

# ── EMAIL ────────────────────────────────────────────────────────────────────
DISPOSABLE_DOMAINS = {
    'mailinator.com','tempmail.com','guerrillamail.com','10minutemail.com',
    'throwaway.email','yopmail.com','fakeinbox.com','sharklasers.com',
    'trashmail.com','trashmail.me','temp-mail.org','dispostable.com',
    'mailnull.com','spamgourmet.com','mytrashmail.com','maildrop.cc',
    'getairmail.com','filzmail.com','throwam.com','tempr.email',
    'spam4.me','binkmail.com','discard.email',
}

TYPO_DOMAIN_RE = re.compile(
    r'g\.mail\.|gmai\.|gmal\.|hotmil\.|yaho\.|'
    r'\.con\b|\.cmo\b|\.ocm\b|\.gom\b|\.vom\b',
    re.IGNORECASE
)

FAKE_LOCAL_RE = re.compile(
    r'^(test\d*|prova\d*|fake\d*|aaa+|bbb+|xxx+|admin\d*|user\d*|'
    r'[a-z]{1,2}\d*|qwerty|asdf|zxcv)$',
    re.IGNORECASE
)


def classify_email(email: str) -> tuple[str, list]:
    """Ritorna (tier, flags): tier = 'valid'|'suspect'|'invalid'"""
    email = email.strip().lower()
    local, _, domain = email.partition('@')
    flags = []

    if not domain:
        return 'invalid', ['no_at']

    if domain in DISPOSABLE_DOMAINS:
        return 'invalid', ['disposable']

    if TYPO_DOMAIN_RE.search(domain):
        flags.append('typo_domain')

    if FAKE_LOCAL_RE.match(local):
        flags.append('suspicious_local')

    dot_in_domain = '.' in domain
    if not dot_in_domain:
        flags.append('no_dot_in_domain')

    if 'invalid' in flags or 'disposable' in flags:
        return 'invalid', flags

    if flags:
        return 'suspect', flags

    return 'valid', []


def classify_name(first: str, last: str) -> tuple[str, list]:
    """Ritorna (tier, flags)"""
    first = first.strip(); last = last.strip()
    flags = []

    if not first or not last:
        return 'invalid', ['missing_name']

    full = first + last
    digit_count = sum(c.isdigit() for c in full)
    if digit_count > 3:
        return 'invalid', ['numbers_in_name']

    if len(first) < 2 or len(last) < 2:
        flags.append('too_short')

    # Nomi "keyboard mash": consonanti consecutive senza vocali
    if re.search(r'[bcdfghjklmnpqrstvwxyz]{5,}', first.lower()) or \
       re.search(r'[bcdfghjklmnpqrstvwxyz]{5,}', last.lower()):
        flags.append('keyboard_mash')

    if digit_count > 0:
        flags.append('has_digits')

    if flags:
        return 'suspect', flags
    return 'valid', []


def get_country(lang_browser: str) -> tuple[str, bool]:
    """Ritorna (country_code_upper, is_shippable)"""
    lang = lang_browser.strip().lower()
    if not lang:
        return 'UNKNOWN', False

    parts = lang.split('-')
    if len(parts) >= 2:
        cc = parts[-1]
        if cc == '419':                     # es-419 = America Latina generica
            return 'LATAM', False
        return cc.upper(), cc in SHIPPABLE_COUNTRIES

    # Solo lingua
    cc = LANG_TO_COUNTRY.get(parts[0], parts[0])
    return cc.upper(), cc in SHIPPABLE_COUNTRIES


def parse_date(date_str: str) -> int | None:
    """Supporta sia 'DD.MM.YYYY HH:MM:SS' (export manuale) che 'YYYY-MM-DD HH:MM:SS' (auto-download)."""
    s = date_str.strip()
    for fmt in ('%d.%m.%Y %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%d.%m.%Y', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(s, fmt)
            return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
        except ValueError:
            continue
    return None


def make_id(email: str) -> str:
    return 'cli_' + hashlib.md5(email.lower().encode()).hexdigest()[:10]


def classify_contact(row: dict) -> dict:
    first = row.get('Nome', '').strip()
    last  = row.get('Cognome', '').strip()
    email = row.get('Email', '').strip()
    # Supporta sia 'Linguabrowser' (manuale) che 'Lingua' (auto-download, es: 'it', 'fr')
    lang  = (row.get('Linguabrowser') or row.get('Lingua') or '').strip()
    # Supporta sia 'Data Registrazione' che 'DataInserimento'
    date  = (row.get('Data Registrazione') or row.get('DataInserimento') or '').strip()

    country, shippable = get_country(lang)
    eq, ef = classify_email(email)
    nq, nf = classify_name(first, last)

    # Tier: solo qualità dei dati (nome + email), indipendente da paese
    RANK = {'valid': 0, 'suspect': 1, 'invalid': 2}
    tier = 'invalid' if RANK[eq] >= 2 or RANK[nq] >= 2 else \
           'suspect' if RANK[eq] >= 1 or RANK[nq] >= 1 else \
           'valid'

    flags = ef + nf

    return {
        'id':              make_id(email),
        'company':         f'{first} {last}'.strip(),  # per compatibilità UI card
        'firstName':       first,
        'lastName':        last,
        'email':           email.lower(),
        'languageBrowser': lang,
        'country':         country,
        'shippable':       shippable,
        'quality':         tier,
        'qualityFlags':    flags,
        'registeredAt':    parse_date(date),
        'importedAt':      int(datetime.now(timezone.utc).timestamp() * 1000),
        'source':          'spottywifi',
        'waveStatus':      None,
        'emailsSent':      [],
        'blacklisted':     False,
        'notes':           '',
        'status':          'new',
    }


def load_clienti() -> dict:
    if not os.path.exists(CLIENTI_FILE):
        return {'contacts': [], 'templates': []}
    with open(CLIENTI_FILE, encoding='utf-8') as f:
        return json.load(f)


def save_clienti(data: dict):
    with open(CLIENTI_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV

    if not os.path.exists(csv_path):
        print(f'✗ CSV non trovato: {csv_path}')
        print(f'  Esegui prima spotty_auto_download.py oppure specifica il file manualmente')
        sys.exit(1)

    print(f'CSV: {csv_path}')
    print(f'Target: {CLIENTI_FILE}')
    print()

    # Leggi CSV
    rows = []
    with open(csv_path, encoding='utf-8-sig', errors='replace') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            rows.append(row)
    print(f'Righe CSV: {len(rows)}')

    # Carica clienti.json esistente
    db = load_clienti()
    existing_emails = {c['email'].lower() for c in db.get('contacts', [])}
    blacklist = {c['email'].lower() for c in db.get('contacts', []) if c.get('blacklisted')}

    print(f'Contatti esistenti: {len(existing_emails)}')
    print(f'Blacklist: {len(blacklist)}')
    print()

    # Importa nuovi contatti
    stats = {'added': 0, 'skipped_existing': 0, 'skipped_blacklist': 0,
             'valid': 0, 'suspect': 0, 'invalid': 0, 'shippable': 0}

    new_contacts = []
    for row in rows:
        email = row.get('Email', '').strip().lower()
        if not email:
            continue
        if email in blacklist:
            stats['skipped_blacklist'] += 1
            continue
        if email in existing_emails:
            stats['skipped_existing'] += 1
            continue

        c = classify_contact(row)
        new_contacts.append(c)
        existing_emails.add(email)  # evita duplicati dentro il CSV stesso

        stats['added'] += 1
        stats[c['quality']] += 1
        if c['shippable']:
            stats['shippable'] += 1

    # Aggiungi in fondo (già ordinati per data nel CSV)
    db.setdefault('contacts', []).extend(new_contacts)

    # Aggiorna lastImportAt
    db['lastImportAt'] = int(datetime.now(timezone.utc).timestamp() * 1000)
    db['lastImportFile'] = os.path.basename(csv_path)

    save_clienti(db)

    # Riepilogo
    print(f"{'='*45}")
    print(f'IMPORTAZIONE COMPLETATA')
    print(f"{'='*45}")
    print(f'  Nuovi aggiunti:     {stats["added"]}')
    print(f'  Già presenti:       {stats["skipped_existing"]}')
    print(f'  Blacklistati:       {stats["skipped_blacklist"]}')
    print()
    print(f'  🟢 Validi:          {stats["valid"]}')
    print(f'  🟡 Sospetti:        {stats["suspect"]}')
    print(f'  🔴 Invalidi:        {stats["invalid"]}')
    print()
    print(f'  Paese spedibile:    {stats["shippable"]}')
    print(f'  Totale contatti DB: {len(db["contacts"])}')
    print(f"{'='*45}")


if __name__ == '__main__':
    main()
