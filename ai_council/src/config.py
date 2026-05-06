"""Configuration for AI Council crew."""

import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"  # ai_council/src/config.py → project root
load_dotenv(env_path)


class Config:
    ANTHROPIC_AUTH_TOKEN = os.getenv("ANTHROPIC_AUTH_TOKEN", "")
    ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "")
    VERBOSE = os.getenv("VERBOSE", "true").lower() == "true"

    PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


# Global model
MODEL_NAME = "MiniMax-M2.7"