# -*- coding: utf-8 -*-
"""
spotty_auto_download.py
=======================
Auto-login su admin.spottywifi.it e download CSV contatti.
Salva in: Spotty/utentiregistrati_latest.csv

Uso:
    python spotty_auto_download.py           # scarica e salva
    python spotty_auto_download.py --test    # solo testa il login
"""

import os
import re
import sys
import requests
from datetime import datetime

BASE_URL    = "http://admin.spottywifi.it"
LOGIN_URL   = f"{BASE_URL}/login.php"
USERS_URL   = f"{BASE_URL}/utenti_registrati/"
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "utentiregistrati_latest.csv")

SPOTTY_USER = os.environ.get("SPOTTY_USER", "ilciliegio.com")
SPOTTY_PASS = os.environ.get("SPOTTY_PASS", "Hotel1000!")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}


def _save_debug(name: str, text: str):
    path = os.path.join(SCRIPT_DIR, f"debug_{name}.html")
    with open(path, "w", encoding="utf-8", errors="replace") as f:
        f.write(text)
    print(f"  ⓘ  Debug HTML salvato: {path}")


def _find_form_fields(html: str):
    """Estrae i nomi dei campi input text/email/password da un form HTML."""
    pattern = re.compile(
        r'<input[^>]+>', re.IGNORECASE | re.DOTALL
    )
    fields = {}
    for tag in pattern.findall(html):
        name_m  = re.search(r'name=["\']([^"\']+)["\']',  tag, re.I)
        type_m  = re.search(r'type=["\']([^"\']+)["\']',  tag, re.I)
        value_m = re.search(r'value=["\']([^"\']*)["\']', tag, re.I)
        if name_m:
            t = (type_m.group(1).lower() if type_m else "text")
            v = (value_m.group(1) if value_m else "")
            fields[name_m.group(1)] = (t, v)
    return fields


def _find_form_action(html: str, fallback: str) -> str:
    m = re.search(r'<form[^>]+action=["\']([^"\']*)["\']', html, re.I)
    if m:
        action = m.group(1)
        if action.startswith("http"):
            return action
        return BASE_URL + "/" + action.lstrip("/")
    return fallback


def do_login() -> requests.Session | None:
    sess = requests.Session()
    sess.headers.update(HEADERS)

    try:
        r = sess.get(LOGIN_URL, timeout=30)
    except Exception as e:
        print(f"✗ Impossibile raggiungere {LOGIN_URL}: {e}")
        return None

    fields  = _find_form_fields(r.text)
    action  = _find_form_action(r.text, LOGIN_URL)

    print(f"  Form action: {action}")
    print(f"  Campi trovati: {list(fields.keys())}")

    # Costruisce il payload identificando user / password field
    payload = {}
    for name, (ftype, default_val) in fields.items():
        n = name.lower()
        if ftype in ("text", "email") and any(k in n for k in ("user","email","login","name","cod")):
            payload[name] = SPOTTY_USER
        elif ftype == "password":
            payload[name] = SPOTTY_PASS
        elif ftype == "hidden":
            payload[name] = default_val  # mantieni token/csrf hidden

    if not any(ftype == "password" for _, (ftype, _) in fields.items()):
        # Fallback se non ha trovato campo password
        print("  ⚠ Nessun campo password trovato — provo con 'username'/'password'")
        payload = {"username": SPOTTY_USER, "password": SPOTTY_PASS}

    print(f"  POST fields: {[k for k in payload if 'pass' not in k.lower()]}")

    try:
        r2 = sess.post(action, data=payload, timeout=30, allow_redirects=True)
    except Exception as e:
        print(f"✗ POST fallito: {e}")
        return None

    # Verifica login riuscito
    text_lower = r2.text.lower()
    success_signals = ["logout", "esci", "dashboard", "utenti_registrati", "benvenuto", "welcome"]
    fail_signals    = ["password errata", "credenziali", "invalid", "incorrect", "login.php"]

    if any(s in text_lower for s in success_signals) and "login" not in r2.url.lower():
        print(f"✓ Login riuscito (redirect: {r2.url})")
        return sess

    if r2.url.endswith("login.php") or any(s in text_lower for s in fail_signals):
        print(f"✗ Login fallito — URL finale: {r2.url}")
        _save_debug("login_failed", r2.text)
        return None

    # Caso ambiguo: salva debug e continua ottimisticamente
    print(f"  ⚠ Login esito incerto (URL: {r2.url}) — provo comunque")
    _save_debug("login_uncertain", r2.text)
    return sess


EXPORT_FORM_URL = f"{BASE_URL}/utilita-esporta_utenti/"
# Periodo di export per aggiornamento settimanale (168h = 7 giorni)
# Scarica utenti che si sono connessi nell'ultimo periodo — l'import script
# ignora automaticamente chi è già nel DB, quindi funziona come diff incrementale
EXPORT_HOURS = "168"


def download_weekly_csv(sess: requests.Session) -> bool:
    """
    POST al form di esportazione con ore_connessione=168.
    Scarica il CSV degli utenti con connessioni nell'ultima settimana.
    """
    try:
        resp = sess.post(
            EXPORT_FORM_URL,
            data={"ore_connessione": EXPORT_HOURS, "esporta": "Esporta utenti"},
            timeout=120,
        )
    except Exception as e:
        print(f"✗ Download fallito: {e}")
        return False

    ct = resp.headers.get("Content-Type", "")
    cd = resp.headers.get("Content-Disposition", "")

    if "octet-stream" in ct or "csv" in ct or "attachment" in cd:
        with open(OUTPUT_FILE, "wb") as f:
            f.write(resp.content)
        size_kb = len(resp.content) / 1024
        print(f"✓ CSV salvato: {OUTPUT_FILE} ({size_kb:.1f} KB, {len(resp.content)} bytes)")
        # Verifica contenuto
        try:
            first_line = resp.content[:200].decode("utf-8", errors="replace")
            rows = resp.text.count("\n")
            print(f"  Righe nel CSV: ~{rows}")
            print(f"  Intestazione: {first_line.split(chr(10))[0][:120]}")
        except Exception:
            pass
        return True

    print(f"✗ Risposta inattesa (Content-Type: {ct!r}, size: {len(resp.content)})")
    _save_debug("export_failed", resp.text)
    print("  Controlla debug_export_failed.html per i dettagli")
    return False


def main():
    test_only = "--test" in sys.argv
    print(f"{'='*50}")
    print(f"SpottyWifi Auto-Download — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    print(f"Utente: {SPOTTY_USER}")
    print()

    print("1. Login...")
    sess = do_login()
    if not sess:
        print("\n✗ Login fallito — controlla debug_login_failed.html per i dettagli")
        sys.exit(1)

    if test_only:
        print("\n✓ Test login completato con successo")
        sys.exit(0)

    print(f"\n2. Download CSV (ultimi {EXPORT_HOURS}h)...")
    ok = download_weekly_csv(sess)
    if not ok:
        print(f"\n✗ Download fallito")
        print(f"  Soluzione manuale: scarica il CSV dal sito e mettilo in:")
        print(f"  {OUTPUT_FILE}")
        sys.exit(1)

    print("\n✓ Download completato")


if __name__ == "__main__":
    main()
