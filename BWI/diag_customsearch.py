"""Diagnostica SOLA LETTURA (0 crediti): cosa restituisce oggi customSearch di BWI ordinato per Created/Updated,
e quante di quelle aziende sono gia' nel CRM (confronto per bwiCompId). Serve a capire perche' il sync settimanale
non importa piu' aziende nuove dal 12/10/2026 mentre BWI ne mostra ~196 a settimana."""
import json, os, sys
from bwi_auto_login import do_login

BASE_URL = "https://api.bestwineimporters.com/api/v1"
FILTRI = {"FilterKeyword": [], "FilterCategories": [], "FilterSubCategories": [], "FilterTypes": [],
          "FilterOrigin": [], "FilterCountry": [], "FilterContinent": [], "FilterEmployee": [], "FilterSales": []}

def main():
    sess, headers = do_login()
    crm = json.load(open(os.path.join(os.path.dirname(__file__), '..', 'data', 'contatti.json'), encoding='utf-8'))['contacts']
    crm_ids = {str(c.get('bwiCompId')) for c in crm if c.get('bwiCompId')}
    print(f'CRM: {len(crm)} aziende, {len(crm_ids)} con bwiCompId')
    # prova varianti del campo "filters" (il formato vecchio ora da 400 "Invalid search filters")
    for nome, filt in (('filters={}', {}), ('filters=assente', None), ('filters=liste vuote + keyword stringa', {**FILTRI, 'FilterKeyword': ''})):
        pl = {"nocache": True, "startAt": 0, "endAt": 5, "sortBy": "Created", "sortDir": "DESC", "id": None, "name": None, "date": None}
        if filt is not None:
            pl["filters"] = filt
        r = sess.post(f"{BASE_URL}/customSearch/", json=pl, headers=headers, timeout=60)
        print(f'VARIANTE {nome}: HTTP {r.status_code} | {r.text[:160]!r}')
    for sort in ('Created', 'Updated'):
        print(f'\n===== customSearch sortBy={sort} DESC =====')
        payload = {"nocache": True, "startAt": 0, "endAt": 50, "sortBy": sort, "sortDir": "DESC",
                   "filters": {}, "id": None, "name": None, "date": None}
        r = sess.post(f"{BASE_URL}/customSearch/", json=payload, headers=headers, timeout=60)
        print('HTTP', r.status_code, '| bytes', len(r.content))
        if r.status_code != 200:
            print('CORPO RISPOSTA:', r.text[:400])
        try:
            data = r.json()
        except Exception as e:
            print('JSON non valido:', e, r.text[:300]); continue
        print('chiavi risposta:', list(data.keys()) if isinstance(data, dict) else type(data))
        print('countComp:', json.dumps(data.get('countComp'))[:200] if isinstance(data, dict) else '')
        comps = data.get('resListComp') or []
        print('aziende nel blocco:', len(comps))
        if comps:
            print('chiavi azienda:', sorted(comps[0].keys()))
        mancanti = 0
        for i, c in enumerate(comps):
            cid = str(c.get('CompId'))
            nel_crm = cid in crm_ids
            mancanti += (not nel_crm)
            if i < 8:
                print(f"  {cid} | {c.get('CompanyName')} | {c.get('Country')} | Created={c.get('Created')} | Updated={c.get('Updated')} | nel CRM: {nel_crm}")
        print(f'-> su {len(comps)} aziende (le prime per {sort}), NON presenti nel CRM: {mancanti}')

if __name__ == '__main__':
    main()
