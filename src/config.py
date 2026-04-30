"""Configuration settings for the business idea evaluator crew."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)


class Config:
    """Application configuration loaded from environment variables."""

    # Custom Anthropic-compatible API (e.g., Third-party Claude wrappers)
    ANTHROPIC_AUTH_TOKEN = os.getenv("ANTHROPIC_AUTH_TOKEN", "")
    ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "")

    # Crew settings
    VERBOSE = os.getenv("VERBOSE", "true").lower() == "true"
    MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "15"))

    # Output directory for reports
    OUTPUT_DIR = Path(__file__).parent.parent / "output"
    OUTPUT_DIR.mkdir(exist_ok=True)


# Global model name
MODEL_NAME = "MiniMax-M2.7"