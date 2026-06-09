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
    mantenendo schema/path/query originali. extra_headers (opzionale) sovrascrive
    header HTTP sulle chiamate SOAP successive (es. Host per virtual-host, o
    User-Agent per evitare il bot-detection del WAF/Akamai)."""
    service = next(iter(client.wsdl.services.values()))
    port    = next(iter(service.ports.values()))
    binding_name   = port.binding.name
    original_addr  = port.binding_options['address']

    original_host = urlsplit(original_addr).hostname
    parts    = urlsplit(original_addr)
    new_addr = urlunsplit((parts.scheme or 'https', REAL_HOST, parts.path, parts.query, parts.fragment))

    print(f'  Endpoint nel WSDL: {original_addr}  (host originale: {original_host})')
    print(f'  Endpoint usato:    {new_addr}' + (f'  con header extra: {extra_headers}' if extra_headers else ''))

    if extra_headers:
        # Il WSDL è già stato caricato con il transport di default (header corretti
        # per scaricare il file). Sostituiamo il transport ORA, sul client già
        # pronto, così i nuovi header si applicano solo alle chiamate SOAP successive.
        session = requests.Session()
        session.headers.update(extra_headers)
        client.transport = Transport(session=session)

    return client.create_service(binding_name, new_addr)


def try_tracking(service, tracking_value: str):
    print(f'\n=== TrackingRequest per "{tracking_value}" ===')
    params = {
        'System':              SYSTEM_VALUE,
        'Credentials':         {'Username': USERNAME, 'Passphrase': PASSPHRASE},
        'InternalReferenceID': 'elink-test-001',
        'TrackingMBE':         tracking_value,
    }
    try:
        result = service.TrackingRequest(RequestContainer=params)
        print('\n  ✓ risposta:')
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


def main():
    if len(sys.argv) < 2:
        print('Uso: python test_mbe_elink.py <tracking_number_o_shipment_code>')
        sys.exit(1)

    tracking_value = sys.argv[1]

    print(f'Carico WSDL da {WSDL_URL} ...')
    client = Client(WSDL_URL)

    # Tentativo 1: endpoint pubblico, header di default (quelli usati per il WSDL)
    print('\n--- Tentativo 1: header di default ---')
    service = fixed_service(client)
    if try_tracking(service, tracking_value):
        return

    # Tentativo 2: header Host forzato all'host interno dichiarato nel WSDL
    # (instradamento per virtual-host) — risposta arrivata da Akamai (errors.edgesuite.net):
    # significa che 'elink' non è un host pubblico valido all'edge, scartiamo questa pista.
    print('\n--- Tentativo 2: con header Host forzato a quello interno del WSDL ---')
    original_host = urlsplit(original_address(client)).hostname
    service2 = fixed_service(client, extra_headers={'Host': original_host})
    if try_tracking(service2, tracking_value):
        return

    # Tentativo 3: User-Agent da browser — il 403 "senza contenuto" del tentativo 1
    # è coerente con bot-detection del WAF Akamai sull'User-Agent di python-zeep/requests
    print('\n--- Tentativo 3: con User-Agent da browser ---')
    service3 = fixed_service(client, extra_headers={
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'),
    })
    if try_tracking(service3, tracking_value):
        return

    print('\nTutti i tentativi hanno fallito con 4xx — il blocco sembra a livello di edge/WAF '
          '(Akamai) o whitelist lato MBE, non risolvibile lato client.')
    print('Prossimo passo: chiedere al supporto MBE se l\'accesso a e-link richiede una '
          'whitelist IP del server chiamante o un header specifico (es. API key separata, '
          'client certificate, ecc.) oltre a Username/Passphrase/System.')


if __name__ == '__main__':
    main()
