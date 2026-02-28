#!/usr/bin/env python3
"""
paths.py - Centralized path configuration for fando-plan

Provides configurable paths with environment variable overrides and
repository-local defaults for better portability and reproducibility.

Usage:
    from paths import get_skill_dir, get_training_dir, get_plan_reviews_dir

    skill_dir = get_skill_dir()
    training_dir = get_training_dir()

Environment Variables:
    FANDO_SKILL_DIR: Override path for skill/optimized/training data
    FANDO_PLAN_REVIEWS_DIR: Override path for plan review storage

Repository-Local Default:
    If .claude directory exists in current repository, uses that instead
    of ~/.claude, allowing repository-local state during development.
"""
import os
from pathlib import Path


def _get_base_claude_dir() -> Path:
    """
    Get the base Claude directory with repository-local fallback.

    Returns:
        Path to Claude directory (either repository-local .claude or ~/.claude)
    """
    # Check for repository-local .claude directory
    repo_claude = Path.cwd() / ".claude"
    if repo_claude.exists() and repo_claude.is_dir():
        return repo_claude

    # Fallback to user home
    return Path.home() / ".claude"


def get_skill_dir() -> Path:
    """
    Get the skill directory for DSPy reviewer state.

    Returns:
        Path to skill directory containing optimized modules and training data

    Environment Override:
        FANDO_SKILL_DIR - Custom path for skill directory
    """
    env_override = os.environ.get("FANDO_SKILL_DIR")
    if env_override:
        return Path(env_override)

    base = _get_base_claude_dir()
    return base / "skills" / "fando-plan"


def get_optimized_dir() -> Path:
    """
    Get the directory for GEPA-optimized DSPy modules.

    Returns:
        Path to optimized modules directory
    """
    return get_skill_dir() / "optimized"


def get_training_dir() -> Path:
    """
    Get the directory for training data examples.

    Returns:
        Path to training data directory
    """
    return get_skill_dir() / "training_data"


def get_plan_reviews_dir() -> Path:
    """
    Get the directory for plan review storage.

    Returns:
        Path to plan-reviews directory

    Environment Override:
        FANDO_PLAN_REVIEWS_DIR - Custom path for plan reviews
    """
    env_override = os.environ.get("FANDO_PLAN_REVIEWS_DIR")
    if env_override:
        return Path(env_override)

    return _get_base_claude_dir() / "plan-reviews"


def get_export_dir() -> Path:
    """
    Get the directory for exported prompt templates.

    Returns:
        Path to exported prompts directory
    """
    return get_skill_dir() / "exported_prompts"
