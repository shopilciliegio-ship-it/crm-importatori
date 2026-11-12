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
def prova_b(orders):
    rep('=== PROVA B: login MBE Online + spedizioni ===')
    try:
        import fetch_mbe_tracking as m
        token = m.get_token()
        log('B: login OK')
        rep('Login: OK')
        ships = m.fetch_all_shipments(token)
    except Exception as e:
        log(f'B: FALLITA ({type(e).__name__})')
        rep(f'FALLITA: {type(e).__name__}: {str(e)[:400]}')
        return
    log(f'B: spedizioni lette da MBE: {len(ships)}')
    rep(f'Spedizioni lette: {len(ships)}')
    if not ships:
        return

    s0 = ships[0]
    pk0 = (s0.get('shipmentPackages') or [{}])[0]
    rep(f'Campi spedizione: {sorted(s0.keys())}')
    rep(f'Campi collo: {sorted(pk0.keys())}')

    by_trk = {}
    by_name = {}
    for s in ships:
        for k in (s.get('mbeTracking'), s.get('shipmentTrackingNumber')):
            if k:
                by_trk[str(k)] = s
        n = norm((s.get('addressTo') or {}).get('companyName'))
        if n and n not in by_name:
            by_name[n] = s

    aperti = [o for o in orders if o.get('status') not in ('consegnato', 'annullato')]
    log(f'B: ordini CRM ancora aperti: {len(aperti)}')
    piu_avanti = 0
    non_trovati = 0
    rep(f'\nOrdini CRM aperti: {len(aperti)}')
    for o in aperti:
        s = (by_trk.get(str(o.get('mbeTrackingNumber') or ''))
             or by_trk.get(str(o.get('trackingNumber') or ''))
             or by_name.get(norm(o.get('customerName'))))
        if not s:
            non_trovati += 1
            rep(f"- {o.get('customerName')} | CRM={o.get('status')} | NON trovato su MBE")
            continue
        pk = (s.get('shipmentPackages') or [{}])[0]
        deliv = bool(s.get('delivered'))
        if deliv:
            piu_avanti += 1
        rep(f"- {o.get('customerName')} | CRM={o.get('status')} | MBE delivered={deliv} "
            f"ultimo_stato_id={pk.get('trackingLastStatusMbeId')} "
            f"desc={pk.get('trackingLastStatusDescription') or pk.get('trackingLastStatus')}")
    log(f'B: aperti nel CRM ma CONSEGNATI su MBE: {piu_avanti}; non trovati su MBE: {non_trovati}')

    crm_trk = {str(o.get('mbeTrackingNumber')) for o in orders if o.get('mbeTrackingNumber')} | \
              {str(o.get('trackingNumber')) for o in orders if o.get('trackingNumber')}
    crm_names = {norm(o.get('customerName')) for o in orders}
    orfane = [s for s in ships
              if str(s.get('mbeTracking')) not in crm_trk and str(s.get('shipmentTrackingNumber')) not in crm_trk
              and norm((s.get('addressTo') or {}).get('companyName')) not in crm_names]
    log(f'B: spedizioni MBE senza ordine nel CRM: {len(orfane)}')
    rep(f'\nSpedizioni MBE senza ordine nel CRM: {len(orfane)} (prime 10)')
    for s in orfane[:10]:
        rep(f"- {(s.get('addressTo') or {}).get('companyName')} | {s.get('shipmentTrackingNumber')} | delivered={s.get('delivered')}")


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
