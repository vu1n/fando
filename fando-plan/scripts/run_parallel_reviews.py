#!/usr/bin/env python3
"""
run_parallel_reviews.py - Run multiple reviewer profiles in parallel

Usage:
    echo "$PLAN" | python3 run_parallel_reviews.py security frontend api
    python3 run_parallel_reviews.py --profiles=security,frontend < plan.md

Output (JSON):
    {
        "results": {
            "security": {"output": "...", "findings": {...}, "error": null},
            "frontend": {"output": "...", "findings": {...}, "error": null}
        },
        "summary": {
            "total_high": 2,
            "total_medium": 3,
            "profiles_completed": 2,
            "profiles_failed": 0
        }
    }
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Import sibling modules
from call_codex import call_codex, verify_codex_cli
from parse_findings import parse_findings, ParseResult
from detect_profiles import PROFILES, get_profile_prompt_path


# Focus context added to each reviewer prompt
FOCUS_PREAMBLE = """
## Your Role in This Review

You are one of several specialist reviewers examining this plan. You have the FULL plan
for context - this helps you understand WHY decisions were made and how your domain
connects to others.

**However**: Only flag issues in YOUR domain. Other specialists cover other areas.
- Understand the full context and reasoning
- But only raise findings for your area of expertise
- If something in your domain depends on another domain's decision, note it but don't
  flag the other domain's choice

This focused approach prevents duplicate findings and lets each specialist go deep
in their area.

---

"""


@dataclass
class ReviewResult:
    profile: str
    output: str = ""
    findings: Optional[ParseResult] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0


@dataclass
class ParallelReviewResult:
    results: dict[str, ReviewResult] = field(default_factory=dict)
    total_high: int = 0
    total_medium: int = 0
    total_low: int = 0
    total_nitpick: int = 0
    profiles_completed: int = 0
    profiles_failed: int = 0
    has_outstanding_issues: bool = False


def load_profile_prompt(profile_name: str) -> Optional[str]:
    """Load the prompt file for a given profile."""
    prompt_path = get_profile_prompt_path(profile_name)

    if not prompt_path or not prompt_path.exists():
        # Fallback: return None to trigger generic prompt
        return None

    return prompt_path.read_text()


def run_single_review(
    profile: str,
    plan: str,
    timeout: int = 600,
    security_level: str = 'public',
) -> ReviewResult:
    """
    Run a single reviewer profile against the plan.

    Args:
        profile: Profile name (e.g., 'security', 'frontend')
        plan: The full plan content to review
        timeout: Maximum seconds to wait for Codex response
        security_level: Security level for severity calibration

    Returns:
        ReviewResult with output, parsed findings, and any errors
    """
    result = ReviewResult(profile=profile)
    start_time = time.time()

    try:
        # Load profile-specific prompt
        prompt = load_profile_prompt(profile)

        # Inject security level for security profile
        if profile == 'security' and prompt:
            prompt = f"Security Level: {security_level}\n\n{prompt}"

        if not prompt:
            # Use generic fallback if profile prompt not found
            display_name = PROFILES.get(profile, {}).get('display_name', profile)
            prompt = f"""You are a {display_name} reviewing an implementation plan.

Review this plan focusing on your area of expertise. Identify issues that would cause problems during implementation.

For each finding, assign a risk level:
- **HIGH**: Critical issue that must be addressed before implementation
- **MEDIUM**: Important consideration that should be addressed
- **LOW**: Minor improvement, nice-to-have
- **NITPICK**: Cosmetic or stylistic preference

Format your response as:

## Findings
- [HIGH/MEDIUM/LOW/NITPICK] Finding description...

## Summary
X high, Y medium, Z low, W nitpick findings.
If no issues: "LGTM - no concerns in my domain"
"""

        # Add focus preamble to help reviewer stay in lane
        full_prompt = FOCUS_PREAMBLE + prompt

        # Call Codex with full plan
        codex_result = call_codex(full_prompt, plan, timeout=timeout)

        if codex_result.error:
            result.error = codex_result.error
        else:
            result.output = codex_result.stdout

            # Parse findings from the response
            parsed = parse_findings(codex_result.stdout)
            result.findings = parsed

    except Exception as e:
        result.error = f"Exception during review: {str(e)}"

    result.duration_seconds = time.time() - start_time
    return result


def run_parallel_reviews(
    plan: str,
    profiles: list[str],
    max_workers: Optional[int] = None,
    timeout: int = 600,
    security_level: str = 'public'
) -> ParallelReviewResult:
    """
    Run multiple reviewers in parallel on the same plan version.

    Each reviewer gets the FULL plan for context understanding, but is
    instructed to only flag issues in their specific domain.

    Args:
        plan: The plan content to review
        profiles: List of profile names to run
        max_workers: Maximum parallel workers (default: number of profiles)
        timeout: Timeout per reviewer in seconds
        security_level: Security level for severity calibration

    Returns:
        ParallelReviewResult with all results and aggregated counts
    """
    result = ParallelReviewResult()

    if not profiles:
        return result

    # Default to running all profiles in parallel
    if max_workers is None:
        max_workers = len(profiles)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all reviews
        future_to_profile = {
            executor.submit(run_single_review, profile, plan, timeout, security_level): profile
            for profile in profiles
        }

        # Collect results as they complete
        for future in as_completed(future_to_profile):
            profile = future_to_profile[future]

            try:
                review_result = future.result()
                result.results[profile] = review_result

                if review_result.error:
                    result.profiles_failed += 1
                else:
                    result.profiles_completed += 1

                    # Aggregate findings
                    if review_result.findings:
                        result.total_high += review_result.findings.high
                        result.total_medium += review_result.findings.medium
                        result.total_low += review_result.findings.low
                        result.total_nitpick += review_result.findings.nitpick

            except Exception as e:
                result.results[profile] = ReviewResult(
                    profile=profile,
                    error=f"Future execution error: {str(e)}"
                )
                result.profiles_failed += 1

    # Determine if there are outstanding issues
    result.has_outstanding_issues = result.total_high > 0 or result.total_medium > 0

    return result


def format_results_for_display(result: ParallelReviewResult) -> str:
    """Format parallel review results for terminal display."""
    lines = []

    for profile, review in result.results.items():
        display_name = PROFILES.get(profile, {}).get('display_name', profile)
        lines.append(f"\n{display_name}:")

        if review.error:
            lines.append(f"  Error: {review.error}")
            continue

        if not review.findings or not review.findings.findings:
            lines.append("  No issues found")
            continue

        # Group findings by level
        for finding in review.findings.findings:
            lines.append(f"  - [{finding.level}] {finding.text}")

    # Summary
    lines.append(f"\n--- Summary ---")
    lines.append(f"Total: {result.total_high} HIGH, {result.total_medium} MEDIUM, "
                 f"{result.total_low} LOW, {result.total_nitpick} NITPICK")
    lines.append(f"Profiles: {result.profiles_completed} completed, "
                 f"{result.profiles_failed} failed")

    if result.has_outstanding_issues:
        lines.append("\nOutstanding issues require addressing")
    else:
        lines.append("\nAll specialists satisfied")

    return '\n'.join(lines)


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Run multiple reviewer profiles in parallel',
        epilog='Plan content is read from stdin'
    )
    parser.add_argument(
        'profiles',
        nargs='*',
        help='Profile names to run (e.g., security frontend api)'
    )
    parser.add_argument(
        '--profiles',
        dest='profiles_flag',
        help='Comma-separated profile names (alternative to positional args)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=600,
        help='Timeout per reviewer in seconds (default: 600)'
    )
    parser.add_argument(
        '--max-workers',
        type=int,
        help='Maximum parallel workers (default: number of profiles)'
    )
    parser.add_argument(
        '--format',
        choices=['json', 'text'],
        default='json',
        help='Output format (default: json)'
    )
    parser.add_argument(
        '--check-only',
        action='store_true',
        help='Only verify Codex CLI is available'
    )
    parser.add_argument(
        '--security-level',
        default='public',
        choices=['personal', 'internal', 'public', 'enterprise'],
        help='Security level for severity calibration (default: public)'
    )

    args = parser.parse_args()

    # Check-only mode
    if args.check_only:
        info = verify_codex_cli()
        if info['error']:
            print(f"Error: {info['error']}", file=sys.stderr)
            sys.exit(1)
        print(f"Codex CLI ready: {info['version']}")
        sys.exit(0)

    # Determine profiles
    profiles = args.profiles or []
    if args.profiles_flag:
        profiles = [p.strip() for p in args.profiles_flag.split(',')]

    if not profiles:
        print("Error: No profiles specified", file=sys.stderr)
        print("Usage: echo '$PLAN' | python3 run_parallel_reviews.py security frontend api",
              file=sys.stderr)
        sys.exit(1)

    # Validate profiles
    invalid = [p for p in profiles if p not in PROFILES]
    if invalid:
        print(f"Warning: Unknown profiles will use generic prompt: {invalid}",
              file=sys.stderr)

    # Read plan from stdin
    plan = sys.stdin.read()

    if not plan.strip():
        print("Error: No plan content provided on stdin", file=sys.stderr)
        sys.exit(1)

    # Run parallel reviews
    result = run_parallel_reviews(
        plan=plan,
        profiles=profiles,
        max_workers=args.max_workers,
        timeout=args.timeout,
        security_level=args.security_level,
    )

    # Output results
    if args.format == 'json':
        output = {
            'results': {},
            'summary': {
                'total_high': result.total_high,
                'total_medium': result.total_medium,
                'total_low': result.total_low,
                'total_nitpick': result.total_nitpick,
                'profiles_completed': result.profiles_completed,
                'profiles_failed': result.profiles_failed,
                'has_outstanding_issues': result.has_outstanding_issues
            },
        }

        for profile, review in result.results.items():
            output['results'][profile] = {
                'output': review.output,
                'findings': {
                    'high': review.findings.high if review.findings else 0,
                    'medium': review.findings.medium if review.findings else 0,
                    'low': review.findings.low if review.findings else 0,
                    'nitpick': review.findings.nitpick if review.findings else 0,
                    'items': [
                        {'level': f.level, 'text': f.text}
                        for f in (review.findings.findings if review.findings else [])
                    ]
                } if review.findings else None,
                'error': review.error,
                'duration_seconds': review.duration_seconds
            }

        print(json.dumps(output, indent=2))

    else:  # text format
        print(format_results_for_display(result))

    # Exit with non-zero if there are outstanding issues
    if result.has_outstanding_issues:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
