#!/usr/bin/env python3
"""
dspy_reviewers.py - DSPy-based plan review system with per-domain Signatures

Replaces hand-crafted markdown prompts with DSPy Signatures so reviewers become
modular, structured, and optimizable with GEPA. Domain knowledge lives in Signature
docstrings (source of truth), not in separate markdown files.

Usage:
    from dspy_reviewers import run_dspy_review, prediction_to_review_output

    results = run_dspy_review(plan, profiles, security_level="public")
    for profile, prediction in results.items():
        text = prediction_to_review_output(prediction)
        parsed = parse_findings(text)
"""
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# DSPy import - optional dependency
try:
    import dspy

    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False
    dspy = None


# ---------------------------------------------------------------------------
# Paths for persistent state
# ---------------------------------------------------------------------------

SKILL_DIR = Path("~/.claude/skills/fando-plan").expanduser()
OPTIMIZED_DIR = SKILL_DIR / "optimized"
TRAINING_DIR = SKILL_DIR / "training_data"


# ===========================================================================
# Training Labeling Constants and Policies
# ===========================================================================

# Minimum word length to consider a word "significant" for matching
SIGNIFICANT_WORD_MIN_LENGTH = 4

# Threshold for considering a finding "acted on" based on word overlap
# If > this fraction of significant words appear in the diff, count as addressed
FINDING_ADDRESS_THRESHOLD = 0.3

# Domain focus weight for staying in lane vs crossing domains
DOMAIN_FOCUS_WEIGHT_IN_LANE = 1.0
DOMAIN_FOCUS_WEIGHT_OUT_OF_LANE = 0.3


# ===========================================================================
# Per-Domain Signatures — docstrings encode domain knowledge from profiles/*.md
# ===========================================================================

if DSPY_AVAILABLE:

    # --- Security -----------------------------------------------------------

    class SecurityReviewSignature(dspy.Signature):
        """Review an implementation plan for security vulnerabilities.

        You are a senior security engineer. Focus on authentication (AuthN),
        authorization (AuthZ), input validation, secrets management, data
        protection, and the OWASP Top 10.

        Adjust severity based on security_level:
        - personal: only flag critical issues (secrets, obvious vulns). Skip rate
          limiting, audit logs, compliance.
        - internal: flag auth issues, basic input validation. Skip compliance,
          advanced threat modeling.
        - public: full security review. Rate limiting, CSRF, input validation all
          important.
        - enterprise: maximum rigor. Audit logs, encryption, compliance docs all
          HIGH priority.

        Severity matrix examples:
        | Finding              | personal | internal | public | enterprise |
        |----------------------|----------|----------|--------|------------|
        | Hardcoded secrets    | HIGH     | HIGH     | HIGH   | HIGH       |
        | No rate limiting     | -        | LOW      | MEDIUM | HIGH       |
        | No CSRF protection   | -        | LOW      | HIGH   | HIGH       |
        | No input validation  | LOW      | MEDIUM   | HIGH   | HIGH       |
        | No audit logging     | -        | -        | LOW    | HIGH       |

        Risk levels:
        - HIGH: vulnerability leading to data breach, unauthorized access, or compromise
        - MEDIUM: best practice not followed; potential weakness
        - LOW: defense-in-depth suggestion
        - NITPICK: stylistic security preference

        Be specific about vulnerability and attack vector. Provide actionable
        remediation. Don't flag theoretical issues outside the plan's context.
        """

        plan: str = dspy.InputField(desc="The full implementation plan to review")
        other_reviewers: str = dspy.InputField(
            desc="Other domains being reviewed — don't duplicate their findings"
        )
        security_level: str = dspy.InputField(
            desc="Security context: personal, internal, public, or enterprise"
        )

        findings: str = dspy.OutputField(
            desc="Bullet list: '- [HIGH/MEDIUM/LOW/NITPICK] description' for security issues only"
        )
        summary: str = dspy.OutputField(
            desc="'X high, Y medium, Z low, W nitpick' or 'LGTM - no security issues identified'"
        )

    # --- Frontend -----------------------------------------------------------

    class FrontendReviewSignature(dspy.Signature):
        """Review an implementation plan for frontend architecture concerns.

        You are a senior frontend architect. Focus on component architecture
        (hierarchy, composition, reusability), state management (local vs global,
        server sync, cache invalidation), UX patterns (loading/error/empty states,
        form validation, navigation), accessibility (semantic HTML, ARIA, keyboard
        nav, focus management, contrast), performance (code splitting, memoization,
        bundle size), and responsive design (mobile-first, breakpoints, touch).

        Risk levels:
        - HIGH: architectural flaw causing significant rework or poor UX
        - MEDIUM: missing UX consideration or component design issue
        - LOW: minor improvement to structure or polish
        - NITPICK: stylistic preference or optional enhancement

        Focus on patterns over syntax. Consider the full user journey including
        edge cases (slow network, errors, empty data). Prioritize accessibility.
        """

        plan: str = dspy.InputField(desc="The full implementation plan to review")
        other_reviewers: str = dspy.InputField(
            desc="Other domains being reviewed — don't duplicate their findings"
        )
        security_level: str = dspy.InputField(
            desc="Security context: personal, internal, public, or enterprise"
        )

        findings: str = dspy.OutputField(
            desc="Bullet list: '- [HIGH/MEDIUM/LOW/NITPICK] description' for frontend issues only"
        )
        summary: str = dspy.OutputField(
            desc="'X high, Y medium, Z low, W nitpick' or 'LGTM - frontend architecture looks solid'"
        )

    # --- API ----------------------------------------------------------------

    class APIReviewSignature(dspy.Signature):
        """Review an implementation plan for API design concerns.

        You are a senior API architect. Focus on contract design (RESTful naming,
        HTTP method semantics, payload structure, GraphQL schema), versioning
        (backwards compat, deprecation), error handling (consistent format, status
        codes, validation errors), pagination and filtering (cursor vs offset,
        metadata, large result sets), rate limiting (strategy, headers, retry-after),
        and developer experience (OpenAPI spec, examples, docs).

        Risk levels:
        - HIGH: design flaw causing breaking changes or poor client experience
        - MEDIUM: missing error handling, pagination, or versioning consideration
        - LOW: minor polish or best practice suggestion
        - NITPICK: naming convention or documentation preference

        Think about API consumers. Ensure consistent patterns across endpoints.
        Consider both success and error paths. Plan for API evolution.
        """

        plan: str = dspy.InputField(desc="The full implementation plan to review")
        other_reviewers: str = dspy.InputField(
            desc="Other domains being reviewed — don't duplicate their findings"
        )
        security_level: str = dspy.InputField(
            desc="Security context: personal, internal, public, or enterprise"
        )

        findings: str = dspy.OutputField(
            desc="Bullet list: '- [HIGH/MEDIUM/LOW/NITPICK] description' for API issues only"
        )
        summary: str = dspy.OutputField(
            desc="'X high, Y medium, Z low, W nitpick' or 'LGTM - API design looks solid'"
        )

    # --- Data ---------------------------------------------------------------

    class DataReviewSignature(dspy.Signature):
        """Review an implementation plan for data architecture concerns.

        You are a senior data architect. Focus on schema design (normalization,
        keys, constraints, indexes, data types), query performance (N+1 problems,
        missing indexes, join complexity, pagination), data integrity (referential
        integrity, cascades, validation, uniqueness), transactions and consistency
        (ACID, boundaries, locking, eventual consistency), migration strategy
        (backwards compat, zero-downtime, rollback, backfill), and scalability
        (sharding, read replicas, connection pooling, large tables).

        Risk levels:
        - HIGH: schema flaw requiring significant migration or causing data integrity issues
        - MEDIUM: missing index, suboptimal design, or query performance issue
        - LOW: minor optimization or best practice suggestion
        - NITPICK: naming convention or stylistic preference

        Think about data at scale. Consider read vs write patterns. Ensure
        migration paths exist. Flag potential N+1 scenarios.
        """

        plan: str = dspy.InputField(desc="The full implementation plan to review")
        other_reviewers: str = dspy.InputField(
            desc="Other domains being reviewed — don't duplicate their findings"
        )
        security_level: str = dspy.InputField(
            desc="Security context: personal, internal, public, or enterprise"
        )

        findings: str = dspy.OutputField(
            desc="Bullet list: '- [HIGH/MEDIUM/LOW/NITPICK] description' for data issues only"
        )
        summary: str = dspy.OutputField(
            desc="'X high, Y medium, Z low, W nitpick' or 'LGTM - data architecture looks solid'"
        )

    # --- DevOps -------------------------------------------------------------

    class DevOpsReviewSignature(dspy.Signature):
        """Review an implementation plan for operational readiness.

        You are a senior DevOps engineer. Focus on deployment strategy (blue-green,
        canary, rolling, rollback, feature flags, zero-downtime), CI/CD (build, test,
        lint, security scanning, artifacts, automation), infrastructure (env parity,
        IaC, containers, service discovery, load balancing), observability (logging,
        metrics, tracing, alerting, health checks), scaling and reliability (auto-scale,
        circuit breakers, graceful degradation, disaster recovery), and secrets/config
        (management, env-specific config, rotation).

        Risk levels:
        - HIGH: deployment risk that could cause outage or data loss
        - MEDIUM: missing observability, scaling, or operational concern
        - LOW: minor operational improvement or automation opportunity
        - NITPICK: tooling preference or documentation suggestion

        Think about day-2 operations. Consider failure modes and recovery. Ensure
        observability is built in. Plan for growth and unexpected load.
        """

        plan: str = dspy.InputField(desc="The full implementation plan to review")
        other_reviewers: str = dspy.InputField(
            desc="Other domains being reviewed — don't duplicate their findings"
        )
        security_level: str = dspy.InputField(
            desc="Security context: personal, internal, public, or enterprise"
        )

        findings: str = dspy.OutputField(
            desc="Bullet list: '- [HIGH/MEDIUM/LOW/NITPICK] description' for devops issues only"
        )
        summary: str = dspy.OutputField(
            desc="'X high, Y medium, Z low, W nitpick' or 'LGTM - operational readiness looks good'"
        )

    # --- Performance --------------------------------------------------------

    class PerformanceReviewSignature(dspy.Signature):
        """Review an implementation plan for performance concerns.

        You are a senior performance engineer. Focus on caching (what to cache,
        invalidation, levels, TTL, warming), database performance (query optimization,
        connection pooling, read replicas, indexes, batch ops), API performance
        (response time, payload size, compression, HTTP/2-3, connection reuse),
        frontend performance (bundle size, code splitting, lazy loading, images,
        Core Web Vitals), concurrency (async processing, queues, parallel ops,
        resource contention), and scalability (horizontal readiness, stateless
        design, bottleneck identification, load testing, capacity planning).

        Risk levels:
        - HIGH: issue causing poor UX or system instability at scale
        - MEDIUM: missing optimization for production readiness
        - LOW: minor performance improvement opportunity
        - NITPICK: micro-optimization or edge case

        Focus on measurable impact. Consider worst-case scenarios. Don't
        prematurely optimize — focus on likely bottlenecks. Suggest profiling.
        """

        plan: str = dspy.InputField(desc="The full implementation plan to review")
        other_reviewers: str = dspy.InputField(
            desc="Other domains being reviewed — don't duplicate their findings"
        )
        security_level: str = dspy.InputField(
            desc="Security context: personal, internal, public, or enterprise"
        )

        findings: str = dspy.OutputField(
            desc="Bullet list: '- [HIGH/MEDIUM/LOW/NITPICK] description' for performance issues only"
        )
        summary: str = dspy.OutputField(
            desc="'X high, Y medium, Z low, W nitpick' or 'LGTM - performance approach looks solid'"
        )

    # --- Architect (final pass) ---------------------------------------------

    class ArchitectReviewSignature(dspy.Signature):
        """Perform the final systems-architect review of an implementation plan.

        You are a senior systems architect. This plan has already been reviewed by
        domain specialists. Your job is to:
        1. Resolve conflicts between specialist recommendations
        2. Check cross-cutting concerns (error handling, logging, config, testing, docs)
        3. Ensure overall coherence (boundaries, dependencies, interfaces, complexity)
        4. Final sanity check for implementation readiness

        Conflict resolution examples:
        - Security wants strict rate limits, Performance wants throughput → context-dependent
        - Frontend wants client-side validation, Security wants server-side → both
        - DevOps wants simple deploy, Data wants complex migration → phased approach

        Risk levels:
        - HIGH: architectural flaw, unresolved conflict, or blocker
        - MEDIUM: cross-cutting concern or coherence issue
        - LOW: minor improvement or future consideration
        - NITPICK: stylistic preference or optional enhancement

        You have the final say on trade-offs. Be decisive. Consider the full system.
        If the plan is solid, say so and approve it.
        """

        plan: str = dspy.InputField(desc="The full implementation plan to review")
        other_reviewers: str = dspy.InputField(
            desc="Specialist domains that already reviewed this plan"
        )
        security_level: str = dspy.InputField(
            desc="Security context: personal, internal, public, or enterprise"
        )

        findings: str = dspy.OutputField(
            desc="Bullet list: '- [HIGH/MEDIUM/LOW/NITPICK] description' for cross-cutting issues"
        )
        summary: str = dspy.OutputField(
            desc="'X high, Y medium, Z low, W nitpick' or 'LGTM - plan approved for implementation'"
        )


# ===========================================================================
# Domain Signature Registry
# ===========================================================================

DOMAIN_SIGNATURES: dict[str, Any] = {}

if DSPY_AVAILABLE:
    DOMAIN_SIGNATURES = {
        "security": SecurityReviewSignature,
        "frontend": FrontendReviewSignature,
        "api": APIReviewSignature,
        "data": DataReviewSignature,
        "devops": DevOpsReviewSignature,
        "performance": PerformanceReviewSignature,
        "architect": ArchitectReviewSignature,
    }


# ===========================================================================
# DSPy Module
# ===========================================================================

if DSPY_AVAILABLE:

    class DomainReviewModule(dspy.Module):
        """DSPy module that performs a plan review for a specific domain.

        Wraps ChainOfThought around the domain's Signature. Can be optimized
        independently via GEPA.
        """

        def __init__(self, domain: str):
            super().__init__()
            if domain not in DOMAIN_SIGNATURES:
                raise ValueError(
                    f"Unknown domain: {domain}. Available: {list(DOMAIN_SIGNATURES)}"
                )
            self.domain = domain
            self.reviewer = dspy.ChainOfThought(DOMAIN_SIGNATURES[domain])

        def forward(
            self,
            plan: str,
            other_reviewers: str,
            security_level: str = "public",
        ) -> dspy.Prediction:
            return self.reviewer(
                plan=plan,
                other_reviewers=other_reviewers,
                security_level=security_level,
            )


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
        Dict mapping profile name → dspy.Prediction
    """
    if not DSPY_AVAILABLE:
        raise ImportError("DSPy is required: uv pip install -e '.[dspy]'")

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


# ===========================================================================
# Output Conversion — prediction_to_review_output
# ===========================================================================


def prediction_to_review_output(prediction: Any) -> str:
    """Convert a DSPy Prediction into the text format parse_findings.py expects.

    Expected output:
        ## Findings
        - [HIGH] description...
        - [MEDIUM] description...

        ## Summary
        X high, Y medium...

    Note: If prediction is an Exception, returns error text that should be
    detected as a failure by the caller.
    """
    if isinstance(prediction, Exception):
        # Return explicit error marker that can be detected
        return f"## Findings\n\n## Summary\nError: DSPY_EXECUTION_FAILED: {prediction}"

    findings = getattr(prediction, "findings", "")
    summary = getattr(prediction, "summary", "")

    # Normalize findings: ensure each line starts with "- ["
    normalized_lines = []
    for line in findings.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # Ensure bullet prefix
        if re.match(r"\[(?:HIGH|MEDIUM|LOW|NITPICK)\]", line):
            line = f"- {line}"
        normalized_lines.append(line)

    findings_text = "\n".join(normalized_lines) if normalized_lines else "No issues found."

    return f"## Findings\n{findings_text}\n\n## Summary\n{summary}"


# ===========================================================================
# Metric — review_metric for GEPA
# ===========================================================================


@dataclass
class ReviewExample:
    """A labeled review example for training/evaluation."""

    plan: str
    domain: str
    other_domains: list[str]
    security_level: str
    review_output: str

    # Evaluation labels (filled after reviewing outcomes)
    findings_acted_on: list[str] = field(default_factory=list)
    findings_ignored: list[str] = field(default_factory=list)
    missed_issues: list[str] = field(default_factory=list)
    stayed_in_lane: bool = True
    severity_gold: dict[str, int] = field(default_factory=dict)  # {"HIGH": 2, "MEDIUM": 1, ...}

    # Metadata
    plan_id: str | None = None
    iteration: int | None = None


def review_metric(
    gold: ReviewExample,
    pred: Any,
    trace: Any = None,
    **kwargs,
) -> dict[str, Any]:
    """Evaluate review quality for GEPA optimization.

    Scoring (0-1):
      - Precision  (25%): predicted findings ∩ findings_acted_on / total predicted
      - Recall     (25%): missed_issues caught in predicted / total missed
      - Domain focus (20%): stayed in lane
      - Actionability (15%): findings contain remediation language
      - Severity calibration (15%): HIGH/MEDIUM distribution matches gold

    Returns dict with 'score' (float 0-1) and 'feedback' (str for GEPA reflection).
    """
    findings_text = getattr(pred, "findings", "")
    pred_findings = _extract_finding_texts(findings_text)
    pred_levels = _extract_finding_levels(findings_text)

    feedback_parts = []

    # --- Precision (25%) ---
    if pred_findings and gold.findings_acted_on:
        acted_set = {f.lower()[:80] for f in gold.findings_acted_on}
        matched = sum(
            1
            for f in pred_findings
            if any(_text_overlap(f.lower()[:80], a) > 0.5 for a in acted_set)
        )
        precision = matched / len(pred_findings) if pred_findings else 0.0
    elif not pred_findings and not gold.findings_acted_on:
        precision = 1.0  # Both empty = correct
    elif not pred_findings:
        precision = 0.0 if gold.findings_acted_on else 1.0
    else:
        # Predictions exist but no gold labels — assume moderate
        precision = 0.5
    feedback_parts.append(f"Precision: {precision:.0%} of findings were acted upon")

    # --- Recall (25%) ---
    if gold.missed_issues:
        caught = sum(
            1
            for m in gold.missed_issues
            if any(
                _text_overlap(m.lower()[:80], f.lower()[:80]) > 0.5
                for f in pred_findings
            )
        )
        recall = caught / len(gold.missed_issues)
    elif not gold.missed_issues:
        recall = 1.0  # Nothing was missed
    else:
        recall = 0.5
    feedback_parts.append(f"Recall: {recall:.0%} of important issues caught")

    # --- Domain Focus (20%) ---
    domain_focus = DOMAIN_FOCUS_WEIGHT_IN_LANE if gold.stayed_in_lane else DOMAIN_FOCUS_WEIGHT_OUT_OF_LANE
    if not gold.stayed_in_lane:
        feedback_parts.append("Domain focus: reviewer flagged issues outside their domain")
    else:
        feedback_parts.append("Domain focus: reviewer stayed in their lane")

    # --- Actionability (15%) ---
    action_keywords = [
        "should", "consider", "add", "implement", "use", "change",
        "replace", "remove", "ensure", "validate", "protect", "require",
    ]
    if pred_findings:
        actionable_count = sum(
            1
            for f in pred_findings
            if any(kw in f.lower() for kw in action_keywords)
        )
        actionability = actionable_count / len(pred_findings)
    else:
        actionability = 1.0  # No findings = nothing needs to be actionable
    feedback_parts.append(f"Actionability: {actionability:.0%} of findings have remediation language")

    # --- Severity Calibration (15%) ---
    if gold.severity_gold and pred_levels:
        total_diff = 0
        total_expected = 0
        for level in ("HIGH", "MEDIUM", "LOW", "NITPICK"):
            expected = gold.severity_gold.get(level, 0)
            actual = pred_levels.get(level, 0)
            total_diff += abs(expected - actual)
            total_expected += expected
        if total_expected > 0:
            severity_cal = max(0.0, 1.0 - total_diff / (total_expected + 1))
        else:
            severity_cal = 1.0 if sum(pred_levels.values()) == 0 else 0.5
    else:
        severity_cal = 0.5  # No gold labels
    feedback_parts.append(f"Severity calibration: {severity_cal:.0%}")

    # --- Weighted combination ---
    weights = {
        "precision": 0.25,
        "recall": 0.25,
        "domain_focus": 0.20,
        "actionability": 0.15,
        "severity_cal": 0.15,
    }
    scores = {
        "precision": precision,
        "recall": recall,
        "domain_focus": domain_focus,
        "actionability": actionability,
        "severity_cal": severity_cal,
    }
    final_score = sum(scores[k] * weights[k] for k in weights)

    return {
        "score": final_score,
        "feedback": "\n".join(feedback_parts),
        **scores,
    }


def _extract_finding_texts(findings_str: str) -> list[str]:
    """Extract finding description texts from formatted findings string."""
    results = []
    for line in findings_str.strip().splitlines():
        m = re.match(r"^-?\s*\[(HIGH|MEDIUM|LOW|NITPICK)\]\s*(.+)", line.strip(), re.IGNORECASE)
        if m:
            results.append(m.group(2).strip())
    return results


def _extract_finding_levels(findings_str: str) -> dict[str, int]:
    """Count findings by severity level."""
    counts: dict[str, int] = {}
    for line in findings_str.strip().splitlines():
        m = re.match(r"^-?\s*\[(HIGH|MEDIUM|LOW|NITPICK)\]", line.strip(), re.IGNORECASE)
        if m:
            level = m.group(1).upper()
            counts[level] = counts.get(level, 0) + 1
    return counts


def _text_overlap(a: str, b: str) -> float:
    """Simple word-overlap similarity between two strings."""
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    return len(intersection) / max(len(words_a), len(words_b))


# ===========================================================================
# Training Data Collection
# ===========================================================================


def collect_training_example(
    plan_before: str,
    plan_after: str,
    domain: str,
    review_output: str,
    other_domains: list[str],
    security_level: str = "public",
    plan_id: str | None = None,
    iteration: int | None = None,
) -> ReviewExample:
    """Create a training example by comparing plan versions.

    Determines which findings were acted on by diffing plan_before vs plan_after.
    Findings whose described concern appears addressed in plan_after are marked
    as 'findings_acted_on'; the rest are 'findings_ignored'.
    """
    pred_findings = _extract_finding_texts(review_output)

    findings_acted_on = []
    findings_ignored = []

    # Simple heuristic: if key terms from a finding appear in the diff
    # (plan_after minus plan_before), the finding was likely addressed
    added_text = _get_added_text(plan_before, plan_after).lower()

    for finding in pred_findings:
        # Extract significant words from the finding
        sig_words = [w for w in finding.lower().split() if len(w) > SIGNIFICANT_WORD_MIN_LENGTH]
        if sig_words:
            matches = sum(1 for w in sig_words if w in added_text)
            if matches / len(sig_words) > FINDING_ADDRESS_THRESHOLD:
                findings_acted_on.append(finding)
            else:
                findings_ignored.append(finding)
        else:
            findings_ignored.append(finding)

    return ReviewExample(
        plan=plan_before,
        domain=domain,
        other_domains=other_domains,
        security_level=security_level,
        review_output=review_output,
        findings_acted_on=findings_acted_on,
        findings_ignored=findings_ignored,
        missed_issues=[],  # Can only be filled by later analysis
        stayed_in_lane=True,  # Default; can be relabeled
        plan_id=plan_id,
        iteration=iteration,
    )


def _get_added_text(before: str, after: str) -> str:
    """Return text present in after but not in before (line-level diff)."""
    before_lines = set(before.splitlines())
    after_lines = after.splitlines()
    added = [line for line in after_lines if line not in before_lines]
    return "\n".join(added)


# ===========================================================================
# Save / Load Helpers
# ===========================================================================


def save_optimized_module(domain: str, module: Any) -> Path:
    """Save an optimized DSPy module's state to disk.

    Args:
        domain: Domain name (e.g. "security")
        module: Optimized DomainReviewModule

    Returns:
        Path to the saved file
    """
    OPTIMIZED_DIR.mkdir(parents=True, exist_ok=True)
    path = OPTIMIZED_DIR / f"{domain}.json"
    module.save(str(path))
    return path


def load_optimized_module(domain: str) -> Optional[Any]:
    """Load a GEPA-optimized module if it exists.

    Returns:
        DomainReviewModule with optimized state, or None if not found
    """
    if not DSPY_AVAILABLE:
        return None

    path = OPTIMIZED_DIR / f"{domain}.json"
    if not path.exists():
        return None

    try:
        mod = DomainReviewModule(domain=domain)
        mod.load(str(path))
        return mod
    except Exception:
        return None


def save_training_example(example: ReviewExample) -> Path:
    """Persist a training example to the training data directory."""
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)

    # Filename: {domain}_{plan_id or timestamp}.json
    name_part = example.plan_id or str(int(__import__("time").time()))
    iter_part = f"_iter{example.iteration}" if example.iteration is not None else ""
    path = TRAINING_DIR / f"{example.domain}_{name_part}{iter_part}.json"

    data = {
        "plan": example.plan,
        "domain": example.domain,
        "other_domains": example.other_domains,
        "security_level": example.security_level,
        "review_output": example.review_output,
        "findings_acted_on": example.findings_acted_on,
        "findings_ignored": example.findings_ignored,
        "missed_issues": example.missed_issues,
        "stayed_in_lane": example.stayed_in_lane,
        "severity_gold": example.severity_gold,
        "plan_id": example.plan_id,
        "iteration": example.iteration,
    }
    path.write_text(json.dumps(data, indent=2))
    return path


def load_training_examples(domain: str | None = None) -> list[ReviewExample]:
    """Load training examples from disk.

    Args:
        domain: Filter to a specific domain, or None for all.

    Returns:
        List of ReviewExample
    """
    examples = []
    if not TRAINING_DIR.exists():
        return examples

    for f in sorted(TRAINING_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            if domain and data.get("domain") != domain:
                continue
            examples.append(
                ReviewExample(
                    plan=data["plan"],
                    domain=data["domain"],
                    other_domains=data.get("other_domains", []),
                    security_level=data.get("security_level", "public"),
                    review_output=data.get("review_output", ""),
                    findings_acted_on=data.get("findings_acted_on", []),
                    findings_ignored=data.get("findings_ignored", []),
                    missed_issues=data.get("missed_issues", []),
                    stayed_in_lane=data.get("stayed_in_lane", True),
                    severity_gold=data.get("severity_gold", {}),
                    plan_id=data.get("plan_id"),
                    iteration=data.get("iteration"),
                )
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Skipping malformed training file {f.name}: {e}")
            continue

    return examples


# ===========================================================================
# CLI
# ===========================================================================


def main():
    """CLI for testing DSPy reviewer integration."""
    import argparse

    parser = argparse.ArgumentParser(
        description="DSPy-based plan review system"
    )
    parser.add_argument("--check", action="store_true", help="Check DSPy availability")
    parser.add_argument(
        "--list-domains", action="store_true", help="List available domain signatures"
    )
    parser.add_argument("--stats", action="store_true", help="Training data statistics")

    args = parser.parse_args()

    if args.check:
        if DSPY_AVAILABLE:
            version = getattr(dspy, "__version__", "unknown")
            print(f"DSPy available: {version}")
            print(f"Domains: {', '.join(DOMAIN_SIGNATURES)}")
        else:
            print("DSPy not installed. Run: uv pip install dspy>=2.6.0")
        return

    if args.list_domains:
        for name, sig_cls in DOMAIN_SIGNATURES.items():
            doc_first_line = (sig_cls.__doc__ or "").strip().splitlines()[0]
            print(f"  {name}: {doc_first_line}")
        return

    if args.stats:
        examples = load_training_examples()
        if not examples:
            print("No training data found.")
            print(f"  Expected location: {TRAINING_DIR}")
            return

        domains: dict[str, int] = {}
        for ex in examples:
            domains[ex.domain] = domains.get(ex.domain, 0) + 1

        print(f"Training data: {len(examples)} examples")
        for domain, count in sorted(domains.items()):
            print(f"  {domain}: {count}")
        return

    print("DSPy reviewer system ready." if DSPY_AVAILABLE else "DSPy not installed.")
    print("Use --check, --list-domains, or --stats for info.")


if __name__ == "__main__":
    main()
