"""
Test login reale BWI — endpoint trovati nel bundle:
  - /api/v1/authentication
  - /api/v1/user/bdnlogin
Risposta attesa: {bdnAccess, userID, username, token, ...}
"""
import requests, json, re

FRONT = "https://app.bestwineimporters.com"
BASE  = "https://api.bestwineimporters.com/api/v1"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": FRONT,
    "Referer": FRONT + "/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

CREDENTIALS = [
    {"email": "luca@sienawine.it",  "password": "260690557"},
    {"email": "info@sienawine.it",  "password": "260690557"},
    # prova anche con username al posto di email
    {"username": "luca@sienawine.it", "password": "260690557"},
    {"username": "info@sienawine.it", "password": "260690557"},
]

ENDPOINTS = [
    f"{BASE}/authentication",
    f"{BASE}/user/bdnlogin",
    f"{BASE}/users/bdnlogin",
]

for url in ENDPOINTS:
    for creds in CREDENTIALS:
        print(f"\n{'='*60}")
        print(f"  POST {url.replace(BASE,'')}")
        print(f"  Payload: {creds}")
        print(f"{'='*60}")
        try:
            r = requests.post(url, json=creds, headers=HEADERS, timeout=10)
            print(f"  Status: {r.status_code}")
            if r.status_code != 404:
                print(f"  Set-Cookie: {r.headers.get('Set-Cookie','—')[:200]}")
                print(f"  Body: {r.text[:600]}")
                if r.status_code == 200:
                    print("\n  ✅ LOGIN OK!")
                    try:
                        data = r.json()
                        print("\n  JSON completo:")
                        print(json.dumps(data, indent=2))
                        bdn = data.get('bdnAccess') or data.get('BdnAccess') or data.get('bdn_access')
                        uid = data.get('userID') or data.get('userId') or data.get('user_id')
                        uname = data.get('username') or data.get('userName') or data.get('email')
                        token = data.get('token') or data.get('accessToken')
                        print(f"\n  bdnAccess: {bdn}")
                        print(f"  userID:    {uid}")
                        print(f"  username:  {uname}")
                        print(f"  token:     {str(token)[:80]}...")
                    except Exception as e:
                        print(f"  (JSON parse error: {e})")
                        print(r.text[:1000])
        except Exception as e:
            print(f"  ERRORE: {e}")
