"""GWS Command Tool — direct access to gws CLI for Google Workspace operations."""
from crewai.tools import BaseTool
from pydantic import Field
from pathlib import Path
import subprocess
import json
from typing import Optional

GWS_BIN = Path.home() / "bin" / "gws"


class GWSCommandTool(BaseTool):
    name: str = Field(default="GWSCommand")
    description: str = (
        "Execute gws CLI commands for Google Workspace (Drive, Gmail, Calendar, Sheets). "
        "Use this for direct Drive file operations, Gmail sending, Calendar management. "
        "Example: service='drive', resource='files', method='list' "
        "Example: service='gmail', resource='users', sub_resource='messages', method='send' "
        "Returns JSON output from gws."
    )

    def _run(
        self,
        service: str,
        resource: str,
        method: str,
        sub_resource: str = "",
        params: str = "{}",
        json_body: str = "",
    ) -> str:
        args = [str(GWS_BIN), service, resource]
        if sub_resource:
            args.append(sub_resource)
        args.extend([method, "--params", params])
        if json_body:
            args.extend(["--json", json_body])

        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return f"gws error: {result.stderr}"
        return result.stdout[:3000]  # Truncate
