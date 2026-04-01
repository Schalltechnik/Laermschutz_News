"""
Lärmschutz News Fetcher
Fetches RSS feeds, summarizes with Gemini, saves to docs/data.json
Optionally generates a weekly executive summary (docs/summary.html)
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.request import urlopen, Request
import xml.etree.ElementTree as ET

# ── Configuration ──────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
)

GENERATE_SUMMARY = os.environ.get("WEEKLY_SUMMARY", "false").lower() == "true"

from datetime import datetime, timedelta

# Berechnet das Datum von vor 7 Tagen im Format YYYY-MM-DD
date_filter = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

CATEGORIES = {
    "steiermark": {
        "label": "Steiermark",
        "icon": "🏞️",
        "color": "#2e7d32",
        "feeds": [
        f"https://news.google.com/rss/search?q=L%C3%A4rmschutz+Steiermark+after:{date_filter}&hl=de&gl=AT&ceid=AT:de",
        f"https://news.google.com/rss/search?q=Verkehrsl%C3%A4rm+Steiermark+after:{date_filter}&hl=de&gl=AT&ceid=AT:de",
        f"https://news.google.com/rss/search?q=Umgebungsl%C3%A4rm+Steiermark+after:{date_filter}&hl=de&gl=AT&ceid=AT:de",
        f"https://news.google.com/rss/search?q=Flugl%C3%A4rm+Graz+after:{date_filter}&hl=de&gl=AT&ceid=AT:de",
        f"https://news.google.com/rss/search?q=L%C3%A4rm+Graz+Steiermark+after:{date_filter}&hl=de&gl=AT&ceid=AT:de",
        ],
        
        
        "feeds": [
            "https://news.google.com/rss/search?q=L%C3%A4rmschutz+Steiermark+when:7d&hl=de&gl=AT&ceid=AT:de",
            "https://news.google.com/rss/search?q=Verkehrsl%C3%A4rm+Steiermark+when:7d&hl=de&gl=AT&ceid=AT:de",
            "https://news.google.com/rss/search?q=Umgebungsl%C3%A4rm+Steiermark&hl+when:7d&hl=de&gl=AT&ceid=AT:de",
            "https://news.google.com/rss/search?q=Flugl%C3%A4rm+Graz&hl=de&gl+when:7d&hl=de&gl=AT&ceid=AT:de",
            "https://news.google.com/rss/search?q=L%C3%A4rm+Graz+Steiermark&hl+when:7d&hl=de&gl=AT&ceid=AT:de",
        ],
        "summary_prompt": (
            "Du bist Experte für Lärmschutz in der Steiermark und Graz. "
            "Fasse die folgenden Nachrichtentitel aus der Steiermark zum Thema Lärm und Lärmschutz "
            "in 3–5 prägnanten deutschen Sätzen zusammen. "
            "Hebe die wichtigsten lokalen Entwicklungen hervor. "
            "Antworte NUR mit dem Fließtext, keine Aufzählungen, keine Überschriften."
        ),
    },
    "austria": {
        "label": "Österreich",
        "icon": "🇦🇹",
        "color": "#c8102e",
        "feeds": [
            "https://news.google.com/rss/search?q=L%C3%A4rmschutz+%C3%96sterreich&hl=de&gl=AT&ceid=AT:de&when=7d",
            "https://news.google.com/rss/search?q=L%C3%A4rmschutzwand+%C3%96sterreich&hl=de&gl=AT&ceid=AT:de&when=7d",
            "https://news.google.com/rss/search?q=L%C3%A4rm+%C3%96sterreich+Verordnung&hl=de&gl=AT&ceid=AT:de&when=7d",
            "https://news.google.com/rss/search?q=Verkehrsl%C3%A4rm+%C3%96sterreich&hl=de&gl=AT&ceid=AT:de&when=7d",
        ],
        "summary_prompt": (
            "Du bist Experte für Lärmschutz in Österreich. "
            "Fasse die folgenden Nachrichtentitel aus Österreich zum Thema Lärmschutz "
            "in 3–5 prägnanten deutschen Sätzen zusammen. "
            "Hebe die wichtigsten Entwicklungen hervor. "
            "Antworte NUR mit dem Fließtext, keine Aufzählungen, keine Überschriften."
        ),
    },
    "dach": {
        "label": "DACH – Umgebungslärm",
        "icon": "🏔️",
        "color": "#5a5a5a",
        "feeds": [
            "https://news.google.com/rss/search?q=Verkehrsl%C3%A4rm+Deutschland+%C3%96sterreich+Schweiz&hl=de&gl=DE&ceid=DE:de&when=7d",
            "https://news.google.com/rss/search?q=Flugl%C3%A4rm+Deutschland&hl=de&gl=DE&ceid=DE:de&when=7d",
            "https://news.google.com/rss/search?q=Flugl%C3%A4rm+%C3%96sterreich+Schweiz&hl=de&gl=AT&ceid=AT:de&when=7d",
            "https://news.google.com/rss/search?q=Schienenl%C3%A4rm+Bahn+Deutschland&hl=de&gl=DE&ceid=DE:de&when=7d",
            "https://news.google.com/rss/search?q=Industriel%C3%A4rm+Umgebungsl%C3%A4rm&hl=de&gl=DE&ceid=DE:de&when=7d",
            "https://news.google.com/rss/search?q=Umgebungsl%C3%A4rm+L%C3%A4rmkarte+L%C3%A4rmbericht&hl=de&gl=DE&ceid=DE:de&when=7d",
        ],
        "summary_prompt": (
            "Du bist Experte für Umgebungslärm in der DACH-Region (Deutschland, Österreich, Schweiz). "
            "Fasse die folgenden Nachrichtentitel zu den Themen Verkehrslärm, Fluglärm, Schienenlärm "
            "und Industrielärm in 3–5 prägnanten deutschen Sätzen zusammen. "
            "Hebe die wichtigsten regionalen Entwicklungen hervor. "
            "Antworte NUR mit dem Fließtext, keine Aufzählungen, keine Überschriften."
        ),
    },
    "europe": {
        "label": "Europa",
        "icon": "🇪🇺",
        "color": "#003399",
        "feeds": [
            "https://news.google.com/rss/search?q=noise+control+EU+directive&hl=en&gl=GB&ceid=GB:en&when=7d",
            "https://news.google.com/rss/search?q=environmental+noise+Europe+regulation&hl=en&gl=GB&ceid=GB:en&when=7d",
            "https://news.google.com/rss/search?q=L%C3%A4rmschutz+Europa+EU&hl=de&gl=DE&ceid=DE:de&when=7d",
        ],
        "summary_prompt": (
            "You are an expert on European noise control policy. "
            "Summarize the following European news headlines about noise control "
            "in 3–5 concise sentences in English. "
            "Focus on significant EU-level or cross-border developments. "
            "Reply ONLY with flowing prose, no bullet points, no headings."
        ),
    },
    "science": {
        "label": "Wissenschaft",
        "icon": "🔬",
        "color": "#1a6b3c",
        "feeds": [
            "https://news.google.com/rss/search?q=acoustics+noise+control+research&hl=en&gl=GB&ceid=GB:en&when=7d",
            "https://news.google.com/rss/search?q=noise+barrier+material+research&hl=en&gl=GB&ceid=GB:en&when=7d",
            "https://news.google.com/rss/search?q=urban+noise+acoustic+study&hl=en&gl=GB&ceid=GB:en&when=7d",
        ],
        "summary_prompt": (
            "You are an acoustics researcher. "
            "Summarize the following scientific news headlines about noise control research "
            "in 3–5 concise sentences in English. "
            "Focus on practical implications for noise control engineers. "
            "Reply ONLY with flowing prose, no bullet points, no headings."
        ),
    },
}

MAX_ITEMS_PER_CATEGORY = 10
MAX_TITLES_FOR_SUMMARY = 15


# ── RSS Fetching ───────────────────────────────────────────────────────────────

def fetch_rss(url: str) -> list[dict]:
    items = []
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"})
        with urlopen(req, timeout=15) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        channel = root.find("channel")
        if channel is None:
            return items
        for item in channel.findall("item"):
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link")  or "").strip()
            pub   = (item.findtext("pubDate") or "").strip()
            source_el = item.find("source")
            source = source_el.text.strip() if source_el is not None else ""
            if title:
                items.append({"title": title, "link": link, "date": pub, "source": source})
    except Exception as e:
        print(f"  Warning: could not fetch {url}: {e}")
    return items


def deduplicate(items: list[dict]) -> list[dict]:
    seen = set()
    result = []
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


# ── Gemini ─────────────────────────────────────────────────────────────────────

def call_gemini(prompt: str, max_tokens: int = 2000) -> str:
    import json as _json
    body = _json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
    }).encode()
    req = Request(GEMINI_URL, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=30) as resp:
            data = _json.loads(resp.read())
        finish_reason = data["candidates"][0].get("finishReason", "unknown")
        print(f"  Finish reason: {finish_reason}")
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"  Gemini error: {e}")
        return "Zusammenfassung konnte nicht erstellt werden."


def summarize_with_gemini(titles: list[str], prompt: str) -> str:
    if not titles:
        return "Keine aktuellen Meldungen gefunden."
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    return call_gemini(prompt + "\n\nNachrichtentitel:\n" + numbered, max_tokens=2000)


# ── Weekly Executive Summary ───────────────────────────────────────────────────

def generate_weekly_summary(categories_data: dict, generated: str) -> None:
    print("\n── Generating Weekly Executive Summary ──")
    sections = []
    for cat_id, cat in categories_data.items():
        summary = cat.get("summary", "")
        items = cat.get("items", [])
        titles = "\n".join(f"- {i['title']}" for i in items[:8])
        sections.append(
            f"## {cat['icon']} {cat['label']}\n"
            f"Zusammenfassung: {summary}\n\nSchlagzeilen:\n{titles}"
        )

    exec_prompt = (
        "Du bist ein Experte für Lärmschutz und Umgebungslärm. "
        "Erstelle einen wöchentlichen Executive Summary auf Deutsch basierend auf den folgenden "
        "Nachrichtenzusammenfassungen aus fünf Kategorien: Steiermark, Österreich, DACH-Region, Europa und Wissenschaft.\n\n"
        "Der Executive Summary soll:\n"
        "- Etwa eine A4-Seite lang sein (400–500 Wörter)\n"
        "- Mit einem kurzen Gesamtüberblick (2–3 Sätze) beginnen\n"
        "- Dann jede Kategorie in einem eigenen Absatz behandeln\n"
        "- Die wichtigsten Trends und Entwicklungen der Woche hervorheben\n"
        "- Professionell und prägnant formuliert sein\n"
        "- NUR Fließtext, keine Aufzählungen, keine Markdown-Formatierung\n\n"
        "Hier sind die Daten:\n\n" + "\n\n".join(sections)
    )

    print("  Calling Gemini for executive summary…")
    exec_text = call_gemini(exec_prompt, max_tokens=3000)
    time.sleep(5)

    paragraphs = [p.strip() for p in exec_text.split("\n") if p.strip()]
    html_paragraphs = "\n".join(f"    <p>{p}</p>" for p in paragraphs)

    now = datetime.now(timezone.utc)
    week_str = now.strftime("KW %W / %Y")
    date_str = now.strftime("%d. %B %Y")

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Executive Summary – {week_str}</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet" />
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'DM Sans', sans-serif; background: #f4f4f0; color: #1a1a1a; padding: 40px 20px 80px; }}
    .page {{ max-width: 740px; margin: 0 auto; background: #fff; border: 1px solid #e0e0e0; border-radius: 10px; padding: 52px 60px; box-shadow: 0 2px 20px rgba(0,0,0,0.06); }}
    .back {{ display: inline-block; margin-bottom: 32px; font-size: 13px; color: #888; text-decoration: none; }}
    .back:hover {{ color: #333; }}
    .kw {{ font-size: 11px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; color: #c8102e; margin-bottom: 10px; }}
    h1 {{ font-family: 'DM Serif Display', serif; font-weight: 400; font-size: 28px; line-height: 1.3; margin-bottom: 6px; }}
    .meta {{ font-size: 13px; color: #999; margin-bottom: 36px; padding-bottom: 24px; border-bottom: 2px solid #1a1a1a; }}
    p {{ font-size: 15px; line-height: 1.75; color: #2a2a2a; margin-bottom: 18px; }}
    p:first-of-type::first-letter {{ font-family: 'DM Serif Display', serif; font-size: 52px; line-height: 0.85; float: left; margin-right: 8px; margin-top: 6px; color: #c8102e; }}
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
    <div class="kw">Wöchentlicher Executive Summary · {week_str}</div>
    <h1>Lärmschutz & Umgebungslärm<br>im Überblick</h1>
    <div class="meta">Erstellt am {date_str} · Basierend auf aktuellen Meldungen aus 5 Kategorien</div>
{html_paragraphs}
    <div class="tags">
      <span class="tag" style="background:#2e7d32">🏞️ Steiermark</span>
      <span class="tag" style="background:#c8102e">🇦🇹 Österreich</span>
      <span class="tag" style="background:#5a5a5a">🏔️ DACH</span>
      <span class="tag" style="background:#003399">🇪🇺 Europa</span>
      <span class="tag" style="background:#1a6b3c">🔬 Wissenschaft</span>
    </div>
    <div class="footer">Automatisch generiert von Gemini AI · Lärmschutz News Monitor</div>
  </div>
</body>
</html>"""

    os.makedirs("docs", exist_ok=True)
    with open("docs/summary.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("  ✅ docs/summary.html written.")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
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

        items = deduplicate(all_items)[:MAX_ITEMS_PER_CATEGORY]
        print(f"  {len(items)} unique items")

        for item in items:
            item["date"] = format_date(item["date"])

        print("  Calling Gemini…")
        titles_for_summary = [i["title"] for i in items[:MAX_TITLES_FOR_SUMMARY]]
        summary = summarize_with_gemini(titles_for_summary, cat["summary_prompt"])
        print(f"  Summary: {summary[:80]}…")
        time.sleep(5)

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

    if GENERATE_SUMMARY:
        generate_weekly_summary(output["categories"], output["generated"])


if __name__ == "__main__":
    main()
