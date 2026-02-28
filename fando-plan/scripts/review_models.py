#!/usr/bin/env python3
"""
review_models.py - Shared data models for review system

Centralizes dataclass definitions used across multiple review modules
to eliminate duplication and ensure schema consistency.

Provides:
- Finding: Base finding structure (level, text)
- AnnotatedFinding: Finding with reviewer source tracking
- ParseResult: Structured parse output with counts and findings list
- ReviewResult: Single reviewer result with output, findings, and timing
- ParallelReviewResult: Aggregated results from multiple reviewers

Usage:
    from review_models import Finding, ParseResult, ReviewResult, ParallelReviewResult

    result = ParseResult()
    result.findings.append(Finding(level="HIGH", text="Missing auth"))
"""
from dataclasses import dataclass, field
from typing import Optional


# ===========================================================================
# Core Finding Models
# ===========================================================================

@dataclass
class Finding:
    """A single finding from a code review.

    Basic structure used across all review modules to ensure consistency.
    """
    level: str
    text: str


@dataclass
class AnnotatedFinding(Finding):
    """A finding with additional metadata about its source.

    Extends Finding to track which reviewer produced the finding,
    useful for aggregation and deduplication.
    """
    source: str  # which reviewer produced this finding


# ===========================================================================
# Result Models
# ===========================================================================

@dataclass
class ParseResult:
    """Structured result from parsing a review response.

    Contains counts by severity level, list of findings, and metadata
    about whether the review passed or needs iteration.
    """
    high: int = 0
    medium: int = 0
    low: int = 0
    nitpick: int = 0
    lgtm: bool = False
    findings: list[Finding] = field(default_factory=list)
    should_stop: bool = False
    stop_reason: Optional[str] = None
    error: Optional[str] = None
    raw: Optional[str] = None


@dataclass
class ReviewResult:
    """Result from a single reviewer's analysis.

    Combines the raw output text with structured findings and metadata.
    """
    profile: str
    output: str = ""
    findings: Optional[ParseResult] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0


@dataclass
class ParallelReviewResult:
    """Aggregated results from multiple parallel reviewers.

    Collects individual ReviewResult objects and provides summary
    statistics across all reviewers.
    """
    results: dict[str, ReviewResult] = field(default_factory=dict)
    total_high: int = 0
    total_medium: int = 0
    total_low: int = 0
    total_nitpick: int = 0
    profiles_completed: int = 0
    profiles_failed: int = 0
    has_outstanding_issues: bool = False
