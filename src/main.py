#!/usr/bin/env python3
"""Main entry point for the Business Idea Evaluator.

Run this script to evaluate a business idea using the CrewAI multi-agent system.

Usage:
    python -m src.main "Your business idea here"

Or for interactive mode:
    python -m src.main
"""

import sys
import argparse
from pathlib import Path

# Add the project root to the path so we can import src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.crew import run_evaluation
from src.config import Config


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Evaluate a business idea using AI-powered multi-agent analysis"
    )
    parser.add_argument(
        "business_idea",
        nargs="?",
        default=None,
        help="Description of the business idea to evaluate",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path for the report (JSON format)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    return parser.parse_args()


def interactive_input():
    """Prompt for business idea input interactively."""
    print("\n" + "=" * 60)
    print("  Business Idea Evaluator - Multi-Agent AI Analysis")
    print("=" * 60)
    print("\nEnter your business idea below (press Ctrl+D to finish):\n")
    idea = sys.stdin.read().strip()
    return idea


def main():
    """Main entry point."""
    args = parse_args()

    # Get the business idea
    if args.business_idea:
        business_idea = args.business_idea
    else:
        business_idea = interactive_input()

    if not business_idea:
        print("Error: No business idea provided. Use --help for usage information.")
        sys.exit(1)

    # Check for API keys
    if not Config.ANTHROPIC_API_KEY and not Config.OPENAI_API_KEY:
        print("\n⚠️  Warning: No API keys found in environment or .env file.")
        print("   Please set ANTHROPIC_API_KEY or OPENAI_API_KEY")
        print("   Copy .env.example to .env and add your credentials.\n")

    # Run the evaluation
    print("\n🔍 Analyzing business idea...\n")
    result = run_evaluation(
        business_idea=business_idea,
        output_file=args.output,
    )

    # Print the final report
    print("\n" + "=" * 60)
    print("  FINAL EVALUATION REPORT")
    print("=" * 60)
    print(result["result"])
    print("=" * 60)


if __name__ == "__main__":
    main()