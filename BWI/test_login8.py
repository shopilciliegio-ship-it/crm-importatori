"""
Test login BWI definitivo.
Dal bundle:
  ("BWI"===this.appconfig.appName) → usa appBaseUrlNew+"user/bdnlogin"
  Authorization: Basic base64(username:password)
  Body: {email, password} (oppure {username, password})
"""
import requests, json, re, base64

FRONT = "https://app.bestwineimporters.com"
BASE  = "https://api.bestwineimporters.com/api/v1"

# Step 1: trova appBaseUrlNew nel bundle
print("1. Cerca appBaseUrlNew nel bundle...")
HEADERS_JS = {"User-Agent": "Mozilla/5.0","Accept":"*/*","Referer": FRONT+"/"}
r = requests.get(f"{FRONT}/main.0dea8a64934bcc6a.js", headers=HEADERS_JS, timeout=20)
js = r.text

for m in re.finditer(r'appBaseUrlNew|BaseUrlNew', js, re.IGNORECASE):
    start = max(0, m.start()-100)
    end   = min(len(js), m.end()+200)
    print(f"  pos {m.start()}: {js[start:end]}")
    print()

# Step 2: login reale
print("\n2. Test login su /user/bdnlogin...")

HEADERS_BASE = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": FRONT,
    "Referer": FRONT + "/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

for email in ["info@sienawine.it", "luca@sienawine.it"]:
    pwd = "260690557"
    b64 = base64.b64encode(f"{email}:{pwd}".encode()).decode()

    for body in [
        {"email": email,    "password": pwd},
        {"username": email, "password": pwd},
        {"email": email,    "password": pwd, "username": email},
    ]:
        h = {**HEADERS_BASE, "Authorization": f"Basic {b64}"}
        url = f"{BASE}/user/bdnlogin"
        try:
            resp = requests.post(url, json=body, headers=h, timeout=15)
            print(f"  {resp.status_code}  {email}  body={list(body.keys())}  → {resp.text[:200]}")
            if resp.status_code == 200:
                print("\n  ✅ SUCCESSO!")
                print(json.dumps(resp.json(), indent=2))
        except Exception as e:
            print(f"  ERR ({email} {list(body.keys())}): {type(e).__name__}: {str(e)[:80]}")
