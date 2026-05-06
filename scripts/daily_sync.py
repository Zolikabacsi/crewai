#!/usr/bin/env python3
"""
Daily calendar sync — run via cron.

1. Fetches events from all relevant calendars via `gws` CLI:
   Private (primary), Swedish Work, Hungarian Work.
2. Detects new / modified / deleted events since last run (etag tracking).
3. Calculates days spent in each country from location data + event titles.
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

# ── Calendars to scan ─────────────────────────────────────────────────────────

CALENDARS = [
    {"id": "primary", "name": "Private"},
    {
        "id": "c_0913dd2a922d81fa408a98187125cab3ab75de5a03b9f530fb164af065b521f7@group.calendar.google.com",
        "name": "Swedish Work",
        "default_country": ("SE", "Sweden"),
    },
    {
        "id": "c_64d5a317b4553db41b79cfdd86cc24c8c3df3fbc1f420dd9f45e445143c9c2e1@group.calendar.google.com",
        "name": "Hungarian Work",
        "default_country": None,   # mixed — resolve per-event from title/location
    },
]

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

# Known Swedish towns / clinics where work shifts are recorded
# (These appear as event titles in Swedish Work and Hungarian Work calendars)
SWEDISH_TOWNS: dict[str, tuple[str, str]] = {
    "hammarstrand":  ("SE", "Sweden"),
    "gimo":          ("SE", "Sweden"),
    "hultsfred":     ("SE", "Sweden"),
    "kalmar":        ("SE", "Sweden"),
    "stockholm":     ("SE", "Sweden"),
    "uppsala":       ("SE", "Sweden"),
    "östersund":     ("SE", "Sweden"),
    "luleå":         ("SE", "Sweden"),
    "umeå":          ("SE", "Sweden"),
    "västerås":      ("SE", "Sweden"),
    "örebro":        ("SE", "Sweden"),
    "linköping":     ("SE", "Sweden"),
    "jönköping":     ("SE", "Sweden"),
    "malmö":         ("SE", "Sweden"),
    "göteborg":      ("SE", "Sweden"),
    "växjö":         ("SE", "Sweden"),
    "jokkmokk":      ("SE", "Sweden"),
    "kramfors":      ("SE", "Sweden"),
    "solna":         ("SE", "Sweden"),
}

# City → (country_code, country_name)
CITY_MAP: dict[str, tuple[str, str]] = {
    "budapest":   ("HU", "Hungary"),
    "miskolc":    ("HU", "Hungary"),
    "copenhagen": ("DK", "Denmark"),
    "kastrup":    ("DK", "Denmark"),
    "malmo":      ("SE", "Sweden"),
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
    "dunaújváros":("HU", "Hungary"),
    "debrecen":   ("HU", "Hungary"),
    "szeged":     ("HU", "Hungary"),
}

# Institutions whose name pattern indicates Hungary
HUNGARIAN_INSTITUTIONS = re.compile(
    r"sote|semmelweis|budapest(?!,?\s*sweden)|váci|márton|"
    r"指望|培训中心",
    re.IGNORECASE,
)


def resolve_country(
    location: str | None,
    summary: str | None,
    default_country: tuple[str, str] | None = None,
) -> tuple[str, str] | None:
    """
    Resolve a country from an event's location string and/or summary.

    Priority:
      1. Airport codes (word-boundary regex)
      2. Explicit country name in text
      3. Known Swedish towns (for work-shift calendar titles)
      4. Hungarian institution keywords
      5. City lookup
      6. Calendar-level default_country (Swedish Work → Sweden, etc.)
    """
    text = f"{summary or ''} {location or ''}".lower()

    # 1. Airport codes
    for code, val in AIRPORT_MAP.items():
        if re.search(rf"\b{re.escape(code)}\b", text):
            return val

    # 2. Explicit country names
    for kw, val in {
        "hungary":       ("HU", "Hungary"),
        "sweden":        ("SE", "Sweden"),
        "denmark":       ("DK", "Denmark"),
        "switzerland":   ("CH", "Switzerland"),
        "serbia":        ("RS", "Serbia"),
        "united kingdom":("GB", "United Kingdom"),
        "germany":       ("DE", "Germany"),
        "france":        ("FR", "France"),
        "netherlands":   ("NL", "Netherlands"),
        "poland":        ("PL", "Poland"),
        "austria":       ("AT", "Austria"),
        "spain":         ("ES", "Spain"),
        "italy":         ("IT", "Italy"),
        "usa":           ("US", "United States"),
        "united states": ("US", "United States"),
        "uae":           ("AE", "UAE"),
        "turkey":        ("TR", "Turkey"),
    }.items():
        if kw in text:
            return val

    # 3. Swedish towns (often appear as bare event titles in shift calendars)
    for town, val in SWEDISH_TOWNS.items():
        # match word boundary within the text (summary or location)
        if re.search(rf"\b{re.escape(town)}\b", text):
            return val

    # 4. Hungarian institution patterns
    if HUNGARIAN_INSTITUTIONS.search(text):
        return ("HU", "Hungary")

    # 5. City lookup
    for city, val in CITY_MAP.items():
        if city in text:
            return val

    # 6. Calendar default
    return default_country or None


# ── gws wrapper ─────────────────────────────────────────────────────────────

def gws_calendar_events(
    calendar_id: str,
    time_min: str,
    time_max: str,
    max_results: int = 200,
) -> list[dict]:
    """Call `gws calendar events list` and return the parsed JSON `items` list."""
    params = {
        "calendarId":   calendar_id,
        "timeMin":      time_min,
        "timeMax":      time_max,
        "singleEvents": True,
        "orderBy":      "startTime",
        "maxResults":   max_results,
    }
    cmd = [
        "gws", "calendar", "events", "list",
        "--params", json.dumps(params),
        "--format", "json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[gws] error for {calendar_id}: {result.stderr.strip()}", file=sys.stderr)
        return []
    try:
        return json.loads(result.stdout).get("items", [])
    except json.JSONDecodeError:
        return []


def fetch_all_calendars(time_min: str, time_max: str) -> list[tuple[dict, list[dict]]]:
    """
    Fetch events from all configured calendars.
    Returns list of (calendar_meta, events).
    """
    results = []
    for cal in CALENDARS:
        events = gws_calendar_events(cal["id"], time_min, time_max)
        results.append((cal, events))
    return results


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
    for attr in ("dateTime", "date"):
        raw = e.get("start", {}).get(attr, "")[:10]
        if raw:
            try:
                return date.fromisoformat(raw)
            except ValueError:
                pass
    return date.today()


def event_end_date(e: dict) -> date:
    for attr in ("dateTime", "date"):
        raw = e.get("end", {}).get(attr, "")[:10]
        if raw:
            try:
                return date.fromisoformat(raw)
            except ValueError:
                pass
    return event_date(e)


def date_range(start_d: date, end_d: date) -> list[date]:
    out, d = [], start_d
    while d <= end_d:
        out.append(d)
        d += timedelta(days=1)
    return out


# ── Country day counting ──────────────────────────────────────────────────────

_STAY_RE   = re.compile(r"\bstay\s+(?:at\s+)?(.+)", re.IGNORECASE)
_FLIGHT_RE = re.compile(r"\bflight\s+(?:to|from)\s+(\w[\w\s]+?)\s*\(", re.IGNORECASE)


def count_country_days(
    calendar_events: list[tuple[dict, list[dict]]],
    since: date,
    until: date,
) -> dict[str, int]:
    """
    Tally calendar days per country across all calendars for events in [since, until].

    For each event:
      - "Stay at X"        → all calendar days in range → X's country
      - "Flight to X"       → the flight day → X's country
      - Swedish Work title  → Swedish towns map → Sweden (via SWEDISH_TOWNS)
      - Hungarian Work title→ Hungarian institution map → Hungary
      - Event with location → resolved from location string
      - No signal           → skipped
    """
    day_countries: dict[date, set[str]] = defaultdict(set)

    for cal_meta, events in calendar_events:
        default_cc = cal_meta.get("default_country")
        cal_name   = cal_meta.get("name", "")

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

            # "Stay at X" → use location for country
            if _STAY_RE.search(summary):
                resolved = resolve_country(location, summary, default_cc)

            # "Flight to X" → parse destination from summary before airline code
            elif re.search(r"\bflight\b", summary, re.IGNORECASE):
                m = _FLIGHT_RE.search(summary)
                dest_text = m.group(1).strip() if m else location
                resolved  = (
                    resolve_country(dest_text, None, default_cc)
                    or resolve_country(location, summary, default_cc)
                )

            # Bare Swedish town names (shift calendar titles like "Hultsfred", "Gimo")
            elif cal_name == "Swedish Work":
                # All Swedish Work events default to Sweden unless location says otherwise
                resolved = resolve_country(location, summary, default_cc)
                if resolved is None:
                    # Bare title like "Hammarstrand Hc" — scan for Swedish towns
                    resolved = resolve_country(None, summary, default_cc)
                if resolved is None:
                    resolved = default_cc  # fallback for bare shift titles

            elif cal_name == "Hungarian Work":
                # Mixed: check for Swedish towns in title, Hungarian institutions,
                #        or bare titles like "Hultsfred" (Swedish) vs "Munka" (unknown)
                resolved = resolve_country(location, summary, default_cc)
                if resolved is None:
                    resolved = resolve_country(None, summary, default_cc)

            else:
                # Primary / Private calendar: standard resolution
                resolved = resolve_country(location, summary, default_cc)

            if resolved:
                key = f"{resolved[0]}:{resolved[1]}"
                for d in date_range(win_start, win_end):
                    day_countries[d].add(key)

    # Tally
    counts: dict[str, int] = defaultdict(int)
    for countries in day_countries.values():
        for c in countries:
            counts[c] += 1
    return dict(counts)


# ── Change detection ───────────────────────────────────────────────────────────

def detect_changes(
    calendar_events: list[tuple[dict, list[dict]]],
    prev_state: dict,
) -> tuple[list[dict], list[dict], list[str]]:
    """
    Compare current events across all calendars against last-seen etags.
    Returns (new_events, modified_events, deleted_ids).
    Event dicts are enriched with '_calendar' key for reporting.
    """
    prev_etags: dict[str, str] = prev_state.get("last_etag", {})
    seen_ids:  set[str] = set()

    new_ev, mod_ev = [], []

    for cal_meta, events in calendar_events:
        cal_name = cal_meta.get("name", "primary")
        for e in events:
            key  = event_key(e)
            etag = e.get("etag", "").strip('"')
            seen_ids.add(key)

            # Attach calendar name for reporting
            e["_calendar"] = cal_name

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
    new_ev:      list[dict],
    mod_ev:      list[dict],
    del_ids:     list[str],
    country_days: dict[str, int],
    sync_time:   datetime,
    since:       date,
    until:       date,
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
            for e in new_ev[:12]:
                cal = e.get("_calendar", "primary")
                lines.append(f"  • [{cal}] {_fmt_event(e)}")
            if len(new_ev) > 12:
                lines.append(f"  …+{len(new_ev)-12} more")

        if mod_ev:
            lines.append(f"✏️ *{len(mod_ev)} modified:*")
            for e in mod_ev[:8]:
                cal = e.get("_calendar", "primary")
                lines.append(f"  • [{cal}] {_fmt_event(e)}")

        if del_ids:
            lines.append(f"🗑️ *{len(del_ids)} deleted:*")
            for k in del_ids[:5]:
                lines.append(f"  • `{k[:35]}…`")

    lines.append("")
    if country_days:
        lines.append(f"🌍 *Country days ({since.strftime('%b %d')}–{until.strftime('%b %d')}):*")
        for key, n in sorted(country_days.items(), key=lambda x: -x[1]):
            cc, name = key.split(":", 1)
            flag = _COUNTRY_FLAGS.get(cc, f"[{cc}]")
            s = "" if n == 1 else "s"
            lines.append(f"  {flag} {name}: *{n}* day{s}")
    else:
        lines.append("🌍 _No country data in the lookback window._")

    lines.append("")
    lines.append("_office-assistant_")
    return "\n".join(lines)


def _fmt_event(e: dict) -> str:
    d   = event_date(e).strftime("%b %d")
    s   = e.get("summary", "_no title_")
    loc = e.get("location", "")
    loc_str = f" @ {loc[:30]}" if loc else ""
    return f"{d}: {s[:45]}{loc_str}"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    now    = datetime.now()
    since  = (now - timedelta(days=LOOKBACK_DAYS)).date()
    until  = now.date()
    time_min = f"{since.isoformat()}T00:00:00Z"
    time_max = f"{until.isoformat()}T23:59:59Z"

    print(f"=== Office Sync — {now.isoformat()} ===")
    print(f"Fetching calendars from {time_min} → {time_max} …")

    calendar_events = fetch_all_calendars(time_min, time_max)

    total = sum(len(evts) for _, evts in calendar_events)
    print(f"Fetched {total} total events:")
    for cal, evts in calendar_events:
        print(f"  [{cal['name']}] {len(evts)} events")

    state = load_state()
    new_ev, mod_ev, deleted = detect_changes(calendar_events, state)

    if new_ev or mod_ev or deleted:
        print(f"  +{len(new_ev)} new, ~{len(mod_ev)} modified, -{len(deleted)} deleted")
    else:
        print("  No changes since last sync.")

    country_days = count_country_days(calendar_events, since, until)

    report = build_report(new_ev, mod_ev, deleted, country_days, now, since, until)
    print("\n" + report)
    send_telegram(report)

    # Persist updated state — key includes calendar id prefix for safety
    new_etags: dict[str, str] = {}
    for cal, evts in calendar_events:
        cal_prefix = cal["id"]
        for e in evts:
            key  = event_key(e)
            etag = e.get("etag", "").strip('"')
            new_etags[f"{cal_prefix}::{key}"] = etag

    state = {
        "last_etag": new_etags,
        "last_sync": now.isoformat(),
    }
    save_state(state)
    print(f"\nState saved → {STATE_FILE}")


if __name__ == "__main__":
    main()
