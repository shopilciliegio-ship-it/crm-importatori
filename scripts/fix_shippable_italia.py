"""
Fix una tantum — usa e getta.
'it' mancava da SHIPPABLE_COUNTRIES in Spotty/spotty_import.py: tutti i
clienti italiani importati finora sono finiti con shippable=False, anche
se in Italia si spedisce normalmente. Corregge i record già presenti in
data/clienti.json (il fix nello script di import evita che il problema si
ripresenti per i prossimi import).

Uso:
    python scripts/fix_shippable_italia.py
"""

import json

PATH = 'data/clienti.json'

with open(PATH, encoding='utf-8') as f:
    db = json.load(f)

contacts = db['contacts']
n = 0
for c in contacts:
    country = (c.get('country') or '').strip().upper()
    if country in ('IT', 'ITALIA', 'ITALY') and c.get('shippable') is not True:
        c['shippable'] = True
        n += 1

with open(PATH, 'w', encoding='utf-8') as f:
    json.dump(db, f, ensure_ascii=False, indent=2)

print(f'Corretti {n} clienti italiani (shippable -> True)')
