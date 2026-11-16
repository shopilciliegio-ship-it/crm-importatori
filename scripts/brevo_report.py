"""Report sola lettura Brevo: statistiche aggregate dal giorno START (default 2026-11-15) + piano/crediti."""
import os, requests
K = {'api-key': os.environ['BREVO_API_KEY'], 'accept': 'application/json'}
START = os.environ.get('START', '2026-11-15'); END = os.environ.get('END', '2026-11-16')
r = requests.get('https://api.brevo.com/v3/smtp/statistics/aggregatedReport', headers=K, params={'startDate': START, 'endDate': END}, timeout=60)
print('AGGREGATO', START, END, r.status_code, r.text[:600])
r = requests.get('https://api.brevo.com/v3/smtp/statistics/reports', headers=K, params={'days': 4}, timeout=60)
print('PER GIORNO', r.status_code, r.text[:1500])
r = requests.get('https://api.brevo.com/v3/account', headers=K, timeout=60)
try:
    j = r.json(); print('PIANO', j.get('plan'))
except Exception: print('ACCOUNT', r.status_code)
