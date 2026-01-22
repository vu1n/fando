#!/usr/bin/env python3
"""
detect_profiles.py - Detect relevant reviewer profiles based on plan content

Usage:
    echo "$PLAN" | python3 detect_profiles.py
    python3 detect_profiles.py < plan.md

Output (JSON):
    {
        "profiles": ["security", "frontend", "api"],
        "detected_keywords": {
            "security": ["auth", "jwt", "token"],
            "frontend": ["react", "component"],
            "api": ["endpoint", "REST"]
        },
        "summary": "Detected: authentication, React UI, REST endpoints"
    }
"""
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Profile definitions with keywords and prompt file locations
PROFILES = {
    'security': {
        'keywords': [
            'auth', 'password', 'token', 'jwt', 'encrypt', 'secret',
            'permission', 'role', 'cors', 'sanitize', 'xss', 'csrf',
            'oauth', 'session', 'login', 'credential', 'rbac', 'acl',
            'hash', 'salt', 'bcrypt', 'argon', 'ssl', 'tls', 'https',
            'certificate', 'firewall', 'vulnerability', 'injection',
            'authentication', 'authorization', 'security', 'secure'
        ],
        'prompt_file': 'profiles/security.md',
        'display_name': 'Security Reviewer',
        'description': 'authentication, authorization, input validation'
    },
    'frontend': {
        'keywords': [
            'react', 'vue', 'angular', 'svelte', 'component', 'css', 'ui', 'ux',
            'form', 'modal', 'page', 'render', 'state', 'redux', 'hook', 'hooks',
            'tailwind', 'styled', 'responsive', 'accessibility', 'a11y',
            'frontend', 'front-end', 'browser', 'dom', 'jsx', 'tsx',
            'nextjs', 'next.js', 'nuxt', 'gatsby', 'remix', 'button',
            'dropdown', 'navigation', 'sidebar', 'dashboard', 'layout'
        ],
        'prompt_file': 'profiles/frontend.md',
        'display_name': 'Frontend Architect',
        'description': 'components, state management, UX patterns'
    },
    'data': {
        'keywords': [
            'database', 'schema', 'migration', 'query', 'sql', 'table', 'index',
            'redis', 'postgres', 'postgresql', 'mysql', 'mongodb', 'dynamodb',
            'orm', 'prisma', 'drizzle', 'sequelize', 'typeorm', 'knex',
            'foreign key', 'primary key', 'relation', 'join', 'aggregate',
            'transaction', 'acid', 'nosql', 'document', 'collection',
            'backup', 'replication', 'sharding', 'partition'
        ],
        'prompt_file': 'profiles/data.md',
        'display_name': 'Data Architect',
        'description': 'schema design, queries, indexes, consistency'
    },
    'api': {
        'keywords': [
            'endpoint', 'rest', 'graphql', 'route', 'request', 'response',
            'http', 'webhook', 'api', 'grpc', 'rpc', 'openapi', 'swagger',
            'versioning', 'pagination', 'filter', 'sort', 'status code',
            'get', 'post', 'put', 'patch', 'delete', 'crud', 'resource',
            'trpc', 'hono', 'express', 'fastapi', 'flask', 'middleware'
        ],
        'prompt_file': 'profiles/api.md',
        'display_name': 'API Designer',
        'description': 'contract design, versioning, error handling'
    },
    'devops': {
        'keywords': [
            'deploy', 'ci/cd', 'cicd', 'docker', 'k8s', 'kubernetes',
            'pipeline', 'terraform', 'aws', 'gcp', 'azure', 'monitoring',
            'cloudflare', 'vercel', 'netlify', 'heroku', 'railway',
            'github actions', 'gitlab', 'jenkins', 'circleci', 'argocd',
            'helm', 'ansible', 'pulumi', 'infrastructure', 'iac',
            'container', 'pod', 'service mesh', 'istio', 'envoy',
            'logging', 'metrics', 'alerting', 'prometheus', 'grafana',
            'datadog', 'newrelic', 'sentry', 'observability'
        ],
        'prompt_file': 'profiles/devops.md',
        'display_name': 'DevOps Engineer',
        'description': 'infrastructure, deployment, observability'
    },
    'performance': {
        'keywords': [
            'cache', 'caching', 'optimize', 'optimization', 'latency',
            'throughput', 'scale', 'scaling', 'load', 'memory', 'cpu',
            'performance', 'benchmark', 'profiling', 'bottleneck',
            'concurrent', 'concurrency', 'parallel', 'async', 'queue',
            'rate limit', 'throttle', 'debounce', 'lazy', 'eager',
            'memoize', 'memoization', 'cdn', 'edge', 'prefetch',
            'bundle', 'minify', 'compress', 'gzip', 'brotli'
        ],
        'prompt_file': 'profiles/performance.md',
        'display_name': 'Performance Engineer',
        'description': 'bottlenecks, caching, optimization strategies'
    }
}


@dataclass
class DetectionResult:
    profiles: list[str] = field(default_factory=list)
    detected_keywords: dict[str, list[str]] = field(default_factory=dict)
    summary: str = ""
    error: Optional[str] = None


def detect_profiles(plan: str, min_keyword_matches: int = 2) -> DetectionResult:
    """
    Analyze plan content and return list of relevant profile names.

    Args:
        plan: The plan text to analyze
        min_keyword_matches: Minimum keyword matches to include a profile (default: 2)

    Returns:
        DetectionResult with detected profiles and matched keywords
    """
    result = DetectionResult()

    if not plan or not plan.strip():
        result.error = "Empty plan"
        return result

    plan_lower = plan.lower()

    # Check each profile for keyword matches
    for profile_name, config in PROFILES.items():
        matched_keywords = []

        for keyword in config['keywords']:
            # Use word boundary matching to avoid partial matches
            # e.g., "api" shouldn't match "capital"
            pattern = rf'\b{re.escape(keyword)}\b'
            if re.search(pattern, plan_lower):
                matched_keywords.append(keyword)

        # Include profile if enough keywords match
        if len(matched_keywords) >= min_keyword_matches:
            result.profiles.append(profile_name)
            result.detected_keywords[profile_name] = matched_keywords

    # Build summary from detected components
    if result.profiles:
        descriptions = [PROFILES[p]['description'] for p in result.profiles]
        result.summary = f"Detected: {', '.join(descriptions)}"
    else:
        result.summary = "No specific domain detected, using generic architect review"

    return result


def get_profile_info(profile_name: str) -> Optional[dict]:
    """Get profile configuration by name."""
    return PROFILES.get(profile_name)


def get_profile_prompt_path(profile_name: str) -> Optional[Path]:
    """Get the absolute path to a profile's prompt file."""
    config = PROFILES.get(profile_name)
    if not config:
        return None

    # Get the references directory relative to this script
    script_dir = Path(__file__).parent
    references_dir = script_dir.parent / 'references'

    return references_dir / config['prompt_file']


def list_all_profiles() -> dict:
    """Return information about all available profiles."""
    return {
        name: {
            'display_name': config['display_name'],
            'description': config['description'],
            'keyword_count': len(config['keywords'])
        }
        for name, config in PROFILES.items()
    }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Detect relevant reviewer profiles for a plan',
        epilog='Plan content is read from stdin'
    )
    parser.add_argument(
        '--min-matches',
        type=int,
        default=2,
        help='Minimum keyword matches to include a profile (default: 2)'
    )
    parser.add_argument(
        '--list-profiles',
        action='store_true',
        help='List all available profiles and exit'
    )
    parser.add_argument(
        '--format',
        choices=['json', 'text', 'names'],
        default='json',
        help='Output format (default: json)'
    )

    args = parser.parse_args()

    # List profiles mode
    if args.list_profiles:
        profiles = list_all_profiles()
        if args.format == 'json':
            print(json.dumps(profiles, indent=2))
        else:
            print("Available reviewer profiles:\n")
            for name, info in profiles.items():
                print(f"  {name}: {info['display_name']}")
                print(f"    {info['description']}")
                print(f"    ({info['keyword_count']} keywords)\n")
        sys.exit(0)

    # Read plan from stdin
    plan = sys.stdin.read()

    if not plan.strip():
        print("Error: No plan content provided on stdin", file=sys.stderr)
        sys.exit(1)

    # Detect profiles
    result = detect_profiles(plan, min_keyword_matches=args.min_matches)

    if result.error:
        print(f"Error: {result.error}", file=sys.stderr)
        sys.exit(1)

    # Output based on format
    if args.format == 'json':
        output = {
            'profiles': result.profiles,
            'detected_keywords': result.detected_keywords,
            'summary': result.summary,
            'profile_details': {
                name: {
                    'display_name': PROFILES[name]['display_name'],
                    'prompt_file': PROFILES[name]['prompt_file']
                }
                for name in result.profiles
            }
        }
        print(json.dumps(output, indent=2))

    elif args.format == 'text':
        if result.profiles:
            print(result.summary)
            print(f"\nRunning specialist reviewers:")
            for profile in result.profiles:
                display_name = PROFILES[profile]['display_name']
                keywords = result.detected_keywords[profile][:5]  # Show top 5
                print(f"  ├─ {display_name}")
                print(f"  │    Keywords: {', '.join(keywords)}")
        else:
            print("No domain-specific profiles detected.")
            print("Will use generic Systems Architect review.")

    elif args.format == 'names':
        # Just output profile names, one per line (useful for scripting)
        for profile in result.profiles:
            print(profile)


if __name__ == '__main__':
    main()
