"""
Newsletter Sender via Brevo API
Reads subscribers from docs/subscribers.json and sends the weekly or monthly newsletter.
Run via GitHub Actions after the newsletter HTML has been generated.
"""

import json
import os
import sys
from urllib.request import urlopen, Request
from urllib.error import HTTPError

# ── Configuration ──────────────────────────────────────────────────────────────

BREVO_API_KEY   = os.environ["BREVO_API_KEY"]
BREVO_SEND_URL  = "https://api.brevo.com/v3/smtp/email"

# Your verified sender in Brevo — change to your email address
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "florian.lackner@example.com")
SENDER_NAME  = "Lärmschutz News Monitor"

SITE_URL = os.environ.get("SITE_URL", "https://schalltechnik.github.io/Laermschutz_News")

WEEKLY_SEND  = os.environ.get("SEND_WEEKLY",  "false").lower() == "true"
MONTHLY_SEND = os.environ.get("SEND_MONTHLY", "false").lower() == "true"


def load_subscribers() -> list[dict]:
    """Load subscribers from docs/subscribers.json"""
    try:
        with open("docs/subscribers.json", encoding="utf-8") as f:
            data = json.load(f)
        return [s for s in data if s.get("active", True)]
    except FileNotFoundError:
        print("No subscribers.json found — no emails sent.")
        return []
    except Exception as e:
        print(f"Error loading subscribers: {e}")
        return []


def load_html(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return ""


def send_email(to_email: str, to_name: str, subject: str, html_content: str) -> bool:
    """Send a single email via Brevo transactional API."""
    import json as _json

    body = _json.dumps({
        "sender":  {"name": SENDER_NAME, "email": SENDER_EMAIL},
        "to":      [{"email": to_email, "name": to_name}],
        "subject": subject,
        "htmlContent": html_content,
    }).encode("utf-8")

    req = Request(
        BREVO_SEND_URL,
        data=body,
        headers={
            "Content-Type":  "application/json",
            "Accept":        "application/json",
            "api-key":       BREVO_API_KEY,
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            result = resp.read()
        print(f"  ✅ Sent to {to_email}")
        return True
    except HTTPError as e:
        body_err = e.read().decode("utf-8", errors="replace")
        print(f"  ❌ Failed to send to {to_email}: HTTP {e.code} — {body_err[:200]}")
        return False
    except Exception as e:
        print(f"  ❌ Failed to send to {to_email}: {e}")
        return False


def inject_unsubscribe_link(html: str, email: str) -> str:
    """Add a personalized unsubscribe link to the footer."""
    from urllib.parse import quote
    unsub_url = f"{SITE_URL}/unsubscribe.html?email={quote(email)}"
    unsub_block = (
        f'<div style="text-align:center;margin-top:20px;font-size:11px;color:#aaa;">'
        f'<a href="{unsub_url}" style="color:#aaa;">Newsletter abbestellen</a>'
        f'</div>'
    )
    # Insert before </body>
    if "</body>" in html:
        return html.replace("</body>", unsub_block + "</body>")
    return html + unsub_block


def main():
    subscribers = load_subscribers()
    if not subscribers:
        print("No active subscribers found.")
        return

    sent_weekly = sent_monthly = 0

    if WEEKLY_SEND:
        print(f"\n── Sending Weekly Newsletter to {len(subscribers)} subscribers ──")
        html = load_html("docs/summary.html")
        if not html:
            print("  Weekly newsletter HTML not found, skipping.")
        else:
            subject = "🔊 Wöchentlicher Lärmschutz Newsletter"
            for sub in subscribers:
                if sub.get("weekly", True):
                    personalized = inject_unsubscribe_link(html, sub["email"])
                    if send_email(sub["email"], sub.get("name", ""), subject, personalized):
                        sent_weekly += 1
        print(f"  Weekly: {sent_weekly} emails sent.")

    if MONTHLY_SEND:
        print(f"\n── Sending Monthly Newsletter to {len(subscribers)} subscribers ──")
        html = load_html("docs/summary_monthly.html")
        if not html:
            print("  Monthly newsletter HTML not found, skipping.")
        else:
            from datetime import datetime, timezone
            month_str = datetime.now(timezone.utc).strftime("%B %Y")
            subject = f"📅 Monatlicher Lärmschutz Newsletter – {month_str}"
            for sub in subscribers:
                if sub.get("monthly", True):
                    personalized = inject_unsubscribe_link(html, sub["email"])
                    if send_email(sub["email"], sub.get("name", ""), subject, personalized):
                        sent_monthly += 1
        print(f"  Monthly: {sent_monthly} emails sent.")

    if not WEEKLY_SEND and not MONTHLY_SEND:
        print("No newsletter type selected. Set SEND_WEEKLY=true or SEND_MONTHLY=true.")


if __name__ == "__main__":
    main()
