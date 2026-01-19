#!/usr/bin/env python3
"""
parse_verification.py - Parse Codex verification response

Usage:
    echo "$CODEX_RESPONSE" | python3 parse_verification.py
    python3 parse_verification.py < response.txt
"""
import argparse
import json
import re
import sys
from dataclasses import dataclass, field


@dataclass
class VerificationItem:
    category: str  # MATCH, IMPROVEMENT, REGRESSION, MISSING, UNPLANNED
    description: str
    details: str = ""


@dataclass
class VerificationResult:
    matches: int = 0
    improvements: int = 0
    regressions: int = 0
    missing: int = 0
    unplanned: int = 0
    items: list[VerificationItem] = field(default_factory=list)
    summary: str = ""
    attention_items: list[str] = field(default_factory=list)
    error: str | None = None


def parse_verification(response: str) -> VerificationResult:
    """
    Parse structured verification response from Codex.

    Expected format:
    ## Verification Results
    - [MATCH] Description
    - [IMPROVEMENT] Description
    - [REGRESSION] Description - needs attention
    - [MISSING] Description
    - [UNPLANNED] Description

    ## Summary
    X matches, Y improvements, Z regressions, W missing, V unplanned
    """
    result = VerificationResult()

    if not response.strip():
        result.error = "Empty response from Codex"
        return result

    # Find verification results section
    # Try multiple patterns to be flexible
    verification_patterns = [
        r'## Verification Results?\s*\n(.*?)(?=\n## |\Z)',
        r'### Verification Results?\s*\n(.*?)(?=\n### |\n## |\Z)',
        r'\*\*Verification Results?\*\*\s*\n(.*?)(?=\n\*\*|\n## |\Z)',
    ]

    text = None
    for pattern in verification_patterns:
        match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
        if match:
            text = match.group(1)
            break

    if not text:
        # Try to find items anywhere in the response
        text = response

    # Parse items with [CATEGORY] markers
    # Pattern matches: - [CATEGORY] description (possibly multiline until next item or section)
    category_pattern = re.compile(
        r'^[-*]\s*\[(MATCH|IMPROVEMENT|REGRESSION|MISSING|UNPLANNED)\]\s*(.+?)(?=^[-*]\s*\[|^##|^[-*]\s*$|\Z)',
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )

    for match in category_pattern.finditer(text):
        category = match.group(1).upper()
        description = match.group(2).strip()

        # Clean up description - remove trailing whitespace and newlines
        description = re.sub(r'\s+', ' ', description).strip()

        item = VerificationItem(
            category=category,
            description=description
        )
        result.items.append(item)

        if category == 'MATCH':
            result.matches += 1
        elif category == 'IMPROVEMENT':
            result.improvements += 1
        elif category == 'REGRESSION':
            result.regressions += 1
            result.attention_items.append(f"[REGRESSION] {description}")
        elif category == 'MISSING':
            result.missing += 1
            result.attention_items.append(f"[MISSING] {description}")
        elif category == 'UNPLANNED':
            result.unplanned += 1

    # Build summary
    total = result.matches + result.improvements + result.regressions + result.missing + result.unplanned

    if total == 0:
        result.error = "No verification items found in response"
        return result

    result.summary = (
        f"{result.matches} matches, {result.improvements} improvements, "
        f"{result.regressions} regressions, {result.missing} missing, "
        f"{result.unplanned} unplanned"
    )

    return result


def format_result_text(result: VerificationResult) -> str:
    """Format verification result as readable text."""
    lines = []

    if result.error:
        lines.append(f"Error: {result.error}")
        return '\n'.join(lines)

    lines.append("## Verification Results\n")

    # Group by category
    categories = ['MATCH', 'IMPROVEMENT', 'REGRESSION', 'MISSING', 'UNPLANNED']

    for category in categories:
        items = [i for i in result.items if i.category == category]
        if items:
            for item in items:
                marker = f"[{item.category}]"
                lines.append(f"- {marker} {item.description}")

    lines.append(f"\n## Summary\n{result.summary}")

    if result.attention_items:
        lines.append("\n## Attention Needed\n")
        for item in result.attention_items:
            lines.append(f"- {item}")

    return '\n'.join(lines)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Parse Codex verification response',
        epilog='Response is read from stdin'
    )
    parser.add_argument(
        '--format',
        choices=['text', 'json'],
        default='text',
        help='Output format'
    )
    parser.add_argument(
        '--summary-only',
        action='store_true',
        help='Output summary line only'
    )

    args = parser.parse_args()

    # Read response from stdin
    response = sys.stdin.read()

    if not response.strip():
        print("Error: No response provided on stdin", file=sys.stderr)
        sys.exit(1)

    result = parse_verification(response)

    if result.error and not result.items:
        if args.format == 'json':
            print(json.dumps({'error': result.error}))
        else:
            print(f"Error: {result.error}", file=sys.stderr)
        sys.exit(1)

    if args.format == 'json':
        output = {
            'matches': result.matches,
            'improvements': result.improvements,
            'regressions': result.regressions,
            'missing': result.missing,
            'unplanned': result.unplanned,
            'summary': result.summary,
            'items': [
                {'category': i.category, 'description': i.description}
                for i in result.items
            ],
            'attention_items': result.attention_items,
            'needs_attention': len(result.attention_items) > 0
        }
        if result.error:
            output['warning'] = result.error
        print(json.dumps(output, indent=2))
    else:
        if args.summary_only:
            print(result.summary)
        else:
            print(format_result_text(result))

    # Exit with code 1 if there are regressions or missing items
    if result.regressions > 0 or result.missing > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
