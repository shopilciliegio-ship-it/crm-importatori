# -*- coding: utf-8 -*-
"""Login BWI confermato — mostra risposta completa e cookies."""
import requests, json, base64, sys
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

FRONT   = "https://app.bestwineimporters.com"
BASE_V1 = "https://api.bestwineimporters.com/api/v1"
BASE_V2 = "https://api2.bestwineimporters.com/v2"

email = "info@sienawine.it"
pwd   = "260690557"
b64   = base64.b64encode(f"{email}:{pwd}".encode()).decode()

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Authorization": f"Basic {b64}",
    "Origin": FRONT,
    "Referer": FRONT + "/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

print("=== LOGIN ===")
sess = requests.Session()
r = sess.post(f"{BASE_V2}/user/bdnlogin",
              json={"username": email, "password": pwd},
              headers=HEADERS, timeout=15)
print(f"Status: {r.status_code}")
print(f"Set-Cookie: {r.headers.get('Set-Cookie','(none)')}")
print(f"Cookies: {dict(r.cookies)}")
print()
try:
    data = r.json()
    print("JSON response:")
    print(json.dumps(data, indent=2))
    # Cerca i campi chiave
    print("\n=== CAMPI CHIAVE ===")
    for key in ['bdnAccess','bdn_access','BdnAccess','userID','userId','user_id',
                'username','token','accessToken','jwt','sessionId']:
        val = data.get(key)
        if val:
            print(f"  {key}: {str(val)[:100]}")
except Exception as e:
    print(f"(non JSON): {r.text[:2000]}")

# Dopo il login, prova una chiamata customSearch per verificare che funzioni
print("\n=== TEST customSearch DOPO LOGIN ===")
# I cookies della sessione
session_cookies = dict(sess.cookies)
print(f"Session cookies: {list(session_cookies.keys())}")

# Prova con i cookie ricevuti
api_headers = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": FRONT,
    "Referer": FRONT + "/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

# Se il response ha bdnAccess, usa quello
try:
    bdn_access = data.get('bdnAccess') or data.get('bdn_access')
    user_id    = str(data.get('userID') or data.get('userId') or '13229')
    username   = data.get('username') or email
    if bdn_access:
        api_headers.update({
            "Bdn-Access": str(bdn_access),
            "Bdn-Id": user_id,
            "Bdn-Name": username,
        })
        print(f"bdnAccess: {str(bdn_access)[:60]}...")
        print(f"userId: {user_id}")
except Exception:
    pass

r2 = sess.post(f"{BASE_V1}/customSearch/",
    json={"nocache":False,"startAt":0,"endAt":3,"sortBy":"","sortDir":"",
          "filters":{"FilterKeyword":[],"FilterCategories":[],"FilterSubCategories":[],
                     "FilterTypes":[],"FilterOrigin":[],"FilterCountry":[],
                     "FilterContinent":[],"FilterEmployee":[],"FilterSales":[]},
          "id":None,"name":None,"date":None},
    headers={**api_headers, **{"Cookie": "; ".join(f"{k}={v}" for k,v in session_cookies.items())}},
    timeout=15)
print(f"customSearch status: {r2.status_code}")
print(f"customSearch body: {r2.text[:300]}")
