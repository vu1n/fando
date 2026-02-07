#!/usr/bin/env python3
"""
optimize.py - GEPA optimization CLI for fando-plan reviewers

Optimizes DSPy reviewer Signatures using labeled training data and a
reflection model. Requires an API key only for the GEPA reflection LM
(one-time optimization cost).

Usage:
    # Show training data statistics
    python3 optimize.py --stats

    # Optimize a single domain
    python3 optimize.py --domain security --reflection-model openai/gpt-4o --auto light

    # Optimize all domains with training data
    python3 optimize.py --all --reflection-model openai/gpt-4o --auto light

    # Export optimized instructions to markdown for inspection
    python3 optimize.py --export

Training data location: ~/.claude/skills/fando-plan/training_data/*.json
Optimized modules:      ~/.claude/skills/fando-plan/optimized/{domain}.json
"""
import argparse
import json
import sys
from pathlib import Path

try:
    import dspy
except ImportError:
    print("DSPy is required: uv pip install dspy>=2.6.0", file=sys.stderr)
    sys.exit(1)

from dspy_reviewers import (
    DOMAIN_SIGNATURES,
    OPTIMIZED_DIR,
    TRAINING_DIR,
    DomainReviewModule,
    ReviewExample,
    load_training_examples,
    review_metric,
    save_optimized_module,
)


def show_stats():
    """Display training data statistics per domain."""
    examples = load_training_examples()

    if not examples:
        print("No training data found.")
        print(f"  Expected location: {TRAINING_DIR}")
        print("\nTraining data is collected automatically during fando-plan sessions.")
        print("Run a few plan reviews to generate data, then come back to optimize.")
        return

    # Group by domain
    domains: dict[str, list[ReviewExample]] = {}
    for ex in examples:
        domains.setdefault(ex.domain, []).append(ex)

    print(f"Training data: {len(examples)} total examples\n")
    print(f"{'Domain':<15} {'Count':>6} {'With Labels':>12} {'Avg Findings':>14}")
    print("-" * 50)

    for domain in sorted(domains):
        exs = domains[domain]
        labeled = sum(1 for e in exs if e.findings_acted_on or e.missed_issues)
        # Count average findings per example
        total_findings = 0
        for e in exs:
            total_findings += len(e.findings_acted_on) + len(e.findings_ignored)
        avg = total_findings / len(exs) if exs else 0

        print(f"{domain:<15} {len(exs):>6} {labeled:>12} {avg:>13.1f}")

    # GEPA readiness check
    print("\nGEPA readiness:")
    for domain in sorted(DOMAIN_SIGNATURES):
        if domain == "architect":
            continue  # Architect doesn't need separate optimization
        count = len(domains.get(domain, []))
        if count >= 50:
            status = "ready"
        elif count >= 10:
            status = f"usable ({count}/50 recommended)"
        elif count > 0:
            status = f"insufficient ({count}/10 minimum)"
        else:
            status = "no data"
        print(f"  {domain}: {status}")


def optimize_domain(
    domain: str,
    reflection_model: str,
    auto: str = "light",
    val_split: float = 0.2,
):
    """Run GEPA optimization for a single domain.

    Args:
        domain: Domain name (e.g. "security")
        reflection_model: Model for GEPA reflection (e.g. "openai/gpt-4o")
        auto: Budget preset ("light", "medium", "heavy")
        val_split: Fraction of data for validation
    """
    print(f"\n--- Optimizing: {domain} ---")

    examples = load_training_examples(domain=domain)
    if len(examples) < 5:
        print(f"  Not enough training data ({len(examples)} examples, need at least 5)")
        return None

    # Split into train/val
    split_idx = max(1, int(len(examples) * (1 - val_split)))
    trainset = examples[:split_idx]
    valset = examples[split_idx:]

    print(f"  Training: {len(trainset)}, Validation: {len(valset)}")

    if len(trainset) < 10:
        print(f"  Warning: only {len(trainset)} training examples. GEPA works best with 50+")

    # Convert ReviewExamples to DSPy Examples
    dspy_trainset = _to_dspy_examples(trainset)
    dspy_valset = _to_dspy_examples(valset)

    # Create base module
    module = DomainReviewModule(domain=domain)

    # Configure GEPA
    print(f"  Reflection model: {reflection_model}")
    print(f"  Budget: {auto}")

    gepa = dspy.GEPA(
        metric=review_metric,
        reflection_lm=dspy.LM(model=reflection_model),
        auto=auto,
    )

    # Run optimization
    print("  Running GEPA optimization...")
    optimized = gepa.compile(
        student=module,
        trainset=dspy_trainset,
        valset=dspy_valset,
    )

    # Save
    path = save_optimized_module(domain, optimized)
    print(f"  Saved optimized module: {path}")

    # Evaluate on validation set
    print("  Evaluating on validation set...")
    total_score = 0.0
    for ex in valset:
        dspy_ex = _to_dspy_example(ex)
        pred = optimized.forward(
            plan=dspy_ex.plan,
            other_reviewers=dspy_ex.other_reviewers,
            security_level=dspy_ex.security_level,
        )
        result = review_metric(ex, pred)
        total_score += result["score"]

    avg_score = total_score / len(valset) if valset else 0.0
    print(f"  Validation score: {avg_score:.2%}")

    return optimized


def export_optimized():
    """Export optimized instructions to markdown for human inspection."""
    if not OPTIMIZED_DIR.exists():
        print("No optimized modules found.")
        print(f"  Expected location: {OPTIMIZED_DIR}")
        return

    export_dir = Path("~/.claude/skills/fando-plan/exported_prompts").expanduser()
    export_dir.mkdir(parents=True, exist_ok=True)

    for json_file in sorted(OPTIMIZED_DIR.glob("*.json")):
        domain = json_file.stem
        print(f"  Exporting {domain}...")

        try:
            data = json.loads(json_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"    Error reading {json_file}: {e}")
            continue

        # Extract instructions from the saved module state
        md_path = export_dir / f"{domain}_optimized.md"
        lines = [f"# {domain.title()} Reviewer (GEPA-Optimized)\n"]
        lines.append(f"Source: `{json_file}`\n")

        # Walk the saved state to find instruction fields
        if isinstance(data, dict):
            _extract_instructions(data, lines, depth=0)

        md_path.write_text("\n".join(lines))
        print(f"    Written to {md_path}")

    print(f"\nAll exports in: {export_dir}")


def _extract_instructions(obj: dict, lines: list[str], depth: int):
    """Recursively extract instruction-like fields from saved module state."""
    for key, value in obj.items():
        if isinstance(value, str) and len(value) > 50:
            lines.append(f"\n{'#' * (depth + 2)} {key}\n")
            lines.append(value)
        elif isinstance(value, dict):
            lines.append(f"\n{'#' * (depth + 2)} {key}\n")
            _extract_instructions(value, lines, depth + 1)


def _to_dspy_examples(examples: list[ReviewExample]) -> list:
    """Convert ReviewExamples to DSPy Example objects."""
    return [_to_dspy_example(ex) for ex in examples]


def _to_dspy_example(ex: ReviewExample):
    """Convert a single ReviewExample to a DSPy Example."""
    other_reviewers = ", ".join(ex.other_domains) if ex.other_domains else "none"
    return dspy.Example(
        plan=ex.plan,
        other_reviewers=other_reviewers,
        security_level=ex.security_level,
        findings=ex.review_output,
        summary="",
    ).with_inputs("plan", "other_reviewers", "security_level")


def main():
    parser = argparse.ArgumentParser(
        description="GEPA optimization for fando-plan reviewers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --stats                              Show training data counts
  %(prog)s --domain security --auto light       Optimize security reviewer
  %(prog)s --all --reflection-model openai/gpt-4o  Optimize all domains
  %(prog)s --export                             Export optimized prompts to markdown
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--stats", action="store_true", help="Show training data statistics"
    )
    group.add_argument(
        "--domain",
        choices=[d for d in DOMAIN_SIGNATURES if d != "architect"],
        help="Optimize a single domain",
    )
    group.add_argument(
        "--all", action="store_true", help="Optimize all domains with sufficient data"
    )
    group.add_argument(
        "--export",
        action="store_true",
        help="Export optimized instructions to markdown",
    )

    parser.add_argument(
        "--reflection-model",
        default="openai/gpt-4o",
        help="Model for GEPA reflection step (default: openai/gpt-4o)",
    )
    parser.add_argument(
        "--auto",
        choices=["light", "medium", "heavy"],
        default="light",
        help="GEPA budget preset (default: light)",
    )
    parser.add_argument(
        "--val-split",
        type=float,
        default=0.2,
        help="Validation set fraction (default: 0.2)",
    )

    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    if args.export:
        export_optimized()
        return

    # Optimization mode
    if args.domain:
        optimize_domain(
            domain=args.domain,
            reflection_model=args.reflection_model,
            auto=args.auto,
            val_split=args.val_split,
        )
    elif args.all:
        domains_to_optimize = [d for d in DOMAIN_SIGNATURES if d != "architect"]
        for domain in domains_to_optimize:
            examples = load_training_examples(domain=domain)
            if len(examples) >= 5:
                optimize_domain(
                    domain=domain,
                    reflection_model=args.reflection_model,
                    auto=args.auto,
                    val_split=args.val_split,
                )
            else:
                print(f"\nSkipping {domain}: only {len(examples)} examples (need 5+)")


if __name__ == "__main__":
    main()
