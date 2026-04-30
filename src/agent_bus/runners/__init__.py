"""Startup wrappers — one file per agent for tmux process launch."""

from .cfo_runner import main as run_cfo
from .ceo_runner import main as run_ceo

__all__ = ["run_cfo", "run_ceo"]
