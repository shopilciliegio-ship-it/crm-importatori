"""
Pre-controllo gratuito dei lead BWI (16/11/2026) — NON spende crediti, NON sblocca niente.

Per ogni azienda del pool (sì, poi forse 5★, poi forse 4★) legge la lista lead di BWI (chiamata
gratuita, la stessa che usa lo sblocco) e salva in data/bwi-precheck.json se c'è almeno una persona
con email sbloccabile ("*"), già in chiaro, o nessuna email. Così si sa PRIMA quanti crediti servono.

Ritmo lento e irregolare (pausa casuale tra una chiamata e l'altra + pause lunghe ogni tanto), una
sola sessione, stop al primo segnale di rifiuto (429/403 ripetuti). Salva ogni CHECKPOINT_EVERY
controlli in un file piccolo dedicato (nessun conflitto col database del CRM).

Parametri (variabili d'ambiente, tutte opzionali):
  MAX_MINUTES  durata massima del giro (default 330)
  MIN_DELAY / MAX_DELAY  pausa in secondi tra due chiamate (default 3 / 6)
  FASI  quali fasi controllare: "1,2,3" (1 = sì, 2 = forse 5★, 3 = forse 4★)
  MAX_CHECKS  tetto di aziende controllate in questo giro (default 100000)
  RECHECK_DAYS  dopo quanti giorni ricontrollare un'azienda già controllata (default 30)
  PAESI  elenco opzionale (separato da virgola) per limitarsi a certi paesi
Anche usato dal giro giornaliero della ricerca AI (scripts/research_ai.py) per le aziende nuove.
"""
import base64
import json
import os
import random
import sys
import time
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'BWI'))
from bwi_auto_login import do_login  # noqa: E402

GH_TOKEN = os.environ['GH_TOKEN']
GH_REPO = os.environ['GH_REPO']
BASE_PATH = 'data/contatti.json'
OVERRIDES_PATH = 'data/contatti-overrides.json'
OUT_PATH = 'data/bwi-precheck.json'
LEADS_URL = 'https://api.bestwineimporters.com/api/v1/leads'

MAX_MINUTES = float(os.environ.get('MAX_MINUTES', '330'))
MIN_DELAY = float(os.environ.get('MIN_DELAY', '3'))
MAX_DELAY = float(os.environ.get('MAX_DELAY', '6'))
FASI = {x.strip() for x in os.environ.get('FASI', '1,2,3').split(',') if x.strip()}
MAX_CHECKS = int(os.environ.get('MAX_CHECKS', '100000'))
RECHECK_DAYS = float(os.environ.get('RECHECK_DAYS', '30'))
PAESI = {x.strip() for x in os.environ.get('PAESI', '').split(',') if x.strip()}
CHECKPOINT_EVERY = 25

ESCLUSI = {'Italy', 'United States', 'Canada', 'Sweden', 'Norway', 'Finland'}
_GH = {'Authorization': f'token {GH_TOKEN}', 'Accept': 'application/vnd.github.v3+json'}


def gh_request(method, url, **kw):
    for attempt in range(5):
        r = requests.request(method, url, timeout=60, **kw)
        if r.status_code in (502, 503, 504) and attempt < 4:
            time.sleep(2 ** attempt)
            continue
        if r.status_code in (403, 429) and attempt < 4:
            time.sleep((30, 90, 180, 300)[attempt])
            continue
        return r
    return r


def gh_get(path):
    meta = gh_request('GET', f'https://api.github.com/repos/{GH_REPO}/contents/{path}', headers=_GH)
    if meta.status_code == 404:
        return None, None
    meta.raise_for_status()
    sha = meta.json()['sha']
    # file grandi (>1 MB, come contatti.json / overrides): download come blob
    for _ in range(3):
        b = gh_request('GET', f'https://api.github.com/repos/{GH_REPO}/git/blobs/{sha}', headers=_GH)
        if b.ok:
            return json.loads(base64.b64decode(b.json()['content']).decode('utf-8')), sha
        time.sleep(3)
    raise RuntimeError(f'download di {path} non riuscito')


def gh_put(path, data, sha, message):
    body = {'message': message,
            'content': base64.b64encode(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).decode('ascii')}
    if sha:
        body['sha'] = sha
    r = gh_request('PUT', f'https://api.github.com/repos/{GH_REPO}/contents/{path}', headers=_GH, json=body)
    return r


def salva(out, sha, messaggio):
    """Salva il file; su conflitto di sha riscarica, unisce (vince il piu' recente) e riprova."""
    for _ in range(4):
        r = gh_put(OUT_PATH, out, sha, messaggio)
        if r.ok:
            return r.json()['content']['sha']
        if r.status_code in (409, 422):
            remoto, sha = gh_get(OUT_PATH)
            if remoto:
                for k, v in (remoto.get('checked') or {}).items():
                    if k not in out['checked'] or (v[3] or 0) > (out['checked'][k][3] or 0):
                        out['checked'][k] = v
            continue
        r.raise_for_status()
    raise RuntimeError('salvataggio bwi-precheck.json non riuscito')


def lead_list(sess_headers, comp_id):
    """Ritorna (leads, http_status). leads = None se la chiamata non e' andata a buon fine."""
    r = requests.post(LEADS_URL, json={'compID': comp_id}, headers=sess_headers, timeout=20)
    if not r.ok:
        return None, r.status_code
    data = r.json()
    if isinstance(data, dict):
        data = data.get('leads', data.get('resListLeads', []))
    return (data if isinstance(data, list) else []), r.status_code


def classifica(leads):
    """('s'|'g'|'n', persone_bloccate, persone_totali)
    s = almeno una persona con email bloccata ("*", sbloccabile), g = email gia' in chiaro, n = nessuna email."""
    emails = [(l.get('Email') or '').strip() for l in leads]
    gia = [e for e in emails if '@' in e]
    blocc = [e for e in emails if e == '*']
    if gia:
        return 'g', len(blocc), len(leads)
    if blocc:
        return 's', len(blocc), len(leads)
    return 'n', 0, len(leads)


def fase_di(c):
    r = c.get('research') or {}
    rec = r.get('raccomandato')
    try:
        st = int(r.get('affidabilita'))
    except (TypeError, ValueError):
        st = 0
    if rec == 'si':
        return '1'
    if rec == 'forse' and st == 5:
        return '2'
    if rec == 'forse' and st == 4:
        return '3'
    return None


def candidati(contacts, checked, now_ms):
    pool = []
    for c in contacts:
        f = fase_di(c)
        if not f or f not in FASI:
            continue
        if (c.get('country') or '') in ESCLUSI:
            continue
        if PAESI and (c.get('country') or '') not in PAESI:
            continue
        if not c.get('bwiCompId'):
            continue
        if c.get('status') in ('sent', 'followup', 'replied', 'cold') or c.get('brevoEvents'):
            continue
        if c.get('contactEmail') or any(p.get('sbloccato') for p in (c.get('contacts') or [])):
            continue                                    # persona gia' sbloccata: niente da controllare
        prev = checked.get(c['id'])
        if prev and (now_ms - (prev[3] or 0)) < RECHECK_DAYS * 86400000:
            continue
        pool.append((f, c))
    # per fase; dentro la fase i paesi piu' grandi prima, Germania in fondo; dentro il paese ordine casuale
    size = {}
    for f, c in pool:
        size[(f, c.get('country'))] = size.get((f, c.get('country')), 0) + 1
    random.shuffle(pool)
    pool.sort(key=lambda fc: (fc[0], (fc[1].get('country') == 'Germany'), -size[(fc[0], fc[1].get('country'))], fc[1].get('country') or ''))
    return pool


def main():
    t0 = time.time()
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    base, _ = gh_get(BASE_PATH)
    contacts = base.get('contacts', []) if isinstance(base, dict) else base
    ov, _ = gh_get(OVERRIDES_PATH)
    by_id = {c['id']: c for c in contacts}
    for cid, ch in (ov or {}).items():
        if cid in by_id:
            by_id[cid].update(ch)
    out, sha = gh_get(OUT_PATH)
    if not out:
        out = {'checked': {}, 'meta': {}}
    out.setdefault('checked', {})

    pool = candidati(list(by_id.values()), out['checked'], now_ms)
    print(f'Aziende da controllare: {len(pool)} (fasi {sorted(FASI)}), ritmo {MIN_DELAY}-{MAX_DELAY} s, max {MAX_MINUTES:.0f} min')
    if not pool:
        return
    _, headers = do_login()
    relogin = 0
    errori_consecutivi = 0
    rifiuti = 0
    fatti = 0
    stat = {'s': 0, 'g': 0, 'n': 0}
    dal_checkpoint = 0
    motivo = 'finite le aziende'
    for f, c in pool:
        if (time.time() - t0) / 60 >= MAX_MINUTES:
            motivo = 'tempo massimo del giro raggiunto'
            break
        if fatti >= MAX_CHECKS:
            motivo = 'tetto di controlli raggiunto'
            break
        leads, code = lead_list(headers, int(c['bwiCompId']))
        if leads is None:
            if code in (401, 403) and relogin < 3:
                relogin += 1
                print(f'  sessione scaduta ({code}): rifaccio il login ({relogin}/3)')
                time.sleep(20)
                _, headers = do_login()
                continue
            if code == 429 or code in (401, 403):
                rifiuti += 1
                if rifiuti >= 2:
                    motivo = f'BWI ha rifiutato piu\' volte (HTTP {code}): mi fermo'
                    break
                print(f'  HTTP {code}: pausa di 10 minuti')
                time.sleep(600)
                continue
            errori_consecutivi += 1
            print(f'  {c.get("company", "?")}: HTTP {code}')
            if errori_consecutivi >= 6:
                motivo = f'6 errori di fila (ultimo HTTP {code}): mi fermo'
                break
            time.sleep(15)
            continue
        errori_consecutivi = 0
        s, nb, nt = classifica(leads)
        out['checked'][c['id']] = [s, nb, nt, int(time.time() * 1000)]
        stat[s] += 1
        fatti += 1
        dal_checkpoint += 1
        if fatti % 50 == 0:
            print(f'  {fatti} controllate — sbloccabili {stat["s"]}, gia in chiaro {stat["g"]}, nessuna email {stat["n"]} — {(time.time() - t0) / 60:.0f} min')
        if dal_checkpoint >= CHECKPOINT_EVERY:
            out['meta'] = {'aggiornato': datetime.now(timezone.utc).isoformat(), 'controllate': len(out['checked'])}
            sha = salva(out, sha, f'Pre-controllo BWI — {len(out["checked"])} aziende controllate')
            dal_checkpoint = 0
        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
        if fatti % 40 == 0:
            time.sleep(random.uniform(20, 60))               # ogni tanto una pausa piu' lunga
    out['meta'] = {'aggiornato': datetime.now(timezone.utc).isoformat(), 'controllate': len(out['checked'])}
    salva(out, sha, f'Pre-controllo BWI — {len(out["checked"])} aziende controllate (fine giro)')
    riepilogo = (f'Giro finito ({motivo}): {fatti} aziende controllate — sbloccabili {stat["s"]}, '
                 f'gia\' in chiaro {stat["g"]}, nessuna email {stat["n"]} — {(time.time() - t0) / 60:.0f} min')
    print(riepilogo)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as fh:
            fh.write('### Pre-controllo BWI\n' + riepilogo + '\n')


if __name__ == '__main__':
    main()
