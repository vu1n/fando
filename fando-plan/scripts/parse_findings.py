#!/usr/bin/env python3
"""
parse_findings.py - Parse Codex review response to extract findings

Usage:
    echo "$CODEX_RESPONSE" | python3 parse_findings.py
    python3 parse_findings.py < response.txt

Output (JSON):
    {
        "high": 1,
        "medium": 2,
        "low": 0,
        "nitpick": 1,
        "lgtm": false,
        "findings": [
            {"level": "HIGH", "text": "Finding description..."},
            ...
        ],
        "should_stop": false,
        "stop_reason": null
    }
"""
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Finding:
    level: str
    text: str


@dataclass
class ParseResult:
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


def parse_findings(response: str) -> ParseResult:
    """
    Extract risk counts and findings from Codex response.

    Uses delimiter-based parsing on the ## Findings section,
    counting only lines that start with "- [LEVEL]" pattern.
    """
    result = ParseResult()

    if not response or not response.strip():
        result.error = "Empty response"
        result.raw = response
        return result

    # Check for LGTM
    result.lgtm = bool(re.search(
        r'LGTM.*(?:ready to implement|no further changes)',
        response,
        re.IGNORECASE
    ))

    # Look for findings section with clear markers
    findings_match = re.search(
        r'## Findings\s*\n(.*?)(?=\n## |\Z)',
        response,
        re.DOTALL
    )

    if not findings_match:
        # No findings section - might be LGTM or malformed
        if result.lgtm:
            result.should_stop = True
            result.stop_reason = "LGTM - plan approved"
        else:
            result.error = "No findings section found"
            result.raw = response
        return result

    findings_text = findings_match.group(1)

    # Parse individual findings with "- [LEVEL]" pattern
    # This avoids false positives from text containing "[HIGH]" etc.
    finding_pattern = re.compile(
        r'^-\s*\[(HIGH|MEDIUM|LOW|NITPICK)\]\s*(.+?)(?=^-\s*\[|$)',
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )

    for match in finding_pattern.finditer(findings_text):
        level = match.group(1).upper()
        text = match.group(2).strip()

        result.findings.append(Finding(level=level, text=text))

        if level == 'HIGH':
            result.high += 1
        elif level == 'MEDIUM':
            result.medium += 1
        elif level == 'LOW':
            result.low += 1
        elif level == 'NITPICK':
            result.nitpick += 1

    # Determine if we should stop
    if result.lgtm or (result.high == 0 and result.medium == 0):
        result.should_stop = True
        if result.lgtm:
            result.stop_reason = "LGTM - plan approved"
        elif result.low == 0 and result.nitpick == 0:
            result.stop_reason = "No findings - plan approved"
        else:
            result.stop_reason = "Only LOW/NITPICK findings remain"

    return result


def check_for_loops(current: ParseResult, history: list[ParseResult]) -> Optional[str]:
    """
    Detect if Codex is looping on the same findings.

    Returns a warning message if looping detected, None otherwise.
    """
    if len(history) < 2:
        return None

    # Get current HIGH/MEDIUM finding texts
    current_issues = {
        f.text[:100] for f in current.findings
        if f.level in ('HIGH', 'MEDIUM')
    }

    if not current_issues:
        return None

    # Check last 2 iterations for same issues
    for prev in history[-2:]:
        prev_issues = {
            f.text[:100] for f in prev.findings
            if f.level in ('HIGH', 'MEDIUM')
        }

        overlap = current_issues & prev_issues
        if len(overlap) >= len(current_issues) * 0.7:  # 70% overlap
            return f"Codex appears to be repeating findings. {len(overlap)} issues unchanged."

    return None


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Parse Codex review findings',
        epilog='Response is read from stdin'
    )
    parser.add_argument(
        '--format',
        choices=['json', 'summary', 'counts'],
        default='json',
        help='Output format (default: json)'
    )

    args = parser.parse_args()

    # Read response from stdin
    response = sys.stdin.read()

    if not response.strip():
        print("Error: No response provided on stdin", file=sys.stderr)
        sys.exit(1)

    # Parse
    result = parse_findings(response)

    # Output based on format
    if args.format == 'json':
        # Convert to dict, handling dataclass fields
        output = {
            'high': result.high,
            'medium': result.medium,
            'low': result.low,
            'nitpick': result.nitpick,
            'lgtm': result.lgtm,
            'findings': [{'level': f.level, 'text': f.text} for f in result.findings],
            'should_stop': result.should_stop,
            'stop_reason': result.stop_reason,
            'error': result.error,
        }
        print(json.dumps(output, indent=2))

    elif args.format == 'summary':
        if result.error:
            print(f"Error: {result.error}")
        else:
            print(f"Findings: {result.high} HIGH, {result.medium} MEDIUM, "
                  f"{result.low} LOW, {result.nitpick} NITPICK")
            if result.lgtm:
                print("Status: LGTM - ready to implement")
            elif result.should_stop:
                print(f"Status: {result.stop_reason}")
            else:
                print("Status: Continue iterating")

    elif args.format == 'counts':
        print(f"{result.high} {result.medium} {result.low} {result.nitpick}")

    # Exit with non-zero if there was an error
    if result.error:
        sys.exit(1)


if __name__ == '__main__':
    main()
