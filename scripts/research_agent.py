# -*- coding: utf-8 -*-
"""
research_agent.py
=================
Ricerca e valutazione automatica di importatori per paese.
Usa Serper (Google Search) + Groq (Llama 3.1 70B) per analizzare ogni azienda.

Uso:
    python scripts/research_agent.py --country Vietnam
    python scripts/research_agent.py --country Germany --limit 20
    python scripts/research_agent.py --country Vietnam --skip-website

Secret (env var o passati da shell):
    SERPER_API_KEY   -> chiave Serper.dev
    GROQ_API_KEY     -> chiave Groq
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

import requests

# ── CONFIG ────────────────────────────────────────────────────────────────────
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")

SERPER_URL = "https://google.serper.dev/search"
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT      = os.path.dirname(SCRIPT_DIR)
CONTATTI_FILE  = os.path.join(REPO_ROOT, "data", "contatti.json")
OUTPUT_DIR     = os.path.join(REPO_ROOT, "data")

SYSTEM_PROMPT = """Sei un analista specializzato nel mercato del vino italiano. Valuta le informazioni sull'azienda e rispondi SOLO con un JSON valido (niente testo fuori dal JSON):

{
  "affidabilita": <1-5>,
  "vino_italiano": "<si|probabile|forse|non_risulta|no>",
  "tipo_business": "<importatore|distributore|retailer|horeca|online|misto|sconosciuto>",
  "mercato_target": "<horeca|retail|online|misto|sconosciuto>",
  "raccomandato": "<si|forse|no>",
  "note": "<max 2 righe di osservazioni chiave>"
}

Criteri di valutazione:
- affidabilita: 5=azienda solida, sito professionale, storia consolidata; 3=info parziali; 1=nessuna info o segnali negativi
- vino_italiano: si=dichiarano esplicitamente vini italiani; probabile=portafoglio mediterraneo/europeo; forse=importatori generici; non_risulta=nessuna info trovata; no=solo birra/spirits/cibo
- raccomandato: si=contattare con priorità; forse=vale la pena verificare; no=non pertinente o inaffidabile"""


# ── SERPER ────────────────────────────────────────────────────────────────────

def search_company(company: str, country: str) -> str:
    query = f'"{company}" wine importer {country}'
    try:
        r = requests.post(
            SERPER_URL,
            json={"q": query, "num": 5, "gl": "us", "hl": "en"},
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            timeout=10,
        )
        if not r.ok:
            return ""
        data = r.json()
        snippets = []
        for item in data.get("organic", [])[:5]:
            t = item.get("title", "")
            s = item.get("snippet", "")
            l = item.get("link", "")
            snippets.append(f"[{t}] {s}  ({l})")
        return "\n".join(snippets)
    except Exception as e:
        print(f"    ⚠ Serper error: {e}")
        return ""


# ── WEBSITE ───────────────────────────────────────────────────────────────────

def fetch_website(url: str, max_chars: int = 2500) -> str:
    if not url or not url.startswith("http"):
        return ""
    try:
        r = requests.get(
            url,
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0 (compatible; WineResearchBot/1.0)"},
            allow_redirects=True,
        )
        if not r.ok:
            return ""
        text = re.sub(r"<[^>]+>", " ", r.text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception:
        return ""


# ── GROQ ──────────────────────────────────────────────────────────────────────

def analyze_company(c: dict, search: str, website_text: str) -> dict:
    prompt = f"""Azienda: {c.get('company','')}
Paese: {c.get('country','')}, Città: {c.get('city','')}
Tipo (database BWI): {c.get('type','')}
Sito web dichiarato: {c.get('website','')}

--- RISULTATI GOOGLE ---
{search or '(nessun risultato)'}

--- TESTO DAL SITO WEB ---
{website_text[:1500] if website_text else '(non disponibile)'}"""

    try:
        r = requests.post(
            GROQ_URL,
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 350,
            },
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=25,
        )
        if not r.ok:
            print(f"    ⚠ Groq {r.status_code}: {r.text[:80]}")
            return {}
        content = r.json()["choices"][0]["message"]["content"].strip()
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            return json.loads(m.group())
        return {}
    except Exception as e:
        print(f"    ⚠ Groq exception: {e}")
        return {}


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Research agent importatori")
    parser.add_argument("--country",       required=True, help="Paese da analizzare (es. Vietnam)")
    parser.add_argument("--limit",         type=int, default=0, help="Limita numero aziende (0=tutte)")
    parser.add_argument("--skip-website",  action="store_true", help="Non visita i siti web (più veloce)")
    parser.add_argument("--output",        default="", help="File output (default: data/research_PAESE_DATA.json)")
    args = parser.parse_args()

    if not SERPER_API_KEY:
        print("ERRORE: SERPER_API_KEY non impostata")
        sys.exit(1)
    if not GROQ_API_KEY:
        print("ERRORE: GROQ_API_KEY non impostata")
        sys.exit(1)

    print(f"Carico contatti da {CONTATTI_FILE}...")
    with open(CONTATTI_FILE, encoding="utf-8") as f:
        data = json.load(f)

    contacts = [
        c for c in data["contacts"]
        if c.get("country", "").strip().lower() == args.country.strip().lower()
    ]

    if not contacts:
        print(f"Nessun contatto trovato per: {args.country}")
        print(f"Paesi disponibili (primi 20): {sorted({c['country'] for c in data['contacts']})[:20]}")
        sys.exit(1)

    if args.limit > 0:
        contacts = contacts[: args.limit]

    country_slug = args.country.replace(" ", "_")
    date_str     = datetime.now().strftime("%Y%m%d")
    output_file  = args.output or os.path.join(OUTPUT_DIR, f"research_{country_slug}_{date_str}.json")

    print(f"\n{'='*55}")
    print(f"  Research Agent — {args.country.upper()}")
    print(f"  Aziende da analizzare: {len(contacts)}")
    print(f"  Visita siti web: {'no (--skip-website)' if args.skip_website else 'sì'}")
    print(f"  Output: {output_file}")
    print(f"{'='*55}\n")

    results = []

    for i, c in enumerate(contacts):
        company = c.get("company", "").strip()
        print(f"[{i+1:>3}/{len(contacts)}] {company[:55]}")

        # 1. Ricerca Google
        search = search_company(company, args.country)
        time.sleep(0.6)

        # 2. Sito web
        website_text = ""
        if not args.skip_website and c.get("website"):
            website_text = fetch_website(c["website"])

        # 3. Analisi AI
        analysis = analyze_company(c, search, website_text)
        time.sleep(0.4)

        result = {
            "id":          c["id"],
            "bwiCompId":   c.get("bwiCompId", ""),
            "company":     company,
            "country":     c.get("country", ""),
            "city":        c.get("city", ""),
            "website":     c.get("website", ""),
            "email":       c.get("email", ""),
            "type":        c.get("type", ""),
            **analysis,
            "analyzed_at": datetime.now().isoformat(),
        }
        results.append(result)

        aff  = analysis.get("affidabilita", "?")
        vino = analysis.get("vino_italiano", "?")
        rec  = analysis.get("raccomandato", "?")
        stars = "★" * int(aff) if isinstance(aff, int) else str(aff)
        print(f"       affidabilità:{stars}  vino_it:{vino:<12}  raccomandato:{rec}")

        # Salva incrementalmente ogni 10 aziende
        if (i + 1) % 10 == 0 or (i + 1) == len(contacts):
            _save_results(output_file, args.country, len(contacts), results)

    # Statistiche finali
    rec_si    = sum(1 for r in results if r.get("raccomandato") == "si")
    rec_forse = sum(1 for r in results if r.get("raccomandato") == "forse")
    vino_conf = sum(1 for r in results if r.get("vino_italiano") in ("si", "probabile"))

    print(f"\n{'='*55}")
    print(f"  RISULTATI {args.country.upper()}")
    print(f"{'='*55}")
    print(f"  Analizzate:    {len(results)} / {len(contacts)}")
    print(f"  Raccomandate:  {rec_si} sì,  {rec_forse} forse")
    print(f"  Vino italiano: {vino_conf} confermate/probabili")
    print(f"  Output:        {output_file}")

    _save_results(output_file, args.country, len(contacts), results)


def _save_results(path: str, country: str, total: int, results: list):
    out = {
        "country":      country,
        "total":        total,
        "analyzed":     len(results),
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "raccomandato_si":    sum(1 for r in results if r.get("raccomandato") == "si"),
            "raccomandato_forse": sum(1 for r in results if r.get("raccomandato") == "forse"),
            "vino_italiano_si":   sum(1 for r in results if r.get("vino_italiano") in ("si", "probabile")),
        },
        "results": results,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
