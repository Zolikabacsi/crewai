"""Email search tool — uses gws gmail to search and read emails."""

from crewai.tools import BaseTool
from pydantic import Field
import subprocess
import json
from typing import Optional


def _run_gws(args: list) -> dict:
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


class EmailSearchTool(BaseTool):
    name: str = "EmailSearchTool"
    description: str = (
        "Use this tool to search emails and read email bodies. "
        "action='search': pass query string (e.g. 'from:accountant subject:Q1'). "
        "action='read': pass message_id to get full email content. "
        "Returns matching email summaries or full email body."
    )

    def _run(self, action: str = "search", query: str = "", message_id: str = "") -> str:
        if action == "search":
            params = {"q": query, "maxResults": 10, "userId": "me"}
            result = _run_gws(["gmail", "users", "messages", "list", "--params", json.dumps(params)])
            if "error" in result:
                return f"Error: {result['error']}"

            messages = result.get("messages", [])
            if not messages:
                return "No emails found matching that query."

            # Summarize each message (id + snippet)
            lines = []
            for m in messages[:10]:
                mid = m["id"]
                # Get snippet via get
                detail = _run_gws(["gmail", "users", "messages", "get", "--params", json.dumps({"userId": "me", "id": mid})])
                snippet = detail.get("snippet", "")
                subject = ""
                for h in detail.get("payload", {}).get("headers", []):
                    if h["name"].lower() == "subject":
                        subject = h["value"]
                        break
                lines.append(f"- [{mid}] {subject}: {snippet[:80]}...")
            return "\n".join(lines)

        elif action == "read":
            if not message_id:
                return "Error: message_id required for read action."
            detail = _run_gws(["gmail", "users", "messages", "get", "--params", json.dumps({"userId": "me", "id": message_id})])
            if "error" in detail:
                return f"Error: {detail['error']}"
            snippet = detail.get("snippet", "")
            subject = ""
            from_addr = ""
            for h in detail.get("payload", {}).get("headers", []):
                if h["name"].lower() == "subject":
                    subject = h["value"]
                if h["name"].lower() == "from":
                    from_addr = h["value"]
            body_parts = detail.get("payload", {}).get("body", {})
            text = body_parts.get("data", "")
            if not text:
                # Walk parts
                parts = detail.get("payload", {}).get("parts", [])
                for p in parts:
                    if p.get("mimeType") == "text/plain":
                        text = p.get("body", {}).get("data", "")
                        break
            import base64
            if text:
                text = base64.urlsafe_b64decode(text.encode()).decode()
            return f"From: {from_addr}\nSubject: {subject}\n\n{text or snippet}"

        return "Unknown action. Use action='search' or action='read'."
