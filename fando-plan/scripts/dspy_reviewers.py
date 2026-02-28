#!/usr/bin/env python3
"""
dspy_reviewers.py - Minimal compatibility facade for DSPy review system

This module provides backward compatibility imports. The actual implementation
is split into focused modules:

Core runtime modules (import these directly for new code):
- review_runtime.py: run_dspy_review orchestration
- review_conversion.py: prediction_to_review_output, prediction_to_parse_result
- review_signatures.py: Domain-specific DSPy Signatures
- review_module.py: DomainReviewModule class

Training modules (import these directly for training/optimization):
- training_metric.py: ReviewExample, review_metric
- training_store.py: collect_training_example, save_training_example, load_training_examples

Path configuration:
- paths.py: get_optimized_dir, get_training_dir, get_plan_reviews_dir

This facade is maintained for backward compatibility. New code should import
from the specific modules listed above.
"""
import logging

logger = logging.getLogger(__name__)

# DSPy import - optional dependency
try:
    import dspy

    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False
    dspy = None


# ===========================================================================
# Re-exports from split modules
# ===========================================================================

# Signatures and registry
from review_signatures import DOMAIN_SIGNATURES

# Individual Signature classes for direct access (only when DSPy is available)
if DSPY_AVAILABLE:
    from review_signatures import (
        SecurityReviewSignature,
        FrontendReviewSignature,
        APIReviewSignature,
        DataReviewSignature,
        DevOpsReviewSignature,
        PerformanceReviewSignature,
        ArchitectReviewSignature,
    )

# DSPy Module
if DSPY_AVAILABLE:
    from review_module import DomainReviewModule
else:
    DomainReviewModule = None  # type: ignore

# Runtime orchestration
from review_runtime import run_dspy_review, save_optimized_module, load_optimized_module

# Output conversion
from review_conversion import (
    DSPyReviewError,
    prediction_to_review_output,
    prediction_to_parse_result,
)

# Training and evaluation
from training_metric import (
    ReviewExample,
    review_metric,
    # Constants
    SIGNIFICANT_WORD_MIN_LENGTH,
    FINDING_ADDRESS_THRESHOLD,
    DOMAIN_FOCUS_WEIGHT_IN_LANE,
    DOMAIN_FOCUS_WEIGHT_OUT_OF_LANE,
)

# Data collection and persistence
from training_store import (
    collect_training_example,
    save_training_example,
    load_training_examples,
)

# Path configuration
from paths import get_optimized_dir, get_training_dir

# Re-export DSPY_AVAILABLE for convenience
_DSPY_AVAILABLE = DSPY_AVAILABLE

# Export __all__ for explicit imports (minimal compatibility facade)
__all__ = [
    # Most commonly used convenience imports
    "DSPY_AVAILABLE",
    "DOMAIN_SIGNATURES",
    "run_dspy_review",
    "prediction_to_review_output",
    "prediction_to_parse_result",
    "DSPyReviewError",
    "ReviewExample",
    "review_metric",
    "collect_training_example",
    "save_training_example",
    "load_training_examples",
    "save_optimized_module",
    "load_optimized_module",
    "get_optimized_dir",
    "get_training_dir",
]


# ===========================================================================
# CLI
# ===========================================================================

def main():
    """CLI for testing DSPy reviewer integration."""
    import argparse

    parser = argparse.ArgumentParser(
        description="DSPy-based plan review system"
    )
    parser.add_argument("--check", action="store_true", help="Check DSPy availability")
    parser.add_argument(
        "--list-domains", action="store_true", help="List available domain signatures"
    )
    parser.add_argument("--stats", action="store_true", help="Training data statistics")

    args = parser.parse_args()

    if args.check:
        if DSPY_AVAILABLE:
            version = getattr(dspy, "__version__", "unknown")
            print(f"DSPy available: {version}")
            print(f"Domains: {', '.join(DOMAIN_SIGNATURES)}")
        else:
            print("DSPy not installed. Run: uv pip install dspy>=2.6.0")
        return

    if args.list_domains:
        for name, sig_cls in DOMAIN_SIGNATURES.items():
            doc_first_line = (sig_cls.__doc__ or "").strip().splitlines()[0]
            print(f"  {name}: {doc_first_line}")
        return

    if args.stats:
        examples = load_training_examples()
        if not examples:
            print("No training data found.")
            print(f"  Expected location: {get_training_dir()}")
            return

        domains: dict[str, int] = {}
        for ex in examples:
            domains[ex.domain] = domains.get(ex.domain, 0) + 1

        print(f"Training data: {len(examples)} examples")
        for domain, count in sorted(domains.items()):
            print(f"  {domain}: {count}")
        return

    print("DSPy reviewer system ready." if DSPY_AVAILABLE else "DSPy not installed.")
    print("Use --check, --list-domains, or --stats for info.")


if __name__ == "__main__":
    main()
