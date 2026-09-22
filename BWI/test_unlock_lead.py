"""
Test one-shot per l'endpoint di sblocco email BWI (unlockLead/) — scoperto il 22/9/2026
ispezionando il Network tab del browser mentre Luca cliccava "Access Email" su un contatto.

Cosa fa:
  1. Login automatico (stesso bwi_auto_login.py già usato da bestwine_scraper.py).
  2. Scarica i lead di UNA azienda (default: Alessi Beverages, compID 89790 — quella testata
     a mano nel browser) e stampa il JSON grezzo del primo lead, per scoprire il nome esatto del
     campo ID (necessario per costruire lo sblocco su qualunque lead, non solo quello già noto).
  3. Sblocca quel lead per davvero (consuma 1 credito BWI — Luca ne ha ~5000) e stampa il
     risultato, confrontandolo con quello già ottenuto a mano nel browser
     ({"leadId":18914,"leadEmail":"jalessi@alessibeverages.com.au","status":200}).

Uso:
    python test_unlock_lead.py                  # usa Alessi Beverages (compID 89790)
    python test_unlock_lead.py <compID>          # un'altra azienda
"""
import json
import sys

import requests

from bwi_auto_login import do_login

UNLOCK_URL = "https://api.bestwineimporters.com/api/v1/unlockLead/"
LEADS_URL  = "https://api.bestwineimporters.com/api/v1/leads"


def get_leads(headers, comp_id):
    r = requests.post(LEADS_URL, json={"compID": comp_id}, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("leads", data.get("resListLeads", []))
    return []


def unlock_lead(headers, comp_id, lead_id, lead_type="manu"):
    body = {"compID": comp_id, "leadID": lead_id, "leadType": lead_type}
    r = requests.post(UNLOCK_URL, json=body, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()


def main():
    comp_id = int(sys.argv[1]) if len(sys.argv) > 1 else 89790  # Alessi Beverages

    print("🔑 Login BWI...")
    _, headers = do_login()
    print("✅ Login OK\n")

    print(f"📋 Scarico i lead dell'azienda compID={comp_id}...")
    leads = get_leads(headers, comp_id)
    print(f"   {len(leads)} lead trovati.\n")

    if not leads:
        print("❌ Nessun lead trovato per questa azienda — provo comunque a stampare la risposta grezza sopra.")
        return

    print("🔍 JSON GREZZO del primo lead (per scoprire il nome esatto del campo ID):")
    print(json.dumps(leads[0], indent=2, ensure_ascii=False))
    print()

    # Prova le chiavi più plausibili per l'ID del lead, in ordine.
    lead_id = None
    for key in ("ID", "Id", "id", "LeadID", "leadID", "leadId"):
        if key in leads[0]:
            lead_id = leads[0][key]
            print(f"➡️  Trovato campo ID lead: \"{key}\" = {lead_id}")
            break

    if lead_id is None:
        print("⚠️ Nessuna chiave ID riconosciuta automaticamente — guarda il JSON sopra e dimmi qual è il campo giusto.")
        return

    print(f"\n🔓 Sblocco il lead {lead_id} (consuma 1 credito)...")
    result = unlock_lead(headers, comp_id, lead_id)
    print("✅ Risposta:")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
