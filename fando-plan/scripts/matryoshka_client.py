#!/usr/bin/env python3
"""
matryoshka_client.py - MCP wrapper for Matryoshka context slicing

Provides session management for Matryoshka MCP server to achieve 75%+ token
savings when sending plans to multiple specialist reviewers.

Usage:
    from matryoshka_client import MatryoshkaClient

    client = MatryoshkaClient(mcp_tools)
    if client.should_use_matryoshka(plan):
        session = client.create_session(plan)
        try:
            slices = client.get_slices_parallel(session, ['security', 'frontend'])
            # Use slices['security'].content instead of full plan
        finally:
            client.close_session(session)
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class SliceResult:
    """Result of extracting a slice for a profile."""
    profile: str
    content: str
    token_count: int = 0
    original_token_count: int = 0
    query_used: str = ""
    error: Optional[str] = None
    used_fallback: bool = False

    @property
    def savings_percent(self) -> float:
        """Calculate token savings percentage."""
        if self.original_token_count == 0:
            return 0.0
        return (1 - self.token_count / self.original_token_count) * 100


@dataclass
class MatryoshkaSession:
    """Active session with Matryoshka MCP server."""
    session_id: str
    plan_content: str
    plan_token_count: int = 0
    active: bool = True


@dataclass
class MatryoshkaStats:
    """Statistics for a Matryoshka-enhanced review run."""
    total_tokens_sent: int = 0
    total_tokens_without_slicing: int = 0
    profiles_sliced: int = 0
    profiles_fallback: int = 0

    @property
    def savings_percent(self) -> float:
        if self.total_tokens_without_slicing == 0:
            return 0.0
        return (1 - self.total_tokens_sent / self.total_tokens_without_slicing) * 100

    def format_summary(self) -> str:
        """Format stats for display."""
        return (
            f"Token efficiency: {self.total_tokens_sent:,} tokens sent "
            f"(vs. {self.total_tokens_without_slicing:,} without slicing)\n"
            f"Savings: {self.savings_percent:.0f}%"
        )


# Nucleus query patterns per reviewer profile
# These are deterministic - same every time, not LLM-generated
PROFILE_QUERIES = {
    'security': '(union (grep "auth|jwt|token|encrypt|secret|password|session|csrf|xss|injection") (section "security"))',
    'frontend': '(union (grep "component|state|ui|react|vue|css|form|modal|hook") (section "frontend"))',
    'api': '(union (grep "endpoint|route|http|rest|graphql|request|response|webhook") (section "api"))',
    'data': '(union (grep "database|schema|migration|query|sql|table|index|postgres|redis") (section "data"))',
    'devops': '(union (grep "deploy|docker|k8s|kubernetes|pipeline|terraform|aws|ci/cd|monitoring") (section "deployment"))',
    'performance': '(union (grep "cache|optimize|latency|throughput|scale|memory|bottleneck") (section "performance"))',
    'architect': '(union (list_symbols) (section "overview") (head 50))',
}

# Minimum slice size (tokens) - below this, use full plan
MIN_SLICE_TOKENS = 50


def estimate_tokens(text: str) -> int:
    """
    Rough token estimation (4 chars per token average).
    This is a fast heuristic, not exact tokenization.
    """
    return len(text) // 4


class MatryoshkaClient:
    """
    MCP wrapper for Matryoshka context slicing.

    Provides deterministic session management with guaranteed cleanup,
    hardcoded Nucleus queries per profile, and graceful fallback.
    """

    def __init__(self, mcp_tools: Optional[dict[str, Callable]] = None):
        """
        Initialize client with optional MCP tools.

        Args:
            mcp_tools: Dict mapping tool names to callables.
                       Expected keys: 'matryoshka_create_session',
                       'matryoshka_query', 'matryoshka_close_session'
        """
        self._mcp_tools = mcp_tools or {}
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        """
        Check if Matryoshka MCP server is available.

        Returns:
            True if MCP tools are available and responding
        """
        if self._available is not None:
            return self._available

        # Check if required MCP tools exist
        required_tools = [
            'mcp__matryoshka__create_session',
            'mcp__matryoshka__query',
            'mcp__matryoshka__close_session',
        ]

        self._available = all(
            tool in self._mcp_tools for tool in required_tools
        )

        return self._available

    def should_use_matryoshka(self, plan: str, threshold_lines: int = 300) -> bool:
        """
        Determine if Matryoshka slicing should be used for this plan.

        Args:
            plan: The plan content
            threshold_lines: Minimum lines to activate Matryoshka

        Returns:
            True if plan is large enough and Matryoshka is available
        """
        if not self.is_available():
            return False

        line_count = len(plan.splitlines())
        return line_count >= threshold_lines

    def create_session(self, plan: str) -> MatryoshkaSession:
        """
        Create a Matryoshka session and load the plan.

        Args:
            plan: The plan content to load

        Returns:
            MatryoshkaSession object

        Raises:
            RuntimeError: If session creation fails
        """
        if not self.is_available():
            raise RuntimeError("Matryoshka MCP not available")

        try:
            create_fn = self._mcp_tools['mcp__matryoshka__create_session']
            result = create_fn(content=plan, content_type='markdown')

            if isinstance(result, dict):
                session_id = result.get('session_id', result.get('id', ''))
            else:
                session_id = str(result)

            return MatryoshkaSession(
                session_id=session_id,
                plan_content=plan,
                plan_token_count=estimate_tokens(plan),
                active=True,
            )

        except Exception as e:
            raise RuntimeError(f"Failed to create Matryoshka session: {e}")

    def get_slice_for_profile(
        self,
        session: MatryoshkaSession,
        profile: str,
    ) -> SliceResult:
        """
        Extract a domain-specific slice for a reviewer profile.

        Args:
            session: Active Matryoshka session
            profile: Reviewer profile name (e.g., 'security', 'frontend')

        Returns:
            SliceResult with extracted content or fallback
        """
        result = SliceResult(
            profile=profile,
            content="",
            original_token_count=session.plan_token_count,
        )

        # Get query for this profile
        query = PROFILE_QUERIES.get(profile)
        if not query:
            # Unknown profile - use full plan
            result.content = session.plan_content
            result.token_count = session.plan_token_count
            result.used_fallback = True
            result.error = f"No query defined for profile: {profile}"
            return result

        result.query_used = query

        try:
            query_fn = self._mcp_tools['mcp__matryoshka__query']
            query_result = query_fn(
                session_id=session.session_id,
                query=query,
            )

            # Extract content from result
            if isinstance(query_result, dict):
                content = query_result.get('content', query_result.get('result', ''))
            else:
                content = str(query_result)

            result.token_count = estimate_tokens(content)

            # Check if slice is too small (likely missed relevant content)
            if result.token_count < MIN_SLICE_TOKENS:
                result.content = session.plan_content
                result.token_count = session.plan_token_count
                result.used_fallback = True
                result.error = f"Slice too small ({result.token_count} tokens)"
            else:
                result.content = content

        except Exception as e:
            # Graceful fallback to full plan
            result.content = session.plan_content
            result.token_count = session.plan_token_count
            result.used_fallback = True
            result.error = str(e)

        return result

    def get_slices_parallel(
        self,
        session: MatryoshkaSession,
        profiles: list[str],
        max_workers: Optional[int] = None,
    ) -> dict[str, SliceResult]:
        """
        Extract slices for multiple profiles in parallel.

        Args:
            session: Active Matryoshka session
            profiles: List of profile names
            max_workers: Max parallel workers (default: len(profiles))

        Returns:
            Dict mapping profile names to SliceResults
        """
        results: dict[str, SliceResult] = {}

        if max_workers is None:
            max_workers = len(profiles)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_profile = {
                executor.submit(self.get_slice_for_profile, session, profile): profile
                for profile in profiles
            }

            for future in as_completed(future_to_profile):
                profile = future_to_profile[future]
                try:
                    results[profile] = future.result()
                except Exception as e:
                    # Fallback on error
                    results[profile] = SliceResult(
                        profile=profile,
                        content=session.plan_content,
                        token_count=session.plan_token_count,
                        original_token_count=session.plan_token_count,
                        used_fallback=True,
                        error=str(e),
                    )

        return results

    def close_session(self, session: MatryoshkaSession) -> bool:
        """
        Close a Matryoshka session and free resources.

        Args:
            session: The session to close

        Returns:
            True if closed successfully, False otherwise
        """
        if not session.active:
            return True

        try:
            close_fn = self._mcp_tools.get('mcp__matryoshka__close_session')
            if close_fn:
                close_fn(session_id=session.session_id)
            session.active = False
            return True

        except Exception as e:
            # Log warning but don't fail
            print(f"Warning: Failed to close Matryoshka session: {e}", file=sys.stderr)
            session.active = False
            return False

    def compute_stats(self, slices: dict[str, SliceResult]) -> MatryoshkaStats:
        """
        Compute statistics from a set of slice results.

        Args:
            slices: Dict of profile -> SliceResult

        Returns:
            MatryoshkaStats with aggregated metrics
        """
        stats = MatryoshkaStats()

        for profile, slice_result in slices.items():
            stats.total_tokens_sent += slice_result.token_count
            stats.total_tokens_without_slicing += slice_result.original_token_count

            if slice_result.used_fallback:
                stats.profiles_fallback += 1
            else:
                stats.profiles_sliced += 1

        return stats


class MatryoshkaContext:
    """
    Context manager for Matryoshka sessions with guaranteed cleanup.

    Usage:
        client = MatryoshkaClient(mcp_tools)
        with MatryoshkaContext(client, plan) as ctx:
            if ctx.session:
                slices = client.get_slices_parallel(ctx.session, profiles)
    """

    def __init__(self, client: MatryoshkaClient, plan: str, threshold_lines: int = 300):
        self.client = client
        self.plan = plan
        self.threshold_lines = threshold_lines
        self.session: Optional[MatryoshkaSession] = None
        self.enabled = False

    def __enter__(self) -> 'MatryoshkaContext':
        if self.client.should_use_matryoshka(self.plan, self.threshold_lines):
            try:
                self.session = self.client.create_session(self.plan)
                self.enabled = True
            except RuntimeError:
                # Fallback - no session
                pass
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.client.close_session(self.session)
        return False  # Don't suppress exceptions


def main():
    """CLI for testing Matryoshka client (requires MCP tools to be available)."""
    import argparse

    parser = argparse.ArgumentParser(description='Test Matryoshka MCP client')
    parser.add_argument(
        '--check',
        action='store_true',
        help='Check if Matryoshka MCP is available',
    )
    parser.add_argument(
        '--threshold',
        type=int,
        default=300,
        help='Line threshold for activation (default: 300)',
    )

    args = parser.parse_args()

    # Create client without MCP tools (for testing structure)
    client = MatryoshkaClient()

    if args.check:
        if client.is_available():
            print("Matryoshka MCP is available")
            sys.exit(0)
        else:
            print("Matryoshka MCP is NOT available")
            print("Run scripts/install.sh to configure MCP")
            sys.exit(1)

    # Test with stdin input
    plan = sys.stdin.read()
    if not plan.strip():
        print("Error: No plan content provided on stdin", file=sys.stderr)
        sys.exit(1)

    line_count = len(plan.splitlines())
    token_count = estimate_tokens(plan)

    print(f"Plan stats: {line_count} lines, ~{token_count} tokens")
    print(f"Threshold: {args.threshold} lines")
    print(f"Would use Matryoshka: {line_count >= args.threshold}")

    # Show what queries would be used
    print("\nNucleus queries per profile:")
    for profile, query in PROFILE_QUERIES.items():
        print(f"  {profile}: {query[:60]}...")


if __name__ == '__main__':
    main()
