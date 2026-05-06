#!/usr/bin/env python3
"""CLI launcher for CMO daemon."""
import subprocess, sys, os
from pathlib import Path

venv_python = Path(__file__).parent.parent / ".venv" / "bin" / "python"
os.execv(str(venv_python), [str(venv_python), str(Path(__file__).with_suffix(".py").parent / "cmo_daemon.py")])
