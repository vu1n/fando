#!/usr/bin/env python3
"""
find_plan.py - Auto-detect the plan to verify against

Usage:
    python3 find_plan.py                    # Auto-detect for current project
    python3 find_plan.py --path=/path/to    # Use explicit path
    python3 find_plan.py --project=my-api   # Find for specific project
    python3 find_plan.py --list             # List available plans
"""
import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PlanInfo:
    path: str
    project: str
    modified: float
    size: int
    error: str | None = None


def get_project_name() -> str:
    """Get project name from git remote or directory."""
    try:
        result = subprocess.run(
            ['git', 'remote', 'get-url', 'origin'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # Handle both HTTPS and SSH URLs
            # https://github.com/user/repo.git -> repo
            # git@github.com:user/repo.git -> repo
            name = url.removesuffix('.git').split('/')[-1].split(':')[-1]
            return name
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fall back to current directory name
    return os.path.basename(os.getcwd()) or "standalone"


def get_plan_reviews_dir() -> Path:
    """Get the base directory for plan reviews."""
    return Path.home() / ".claude" / "plan-reviews"


def find_latest_plan(project: str = None) -> PlanInfo | None:
    """
    Find the most recent plan file for this project.

    Args:
        project: Project name. If None, auto-detect from git/directory.

    Returns:
        PlanInfo with path and metadata, or None if not found.
    """
    project = project or get_project_name()
    plan_dir = get_plan_reviews_dir() / project

    if not plan_dir.exists():
        return None

    # Find most recent .md file (excluding -verify.md files)
    plans = [
        p for p in plan_dir.glob("*.md")
        if not p.name.endswith("-verify.md")
    ]

    if not plans:
        return None

    # Sort by modification time, most recent first
    plans.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    latest = plans[0]
    stat = latest.stat()

    return PlanInfo(
        path=str(latest),
        project=project,
        modified=stat.st_mtime,
        size=stat.st_size
    )


def list_plans(project: str = None) -> list[PlanInfo]:
    """
    List all available plans for a project.

    Args:
        project: Project name. If None, list all projects.

    Returns:
        List of PlanInfo objects.
    """
    base_dir = get_plan_reviews_dir()
    plans = []

    if project:
        project_dirs = [base_dir / project] if (base_dir / project).exists() else []
    else:
        project_dirs = [d for d in base_dir.iterdir() if d.is_dir()]

    for project_dir in project_dirs:
        proj_name = project_dir.name
        for plan_file in project_dir.glob("*.md"):
            if plan_file.name.endswith("-verify.md"):
                continue
            stat = plan_file.stat()
            plans.append(PlanInfo(
                path=str(plan_file),
                project=proj_name,
                modified=stat.st_mtime,
                size=stat.st_size
            ))

    # Sort by modification time, most recent first
    plans.sort(key=lambda p: p.modified, reverse=True)
    return plans


def find_plan(explicit_path: str = None, project: str = None) -> tuple[str | None, str]:
    """
    Find plan content and source description.

    Args:
        explicit_path: Explicit path to plan file.
        project: Project name for auto-detection.

    Returns:
        (plan_content, source_description) or (None, error_message)
    """
    if explicit_path:
        path = Path(explicit_path).expanduser()
        if not path.exists():
            return None, f"Plan file not found: {explicit_path}"
        try:
            content = path.read_text()
            return content, f"from {path}"
        except Exception as e:
            return None, f"Error reading {explicit_path}: {e}"

    info = find_latest_plan(project)
    if info:
        try:
            content = Path(info.path).read_text()
            return content, f"from {info.path}"
        except Exception as e:
            return None, f"Error reading {info.path}: {e}"

    project_name = project or get_project_name()
    return None, f"No plan found for project '{project_name}' in {get_plan_reviews_dir()}"


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Find plan file to verify against',
        epilog='If no path specified, auto-detects based on project'
    )
    parser.add_argument(
        '--path',
        help='Explicit path to plan file'
    )
    parser.add_argument(
        '--project',
        help='Project name (default: auto-detect from git)'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List available plans'
    )
    parser.add_argument(
        '--format',
        choices=['text', 'json'],
        default='text',
        help='Output format'
    )
    parser.add_argument(
        '--content',
        action='store_true',
        help='Output plan content instead of just path'
    )

    args = parser.parse_args()

    if args.list:
        plans = list_plans(args.project)
        if args.format == 'json':
            print(json.dumps([{
                'path': p.path,
                'project': p.project,
                'modified': p.modified,
                'size': p.size
            } for p in plans], indent=2))
        else:
            if not plans:
                print("No plans found.")
                sys.exit(1)
            print(f"Found {len(plans)} plan(s):\n")
            for p in plans:
                from datetime import datetime
                mtime = datetime.fromtimestamp(p.modified).strftime('%Y-%m-%d %H:%M')
                print(f"  {p.project}: {Path(p.path).name}")
                print(f"    Path: {p.path}")
                print(f"    Modified: {mtime}")
                print()
        sys.exit(0)

    content, source = find_plan(args.path, args.project)

    if content is None:
        if args.format == 'json':
            print(json.dumps({'error': source}))
        else:
            print(f"Error: {source}", file=sys.stderr)
        sys.exit(1)

    if args.format == 'json':
        output = {
            'source': source,
            'found': True
        }
        if args.content:
            output['content'] = content
        print(json.dumps(output, indent=2))
    else:
        if args.content:
            print(f"# Plan {source}\n")
            print(content)
        else:
            print(f"Found plan {source}")


if __name__ == '__main__':
    main()
