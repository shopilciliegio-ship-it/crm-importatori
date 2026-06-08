"""
Reset una tantum del flag bwiStatus — usa e getta.
Azzera bwiStatus su tutti i contatti dell'archivio (mega-import BWI del
05-06/06/2026), così che NUOVO/AGGIORNATO tornino a comparire solo per i
prossimi import realmente nuovi o modificati (badge con scadenza automatica
a 4 mesi, vedi bwiBadgeStatus in js/contacts.js).

Uso:
    python scripts/reset_bwi_status.py
"""

import json

PATH = 'data/contatti.json'

with open(PATH, encoding='utf-8') as f:
    db = json.load(f)

contacts = db['contacts']
n = sum(1 for c in contacts if c.get('bwiStatus') is not None)
for c in contacts:
    c['bwiStatus'] = None

with open(PATH, 'w', encoding='utf-8') as f:
    json.dump(db, f, ensure_ascii=False, separators=(',', ':'))

print(f'Azzerato bwiStatus su {n} contatti (totale archivio: {len(contacts)})')
