"""
Sblocco email contatti BWI (bulk) — LATO SERVER
Siena Wine / Small Vineyards International

Endpoint BWI scoperto il 22/9/2026 ispezionando il Network tab del browser mentre Luca
sbloccava a mano un contatto (Joe Alessi, Alessi Beverages): POST unlockLead/ con
{compID, leadID, leadType}, 1 credito BWI per sblocco (Luca ne ha ~12.000 al 23/9/2026).

Flusso:
  1. Il browser (js/unlock.js) scrive data/unlock-leads-job.json con
     {raccomandato, stelle:[...], maxCredits, status:'pending'} e lancia questo workflow via
     workflow_dispatch — l'anteprima (quanti contatti, quanti crediti) è già stata calcolata dal
     browser PRIMA di lanciare, maxCredits è il tetto scelto da Luca nel popup
     (default = tutti i candidati trovati dall'anteprima).
  2. Questo script: filtra i contatti che matchano raccomandato+stelle, hanno almeno una persona
     in scheda (contacts[]) ma NESSUNA con email nota (mai sbloccata prima — non rispende crediti
     per chi ce l'ha già), sceglie per ciascuno il lead con priorità di ruolo più alta (stessa
     logica di select_best_contact in send_importatori_bulk.py), fa login su BWI e chiama
     unlockLead/ uno alla volta, fermandosi se raggiunge maxCredits o se i crediti BWI finiscono
     (risposta 402/403 o messaggio esplicito).
  3. Salva l'email sbloccata in contactEmail/contactName del contatto (stessi campi letti da
     select_send_email() — il prossimo invio la userà in automatico) + un log. Salvataggio
     progressivo ogni CHECKPOINT_EVERY sblocchi, non solo a fine batch.
  4. Manda un resoconto finale via email (stesso schema degli altri digest del CRM).
"""

import base64
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'BWI'))
from bwi_auto_login import do_login  # noqa: E402

# ── Config ────────────────────────────────────────────────────────────────────
BREVO_API_KEY = os.environ['BREVO_API_KEY']
GH_TOKEN      = os.environ['GH_TOKEN']
GH_REPO       = os.environ['GH_REPO']

BASE_PATH      = 'data/contatti.json'
OVERRIDES_PATH = 'data/contatti-overrides.json'
JOB_PATH       = 'data/unlock-leads-job.json'

DIGEST_RECIPIENT = 'luca@ilciliegio.com'
SENDER_NAME  = 'Il Ciliegio — Azienda Agricola'
SENDER_EMAIL = 'luca@sienawine.it'
ACCENT, BG   = '#B8941A', '#2c2c2c'

CHECKPOINT_EVERY = 20  # sblocchi tra un salvataggio incrementale e l'altro

UNLOCK_URL = 'https://api.bestwineimporters.com/api/v1/unlockLead/'
LEADS_URL  = 'https://api.bestwineimporters.com/api/v1/leads'

_GH_HEADERS = {
    'Authorization': f'token {GH_TOKEN}',
    'Accept':        'application/vnd.github.v3+json',
}
_BREVO_HEADERS = {
    'api-key':      BREVO_API_KEY,
    'Content-Type': 'application/json',
    'Accept':       'application/json',
}

# Stessa identica priorità di ruolo di select_best_contact/select_send_email in
# send_importatori_bulk.py — sceglie CHI sbloccare quando un'azienda ha più persone in scheda.
JOB_PRIORITY = {
    1: ['sales manager', 'buyer', 'purchasing manager', 'managing partner', 'sales representative', 'sales director', 'commercial director', 'sales', 'commercial', 'commercial manager', 'wine buyer', 'senior buyer', 'purchasing', 'import manager', 'sales consultant', 'regional sales manager', 'product manager', 'area sales manager', 'marketing manager', 'purchasing director', 'wine manager', 'purchaser', 'national sales manager', 'head of sales', 'buying manager', 'wine sales specialist', 'director of sales', 'wine sales', 'purchase manager', 'buying director', 'general sales manager', 'wine importer'],
    2: ['managing director', 'manager', 'director', 'general manager', 'administrator', 'in charge', 'operations manager', 'wine merchant', 'representative', 'chief executive officer', 'account manager', 'executive director', 'business owner', 'co-founder', 'representative director', 'general director', 'director of operations', 'president & ceo', 'wine director', 'sales specialist', 'wine sales representative', 'procurement manager', 'logistics manager', 'owner/ manager', 'co-owner', 'operation manager', 'senior brand manager', 'chief operating officer', 'regional manager', 'sales assistant', 'sales agent', 'ceo & founder', 'junior buyer', 'portfolio manager', 'area manager', 'senior sales manager', 'founder and ceo', 'business manager', 'managing director/ owner'],
    3: ['owner', 'ceo', 'president', 'founder', 'co-owner', 'sommelier', 'partner', 'co-founder', 'wine consultant', 'brand manager', 'store manager', 'business development manager', 'category manager', 'key account manager', 'wine specialist', 'vice president', 'sales associate', 'president and ceo', 'sales executive', 'administrative', 'administrative manager', 'brand ambassador', 'administrative assistant'],
}


# Log scritto quando BWI scala il credito ma non ha l'email della persona (visto il 23/9/2026: 14 su 34,
# Email "" anche dopo lo sblocco pagato). Serve anche come marcatore: quell'azienda non si ritenta più.
LOG_SENZA_EMAIL = '🔓 Sblocco BWI senza email'

# Provider generici: un'email personale su questi domini non è "sospetta" anche se l'azienda ha un
# dominio suo (piccoli importatori usano spesso gmail & co.).
FREE_MAIL = {'gmail.com', 'googlemail.com', 'hotmail.com', 'outlook.com', 'live.com', 'yahoo.com',
             'icloud.com', 'me.com', 'aol.com', 'msn.com', 'gmx.com', 'gmx.de', 'web.de', 'libero.it',
             'yandex.ru', 'mail.ru', 'qq.com', '163.com', 'bigpond.com', 'hotmail.it', 'yahoo.it'}


def _norm_name(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
    return ' '.join(s.replace('.', ' ').split())


def _same_person(crm_name, bwi_name):
    """BWI tronca il nome alle prime 2 parole ("Elvis Enrique" per "Elvis Enrique Medina"):
    stessa persona se i nomi coincidono o se quello CRM inizia con quello BWI."""
    a, b = _norm_name(crm_name), _norm_name(bwi_name)
    return bool(a and b) and (a == b or a.startswith(b + ' ') or b.startswith(a + ' '))


def _domain(s):
    s = (s or '').strip().lower()
    if '@' in s:
        s = s.rsplit('@', 1)[1]
    s = s.split('://')[-1].split('/')[0].split(':')[0]
    return s[4:] if s.startswith('www.') else s


def _email_sospetta(c, email):
    """True se l'email sbloccata è su un dominio che non c'entra con l'azienda (es. Ken John di
    P. & T. Basile -> kenjohnson@ea.com, cioè Electronic Arts): dato sbagliato di BWI."""
    d = _domain(email)
    if not d or d in FREE_MAIL:
        return False
    company = {_domain(c.get('email')), _domain(c.get('website'))} - {''}
    if not company:
        return False
    return not any(d == k or d.endswith('.' + k) or k.endswith('.' + d) for k in company)


def _priority_score(title: str) -> int:
    if not title:
        return 99
    t = title.lower()
    for p, titles in JOB_PRIORITY.items():
        if any(pt in t or t in pt for pt in titles):
            return p
    return 98


# ── GitHub Contents API ─────────────────────────────────────────────────────────

def _gh_request(method, url, **kwargs):
    for attempt in range(3):
        r = requests.request(method, url, **kwargs)
        if r.status_code in (502, 503, 504) and attempt < 2:
            time.sleep(2 ** attempt)
            continue
        return r


def gh_get(path):
    url = f'https://api.github.com/repos/{GH_REPO}/contents/{path}'
    r = _gh_request('GET', url, headers=_GH_HEADERS)
    if r.status_code == 404:
        return {}, None
    r.raise_for_status()
    data = r.json()
    sha  = data['sha']
    raw  = data.get('content') or ''
    if not raw and data.get('download_url'):
        rr = _gh_request('GET', data['download_url'])
        rr.raise_for_status()
        return rr.json(), sha
    if not raw:
        return {}, sha
    return json.loads(base64.b64decode(raw).decode('utf-8')), sha


def gh_put(path, data, sha, message):
    url = f'https://api.github.com/repos/{GH_REPO}/contents/{path}'
    content = base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')).decode('utf-8')
    body = {'message': message, 'content': content}
    if sha:
        body['sha'] = sha
    r = _gh_request('PUT', url, headers=_GH_HEADERS, json=body)
    r.raise_for_status()
    return r.json()['content']['sha']


def save_job(job):
    _, sha = gh_get(JOB_PATH)
    gh_put(JOB_PATH, job, sha, f'Sblocco email BWI — job {job.get("status")}')


# ── BWI API ──────────────────────────────────────────────────────────────────

def get_leads(headers, comp_id):
    r = requests.post(LEADS_URL, json={'compID': comp_id}, headers=headers, timeout=15)
    if not r.ok:
        return []
    data = r.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get('leads', data.get('resListLeads', []))
    return []


def unlock_lead(headers, comp_id, lead_id, lead_type):
    r = requests.post(UNLOCK_URL, json={'compID': comp_id, 'leadID': lead_id, 'leadType': lead_type},
                       headers=headers, timeout=15)
    return r


# ── Selezione contatti target ────────────────────────────────────────────────

def target_contacts(contacts, raccomandato, stelle_set):
    """Aziende che matchano raccomandato+stelle, hanno almeno una persona in scheda, e NESSUNA
    con email già nota (mai sbloccata prima — non rispende crediti inutilmente)."""
    out = []
    for c in contacts:
        research = c.get('research') or {}
        if research.get('raccomandato') != raccomandato:
            continue
        if research.get('affidabilita') not in stelle_set:
            continue
        people = c.get('contacts') or []
        if not people:
            continue
        if any((p.get('email') or '').strip() or (p.get('emailSospetta') or '').strip() for p in people):
            continue  # già sbloccato in passato, salta
        if any(LOG_SENZA_EMAIL in (l.get('msg') or '') for l in (c.get('log') or [])):
            continue  # già pagato una volta e BWI non ha l'email: non rispendere
        out.append(c)
    # Più stelle prima: con un tetto di crediti (maxCredits) si sbloccano le aziende migliori.
    out.sort(key=lambda c: -((c.get('research') or {}).get('affidabilita') or 0))
    return out


def best_person(people):
    scored = sorted(people, key=lambda p: _priority_score(p.get('title')))
    return scored[0] if scored else None


# ── Digest finale ────────────────────────────────────────────────────────────

def send_digest(job, unlocked, failed, skipped, credits_left_hint):
    now_str = datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')
    subject = f'🔓 Sblocco email BWI — {unlocked} sbloccate ({now_str})'
    rows = [
        ('Categoria', f'{job.get("raccomandato","?")} · {"/".join(str(s) for s in job.get("stelle",[]))} stelle'),
        ('Email ottenute', str(unlocked)),
        ('Crediti BWI spesi', str((job.get('result') or {}).get('spent', '?'))),
        ('Pagate senza email / errori', str(failed)),
        ('Saltate (nessuna email su BWI, 0 crediti)', str(skipped)),
    ]
    if credits_left_hint is not None:
        rows.append(('Crediti BWI residui (stima)', str(credits_left_hint)))
    rows_html = ''.join(
        f'<tr><td style="padding:6px 0;color:#999;font-size:13px">{k}</td>'
        f'<td style="padding:6px 0;text-align:right;font-weight:700;color:#222;font-size:14px">{v}</td></tr>'
        for k, v in rows
    )
    html_content = f"""<!DOCTYPE html><html lang="it"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f4f0;font-family:Georgia,'Times New Roman',serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f0;padding:32px 16px"><tr><td align="center">
<table width="500" cellpadding="0" cellspacing="0" style="max-width:500px;width:100%">
<tr><td style="background:{BG};border-radius:12px 12px 0 0;padding:20px 32px"><h2 style="color:#FFF3DC;margin:0;font-size:18px">🔓 Sblocco email BWI</h2></td></tr>
<tr><td style="background:{ACCENT};height:4px;font-size:0">&nbsp;</td></tr>
<tr><td style="background:#fff;padding:24px 32px"><table width="100%" cellpadding="0" cellspacing="0">{rows_html}</table></td></tr>
<tr><td style="background:{ACCENT};height:3px;font-size:0">&nbsp;</td></tr>
<tr><td style="background:{BG};border-radius:0 0 12px 12px;padding:14px 32px;text-align:center"><p style="margin:0;color:#999;font-size:11px">Il Ciliegio CRM — sblocco automatico</p></td></tr>
</table></td></tr></table></body></html>"""
    payload = {
        'sender': {'name': SENDER_NAME, 'email': SENDER_EMAIL},
        'to': [{'email': DIGEST_RECIPIENT, 'name': 'Luca'}],
        'subject': subject, 'htmlContent': html_content,
        'textContent': '\n'.join(f'{k}: {v}' for k, v in rows),
        'tags': ['wine-crm', 'unlock-bwi'], 'trackClicks': False, 'trackOpens': False,
    }
    r = requests.post('https://api.brevo.com/v3/smtp/email', headers=_BREVO_HEADERS, json=payload, timeout=20)
    print(f'{"✓" if r.ok else "⚠"} Resoconto inviato' if r.ok else f'⚠ Resoconto fallito: {r.status_code}')


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    job, job_sha = gh_get(JOB_PATH)
    if not job or job.get('status') != 'pending':
        print(f'✗ Nessun job "pending" trovato in {JOB_PATH}. Esco.')
        return

    raccomandato = job.get('raccomandato')
    stelle_set   = set(job.get('stelle') or [])
    max_credits  = int(job.get('maxCredits') or 0)
    if not raccomandato or not stelle_set or max_credits <= 0:
        print(f'✗ Job non valido: {job}')
        return

    job['status'] = 'running'
    job['startedAt'] = datetime.now(timezone.utc).isoformat()
    save_job(job)

    base_raw, _ = gh_get(BASE_PATH)
    contacts = base_raw.get('contacts', []) if isinstance(base_raw, dict) else base_raw
    overrides, _ov_sha_ignore = gh_get(OVERRIDES_PATH)
    if not isinstance(overrides, dict):
        overrides = {}
    by_id = {c['id']: c for c in contacts}
    for cid, changes in overrides.items():
        if cid in by_id:
            by_id[cid].update(changes)

    base_snap = {c['id']: {
        'status': c.get('status') or '', 'log': json.dumps(c.get('log') or [], ensure_ascii=False),
        'contactEmail': c.get('contactEmail') or '', 'contactName': c.get('contactName') or '',
        'contactTitle': c.get('contactTitle') or '',
        'contacts': json.dumps(c.get('contacts') or [], ensure_ascii=False),
    } for c in contacts}

    targets = target_contacts(list(by_id.values()), raccomandato, stelle_set)
    print(f'🎯 {len(targets)} aziende target ("{raccomandato}", stelle {sorted(stelle_set)}), '
          f'budget {max_credits} crediti.')

    print('🔑 Login BWI...')
    _, headers = do_login()
    print('✅ Login OK\n')

    unlocked = failed = skipped = spent = 0
    since_checkpoint = 0
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    stop_reason = None

    for c in targets:
        if spent >= max_credits:  # tetto sui crediti SPESI, non sulle email ottenute (23/9: tetto 20, spesi 34)
            stop_reason = f'budget di {max_credits} crediti raggiunto'
            break

        comp_id = c.get('bwiCompId')
        if not comp_id:
            skipped += 1
            continue

        leads = get_leads(headers, int(comp_id))
        if not leads:
            skipped += 1
            continue
        # Campo Email nella lista lead (gratuita), scoperto il 23/9/2026 dopo 14 crediti spesi a vuoto:
        #   "*"         = email presente ma bloccata -> sbloccabile (1 credito)
        #   ""          = BWI non ha l'email ("No Email/Phone" sul portale): sbloccare costa 1 credito
        #                 e non restituisce nulla -> MAI sbloccare
        #   "x@dominio" = già sbloccata (es. a mano dal portale) -> la prendiamo gratis
        gia_note  = [l for l in leads if '@' in (l.get('Email') or '')]
        bloccate  = [l for l in leads if (l.get('Email') or '').strip() == '*']
        gratis = bool(gia_note)
        target_lead = best_person(gia_note or bloccate)
        if not target_lead or not target_lead.get('LeadId'):
            # Nessuna persona con email su BWI: lo segniamo (gratis) così l'azienda esce dai candidati.
            c.setdefault('log', []).append({
                'ts': now_ms,
                'msg': f'{LOG_SENZA_EMAIL}: nessuna persona con email su BWI (verificato senza spendere crediti)',
            })
            print(f'  ∅ {c.get("company","?")}: nessuna persona con email su BWI — saltata, 0 crediti')
            skipped += 1
            since_checkpoint += 1
            continue

        if gratis:
            result = {'leadEmail': target_lead['Email'].strip()}  # già in chiaro: nessuno sblocco, 0 crediti
        else:
            try:
                r = unlock_lead(headers, int(comp_id), target_lead['LeadId'], target_lead.get('LeadType', 'manu'))
            except Exception as e:
                print(f'  ⚠ {c.get("company","?")}: errore rete — {e}')
                failed += 1
                continue
            if r.status_code in (402, 403):
                stop_reason = f'BWI ha rifiutato lo sblocco (HTTP {r.status_code}) — probabile fine crediti'
                print(f'  ❌ {stop_reason}')
                break
            if not r.ok:
                print(f'  ⚠ {c.get("company","?")}: HTTP {r.status_code}')
                failed += 1
                continue
            spent += 1  # BWI scala il credito anche se poi non restituisce l'email
            result = r.json()
        email = (result.get('leadEmail') or '').strip()
        if not email:
            # BWI scala comunque il credito: lo segniamo nella scheda così non si ritenta più.
            print(f'  ∅ {c.get("company","?")}: BWI non ha l\'email di {target_lead.get("FullName","")} '
                  f'(credito speso) — risposta: {json.dumps(result, ensure_ascii=False)[:200]}')
            c.setdefault('log', []).append({
                'ts': now_ms,
                'msg': f'{LOG_SENZA_EMAIL}: BWI non ha l\'email di {target_lead.get("FullName","")} '
                       f'({target_lead.get("Position","")}) — credito speso, non si ritenta',
            })
            failed += 1
            since_checkpoint += 1
            continue

        # La persona sbloccata va nella scheda (contacts[]) con email e flag "sbloccato": da lì la
        # scelgono come destinatario, a prescindere dal ruolo, invio massivo, follow-up, CRM e saluto
        # "Dear ..." (sort in select_best_contact/select_send_email/selectBestContact).
        full_name = (target_lead.get('FullName') or '').strip()
        position  = (target_lead.get('Position') or '').strip()
        people = [dict(p) for p in (c.get('contacts') or [])]
        same = next((p for p in people if _same_person(p.get('name'), full_name)), None)
        if not same:
            same = {'name': full_name, 'title': position}
            people.append(same)
        elif position and not same.get('title'):
            same['title'] = position
        name_crm = same.get('name') or full_name  # il nome completo del CRM vince su quello troncato di BWI
        if _email_sospetta(c, email):
            # Dominio che non c'entra con l'azienda: la teniamo in scheda ma NON la usiamo per gli invii.
            same['emailSospetta'] = email
            c['contacts'] = people
            c.setdefault('log', []).append({
                'ts': now_ms,
                'msg': f'⚠ Email sbloccata via BWI con dominio diverso dall\'azienda: {name_crm} <{email}> '
                       f'— da verificare, NON usata per gli invii',
            })
            print(f'  ⚠ {c.get("company","?")}: {name_crm} <{email}> — dominio sospetto, non usata')
            unlocked += 1
            since_checkpoint += 1
            continue
        same['email'] = email
        same['sbloccato'] = True
        c['contacts']     = people
        c['contactEmail'] = email
        c['contactName']  = name_crm
        c['contactTitle'] = same.get('title') or position
        c.setdefault('log', []).append({
            'ts': now_ms,
            'msg': f'🔓 Email sbloccata via BWI: {name_crm} <{email}> ({target_lead.get("Position","")})',
        })
        unlocked += 1
        since_checkpoint += 1
        print(f'  ✅ {c.get("company","?")}: {name_crm} <{email}>')
        time.sleep(0.3)

        if since_checkpoint >= CHECKPOINT_EVERY:
            new_ov = {}
            for cc in by_id.values():
                snap = base_snap.get(cc['id'])
                if not snap:
                    continue
                diff = {}
                if (cc.get('contactEmail') or '') != snap['contactEmail']:
                    diff['contactEmail'] = cc.get('contactEmail') or ''
                if (cc.get('contactName') or '') != snap['contactName']:
                    diff['contactName'] = cc.get('contactName') or ''
                if json.dumps(cc.get('log') or [], ensure_ascii=False) != snap['log']:
                    diff['log'] = cc.get('log') or []
                if json.dumps(cc.get('contacts') or [], ensure_ascii=False) != snap['contacts']:
                    diff['contacts'] = cc.get('contacts') or []
                if (cc.get('contactTitle') or '') != snap['contactTitle']:
                    diff['contactTitle'] = cc.get('contactTitle') or ''
                if diff:
                    new_ov.setdefault(cc['id'], {}).update(diff)
            merged = {**overrides, **{k: {**overrides.get(k, {}), **v} for k, v in new_ov.items()}}
            fresh_sha = get_ov_sha()
            gh_put(OVERRIDES_PATH, merged, fresh_sha, f'Sblocco email BWI — checkpoint ({unlocked} sbloccate)')
            overrides = merged
            since_checkpoint = 0
            print(f'    💾 Checkpoint salvato ({unlocked} sbloccate finora)')

    # Salvataggio finale
    new_ov = {}
    for cc in by_id.values():
        snap = base_snap.get(cc['id'])
        if not snap:
            continue
        diff = {}
        if (cc.get('contactEmail') or '') != snap['contactEmail']:
            diff['contactEmail'] = cc.get('contactEmail') or ''
        if (cc.get('contactName') or '') != snap['contactName']:
            diff['contactName'] = cc.get('contactName') or ''
        if json.dumps(cc.get('log') or [], ensure_ascii=False) != snap['log']:
            diff['log'] = cc.get('log') or []
        if json.dumps(cc.get('contacts') or [], ensure_ascii=False) != snap['contacts']:
            diff['contacts'] = cc.get('contacts') or []
        if (cc.get('contactTitle') or '') != snap['contactTitle']:
            diff['contactTitle'] = cc.get('contactTitle') or ''
        if diff:
            new_ov.setdefault(cc['id'], {}).update(diff)
    merged = {**overrides, **{k: {**overrides.get(k, {}), **v} for k, v in new_ov.items()}}
    fresh_sha = get_ov_sha()
    gh_put(OVERRIDES_PATH, merged, fresh_sha, f'Sblocco email BWI — completato ({unlocked} sbloccate)')

    job['status']   = 'done'
    job['finishedAt'] = datetime.now(timezone.utc).isoformat()
    job['result']   = {'unlocked': unlocked, 'spent': spent, 'failed': failed, 'skipped': skipped, 'stopReason': stop_reason}
    save_job(job)

    print(f'\n✅ Fatto. Email ottenute {unlocked}, crediti spesi {spent}, fallite {failed}, saltate {skipped}.'
          + (f' Fermato: {stop_reason}' if stop_reason else ''))

    send_digest(job, unlocked, failed, skipped, None)


def get_ov_sha():
    return _gh_request('GET', f'https://api.github.com/repos/{GH_REPO}/contents/{OVERRIDES_PATH}',
                        headers=_GH_HEADERS).json().get('sha')


if __name__ == '__main__':
    main()
