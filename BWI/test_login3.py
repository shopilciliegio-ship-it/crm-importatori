"""
Analizza il bundle JS del frontend per trovare l'endpoint di login.
"""
import requests, re, json

FRONT = "https://app.bestwineimporters.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*"
}

print("1. Fetching index.html...")
r = requests.get(FRONT, headers=HEADERS, timeout=10)
print(f"   Status: {r.status_code}")

# Cerca tutti i file .js
js_files = re.findall(r'src="([^"]+\.js[^"]*)"', r.text)
print(f"   JS files trovati: {len(js_files)}")

# Cerca anche in <link> e <script>
scripts = re.findall(r'(?:src|href)="([^"]*(?:main|chunk|app)[^"]*\.js[^"]*)"', r.text)
print(f"   Script rilevanti: {scripts}")
print()

HEADERS_JS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": FRONT + "/"
}

for js_url in (scripts or js_files)[:5]:
    if not js_url.startswith("http"):
        js_url = FRONT + "/" + js_url.lstrip("/")
    print(f"2. Fetching {js_url[:80]}...")
    try:
        jr = requests.get(js_url, headers=HEADERS_JS, timeout=15)
        js = jr.text
        print(f"   Size: {len(js):,} chars")

        # Cerca pattern di login/auth
        patterns = [
            r'["\'](?:/api[/\w]*(?:login|auth|signin|session)[/\w]*)["\']',
            r'(?:login|auth|signin|session)\w*\s*[=:]\s*["\']([^"\']+)["\']',
            r'POST[^"\']*["\']([^"\']*(?:login|auth|signin)[^"\']*)["\']',
            r'bdnaccess|bdn.access|bdn_access|BdnAccess',
            r'sessionId|session_id',
        ]
        for pat in patterns:
            matches = re.findall(pat, js, re.IGNORECASE)
            if matches:
                print(f"   [{pat[:40]}]: {matches[:5]}")
    except Exception as e:
        print(f"   ERRORE: {e}")
    print()

# Prova anche con Playwright se installato
print("3. Provo con requests-html / selenium se disponibile...")
try:
    import subprocess
    result = subprocess.run(["python", "-c", "import playwright; print('playwright ok')"],
                           capture_output=True, text=True, timeout=5)
    print(f"   Playwright: {result.stdout.strip() or result.stderr.strip()}")
except Exception as e:
    print(f"   Playwright non disponibile: {e}")
