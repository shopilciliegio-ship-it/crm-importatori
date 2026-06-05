# -*- coding: utf-8 -*-
"""
Test login BWI - URL finale: https://api2.bestwineimporters.com/v2/user/bdnlogin
Authorization: Basic base64(username:password)
"""
import requests, json, base64, sys

# Fix encoding Windows
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

FRONT   = "https://app.bestwineimporters.com"
BASE_V2 = "https://api2.bestwineimporters.com/v2"

HEADERS_BASE = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": FRONT,
    "Referer": FRONT + "/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

URL = f"{BASE_V2}/user/bdnlogin"
print(f"URL: {URL}")

for email in ["info@sienawine.it", "luca@sienawine.it"]:
    pwd = "260690557"
    b64 = base64.b64encode(f"{email}:{pwd}".encode()).decode()
    h   = {**HEADERS_BASE, "Authorization": f"Basic {b64}"}

    for body in [
        {"username": email, "password": pwd},
        {"email": email,    "password": pwd},
        {"username": email, "password": pwd, "email": email},
    ]:
        try:
            resp = requests.post(URL, json=body, headers=h, timeout=15)
            body_keys = list(body.keys())
            print(f"  {resp.status_code}  [{email}]  keys={body_keys}")
            if resp.status_code != 404:
                print(f"    Body: {resp.text[:300]}")
            if resp.status_code == 200:
                print("    *** LOGIN OK! ***")
                try:
                    print(json.dumps(resp.json(), indent=2))
                except Exception:
                    print(resp.text[:1000])
        except Exception as e:
            print(f"  ERR [{email}]: {type(e).__name__}: {str(e)[:80]}")
