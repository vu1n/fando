#!/usr/bin/env python3
"""
secrets.py - Secret detection and redaction for plans

Usage:
    echo "$PLAN" | python3 secrets.py --mode=check   # Check for secrets
    echo "$PLAN" | python3 secrets.py --mode=redact  # Redact secrets
    echo "$PLAN" | python3 secrets.py --mode=block   # Fail if secrets found

Exit codes:
    0 - No secrets found (or redaction successful)
    1 - Secrets found (in check/block mode)
    2 - Error
"""
import json
import re
import sys
from dataclasses import dataclass
from typing import Optional


# Secret patterns with descriptions
SECRET_PATTERNS = [
    # API Keys
    (r'sk-[a-zA-Z0-9]{20,}', 'OpenAI API key'),
    (r'sk-proj-[a-zA-Z0-9_-]{20,}', 'OpenAI project key'),
    (r'sk-ant-[a-zA-Z0-9_-]{20,}', 'Anthropic API key'),

    # GitHub
    (r'ghp_[a-zA-Z0-9]{36}', 'GitHub personal access token'),
    (r'gho_[a-zA-Z0-9]{36}', 'GitHub OAuth token'),
    (r'ghu_[a-zA-Z0-9]{36}', 'GitHub user-to-server token'),
    (r'ghs_[a-zA-Z0-9]{36}', 'GitHub server-to-server token'),
    (r'github_pat_[a-zA-Z0-9_]{22,}', 'GitHub fine-grained PAT'),

    # AWS
    (r'AKIA[0-9A-Z]{16}', 'AWS access key ID'),
    (r'(?i)aws_secret_access_key\s*[=:]\s*["\']?([a-zA-Z0-9/+=]{40})', 'AWS secret key'),

    # Generic patterns (more prone to false positives)
    (r'(?i)(api[_-]?key|secret[_-]?key|auth[_-]?token|access[_-]?token|password)\s*[=:]\s*["\']?([a-zA-Z0-9_-]{20,})["\']?', 'credential'),

    # Private keys
    (r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----', 'private key'),

    # Database URLs with credentials
    (r'(?i)(postgres|mysql|mongodb)://[^:]+:[^@]+@', 'database URL with credentials'),
]


@dataclass
class SecretMatch:
    pattern_name: str
    matched_text: str
    redacted_text: str
    start: int
    end: int


@dataclass
class ScanResult:
    has_secrets: bool
    matches: list[SecretMatch]
    processed_text: Optional[str] = None
    error: Optional[str] = None


class SecretFoundError(Exception):
    """Raised when secrets are found and mode is 'block'."""
    pass


def redact_secret(secret: str) -> str:
    """
    Redact a secret, preserving prefix/suffix for identification.

    Examples:
        sk-abcdefgh12345678 -> sk-abcd****5678
        ghp_1234567890abcdefghijklmnopqrstuvwxyz -> ghp_1234****wxyz
    """
    if len(secret) <= 8:
        return '*' * len(secret)

    # Keep first 4-8 chars and last 4 chars
    prefix_len = min(8, len(secret) // 4)
    suffix_len = 4
    middle_len = len(secret) - prefix_len - suffix_len

    return secret[:prefix_len] + '*' * middle_len + secret[-suffix_len:]


def scan_for_secrets(text: str) -> ScanResult:
    """
    Scan text for potential secrets.

    Returns ScanResult with list of matches and their locations.
    """
    matches = []

    for pattern, name in SECRET_PATTERNS:
        for match in re.finditer(pattern, text):
            matched_text = match.group(0)

            # For patterns with capture groups, use the captured group
            if match.lastindex and match.lastindex >= 1:
                # Use the last capture group (usually the secret itself)
                matched_text = match.group(match.lastindex)

            matches.append(SecretMatch(
                pattern_name=name,
                matched_text=matched_text,
                redacted_text=redact_secret(matched_text),
                start=match.start(),
                end=match.end()
            ))

    # Sort by position and deduplicate overlapping matches
    matches.sort(key=lambda m: (m.start, -m.end))

    deduplicated = []
    last_end = -1
    for match in matches:
        if match.start >= last_end:
            deduplicated.append(match)
            last_end = match.end

    return ScanResult(
        has_secrets=len(deduplicated) > 0,
        matches=deduplicated
    )


def scan_and_handle_secrets(
    text: str,
    mode: str = 'block'
) -> tuple[str, list[str]]:
    """
    Scan for secrets and either block or redact.

    Args:
        text: The text to scan
        mode: 'check' (return results), 'block' (raise if found), 'redact' (mask secrets)

    Returns:
        (processed_text, warnings)

    Raises:
        SecretFoundError: If mode='block' and secrets found
    """
    result = scan_for_secrets(text)
    warnings = []

    if not result.has_secrets:
        return text, []

    # Build warnings
    for match in result.matches:
        warnings.append(f"Found {match.pattern_name}: {match.redacted_text}")

    if mode == 'block':
        raise SecretFoundError(
            f"Found {len(result.matches)} potential secret(s):\n" +
            "\n".join(f"  - {w}" for w in warnings) +
            "\n\nRemove secrets or use --mode=redact"
        )

    if mode == 'redact':
        # Replace secrets with redacted versions
        processed = text
        # Process in reverse order to maintain positions
        for match in reversed(result.matches):
            processed = (
                processed[:match.start] +
                f"[REDACTED: {match.redacted_text}]" +
                processed[match.end:]
            )
        return processed, warnings

    # mode == 'check' - just return original with warnings
    return text, warnings


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Scan for secrets in plan text',
        epilog='Text is read from stdin'
    )
    parser.add_argument(
        '--mode',
        choices=['check', 'block', 'redact'],
        default='check',
        help='Mode: check (report), block (fail if found), redact (mask secrets)'
    )
    parser.add_argument(
        '--format',
        choices=['text', 'json'],
        default='text',
        help='Output format'
    )

    args = parser.parse_args()

    # Read text from stdin
    text = sys.stdin.read()

    if not text.strip():
        print("Error: No text provided on stdin", file=sys.stderr)
        sys.exit(2)

    try:
        processed, warnings = scan_and_handle_secrets(text, mode=args.mode)

        if args.format == 'json':
            output = {
                'has_secrets': len(warnings) > 0,
                'warnings': warnings,
                'mode': args.mode
            }
            if args.mode == 'redact':
                output['processed_text'] = processed
            print(json.dumps(output, indent=2))
        else:
            if warnings:
                print(f"Found {len(warnings)} potential secret(s):", file=sys.stderr)
                for w in warnings:
                    print(f"  - {w}", file=sys.stderr)

                if args.mode == 'redact':
                    print("\nRedacted output:", file=sys.stderr)
                    print(processed)

                sys.exit(1)
            else:
                print("No secrets found.")
                sys.exit(0)

    except SecretFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
