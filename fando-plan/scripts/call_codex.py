#!/usr/bin/env python3
"""
call_codex.py - Calls Codex with plan for review via stdin

Usage:
    echo "$PLAN" | python3 call_codex.py "Review prompt here"
    python3 call_codex.py "Review prompt" < plan.md
"""
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class CodexResult:
    stdout: str
    stderr: str
    exit_code: int
    error: str | None = None


def verify_codex_cli() -> dict:
    """Check Codex CLI availability and capabilities."""
    result = {
        'installed': False,
        'version': None,
        'supports_skip_git': False,
        'error': None
    }

    try:
        # Check if codex exists
        version_result = subprocess.run(
            ['codex', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if version_result.returncode == 0:
            result['installed'] = True
            result['version'] = version_result.stdout.strip()

        # Test --skip-git-repo-check support
        help_result = subprocess.run(
            ['codex', 'exec', '--help'],
            capture_output=True,
            text=True,
            timeout=5
        )
        result['supports_skip_git'] = '--skip-git-repo-check' in help_result.stdout

    except FileNotFoundError:
        result['error'] = "Codex CLI not found. Install from https://github.com/openai/codex"
    except subprocess.TimeoutExpired:
        result['error'] = "Codex CLI timed out during capability check"

    return result


def call_codex(prompt: str, plan: str, timeout: int = 600) -> CodexResult:
    """
    Call Codex exec with plan passed via stdin.

    Args:
        prompt: The review instructions
        plan: The plan content to review
        timeout: Maximum seconds to wait for response

    Returns:
        CodexResult with stdout, stderr, exit_code, and any error message.
    """
    full_prompt = f"{prompt}\n\n## Plan to Review\n\n{plan}"

    # Check CLI capabilities first
    cli_info = verify_codex_cli()
    if cli_info['error']:
        return CodexResult(
            stdout="",
            stderr="",
            exit_code=-1,
            error=cli_info['error']
        )

    # Build command with optional flags
    cmd = ['codex', 'exec']
    if cli_info['supports_skip_git']:
        cmd.append('--skip-git-repo-check')

    try:
        # Pass prompt content via stdin - Codex reads from stdin when no prompt arg given
        result = subprocess.run(
            cmd,
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        # Check for errors
        error = None
        if result.returncode != 0:
            error = f"Codex exited with code {result.returncode}: {result.stderr}"

        return CodexResult(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
            error=error
        )

    except subprocess.TimeoutExpired:
        return CodexResult(
            stdout="",
            stderr="",
            exit_code=-1,
            error=f"ERROR: Codex timed out after {timeout}s"
        )
    except FileNotFoundError:
        return CodexResult(
            stdout="",
            stderr="",
            exit_code=-1,
            error="ERROR: 'codex' command not found. Is Codex CLI installed?"
        )


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Call Codex to review a plan',
        epilog='Plan content is read from stdin'
    )
    parser.add_argument(
        'prompt',
        nargs='?',
        default='Review this plan for architecture, risks, and completeness.',
        help='Review prompt/instructions'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=600,
        help='Timeout in seconds (default: 600 / 10 minutes)'
    )
    parser.add_argument(
        '--check-only',
        action='store_true',
        help='Only check Codex CLI availability, do not call'
    )

    args = parser.parse_args()

    # Check-only mode for verification
    if args.check_only:
        info = verify_codex_cli()
        if info['error']:
            print(f"Error: {info['error']}", file=sys.stderr)
            sys.exit(1)
        print(f"Codex CLI: {info['version']}")
        print(f"Supports --skip-git-repo-check: {info['supports_skip_git']}")
        sys.exit(0)

    # Read plan from stdin
    plan = sys.stdin.read()
    if not plan.strip():
        print("Error: No plan content provided on stdin", file=sys.stderr)
        sys.exit(1)

    # Call Codex
    result = call_codex(args.prompt, plan, timeout=args.timeout)

    if result.error:
        print(f"Error: {result.error}", file=sys.stderr)
        sys.exit(1)

    # Output the response
    print(result.stdout)

    # Also output stderr if present (may contain useful info)
    if result.stderr:
        print(f"\n[stderr]: {result.stderr}", file=sys.stderr)


if __name__ == '__main__':
    main()
