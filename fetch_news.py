"""
Lärmschutz News Fetcher
Fetches RSS feeds, filters by date, summarizes with Gemini, saves to docs/data.json

Schedule:
  - Daily news:           03:00 UTC  (≈ 05:00 Graz)
  - Weekly summary:       20:00 UTC Thursday  (≈ 22:00 Graz)
  - Monthly summary:      10:00 UTC last day of month  (≈ 12:00 Graz)
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

# Mode flags — set by GitHub Actions workflow via environment variables
GENERATE_WEEKLY  = os.environ.get("WEEKLY_SUMMARY",  "false").lower() == "true"
GENERATE_MONTHLY = os.environ.get("MONTHLY_SUMMARY", "false").lower() == "true"

# For monthly: only run if today is actually the last day of the month
def _is_last_day_of_month() -> bool:
    now = datetime.now(timezone.utc)
    tomorrow = now + timedelta(days=1)
    return tomorrow.day == 1

if GENERATE_MONTHLY and not _is_last_day_of_month():
    print("Monthly summary requested but today is not the last day of the month — skipping.")
    GENERATE_MONTHLY = False

MAX_ITEMS_FROM_FEED     = 100
MAX_AGE_DAYS            = 7
MAX_ITEMS_PER_CATEGORY  = 15
MAX_TITLES_FOR_SUMMARY  = 15
GEMINI_PAUSE_SECONDS    = 120
GEMINI_RETRY_ATTEMPTS   = 10
GEMINI_RETRY_WAIT       = 120
SUMMARY_PRE_PAUSE       = 180


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
            "Fasse die folgenden Nachrichtentitel aus der Steiermark zum Thema Lärm und Lärmschutz "
            "in 3 prägnanten deutschen Sätzen zusammen. "
            "Hebe die wichtigsten lokalen Entwicklungen hervor. "
            "Antworte NUR mit dem Fließtext, keine Aufzählungen, keine Überschriften."
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
            "Fasse die folgenden Nachrichtentitel aus Österreich zum Thema Lärmschutz "
            "in 3 prägnanten deutschen Sätzen zusammen. "
            "Hebe die wichtigsten Entwicklungen hervor. "
            "Antworte NUR mit dem Fließtext, keine Aufzählungen, keine Überschriften."
        ),
    },
    "dach": {
        "label": "DACH – Umgebungslärm",
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
            "Du bist Experte für Umgebungslärm in der DACH-Region (Deutschland, Österreich, Schweiz). "
            "Fasse die folgenden Nachrichtentitel zu den Themen Verkehrslärm, Fluglärm, Schienenlärm, "
            "Industrielärm und weiteren Lärmthemen in 3 prägnanten deutschen Sätzen zusammen. "
            "Hebe die wichtigsten regionalen Entwicklungen hervor. "
            "Antworte NUR mit dem Fließtext, keine Aufzählungen, keine Überschriften."
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
            "Summarize the following European news headlines about noise control "
            "in 3 concise sentences in English. "
            "Focus on significant EU-level or cross-border developments. "
            "Reply ONLY with flowing prose, no bullet points, no headings."
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
            "Summarize the following scientific news headlines about noise control research "
            "in 3 concise sentences in English. "
            "Focus on practical implications for noise control engineers. "
            "Reply ONLY with flowing prose, no bullet points, no headings."
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
                    "title": title,
                    "link": link,
                    "date_raw": pub,
                    "date_parsed": parse_pub_date(pub),
                    "source": source,
                })
    except Exception as e:
        print(f"  Warning: could not fetch {url[:70]}: {e}")
    return items


def filter_by_age(items: list[dict], max_age_days: int) -> list[dict]:
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


def deduplicate(items: list[dict]) -> list[dict]:
    seen, result = set(), []
    for item in items:
        key = re.sub(r"\s+", " ", item["title"].lower().strip())
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def format_date(raw: str) -> str:
    if not raw:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(raw)
        return dt.strftime("%-d. %b %Y")
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
            req = Request(
                GEMINI_URL,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=30) as resp:
                data = _json.loads(resp.read())
            finish_reason = data["candidates"][0].get("finishReason", "unknown")
            print(f"  Finish reason: {finish_reason}")
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()

        except HTTPError as e:
            if e.code == 429:
                if attempt < GEMINI_RETRY_ATTEMPTS:
                    print(f"  Gemini 429 (attempt {attempt}/{GEMINI_RETRY_ATTEMPTS}) – waiting {GEMINI_RETRY_WAIT}s…")
                    time.sleep(GEMINI_RETRY_WAIT)
                else:
                    print(f"  Gemini 429 – all {GEMINI_RETRY_ATTEMPTS} attempts exhausted.")
                    return "Zusammenfassung konnte nicht erstellt werden (Rate Limit)."
            else:
                print(f"  Gemini HTTP error {e.code}: {e}")
                return "Zusammenfassung konnte nicht erstellt werden."
        except Exception as e:
            print(f"  Gemini error: {e}")
            return "Zusammenfassung konnte nicht erstellt werden."

    return "Zusammenfassung konnte nicht erstellt werden."


def summarize_with_gemini(titles: list[str], prompt: str) -> str:
    if not titles:
        return "Keine aktuellen Meldungen der letzten 7 Tage gefunden."
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    return call_gemini(prompt + "\n\nNachrichtentitel:\n" + numbered, max_tokens=2000)


# ── HTML Summary Builder ───────────────────────────────────────────────────────

def build_summary_html(title: str, kw_label: str, date_str: str, subtitle: str, exec_text: str) -> str:
    paragraphs = [p.strip() for p in exec_text.split("\n") if p.strip()]
    html_paragraphs = "\n".join(f"    <p>{p}</p>" for p in paragraphs)
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
    .page {{ max-width: 740px; margin: 0 auto; background: #fff; border: 1px solid #c8dbc8; border-radius: 10px; padding: 52px 60px; box-shadow: 0 2px 20px rgba(26,92,56,0.08); }}
    .back {{ display: inline-block; margin-bottom: 32px; font-size: 13px; color: #1a5c38; text-decoration: none; }}
    .back:hover {{ color: #333; }}
    .kw {{ font-size: 11px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; color: #1a5c38; margin-bottom: 10px; }}
    h1 {{ font-family: 'DM Serif Display', serif; font-weight: 400; font-size: 28px; line-height: 1.3; margin-bottom: 6px; }}
    .meta {{ font-size: 13px; color: #999; margin-bottom: 36px; padding-bottom: 24px; border-bottom: 2px solid #1a5c38; }}
    p {{ font-size: 15px; line-height: 1.75; color: #2a2a2a; margin-bottom: 18px; }}
    p:first-of-type::first-letter {{ font-family: 'DM Serif Display', serif; font-size: 52px; line-height: 0.85; float: left; margin-right: 8px; margin-top: 6px; color: #1a5c38; }}
    .tags {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 36px; padding-top: 24px; border-top: 1px solid #e0e0e0; }}
    .tag {{ font-size: 11px; font-weight: 600; padding: 4px 10px; border-radius: 20px; color: #fff; }}
    .footer {{ margin-top: 32px; font-size: 11px; color: #bbb; text-align: center; }}
    @media (max-width: 600px) {{ .page {{ padding: 32px 24px; }} h1 {{ font-size: 22px; }} }}
    @media print {{ body {{ background: #fff; padding: 0; }} .page {{ box-shadow: none; border: none; }} .back {{ display: none; }} }}
  </style>
</head>
<body>
  <div class="page">
    <a class="back" href="index.html">← Zurück zur Übersicht</a>
    <div class="kw">{kw_label}</div>
    <h1>Lärmschutz & Umgebungslärm<br>im Überblick</h1>
    <div class="meta">{subtitle} · Erstellt am {date_str}</div>
{html_paragraphs}
    <div class="tags">
      <span class="tag" style="background:#1a5c38">🏞️ Steiermark</span>
      <span class="tag" style="background:#c8102e">🇦🇹 Österreich</span>
      <span class="tag" style="background:#5a5a5a">🏔️ DACH</span>
      <span class="tag" style="background:#003399">🇪🇺 Europa</span>
      <span class="tag" style="background:#1a6b3c">🔬 Wissenschaft</span>
    </div>
    <div class="footer">© Florian Lackner · Created using Claude.ai, powered by Google Gemini AI & GitHub Actions</div>
  </div>
</body>
</html>"""


# ── Weekly Executive Summary ───────────────────────────────────────────────────

def generate_weekly_summary(categories_data: dict) -> None:
    print("\n── Generating Weekly Executive Summary ──")
    print(f"  Waiting {SUMMARY_PRE_PAUSE}s for rate limit recovery…")
    time.sleep(SUMMARY_PRE_PAUSE)

    sections = _build_sections(categories_data)
    exec_prompt = (
        "Du bist ein Experte für Lärmschutz und Umgebungslärm. "
        "Erstelle einen wöchentlichen Executive Summary auf Deutsch.\n\n"
        "Struktur:\n"
        "1. Einleitender Gesamtüberblick (3 Sätze).\n"
        "2. Je ein Absatz pro Kategorie (Steiermark, Österreich, DACH, Europa, Wissenschaft).\n"
        "Analysiere Trends und Fachdetails. Schreibe insgesamt ca. 300 Wörter.\n"
        "NUR Fließtext, keine Aufzählungen, keine Markdown-Formatierung.\n\n"
        "Daten:\n" + "\n\n".join(sections)
    )

    print("  Calling Gemini for weekly summary…")
    exec_text = call_gemini(exec_prompt, max_tokens=1500)

    now = datetime.now(timezone.utc)
    week_str = f"KW {now.strftime('%W')} / {now.year}"
    date_str = now.strftime("%d. %B %Y")

    html = build_summary_html(
        title=f"Wöchentlicher Executive Summary – {week_str}",
        kw_label=f"Wöchentlicher Executive Summary · {week_str}",
        date_str=date_str,
        subtitle="Wochenrückblick",
        exec_text=exec_text,
    )

    os.makedirs("docs", exist_ok=True)
    with open("docs/summary.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("  ✅ docs/summary.html written.")


# ── Monthly Executive Summary ──────────────────────────────────────────────────

def generate_monthly_summary(categories_data: dict) -> None:
    now = datetime.now(timezone.utc)
    month_str = now.strftime("%B %Y")
    print(f"\n── Generating Monthly Executive Summary ({month_str}) ──")
    print(f"  Waiting {SUMMARY_PRE_PAUSE}s for rate limit recovery…")
    time.sleep(SUMMARY_PRE_PAUSE)

    sections = _build_sections(categories_data)
    exec_prompt = (
        "Du bist ein Experte für Lärmschutz und Umgebungslärm. "
        f"Erstelle einen monatlichen Executive Summary für {month_str} auf Deutsch.\n\n"
        "Struktur:\n"
        "1. Gesamtüberblick des Monats (3–4 Sätze): wichtigste Themen, übergeordnete Trends.\n"
        "2. Je ein Absatz pro Kategorie (Steiermark, Österreich, DACH, Europa, Wissenschaft): "
        "die bedeutendsten Entwicklungen des Monats.\n"
        "3. Abschließender Ausblick: was im nächsten Monat relevant sein könnte (2 Sätze).\n"
        "Schreibe insgesamt ca. 500 Wörter. NUR Fließtext, keine Aufzählungen, keine Markdown.\n\n"
        "Daten:\n" + "\n\n".join(sections)
    )

    print("  Calling Gemini for monthly summary…")
    exec_text = call_gemini(exec_prompt, max_tokens=2500)

    date_str = now.strftime("%d. %B %Y")

    html = build_summary_html(
        title=f"Monatlicher Executive Summary – {month_str}",
        kw_label=f"Monatlicher Executive Summary · {month_str}",
        date_str=date_str,
        subtitle=f"Monatsrückblick {month_str}",
        exec_text=exec_text,
    )

    os.makedirs("docs", exist_ok=True)
    with open("docs/summary_monthly.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("  ✅ docs/summary_monthly.html written.")


def _build_sections(categories_data: dict) -> list[str]:
    sections = []
    for cat_id, cat in categories_data.items():
        summary = cat.get("summary", "")
        items = cat.get("items", [])
        titles = "\n".join(f"- {i['title']}" for i in items[:8])
        sections.append(
            f"## {cat['icon']} {cat['label']}\n"
            f"Zusammenfassung: {summary}\n\nSchlagzeilen:\n{titles}"
        )
    return sections


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    mode = []
    if GENERATE_WEEKLY:  mode.append("weekly summary")
    if GENERATE_MONTHLY: mode.append("monthly summary")
    print(f"Mode: daily news" + (f" + {', '.join(mode)}" if mode else ""))

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
        all_items = filter_by_age(all_items, MAX_AGE_DAYS)
        items = deduplicate(all_items)[:MAX_ITEMS_PER_CATEGORY]
        print(f"  {len(items)} unique items after date filter")

        for item in items:
            item["date"] = format_date(item.pop("date_raw", ""))
            item.pop("date_parsed", None)

        print("  Calling Gemini…")
        titles_for_summary = [i["title"] for i in items[:MAX_TITLES_FOR_SUMMARY]]
        summary = summarize_with_gemini(titles_for_summary, cat["summary_prompt"])
        print(f"  Summary: {summary[:80]}…")
        print(f"  Waiting {GEMINI_PAUSE_SECONDS}s…")
        time.sleep(GEMINI_PAUSE_SECONDS)

        output["categories"][cat_id] = {
            "label": cat["label"],
            "icon": cat["icon"],
            "color": cat["color"],
            "summary": summary,
            "items": items,
        }

    os.makedirs("docs", exist_ok=True)
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("\n✅ docs/data.json written successfully.")

    if GENERATE_WEEKLY:
        generate_weekly_summary(output["categories"])

    if GENERATE_MONTHLY:
        generate_monthly_summary(output["categories"])


if __name__ == "__main__":
    main()
