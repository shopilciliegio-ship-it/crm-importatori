# -*- coding: utf-8 -*-
"""
fix_failed_wave1_sends.py
==========================
Intervento puntuale, da eseguire UNA SOLA VOLTA.

Il batch wave1 del 17/06/2026 13:21 UTC (50 email) è stato inviato con un
sender (export@ilciliegio.com) non validato su Brevo. L'API ha comunque
risposto con un messageId (la validazione del sender avviene più avanti
nella pipeline di consegna, non alla chiamata API), quindi
send_clienti_wave.py li ha registrati come `waveStatus: wave1_sent` —
anche se l'email non è mai arrivata davvero ai destinatari.

Risultato: questi 50 contatti verrebbero saltati per sempre dalle prossime
wave (il filtro candidati esclude chiunque abbia già un waveStatus).

Questo script riporta i 50 contatti coinvolti allo stato precedente
(waveStatus, status, emailsSent, brevoEvents) cosi rientrano nel prossimo
batch — ora che il sender è stato corretto in luca@sienawine.it.
"""

import base64
import json
import os
import sys
from datetime import datetime, timezone

import requests

DATA_PATH = 'data/clienti.json'

GH_TOKEN = os.environ.get('GH_TOKEN', '')
GH_OWNER = os.environ.get('GH_OWNER', 'shopilciliegio-ship-it')
GH_REPO  = os.environ.get('GH_REPO', 'crm-importatori')

# I 50 contatti finiti in wave1_sent dal commit 85bdf80 (batch col sender rotto)
FAILED_IDS = [
    "cli_46bb0b94eb", "cli_e2b371aded", "cli_273e2a6629", "cli_5a2f89f44f", "cli_23a3d63021",
    "cli_5525e055ce", "cli_2908f98dbf", "cli_0cd3e4f33f", "cli_fbde29617e", "cli_65614159fb",
    "cli_4c296278e9", "cli_93b0172089", "cli_4f7074628f", "cli_391416639a", "cli_4449040d24",
    "cli_81708b360c", "cli_69c55f740b", "cli_338b699a80", "cli_ced9deffde", "cli_db0874b5a2",
    "cli_a600c89f3e", "cli_0c64c1c852", "cli_f2aa4a3b95", "cli_ca52b88d89", "cli_65655cc57c",
    "cli_7037446c0a", "cli_966fe949ba", "cli_522a7a1b7a", "cli_7dbe18875e", "cli_b1dcf9b287",
    "cli_4a3994a74b", "cli_9a224a67a5", "cli_f3adeb2bd0", "cli_dc977bf824", "cli_50c765c33d",
    "cli_ac3441e34d", "cli_fcf69e9ade", "cli_0cee4a74bf", "cli_dddd4cdb51", "cli_d1aa0ee674",
    "cli_17902dc733", "cli_d60adc2096", "cli_4dcdaec1aa", "cli_b22d5c6817", "cli_d010581343",
    "cli_0395430894", "cli_e3b7c4da0a", "cli_add6468d3f", "cli_c5d1b1e38c", "cli_c375f7c44e",
]

_GH_HEADERS = {
    'Authorization': f'token {GH_TOKEN}',
    'Accept':        'application/vnd.github.v3+json',
}


def gh_get(path: str):
    url = f'https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{path}'
    r = requests.get(url, headers=_GH_HEADERS, timeout=20)
    r.raise_for_status()
    d = r.json()
    sha = d.get('sha')
    raw = d.get('content', '').replace('\n', '')
    if raw:
        json_str = base64.b64decode(raw).decode('utf-8')
    else:
        dl = d.get('download_url')
        r2 = requests.get(dl, timeout=60)
        r2.raise_for_status()
        json_str = r2.text
    return json.loads(json_str), sha


def gh_put(path: str, data, sha: str, message: str) -> bool:
    url = f'https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{path}'
    content = base64.b64encode(
        json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    ).decode()
    body = {'message': message, 'content': content, 'sha': sha}
    r = requests.put(url, headers=_GH_HEADERS, json=body, timeout=30)
    if r.status_code in (200, 201):
        return True
    print(f'✗ gh_put {path}: {r.status_code} {r.text[:300]}')
    return False


def main():
    print('=== fix_failed_wave1_sends.py ===')
    db, sha = gh_get(DATA_PATH)
    contacts = db.get('contacts') or []
    by_id = {c['id']: c for c in contacts}

    reset = 0
    skipped = 0
    for cid in FAILED_IDS:
        c = by_id.get(cid)
        if not c:
            print(f'  ⚠ {cid}: non trovato, skip')
            skipped += 1
            continue
        if c.get('waveStatus') != 'wave1_sent':
            print(f'  ⚠ {cid}: waveStatus già diverso da wave1_sent ({c.get("waveStatus")}), skip per sicurezza')
            skipped += 1
            continue

        c['waveStatus'] = None
        c['emailsSent'] = [e for e in (c.get('emailsSent') or []) if e.get('type') != 'wave1']
        c['brevoEvents'] = [e for e in (c.get('brevoEvents') or [])
                             if e.get('subject') not in ('A special thought for you from Il Ciliegio 🍷',
                                                          'Un pensiero speciale per te da Il Ciliegio 🍷')]
        if c.get('status') == 'sent':
            c['status'] = 'new'
        log = c.get('log')
        if not isinstance(log, list):
            log = []
        log.append({'ts': int(datetime.now(timezone.utc).timestamp() * 1000),
                     'msg': '↩ Wave1 ripristinata: invio originale fallito per sender non validato (export@ilciliegio.com)'})
        c['log'] = log
        reset += 1

    print(f'Ripristinati: {reset} / {len(FAILED_IDS)} ({skipped} saltati)')

    if reset:
        ok = gh_put(DATA_PATH, db, sha,
                    f'Fix wave1 fallita per sender invalido — {reset} contatti ripristinati')
        if ok:
            print('✓ clienti.json aggiornato su GitHub')
        else:
            sys.exit(1)
    else:
        print('Nessuna modifica da salvare.')


if __name__ == '__main__':
    main()
