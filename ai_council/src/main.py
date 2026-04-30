#!/usr/bin/env python3
"""AI Council - Multi-agent strategic advisory board with memory."""

import sys
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.crew import execute_council_with_memory, run_council


def main():
    parser = argparse.ArgumentParser(description="AI Council - Strategic Advisory Board")
    parser.add_argument("topic", nargs="?", help="Topic to discuss with the council")
    parser.add_argument("-o", "--output", help="Output file for results")
    parser.add_argument("--no-memory", action="store_true", help="Disable memory saving")
    args = parser.parse_args()

    if not args.topic:
        print("Enter your topic for the AI Council: ")
        args.topic = sys.stdin.read().strip()

    if not args.topic:
        print("Error: No topic provided")
        sys.exit(1)

    if args.no_memory:
        import os
        os.environ["DISABLE_MEMORY"] = "true"

    # Execute with memory integration
    result = execute_council_with_memory(args.topic)

    print("\n" + "="*60)
    print("  AI COUNCIL FINAL RECOMMENDATION")
    print("="*60)
    print(result["result"])
    print("="*60)

    if result.get("memory_id"):
        print(f"\n📝 Memory saved: {result['memory_id']}")

    if args.output:
        with open(args.output, 'w') as f:
            f.write(str(result["result"]))

if __name__ == "__main__":
    main()