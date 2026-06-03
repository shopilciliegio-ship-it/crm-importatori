"""
Test rapido — chiama l'API per una singola azienda e mostra la risposta.
Aggiorna COOKIE, BDN_ACCESS, BDN_ID, BDN_NAME con i tuoi dati attuali.
"""
import requests
import json

# ── AGGIORNA QUI ──
COOKIE     = "_ga=GA1.1.586675849.1777477552; intercom-id-hhkybma9=c648fe74-a61c-4ff3-9ce2-322bd40941ae; intercom-session-hhkybma9=; intercom-device-id-hhkybma9=0ddcf177-5992-4260-a48a-1a5a863ff96d; _gcl_au=1.1.303388429.1776775811.1595798605.1778427736.1778427736; token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoiaW5mb0BzaWVuYXdpbmUuaXQiLCJ1c2VySWQiOjEzMjI5LCJzZXNzaW9uSWQiOiI3MzhmOTJlOTc4ODZmYTRkODNkY2U4ZDI4Yjg4NWVjMiIsImlhdCI6MTc3ODUxNTQ0NSwiZXhwIjoxNzc4NTE3MjQ1LCJpc3MiOiJiZXN0d2luZWltcG9ydGVycy5jb20ifQ.m8dirzrp_AU_x-fOuxJsIk5BqR4amG5wJheYMHQ_yok; tokenRef=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoiaW5mb0BzaWVuYXdpbmUuaXQiLCJ1c2VySWQiOjEzMjI5LCJzZXNzaW9uSWQiOiI3MzhmOTJlOTc4ODZmYTRkODNkY2U4ZDI4Yjg4NWVjMiIsImlhdCI6MTc3ODUxNTQ0NSwiZXhwIjoxNzc4NjAxODQ1LCJpc3MiOiJiZXN0d2luZWltcG9ydGVycy5jb20ifQ.K8p8jbOuFR_ExXlL0Tias3F6elhkL580QqWh1jkQWbE; jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxMzIyOSwicm9sZSI6ImRlbW8iLCJpYXQiOjE3Nzg1MTU0NDUsImV4cCI6MTc3ODU0NDI0NX0.Ug-fYMqSXE9GaOrwvkcAo_4oN4im59ICTXuwOeEhN7I; _ga_4B4PSNEGMV=GS2.1.s1778515437$o8$g1$t1778515474$j23$l0$h1060534165$dA6Q-a8cDC9GsTakIbW4KuIChXgC7Dsn1PQ"
BDN_ACCESS = "$2a$10$jGEdpGH9wc67nQkgEVOH.eWL0RfiNhNIjdmCNb9QUUK1G7LOLzns2"
BDN_ID     = "13229"
BDN_NAME   = "info@sienawine.it"
# ─────────────────

BASE_URL = "https://api.bestwineimporters.com/api/v1"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Cookie": COOKIE,
    "Bdn-Access": BDN_ACCESS,
    "Bdn-Id": BDN_ID,
    "Bdn-Name": BDN_NAME,
    "Origin": "https://app.bestwineimporters.com",
    "Referer": "https://app.bestwineimporters.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

print("=" * 50)
print("TEST 1 — customSearch (prime 3 aziende)")
print("=" * 50)
try:
    r = requests.post(f"{BASE_URL}/customSearch/", json={
        "nocache": False, "startAt": 0, "endAt": 3,
        "sortBy": "", "sortDir": "",
        "filters": {"FilterKeyword":[],"FilterCategories":[],"FilterSubCategories":[],
                    "FilterTypes":[],"FilterOrigin":[],"FilterCountry":[],
                    "FilterContinent":[],"FilterEmployee":[],"FilterSales":[]},
        "id": None, "name": None, "date": None
    }, headers=HEADERS, timeout=10)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:500]}")
except Exception as e:
    print(f"ERRORE: {type(e).__name__}: {e}")

print()
print("=" * 50)
print("TEST 2 — profileinfo di Mercian (ID: 167101)")
print("=" * 50)
try:
    r = requests.post(f"{BASE_URL}/profileinfo/",
        json={"compID": "167101"}, headers=HEADERS, timeout=10)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:500]}")
except Exception as e:
    print(f"ERRORE: {type(e).__name__}: {e}")

print()
print("TEST COMPLETATO")