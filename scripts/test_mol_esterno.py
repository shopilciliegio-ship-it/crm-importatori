"""
Prova ESTERNA su MBE Online (MOL) — NON fa parte della pipeline del CRM.
Sola lettura: non scrive in ordini.json, non fa commit, non modifica nulla.

Il repo e' pubblico e i log delle Actions sono leggibili da tutti: qui nel log vanno SOLO numeri
e stati aggregati. Il dettaglio (nomi, tracking, confronto ordine per ordine) va solo nella
mail al destinatario del digest del CRM (Brevo).

Prova A: API ufficiale e-link (SOAP) — era bloccata da un WAF (403).
Prova B: login MBE Online con 2FA + lettura spedizioni (la pagina /shipments) e confronto col CRM.
"""
import base64
import json
import os
import re
import sys
import traceback

import requests

sys.path.insert(0, os.path.dirname(__file__))

REPORT = []          # righe del dettaglio (solo per la mail)


def log(msg):        # log pubblico: solo cose non sensibili
    print(msg, flush=True)


def rep(msg):
    REPORT.append(msg)


def norm(s):
    return re.sub(r'\s+', ' ', (s or '').upper().strip())


def load_orders():
    with open('data/ordini.json', encoding='utf-8') as f:
        return json.load(f)['orders']


def digest_recipient():
    # stesso destinatario del digest gia' usato dal CRM (send_reminders.py)
    with open(os.path.join(os.path.dirname(__file__), 'send_reminders.py'), encoding='utf-8') as f:
        m = re.search(r"DIGEST_RECIPIENT\s*=\s*'([^']+)'", f.read())
    return m.group(1) if m else None


# ───────────────────────── Prova B: login + spedizioni ─────────────────────────
def _shipkey(s):
    return str(s.get('id') or s.get('mbeTracking') or s.get('shipmentTrackingNumber') or id(s))


def _fetch_tagged(m, token):
    """Come fetch_all_shipments ma tiene traccia della lista di provenienza."""
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json;charset=UTF-8',
        'baseurl': 'www.mbeonline.it',
        'source': 'Online',
        'x-teleport-tenant': '1',
    }
    body = {'and': [{'field': 'customerId', 'type': 'INTEGER', 'operation': '=', 'values': [m.CUSTOMER_ID]}]}
    out = {}
    for ep in m.MBE_ENDPOINTS:
        items, page = [], 0
        while True:
            url = f'{m.MBE_API_BASE}/shipments/search/{ep}?page={page}&pageSize=100&sortBy=creationDate+desc'
            r = requests.post(url, headers=headers, json=body, timeout=30)
            r.raise_for_status()
            data = r.json()
            items.extend(data.get('content', []))
            if data.get('last', True):
                break
            page += 1
        out[ep] = items
    return out


def prova_b(orders):
    rep('=== PROVA B (v2): login MBE Online + spedizioni ===')
    try:
        import fetch_mbe_tracking as m
        token = m.get_token()
        log('B: login OK')
        rep('Login: OK')
        per_ep = _fetch_tagged(m, token)
    except Exception as e:
        log(f'B: FALLITA ({type(e).__name__})')
        rep(f'FALLITA: {type(e).__name__}: {str(e)[:400]}')
        return

    # --- conteggi per lista, duplicati, date ---
    keys = {}
    for ep, items in per_ep.items():
        ks = [_shipkey(s) for s in items]
        keys[ep] = set(ks)
        dates = sorted(str(s.get('creationDate') or s.get('shipmentDate') or '')[:10] for s in items)
        log(f'B: lista {ep}: {len(items)} righe, {len(set(ks))} uniche')
        rep(f'Lista {ep}: {len(items)} righe, {len(set(ks))} uniche, dal {dates[0] if dates else "-"} al {dates[-1] if dates else "-"}')
    eps = list(per_ep)
    if len(eps) == 2:
        comuni = keys[eps[0]] & keys[eps[1]]
        log(f'B: spedizioni presenti in ENTRAMBE le liste: {len(comuni)}')
        rep(f'In entrambe le liste: {len(comuni)}')

    uniche = {}
    for items in per_ep.values():
        for s in items:
            uniche.setdefault(_shipkey(s), s)
    ships = list(uniche.values())
    log(f'B: spedizioni UNICHE su MBE: {len(ships)}')
    rep(f'Spedizioni uniche: {len(ships)}')
    if not ships:
        return

    s0 = ships[0]
    pk0 = (s0.get('shipmentPackages') or [{}])[0]
    rep(f'Campi spedizione: {sorted(s0.keys())}')
    rep(f'Campi collo: {sorted(pk0.keys())}')

    by_name = {}
    for s in ships:
        n = norm((s.get('addressTo') or {}).get('companyName'))
        if n:
            by_name.setdefault(n, []).append(s)

    def ups_of(s):
        return str(s.get('shipmentTrackingNumber') or '').strip()

    # --- ordini aperti SENZA numero UPS: cosa trova MOL ---
    aperti = [o for o in orders if o.get('status') not in ('consegnato', 'annullato')]
    senza = [o for o in aperti if not o.get('trackingNumber')]
    trovati = 0
    rep(f'\nOrdini aperti senza numero UPS nel CRM: {len(senza)}')
    for o in senza:
        c = by_name.get(norm(o.get('customerName'))) or []
        if c:
            trovati += 1
            rep(f"- {o.get('customerName')} | CRM={o.get('status')} | MOL: " +
                '; '.join(f"UPS={ups_of(s)} mbe={s.get('mbeTracking')} creata={str(s.get('creationDate'))[:10]}" for s in c[:3]))
        else:
            rep(f"- {o.get('customerName')} | CRM={o.get('status')} | NON ancora su MOL")
    log(f'B: ordini aperti senza UPS: {len(senza)}; di cui trovati su MOL con un numero: {trovati}')

    # --- tutti gli ordini col numero UPS: coincide con quello di MOL? ---
    uguali = diversi = nonmol = 0
    rep('\nControllo numero UPS CRM vs MOL (tutti gli ordini con numero UPS):')
    for o in orders:
        t = str(o.get('trackingNumber') or '').strip()
        if not t:
            continue
        c = by_name.get(norm(o.get('customerName'))) or []
        if not c:
            nonmol += 1
            continue
        if any(ups_of(s) == t for s in c):
            uguali += 1
        else:
            diversi += 1
            rep(f"- DIVERSO: {o.get('customerName')} | CRM={t} | MOL=" + ','.join(ups_of(s) for s in c[:3]))
    log(f'B: numero UPS uguale CRM/MOL: {uguali}; diverso: {diversi}; ordine non trovato su MOL: {nonmol}')
    rep(f'Uguali: {uguali}; diversi: {diversi}; non trovati su MOL: {nonmol}')

    # --- spedizioni MOL (uniche) senza ordine nel CRM ---
    crm_names = {norm(o.get('customerName')) for o in orders}
    crm_ups = {str(o.get('trackingNumber')) for o in orders if o.get('trackingNumber')}
    orfane = [s for s in ships
              if norm((s.get('addressTo') or {}).get('companyName')) not in crm_names and ups_of(s) not in crm_ups]
    log(f'B: spedizioni MOL uniche senza ordine nel CRM: {len(orfane)}')
    rep(f'\nSpedizioni MOL uniche senza ordine nel CRM: {len(orfane)}')
    for s in orfane[:40]:
        rep(f"- {(s.get('addressTo') or {}).get('companyName')} | UPS={ups_of(s)} | creata={str(s.get('creationDate'))[:10]} | delivered={s.get('delivered')}")



# ───────────────────────── Prova A: API e-link ─────────────────────────
def prova_a(orders):
    rep('\n=== PROVA A: API ufficiale e-link ===')
    user = os.environ.get('MBE_ELINK_USERNAME', '')
    pw = os.environ.get('MBE_ELINK_PASSPHRASE', '')
    if not user or not pw:
        log('A: credenziali e-link mancanti')
        rep('Credenziali e-link mancanti')
        return
    basic = 'Basic ' + base64.b64encode(f'{user}:{pw}'.encode()).decode()
    body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ws="http://www.onlinembe.it/ws/">'
        '<soapenv:Header/><soapenv:Body><ws:ManageCustomerRequest><RequestContainer>'
        f'<Credentials><Username>{user}</Username><Passphrase>{pw}</Passphrase></Credentials>'
        '<InternalReferenceID>Test</InternalReferenceID><Action>GET</Action>'
        '</RequestContainer></ws:ManageCustomerRequest></soapenv:Body></soapenv:Envelope>'
    )
    h = {'Content-Type': 'text/xml; charset=utf-8', 'SOAPAction': '"ManageCustomerRequest"', 'Authorization': basic}
    try:
        r = requests.post('https://api.mbeonline.it/ws', data=body.encode(), headers=h, timeout=30)
    except Exception as e:
        log(f'A: errore rete {type(e).__name__}')
        rep(f'errore: {e}')
        return
    log(f'A: ManageCustomer: HTTP {r.status_code}')
    rep(f'ManageCustomer: HTTP {r.status_code}  Server-Timing={r.headers.get("Server-Timing")}')
    if r.status_code != 200:
        log('A: API e-link ancora NON accessibile')
        rep('API e-link ancora NON accessibile (WAF).')
        return
    txt = re.sub(r'<Passphrase>.*?</Passphrase>', '<Passphrase>***</Passphrase>', r.text, flags=re.S)
    rep('Risposta (prime 300 car.): ' + txt[:300])
    try:
        import test_mbe_elink as t
        client = t.Client(t.WSDL_URL)
        service = t.fixed_service(client)
        aperti = [o for o in orders if o.get('status') not in ('consegnato', 'annullato') and o.get('mbeTrackingNumber')][:5]
        log(f'A: provo TrackingRequest su {len(aperti)} ordini aperti')
        for o in aperti:
            params = {'System': t.SYSTEM_VALUE, 'Credentials': {'Username': user, 'Passphrase': pw},
                      'InternalReferenceID': 'test', 'TrackingMBE': o['mbeTrackingNumber']}
            try:
                res = service.TrackingRequest(RequestContainer=params)
                rep(f"- {o.get('customerName')} ({o['mbeTrackingNumber']}): {str(t.serialize_object(res))[:600]}")
            except Exception as e:
                rep(f"- {o.get('customerName')}: errore {type(e).__name__}: {str(e)[:200]}")
    except Exception as e:
        rep(f'TrackingRequest non eseguibile: {type(e).__name__}: {e}')


# ───────────────────────── Mail con il dettaglio ─────────────────────────
def invia_mail():
    key = os.environ.get('BREVO_API_KEY')
    to = digest_recipient()
    if not key or not to:
        log('mail: chiave Brevo o destinatario mancanti')
        return
    html = '<pre style="font:13px/1.4 monospace;white-space:pre-wrap">' + \
        '\n'.join(REPORT).replace('&', '&amp;').replace('<', '&lt;') + '</pre>'
    r = requests.post('https://api.brevo.com/v3/smtp/email',
                      headers={'api-key': key, 'Content-Type': 'application/json'},
                      json={'sender': {'name': 'CRM Il Ciliegio', 'email': 'luca@sienawine.it'},
                            'to': [{'email': to}],
                            'subject': 'Prova MBE Online (MOL): risultati',
                            'htmlContent': html}, timeout=30)
    log(f'mail dettaglio: HTTP {r.status_code}')


def main():
    orders = load_orders()
    log(f'Ordini nel CRM: {len(orders)}')
    for fn in (prova_b, prova_a):
        try:
            fn(orders)
        except Exception:
            log(f'{fn.__name__}: eccezione {sys.exc_info()[0].__name__}')
            REPORT.append(traceback.format_exc()[-800:])
    invia_mail()


if __name__ == '__main__':
    main()
