"""
Test e-link MBE — script usa e getta per interrogare TrackingRequest dell'API
SOAP/WSDL ufficiale MBE e confrontare gli stati con Fieramente.
Non fa parte della pipeline.

Uso:
    pip install zeep
    set MBE_ELINK_USERNAME=...
    set MBE_ELINK_PASSPHRASE=...
    python scripts/test_mbe_elink.py <tracking_number_o_shipment_code>
"""

import base64
import os
import sys
from urllib.parse import urlsplit, urlunsplit

import requests
from zeep import Client
from zeep.transports import Transport
from zeep.helpers import serialize_object

WSDL_URL  = 'https://api.mbeonline.it/ws/e-link.wsdl'
REAL_HOST = 'api.mbeonline.it'

USERNAME   = os.environ['MBE_ELINK_USERNAME']
PASSPHRASE = os.environ['MBE_ELINK_PASSPHRASE']

# MBE ha confermato (screenshot Postman funzionante) che, oltre alle credenziali
# nel body SOAP (Credentials/Username+Passphrase), la richiesta porta un header
# HTTP "Authorization" — Basic Auth con le stesse credenziali.
BASIC_AUTH = 'Basic ' + base64.b64encode(f'{USERNAME}:{PASSPHRASE}'.encode('utf-8')).decode('ascii')

# "Plugin" supera la validazione client-side di zeep, ma secondo la documentazione
# ufficiale OnlineMbe (onlinembe.de/wsdl/documentation.html) il campo SystemType è
# in realtà un enum geografico (IT/DE/ES/AT/FR, "definito dall'URL chiamante").
# Per l'endpoint italiano api.mbeonline.it il valore corretto è quindi "IT".
SYSTEM_VALUE = 'IT'


def original_address(client: Client) -> str:
    service = next(iter(client.wsdl.services.values()))
    port    = next(iter(service.ports.values()))
    return port.binding_options['address']


def fixed_service(client: Client, extra_headers: dict | None = None):
    """Il WSDL espone un endpoint con host interno (es. 'elink') non risolvibile
    pubblicamente. Lo ricreiamo sostituendo l'host con quello pubblico reale,
    mantenendo schema/path/query originali. extra_headers (opzionale) aggiunge/
    sovrascrive header HTTP sulle chiamate SOAP successive (es. Host per
    virtual-host, o User-Agent per evitare il bot-detection del WAF/Akamai)."""
    service = next(iter(client.wsdl.services.values()))
    port    = next(iter(service.ports.values()))
    binding_name   = port.binding.name
    original_addr  = port.binding_options['address']

    original_host = urlsplit(original_addr).hostname
    parts    = urlsplit(original_addr)
    new_addr = urlunsplit((parts.scheme or 'https', REAL_HOST, parts.path, parts.query, parts.fragment))

    print(f'  Endpoint nel WSDL: {original_addr}  (host originale: {original_host})')
    print(f'  Endpoint usato:    {new_addr}' + (f'  con header extra: {extra_headers}' if extra_headers else ''))

    # Il WSDL è già stato caricato con il transport di default (header corretti
    # per scaricare il file). Sostituiamo il transport ORA, sul client già
    # pronto, così i nuovi header si applicano solo alle chiamate SOAP successive.
    # Authorization Basic sempre presente, come nell'esempio Postman fornito da MBE.
    headers = {'Authorization': BASIC_AUTH}
    if extra_headers:
        headers.update(extra_headers)
    session = requests.Session()
    session.headers.update(headers)
    client.transport = Transport(session=session)

    return client.create_service(binding_name, new_addr)


def _call(service, operation: str, params: dict) -> bool:
    try:
        result = getattr(service, operation)(RequestContainer=params)
        print(f'\n  ✓ risposta:')
        print(f'  {serialize_object(result)}')
        return True
    except Exception as e:
        status  = getattr(e, 'status_code', None)
        content = getattr(e, 'content', None)
        print(f'\n  ✗ errore ({type(e).__name__}): {e}')
        if status is not None:
            print(f'    status_code: {status}')
        if content:
            print(f'    content: {content!r}')
        return False


def try_manage_customer_raw(endpoint_url: str, extra_headers: dict | None = None) -> bool:
    """ManageCustomerRequest GET via raw HTTP POST — bypassa la validazione zeep."""
    print('\n=== ManageCustomerRequest (Action=GET) — raw SOAP ===')
    soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ws="http://www.onlinembe.it/ws/">
  <soapenv:Header/>
  <soapenv:Body>
    <ws:ManageCustomerRequest>
      <RequestContainer>
        <Credentials>
          <Username>{USERNAME}</Username>
          <Passphrase>{PASSPHRASE}</Passphrase>
        </Credentials>
        <InternalReferenceID>Test</InternalReferenceID>
        <Action>GET</Action>
      </RequestContainer>
    </ws:ManageCustomerRequest>
  </soapenv:Body>
</soapenv:Envelope>"""

    headers = {
        'Content-Type':  'text/xml; charset=utf-8',
        'SOAPAction':    '"ManageCustomerRequest"',
        'Authorization': BASIC_AUTH,
    }
    if extra_headers:
        headers.update(extra_headers)

    try:
        r = requests.post(endpoint_url, data=soap_body.encode('utf-8'), headers=headers, timeout=30)
        print(f'  HTTP {r.status_code}')
        print(f'  {r.text[:2000]}')
        return r.status_code == 200
    except Exception as e:
        print(f'  ✗ errore: {e}')
        return False


def try_tracking(service, tracking_value: str) -> bool:
    print(f'\n=== TrackingRequest per "{tracking_value}" ===')
    params = {
        'System':              SYSTEM_VALUE,
        'Credentials':         {'Username': USERNAME, 'Passphrase': PASSPHRASE},
        'InternalReferenceID': 'elink-test-001',
        'TrackingMBE':         tracking_value,
    }
    return _call(service, 'TrackingRequest', params)


def main():
    tracking_value = sys.argv[1] if len(sys.argv) > 1 else None

    print(f'Carico WSDL da {WSDL_URL} ...')
    client = Client(WSDL_URL)

    # Ricava l'endpoint pubblico dal WSDL
    service     = fixed_service(client)
    endpoint_url = 'https://api.mbeonline.it/ws'

    # Passo 1: ManageCustomerRequest raw (esattamente come l'esempio del supporto MBE)
    if not try_manage_customer_raw(endpoint_url):
        print('\nRiprovo con User-Agent da browser (anti-WAF Akamai)...')
        ua = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
        if not try_manage_customer_raw(endpoint_url, extra_headers={'User-Agent': ua}):
            print('\nAncora bloccato — problema di whitelist IP o WAF, non risolvibile lato client.')
            return

    # Passo 2: TrackingRequest via zeep (solo se fornito un tracking number)
    if tracking_value:
        try_tracking(service, tracking_value)
    else:
        print('\nNessun tracking number fornito — fermato dopo ManageCustomer.')
        print('Uso: python test_mbe_elink.py <tracking_number>')


if __name__ == '__main__':
    main()
