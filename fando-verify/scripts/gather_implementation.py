#!/usr/bin/env python3
"""
gather_implementation.py - Collect implementation diff via git

Usage:
    python3 gather_implementation.py              # Diff against merge-base with main
    python3 gather_implementation.py --ref=abc123 # Diff against specific commit
    python3 gather_implementation.py --stat       # Show stats only
"""
import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field


@dataclass
class ImplementationDiff:
    diff: str
    base_ref: str
    head_ref: str
    files_changed: list[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    error: str | None = None


def _run_git(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    """Run git command with standard timeout and output handling.

    Args:
        args: Git command arguments (e.g., ['rev-parse', '--short', 'HEAD'])
        timeout: Maximum seconds to wait (default: 30)

    Returns:
        subprocess.CompletedProcess with stdout/stderr as strings

    Raises:
        subprocess.TimeoutExpired: If git command times out
        FileNotFoundError: If git is not available
    """
    cmd = ['git'] + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout
    )


def is_git_repo() -> bool:
    """Check if current directory is in a git repository."""
    result = _run_git(['rev-parse', '--git-dir'])
    return result.returncode == 0


def get_current_ref() -> str | None:
    """Get current HEAD reference."""
    result = _run_git(['rev-parse', '--short', 'HEAD'])
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def get_merge_base(target: str = "main") -> str | None:
    """
    Find merge base with target branch.

    Tries multiple common branch names in order.
    """
    branches_to_try = [target, "master", f"origin/{target}", "origin/main", "origin/master"]

    for branch in branches_to_try:
        result = _run_git(['merge-base', 'HEAD', branch])
        if result.returncode == 0:
            return result.stdout.strip()
    return None


def get_diff_stats(ref: str) -> tuple[int, int]:
    """Get additions and deletions count."""
    result = _run_git(['diff', '--shortstat', ref])
    if result.returncode != 0:
        return 0, 0

    text = result.stdout.strip()
    additions = 0
    deletions = 0

    # Parse "X files changed, Y insertions(+), Z deletions(-)"
    import re
    add_match = re.search(r'(\d+) insertion', text)
    del_match = re.search(r'(\d+) deletion', text)

    if add_match:
        additions = int(add_match.group(1))
    if del_match:
        deletions = int(del_match.group(1))

    return additions, deletions


def _collect_diff(
    ref: str,
    head_ref: str,
    include_untracked: bool = False
) -> ImplementationDiff:
    """
    Internal diff collection pipeline with shared orchestration.

    Args:
        ref: Git reference to diff against
        head_ref: Current HEAD reference for metadata
        include_untracked: Whether to include untracked files

    Returns:
        ImplementationDiff with collected diff data, or error if git fails
    """
    # Get list of changed files
    files_result = _run_git(['diff', '--name-only', ref])
    files = files_result.stdout.strip().split('\n') if files_result.stdout.strip() else []

    # Include untracked files if requested
    if include_untracked:
        untracked_result = _run_git(['ls-files', '--others', '--exclude-standard'])
        if untracked_result.stdout.strip():
            files.extend(untracked_result.stdout.strip().split('\n'))

    # Get diff
    diff_result = _run_git(['diff', ref])

    if diff_result.returncode != 0:
        return ImplementationDiff(
            diff="", base_ref=ref[:8] if len(ref) > 8 else ref, head_ref=head_ref,
            files_changed=files,
            error=f"git diff failed: {diff_result.stderr}"
        )

    # Get stats
    additions, deletions = get_diff_stats(ref)

    return ImplementationDiff(
        diff=diff_result.stdout,
        base_ref=ref[:8] if len(ref) > 8 else ref,
        head_ref=head_ref,
        files_changed=files,
        additions=additions,
        deletions=deletions
    )


def gather_diff(ref: str = None, target_branch: str = "main") -> ImplementationDiff:
    """
    Gather git diff for verification.

    Args:
        ref: Specific commit/ref to diff against. If None, uses merge-base with main.
        target_branch: Branch to find merge-base with (default: main)

    Returns:
        ImplementationDiff with diff content, metadata, and any errors.
    """
    if not is_git_repo():
        return ImplementationDiff(
            diff="", base_ref="", head_ref="",
            error="Not in a git repository. Run from within a git repo or specify --ref explicitly."
        )

    head_ref = get_current_ref() or "HEAD"

    if ref is None:
        ref = get_merge_base(target_branch)
        if ref is None:
            return ImplementationDiff(
                diff="", base_ref="", head_ref=head_ref,
                error=f"Could not find base branch ({target_branch}/master). Specify --ref explicitly."
            )

    # Use shared diff collection pipeline (no untracked files for committed diffs)
    return _collect_diff(ref, head_ref, include_untracked=False)


def gather_working_tree_diff() -> ImplementationDiff:
    """
    Gather diff of working tree (uncommitted changes).

    Useful when there's no merge-base or user wants to verify uncommitted work.
    """
    if not is_git_repo():
        return ImplementationDiff(
            diff="", base_ref="", head_ref="",
            error="Not in a git repository."
        )

    head_ref = get_current_ref() or "HEAD"

    # Use shared diff collection pipeline (include untracked files for working tree)
    result = _collect_diff('HEAD', 'working-tree', include_untracked=True)
    result.head_ref = "working-tree"
    return result


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Gather git diff for verification',
        epilog='Default: diff against merge-base with main/master'
    )
    parser.add_argument(
        '--ref',
        help='Specific commit/ref to diff against'
    )
    parser.add_argument(
        '--target',
        default='main',
        help='Target branch for merge-base (default: main)'
    )
    parser.add_argument(
        '--working-tree',
        action='store_true',
        help='Diff working tree (uncommitted changes) against HEAD'
    )
    parser.add_argument(
        '--stat',
        action='store_true',
        help='Show stats only, not full diff'
    )
    parser.add_argument(
        '--format',
        choices=['text', 'json'],
        default='text',
        help='Output format'
    )

    args = parser.parse_args()

    if args.working_tree:
        result = gather_working_tree_diff()
    else:
        result = gather_diff(args.ref, args.target)

    if result.error:
        if args.format == 'json':
            print(json.dumps({'error': result.error}))
        else:
            print(f"Error: {result.error}", file=sys.stderr)
        sys.exit(1)

    if args.format == 'json':
        output = {
            'base_ref': result.base_ref,
            'head_ref': result.head_ref,
            'files_changed': result.files_changed,
            'file_count': len(result.files_changed),
            'additions': result.additions,
            'deletions': result.deletions
        }
        if not args.stat:
            output['diff'] = result.diff
        print(json.dumps(output, indent=2))
    else:
        if args.stat:
            print(f"Base: {result.base_ref}")
            print(f"Head: {result.head_ref}")
            print(f"Files changed: {len(result.files_changed)}")
            print(f"Additions: {result.additions}")
            print(f"Deletions: {result.deletions}")
            if result.files_changed:
                print("\nChanged files:")
                for f in result.files_changed:
                    print(f"  {f}")
        else:
            print(result.diff)


if __name__ == '__main__':
    main()
