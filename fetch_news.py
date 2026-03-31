"""
Lärmschutz News Fetcher
Fetches RSS feeds, summarizes with Gemini, saves to docs/data.json
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError
from urllib.parse import quote
import xml.etree.ElementTree as ET

# ── Configuration ──────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
)

CATEGORIES = {
    "austria": {
        "label": "Österreich",
        "icon": "🇦🇹",
        "color": "#c8102e",
        "feeds": [
            # Google News RSS – Austrian sources, German keywords
            "https://news.google.com/rss/search?q=L%C3%A4rmschutz+%C3%96sterreich&hl=de&gl=AT&ceid=AT:de",
            "https://news.google.com/rss/search?q=L%C3%A4rmschutzwand+Austria&hl=de&gl=AT&ceid=AT:de",
            "https://news.google.com/rss/search?q=L%C3%A4rm+%C3%96sterreich+Verordnung&hl=de&gl=AT&ceid=AT:de",
            "https://news.google.com/rss/search?q=Verkehrsl%C3%A4rm+%C3%96sterreich&hl=de&gl=AT&ceid=AT:de",
        ],
        "summary_prompt": (
            "Du bist Experte für Lärmschutz in Österreich. "
            "Fasse die folgenden Nachrichtentitel aus Österreich zum Thema Lärmschutz "
            "in 3–5 prägnanten deutschen Sätzen zusammen. "
            "Hebe die wichtigsten Entwicklungen hervor. "
            "Antworte NUR mit dem Fließtext, keine Aufzählungen, keine Überschriften."
        ),
    },
    "europe": {
        "label": "Europa",
        "icon": "🇪🇺",
        "color": "#003399",
        "feeds": [
            "https://news.google.com/rss/search?q=noise+control+EU+directive&hl=en&gl=GB&ceid=GB:en",
            "https://news.google.com/rss/search?q=environmental+noise+Europe+regulation&hl=en&gl=GB&ceid=GB:en",
            "https://news.google.com/rss/search?q=L%C3%A4rmschutz+Europa+EU&hl=de&gl=DE&ceid=DE:de",
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
            "https://news.google.com/rss/search?q=acoustics+noise+control+research&hl=en&gl=GB&ceid=GB:en",
            "https://news.google.com/rss/search?q=noise+barrier+material+research&hl=en&gl=GB&ceid=GB:en",
            "https://news.google.com/rss/search?q=urban+noise+acoustic+study&hl=en&gl=GB&ceid=GB:en",
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

MAX_ITEMS_PER_CATEGORY = 10  # articles shown on website
MAX_TITLES_FOR_SUMMARY = 15  # titles sent to Gemini


# ── RSS Fetching ───────────────────────────────────────────────────────────────

def fetch_rss(url: str) -> list[dict]:
    """Fetch and parse a single RSS feed, return list of items."""
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
    """Remove duplicate titles (case-insensitive)."""
    seen = set()
    result = []
    for item in items:
        key = re.sub(r"\s+", " ", item["title"].lower().strip())
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def format_date(raw: str) -> str:
    """Convert RSS date string to readable format."""
    if not raw:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(raw)
        return dt.strftime("%-d. %b %Y")
    except Exception:
        return raw[:16]


# ── Gemini Summarization ───────────────────────────────────────────────────────

def summarize_with_gemini(titles: list[str], prompt: str) -> str:
    """Call Gemini API to summarize a list of news titles."""
    if not titles:
        return "Keine aktuellen Meldungen gefunden."

    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    full_prompt = prompt + "\n\nNachrichtentitel:\n" + numbered

    import urllib.request, json as _json
    body = _json.dumps({
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"maxOutputTokens": 1000, "temperature": 0.3},
    }).encode()

    req = Request(
        GEMINI_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            data = _json.loads(resp.read())
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"  Gemini error: {e}")
        return "Zusammenfassung konnte nicht erstellt werden."


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    output = {
        "generated": datetime.now(timezone.utc).strftime("%d. %B %Y, %H:%M UTC"),
        "categories": {},
    }

    for cat_id, cat in CATEGORIES.items():
        print(f"\n── {cat['label']} ──")

        # Fetch all feeds
        all_items = []
        for feed_url in cat["feeds"]:
            print(f"  Fetching: {feed_url[:80]}…")
            all_items.extend(fetch_rss(feed_url))

        # Deduplicate and limit
        items = deduplicate(all_items)[:MAX_ITEMS_PER_CATEGORY]
        print(f"  {len(items)} unique items")

        # Format dates
        for item in items:
            item["date"] = format_date(item["date"])

        # Summarize
        print("  Calling Gemini…")
        titles_for_summary = [i["title"] for i in items[:MAX_TITLES_FOR_SUMMARY]]
        summary = summarize_with_gemini(titles_for_summary, cat["summary_prompt"])
        print(f"  Summary: {summary[:80]}…")
        time.sleep(5)  # kurze Pause zwischen Kategorien

        output["categories"][cat_id] = {
            "label": cat["label"],
            "icon": cat["icon"],
            "color": cat["color"],
            "summary": summary,
            "items": items,
        }

    # Save to docs/data.json (served by GitHub Pages)
    os.makedirs("docs", exist_ok=True)
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\n✅ docs/data.json written successfully.")


if __name__ == "__main__":
    main()
