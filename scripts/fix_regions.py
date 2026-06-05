# -*- coding: utf-8 -*-
"""
fix_regions.py
Corregge il campo region in contatti.json usando la stessa mappa COUNTRY_REGION del JS.
"""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

COUNTRY_REGION = {
    'Argentina':'Sud America','Bolivia':'Sud America','Brazil':'Sud America','Brasil':'Sud America',
    'Chile':'Sud America','Colombia':'Sud America','Ecuador':'Sud America','El Salvador':'Sud America',
    'Guatemala':'Sud America','Honduras':'Sud America','Mexico':'Sud America','Messico':'Sud America',
    'Nicaragua':'Sud America','Panama':'Sud America','Paraguay':'Sud America','Peru':'Sud America',
    'Suriname':'Sud America','Uruguay':'Sud America','Venezuela':'Sud America','Costa Rica':'Sud America',
    'Dominican Republic':'Sud America','Cuba':'Sud America','Haiti':'Sud America','Jamaica':'Sud America',
    'Trinidad and Tobago':'Sud America','Trinidad And Tobago':'Sud America','Belize':'Sud America',
    'Guyana':'Sud America','French Guiana':'Sud America','Martinique':'Sud America',
    'Guadeloupe':'Sud America','Distrito Nacional':'Sud America',
    'United States':'Nord America','USA':'Nord America','Canada':'Nord America',
    'Cayman Islands':'Caraibi','Barbados':'Caraibi','Bermuda':'Caraibi','Bahamas':'Caraibi',
    'Puerto Rico':'Caraibi','Aruba':'Caraibi','Curacao':'Caraibi','Curacao':'Caraibi',
    'Saint Lucia':'Caraibi','Grenada':'Caraibi','Antigua and Barbuda':'Caraibi',
    'Antigua And Barbuda':'Caraibi','Saint Kitts and Nevis':'Caraibi','Dominica':'Caraibi',
    'Virgin Islands':'Caraibi','Turks and Caicos Islands':'Caraibi','Sint Maarten':'Caraibi',
    'Saint Martin':'Caraibi','Santo Domingo':'Caraibi','Tortola':'Caraibi','Gustavia':'Caraibi',
    'Saint-Paul':'Caraibi','Kingstown':'Caraibi','Saint Thomas':'Caraibi',
    'Saint Vincent and the Grenadines':'Caraibi','Anguilla':'Caraibi','Montserrat':'Caraibi',
    'Albania':'Europa','Andorra':'Europa','Austria':'Europa','Belgium':'Europa','Belgio':'Europa',
    'Bosnia and Herzegovina':'Europa','Bosnia And Herzegovina':'Europa',
    'Bosnia (Federacija Bosanska)':'Europa','Republika Srpska':'Europa',
    'Bulgaria':'Europa','Croatia':'Europa','Cyprus':'Europa','Czech Republic':'Europa',
    'Czechia':'Europa','Denmark':'Europa','Estonia':'Europa','Finland':'Europa',
    'France':'Europa','Germany':'Europa','Greece':'Europa','Hungary':'Europa',
    'Iceland':'Europa','Ireland':'Europa','Italy':'Europa','Kosovo':'Europa',
    'Latvia':'Europa','Lithuania':'Europa','Luxembourg':'Europa','Malta':'Europa',
    'Moldova':'Europa','Montenegro':'Europa','Netherlands':'Europa','North Macedonia':'Europa',
    'Norway':'Europa','Poland':'Europa','Portugal':'Europa','Romania':'Europa',
    'Russia':'Europa','Serbia':'Europa','Slovakia':'Europa','Slovenia':'Europa',
    'Spain':'Europa','Sweden':'Europa','Switzerland':'Europa','Ukraine':'Europa',
    'United Kingdom':'Europa','UK':'Europa','GB':'Europa','Belarus':'Europa',
    'Liechtenstein':'Europa','Monaco':'Europa','San Marino':'Europa','Faroe Islands':'Europa',
    'Gibraltar':'Europa','Douglas':'Europa','Isle of Man':'Europa',
    'Australia':'Oceania','New Zealand':'Oceania','Fiji':'Oceania',
    'Papua New Guinea':'Oceania','French Polynesia':'Oceania','New Caledonia':'Oceania',
    'China':'Asia','Japan':'Asia','South Korea':'Asia','Korea':'Asia','India':'Asia',
    'Indonesia':'Asia','Malaysia':'Asia','Philippines':'Asia','Singapore':'Asia',
    'Thailand':'Asia','Vietnam':'Asia','Taiwan':'Asia','Hong Kong':'Asia',
    'Bangladesh':'Asia','Sri Lanka':'Asia','Myanmar':'Asia','Cambodia':'Asia',
    'Nepal':'Asia','Pakistan':'Asia','Kazakhstan':'Asia','Uzbekistan':'Asia',
    'Mongolia':'Asia','Laos':'Asia','Brunei':'Asia','Macao':'Asia','Macau':'Asia',
    'Maldives':'Asia','Bhutan':'Asia','Afghanistan':'Asia','Tajikistan':'Asia',
    'Kyrgyzstan':'Asia','Turkmenistan':'Asia','Azerbaijan':'Asia','Georgia':'Asia','Armenia':'Asia',
    'United Arab Emirates':'Medio Oriente','UAE':'Medio Oriente','Saudi Arabia':'Medio Oriente',
    'Israel':'Medio Oriente','Qatar':'Medio Oriente','Kuwait':'Medio Oriente',
    'Bahrain':'Medio Oriente','Oman':'Medio Oriente','Jordan':'Medio Oriente',
    'Lebanon':'Medio Oriente','Turkey':'Medio Oriente','Iran':'Medio Oriente',
    'Iraq':'Medio Oriente','Syria':'Medio Oriente','Yemen':'Medio Oriente',
    'South Africa':'Africa','Kenya':'Africa','Nigeria':'Africa','Ethiopia':'Africa',
    'Tanzania':'Africa','Uganda':'Africa','Ghana':'Africa','Senegal':'Africa',
    'Morocco':'Africa','Tunisia':'Africa','Algeria':'Africa','Egypt':'Africa',
    'Angola':'Africa','Mozambique':'Africa','Zimbabwe':'Africa','Zambia':'Africa',
    'Botswana':'Africa','Namibia':'Africa','Cameroon':'Africa','Madagascar':'Africa',
    'Mauritius':'Africa','Rwanda':'Africa','Malawi':'Africa','Sudan':'Africa',
}

def region_from_country(country):
    if not country:
        return 'Altro'
    c = country.strip()
    return COUNTRY_REGION.get(c) or COUNTRY_REGION.get(c.title()) or 'Altro'

print("Carico contatti.json...")
with open('data/contatti.json', encoding='utf-8') as f:
    data = json.load(f)

changed = 0
for c in data['contacts']:
    correct = region_from_country(c.get('country',''))
    if c.get('region') != correct:
        c['region'] = correct
        changed += 1

print(f"Contatti aggiornati: {changed} / {len(data['contacts'])}")

from collections import Counter
reg_count = Counter(c.get('region','') for c in data['contacts'])
for r, n in sorted(reg_count.items(), key=lambda x: -x[1]):
    print(f"  {r:<25} {n:>6}")

if changed > 0:
    print("\nSalvo contatti.json...")
    with open('data/contatti.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    print("Salvato.")
else:
    print("Nessuna modifica necessaria.")
