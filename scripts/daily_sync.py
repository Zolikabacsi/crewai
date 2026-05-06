#!/usr/bin/env python3
"""
Daily calendar sync — run via cron.

1. Fetches primary calendar events via `gws` CLI.
2. Detects new / modified / deleted events since last run (etag tracking).
3. Calculates days spent in each country from location data + flight events.
4. Sends a human-readable summary to Telegram.

State is persisted to ~/.claude/office_assistant_state.json.
"""

import os
import sys
import json
import subprocess
import re
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

# ── Paths ────────────────────────────────────────────────────────────────────

STATE_FILE = Path.home() / ".claude" / "office_assistant_state.json"
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# How many past days to look back for the country tally
LOOKBACK_DAYS = 30

# ── Country resolver ───────────────────────────────────────────────────────────

# Airport code → (country_code, country_name)
AIRPORT_MAP: dict[str, tuple[str, str]] = {
    "BUD": ("HU", "Hungary"),
    "ARN": ("SE", "Sweden"),
    "CPH": ("DK", "Denmark"),
    "ZRH": ("CH", "Switzerland"),
    "GVA": ("CH", "Switzerland"),
    "FRA": ("DE", "Germany"),
    "LHR": ("GB", "United Kingdom"),
    "LGW": ("GB", "United Kingdom"),
    "CDG": ("FR", "France"),
    "AMS": ("NL", "Netherlands"),
    "BEG": ("RS", "Serbia"),
    "WAW": ("PL", "Poland"),
    "VIE": ("AT", "Austria"),
    "MAD": ("ES", "Spain"),
    "FCO": ("IT", "Italy"),
    "JFK": ("US", "United States"),
    "LAX": ("US", "United States"),
    "DXB": ("AE", "UAE"),
    "IST": ("TR", "Turkey"),
}

# City → (country_code, country_name) for ambiguous free-text locations
CITY_MAP: dict[str, tuple[str, str]] = {
    "budapest":   ("HU", "Hungary"),
    "miskolc":    ("HU", "Hungary"),
    "copenhagen": ("DK", "Denmark"),
    "kastrup":    ("DK", "Denmark"),
    "malmo":      ("SE", "Sweden"),
    "stockholm":  ("SE", "Sweden"),
    "hultsfred":  ("SE", "Sweden"),
    "kalmar":     ("SE", "Sweden"),
    "zurich":     ("CH", "Switzerland"),
    "geneva":     ("CH", "Switzerland"),
    "belgrade":   ("RS", "Serbia"),
    "beograd":    ("RS", "Serbia"),
    "london":     ("GB", "United Kingdom"),
    "paris":      ("FR", "France"),
    "amsterdam":  ("NL", "Netherlands"),
    "berlin":     ("DE", "Germany"),
    "warsaw":     ("PL", "Poland"),
    "vienna":     ("AT", "Austria"),
}


def resolve_country(location: str | None, summary: str | None) -> tuple[str, str] | None:
    """
    Resolve a country from a calendar event's location string and/or summary.

    Priority: airport code › explicit country name › city lookup.
    Returns (country_code, country_name) or None.
    """
    text = f"{summary or ''} {location or ''}".lower()

    # 1. Airport codes (word-boundary match)
    for code, val in AIRPORT_MAP.items():
        if re.search(rf"\b{code}\b", text):
            return val

    # 2. Explicit country names
    for kw, val in {
        "hungary":      ("HU", "Hungary"),
        "sweden":       ("SE", "Sweden"),
        "denmark":      ("DK", "Denmark"),
        "switzerland":  ("CH", "Switzerland"),
        "serbia":       ("RS", "Serbia"),
        "united kingdom": ("GB", "United Kingdom"),
        "germany":      ("DE", "Germany"),
        "france":       ("FR", "France"),
        "netherlands":  ("NL", "Netherlands"),
        "poland":       ("PL", "Poland"),
        "austria":      ("AT", "Austria"),
        "spain":        ("ES", "Spain"),
        "italy":        ("IT", "Italy"),
        "usa":          ("US", "United States"),
        "united states": ("US", "United States"),
        "uae":          ("AE", "UAE"),
        "turkey":       ("TR", "Turkey"),
    }.items():
        if kw in text:
            return val

    # 3. City lookup
    for city, val in CITY_MAP.items():
        if city in text:
            return val

    return None


# ── gws wrapper ─────────────────────────────────────────────────────────────

def gws_calendar_events(time_min: str, time_max: str, max_results: int = 200) -> list[dict]:
    """Call `gws calendar events list` and return the parsed JSON `items` list."""
    params = {
        "calendarId":   "primary",
        "timeMin":      time_min,
        "timeMax":      time_max,
        "singleEvents": True,
        "orderBy":      "startTime",
        "maxResults":   max_results,
    }
    cmd = ["gws", "calendar", "events", "list",
           "--params", json.dumps(params), "--format", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[gws] error: {result.stderr.strip()}", file=sys.stderr)
        return []
    try:
        return json.loads(result.stdout).get("items", [])
    except json.JSONDecodeError as exc:
        print(f"[gws] JSON parse error: {exc}", file=sys.stderr)
        return []


# ── State persistence ─────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_etag": {}, "last_sync": None}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


# ── Event helpers ─────────────────────────────────────────────────────────────

def event_key(e: dict) -> str:
    """Stable key for deduplication / change detection."""
    return e.get("iCalUID", "") or e.get("id", "")


def event_date(e: dict) -> date:
    """Return the date (date-only) of an event's start."""
    start = e.get("start", {})
    for attr in ("dateTime", "date"):
        if attr in start:
            raw = start[attr][:10]
            try:
                return date.fromisoformat(raw)
            except ValueError:
                pass
    return date.today()


def event_end_date(e: dict) -> date:
    """Return the date (date-only) of an event's end."""
    end = e.get("end", {})
    for attr in ("dateTime", "date"):
        if attr in end:
            raw = end[attr][:10]
            try:
                return date.fromisoformat(raw)
            except ValueError:
                pass
    return event_date(e)


def date_range(start_d: date, end_d: date) -> list[date]:
    """Inclusive range of dates."""
    out, d = [], start_d
    while d <= end_d:
        out.append(d)
        d += timedelta(days=1)
    return out


# ── Country day counting ──────────────────────────────────────────────────────

# Patterns that indicate a travel "stay" event (multi-day)
_STAY_RE  = re.compile(r"\bstay\s+(?:at\s+)?(.+)", re.IGNORECASE)
_FLIGHT_RE = re.compile(r"\bflight\s+(?:to|from)\s+(\w[\w\s]+?)\s*\(", re.IGNORECASE)


def count_country_days(events: list[dict], since: date, until: date) -> dict[str, int]:
    """
    Tally calendar days per country for events in [since, until].

    - "Stay at X" events  → every calendar day in the range belongs to X.
    - "Flight to X" events → the flight day belongs to X.
    - Other located events → the day belongs to X.
    - Unlocated events (personal, video calls) → ignored.
    """
    day_countries: dict[date, set[str]] = defaultdict(set)

    for e in events:
        summary   = e.get("summary", "") or ""
        location  = e.get("location") or ""
        start_d   = event_date(e)
        end_d     = event_end_date(e)

        if end_d < since or start_d > until:
            continue

        win_start = max(start_d, since)
        win_end   = min(end_d,   until)
        if win_end < win_start:
            continue

        resolved: tuple[str, str] | None = None

        if _STAY_RE.search(summary):
            # Stay events: resolve from full location
            resolved = resolve_country(location, summary)
            if resolved:
                for d in date_range(win_start, win_end):
                    day_countries[d].add(f"{resolved[0]}:{resolved[1]}")

        elif re.search(r"\bflight\b", summary, re.IGNORECASE):
            # Flights: infer destination from summary text before the airline code
            m = _FLIGHT_RE.search(summary)
            dest_text = m.group(1).strip() if m else location
            resolved  = resolve_country(dest_text, None) or resolve_country(location, summary)
            if resolved:
                day_countries[win_start].add(f"{resolved[0]}:{resolved[1]}")

        elif location:
            # Regular events with a location
            resolved = resolve_country(location, summary)
            if resolved:
                for d in date_range(win_start, win_end):
                    day_countries[d].add(f"{resolved[0]}:{resolved[1]}")

    # Tally — one vote per country per day
    counts: dict[str, int] = defaultdict(int)
    for countries in day_countries.values():
        for c in countries:
            counts[c] += 1
    return dict(counts)


# ── Change detection ───────────────────────────────────────────────────────────

def detect_changes(
    events: list[dict],
    prev_state: dict,
) -> tuple[list[dict], list[dict], list[str]]:
    """
    Compare current events against last-seen etags.
    Returns (new_events, modified_events, deleted_ids).
    """
    prev_etags: dict[str, str] = prev_state.get("last_etag", {})
    seen_ids:   set[str] = set()

    new_ev, mod_ev = [], []

    for e in events:
        key  = event_key(e)
        etag = e.get("etag", "").strip('"')
        seen_ids.add(key)

        if key not in prev_etags:
            new_ev.append(e)
        elif etag and etag != prev_etags.get(key, ""):
            mod_ev.append(e)

    deleted = [k for k in prev_etags if k not in seen_ids]
    return new_ev, mod_ev, deleted


# ── Telegram ──────────────────────────────────────────────────────────────────

def send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not TELEGRAM_CHAT_ID or not token:
        print("[Telegram] No credentials — logged:\n" + text)
        return False
    try:
        import httpx
        r = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )
        r.raise_for_status()
        return True
    except Exception as exc:
        print(f"[Telegram] Failed: {exc}\n{text}", file=sys.stderr)
        return False


# ── Country flags ───────────────────────────────────────────────────────────────

_COUNTRY_FLAGS = {
    "HU": "🇭🇺", "SE": "🇸🇪", "DK": "🇩🇰", "CH": "🇨🇭",
    "RS": "🇷🇸", "GB": "🇬🇧", "DE": "🇩🇪", "FR": "🇫🇷",
    "NL": "🇳🇱", "PL": "🇵🇱", "AT": "🇦🇹", "ES": "🇪🇸",
    "IT": "🇮🇹", "US": "🇺🇸", "AE": "🇦🇪", "TR": "🇹🇷",
}


def build_report(
    new_ev:  list[dict],
    mod_ev:  list[dict],
    del_ids: list[str],
    country_days: dict[str, int],
    sync_time: datetime,
    since: date,
    until: date,
) -> str:
    lines = [
        f"📅 *Calendar Sync* — {sync_time.strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    if not new_ev and not mod_ev and not del_ids:
        lines.append("✅ No changes since last sync.")
    else:
        if new_ev:
            lines.append(f"🆕 *{len(new_ev)} new:*")
            for e in new_ev[:10]:
                lines.append(f"  • {_fmt_event(e)}")
            if len(new_ev) > 10:
                lines.append(f"  …+{len(new_ev)-10} more")

        if mod_ev:
            lines.append(f"✏️ *{len(mod_ev)} modified:*")
            for e in mod_ev[:10]:
                lines.append(f"  • {_fmt_event(e)}")

        if del_ids:
            lines.append(f"🗑️ *{len(del_ids)} deleted:*")
            for k in del_ids[:5]:
                lines.append(f"  • `{k[:30]}…`")

    lines.append("")
    if country_days:
        lines.append(f"🌍 *Country days ({since.strftime('%b %d')}–{until.strftime('%b %d')}):*")
        for key, n in sorted(country_days.items(), key=lambda x: -x[1]):
            cc, name = key.split(":", 1)
            flag = _COUNTRY_FLAGS.get(cc, f"[{cc}]")
            s = "" if n == 1 else "s"
            lines.append(f"  {flag} {name}: *{n}* day{s}")
    else:
        lines.append("🌍 _No country data in the last 30 days._")

    lines.append("")
    lines.append("_office-assistant_")
    return "\n".join(lines)


def _fmt_event(e: dict) -> str:
    d   = event_date(e).strftime("%b %d")
    s   = e.get("summary", "_no title_")
    loc = e.get("location", "")
    loc_str = f" @ {loc[:35]}" if loc else ""
    return f"{d}: {s[:50]}{loc_str}"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    now    = datetime.now()
    since  = (now - timedelta(days=LOOKBACK_DAYS)).date()
    until  = now.date()
    time_min = f"{since.isoformat()}T00:00:00Z"
    time_max = f"{until.isoformat()}T23:59:59Z"

    print(f"=== Office Sync — {now.isoformat()} ===")
    print(f"Fetching calendar from {time_min} → {time_max} …")

    events = gws_calendar_events(time_min, time_max)
    print(f"Fetched {len(events)} events.")

    state    = load_state()
    new_ev, mod_ev, deleted = detect_changes(events, state)

    if new_ev or mod_ev or deleted:
        print(f"  +{len(new_ev)} new, ~{len(mod_ev)} modified, -{len(deleted)} deleted")
    else:
        print("  No changes since last sync.")

    country_days = count_country_days(events, since, until)

    report = build_report(new_ev, mod_ev, deleted, country_days, now, since, until)
    print("\n" + report)
    send_telegram(report)

    # Persist updated etag state
    state = {
        "last_etag":  {event_key(e): e.get("etag", "").strip('"') for e in events},
        "last_sync":  now.isoformat(),
    }
    save_state(state)
    print(f"\nState saved → {STATE_FILE}")


if __name__ == "__main__":
    main()
