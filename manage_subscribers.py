"""
Subscriber Manager
Handles subscribe and unsubscribe events from GitHub Actions repository_dispatch.
Run with: python manage_subscribers.py subscribe email@example.com "Name" weekly monthly
       or: python manage_subscribers.py unsubscribe email@example.com
"""

import json
import os
import sys
from datetime import datetime, timezone

SUBSCRIBERS_FILE = "docs/subscribers.json"


def load() -> list[dict]:
    try:
        with open(SUBSCRIBERS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save(data: list[dict]) -> None:
    os.makedirs("docs", exist_ok=True)
    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def subscribe(email: str, name: str, weekly: bool, monthly: bool) -> None:
    data = load()
    # Check if already subscribed
    for sub in data:
        if sub["email"].lower() == email.lower():
            sub["name"]    = name
            sub["weekly"]  = weekly
            sub["monthly"] = monthly
            sub["active"]  = True
            sub["updated"] = datetime.now(timezone.utc).isoformat()
            save(data)
            print(f"Updated subscriber: {email}")
            return
    # New subscriber
    data.append({
        "email":     email,
        "name":      name,
        "weekly":    weekly,
        "monthly":   monthly,
        "active":    True,
        "subscribed": datetime.now(timezone.utc).isoformat(),
    })
    save(data)
    print(f"New subscriber: {email} (weekly={weekly}, monthly={monthly})")


def unsubscribe(email: str) -> None:
    data = load()
    for sub in data:
        if sub["email"].lower() == email.lower():
            sub["active"]      = False
            sub["unsubscribed"] = datetime.now(timezone.utc).isoformat()
            save(data)
            print(f"Unsubscribed: {email}")
            return
    print(f"Email not found: {email}")


if __name__ == "__main__":
    action = os.environ.get("ACTION", sys.argv[1] if len(sys.argv) > 1 else "")
    email  = os.environ.get("EMAIL",  sys.argv[2] if len(sys.argv) > 2 else "")
    name   = os.environ.get("NAME",   sys.argv[3] if len(sys.argv) > 3 else "")
    weekly  = os.environ.get("WEEKLY",  "true").lower() == "true"
    monthly = os.environ.get("MONTHLY", "true").lower() == "true"

    if action == "subscribe" and email:
        subscribe(email, name, weekly, monthly)
    elif action == "unsubscribe" and email:
        unsubscribe(email)
    else:
        print(f"Usage: python manage_subscribers.py subscribe|unsubscribe email [name] [weekly] [monthly]")
        sys.exit(1)
