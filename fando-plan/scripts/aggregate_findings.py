#!/usr/bin/env python3
"""
aggregate_findings.py - Merge and analyze findings from multiple reviewers

Usage:
    python3 aggregate_findings.py < parallel_review_results.json
    cat results.json | python3 aggregate_findings.py --detect-conflicts

Output (JSON):
    {
        "by_reviewer": {...},
        "all_findings": [...],
        "conflicts": [...],
        "summary": {...}
    }
"""
import json
import re
import sys
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional


@dataclass
class Finding:
    level: str
    text: str
    source: str  # which reviewer


@dataclass
class Conflict:
    finding_a: Finding
    finding_b: Finding
    description: str
    resolution_hint: Optional[str] = None


@dataclass
class AggregatedResult:
    by_reviewer: dict[str, list[Finding]] = field(default_factory=dict)
    all_findings: list[Finding] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    duplicates_removed: int = 0
    total_high: int = 0
    total_medium: int = 0
    total_low: int = 0
    total_nitpick: int = 0
    has_outstanding_issues: bool = False


# Common conflict patterns to detect
CONFLICT_PATTERNS = [
    {
        'name': 'rate_limit_conflict',
        'keywords_a': ['rate limit', 'throttle', 'restrict', 'limit requests'],
        'keywords_b': ['throughput', 'performance', 'scale', 'high volume'],
        'description': 'Rate limiting vs. throughput requirements',
        'hint': 'Consider tiered rate limits: strict for public APIs, relaxed for authenticated users'
    },
    {
        'name': 'client_vs_server_validation',
        'keywords_a': ['client-side validation', 'frontend validation', 'ui validation'],
        'keywords_b': ['server-side validation', 'backend validation', 'never trust client'],
        'description': 'Client-side vs. server-side validation approach',
        'hint': 'Both: client-side for UX, server-side for security'
    },
    {
        'name': 'caching_vs_consistency',
        'keywords_a': ['cache', 'caching', 'cache aggressively'],
        'keywords_b': ['consistency', 'real-time', 'up-to-date', 'stale data'],
        'description': 'Caching strategy vs. data consistency',
        'hint': 'Use cache invalidation strategies, consider TTL based on data sensitivity'
    },
    {
        'name': 'simplicity_vs_security',
        'keywords_a': ['simple', 'straightforward', 'minimal'],
        'keywords_b': ['security', 'secure', 'protection', 'defense in depth'],
        'description': 'Implementation simplicity vs. security requirements',
        'hint': 'Security is non-negotiable; simplify within security constraints'
    },
    {
        'name': 'deploy_vs_migration',
        'keywords_a': ['simple deploy', 'quick deploy', 'fast rollout'],
        'keywords_b': ['migration', 'data migration', 'schema change', 'backwards compatible'],
        'description': 'Deployment simplicity vs. migration complexity',
        'hint': 'Phased approach: deploy code first, migrate data incrementally'
    }
]


def normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    return re.sub(r'\s+', ' ', text.lower().strip())


def text_similarity(a: str, b: str) -> float:
    """Calculate similarity ratio between two texts."""
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def is_duplicate(finding_a: Finding, finding_b: Finding, threshold: float = 0.7) -> bool:
    """Check if two findings are duplicates based on text similarity."""
    if finding_a.level != finding_b.level:
        return False
    return text_similarity(finding_a.text, finding_b.text) >= threshold


def detect_conflict(finding_a: Finding, finding_b: Finding) -> Optional[Conflict]:
    """
    Check if two findings represent a conflict.

    Conflicts occur when reviewers from different domains have opposing recommendations.
    """
    # Only check findings from different reviewers
    if finding_a.source == finding_b.source:
        return None

    text_a = normalize_text(finding_a.text)
    text_b = normalize_text(finding_b.text)

    for pattern in CONFLICT_PATTERNS:
        # Check if finding_a matches keywords_a and finding_b matches keywords_b
        a_matches_a = any(kw in text_a for kw in pattern['keywords_a'])
        b_matches_b = any(kw in text_b for kw in pattern['keywords_b'])

        a_matches_b = any(kw in text_a for kw in pattern['keywords_b'])
        b_matches_a = any(kw in text_b for kw in pattern['keywords_a'])

        if (a_matches_a and b_matches_b) or (a_matches_b and b_matches_a):
            return Conflict(
                finding_a=finding_a,
                finding_b=finding_b,
                description=pattern['description'],
                resolution_hint=pattern['hint']
            )

    return None


def aggregate_findings(results: dict) -> AggregatedResult:
    """
    Aggregate findings from parallel review results.

    Args:
        results: Dictionary from run_parallel_reviews.py output

    Returns:
        AggregatedResult with merged findings, conflicts detected, and summaries
    """
    aggregated = AggregatedResult()

    # Handle both raw results dict and wrapped format
    if 'results' in results:
        review_results = results['results']
    else:
        review_results = results

    # Extract findings from each reviewer
    for profile, data in review_results.items():
        if data is None:
            continue

        findings_data = data.get('findings')
        if not findings_data:
            continue

        profile_findings = []
        items = findings_data.get('items', [])

        for item in items:
            finding = Finding(
                level=item.get('level', 'UNKNOWN'),
                text=item.get('text', ''),
                source=profile
            )
            profile_findings.append(finding)
            aggregated.all_findings.append(finding)

            # Count by level
            level = finding.level.upper()
            if level == 'HIGH':
                aggregated.total_high += 1
            elif level == 'MEDIUM':
                aggregated.total_medium += 1
            elif level == 'LOW':
                aggregated.total_low += 1
            elif level == 'NITPICK':
                aggregated.total_nitpick += 1

        aggregated.by_reviewer[profile] = profile_findings

    # Detect duplicates and remove them from all_findings
    unique_findings = []
    for finding in aggregated.all_findings:
        is_dupe = False
        for existing in unique_findings:
            if is_duplicate(finding, existing):
                is_dupe = True
                aggregated.duplicates_removed += 1
                break
        if not is_dupe:
            unique_findings.append(finding)

    # Note: we keep all_findings as-is but track duplicates_removed count

    # Detect conflicts between findings from different reviewers
    high_medium_findings = [
        f for f in aggregated.all_findings
        if f.level in ('HIGH', 'MEDIUM')
    ]

    for i, finding_a in enumerate(high_medium_findings):
        for finding_b in high_medium_findings[i+1:]:
            conflict = detect_conflict(finding_a, finding_b)
            if conflict:
                aggregated.conflicts.append(conflict)

    # Set outstanding issues flag
    aggregated.has_outstanding_issues = (
        aggregated.total_high > 0 or aggregated.total_medium > 0
    )

    return aggregated


def format_for_display(result: AggregatedResult) -> str:
    """Format aggregated results for terminal display."""
    lines = []

    # Findings by reviewer
    lines.append("━━━ Findings by Reviewer ━━━")
    for reviewer, findings in result.by_reviewer.items():
        lines.append(f"\n{reviewer.title()}:")
        if not findings:
            lines.append("  ✓ No issues")
        else:
            for f in findings:
                lines.append(f"  - [{f.level}] {f.text}")

    # Conflicts
    if result.conflicts:
        lines.append("\n━━━ Potential Conflicts Detected ━━━")
        for conflict in result.conflicts:
            lines.append(f"\n⚠️  {conflict.description}")
            lines.append(f"   {conflict.finding_a.source}: {conflict.finding_a.text[:80]}...")
            lines.append(f"   {conflict.finding_b.source}: {conflict.finding_b.text[:80]}...")
            if conflict.resolution_hint:
                lines.append(f"   💡 Suggestion: {conflict.resolution_hint}")

    # Summary
    lines.append("\n━━━ Summary ━━━")
    lines.append(f"Total: {result.total_high} HIGH, {result.total_medium} MEDIUM, "
                 f"{result.total_low} LOW, {result.total_nitpick} NITPICK")
    lines.append(f"Reviewers: {len(result.by_reviewer)}")
    lines.append(f"Duplicates removed: {result.duplicates_removed}")
    lines.append(f"Conflicts detected: {len(result.conflicts)}")

    if result.has_outstanding_issues:
        lines.append("\n⚠️  Outstanding HIGH/MEDIUM issues require addressing")
    else:
        lines.append("\n✓ No outstanding issues")

    return '\n'.join(lines)


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Aggregate findings from multiple reviewers',
        epilog='Parallel review results (JSON) are read from stdin'
    )
    parser.add_argument(
        '--format',
        choices=['json', 'text'],
        default='json',
        help='Output format (default: json)'
    )
    parser.add_argument(
        '--detect-conflicts',
        action='store_true',
        help='Enable conflict detection (default: enabled)'
    )
    parser.add_argument(
        '--show-duplicates',
        action='store_true',
        help='Show duplicate findings that were detected'
    )

    args = parser.parse_args()

    # Read results from stdin
    try:
        input_data = sys.stdin.read()
        if not input_data.strip():
            print("Error: No input provided on stdin", file=sys.stderr)
            sys.exit(1)
        results = json.loads(input_data)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)

    # Aggregate findings
    aggregated = aggregate_findings(results)

    # Output
    if args.format == 'json':
        output = {
            'by_reviewer': {
                reviewer: [
                    {'level': f.level, 'text': f.text, 'source': f.source}
                    for f in findings
                ]
                for reviewer, findings in aggregated.by_reviewer.items()
            },
            'all_findings': [
                {'level': f.level, 'text': f.text, 'source': f.source}
                for f in aggregated.all_findings
            ],
            'conflicts': [
                {
                    'finding_a': {
                        'level': c.finding_a.level,
                        'text': c.finding_a.text,
                        'source': c.finding_a.source
                    },
                    'finding_b': {
                        'level': c.finding_b.level,
                        'text': c.finding_b.text,
                        'source': c.finding_b.source
                    },
                    'description': c.description,
                    'resolution_hint': c.resolution_hint
                }
                for c in aggregated.conflicts
            ],
            'summary': {
                'total_high': aggregated.total_high,
                'total_medium': aggregated.total_medium,
                'total_low': aggregated.total_low,
                'total_nitpick': aggregated.total_nitpick,
                'duplicates_removed': aggregated.duplicates_removed,
                'conflicts_detected': len(aggregated.conflicts),
                'has_outstanding_issues': aggregated.has_outstanding_issues
            }
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_for_display(aggregated))

    # Exit with non-zero if outstanding issues
    if aggregated.has_outstanding_issues:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
