"""
Lärmschutz News Fetcher

Modes:
  - Daily:          fetch 7-day news, update data.json
  - Weekly summary: read data.json, generate summary.html (newsletter format)
  - Monthly summary: fetch 30-day news, generate summary_monthly_YYYY-MM.html (newsletter format)
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

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
)

WEEKLY_SUMMARY_ONLY  = os.environ.get("WEEKLY_SUMMARY",  "false").lower() == "true"
MONTHLY_SUMMARY_ONLY = os.environ.get("MONTHLY_SUMMARY", "false").lower() == "true"

def _is_last_day_of_month() -> bool:
    return (datetime.now(timezone.utc) + timedelta(days=1)).day == 1

#if MONTHLY_SUMMARY_ONLY and not _is_last_day_of_month():
#    print("Monthly summary requested but today is not the last day of the month — skipping.")
#    MONTHLY_SUMMARY_ONLY = False

MAX_ITEMS_FROM_FEED    = 100
MAX_AGE_DAYS_WEEKLY    = 7
MAX_AGE_DAYS_MONTHLY   = 31
MAX_ITEMS_PER_CATEGORY = 15
MAX_TITLES_FOR_SUMMARY = 15
GEMINI_PAUSE_SECONDS   = 120
GEMINI_RETRY_ATTEMPTS  = 10
GEMINI_RETRY_WAIT      = 120
SUMMARY_PRE_PAUSE      = 30


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
        "summary_prompt": (
            "Du bist Experte für Lärmschutz in der Steiermark und Graz. "
            "Fasse die folgenden Nachrichtentitel in 3 prägnanten deutschen Sätzen zusammen. "
            "Antworte NUR mit dem Fließtext, keine Aufzählungen, keine Überschriften."
        ),
        "monthly_prompt": (
            "Du bist Experte für Lärmschutz in der Steiermark. "
            "Fasse die wichtigsten Entwicklungen des letzten Monats in 3–4 Sätzen zusammen. "
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
        ],
        "summary_prompt": (
            "Du bist Experte für Lärmschutz in Österreich. "
            "Fasse die folgenden Nachrichtentitel in 3 prägnanten deutschen Sätzen zusammen. "
            "Antworte NUR mit Fließtext."
        ),
        "monthly_prompt": (
            "Du bist Experte für Lärmschutz in Österreich. "
            "Fasse die wichtigsten Entwicklungen des letzten Monats in 3–4 Sätzen zusammen. "
            "Antworte NUR mit Fließtext."
        ),
    },
    "dach": {
        "label": "DACH",
        "icon": "🏔️",
        "color": "#5a5a5a",
        "feeds": [
            gnews("Verkehrslärm Deutschland Österreich Schweiz", country="DE"),
            gnews("Umgebungslärm Deutschland", country="DE"),
            gnews("Fluglärm Deutschland", country="DE"),
            gnews("Fluglärm Schweiz", country="DE"),
            gnews("Schienenlärm Bahn Deutschland", country="DE"),
            gnews("Industrielärm Deutschland", country="DE"),
            gnews("Lärmkarte Lärmkartierung Deutschland", country="DE"),
            gnews("Ruhige Gebiete Lärmschutz Deutschland", country="DE"),
            gnews("Infraschall Deutschland Österreich", country="DE"),
            gnews("tieffrequenter Schall DACH", country="DE"),
            gnews("Brummton Deutschland Schweiz", country="DE"),
            gnews("Lärmbekämpfung DACH", country="DE"),
            gnews("Raumordnung Lärm Deutschland", country="DE"),
        ],
        "summary_prompt": (
            "Du bist Experte für Umgebungslärm in der DACH-Region. "
            "Fasse die folgenden Nachrichtentitel in 3 prägnanten deutschen Sätzen zusammen. "
            "Antworte NUR mit Fließtext."
        ),
        "monthly_prompt": (
            "Du bist Experte für Umgebungslärm in der DACH-Region. "
            "Fasse die wichtigsten Entwicklungen des letzten Monats in 3–4 Sätzen zusammen. "
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
        "summary_prompt": (
            "You are an expert on European noise control policy. "
            "Summarize the following headlines in 3 concise sentences in English. "
            "Reply ONLY with flowing prose."
        ),
        "monthly_prompt": (
            "You are an expert on European noise control policy. "
            "Summarize the most significant developments of the past month in 3–4 sentences. "
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
        "summary_prompt": (
            "You are an acoustics researcher. "
            "Summarize the following headlines in 3 concise sentences in English. "
            "Reply ONLY with flowing prose."
        ),
        "monthly_prompt": (
            "You are an acoustics researcher. "
            "Summarize the most significant research developments of the past month in 3–4 sentences. "
            "Reply ONLY with flowing prose."
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
        return None


def fetch_rss(url: str) -> list[dict]:
    items = []
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"})
        with urlopen(req, timeout=30) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        channel = root.find("channel")
        if channel is None:
            return items
        for item in channel.findall("item")[:MAX_ITEMS_FROM_FEED]:
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link")  or "").strip()
            pub   = (item.findtext("pubDate") or "").strip()
            source_el = item.find("source")
            source = source_el.text.strip() if source_el is not None else ""
            if title:
                items.append({
                    "title": title, "link": link,
                    "date_raw": pub, "date_parsed": parse_pub_date(pub), "source": source,
                })
    except Exception as e:
        print(f"  Warning: could not fetch {url[:70]}: {e}")
    return items


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
        return raw[:16]


# ── Gemini with retry ──────────────────────────────────────────────────────────

def call_gemini(prompt: str, max_tokens: int = 2000) -> str:
    import json as _json
    body = _json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
    }).encode()
    for attempt in range(1, GEMINI_RETRY_ATTEMPTS + 1):
        try:
            req = Request(GEMINI_URL, data=body,
                          headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(req, timeout=30) as resp:
                data = _json.loads(resp.read())
            print(f"  Finish reason: {data['candidates'][0].get('finishReason','unknown')}")
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except HTTPError as e:
            if e.code == 429:
                if attempt < GEMINI_RETRY_ATTEMPTS:
                    print(f"  Gemini 429 (attempt {attempt}/{GEMINI_RETRY_ATTEMPTS}) – waiting {GEMINI_RETRY_WAIT}s…")
                    time.sleep(GEMINI_RETRY_WAIT)
                else:
                    return "Zusammenfassung konnte nicht erstellt werden (Rate Limit)."
            else:
                print(f"  Gemini HTTP error {e.code}")
                return "Zusammenfassung konnte nicht erstellt werden."
        except Exception as e:
            print(f"  Gemini error: {e}")
            return "Zusammenfassung konnte nicht erstellt werden."
    return "Zusammenfassung konnte nicht erstellt werden."


def summarize_with_gemini(titles, prompt):
    if not titles:
        return "Keine aktuellen Meldungen gefunden."
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    return call_gemini(prompt + "\n\nNachrichtentitel:\n" + numbered, max_tokens=2000)


# ── Newsletter HTML Builder ────────────────────────────────────────────────────

def render_newsletter_text(raw_text: str) -> str:
    """Convert Gemini's bullet-point text to styled HTML."""
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

        # Detect section headers (lines ending with : or starting with **)
        if re.match(r"^(\*\*)?[A-ZÄÖÜ&][^.!?]{0,40}:(\*\*)?$", line):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            clean = re.sub(r"\*\*", "", line).rstrip(":")
            html_lines.append(f'<h3 class="nl-section">{clean}</h3>')

        # Detect bullet points (-, •, *, numbers)
        elif re.match(r"^[-•*]\s+|^\d+\.\s+", line):
            if not in_list:
                html_lines.append('<ul class="nl-list">')
                in_list = True
            text = re.sub(r"^[-•*]\s+|^\d+\.\s+", "", line)
            text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)
            html_lines.append(f"<li>{text}</li>")

        # Regular paragraph
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", line)
            html_lines.append(f"<p>{text}</p>")

    if in_list:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


def build_newsletter_html(title: str, kw_label: str, date_str: str, subtitle: str, exec_text: str) -> str:
    content = render_newsletter_text(exec_text)
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

    /* Newsletter header band */
    .nl-header {{
      background: #1a5c38;
      color: #fff;
      padding: 28px 40px 24px;
    }}
    .nl-header .kw {{
      font-size: 10px; font-weight: 700; letter-spacing: 2px;
      text-transform: uppercase; color: rgba(255,255,255,0.6); margin-bottom: 8px;
    }}
    .nl-header h1 {{
      font-family: 'DM Serif Display', serif; font-weight: 400;
      font-size: 26px; line-height: 1.3; margin-bottom: 6px;
    }}
    .nl-header .meta {{ font-size: 12px; color: rgba(255,255,255,0.6); }}

    /* Body */
    .nl-body {{ padding: 32px 40px 36px; }}
    .back {{ display: inline-block; margin-bottom: 24px; font-size: 13px; color: #1a5c38; text-decoration: none; }}
    .back:hover {{ text-decoration: underline; }}

    /* Section headers */
    h3.nl-section {{
      font-size: 12px; font-weight: 700; letter-spacing: 1.2px;
      text-transform: uppercase; color: #1a5c38;
      margin: 24px 0 10px;
      padding-bottom: 6px;
      border-bottom: 1.5px solid #d4e4d4;
    }}
    h3.nl-section:first-child {{ margin-top: 0; }}

    /* Bullet lists */
    ul.nl-list {{
      list-style: none;
      margin: 0 0 12px 0;
      padding: 0;
    }}
    ul.nl-list li {{
      font-size: 14px;
      line-height: 1.6;
      color: #2a2a2a;
      padding: 6px 0 6px 20px;
      border-bottom: 1px solid #f0f0f0;
      position: relative;
    }}
    ul.nl-list li:last-child {{ border-bottom: none; }}
    ul.nl-list li::before {{
      content: "▸";
      color: #1a5c38;
      position: absolute;
      left: 0;
      font-size: 12px;
      top: 7px;
    }}

    /* Paragraphs */
    p {{ font-size: 14px; line-height: 1.7; color: #333; margin-bottom: 14px; }}

    /* Tags */
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
      <h1>Lärmschutz & Umgebungslärm<br>Executive Newsletter</h1>
      <div class="meta">{subtitle} · {date_str}</div>
    </div>
    <div class="nl-body">
      <a class="back" href="index.html">← Zurück zur Übersicht</a>
{content}
      <div class="tags">
        <span class="tag" style="background:#1a5c38">🏞️ Steiermark</span>
        <span class="tag" style="background:#c8102e">🇦🇹 Österreich</span>
        <span class="tag" style="background:#5a5a5a">🏔️ DACH</span>
        <span class="tag" style="background:#003399">🇪🇺 Europa</span>
        <span class="tag" style="background:#1a6b3c">🔬 Wissenschaft</span>
      </div>
      <div class="footer">© Florian Lackner · Created using Claude.ai, powered by Google Gemini AI & GitHub Actions</div>
    </div>
  </div>
</body>
</html>"""


# ── Newsletter prompt ──────────────────────────────────────────────────────────

def newsletter_prompt(period_str: str, period_type: str, sections: list[str]) -> str:
    return (
        f"Du bist ein Experte für Lärmschutz und Umgebungslärm. "
        f"Erstelle einen kompakten Executive Newsletter für {period_str} auf Deutsch.\n\n"
        "Format (exakt einhalten):\n"
        "Key Takeaways:\n"
        "- [max. 12 Wörter]\n"
        "- [max. 12 Wörter]\n"
        "- [max. 12 Wörter]\n\n"
        "Top-Themen:\n"
        "- [1 kurzer Satz je Thema, 3–5 Punkte]\n\n"
        "Steiermark:\n"
        "- [1–2 Bullet Points]\n\n"
        "Österreich:\n"
        "- [1–2 Bullet Points]\n\n"
        "DACH:\n"
        "- [1–2 Bullet Points]\n\n"
        "Europa:\n"
        "- [1–2 Bullet Points]\n\n"
        "Wissenschaft:\n"
        "- [1–2 Bullet Points]\n\n"
        "Risiken & Trends:\n"
        "- [2–3 Bullet Points]\n\n"
        "Ausblick:\n"
        "- [1–2 Bullet Points]\n\n"
        "Regeln:\n"
        "- NUR Bullet Points, kein Fließtext\n"
        "- Fokus auf wichtigste Erkenntnisse\n"
        "- Keine Einleitung, keine Wiederholungen\n"
        "- Ignoriere unwichtige Details\n\n"
        "Daten:\n" + "\n\n".join(sections)
    )


def _build_sections(categories_data: dict) -> list[str]:
    sections = []
    for cat_id, cat in categories_data.items():
        titles = "\n".join(f"- {i['title']}" for i in cat.get("items", [])[:10])
        sections.append(
            f"## {cat['icon']} {cat['label']}\n"
            f"Zusammenfassung: {cat.get('summary','')}\n\nSchlagzeilen:\n{titles}"
        )
    return sections


# ── Weekly Summary Only ────────────────────────────────────────────────────────

def run_weekly_summary_only() -> None:
    print("\n── Weekly Newsletter Only Mode ──")
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
    sections = _build_sections(categories_data)

    print("  Calling Gemini for weekly newsletter…")
    exec_text = call_gemini(newsletter_prompt(week_str, "weekly", sections), max_tokens=1500)

    html = build_newsletter_html(
        title=f"Executive Newsletter – {week_str}",
        kw_label=f"Wöchentlicher Executive Newsletter · {week_str}",
        date_str=now.strftime("%d. %B %Y"),
        subtitle="Wochenrückblick",
        exec_text=exec_text,
    )
    os.makedirs("docs", exist_ok=True)
    with open("docs/summary.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("  ✅ docs/summary.html written.")


# ── Monthly Summary Only ───────────────────────────────────────────────────────

def run_monthly_summary_only() -> None:
    now = datetime.now(timezone.utc)
    month_str = now.strftime("%B %Y")
    month_slug = now.strftime("%Y-%m")
    print(f"\n── Monthly Newsletter Only Mode ({month_str}) ──")

    # Fetch 30-day data
    monthly_categories = {}
    for cat_id, cat in CATEGORIES.items():
        print(f"\n  ── {cat['label']} (30 days) ──")
        all_items = []
        for feed_url in cat["feeds"]:
            all_items.extend(fetch_rss(feed_url))

        all_items = filter_by_age(all_items, MAX_AGE_DAYS_MONTHLY)
        items = deduplicate(all_items)[:30]
        print(f"  {len(items)} unique items in last 30 days")

        for item in items:
            item["date"] = format_date(item.pop("date_raw", ""))
            item.pop("date_parsed", None)

        print("  Calling Gemini for category summary…")
        summary = summarize_with_gemini([i["title"] for i in items[:20]], cat["monthly_prompt"])
        print(f"  Summary: {summary[:80]}…")
        print(f"  Waiting {GEMINI_PAUSE_SECONDS}s…")
        time.sleep(GEMINI_PAUSE_SECONDS)

        monthly_categories[cat_id] = {
            "label": cat["label"], "icon": cat["icon"],
            "color": cat["color"], "summary": summary, "items": items,
        }

    print(f"\n  Waiting {SUMMARY_PRE_PAUSE}s before executive newsletter call…")
    time.sleep(SUMMARY_PRE_PAUSE)

    sections = _build_sections(monthly_categories)
    print("  Calling Gemini for monthly newsletter…")
    exec_text = call_gemini(newsletter_prompt(month_str, "monthly", sections), max_tokens=2000)

    html = build_newsletter_html(
        title=f"Executive Newsletter – {month_str}",
        kw_label=f"Monatlicher Executive Newsletter · {month_str}",
        date_str=now.strftime("%d. %B %Y"),
        subtitle=f"Monatsrückblick {month_str}",
        exec_text=exec_text,
    )

    os.makedirs("docs", exist_ok=True)

    # Save with month slug for archive AND overwrite the latest
    archived_path = f"docs/summary_monthly_{month_slug}.html"
    with open(archived_path, "w", encoding="utf-8") as f:
        f.write(html)
    with open("docs/summary_monthly.html", "w", encoding="utf-8") as f:
        f.write(html)

    # Update archive index
    _update_monthly_archive(month_slug, month_str)

    print(f"  ✅ docs/summary_monthly_{month_slug}.html written.")
    print(f"  ✅ docs/summary_monthly.html updated.")


def _update_monthly_archive(new_slug: str, new_label: str) -> None:
    """Maintain a JSON index of all monthly summaries."""
    archive_path = "docs/monthly_archive.json"
    try:
        with open(archive_path, encoding="utf-8") as f:
            archive = json.load(f)
    except Exception:
        archive = []

    # Add entry if not already present
    entry = {"slug": new_slug, "label": new_label, "file": f"summary_monthly_{new_slug}.html"}
    if not any(e["slug"] == new_slug for e in archive):
        archive.insert(0, entry)  # newest first
        archive.sort(key=lambda x: x["slug"], reverse=True)

    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)
    print(f"  ✅ docs/monthly_archive.json updated ({len(archive)} entries).")


# ── Daily ──────────────────────────────────────────────────────────────────────

def run_daily() -> None:
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

        print(f"  {len(all_items)} total items before filtering")
        all_items = filter_by_age(all_items, MAX_AGE_DAYS_WEEKLY)
        items = deduplicate(all_items)[:MAX_ITEMS_PER_CATEGORY]
        print(f"  {len(items)} unique items after filter")

        for item in items:
            item["date"] = format_date(item.pop("date_raw", ""))
            item.pop("date_parsed", None)

        print("  Calling Gemini…")
        summary = summarize_with_gemini(
            [i["title"] for i in items[:MAX_TITLES_FOR_SUMMARY]], cat["summary_prompt"]
        )
        print(f"  Summary: {summary[:80]}…")
        print(f"  Waiting {GEMINI_PAUSE_SECONDS}s…")
        time.sleep(GEMINI_PAUSE_SECONDS)

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
