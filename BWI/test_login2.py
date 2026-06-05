"""
Test auto-login BWI — round 2: base paths alternative + email alternativa
"""
import requests, json

EMAILS    = ["luca@sienawine.it", "info@sienawine.it"]
PASSWORD  = "260690557"
FRONT     = "https://app.bestwineimporters.com"

HEADERS_BASE = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": FRONT,
    "Referer": FRONT + "/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

# Prova base URL diverse
BASES = [
    "https://api.bestwineimporters.com",
    "https://api.bestwineimporters.com/api",
    "https://api.bestwineimporters.com/api/v1",
    "https://app.bestwineimporters.com/api/v1",
    "https://app.bestwineimporters.com/api",
]

PATHS = ["/auth/login", "/login", "/signin", "/user/login", "/users/login", "/session"]

print("=" * 70)
print("  BWI Login Discovery — Round 2")
print("=" * 70)

found = False
for base in BASES:
    for path in PATHS:
        for email in EMAILS:
            url = base + path
            payload = {"email": email, "password": PASSWORD}
            try:
                r = requests.post(url, json=payload, headers=HEADERS_BASE, timeout=6)
                if r.status_code != 404:
                    print(f"\n  ✨ {r.status_code}  POST {url}  [{email}]")
                    print(f"  Response-Headers: {dict(r.headers)}")
                    print(f"  Body: {r.text[:500]}")
                    if r.status_code == 200:
                        print("\n  ✅ LOGIN RIUSCITO!")
                        try: print(json.dumps(r.json(), indent=2))
                        except: print(r.text)
                        found = True
                        break
            except Exception as e:
                pass
        if found: break
    if found: break

if not found:
    print("\n  Nessun endpoint trovato con POST standard.")
    print("  Provo GET e OPTIONS per scoprire le route disponibili...")
    for base in BASES[:2]:
        for path in ["", "/api", "/api/v1", "/health", "/status"]:
            url = base + path
            try:
                r = requests.get(url, headers=HEADERS_BASE, timeout=5)
                if r.status_code != 404:
                    print(f"\n  GET {url} → {r.status_code}: {r.text[:200]}")
            except Exception as e:
                pass

print("\n" + "=" * 70)
