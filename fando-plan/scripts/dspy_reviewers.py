#!/usr/bin/env python3
"""
dspy_reviewers.py - Experimental DSPy integration for reviewer prompt optimization

STATUS: Experimental - scaffolded for future GEPA optimization when training data exists.

This module provides DSPy signatures for plan reviews. Once we have historical
review data (good/bad reviews with outcomes), we can use GEPA to optimize the
reviewer prompts automatically.

Current state:
- Signatures defined for each reviewer type
- Metric function scaffolded (needs real evaluation logic)
- GEPA integration ready but disabled

To activate:
1. Collect training data from fando-plan sessions
2. Implement the metric function with real evaluation
3. Run GEPA optimization
4. Export optimized prompts back to profile markdown files

Usage (future):
    from dspy_reviewers import optimize_reviewers, ReviewerModule

    # When we have data
    optimized = optimize_reviewers(training_data, validation_data)
    optimized.save("optimized_reviewers.json")
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# DSPy import - optional dependency
try:
    import dspy
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False
    dspy = None


# --- Data Classes for Training Data ---

@dataclass
class ReviewExample:
    """A single review example for training/evaluation."""
    plan: str                      # The plan that was reviewed
    domain: str                    # Reviewer domain (security, frontend, etc)
    other_domains: list[str]       # What other reviewers covered
    review_output: str             # The review findings

    # Evaluation signals (filled in after the fact)
    findings_acted_on: list[str]   # Which findings led to plan changes
    findings_ignored: list[str]    # Which findings were noise
    missed_issues: list[str]       # Issues found later that should have been caught
    stayed_in_lane: bool           # Did reviewer stick to their domain?

    # Optional metadata
    plan_id: Optional[str] = None
    iteration: Optional[int] = None


@dataclass
class ReviewMetricResult:
    """Result from evaluating a review."""
    score: float                   # 0.0 to 1.0
    feedback: str                  # Textual explanation for GEPA
    precision: float               # Findings that were useful / total findings
    recall: float                  # Issues caught / total issues
    domain_focus: float            # How well it stayed in lane


# --- DSPy Signatures ---

if DSPY_AVAILABLE:

    class PlanReviewSignature(dspy.Signature):
        """Review an implementation plan from a specialist perspective.

        You are one of several specialist reviewers. You have the FULL plan for
        context - understand WHY decisions were made. But only flag issues in
        YOUR domain. Other specialists cover other areas.
        """

        plan: str = dspy.InputField(
            desc="The full implementation plan to review"
        )
        domain: str = dspy.InputField(
            desc="Your specialist domain (security, frontend, api, data, devops, performance)"
        )
        other_reviewers: str = dspy.InputField(
            desc="Domains covered by other reviewers (don't duplicate their work)"
        )
        security_level: str = dspy.InputField(
            desc="Security context: personal, internal, public, or enterprise"
        )

        findings: str = dspy.OutputField(
            desc="Your findings as [HIGH/MEDIUM/LOW/NITPICK] bullets, only for your domain"
        )
        summary: str = dspy.OutputField(
            desc="Count of findings by level, or 'LGTM - no concerns in my domain'"
        )


    class SecurityReviewSignature(PlanReviewSignature):
        """Security-focused review signature with additional context."""

        # Inherits all fields, can add security-specific ones
        pass


    class FrontendReviewSignature(PlanReviewSignature):
        """Frontend/UX-focused review signature."""
        pass


    class APIReviewSignature(PlanReviewSignature):
        """API design-focused review signature."""
        pass


    # --- Reviewer Module ---

    class ReviewerModule(dspy.Module):
        """DSPy module that performs a plan review."""

        def __init__(self, domain: str):
            super().__init__()
            self.domain = domain
            self.reviewer = dspy.ChainOfThought(PlanReviewSignature)

        def forward(self, plan: str, other_reviewers: str, security_level: str = "public"):
            return self.reviewer(
                plan=plan,
                domain=self.domain,
                other_reviewers=other_reviewers,
                security_level=security_level,
            )


# --- Metric Function ---

def review_metric(
    gold: ReviewExample,
    pred: any,
    trace: any = None,
    predictor_name: str = None,
    predictor_trace: any = None,
) -> dict:
    """
    Evaluate a review's quality for GEPA optimization.

    Returns both a score and textual feedback explaining the score.
    GEPA uses the textual feedback to guide prompt mutations.

    Args:
        gold: The ground truth example with evaluation signals
        pred: The model's prediction (review output)
        trace: Execution trace (optional)
        predictor_name: Name of the predictor being evaluated
        predictor_trace: Predictor-specific trace

    Returns:
        Dict with 'score' (float) and 'feedback' (str)
    """
    feedback_parts = []
    scores = []

    # --- Precision: Were the findings useful? ---
    # TODO: Parse pred.findings and compare to gold.findings_acted_on
    # For now, placeholder
    precision = 0.5
    scores.append(precision)
    feedback_parts.append(f"Precision: {precision:.0%} of findings were acted upon")

    # --- Recall: Did it catch the important issues? ---
    # TODO: Check if gold.missed_issues were in pred.findings
    recall = 0.5
    scores.append(recall)
    feedback_parts.append(f"Recall: {recall:.0%} of important issues were caught")

    # --- Domain Focus: Did it stay in its lane? ---
    # TODO: Check if findings are within the reviewer's domain
    domain_focus = 1.0 if gold.stayed_in_lane else 0.5
    scores.append(domain_focus)
    if not gold.stayed_in_lane:
        feedback_parts.append("Domain focus: Reviewer flagged issues outside their domain")
    else:
        feedback_parts.append("Domain focus: Reviewer stayed in their lane")

    # --- Actionability: Was the feedback useful? ---
    # TODO: Analyze whether findings have clear remediation steps
    actionability = 0.5
    scores.append(actionability)

    # Combine scores (weighted average)
    weights = [0.3, 0.3, 0.2, 0.2]  # precision, recall, focus, actionability
    final_score = sum(s * w for s, w in zip(scores, weights))

    return {
        'score': final_score,
        'feedback': '\n'.join(feedback_parts),
        'precision': precision,
        'recall': recall,
        'domain_focus': domain_focus,
        'actionability': actionability,
    }


# --- GEPA Optimization ---

def optimize_reviewers(
    trainset: list[ReviewExample],
    valset: list[ReviewExample],
    reflection_model: str = "claude-sonnet-4-20250514",
    auto: str = "light",
) -> Optional['ReviewerModule']:
    """
    Optimize reviewer prompts using GEPA.

    Args:
        trainset: Training examples with evaluation signals
        valset: Validation examples
        reflection_model: Model for GEPA's reflection step
        auto: Budget preset ('light', 'medium', 'heavy')

    Returns:
        Optimized ReviewerModule, or None if DSPy unavailable
    """
    if not DSPY_AVAILABLE:
        print("DSPy not installed. Run: pip install dspy")
        return None

    if len(trainset) < 10:
        print(f"Warning: Only {len(trainset)} training examples. GEPA works best with 50+")

    # Create base module
    # TODO: Support multiple domains
    module = ReviewerModule(domain="security")

    # Configure GEPA
    gepa = dspy.GEPA(
        metric=review_metric,
        reflection_lm=dspy.LM(model=reflection_model),
        auto=auto,
    )

    # Run optimization
    optimized = gepa.compile(
        student=module,
        trainset=trainset,
        valset=valset,
    )

    return optimized


# --- Data Collection Helpers ---

def load_review_history(history_dir: Path) -> list[ReviewExample]:
    """
    Load historical reviews from fando-plan sessions.

    Looks for plan-reviews in ~/.claude/plan-reviews/ and extracts
    examples that can be used for training.

    Args:
        history_dir: Path to plan-reviews directory

    Returns:
        List of ReviewExample (without evaluation signals filled in)
    """
    examples = []

    if not history_dir.exists():
        return examples

    # TODO: Parse historical review files
    # Format: {project}/{date}-{slug}.md
    # Each file contains plan versions and reviewer feedback

    for project_dir in history_dir.iterdir():
        if not project_dir.is_dir():
            continue

        for review_file in project_dir.glob("*.md"):
            # TODO: Parse the review file structure
            # Extract: plan content, reviewer outputs, iteration history
            pass

    return examples


def export_optimized_prompts(module: 'ReviewerModule', output_dir: Path):
    """
    Export optimized prompts back to profile markdown files.

    After GEPA optimization, this extracts the learned prompts and
    writes them to the references/profiles/ directory.

    Args:
        module: Optimized ReviewerModule from GEPA
        output_dir: Path to profiles directory
    """
    if not DSPY_AVAILABLE:
        return

    # TODO: Extract optimized instructions from module
    # Write to {domain}.md files
    pass


# --- CLI ---

def main():
    """CLI for testing DSPy integration."""
    import argparse

    parser = argparse.ArgumentParser(description='DSPy reviewer optimization (experimental)')
    parser.add_argument('--check', action='store_true', help='Check if DSPy is available')
    parser.add_argument('--load-history', type=Path, help='Load review history from directory')
    parser.add_argument('--stats', action='store_true', help='Show training data statistics')

    args = parser.parse_args()

    if args.check:
        if DSPY_AVAILABLE:
            print(f"DSPy available: {dspy.__version__ if hasattr(dspy, '__version__') else 'yes'}")
        else:
            print("DSPy not installed. Run: pip install dspy")
        return

    if args.load_history:
        examples = load_review_history(args.load_history)
        print(f"Loaded {len(examples)} review examples")

        if args.stats and examples:
            domains = {}
            for ex in examples:
                domains[ex.domain] = domains.get(ex.domain, 0) + 1
            print("\nExamples by domain:")
            for domain, count in sorted(domains.items()):
                print(f"  {domain}: {count}")

    print("\nDSPy reviewer optimization is experimental.")
    print("Collect training data from fando-plan sessions, then run optimization.")


if __name__ == '__main__':
    main()
