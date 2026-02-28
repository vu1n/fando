#!/usr/bin/env python3
"""
training_metric.py - Training constants and evaluation metrics for GEPA

Provides constants for labeling training data and the review_metric function
used by GEPA to optimize DSPy reviewers.

Usage:
    from training_metric import ReviewExample, review_metric

    score_info = review_metric(gold_example, prediction)
    print(f"Score: {score_info['score']:.2%}")
"""
import re
from dataclasses import dataclass, field
from typing import Any


# ===========================================================================
# Training Labeling Constants and Policies
# ===========================================================================

# Minimum word length to consider a word "significant" for matching
SIGNIFICANT_WORD_MIN_LENGTH = 4

# Threshold for considering a finding "acted on" based on word overlap
# If > this fraction of significant words appear in the diff, count as addressed
FINDING_ADDRESS_THRESHOLD = 0.3

# Domain focus weight for staying in lane vs crossing domains
DOMAIN_FOCUS_WEIGHT_IN_LANE = 1.0
DOMAIN_FOCUS_WEIGHT_OUT_OF_LANE = 0.3


# ===========================================================================
# Training Data Structures
# ===========================================================================

@dataclass
class ReviewExample:
    """A labeled review example for training/evaluation."""

    plan: str
    domain: str
    other_domains: list[str]
    security_level: str
    review_output: str

    # Evaluation labels (filled after reviewing outcomes)
    findings_acted_on: list[str] = field(default_factory=list)
    findings_ignored: list[str] = field(default_factory=list)
    missed_issues: list[str] = field(default_factory=list)
    stayed_in_lane: bool = True
    severity_gold: dict[str, int] = field(default_factory=dict)  # {"HIGH": 2, "MEDIUM": 1, ...}

    # Metadata
    plan_id: str | None = None
    iteration: int | None = None


# ===========================================================================
# GEPA Metric
# ===========================================================================

def review_metric(
    gold: ReviewExample,
    pred: Any,
    trace: Any = None,
    **kwargs,
) -> dict[str, Any]:
    """Evaluate review quality for GEPA optimization.

    Scoring (0-1):
      - Precision  (25%): predicted findings ∩ findings_acted_on / total predicted
      - Recall     (25%): missed_issues caught in predicted / total missed
      - Domain focus (20%): stayed in lane
      - Actionability (15%): findings contain remediation language
      - Severity calibration (15%): HIGH/MEDIUM distribution matches gold

    Returns dict with 'score' (float 0-1) and 'feedback' (str for GEPA reflection).
    """
    findings_text = getattr(pred, "findings", "")
    pred_findings = _extract_finding_texts(findings_text)
    pred_levels = _extract_finding_levels(findings_text)

    feedback_parts = []

    # --- Precision (25%) ---
    if pred_findings and gold.findings_acted_on:
        acted_set = {f.lower()[:80] for f in gold.findings_acted_on}
        matched = sum(
            1
            for f in pred_findings
            if any(_text_overlap(f.lower()[:80], a) > 0.5 for a in acted_set)
        )
        precision = matched / len(pred_findings) if pred_findings else 0.0
    elif not pred_findings and not gold.findings_acted_on:
        precision = 1.0  # Both empty = correct
    elif not pred_findings:
        precision = 0.0 if gold.findings_acted_on else 1.0
    else:
        # Predictions exist but no gold labels — assume moderate
        precision = 0.5
    feedback_parts.append(f"Precision: {precision:.0%} of findings were acted upon")

    # --- Recall (25%) ---
    if gold.missed_issues:
        caught = sum(
            1
            for m in gold.missed_issues
            if any(
                _text_overlap(m.lower()[:80], f.lower()[:80]) > 0.5
                for f in pred_findings
            )
        )
        recall = caught / len(gold.missed_issues)
    elif not gold.missed_issues:
        recall = 1.0  # Nothing was missed
    else:
        recall = 0.5
    feedback_parts.append(f"Recall: {recall:.0%} of important issues caught")

    # --- Domain Focus (20%) ---
    domain_focus = DOMAIN_FOCUS_WEIGHT_IN_LANE if gold.stayed_in_lane else DOMAIN_FOCUS_WEIGHT_OUT_OF_LANE
    if not gold.stayed_in_lane:
        feedback_parts.append("Domain focus: reviewer flagged issues outside their domain")
    else:
        feedback_parts.append("Domain focus: reviewer stayed in their lane")

    # --- Actionability (15%) ---
    action_keywords = [
        "should", "consider", "add", "implement", "use", "change",
        "replace", "remove", "ensure", "validate", "protect", "require",
    ]
    if pred_findings:
        actionable_count = sum(
            1
            for f in pred_findings
            if any(kw in f.lower() for kw in action_keywords)
        )
        actionability = actionable_count / len(pred_findings)
    else:
        actionability = 1.0  # No findings = nothing needs to be actionable
    feedback_parts.append(f"Actionability: {actionability:.0%} of findings have remediation language")

    # --- Severity Calibration (15%) ---
    if gold.severity_gold and pred_levels:
        total_diff = 0
        total_expected = 0
        for level in ("HIGH", "MEDIUM", "LOW", "NITPICK"):
            expected = gold.severity_gold.get(level, 0)
            actual = pred_levels.get(level, 0)
            total_diff += abs(expected - actual)
            total_expected += expected
        if total_expected > 0:
            severity_cal = max(0.0, 1.0 - total_diff / (total_expected + 1))
        else:
            severity_cal = 1.0 if sum(pred_levels.values()) == 0 else 0.5
    else:
        severity_cal = 0.5  # No gold labels
    feedback_parts.append(f"Severity calibration: {severity_cal:.0%}")

    # --- Weighted combination ---
    weights = {
        "precision": 0.25,
        "recall": 0.25,
        "domain_focus": 0.20,
        "actionability": 0.15,
        "severity_cal": 0.15,
    }
    scores = {
        "precision": precision,
        "recall": recall,
        "domain_focus": domain_focus,
        "actionability": actionability,
        "severity_cal": severity_cal,
    }
    final_score = sum(scores[k] * weights[k] for k in weights)

    return {
        "score": final_score,
        "feedback": "\n".join(feedback_parts),
        **scores,
    }


# ===========================================================================
# Helper Functions
# ===========================================================================

def _extract_finding_texts(findings_str: str) -> list[str]:
    """Extract finding description texts from formatted findings string."""
    results = []
    for line in findings_str.strip().splitlines():
        m = re.match(r"^-?\s*\[(HIGH|MEDIUM|LOW|NITPICK)\]\s*(.+)", line.strip(), re.IGNORECASE)
        if m:
            results.append(m.group(2).strip())
    return results


def _extract_finding_levels(findings_str: str) -> dict[str, int]:
    """Count findings by severity level."""
    counts: dict[str, int] = {}
    for line in findings_str.strip().splitlines():
        m = re.match(r"^-?\s*\[(HIGH|MEDIUM|LOW|NITPICK)\]", line.strip(), re.IGNORECASE)
        if m:
            level = m.group(1).upper()
            counts[level] = counts.get(level, 0) + 1
    return counts


def _text_overlap(a: str, b: str) -> float:
    """Simple word-overlap similarity between two strings."""
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    return len(intersection) / max(len(words_a), len(words_b))
