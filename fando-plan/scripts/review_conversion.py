#!/usr/bin/env python3
"""
review_conversion.py - Convert DSPy Predictions to expected output formats

Provides conversion functions from DSPy Prediction objects to both markdown
format (for parse_findings.py) and structured ParseResult format.

Usage:
    from review_conversion import prediction_to_review_output, prediction_to_parse_result

    # Convert to markdown (for parse_findings.py compatibility)
    text = prediction_to_review_output(prediction)

    # Convert directly to ParseResult (bypasses markdown roundtrip)
    result = prediction_to_parse_result(prediction)
"""
import re
from typing import Any


class DSPyReviewError(Exception):
    """Exception raised when DSPy review execution fails."""

    def __init__(self, message: str, original_exception: Exception | None = None):
        super().__init__(message)
        self.original_exception = original_exception


def prediction_to_review_output(prediction: Any) -> str:
    """Convert a DSPy Prediction into the text format parse_findings.py expects.

    Expected output:
        ## Findings
        - [HIGH] description...
        - [MEDIUM] description...

        ## Summary
        X high, Y medium...

    Raises:
        DSPyReviewError: If prediction is an Exception object
    """
    if isinstance(prediction, Exception):
        raise DSPyReviewError(
            f"DSPy review execution failed: {prediction}",
            original_exception=prediction
        )

    findings = getattr(prediction, "findings", "")
    summary = getattr(prediction, "summary", "")

    # Normalize findings: ensure each line starts with "- ["
    normalized_lines = []
    for line in findings.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # Ensure bullet prefix
        if re.match(r"\[(?:HIGH|MEDIUM|LOW|NITPICK)\]", line):
            line = f"- {line}"
        normalized_lines.append(line)

    findings_text = "\n".join(normalized_lines) if normalized_lines else "No issues found."

    return f"## Findings\n{findings_text}\n\n## Summary\n{summary}"


def prediction_to_parse_result(prediction: Any) -> "ParseResult":
    """Convert a DSPy Prediction directly to ParseResult (structured format).

    This bypasses the markdown roundtrip, improving efficiency and contract clarity.

    Args:
        prediction: DSPy Prediction object or Exception

    Returns:
        ParseResult with structured findings data

    Note: Import ParseResult lazily to avoid circular dependency.
    """
    # Lazy import to avoid circular dependency
    from parse_findings import ParseResult, Finding

    result = ParseResult()

    if isinstance(prediction, Exception):
        result.error = f"DSPY_EXECUTION_FAILED: {prediction}"
        result.should_stop = True
        result.stop_reason = "DSPy execution failed"
        result.raw = str(prediction)
        return result

    # Extract findings from prediction
    findings_text = getattr(prediction, "findings", "")
    summary = getattr(prediction, "summary", "")

    # Parse findings text to extract levels and items
    findings_list = []
    for line in findings_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        # Match patterns like "[HIGH]", "[MEDIUM]", etc.
        level_match = re.search(r'\[(HIGH|MEDIUM|LOW|NITPICK)\]', line.upper())
        if level_match:
            level = level_match.group(1)
            # Remove the level prefix to get the description
            desc = re.sub(r'\[(HIGH|MEDIUM|LOW|NITPICK)\]\s*', '', line, flags=re.IGNORECASE).strip()

            findings_list.append(Finding(level=level, text=desc))

            # Increment counts
            if level == "HIGH":
                result.high += 1
            elif level == "MEDIUM":
                result.medium += 1
            elif level == "LOW":
                result.low += 1
            elif level == "NITPICK":
                result.nitpick += 1

    result.findings = findings_list

    # Check for LGTM in summary
    result.lgtm = bool(re.search(
        r'LGTM.*(?:ready to implement|no further changes)',
        summary,
        re.IGNORECASE
    ))

    # Set should_stop if no high/medium findings
    result.should_stop = (result.high == 0 and result.medium == 0)
    if result.should_stop and not result.lgtm:
        result.stop_reason = "No outstanding issues"
    elif result.lgtm:
        result.stop_reason = "LGTM - ready to implement"

    result.raw = summary  # Store summary in raw field for reference

    return result
