"""Dettaglio Brevo (SOLA LETTURA) per giorno e provider, campagna Natale. Stampa solo aggregati: nessun indirizzo nei log (repo pubblico)."""
import os, sys, time, collections, requests
K = {'api-key': os.environ['BREVO_API_KEY'], 'accept': 'application/json'}
START = os.environ.get('START', '2026-11-16'); END = os.environ.get('END', '2026-11-23')
TAG = os.environ.get('TAG', 'natale')
EVENTS = ['requests', 'delivered', 'opened', 'clicks', 'softBounces', 'hardBounces', 'unsubscribed', 'spam', 'blocked', 'invalid', 'deferred']
BIG = {'gmail.com', 'googlemail.com', 'icloud.com', 'me.com', 'mac.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'live.com', 'aol.com'}

def fetch(ev):
    out, off = [], 0
    while True:
        for t in range(4):
            r = requests.get('https://api.brevo.com/v3/smtp/statistics/events', headers=K, timeout=90,
                             params={'startDate': START, 'endDate': END, 'event': ev, 'tags': TAG, 'limit': 500, 'offset': off})
            if r.status_code == 200: break
            time.sleep(3 * (t + 1))
        else:
            print('ERRORE', ev, r.status_code, r.text[:200]); return out
        evs = r.json().get('events', [])
        out += evs
        if len(evs) < 500: return out
        off += 500

def prov(e):
    d = (e.get('email') or '').split('@')[-1].lower()
    return d if d in BIG else 'altri'

rows = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))  # giorno -> provider -> evento
uniq = collections.defaultdict(lambda: collections.defaultdict(set))
for ev in EVENTS:
    for e in fetch(ev):
        day = (e.get('date') or '')[:10]; p = prov(e)
        rows[day][p][ev] += 1
        uniq[ev][p].add((e.get('email') or '').lower())
    print('letto', ev, file=sys.stderr)

print('PERIODO', START, END, 'tag', TAG)
cols = ['requests', 'delivered', 'opened', 'clicks', 'softBounces', 'hardBounces', 'unsubscribed', 'spam', 'blocked', 'invalid', 'deferred']
print('GIORNO|PROVIDER|' + '|'.join(cols))
for day in sorted(rows):
    tot = collections.Counter()
    for p in sorted(rows[day]):
        print(day, p, *[rows[day][p][c] for c in cols], sep='|'); tot.update(rows[day][p])
    print(day, 'TOTALE', *[tot[c] for c in cols], sep='|')
print('\nUNICI PER PROVIDER (indirizzi distinti, periodo intero)')
print('PROVIDER|' + '|'.join(cols))
for p in sorted({p for ev in uniq for p in uniq[ev]}):
    print(p, *[len(uniq[c][p]) for c in cols], sep='|')
sent = set().union(*[uniq['requests'][p] for p in uniq['requests']]) if uniq['requests'] else set()
act = set().union(*[uniq['opened'][p] | uniq['clicks'][p] for p in set(uniq['opened']) | set(uniq['clicks'])]) if uniq['opened'] or uniq['clicks'] else set()
print('\nINVIATI UNICI', len(sent), '| ATTIVI (aperto o cliccato)', len(act))
