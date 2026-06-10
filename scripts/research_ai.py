"""
Ricerca AI automatica importatori — Il Ciliegio CRM
Eseguito ogni mattina nel workflow import_ordini.yml (server-side, non serve il browser aperto)

Logica (FIFO sulla coda paesi):
  - Legge data/research-config.json: {queue: [paesi flaggati in ordine], dailyLimit}
  - Scorre i paesi in coda in ordine e accumula contatti senza `research` finché non raggiunge `dailyLimit`
    in totale (se un paese si esaurisce prima della quota, prosegue con il successivo)
  - Analizza i contatti raccolti (Google via Serper + sito web + Claude Haiku 4.5)
  - Salva i risultati come override in data/contatti-overrides.json (merge — non tocca status/notes/log esistenti)
  - Se la quota giornaliera non basta per finire un paese, il giorno dopo riprende da dove si era fermato
    (i contatti già analizzati hanno `research` negli override e vengono saltati)
  - Invia un resoconto via email a fine esecuzione, stesso stile/destinatario del digest ordini
"""

import base64
import html
import json
import os
import re
import time
from datetime import datetime, timezone

import requests

# ── Config ───────────────────────────────────────────────────────────────────
SERPER_API_KEY = os.environ['SERPER_API_KEY']
CLAUDE_API_KEY = os.environ['CLAUDE_API_KEY']
BREVO_API_KEY  = os.environ['BREVO_API_KEY']
GH_TOKEN       = os.environ['GH_TOKEN']
GH_REPO        = os.environ['GH_REPO']

CONFIG_PATH    = 'data/research-config.json'
CONTACTS_PATH  = 'data/contatti.json'
OVERRIDES_PATH = 'data/contatti-overrides.json'

DEFAULT_CONFIG = {'queue': [], 'dailyLimit': 150}

DIGEST_RECIPIENT = 'luca@ilciliegio.com'
SENDER_NAME  = 'Il Ciliegio — Azienda Agricola'
SENDER_EMAIL = 'luca@sienawine.it'
LOGO_URL     = 'https://shopilciliegio-ship-it.github.io/crm-importatori/assets/logo_ciliegio.png'
ACCENT       = '#B8941A'
BG           = '#2c2c2c'

_GH_HEADERS = {
    'Authorization': f'token {GH_TOKEN}',
    'Accept':        'application/vnd.github.v3+json',
}
_BREVO_HEADERS = {
    'api-key':      BREVO_API_KEY,
    'Content-Type': 'application/json',
    'Accept':       'application/json',
}

RESEARCH_SYSTEM_PROMPT = """Sei un analista specializzato nel mercato del vino italiano.
Analizza le informazioni sull'azienda e rispondi SOLO con un oggetto JSON valido (niente testo fuori dal JSON):

{
  "affidabilita": <1-5>,
  "vino_italiano": "<si|probabile|forse|non_risulta|no>",
  "tipo_business": "<importatore|distributore|retailer|horeca|online|misto|sconosciuto>",
  "mercato_target": "<horeca|retail|online|misto|sconosciuto>",
  "raccomandato": "<si|forse|no>",
  "note": "<max 2 righe: punti chiave per decidere se contattare>"
}

Criteri di valutazione:
- affidabilita: 5=azienda solida con sito professionale e storia consolidata; 4=buoni segnali; 3=info parziali; 2=dati scarsi; 1=nessuna info o segnali negativi
- vino_italiano: si=citano esplicitamente vini italiani; probabile=portafoglio mediterraneo/europeo; forse=importatori generici di vino; non_risulta=nessuna info trovata; no=solo birra/spirits/cibo
- raccomandato: si=contattare con priorità; forse=vale la pena verificare; no=non pertinente o inaffidabile
- Considera dipendenti, fatturato, tipologia cliente (horeca vs retail) per valutare dimensione e fit"""


# ── GitHub helpers ────────────────────────────────────────────────────────────

def gh_get(path):
    """Ritorna (dati_json, sha) oppure (None, None) se il file non esiste."""
    url = f'https://api.github.com/repos/{GH_REPO}/contents/{path}'
    r = requests.get(url, headers=_GH_HEADERS)
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    d = r.json()
    raw = (d.get('content') or '').replace('\n', '')
    if raw:
        content = base64.b64decode(raw).decode('utf-8')
    else:
        # File > 1 MB: l'API Contents non include il content, va scaricato da download_url
        rr = requests.get(d['download_url'])
        rr.raise_for_status()
        content = rr.text
    return json.loads(content), d['sha']


def gh_put(path, data, sha, message):
    url     = f'https://api.github.com/repos/{GH_REPO}/contents/{path}'
    content = base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')).decode('utf-8')
    body    = {'message': message, 'content': content}
    if sha:
        body['sha'] = sha
    r = requests.put(url, headers=_GH_HEADERS, json=body)
    r.raise_for_status()
    return r.json()['content']['sha']


# ── Ricerca: Serper (Google), sito web, Claude ────────────────────────────────

def serper_search(company, country):
    if not SERPER_API_KEY:
        return ''
    try:
        r = requests.post('https://google.serper.dev/search',
            headers={'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'},
            json={'q': f'"{company}" wine importer {country}', 'num': 6, 'gl': 'us', 'hl': 'en'},
            timeout=20)
        if not r.ok:
            return ''
        data = r.json()
        parts = []
        kg = data.get('knowledgeGraph')
        if kg:
            parts.append(f"[Knowledge Graph] {kg.get('title','')} — {kg.get('description','')} ({kg.get('website','')})")
        for i in (data.get('organic') or [])[:5]:
            parts.append(f"[{i.get('title','')}] {i.get('snippet','')} ({i.get('link','')})")
        return '\n'.join(parts)
    except Exception as e:
        print(f'  ⚠ Serper error: {e}')
        return ''


_STYLE_RE  = re.compile(r'<style[\s\S]*?</style>', re.I)
_SCRIPT_RE = re.compile(r'<script[\s\S]*?</script>', re.I)
_TAG_RE    = re.compile(r'<[^>]+>')
_WS_RE     = re.compile(r'\s+')


def fetch_website(url):
    if not url or not url.startswith('http'):
        return ''
    try:
        r = requests.get(url, timeout=12, headers={'User-Agent': 'Mozilla/5.0 (compatible; IlCiliegioBot/1.0)'})
        if not r.ok:
            return ''
        text = _STYLE_RE.sub('', r.text)
        text = _SCRIPT_RE.sub('', text)
        text = _TAG_RE.sub(' ', text)
        text = _WS_RE.sub(' ', text).strip()
        return text[:2500]
    except Exception:
        return ''


_JSON_RE = re.compile(r'\{[\s\S]*\}')


def claude_analyze(c, search_text, web_text):
    prompt = f"""Azienda: {c.get('company','')}
Paese: {c.get('country','')} | Città: {c.get('city','')}
Tipo (BWI): {c.get('type','')} | Prodotti: {c.get('prodType','')}
Dipendenti: {c.get('employees','?')} | Fatturato: {c.get('sales','?')}
Sito dichiarato: {c.get('website') or '(nessuno)'}

--- RISULTATI GOOGLE ---
{search_text or '(nessun risultato trovato)'}

--- TESTO DAL SITO WEB ---
{web_text[:1800] if web_text else '(non disponibile o irraggiungibile)'}"""

    body = {
        'model':       'claude-haiku-4-5',
        'system':      RESEARCH_SYSTEM_PROMPT,
        'messages':    [{'role': 'user', 'content': prompt}],
        'temperature': 0.1,
        'max_tokens':  450,
    }
    headers = {
        'x-api-key':           CLAUDE_API_KEY,
        'anthropic-version':   '2023-06-01',
        'Content-Type':        'application/json',
    }

    for attempt in range(4):
        try:
            r = requests.post('https://api.anthropic.com/v1/messages', headers=headers, json=body, timeout=60)
            if r.status_code == 429:
                retry_after = int(r.headers.get('retry-after', 0) or 0)
                wait = retry_after if retry_after > 0 else [15, 30, 60][min(attempt, 2)]
                print(f'  ⏳ Rate limit Claude — attendo {wait}s (tentativo {attempt+1}/4)')
                time.sleep(wait)
                continue
            if not r.ok:
                print(f'  ⚠ Claude error: {r.status_code} {r.text[:150]}')
                return {}
            data    = r.json()
            content = (data.get('content') or [{}])[0].get('text', '').strip()
            m = _JSON_RE.search(content)
            return json.loads(m.group(0)) if m else {}
        except Exception as e:
            print(f'  ⚠ Claude exception: {e}')
            if attempt < 3:
                time.sleep(5)
    return {}


# ── Stato coda (per il resoconto email e per scegliere il paese attivo) ───────

def queue_progress(queue, by_country, overrides):
    """Per ogni paese in coda: (nome, analizzati, totale)."""
    rows = []
    for country in queue:
        contacts = by_country.get(country, [])
        done = sum(1 for c in contacts if (overrides.get(c['id']) or {}).get('research'))
        rows.append((country, done, len(contacts)))
    return rows


# ── Email di resoconto ────────────────────────────────────────────────────────

def send_report(subject_suffix, headline, stats_rows, queue_rows, active_countries=None):
    active_countries = active_countries or set()
    now_str = datetime.now().strftime('%d/%m/%Y %H:%M')

    def _stats_table(rows):
        if not rows:
            return ''
        trs = ''.join(
            f'<tr><td style="padding:4px 12px 4px 0;color:#555;font-size:14px">{html.escape(label)}</td>'
            f'<td style="padding:4px 0;font-weight:bold;font-size:14px;color:#333">{value}</td></tr>'
            for label, value in rows
        )
        return f'<table style="border-collapse:collapse;margin:8px 0 20px">{trs}</table>'

    def _queue_list(rows):
        if not rows:
            return '<p style="color:#999;font-size:13px;margin:0">Nessun paese in coda — seleziona dei paesi nella pagina Importatori per avviare nuove ricerche.</p>'
        items = []
        for country, done, total in rows:
            pct = round(done / total * 100) if total else 0
            badge = '🟡' if done < total else '🟢'
            active = ' <span style="color:' + ACCENT + ';font-weight:bold">← in lavorazione</span>' if country in active_countries else ''
            items.append(
                f'<li style="padding:3px 0;color:#333;font-size:14px">{badge} <b>{html.escape(country)}</b> — {done} / {total} analizzati ({pct}%){active}</li>'
            )
        return f'<ul style="margin:0;padding-left:20px">{"".join(items)}</ul>'

    body_html = f"""
    <p style="margin:0 0 4px;color:#999;font-size:12px">{now_str}</p>
    <h2 style="margin:0 0 20px;color:#222;font-size:20px;font-weight:bold">🔬 Ricerca AI importatori</h2>
    <p style="margin:0 0 8px;color:#333;font-size:15px">{headline}</p>
    {_stats_table(stats_rows)}
    <h3 style="margin:24px 0 8px;color:#555;font-size:13px;text-transform:uppercase;letter-spacing:1px">📋 Stato coda paesi</h3>
    {_queue_list(queue_rows)}
    """

    html_content = f"""<!DOCTYPE html><html lang="it">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f4f0;font-family:Georgia,'Times New Roman',serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f0;padding:32px 16px">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
  <tr><td style="background:{BG};border-radius:12px 12px 0 0;padding:20px 32px;text-align:center">
    <img src="{LOGO_URL}" width="140" alt="Il Ciliegio" style="display:block;margin:0 auto">
  </td></tr>
  <tr><td style="background:{ACCENT};height:4px;font-size:0">&nbsp;</td></tr>
  <tr><td style="background:#ffffff;padding:32px 40px">{body_html}</td></tr>
  <tr><td style="background:{ACCENT};height:3px;font-size:0">&nbsp;</td></tr>
  <tr><td style="background:{BG};border-radius:0 0 12px 12px;padding:16px 32px;text-align:center">
    <p style="margin:0;color:#999;font-size:11px">Il Ciliegio CRM — report automatico</p>
  </td></tr>
</table></td></tr></table>
</body></html>"""

    plain_headline = re.sub(r'<br\s*/?>', '\n', headline)
    plain_headline = re.sub(r'<[^>]+>', '', plain_headline)
    text_lines = [plain_headline] + [f'{label}: {value}' for label, value in stats_rows]
    text_lines.append('')
    text_lines.append('Stato coda:')
    for country, done, total in queue_rows:
        text_lines.append(f'  {country}: {done}/{total}')

    payload = {
        'sender':      {'name': SENDER_NAME, 'email': SENDER_EMAIL},
        'to':          [{'email': DIGEST_RECIPIENT, 'name': 'Luca'}],
        'subject':     f'🔬 Ricerca AI — {subject_suffix} — {now_str}',
        'htmlContent': html_content,
        'textContent': '\n'.join(text_lines),
        'tags':        ['wine-crm', 'ricerca-ai'],
        'trackClicks': False,
        'trackOpens':  False,
    }
    r = requests.post('https://api.brevo.com/v3/smtp/email', headers=_BREVO_HEADERS, json=payload)
    if r.ok:
        print(f'✓ Resoconto inviato a {DIGEST_RECIPIENT}')
    else:
        print(f'⚠ Resoconto fallito: {r.status_code} {r.text[:150]}')


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    config, _ = gh_get(CONFIG_PATH)
    if config is None:
        config = DEFAULT_CONFIG
    queue       = config.get('queue') or []
    daily_limit = config.get('dailyLimit') or DEFAULT_CONFIG['dailyLimit']

    if not queue:
        print('Coda vuota — nessun paese selezionato per la ricerca automatica')
        send_report('coda vuota', '📭 Nessun paese selezionato per la ricerca automatica oggi.', [], [])
        return

    print(f'Coda: {queue} — quota giornaliera: {daily_limit}')

    contacts_data, _ = gh_get(CONTACTS_PATH)
    contacts = (contacts_data or {}).get('contacts', [])
    if not contacts:
        print('⚠ data/contatti.json vuoto o non disponibile — interrompo')
        return

    overrides, overrides_sha = gh_get(OVERRIDES_PATH)
    if overrides is None:
        overrides = {}

    by_country = {}
    for c in contacts:
        by_country.setdefault(c.get('country', ''), []).append(c)

    # Costruisce il piano di lavoro scorrendo la coda in ordine FIFO finché
    # non si raggiunge la quota giornaliera (un paese esaurito passa al successivo)
    plan           = []  # [(country, [contatti]), ...]
    pending_totals = {}  # country -> totale contatti pendenti prima di questa run
    remaining_budget = daily_limit
    for country in queue:
        country_contacts = by_country.get(country, [])
        pending = [c for c in country_contacts if not (overrides.get(c['id']) or {}).get('research')]
        if not pending:
            continue
        pending_totals[country] = len(pending)
        if remaining_budget <= 0:
            continue
        take = pending[:remaining_budget]
        plan.append((country, take))
        remaining_budget -= len(take)

    if not plan:
        print('Tutti i paesi in coda sono già completamente analizzati')
        rows = queue_progress(queue, by_country, overrides)
        send_report(
            'coda completata',
            '✅ Tutti i paesi in coda sono completamente analizzati. Seleziona altri paesi nella pagina Importatori per avviare nuove ricerche.',
            [], rows
        )
        return

    total_to_analyze = sum(len(c) for _, c in plan)
    print(f'Piano: {[(country, len(c)) for country, c in plan]} — {total_to_analyze} da analizzare oggi ({daily_limit} quota)')

    stats = {'si': 0, 'forse': 0, 'no': 0, 'vino': 0}
    analyzed_by_country = {}
    analyzed = 0
    errors   = 0

    for country, contacts_list in plan:
        print(f'Paese: {country} — {len(contacts_list)} da analizzare oggi')
        for i, c in enumerate(contacts_list, 1):
            analyzed += 1
            print(f'  [{i}/{len(contacts_list)}] {(c.get("company","") or "")[:50]}')

            search_text = serper_search(c.get('company', ''), country)
            web_text    = fetch_website(c.get('website', '')) if c.get('website') else ''
            analysis    = claude_analyze(c, search_text, web_text)

            if analysis:
                now_iso = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
                entry = overrides.setdefault(c['id'], {})
                entry['research'] = {**analysis, 'analyzed_at': now_iso}

                rec = analysis.get('raccomandato')
                if rec == 'si':
                    stats['si'] += 1
                elif rec == 'forse':
                    stats['forse'] += 1
                elif rec == 'no':
                    stats['no'] += 1
                if analysis.get('vino_italiano') in ('si', 'probabile'):
                    stats['vino'] += 1
            else:
                errors += 1

            time.sleep(2.5)

        analyzed_by_country[country] = len(contacts_list)

    countries_label = '+'.join(plan[i][0] for i in range(len(plan)))
    gh_put(OVERRIDES_PATH, overrides, overrides_sha, f'Ricerca AI — {countries_label} ({analyzed} analizzati)')
    print(f'✓ {analyzed} risultati salvati in {OVERRIDES_PATH} ({errors} errori)')

    headline_lines = []
    for country, took in analyzed_by_country.items():
        country_remaining = pending_totals[country] - took
        if country_remaining > 0:
            headline_lines.append(
                f'🔬 <b>{html.escape(country)}</b>: analizzati {took} contatti oggi. '
                f'Ne restano <b>{country_remaining}</b> — la ricerca riprenderà domani da dove si è fermata.'
            )
        else:
            headline_lines.append(
                f'✅ <b>{html.escape(country)}</b> completata: analizzati gli ultimi {took} contatti. '
                f'Il paese è ora interamente coperto 🟢.'
            )
    headline = '<br>'.join(headline_lines)

    rows = queue_progress(queue, by_country, overrides)
    stats_rows = [
        ('🔍 Analizzati oggi',            analyzed),
        ('✅ Consigliati (sì)',           stats['si']),
        ('🤔 Forse',                      stats['forse']),
        ('❌ Non consigliati',            stats['no']),
        ('🍷 Vino italiano sì/probabile', stats['vino']),
        ('⚠️ Errori',                     errors),
    ]
    subject_suffix = countries_label if len(plan) <= 2 else f'{len(plan)} paesi'
    send_report(subject_suffix, headline, stats_rows, rows, active_countries=set(analyzed_by_country))


if __name__ == '__main__':
    main()
