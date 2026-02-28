#!/usr/bin/env python3
"""
training_store.py - Training data collection and persistence

Provides functions for collecting training examples from plan diff analysis,
and for saving/loading training examples from disk.

Usage:
    from training_store import collect_training_example, save_training_example, load_training_examples

    # Create training example from plan diff
    example = collect_training_example(plan_before, plan_after, "security", review_output, [])
    save_training_example(example)

    # Load examples for a domain
    examples = load_training_examples(domain="security")
"""
import json
import logging
import tempfile
from pathlib import Path

from constants import SIGNIFICANT_WORD_MIN_LENGTH, FINDING_ADDRESS_THRESHOLD
from paths import get_training_dir
from training_metric import (
    ReviewExample,
    _extract_finding_texts,
)

logger = logging.getLogger(__name__)


# ===========================================================================
# Training Data Collection
# ===========================================================================

def collect_training_example(
    plan_before: str,
    plan_after: str,
    domain: str,
    review_output: str,
    other_domains: list[str],
    security_level: str = "public",
    plan_id: str | None = None,
    iteration: int | None = None,
) -> ReviewExample:
    """Create a training example by comparing plan versions.

    Determines which findings were acted on by diffing plan_before vs plan_after.
    Findings whose described concern appears addressed in plan_after are marked
    as 'findings_acted_on'; the rest are 'findings_ignored'.
    """
    pred_findings = _extract_finding_texts(review_output)

    findings_acted_on = []
    findings_ignored = []

    # Simple heuristic: if key terms from a finding appear in the diff
    # (plan_after minus plan_before), the finding was likely addressed
    added_text = _get_added_text(plan_before, plan_after).lower()

    for finding in pred_findings:
        # Extract significant words from the finding
        sig_words = [w for w in finding.lower().split() if len(w) > SIGNIFICANT_WORD_MIN_LENGTH]
        if sig_words:
            matches = sum(1 for w in sig_words if w in added_text)
            if matches / len(sig_words) > FINDING_ADDRESS_THRESHOLD:
                findings_acted_on.append(finding)
            else:
                findings_ignored.append(finding)
        else:
            findings_ignored.append(finding)

    return ReviewExample(
        plan=plan_before,
        domain=domain,
        other_domains=other_domains,
        security_level=security_level,
        review_output=review_output,
        findings_acted_on=findings_acted_on,
        findings_ignored=findings_ignored,
        missed_issues=[],  # Can only be filled by later analysis
        stayed_in_lane=True,  # Default; can be relabeled
        plan_id=plan_id,
        iteration=iteration,
    )


def _get_added_text(before: str, after: str) -> str:
    """Return text present in after but not in before (line-level diff)."""
    before_lines = set(before.splitlines())
    after_lines = after.splitlines()
    added = [line for line in after_lines if line not in before_lines]
    return "\n".join(added)


# ===========================================================================
# Persistence
# ===========================================================================

def save_training_example(example: ReviewExample) -> Path:
    """Persist a training example to the training data directory."""
    get_training_dir().mkdir(parents=True, exist_ok=True)

    # Filename: {domain}_{plan_id or timestamp}.json
    name_part = example.plan_id or str(int(__import__("time").time()))
    iter_part = f"_iter{example.iteration}" if example.iteration is not None else ""
    path = get_training_dir() / f"{example.domain}_{name_part}{iter_part}.json"

    data = {
        "plan": example.plan,
        "domain": example.domain,
        "other_domains": example.other_domains,
        "security_level": example.security_level,
        "review_output": example.review_output,
        "findings_acted_on": example.findings_acted_on,
        "findings_ignored": example.findings_ignored,
        "missed_issues": example.missed_issues,
        "stayed_in_lane": example.stayed_in_lane,
        "severity_gold": example.severity_gold,
        "plan_id": example.plan_id,
        "iteration": example.iteration,
    }
    # Atomic write: temp file + rename
    temp_fd, temp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp"
    )
    try:
        import os
        with os.fdopen(temp_fd, 'w') as f:
            json.dump(data, f, indent=2)
        os.rename(temp_path, path)
    except Exception:
        # Clean up temp file on error
        try:
            import os
            os.unlink(temp_path)
        except Exception:
            pass
        raise
    return path


def load_training_examples(domain: str | None = None) -> list[ReviewExample]:
    """Load training examples from disk.

    Args:
        domain: Filter to a specific domain, or None for all.

    Returns:
        List of ReviewExample
    """
    examples = []
    if not get_training_dir().exists():
        return examples

    for f in sorted(get_training_dir().glob("*.json")):
        try:
            data = json.loads(f.read_text())
            if domain and data.get("domain") != domain:
                continue
            examples.append(
                ReviewExample(
                    plan=data["plan"],
                    domain=data["domain"],
                    other_domains=data.get("other_domains", []),
                    security_level=data.get("security_level", "public"),
                    review_output=data.get("review_output", ""),
                    findings_acted_on=data.get("findings_acted_on", []),
                    findings_ignored=data.get("findings_ignored", []),
                    missed_issues=data.get("missed_issues", []),
                    stayed_in_lane=data.get("stayed_in_lane", True),
                    severity_gold=data.get("severity_gold", {}),
                    plan_id=data.get("plan_id"),
                    iteration=data.get("iteration"),
                )
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Skipping malformed training file {f.name}: {e}")
            continue

    return examples
