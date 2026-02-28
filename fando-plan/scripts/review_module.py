#!/usr/bin/env python3
"""
review_module.py - DSPy Module wrapper for domain-specific plan review

Provides DomainReviewModule which wraps ChainOfThought around a domain's
Signature, enabling independent GEPA optimization per domain.

Usage:
    from review_module import DomainReviewModule

    module = DomainReviewModule(domain="security")
    prediction = module.forward(
        plan="Implement user auth...",
        other_reviewers="none",
        security_level="public"
    )
"""
# DSPy import - optional dependency
try:
    import dspy

    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False

    # Create a dummy dspy module for type checking when DSPy is not available
    class DummyModule:
        pass

    class DummyDSPy:
        Module = DummyModule

    dspy = DummyDSPy()  # type: ignore

if DSPY_AVAILABLE:
    from review_signatures import DOMAIN_SIGNATURES
else:
    # Empty registry when DSPy is not available
    DOMAIN_SIGNATURES = {}


if DSPY_AVAILABLE:

    class DomainReviewModule(dspy.Module):
        """DSPy module that performs a plan review for a specific domain.

        Wraps ChainOfThought around the domain's Signature. Can be optimized
        independently via GEPA.
        """

        def __init__(self, domain: str):
            super().__init__()
            if domain not in DOMAIN_SIGNATURES:
                raise ValueError(
                    f"Unknown domain: {domain}. Available: {list(DOMAIN_SIGNATURES)}"
                )
            self.domain = domain
            self.reviewer = dspy.ChainOfThought(DOMAIN_SIGNATURES[domain])

        def forward(
            self,
            plan: str,
            other_reviewers: str,
            security_level: str = "public",
        ) -> dspy.Prediction:
            return self.reviewer(
                plan=plan,
                other_reviewers=other_reviewers,
                security_level=security_level,
            )
else:
    # Stub class when DSPy is not installed
    class DomainReviewModule:  # type: ignore
        """Stub class when DSPy is not installed."""

        def __init__(self, domain: str):
            raise ImportError("DSPy is required: uv pip install dspy>=2.6.0")
