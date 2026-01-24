#!/usr/bin/env python3
"""
detect_security_level.py - Detect security level based on plan content

Usage:
    echo "$PLAN" | python3 detect_security_level.py
    python3 detect_security_level.py < plan.md

Output (JSON):
    {
        "level": "internal",
        "confidence": 0.8,
        "matched_keywords": ["admin", "dashboard", "employee"],
        "description": "Internal tool for authenticated employees"
    }

Security Levels:
    - personal: Side projects, learning, prototypes (minimal exposure)
    - internal: Company internal tools, trusted users (authenticated employees)
    - public: Public-facing apps, customer data (untrusted internet users)
    - enterprise: Regulated industries, sensitive data (compliance, audit)
"""
import json
import re
import sys
from dataclasses import dataclass, field
from typing import Optional


# Security level definitions with keywords and descriptions
SECURITY_LEVELS = {
    'personal': {
        'keywords': [
            'side project', 'learning', 'prototype', 'hobby',
            'personal', 'toy', 'experiment', 'playground', 'demo',
            'tutorial', 'practice', 'sandbox', 'test project', 'poc',
            'proof of concept', 'just for fun', 'pet project'
        ],
        'description': 'Personal/hobby project with minimal exposure'
    },
    'internal': {
        'keywords': [
            'internal', 'admin', 'backoffice', 'employee', 'intranet',
            'dashboard', 'ops', 'tooling', 'internal tool', 'staff',
            'company', 'corporate', 'back office', 'management',
            'hr', 'operations', 'internal users', 'employees only'
        ],
        'description': 'Internal tool for authenticated employees'
    },
    'public': {
        'keywords': [
            'public', 'customer', 'user-facing', 'saas', 'production',
            'users', 'signup', 'registration', 'billing', 'payment',
            'checkout', 'consumer', 'end user', 'customer-facing',
            'public api', 'external', 'internet', 'web app'
        ],
        'description': 'Public-facing app with customer data'
    },
    'enterprise': {
        'keywords': [
            'compliance', 'hipaa', 'pci', 'soc2', 'gdpr', 'regulated',
            'healthcare', 'financial', 'government', 'audit', 'pii',
            'sox', 'fedramp', 'banking', 'insurance', 'medical',
            'phi', 'ferpa', 'ccpa', 'sensitive data', 'classified'
        ],
        'description': 'Regulated industry with compliance requirements'
    }
}

# Default level when detection is uncertain
DEFAULT_LEVEL = 'public'


@dataclass
class DetectionResult:
    level: str = DEFAULT_LEVEL
    confidence: float = 0.0
    matched_keywords: list[str] = field(default_factory=list)
    description: str = ""
    all_matches: dict[str, list[str]] = field(default_factory=dict)
    error: Optional[str] = None


def detect_security_level(plan: str) -> DetectionResult:
    """
    Analyze plan content and return detected security level with confidence.

    Args:
        plan: The plan text to analyze

    Returns:
        DetectionResult with detected level, confidence, and matched keywords
    """
    result = DetectionResult()

    if not plan or not plan.strip():
        result.error = "Empty plan"
        result.description = SECURITY_LEVELS[DEFAULT_LEVEL]['description']
        return result

    plan_lower = plan.lower()

    # Count keyword matches for each level
    level_scores: dict[str, list[str]] = {}

    for level_name, config in SECURITY_LEVELS.items():
        matched_keywords = []

        for keyword in config['keywords']:
            # Use word boundary matching for single words,
            # exact substring for phrases
            if ' ' in keyword:
                # Phrase matching
                if keyword in plan_lower:
                    matched_keywords.append(keyword)
            else:
                # Word boundary matching
                pattern = rf'\b{re.escape(keyword)}\b'
                if re.search(pattern, plan_lower):
                    matched_keywords.append(keyword)

        if matched_keywords:
            level_scores[level_name] = matched_keywords
            result.all_matches[level_name] = matched_keywords

    # Determine the best match
    if not level_scores:
        # No matches - use default with low confidence
        result.level = DEFAULT_LEVEL
        result.confidence = 0.3
        result.description = SECURITY_LEVELS[DEFAULT_LEVEL]['description']
        return result

    # Find level with most matches
    best_level = max(level_scores, key=lambda k: len(level_scores[k]))
    best_matches = level_scores[best_level]

    # Calculate confidence based on:
    # - Number of matches (more = higher confidence)
    # - Whether there are competing levels (ambiguity reduces confidence)
    match_count = len(best_matches)
    total_levels_matched = len(level_scores)

    # Base confidence from match count
    if match_count >= 5:
        base_confidence = 0.95
    elif match_count >= 3:
        base_confidence = 0.85
    elif match_count >= 2:
        base_confidence = 0.75
    else:
        base_confidence = 0.6

    # Reduce confidence if multiple levels matched (ambiguity)
    if total_levels_matched > 1:
        # Check if there's a close competitor
        sorted_levels = sorted(
            level_scores.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )
        if len(sorted_levels) > 1:
            best_count = len(sorted_levels[0][1])
            second_count = len(sorted_levels[1][1])
            if second_count >= best_count - 1:
                # Close competition - reduce confidence
                base_confidence *= 0.8

    result.level = best_level
    result.confidence = round(base_confidence, 2)
    result.matched_keywords = best_matches
    result.description = SECURITY_LEVELS[best_level]['description']

    return result


def get_level_info(level_name: str) -> Optional[dict]:
    """Get security level configuration by name."""
    return SECURITY_LEVELS.get(level_name)


def list_all_levels() -> dict:
    """Return information about all available security levels."""
    return {
        name: {
            'description': config['description'],
            'keyword_count': len(config['keywords'])
        }
        for name, config in SECURITY_LEVELS.items()
    }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Detect security level for a plan',
        epilog='Plan content is read from stdin'
    )
    parser.add_argument(
        '--list-levels',
        action='store_true',
        help='List all available security levels and exit'
    )
    parser.add_argument(
        '--format',
        choices=['json', 'text'],
        default='json',
        help='Output format (default: json)'
    )

    args = parser.parse_args()

    # List levels mode
    if args.list_levels:
        levels = list_all_levels()
        if args.format == 'json':
            print(json.dumps(levels, indent=2))
        else:
            print("Available security levels:\n")
            for name, info in levels.items():
                print(f"  {name}: {info['description']}")
                print(f"    ({info['keyword_count']} keywords)\n")
        sys.exit(0)

    # Read plan from stdin
    plan = sys.stdin.read()

    if not plan.strip():
        print("Error: No plan content provided on stdin", file=sys.stderr)
        sys.exit(1)

    # Detect security level
    result = detect_security_level(plan)

    if result.error:
        print(f"Error: {result.error}", file=sys.stderr)
        sys.exit(1)

    # Output based on format
    if args.format == 'json':
        output = {
            'level': result.level,
            'confidence': result.confidence,
            'matched_keywords': result.matched_keywords,
            'description': result.description
        }
        # Include all matches if there were multiple levels detected
        if len(result.all_matches) > 1:
            output['all_matches'] = result.all_matches
        print(json.dumps(output, indent=2))

    else:  # text format
        print(f"Security level: {result.level}")
        print(f"Confidence: {result.confidence:.0%}")
        print(f"Description: {result.description}")
        if result.matched_keywords:
            print(f"Matched keywords: {', '.join(result.matched_keywords[:5])}")
        if len(result.all_matches) > 1:
            print("\nOther matches:")
            for level, keywords in result.all_matches.items():
                if level != result.level:
                    print(f"  {level}: {', '.join(keywords[:3])}")


if __name__ == '__main__':
    main()
