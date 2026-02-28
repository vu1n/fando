#!/usr/bin/env python3
"""
review_runtime.py - DSPy review orchestration and optimized module management

Provides run_dspy_review for parallel execution of domain-specific reviews,
and load/save helpers for GEPA-optimized modules.

Usage:
    from review_runtime import run_dspy_review, save_optimized_module, load_optimized_module

    results = run_dspy_review(plan, ["security", "api"], security_level="public")

    # After GEPA optimization
    save_optimized_module("security", optimized_module)
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

# DSPy import - optional dependency
try:
    import dspy

    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False
    dspy = None

from paths import get_optimized_dir
from review_module import DomainReviewModule

logger = logging.getLogger(__name__)


# ===========================================================================
# Optimized Module Persistence
# ===========================================================================

def save_optimized_module(domain: str, module: Any) -> Path:
    """Save an optimized DSPy module's state to disk.

    Args:
        domain: Domain name (e.g. "security")
        module: Optimized DomainReviewModule

    Returns:
        Path to the saved file
    """
    get_optimized_dir().mkdir(parents=True, exist_ok=True)
    path = get_optimized_dir() / f"{domain}.json"
    module.save(str(path))
    return path


def load_optimized_module(domain: str) -> Optional[Any]:
    """Load a GEPA-optimized module if it exists.

    Returns:
        DomainReviewModule with optimized state, or None if not found or error.

    Logs a warning if the file exists but fails to load (corruption/incompatibility).
    """
    if not DSPY_AVAILABLE:
        return None

    path = get_optimized_dir() / f"{domain}.json"
    if not path.exists():
        return None

    try:
        mod = DomainReviewModule(domain=domain)
        mod.load(str(path))
        return mod
    except FileNotFoundError:
        # File was removed between exists() check and load() - treat as not found
        return None
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as e:
        # File exists but is corrupt or incompatible - log the error
        logger.warning(f"Failed to load optimized module for domain '{domain}' from {path}: {e}")
        return None
    except Exception as e:
        # Unexpected error - log with more details
        logger.error(f"Unexpected error loading optimized module for domain '{domain}' from {path}: {type(e).__name__}: {e}")
        return None


# ===========================================================================
# Orchestration — run_dspy_review
# ===========================================================================

def run_dspy_review(
    plan: str,
    profiles: list[str],
    security_level: str = "public",
    use_optimized: bool = True,
    max_workers: int | None = None,
) -> dict[str, Any]:
    """Run DSPy-based reviews in parallel for the given profiles.

    Args:
        plan: Full plan text
        profiles: Domain names to review (e.g. ["security", "api"])
        security_level: personal / internal / public / enterprise
        use_optimized: Load GEPA-optimized module state if available
        max_workers: Thread pool size (default: len(profiles))

    Returns:
        Dict mapping profile name → dspy.Prediction (empty dict if no profiles)
    """
    if not DSPY_AVAILABLE:
        raise ImportError("DSPy is required: uv pip install -e '.[dspy]'")

    # Early return for empty profiles matches run_parallel_reviews() behavior
    if not profiles:
        return {}

    # Configure CodexLM as the DSPy LM (if not already configured)
    if dspy.settings.lm is None:
        from codex_lm import CodexLM

        dspy.configure(lm=CodexLM())

    if max_workers is None:
        max_workers = len(profiles)

    # Build modules, loading optimized state where available
    modules: dict[str, DomainReviewModule] = {}
    for profile in profiles:
        mod = DomainReviewModule(domain=profile)
        if use_optimized:
            loaded = load_optimized_module(profile)
            if loaded is not None:
                mod = loaded
        modules[profile] = mod

    # Build the "other reviewers" context string for focus
    other_map: dict[str, str] = {}
    for profile in profiles:
        others = [p for p in profiles if p != profile]
        other_map[profile] = ", ".join(others) if others else "none"

    # Run reviews in parallel
    results: dict[str, Any] = {}

    def _run_one(profile: str) -> tuple[str, Any]:
        mod = modules[profile]
        prediction = mod.forward(
            plan=plan,
            other_reviewers=other_map[profile],
            security_level=security_level,
        )
        return profile, prediction

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run_one, profile): profile for profile in profiles
        }
        for future in as_completed(futures):
            profile = futures[future]
            try:
                _, prediction = future.result()
                results[profile] = prediction
            except Exception as exc:
                results[profile] = exc

    return results
