"""
Lärmschutz News Fetcher

Modes:
  - Daily:          fetch 7-day news, update data.json  → Claude Haiku 4.5
  - Weekly summary: read data.json, generate summary.html → Claude Sonnet 4.6
  - Monthly summary: fetch 30-day news, generate summary_monthly_YYYY-MM.html → Claude Sonnet 4.6
"""

import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import HTTPError
import xml.etree.ElementTree as ET

# ── Configuration ──────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
ANTHROPIC_URL     = "https://api.anthropic.com/v1/messages"

# Haiku for daily summaries (fast, cheap)
CLAUDE_HAIKU  = "claude-haiku-4-5-20251001"
# Sonnet for newsletters (better quality)
CLAUDE_SONNET = "claude-sonnet-4-6"

WEEKLY_SUMMARY_ONLY  = os.environ.get("WEEKLY_SUMMARY",  "false").lower() == "true"
MONTHLY_SUMMARY_ONLY = os.environ.get("MONTHLY_SUMMARY", "false").lower() == "true"

MAX_ITEMS_FROM_FEED    = 100
MAX_AGE_DAYS_WEEKLY    = 7
MAX_AGE_DAYS_MONTHLY   = 31
MAX_ITEMS_PER_CATEGORY = 15
MAX_TITLES_FOR_SUMMARY = 15
CLAUDE_PAUSE_SECONDS   = 10   # Claude hat kein hartes Rate Limit wie Gemini
CLAUDE_RETRY_ATTEMPTS  = 5
CLAUDE_RETRY_WAIT      = 60
SUMMARY_PRE_PAUSE      = 5

# OIB keyword filters
BAUAKUSTIK_EXCLUDE_KEYWORDS = [
    "aktiengesellschaft", "börse", "investition", "aktien",
    "begrünung", "dachbegrünung", "fassadenbegrünung", "energieeffizienz",
    "sri ", "smart readiness", "photovoltaik", "solar", "heizung",
    "brandschutz",
    "betriebsausflug", "jubiläum", "vorhang auf",
]
BAUAKUSTIK_INCLUDE_KEYWORDS = [
    "schallschutz", "akustik", "lärm", "schall", "bauakustik",
    "schwingung", "trittschall", "luftschall", "oib-richtlinie 5",
    "wärmepumpe", "lüftung", "klimaanlage",
    "richtlinie 5", "geräusch",
]


def gnews(query: str, lang: str = "de", country: str = "AT") -> str:
    from urllib.parse import quote
    return (
        f"https://news.google.com/rss/search"
        f"?q={quote(query)}&hl={lang}&gl={country}&ceid={country}:{lang}"
    )


CATEGORIES = {
    "steiermark": {
        "label": "Steiermark",
        "icon": "🏞️",
        "color": "#1a5c38",
        "feeds": [
            gnews("Lärmschutz Steiermark"),
            gnews("Verkehrslärm Steiermark"),
            gnews("Umgebungslärm Steiermark"),
            gnews("Fluglärm Graz"),
            gnews("Lärm Graz Steiermark"),
            gnews("Schienenlärm Steiermark"),
            gnews("Infraschall Steiermark"),
            gnews("tieffrequenter Schall Steiermark"),
            gnews("Brummton Steiermark"),
            gnews("Raumordnung Lärm Steiermark"),
            gnews("Lärmbekämpfung Steiermark"),
            gnews("Red Bull Ring Lärm"),
            gnews("Formel 1 Spielberg Lärm"),
            gnews("MotoGP Spielberg Lärm"),
            gnews("Fohnsdorf Lärm"),
            gnews("Abteilung 15 Land Steiermark Lärm"),
            gnews("Abteilung 13 Land Steiermark Lärm"),
            gnews("UVP Verfahren Steiermark Lärm"),
        ],
        "keyword_filter": None,
        "summary_prompt": (
            "Du bist Experte für Lärmschutz in der Steiermark und Graz. "
            "Fasse die folgenden Nachrichtentitel in 2 prägnanten deutschen Sätzen zusammen. "
            "Antworte NUR mit Fließtext."
        ),
        "monthly_prompt": (
            "Du bist Experte für Lärmschutz in der Steiermark. "
            "Fasse die wichtigsten Entwicklungen des letzten Monats in 2–3 Sätzen zusammen. "
            "Antworte NUR mit Fließtext."
        ),
    },
    "austria": {
        "label": "Österreich",
        "icon": "🇦🇹",
        "color": "#c8102e",
        "feeds": [
            gnews("Lärmschutz Österreich"),
            gnews("Lärmschutzwand Österreich"),
            gnews("Verkehrslärm Österreich"),
            gnews("Umgebungslärm Österreich"),
            gnews("Schienenlärm Österreich"),
            gnews("Fluglärm Österreich"),
            gnews("Industrielärm Österreich"),
            gnews("Infraschall Österreich"),
            gnews("tieffrequenter Schall Österreich"),
            gnews("Brummton Österreich"),
            gnews("Lärm Verordnung Österreich"),
            gnews("Lärmbekämpfung Österreich"),
            gnews("Ruhige Gebiete Österreich"),
            gnews("Lärmkarte Österreich"),
            gnews("Raumordnung Lärm Österreich"),
            gnews("ÖAL Österreichischer Arbeitsring Lärmbekämpfung"),
            gnews("site:oal.at"),
            "https://www.oal.at/?format=feed&type=rss",
        ],
        "keyword_filter": None,
        "summary_prompt": (
            "Du bist Experte für Lärmschutz in Österreich. "
            "Fasse die folgenden Nachrichtentitel in 2 prägnanten deutschen Sätzen zusammen. "
            "Hebe auch Neuigkeiten vom Österreichischen Arbeitsring für Lärmbekämpfung (ÖAL) hervor. "
            "Antworte NUR mit Fließtext."
        ),
        "monthly_prompt": (
            "Du bist Experte für Lärmschutz in Österreich. "
            "Fasse die wichtigsten Entwicklungen des letzten Monats in 2–3 Sätzen zusammen. "
            "Antworte NUR mit Fließtext."
        ),
    },
    "dach": {
        "label": "DACH",
        "icon": "🏔️",
        "color": "#5a5a5a",
        "feeds": [
            gnews("Verkehrslärm Deutschland", country="DE"),
            gnews("Umgebungslärm Deutschland", country="DE"),
            gnews("Fluglärm Deutschland", country="DE"),
            gnews("Schienenlärm Bahn Deutschland", country="DE"),
            gnews("Industrielärm Deutschland", country="DE"),
            gnews("Lärmkarte Lärmkartierung Deutschland", country="DE"),
            gnews("Ruhige Gebiete Lärmschutz Deutschland", country="DE"),
            gnews("Infraschall Deutschland", country="DE"),
            gnews("Brummton Deutschland", country="DE"),
            gnews("Lärmbekämpfung Deutschland", country="DE"),
            gnews("Lärmschutz Schweiz", country="DE"),
            gnews("Verkehrslärm Schweiz", country="DE"),
            gnews("Fluglärm Schweiz Zürich", country="DE"),
            gnews("Umgebungslärm Schweiz", country="DE"),
            gnews("Schienenlärm Schweiz", country="DE"),
            gnews("DEGA Akustik Veranstaltungen Konferenz", country="DE"),
            gnews("DEGA Akustik Neuigkeiten", country="DE"),
            gnews("site:dega-akustik.de", country="DE"),
            "https://www.dega-akustik.de/index.php?id=2&type=100",
        ],
        "keyword_filter": None,
        "summary_prompt": (
            "Du bist Experte für Umgebungslärm in der DACH-Region (Deutschland, Österreich, Schweiz). "
            "Fasse die folgenden Nachrichtentitel in 2 prägnanten deutschen Sätzen zusammen. "
            "Erwähne explizit Entwicklungen aus Deutschland UND der Schweiz wenn vorhanden. "
            "Hebe auch Veranstaltungen und Neuigkeiten der DEGA hervor. "
            "Antworte NUR mit Fließtext."
        ),
        "monthly_prompt": (
            "Du bist Experte für Umgebungslärm in der DACH-Region. "
            "Fasse die wichtigsten Entwicklungen des letzten Monats in 2–3 Sätzen zusammen. "
            "Antworte NUR mit Fließtext."
        ),
    },
    "europe": {
        "label": "Europa",
        "icon": "🇪🇺",
        "color": "#003399",
        "feeds": [
            gnews("noise control EU directive", lang="en", country="GB"),
            gnews("environmental noise Europe regulation", lang="en", country="GB"),
            gnews("noise pollution Europe policy", lang="en", country="GB"),
            gnews("Umgebungslärm EU Richtlinie", country="DE"),
            gnews("quiet areas noise Europe", lang="en", country="GB"),
            gnews("low frequency noise Europe", lang="en", country="GB"),
            gnews("infrasound regulation Europe", lang="en", country="GB"),
        ],
        "keyword_filter": None,
        "summary_prompt": (
            "You are an expert on European noise control policy. "
            "Summarize the following headlines in 2 concise sentences in English. "
            "Reply ONLY with flowing prose."
        ),
        "monthly_prompt": (
            "You are an expert on European noise control policy. "
            "Summarize the most significant developments of the past month in 2–3 sentences. "
            "Reply ONLY with flowing prose."
        ),
    },
    "science": {
        "label": "Wissenschaft",
        "icon": "🔬",
        "color": "#1a6b3c",
        "feeds": [
            gnews("acoustics noise control research", lang="en", country="GB"),
            gnews("noise barrier material research", lang="en", country="GB"),
            gnews("urban noise acoustic study", lang="en", country="GB"),
            gnews("noise pollution health research", lang="en", country="GB"),
            gnews("low frequency noise infrasound research", lang="en", country="GB"),
            gnews("Lärmbekämpfung Forschung", country="DE"),
            gnews("Lärmschutz Wissenschaft Studie", country="DE"),
            gnews("site:ingenieur.de/fachmedien/laermbekaempfung", country="DE"),
            gnews("Lärmbekämpfung Akustik ingenieur.de", country="DE"),
        ],
        "keyword_filter": None,
        "summary_prompt": (
            "You are an acoustics researcher. "
            "Summarize the following headlines in 2 concise sentences in English. "
            "Reply ONLY with flowing prose."
        ),
        "monthly_prompt": (
            "You are an acoustics researcher. "
            "Summarize the most significant research developments of the past month in 2–3 sentences. "
            "Reply ONLY with flowing prose."
        ),
    },
    "bauakustik": {
        "label": "Bauakustik",
        "icon": "🏗️",
        "color": "#7b4f12",
        "feeds": [
            gnews("Bauakustik Österreich"),
            gnews("Bauakustik DACH", country="DE"),
            gnews("OIB Richtlinie Schallschutz Gebäude"),
            gnews("OIB Richtlinie 5 Schallschutz"),
            gnews("Schallschutz Gebäude Österreich"),
            gnews("Gebäudeakustik Österreich"),
            gnews("Gebäudeschwingung Österreich"),
            gnews("Schallschutz Wohnbau Österreich"),
            gnews("Bauakustik Norm"),
            gnews("Trittschallschutz Österreich"),
            gnews("Schallschutz Neubau DACH", country="DE"),
            gnews("Gebäudeakustik Forschung", country="DE"),
            "https://www.oib.or.at/feed/",
            gnews("DEGA Bauakustik Seminar Schulung", country="DE"),
            gnews("site:dega-akustik.de Bauakustik", country="DE"),
            gnews("ÖAL Österreichischer Arbeitsring Bauakustik"),
            gnews("site:oal.at Bauakustik Schallschutz"),
            "https://www.oal.at/?format=feed&type=rss",
        ],
        "keyword_filter": {
            "include": BAUAKUSTIK_INCLUDE_KEYWORDS,
            "exclude": BAUAKUSTIK_EXCLUDE_KEYWORDS,
            "filter_source": "oib.or.at",
        },
        "summary_prompt": (
            "Du bist Experte für Bauakustik und Schallschutz in Gebäuden im DACH-Raum. "
            "Fasse die folgenden Nachrichtentitel in 2 prägnanten deutschen Sätzen zusammen. "
            "Fokus auf OIB-Richtlinien, Schallschutz im Hochbau, DEGA- und ÖAL-Neuigkeiten. "
            "Antworte NUR mit Fließtext."
        ),
        "monthly_prompt": (
            "Du bist Experte für Bauakustik im DACH-Raum. "
            "Fasse die wichtigsten Entwicklungen des letzten Monats zu Bauakustik "
            "und Schallschutz in Gebäuden in 2–3 Sätzen zusammen. "
            "Antworte NUR mit Fließtext."
        ),
    },
}


# ── RSS Fetching ───────────────────────────────────────────────────────────────

def parse_pub_date(raw: str):
    if not raw:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(raw)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(raw.rstrip("Z") + "+00:00")
    except Exception:
        return None


def fetch_rss(url: str) -> list[dict]:
    items = []
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"})
        with urlopen(req, timeout=30) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        channel = root.find("channel")
        if channel is not None:
            entries = channel.findall("item")
        else:
            entries = (root.findall("{http://www.w3.org/2005/Atom}entry") or
                       root.findall("entry"))
        for item in entries[:MAX_ITEMS_FROM_FEED]:
            title = (item.findtext("title") or
                     item.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
            title = re.sub(r"<[^>]+>", "", title).strip()
            link_el = item.find("link")
            if link_el is not None:
                link = (link_el.get("href") or link_el.text or "").strip()
            else:
                link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or
                   item.findtext("published") or
                   item.findtext("{http://www.w3.org/2005/Atom}published") or
                   item.findtext("updated") or
                   item.findtext("{http://www.w3.org/2005/Atom}updated") or "").strip()
            source_el = item.find("source")
            source = source_el.text.strip() if source_el is not None else ""
            if not source:
                try:
                    from urllib.parse import urlparse
                    source = urlparse(url).netloc.replace("www.", "")
                except Exception:
                    pass
            if title:
                items.append({
                    "title": title, "link": link,
                    "date_raw": pub, "date_parsed": parse_pub_date(pub), "source": source,
                })
    except Exception as e:
        print(f"  Warning: could not fetch {url[:70]}: {e}")
    return items


def apply_keyword_filter(items: list[dict], kf: dict) -> list[dict]:
    if not kf:
        return items
    filter_source = kf.get("filter_source", "")
    include_kw = [k.lower() for k in kf.get("include", [])]
    exclude_kw = [k.lower() for k in kf.get("exclude", [])]
    result = []
    for item in items:
        if filter_source and filter_source not in item.get("source", "").lower():
            result.append(item)
            continue
        title_lower = item["title"].lower()
        if any(kw in title_lower for kw in exclude_kw):
            continue
        if include_kw and not any(kw in title_lower for kw in include_kw):
            continue
        result.append(item)
    filtered = len(items) - len(result)
    if filtered:
        print(f"  Keyword-filtered {filtered} irrelevant items from {filter_source}")
    return result


def filter_by_age(items, max_age_days):
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    result, skipped = [], 0
    for item in items:
        dt = item.get("date_parsed")
        if dt is None or dt >= cutoff:
            result.append(item)
        else:
            skipped += 1
    if skipped:
        print(f"  Filtered out {skipped} items older than {max_age_days} days")
    return result


def deduplicate(items):
    seen, result = set(), []
    for item in items:
        key = re.sub(r"\s+", " ", item["title"].lower().strip())
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def format_date(raw):
    if not raw:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(raw).strftime("%-d. %b %Y")
    except Exception:
        pass
    try:
        return datetime.fromisoformat(raw.rstrip("Z") + "+00:00").strftime("%-d. %b %Y")
    except Exception:
        return raw[:16]


# ── Claude API ─────────────────────────────────────────────────────────────────

def call_claude(prompt: str, model: str = CLAUDE_HAIKU, max_tokens: int = 1024) -> str:
    import json as _json
    body = _json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    for attempt in range(1, CLAUDE_RETRY_ATTEMPTS + 1):
        try:
            req = Request(
                ANTHROPIC_URL,
                data=body,
                headers={
                    "Content-Type":      "application/json",
                    "x-api-key":         ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with urlopen(req, timeout=30) as resp:
                data = _json.loads(resp.read())
            text = data["content"][0]["text"].strip()
            print(f"  ✅ Claude ({model.split('-')[1]}) OK — {len(text)} chars")
            return text
        except HTTPError as e:
            body_err = e.read().decode("utf-8", errors="replace")
            if e.code == 429:
                if attempt < CLAUDE_RETRY_ATTEMPTS:
                    print(f"  Claude 429 (attempt {attempt}/{CLAUDE_RETRY_ATTEMPTS}) – waiting {CLAUDE_RETRY_WAIT}s… {body_err[:100]}")
                    time.sleep(CLAUDE_RETRY_WAIT)
                else:
                    return "Zusammenfassung konnte nicht erstellt werden (Rate Limit)."
            else:
                print(f"  Claude HTTP error {e.code}: {body_err[:300]}")
                return "Zusammenfassung konnte nicht erstellt werden."
        except Exception as e:
            print(f"  Claude error: {e}")
            return "Zusammenfassung konnte nicht erstellt werden."
    return "Zusammenfassung konnte nicht erstellt werden."


def summarize_daily(titles, prompt) -> str:
    """Daily summaries use Haiku — fast and cheap."""
    if not titles:
        return "Keine aktuellen Meldungen gefunden."
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    return call_claude(
        prompt + "\n\nNachrichtentitel:\n" + numbered,
        model=CLAUDE_HAIKU,
        max_tokens=512,
    )


def summarize_monthly_category(titles, prompt) -> str:
    """Monthly per-category summaries use Haiku."""
    if not titles:
        return "Keine aktuellen Meldungen gefunden."
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    return call_claude(
        prompt + "\n\nNachrichtentitel:\n" + numbered,
        model=CLAUDE_HAIKU,
        max_tokens=512,
    )


def generate_newsletter(prompt: str) -> str:
    """Full newsletter generation uses Sonnet — better structure and quality."""
    return call_claude(prompt, model=CLAUDE_SONNET, max_tokens=2000)


# ── Newsletter HTML Builder ────────────────────────────────────────────────────

def render_newsletter_text(raw_text: str) -> str:
    lines = raw_text.split("\n")
    html_lines = []
    in_list = False
    for line in lines:
        line = line.strip()
        if not line:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            continue
        if re.match(r"^(\*\*)?[A-ZÄÖÜ&][^.!?\n]{0,50}:(\*\*)?$", line):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            clean = re.sub(r"\*\*", "", line).rstrip(":")
            html_lines.append(f'<h3 class="nl-section">{clean}</h3>')
        elif re.match(r"^[-•*]\s+|^\d+\.\s+", line):
            if not in_list:
                html_lines.append('<ul class="nl-list">')
                in_list = True
            text = re.sub(r"^[-•*]\s+|^\d+\.\s+", "", line)
            text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)
            html_lines.append(f"<li>{text}</li>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", line)
            html_lines.append(f"<p>{text}</p>")
    if in_list:
        html_lines.append("</ul>")
    return "\n".join(html_lines)


def build_top_articles_html(top_articles):
    if not top_articles:
        return ""
    html = '<h3 class="nl-section">Wichtigste Meldungen</h3><ul class="nl-list nl-links">'
    for art in top_articles:
        t = art.get("title", "")
        u = art.get("link", "")
        d = art.get("date", "")
        s = art.get("source", "")
        meta = " · ".join(filter(None, [s, d]))
        html += f'<li><a href="{u}" target="_blank" rel="noopener">{t}</a>' if u else f'<li>{t}'
        if meta:
            html += f' <span class="nl-meta">{meta}</span>'
        html += '</li>'
    html += '</ul>'
    return html


def build_newsletter_html(title, kw_label, date_str, subtitle, exec_text, top_articles=None):
    content = render_newsletter_text(exec_text)
    links_html = build_top_articles_html(top_articles or [])
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet" />
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'DM Sans', sans-serif; background: #f0f4f0; color: #1a1a1a; padding: 40px 20px 80px; }}
    .page {{ max-width: 740px; margin: 0 auto; background: #fff; border: 1px solid #c8dbc8; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 20px rgba(26,92,56,0.08); }}
    .nl-header {{ background: #1a5c38; color: #fff; padding: 28px 40px 24px; }}
    .nl-header .kw {{ font-size: 10px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase; color: rgba(255,255,255,0.6); margin-bottom: 8px; }}
    .nl-header h1 {{ font-family: 'DM Serif Display', serif; font-weight: 400; font-size: 26px; line-height: 1.3; margin-bottom: 6px; }}
    .nl-header .meta {{ font-size: 12px; color: rgba(255,255,255,0.6); }}
    .nl-body {{ padding: 32px 40px 36px; }}
    .back {{ display: inline-block; margin-bottom: 24px; font-size: 13px; color: #1a5c38; text-decoration: none; }}
    .back:hover {{ text-decoration: underline; }}
    h3.nl-section {{ font-size: 12px; font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase; color: #1a5c38; margin: 24px 0 10px; padding-bottom: 6px; border-bottom: 1.5px solid #d4e4d4; }}
    h3.nl-section:first-of-type {{ margin-top: 0; }}
    ul.nl-list {{ list-style: none; margin: 0 0 12px; padding: 0; }}
    ul.nl-list li {{ font-size: 14px; line-height: 1.6; color: #2a2a2a; padding: 6px 0 6px 20px; border-bottom: 1px solid #f0f0f0; position: relative; }}
    ul.nl-list li:last-child {{ border-bottom: none; }}
    ul.nl-list li::before {{ content: "▸"; color: #1a5c38; position: absolute; left: 0; font-size: 12px; top: 7px; }}
    ul.nl-links li a {{ color: #1a5c38; text-decoration: none; font-weight: 600; }}
    ul.nl-links li a:hover {{ text-decoration: underline; }}
    .nl-meta {{ font-size: 11px; color: #999; margin-left: 6px; font-weight: 400; }}
    p {{ font-size: 14px; line-height: 1.7; color: #333; margin-bottom: 14px; }}
    .tags {{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: 28px; padding-top: 20px; border-top: 1px solid #e8e8e8; }}
    .tag {{ font-size: 11px; font-weight: 600; padding: 3px 9px; border-radius: 20px; color: #fff; }}
    .footer {{ margin-top: 20px; font-size: 11px; color: #bbb; text-align: center; }}
    @media (max-width: 600px) {{ .nl-header, .nl-body {{ padding-left: 20px; padding-right: 20px; }} }}
    @media print {{ body {{ background: #fff; padding: 0; }} .page {{ box-shadow: none; }} .back {{ display: none; }} }}
  </style>
</head>
<body>
  <div class="page">
    <div class="nl-header">
      <div class="kw">{kw_label}</div>
      <h1>Lärmschutz & Umgebungslärm<br>Newsletter</h1>
      <div class="meta">{subtitle} · {date_str}</div>
    </div>
    <div class="nl-body">
      <a class="back" href="index.html">← Zurück zur Übersicht</a>
{content}
{links_html}
      <div class="tags">
        <span class="tag" style="background:#1a5c38">🏞️ Steiermark</span>
        <span class="tag" style="background:#c8102e">🇦🇹 Österreich</span>
        <span class="tag" style="background:#5a5a5a">🏔️ DACH</span>
        <span class="tag" style="background:#003399">🇪🇺 Europa</span>
        <span class="tag" style="background:#1a6b3c">🔬 Wissenschaft</span>
        <span class="tag" style="background:#7b4f12">🏗️ Bauakustik</span>
      </div>
      <div class="footer">© Florian Lackner · Created using Claude.ai, powered by Anthropic Claude AI & GitHub Actions</div>
    </div>
  </div>
</body>
</html>"""


# ── Newsletter prompts ─────────────────────────────────────────────────────────

def weekly_newsletter_prompt(week_str, sections):
    return (
        f"Du bist ein Experte für Lärmschutz und Umgebungslärm. "
        f"Erstelle einen kompakten Newsletter für {week_str} auf Deutsch.\n\n"
        "Format (exakt einhalten, NUR Bullet Points):\n\n"
        "Key Takeaways:\n- [max. 12 Wörter]\n- [max. 12 Wörter]\n- [max. 12 Wörter]\n\n"
        "Steiermark:\n- [1–2 Bullet Points, je 1 Satz]\n\n"
        "Österreich:\n- [1–2 Bullet Points, je 1 Satz]\n\n"
        "DACH:\n- [1–2 Bullet Points, je 1 Satz]\n\n"
        "Europa:\n- [1–2 Bullet Points, je 1 Satz]\n\n"
        "Wissenschaft:\n- [1–2 Bullet Points, je 1 Satz]\n\n"
        "Bauakustik:\n- [1–2 Bullet Points, je 1 Satz]\n\n"
        "Regeln: NUR Bullet Points, kein Fließtext, keine Einleitung, keine Wiederholungen.\n\n"
        "Daten:\n" + "\n\n".join(sections)
    )


def monthly_newsletter_prompt(month_str, sections):
    return (
        f"Du bist ein Experte für Lärmschutz und Umgebungslärm. "
        f"Erstelle einen kompakten Monats-Newsletter für {month_str} auf Deutsch.\n\n"
        "Format (exakt einhalten, NUR Bullet Points):\n\n"
        "Key Takeaways des Monats:\n- [max. 12 Wörter]\n- [max. 12 Wörter]\n- [max. 12 Wörter]\n\n"
        "Steiermark:\n- [2–3 ausführliche Bullet Points]\n\n"
        "Österreich:\n- [2–3 ausführliche Bullet Points]\n\n"
        "DACH:\n- [2–3 ausführliche Bullet Points]\n\n"
        "Europa:\n- [2–3 ausführliche Bullet Points]\n\n"
        "Wissenschaft:\n- [2–3 ausführliche Bullet Points]\n\n"
        "Bauakustik:\n- [2–3 ausführliche Bullet Points]\n\n"
        "Regeln: NUR Bullet Points, kein Fließtext, keine Einleitung.\n\n"
        "Daten:\n" + "\n\n".join(sections)
    )


def _build_sections(categories_data):
    sections = []
    for cat_id, cat in categories_data.items():
        titles = "\n".join(f"- {i['title']}" for i in cat.get("items", [])[:10])
        sections.append(
            f"## {cat['icon']} {cat['label']}\n"
            f"Zusammenfassung: {cat.get('summary','')}\n\nSchlagzeilen:\n{titles}"
        )
    return sections


def _top_articles(categories_data, n=8):
    all_items = []
    for cat in categories_data.values():
        for item in cat.get("items", [])[:2]:
            if item.get("link"):
                all_items.append(item)
    return all_items[:n]


# ── Weekly Summary Only ────────────────────────────────────────────────────────

def run_weekly_summary_only():
    print("\n── Weekly Newsletter Only Mode (Claude Sonnet) ──")
    try:
        with open("docs/data.json", encoding="utf-8") as f:
            data = json.load(f)
        categories_data = data.get("categories", {})
    except Exception as e:
        print(f"  Could not read docs/data.json: {e}")
        return
    print(f"  Waiting {SUMMARY_PRE_PAUSE}s…")
    time.sleep(SUMMARY_PRE_PAUSE)
    now = datetime.now(timezone.utc)
    week_str = f"KW {now.strftime('%W')} / {now.year}"
    print("  Calling Claude Sonnet for weekly newsletter…")
    exec_text = generate_newsletter(weekly_newsletter_prompt(week_str, _build_sections(categories_data)))
    html = build_newsletter_html(
        title=f"Newsletter – {week_str}",
        kw_label=f"Wöchentlicher Newsletter · {week_str}",
        date_str=now.strftime("%d. %B %Y"),
        subtitle="Wochenrückblick",
        exec_text=exec_text,
        top_articles=_top_articles(categories_data),
    )
    os.makedirs("docs", exist_ok=True)
    with open("docs/summary.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("  ✅ docs/summary.html written.")


# ── Monthly Summary Only ───────────────────────────────────────────────────────

def run_monthly_summary_only():
    now = datetime.now(timezone.utc)
    month_str = now.strftime("%B %Y")
    month_slug = now.strftime("%Y-%m")
    print(f"\n── Monthly Newsletter Only Mode ({month_str}) ──")
    monthly_categories = {}
    for cat_id, cat in CATEGORIES.items():
        print(f"\n  ── {cat['label']} (30 days) ──")
        all_items = []
        for feed_url in cat["feeds"]:
            all_items.extend(fetch_rss(feed_url))
        all_items = apply_keyword_filter(all_items, cat.get("keyword_filter"))
        all_items = filter_by_age(all_items, MAX_AGE_DAYS_MONTHLY)
        items = deduplicate(all_items)[:30]
        print(f"  {len(items)} unique items in last 30 days")
        for item in items:
            item["date"] = format_date(item.pop("date_raw", ""))
            item.pop("date_parsed", None)
        print("  Calling Claude Haiku for category summary…")
        summary = summarize_monthly_category([i["title"] for i in items[:15]], cat["monthly_prompt"])
        print(f"  Summary: {summary[:80]}…")
        print(f"  Waiting {CLAUDE_PAUSE_SECONDS}s…")
        time.sleep(CLAUDE_PAUSE_SECONDS)
        monthly_categories[cat_id] = {
            "label": cat["label"], "icon": cat["icon"],
            "color": cat["color"], "summary": summary, "items": items,
        }
    print(f"\n  Waiting {SUMMARY_PRE_PAUSE}s before newsletter call…")
    time.sleep(SUMMARY_PRE_PAUSE)
    print("  Calling Claude Sonnet for monthly newsletter…")
    exec_text = generate_newsletter(monthly_newsletter_prompt(month_str, _build_sections(monthly_categories)))
    html = build_newsletter_html(
        title=f"Newsletter – {month_str}",
        kw_label=f"Monatlicher Newsletter · {month_str}",
        date_str=now.strftime("%d. %B %Y"),
        subtitle=f"Monatsrückblick {month_str}",
        exec_text=exec_text,
        top_articles=_top_articles(monthly_categories, n=10),
    )
    os.makedirs("docs", exist_ok=True)
    archived = f"docs/summary_monthly_{month_slug}.html"
    for path in [archived, "docs/summary_monthly.html"]:
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
    _update_monthly_archive(month_slug, month_str)
    print(f"  ✅ {archived} written.")


def _update_monthly_archive(new_slug, new_label):
    archive_path = "docs/monthly_archive.json"
    try:
        with open(archive_path, encoding="utf-8") as f:
            archive = json.load(f)
    except Exception:
        archive = []
    entry = {"slug": new_slug, "label": new_label, "file": f"summary_monthly_{new_slug}.html"}
    if not any(e["slug"] == new_slug for e in archive):
        archive.insert(0, entry)
        archive.sort(key=lambda x: x["slug"], reverse=True)
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)
    print(f"  ✅ monthly_archive.json updated ({len(archive)} entries).")


# ── Daily ──────────────────────────────────────────────────────────────────────

def run_daily():
    output = {
        "generated": datetime.now(timezone.utc).strftime("%d. %B %Y, %H:%M UTC"),
        "categories": {},
    }
    for cat_id, cat in CATEGORIES.items():
        print(f"\n── {cat['label']} ──")
        all_items = []
        for feed_url in cat["feeds"]:
            print(f"  Fetching: {feed_url[:80]}…")
            all_items.extend(fetch_rss(feed_url))
        all_items = apply_keyword_filter(all_items, cat.get("keyword_filter"))
        print(f"  {len(all_items)} total items before age filter")
        all_items = filter_by_age(all_items, MAX_AGE_DAYS_WEEKLY)
        items = deduplicate(all_items)[:MAX_ITEMS_PER_CATEGORY]
        print(f"  {len(items)} unique items after filter")
        for item in items:
            item["date"] = format_date(item.pop("date_raw", ""))
            item.pop("date_parsed", None)
        print("  Calling Claude Haiku…")
        summary = summarize_daily(
            [i["title"] for i in items[:MAX_TITLES_FOR_SUMMARY]], cat["summary_prompt"]
        )
        print(f"  Summary: {summary[:80]}…")
        print(f"  Waiting {CLAUDE_PAUSE_SECONDS}s…")
        time.sleep(CLAUDE_PAUSE_SECONDS)
        output["categories"][cat_id] = {
            "label": cat["label"], "icon": cat["icon"],
            "color": cat["color"], "summary": summary, "items": items,
        }
    os.makedirs("docs", exist_ok=True)
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("\n✅ docs/data.json written successfully.")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if WEEKLY_SUMMARY_ONLY:
        print("Mode: WEEKLY NEWSLETTER ONLY")
        run_weekly_summary_only()
    elif MONTHLY_SUMMARY_ONLY:
        print("Mode: MONTHLY NEWSLETTER ONLY")
        run_monthly_summary_only()
    else:
        print("Mode: DAILY NEWS UPDATE")
        run_daily()


if __name__ == "__main__":
    main()
