"""Calendar tool — uses gws calendar to list events."""

from crewai.tools import BaseTool
from pydantic import Field
import subprocess
import json
from datetime import datetime, timedelta
from typing import Optional


def _run_gws(args: list) -> dict:
    """Run gws command and return parsed JSON."""
    result = subprocess.run(
        ["~/bin/gws"] + args,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return {"error": result.stderr}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw": result.stdout}


class CalendarTool(BaseTool):
    name: str = "CalendarTool"
    description: str = (
        "Use this tool to list calendar events. "
        "Call with action='list' and optionally start_date/end_date (YYYY-MM-DD). "
        "Returns the list of events with title, start time, and attendees."
    )

    def _run(self, action: str = "list", start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
        if action == "list":
            params = {"calendarId": "primary", "timeMin": start_date or "", "timeMax": end_date or ""}
            # Build gws args
            args = ["calendar", "events", "list", "--params", json.dumps(params)]
            result = _run_gws(args)

            if "error" in result:
                return f"Error: {result['error']}"

            events = result.get("events", result.get("items", []))
            if not events:
                return "No events found in the specified range."

            lines = []
            for e in events:
                start = e.get("start", {}).get("dateTime", e.get("start", {}).get("date", "unknown"))
                summary = e.get("summary", "(No title)")
                attendees = e.get("attendees", [])
                lines.append(f"- {start}: {summary} ({len(attendees)} attendees)")
            return "\n".join(lines)

        return "Unknown action. Use action='list'."