"""
Test login reale con endpoint trovato nel bundle JS.
"""
import requests, json

FRONT  = "https://app.bestwineimporters.com"
BASE   = "https://api.bestwineimporters.com"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": FRONT,
    "Referer": FRONT + "/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

for email in ["luca@sienawine.it", "info@sienawine.it"]:
    print(f"\n{'='*60}")
    print(f"  Tentativo: {email}")
    print(f"{'='*60}")
    try:
        r = requests.post(
            f"{BASE}/api/auth/sign-in",
            json={"email": email, "password": "260690557"},
            headers=HEADERS,
            timeout=10
        )
        print(f"  Status: {r.status_code}")
        print(f"  Response-Headers: {dict(r.headers)}")
        print(f"  Set-Cookie: {r.headers.get('Set-Cookie','—')}")
        print(f"  Body (500 chars): {r.text[:500]}")
        if r.status_code == 200:
            print("\n  ✅ LOGIN OK!")
            try:
                data = r.json()
                print(json.dumps(data, indent=2))
                # Cerca bdnAccess / BDN-access nel body
                body_str = json.dumps(data)
                import re
                bdn = re.findall(r'[Bb][Dd][Nn][Aa]ccess["\s:]*([^\s,"\'}{]+)', body_str)
                print(f"\n  bdnAccess trovato: {bdn}")
            except Exception as e:
                print(f"  (JSON parse error: {e})")
                print(r.text)
    except Exception as e:
        print(f"  ERRORE: {e}")
