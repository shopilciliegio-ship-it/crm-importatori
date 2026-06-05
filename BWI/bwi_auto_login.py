# -*- coding: utf-8 -*-
"""
BWI auto-login — restituisce (session, api_headers) con token freschi.

Endpoint scoperto nel bundle JS:
  POST https://api2.bestwineimporters.com/v2/user/bdnlogin
  Authorization: Basic base64(email:password)
  Body: {"username": email, "password": password}
  Risposta 201: {bdnAccess, userID, username, ...} + Set-Cookie: token/tokenRef/jwt

Uso:
  from bwi_auto_login import do_login
  session, headers = do_login()           # usa env BWI_EMAIL / BWI_PASSWORD
  session, headers = do_login(email, pwd) # credenziali esplicite
"""
import os, requests, base64

LOGIN_URL = "https://api2.bestwineimporters.com/v2/user/bdnlogin"
FRONT     = "https://app.bestwineimporters.com"

def do_login(email: str | None = None, password: str | None = None):
    email    = email    or os.environ.get("BWI_EMAIL",    "info@sienawine.it")
    password = password or os.environ.get("BWI_PASSWORD", "260690557")

    b64 = base64.b64encode(f"{email}:{password}".encode()).decode()
    login_headers = {
        "Accept":         "application/json, text/plain, */*",
        "Content-Type":   "application/json",
        "Authorization":  f"Basic {b64}",
        "Origin":         FRONT,
        "Referer":        FRONT + "/",
        "User-Agent":     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
    }

    sess = requests.Session()
    r = sess.post(LOGIN_URL,
                  json={"username": email, "password": password},
                  headers=login_headers, timeout=20)

    if r.status_code not in (200, 201):
        raise RuntimeError(f"BWI login failed: {r.status_code} — {r.text[:200]}")

    data = r.json()
    api_headers = {
        "Accept":       "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Cookie":       "; ".join(f"{k}={v}" for k, v in sess.cookies.items()),
        "Bdn-Access":   str(data["bdnAccess"]),
        "Bdn-Id":       str(data["userID"]),
        "Bdn-Name":     str(data["username"]),
        "Origin":       FRONT,
        "Referer":      FRONT + "/",
        "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Connection":   "close"
    }
    return sess, api_headers


if __name__ == "__main__":
    _, h = do_login()
    print("Login OK!")
    print(f"  Bdn-Access : {h['Bdn-Access'][:45]}...")
    print(f"  Bdn-Id     : {h['Bdn-Id']}")
    print(f"  Bdn-Name   : {h['Bdn-Name']}")
    print(f"  Cookie len : {len(h['Cookie'])} chars")
