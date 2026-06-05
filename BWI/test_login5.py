"""
Cerca nel bundle JS il contesto completo dell'endpoint sign-in
e tutti gli URL di API usati dall'app.
"""
import requests, re

FRONT = "https://app.bestwineimporters.com"
HEADERS_JS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": FRONT + "/"
}

print("Fetching bundle JS...")
r = requests.get(f"{FRONT}/main.0dea8a64934bcc6a.js", headers=HEADERS_JS, timeout=20)
js = r.text
print(f"Bundle size: {len(js):,} chars\n")

# 1. Cerca il contesto intorno a sign-in
print("="*60)
print("CONTESTO intorno a 'sign-in':")
print("="*60)
for m in re.finditer(r'sign.in', js, re.IGNORECASE):
    start = max(0, m.start()-200)
    end   = min(len(js), m.end()+200)
    snippet = js[start:end]
    print(f"\n--- pos {m.start()} ---")
    print(snippet)
    print()

# 2. Cerca tutti gli URL che iniziano con https://
print("="*60)
print("URL https:// nel bundle:")
print("="*60)
urls = set(re.findall(r'https?://[a-zA-Z0-9._/%-]+', js))
for u in sorted(urls):
    if 'bestwine' in u.lower() or 'bwi' in u.lower():
        print(f"  {u}")

# 3. Cerca environment/apiUrl
print("\n"+"="*60)
print("API base URL / environment:")
print("="*60)
env_matches = re.findall(r'(?:apiUrl|baseUrl|API_URL|environment)[^;]{0,200}', js, re.IGNORECASE)
for m in env_matches[:10]:
    print(f"  {m[:200]}")

# 4. Cerca bdnAccess nel contesto
print("\n"+"="*60)
print("bdnAccess nel contesto:")
print("="*60)
for m in re.finditer(r'bdnAccess', js, re.IGNORECASE):
    start = max(0, m.start()-150)
    end   = min(len(js), m.end()+150)
    print(f"\n--- pos {m.start()} ---")
    print(js[start:end])
