"""Sola lettura: eventi 'blocked' Brevo raggruppati per dominio e motivo."""
import os, requests, collections
K = {'api-key': os.environ['BREVO_API_KEY'], 'accept': 'application/json'}
START = os.environ.get('START', '2026-11-15'); END = os.environ.get('END', '2026-11-18')
EV = os.environ.get('EVENTO', 'blocked')
tot = []; off = 0
while True:
    r = requests.get('https://api.brevo.com/v3/smtp/statistics/events', headers=K,
        params={'event': EV, 'startDate': START, 'endDate': END, 'limit': 2500, 'offset': off}, timeout=90)
    if r.status_code != 200: print('ERR', r.status_code, r.text[:300]); break
    ev = r.json().get('events', [])
    tot += ev; off += len(ev)
    if len(ev) < 2500: break
print('TOTALE', EV, len(tot))
dom = collections.Counter(e['email'].split('@')[-1].lower() for e in tot)
print('DOMINI', dom.most_common(15))
rs = collections.Counter((e.get('reason') or '?')[:110] for e in tot)
print('MOTIVI'); [print(' ', n, m) for m, n in rs.most_common(10)]
day = collections.Counter(str(e.get('date'))[:10] for e in tot)
print('GIORNI', sorted(day.items()))
