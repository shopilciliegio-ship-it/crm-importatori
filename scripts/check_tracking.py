#!/usr/bin/env python3
"""
Fase 2 — Script automatico tracking ordini
Controlla lo stato spedizioni via 17track API e aggiorna data/ordini.json su GitHub.
Se lo stato cambia invia una email al cliente via Brevo.

━━━ START / STOP ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ENABLED = False  → script si avvia ma non fa nulla
  ENABLED = True   → attiva il controllo tracking
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

ENABLED = False  # ← metti True per attivare

# ── Configurazione ────────────────────────────────────
import os, json, base64, sys
from datetime import datetime

try:
    import requests
except ImportError:
    sys.exit("Installa dipendenze: pip install requests")

GITHUB_TOKEN   = os.environ.get("GH_TOKEN", "")
GITHUB_OWNER   = os.environ.get("GH_OWNER", "shopilciliegio-ship-it")
GITHUB_REPO    = os.environ.get("GH_REPO",  "crm-importatori")
BREVO_API_KEY  = os.environ.get("BREVO_API_KEY", "")
TRACK17_KEY    = os.environ.get("TRACK17_API_KEY", "")
SENDER_EMAIL   = os.environ.get("SENDER_EMAIL", "export@ilciliegio.com")
SENDER_NAME    = os.environ.get("SENDER_NAME",  "Il Ciliegio — Azienda Agricola")

ORD_PATH = "data/ordini.json"

# Mappatura stati 17track → nostri stati CRM
STATUS_MAP_17TRACK = {
    "NotFound":    None,          # non ancora tracciato
    "InTransit":   "in_transito",
    "Expired":     "problema",
    "PickedUp":    "spedito",
    "Delivered":   "consegnato",
    "UnDelivered": "problema",
    "Returning":   "problema",
    "Returned":    "problema",
    "Exception":   "problema",
}

# ── GitHub helpers ────────────────────────────────────

def gh_get(path):
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"
    r = requests.get(url, headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }, timeout=15)
    r.raise_for_status()
    d = r.json()
    content = base64.b64decode(d["content"].replace("\n","")).decode("utf-8")
    return json.loads(content), d["sha"]

def gh_put(path, data, sha, message):
    content_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    content_b64 = base64.b64encode(content_bytes).decode("ascii")
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"
    body = {"message": message, "content": content_b64, "sha": sha}
    r = requests.put(url, json=body, headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }, timeout=15)
    r.raise_for_status()
    return r.json()["content"]["sha"]

# ── 17track API ───────────────────────────────────────

def check_17track(tracking_number):
    """Restituisce lo status CRM normalizzato, o None se invariato/errore."""
    if not TRACK17_KEY:
        print(f"    ⚠ TRACK17_API_KEY non impostata — skip tracking")
        return None
    try:
        r = requests.post(
            "https://api.17track.net/track/v2.2/gettrackinfo",
            headers={"17token": TRACK17_KEY, "Content-Type": "application/json"},
            json=[{"number": tracking_number}],
            timeout=15
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            print(f"    ⚠ 17track codice errore: {data.get('code')}")
            return None
        accepted = data.get("data", {}).get("accepted", [])
        if not accepted:
            return None
        tag = accepted[0].get("track", {}).get("tag", "")
        return STATUS_MAP_17TRACK.get(tag)
    except Exception as e:
        print(f"    ✗ 17track error: {e}")
        return None

# ── Brevo email ───────────────────────────────────────

def send_email(to_email, to_name, subject, body_text):
    if not BREVO_API_KEY:
        print(f"    ⚠ BREVO_API_KEY non impostata — email saltata")
        return False
    try:
        r = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
            json={
                "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
                "to": [{"email": to_email, "name": to_name}],
                "subject": subject,
                "textContent": body_text,
                "tags": ["wine-crm", "ordini", "auto-tracking"]
            },
            timeout=15
        )
        return r.status_code == 201
    except Exception as e:
        print(f"    ✗ Brevo error: {e}")
        return False

def build_email(order, new_status):
    """Restituisce (subject, body) per il nuovo stato. None se non va inviata email."""
    nome = order["customerName"].split()[0]
    tracking = order.get("trackingNumber", "")
    track_url = f"https://www.17track.net/en/track?nums={tracking}" if tracking else ""

    firma = "\n\nLuca Pattaro\nIl Ciliegio — Azienda Agricola\nexport@ilciliegio.com | +39 331 1347899"

    if new_status == "spedito":
        subj = f"Il tuo ordine è partito!{' — Tracking: '+tracking if tracking else ''}"
        body = (f"Caro {nome},\n\nil tuo ordine è stato spedito ed è in viaggio verso di te! 🍷\n\n"
                + (f"Tracking: {tracking}\nSeguilo su: {track_url}\n\n" if tracking else "")
                + "Consegna stimata: 7–10 giorni lavorativi." + firma)
    elif new_status == "in_transito":
        subj = "Aggiornamento spedizione — Il tuo vino è in viaggio"
        body = (f"Caro {nome},\n\nil tuo ordine è in transito e procede regolarmente. 📦\n\n"
                + (f"Aggiornamenti: {track_url}\n\n" if track_url else "")
                + "Tempi stimati: 5–10 giorni lavorativi dalla spedizione." + firma)
    elif new_status == "dogana":
        subj = "Il tuo ordine è in fase di sdoganamento"
        body = (f"Caro {nome},\n\nil tuo ordine è in dogana (normalmente 2–5 giorni lavorativi).\n\n"
                + (f"Segui: {track_url}\n\n" if track_url else "")
                + "Non è richiesta nessuna azione da parte tua — ti aggiorneremo appena riparte." + firma)
    elif new_status == "consegnato":
        subj = "Il tuo ordine è stato consegnato! 🍷 Buona degustazione!"
        body = f"Caro {nome},\n\nottime notizie! Il tuo ordine è stato consegnato con successo. 🎉\n\nSperiamo che i vini ti piacciano — qualsiasi feedback è benvenuto!" + firma
    elif new_status == "problema":
        subj = "⚠ Aggiornamento importante sulla tua spedizione"
        body = (f"Caro {nome},\n\nsi è verificato un problema con la tua spedizione. Il nostro team è già al lavoro.\n\n"
                + (f"Tracking: {tracking}" if tracking else "")
                + "\n\nTi aggiorneremo al più presto. Per urgenze rispondi a questa email." + firma)
    else:
        return None, None

    return subj, body

# ── Main ──────────────────────────────────────────────

def run():
    if not ENABLED:
        print("⏸  Script disabilitato — imposta ENABLED = True per attivare.")
        return

    if not GITHUB_TOKEN:
        sys.exit("✗ GH_TOKEN non configurato")

    print(f"📂 Carico ordini da GitHub ({GITHUB_OWNER}/{GITHUB_REPO})...")
    try:
        db, sha = gh_get(ORD_PATH)
    except Exception as e:
        sys.exit(f"✗ Errore lettura ordini.json: {e}")

    orders = db.get("orders", [])
    attivi = [o for o in orders
              if o.get("trackingNumber")
              and o.get("status") not in ("consegnato", "annullato")]

    print(f"📦 {len(attivi)} ordini attivi con tracking da verificare\n")

    changed = 0
    for order in attivi:
        tracking = order["trackingNumber"]
        current  = order["status"]
        print(f"  {order['customerName']} ({tracking}) — stato attuale: {current}")

        new_status = check_17track(tracking)

        if not new_status:
            print(f"    → Nessun aggiornamento da 17track")
            continue
        if new_status == current:
            print(f"    → Stato invariato ({current})")
            continue

        print(f"    → Cambio: {current} → {new_status}")

        # Aggiorna ordine
        order["status"] = new_status
        now_ms = int(datetime.now().timestamp() * 1000)
        order.setdefault("statusHistory", []).append({
            "status": new_status,
            "date":   now_ms,
            "note":   "Aggiornato automaticamente dallo script tracking"
        })
        if new_status == "spedito" and not order.get("shippingDate"):
            order["shippingDate"] = now_ms
        order["updatedAt"] = now_ms

        # Email al cliente
        customer_email = order.get("customerEmail", "").strip()
        if customer_email:
            subject, body = build_email(order, new_status)
            if subject:
                ok = send_email(customer_email, order["customerName"], subject, body)
                if ok:
                    order.setdefault("emailsSent", []).append({
                        "type":   new_status,
                        "sentAt": now_ms,
                        "source": "auto-tracking"
                    })
                    print(f"    📧 Email inviata a {customer_email}")
                else:
                    print(f"    ⚠ Email non inviata")
        else:
            print(f"    ⚠ Email cliente mancante — notifica saltata")

        changed += 1

    if changed > 0:
        msg = f"Auto-tracking: {changed} ordini aggiornati — {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        print(f"\n💾 Salvo su GitHub...")
        new_sha = gh_put(ORD_PATH, db, sha, msg)
        print(f"✓ Salvato ({new_sha[:8]}...)")
    else:
        print("\n✓ Nessun aggiornamento necessario")


if __name__ == "__main__":
    run()
