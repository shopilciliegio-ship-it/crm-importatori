"""
Test auto-login BWI — prova vari endpoint per trovare quello giusto.
Cerca Bdn-Access nella risposta.
"""
import requests, json

EMAIL    = "luca@sienawine.it"
PASSWORD = "260690557"

BASE  = "https://api.bestwineimporters.com/api/v1"
FRONT = "https://app.bestwineimporters.com"

HEADERS_BASE = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": FRONT,
    "Referer": FRONT + "/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

ENDPOINTS = [
    ("POST", f"{BASE}/auth/login",      {"email": EMAIL, "password": PASSWORD}),
    ("POST", f"{BASE}/login",           {"email": EMAIL, "password": PASSWORD}),
    ("POST", f"{BASE}/user/login",      {"email": EMAIL, "password": PASSWORD}),
    ("POST", f"{BASE}/signin",          {"email": EMAIL, "password": PASSWORD}),
    ("POST", f"{BASE}/auth/signin",     {"email": EMAIL, "password": PASSWORD}),
    ("POST", f"{BASE}/users/login",     {"email": EMAIL, "password": PASSWORD}),
    ("POST", f"{BASE}/auth",            {"email": EMAIL, "password": PASSWORD}),
    ("POST", f"{BASE}/account/login",   {"email": EMAIL, "password": PASSWORD}),
    # Prova anche con username invece di email
    ("POST", f"{BASE}/auth/login",      {"username": EMAIL, "password": PASSWORD}),
    ("POST", f"{BASE}/login",           {"username": EMAIL, "password": PASSWORD}),
]

print("=" * 60)
print("  BWI Login API Discovery")
print("=" * 60)

for method, url, payload in ENDPOINTS:
    try:
        r = requests.post(url, json=payload, headers=HEADERS_BASE, timeout=8)
        status = r.status_code
        body_preview = r.text[:300].replace("\n", " ")
        print(f"\n  {method} {url.replace(BASE,'')}")
        print(f"  Status: {status}")
        if status not in (404, 405):
            print(f"  Body:   {body_preview}")
            print(f"  Headers: {dict(r.headers)}")
            if status == 200:
                print("\n  ✅ TROVATO! Risposta completa:")
                try:
                    print(json.dumps(r.json(), indent=2))
                except Exception:
                    print(r.text)
                break
    except Exception as e:
        print(f"\n  {method} {url.replace(BASE,'')}")
        print(f"  ERRORE: {e}")

print("\n" + "=" * 60)
