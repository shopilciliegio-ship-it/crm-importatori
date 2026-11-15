import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import send_importatori_bulk as b
tpl = json.load(open('data/templates.json', encoding='utf-8'))[0]
fake = {'company': 'Esempio Wines Ltd', 'country': 'France', 'city': 'Paris',
        'contacts': [{'name': 'Jean Dupont', 'email': 'jean@example.com', 'title': 'Owner'}],
        'contactEmail': 'jean@example.com', 'email': 'info@example.com'}
body = b.fill_tpl_for_contact(tpl['body'], fake)
for brand in ('sienawine', 'ciliegio'):
    b = b
    bb = b.BRANDS[brand]
    payload = {'sender': {'name': bb['senderName'], 'email': bb['senderEmail']},
               'to': [{'email': 'luca@ilciliegio.com', 'name': 'Luca'}],
               'subject': f'[PROVA {brand}] ' + tpl['subject'],
               'htmlContent': b.build_html_email(body, brand), 'textContent': body,
               'tags': ['prova-importatori']}
    r = b.requests.post('https://api.brevo.com/v3/smtp/email', headers=b._BREVO_HEADERS, json=payload)
    print(brand, r.status_code, r.text[:150])
