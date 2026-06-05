"""
Cerca nel bundle il codice esatto della chiamata /authentication
e prova varianti di payload.
"""
import requests, json, re, base64

FRONT = "https://app.bestwineimporters.com"
BASE  = "https://api.bestwineimporters.com/api/v1"

HEADERS_JS = {"User-Agent": "Mozilla/5.0","Accept":"*/*","Referer": FRONT+"/"}

# --- Step 1: cerca il codice intorno ad "authentication" nel bundle ---
print("1. Analisi bundle: contesto 'authentication'...")
r = requests.get(f"{FRONT}/main.0dea8a64934bcc6a.js", headers=HEADERS_JS, timeout=20)
js = r.text

for m in re.finditer(r'authentication', js, re.IGNORECASE):
    start = max(0, m.start()-300)
    end   = min(len(js), m.end()+300)
    snippet = js[start:end]
    # Filtra solo quelli che sembrano chiamate HTTP reali
    if any(k in snippet.lower() for k in ['post', 'http', 'body', 'headers', 'email', 'password', 'user']):
        print(f"\n  --- pos {m.start()} ---")
        print(snippet)
        print()

# --- Step 2: cerca il login form e cosa invia ---
print("\n2. Cerca 'login' e 'password' nel bundle...")
for pat in [r'this\.http\.(post|get)\([^)]{0,200}auth[^)]{0,100}\)', r'login[^;]{0,300}password', r'password[^;]{0,300}http\.post']:
    matches = re.findall(pat, js, re.IGNORECASE)
    if matches:
        print(f"   Pattern: {pat[:50]}")
        for m in matches[:3]:
            print(f"   {m[:300]}")
        print()

# --- Step 3: prova varianti di payload ---
print("\n3. Prova varianti payload su /authentication...")
HEADERS_API = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": FRONT,
    "Referer": FRONT + "/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

email = "info@sienawine.it"
pwd   = "260690557"
b64   = base64.b64encode(f"{email}:{pwd}".encode()).decode()

payloads = [
    ({}, {}),
    ({"user": email, "password": pwd}, {}),
    ({"email": email, "pass": pwd}, {}),
    ({"email": email, "password": pwd}, {"Authorization": f"Basic {b64}"}),
    ({"email": email, "password": pwd}, {"Authorization": f"Bearer dummy"}),
    # corpo vuoto, solo basic auth
    ({}, {"Authorization": f"Basic {b64}"}),
]

for payload, extra_headers in payloads:
    h = {**HEADERS_API, **extra_headers}
    try:
        r = requests.post(f"{BASE}/authentication", json=payload, headers=h, timeout=8)
        print(f"  {r.status_code}  payload={list(payload.keys())} extra={list(extra_headers.keys())}  → {r.text[:150]}")
        if r.status_code == 200:
            print("  ✅ SUCCESSO!")
            print(json.dumps(r.json(), indent=2))
    except Exception as e:
        print(f"  ERR: {e}")
