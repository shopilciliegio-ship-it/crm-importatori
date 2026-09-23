"""
Diagnostica SOLA LETTURA dei lead BWI di alcune aziende — nessuno sblocco, 0 crediti.

Nata il 23/9/2026: il primo sblocco reale (20 crediti) ha avuto 14 "fallite" — BWI ha accettato
unlockLead/ (e scalato il credito: 11977 -> 11943) ma senza leadEmail nella risposta. Qui si
scaricano i lead (endpoint leads, gratuito, lo stesso dello scraper) e si stampa il JSON grezzo,
per vedere com'è fatto un lead già pagato ma senza email.

Uso:
    python diag_leads_bwi.py 80093,80194,25508
"""
import json
import sys

import requests

from bwi_auto_login import do_login

LEADS_URL = "https://api.bestwineimporters.com/api/v1/leads"


def main():
    comp_ids = [int(x) for x in sys.argv[1].replace(" ", "").split(",") if x]
    print("🔑 Login BWI...")
    _, headers = do_login()
    print("✅ Login OK\n")
    for comp_id in comp_ids:
        r = requests.post(LEADS_URL, json={"compID": comp_id}, headers=headers, timeout=15)
        print(f"===== compID {comp_id} — HTTP {r.status_code}")
        try:
            print(json.dumps(r.json(), indent=1, ensure_ascii=False)[:4000])
        except ValueError:
            print(r.text[:2000])
        print()


if __name__ == "__main__":
    main()
