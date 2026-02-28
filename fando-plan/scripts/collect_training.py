#!/usr/bin/env python3
"""
collect_training.py - Collect training data during plan review iterations

Standalone CLI for Claude to call during the SKILL.md iteration loop.
Reads review output from stdin, plan files from paths, and saves a
training example.

Usage:
    python3 collect_training.py \
      --domain security \
      --other-domains "frontend,api" \
      --security-level public \
      --plan-id "my-project-2026-02-06" \
      --iteration 1 \
      --plan-before /path/to/plan_v1.md \
      --plan-after /path/to/plan_v2.md \
      <<< "$REVIEW_OUTPUT"
"""
import argparse
import sys
from pathlib import Path


def main() -> None:
    from dspy_reviewers import collect_training_example, save_training_example

    parser = argparse.ArgumentParser(
        description="Collect a training example from a plan review iteration"
    )
    parser.add_argument(
        "--domain", required=True, help="Primary reviewer domain (e.g. security)"
    )
    parser.add_argument(
        "--other-domains",
        default="",
        help="Comma-separated other active domains",
    )
    parser.add_argument(
        "--security-level",
        default="public",
        choices=["personal", "internal", "public", "enterprise"],
        help="Security level (default: public)",
    )
    parser.add_argument(
        "--plan-id", required=True, help="Plan identifier (e.g. project-date)"
    )
    parser.add_argument(
        "--iteration", required=True, type=int, help="Iteration number"
    )
    parser.add_argument(
        "--plan-before",
        required=True,
        type=Path,
        help="Path to plan text before this iteration",
    )
    parser.add_argument(
        "--plan-after",
        required=True,
        type=Path,
        help="Path to plan text after addressing findings",
    )
    args = parser.parse_args()

    # Read review output from stdin
    review_output = sys.stdin.read()
    if not review_output.strip():
        print("Error: No review output on stdin", file=sys.stderr)
        sys.exit(1)

    # Read plan files with consistent error handling
    try:
        plan_before = args.plan_before.read_text()
    except OSError as e:
        print(f"Error: Failed to read plan-before file {args.plan_before}: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        plan_after = args.plan_after.read_text()
    except OSError as e:
        print(f"Error: Failed to read plan-after file {args.plan_after}: {e}", file=sys.stderr)
        sys.exit(1)

    other_domains = [d.strip() for d in args.other_domains.split(",") if d.strip()]

    # Create and save example
    example = collect_training_example(
        plan_before=plan_before,
        plan_after=plan_after,
        domain=args.domain,
        review_output=review_output,
        other_domains=other_domains,
        security_level=args.security_level,
        plan_id=args.plan_id,
        iteration=args.iteration,
    )

    path = save_training_example(example)

    acted = len(example.findings_acted_on)
    ignored = len(example.findings_ignored)
    print(f"Saved training example: {path}")
    print(f"  Domain: {example.domain}, Iteration: {example.iteration}")
    print(f"  Findings acted on: {acted}, ignored: {ignored}")


if __name__ == "__main__":
    main()
