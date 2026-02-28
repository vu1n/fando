#!/usr/bin/env python3
"""
review_signatures.py - DSPy Signatures for domain-specific plan review

Provides per-domain Signature classes with domain knowledge encoded in
docstrings. These are the source of truth for what each domain cares about.

Usage:
    from review_signatures import DOMAIN_SIGNATURES

    sig_class = DOMAIN_SIGNATURES["security"]
    print(sig_class.__doc__)  # Domain knowledge lives here
"""
from typing import Any

# DSPy import - optional dependency
try:
    import dspy

    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False
    dspy = None


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
