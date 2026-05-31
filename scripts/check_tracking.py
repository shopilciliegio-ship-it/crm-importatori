#!/usr/bin/env python3
"""
Tracking automatico ordini — Il Ciliegio CRM
Controlla lo stato spedizioni via 17track API, aggiorna data/ordini.json su GitHub
e invia email al cliente via Brevo ad ogni cambio di stato.

Variabili d'ambiente:
  TRACKING_ENABLED  "true" per attivare (default: false)
  DRY_RUN           "true" per simulare senza salvare né inviare email (default: false)
  GH_TOKEN          GitHub token (GITHUB_TOKEN è auto-fornito da Actions)
  GH_OWNER          es. shopilciliegio-ship-it
  GH_REPO           es. crm-importatori
  BREVO_API_KEY     chiave API Brevo
  TRACK17_API_KEY   chiave API 17track (platform.17track.net)
  SENDER_EMAIL      mittente email (default: export@ilciliegio.com)
  SENDER_NAME       nome mittente (default: Il Ciliegio — Azienda Agricola)
"""

import os, json, base64, sys
from datetime import datetime

try:
    import requests
except ImportError:
    sys.exit("Installa dipendenze: pip install requests")

# ── Config ────────────────────────────────────────────────────────────────────
ENABLED   = os.environ.get("TRACKING_ENABLED", "false").lower() == "true"
DRY_RUN   = os.environ.get("DRY_RUN",          "false").lower() == "true"

GH_TOKEN      = os.environ.get("GH_TOKEN",      "")
GH_OWNER      = os.environ.get("GH_OWNER",      "shopilciliegio-ship-it")
GH_REPO       = os.environ.get("GH_REPO",       "crm-importatori")
BREVO_KEY     = os.environ.get("BREVO_API_KEY",  "")
TRACK17_KEY   = os.environ.get("TRACK17_API_KEY","")
SENDER_EMAIL  = os.environ.get("SENDER_EMAIL",   "export@ilciliegio.com")
SENDER_NAME   = os.environ.get("SENDER_NAME",    "Il Ciliegio — Azienda Agricola")

ORD_PATH = "data/ordini.json"

# Mappatura tag 17track → stati CRM
# Ref: https://www.17track.net/en/apidoc
STATUS_MAP = {
    "InfoReceived":  "preparazione",  # etichetta creata, non ancora ritirato
    "PickedUp":      "spedito",       # ritirato dal corriere
    "InTransit":     "in_transito",
    "Delivered":     "consegnato",
    "UnDelivered":   "problema",
    "Returning":     "problema",
    "Returned":      "problema",
    "Exception":     "problema",
    "Expired":       "problema",
    "NotFound":      None,            # non ancora tracciato — ignora
}

# Stati che non aggiorniamo automaticamente (terminali o gestiti a mano)
STATI_FINALI = {"consegnato", "annullato", "problema"}

# ── GitHub helpers ────────────────────────────────────────────────────────────

_GH_HDR = lambda: {
    "Authorization": f"token {GH_TOKEN}",
    "Accept":        "application/vnd.github.v3+json",
}

def gh_get(path):
    url = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{path}"
    r = requests.get(url, headers=_GH_HDR(), timeout=15)
    r.raise_for_status()
    d = r.json()
    content = base64.b64decode(d["content"].replace("\n", "")).decode("utf-8")
    return json.loads(content), d["sha"]

def gh_put(path, data, sha, message):
    content_b64 = base64.b64encode(
        json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    url = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{path}"
    r = requests.put(url, json={"message": message, "content": content_b64, "sha": sha},
                     headers=_GH_HDR(), timeout=15)
    r.raise_for_status()
    return r.json()["content"]["sha"]

# ── 17track API ───────────────────────────────────────────────────────────────

def check_17track(tracking_number: str) -> str | None:
    """Restituisce lo stato CRM normalizzato, o None se non aggiornato/errore."""
    if not TRACK17_KEY:
        print("    ⚠ TRACK17_API_KEY non impostata — skip")
        return None
    try:
        r = requests.post(
            "https://api.17track.net/track/v2.2/gettrackinfo",
            headers={"17token": TRACK17_KEY, "Content-Type": "application/json"},
            json=[{"number": tracking_number}],
            timeout=20
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            print(f"    ⚠ 17track errore {data.get('code')}: {data.get('message','')}")
            return None
        accepted = data.get("data", {}).get("accepted", [])
        if not accepted:
            return None
        track_info = accepted[0].get("track", {})
        tag = track_info.get("tag", "")
        new_status = STATUS_MAP.get(tag)

        # Tenta di rilevare dogana dal testo dell'ultimo evento
        if new_status == "in_transito":
            latest = track_info.get("lastEvent", {}).get("description", "").lower()
            if any(w in latest for w in ("customs", "dogana", "clearance", "sdoganamento")):
                new_status = "dogana"

        return new_status
    except Exception as e:
        print(f"    ✗ 17track error: {e}")
        return None

# ── Brevo email ───────────────────────────────────────────────────────────────

def send_status_email(order: dict, new_status: str) -> bool:
    if not BREVO_KEY:
        print("    ⚠ BREVO_API_KEY non impostata — email saltata")
        return False
    to_email = order.get("customerEmail", "").strip()
    if not to_email:
        print("    ⚠ Email cliente mancante — notifica saltata")
        return False

    subject, body = _build_email(order, new_status)
    if not subject:
        return False

    if DRY_RUN:
        print(f"    📧 [DRY RUN] Email a {to_email}: {subject}")
        return True

    try:
        r = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": BREVO_KEY, "Content-Type": "application/json"},
            json={
                "sender":      {"name": SENDER_NAME, "email": SENDER_EMAIL},
                "to":          [{"email": to_email, "name": order["customerName"]}],
                "subject":     subject,
                "textContent": body,
                "tags":        ["wine-crm", "ordini", "auto-tracking"],
            },
            timeout=15
        )
        ok = r.status_code == 201
        if ok:
            print(f"    📧 Email inviata a {to_email}")
        else:
            print(f"    ⚠ Brevo {r.status_code}: {r.text[:120]}")
        return ok
    except Exception as e:
        print(f"    ✗ Brevo error: {e}")
        return False

def _build_email(order: dict, status: str) -> tuple[str, str]:
    nome     = order["customerName"].split()[0]
    tracking = order.get("trackingNumber", "")
    track_url = f"https://www.17track.net/en/track?nums={tracking}" if tracking else ""
    firma = "\n\nLuca Pattaro\nIl Ciliegio — Azienda Agricola\nexport@ilciliegio.com | +39 331 1347899"

    if status == "spedito":
        return (
            f"Il tuo ordine è partito!{' — Tracking: '+tracking if tracking else ''}",
            f"Caro {nome},\n\nil tuo ordine è stato spedito ed è in viaggio! 🍷\n\n"
            + (f"Tracking: {tracking}\nSeguilo su: {track_url}\n\n" if tracking else "")
            + "Consegna stimata: 7–10 giorni lavorativi." + firma
        )
    if status == "in_transito":
        return (
            "Aggiornamento spedizione — Il tuo vino è in viaggio",
            f"Caro {nome},\n\nil tuo ordine è in transito e procede regolarmente. 📦\n\n"
            + (f"Aggiornamenti: {track_url}\n\n" if track_url else "")
            + "Tempi stimati: 5–10 giorni lavorativi dalla spedizione." + firma
        )
    if status == "dogana":
        return (
            "Il tuo ordine è in fase di sdoganamento",
            f"Caro {nome},\n\nil tuo ordine è attualmente in dogana (di solito 2–5 giorni lavorativi).\n\n"
            + (f"Segui l'avanzamento: {track_url}\n\n" if track_url else "")
            + "Non è richiesta nessuna azione da parte tua — ti aggiorneremo appena riparte." + firma
        )
    if status == "consegnato":
        return (
            "Il tuo ordine è stato consegnato! 🍷 Buona degustazione!",
            f"Caro {nome},\n\nottime notizie! Il tuo ordine è arrivato. 🎉\n\n"
            + "Speriamo che i vini ti piacciano — qualsiasi feedback è benvenuto!" + firma
        )
    if status == "problema":
        return (
            "⚠ Aggiornamento importante sulla tua spedizione",
            f"Caro {nome},\n\nsi è verificato un problema con la tua spedizione. "
            + "Il nostro team è già al lavoro.\n\n"
            + (f"Tracking: {tracking}\n\n" if tracking else "")
            + "Ti aggiorneremo al più presto. Per urgenze rispondi a questa email." + firma
        )
    return "", ""

# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    if not ENABLED:
        print("⏸  Script disabilitato (TRACKING_ENABLED != 'true').")
        return

    if not GH_TOKEN:
        sys.exit("✗ GH_TOKEN non configurato")

    mode = "[DRY RUN] " if DRY_RUN else ""
    print(f"📦 {mode}Carico ordini da {GH_OWNER}/{GH_REPO}...")

    try:
        db, sha = gh_get(ORD_PATH)
    except Exception as e:
        sys.exit(f"✗ Errore lettura ordini.json: {e}")

    orders = db.get("orders", [])
    attivi = [
        o for o in orders
        if o.get("trackingNumber")
        and o.get("status") not in STATI_FINALI
    ]

    print(f"🔍 {len(attivi)} ordini attivi con tracking da verificare\n")
    if not attivi:
        print("✓ Nessun ordine da controllare.")
        return

    changed = 0
    now_ms  = int(datetime.now().timestamp() * 1000)

    for order in attivi:
        tracking = order["trackingNumber"]
        current  = order["status"]
        print(f"  {order['customerName']} ({order.get('shipmentCode','?')}) "
              f"tracking={tracking} stato={current}")

        new_status = check_17track(tracking)

        if new_status is None:
            print(f"    → Nessun aggiornamento da 17track")
            continue
        if new_status == current:
            print(f"    → Invariato ({current})")
            continue

        print(f"    → Cambio: {current} → {new_status}")

        if DRY_RUN:
            print(f"    [DRY RUN] saltato aggiornamento e email")
            continue

        # Aggiorna ordine
        order["status"] = new_status
        order.setdefault("statusHistory", []).append({
            "status": new_status,
            "date":   now_ms,
            "note":   "Aggiornato automaticamente — 17track"
        })
        if new_status == "spedito" and not order.get("shippingDate"):
            order["shippingDate"] = now_ms
        order["updatedAt"] = now_ms

        # Email cliente
        ok = send_status_email(order, new_status)
        if ok:
            order.setdefault("emailsSent", []).append({
                "type":   new_status,
                "sentAt": now_ms,
                "source": "auto-tracking"
            })

        changed += 1

    if changed > 0 and not DRY_RUN:
        msg = f"Auto-tracking: {changed} ordini aggiornati — {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        print(f"\n💾 Salvo su GitHub...")
        new_sha = gh_put(ORD_PATH, db, sha, msg)
        print(f"✓ Salvato ({new_sha[:8]}...)")
    elif changed == 0:
        print("\n✓ Nessun aggiornamento necessario.")
    else:
        print(f"\n[DRY RUN] {changed} ordini avrebbero cambiato stato — nessun salvataggio.")


if __name__ == "__main__":
    run()
