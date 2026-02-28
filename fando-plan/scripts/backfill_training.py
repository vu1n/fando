#!/usr/bin/env python3
"""
backfill_training.py - Backfill training data from existing plan review logs

Parses structured review logs from ~/.claude/plan-reviews/ and creates
training examples for DSPy reviewer optimization.

Usage:
    python3 backfill_training.py                    # Backfill all
    python3 backfill_training.py --dry-run          # Preview without writing
    python3 backfill_training.py --stats            # Show results after
"""
import argparse
import re
import sys
from pathlib import Path

PLAN_REVIEWS_DIR = Path("~/.claude/plan-reviews").expanduser()


def classify_domain(text: str, profiles: dict[str, dict]) -> str:
    """Classify finding text into a domain using PROFILES keyword lists.

    Args:
        text: Finding text to classify
        profiles: PROFILES dictionary with domain keyword mappings

    Returns:
        Domain name with highest keyword match count, or 'architect' as fallback
    """
    text_lower = text.lower()
    scores: dict[str, int] = {}

    for domain, config in profiles.items():
        count = 0
        for keyword in config["keywords"]:
            pattern = rf"\b{re.escape(keyword)}\b"
            if re.search(pattern, text_lower):
                count += 1
        if count > 0:
            scores[domain] = count

    if not scores:
        return "architect"
    return max(scores, key=scores.get)


def parse_zellij_bridge(path: Path, profiles: dict[str, dict]) -> list[ReviewExample]:
    """Parse willo/zellij-bridge-phase2.md into training examples.

    Args:
        path: Path to the markdown file
        profiles: PROFILES dictionary with domain keyword mappings

    Structure: ### Iteration N: Title, then **SEVERITY (count):** blocks
    with bullet findings, then **Resolution:** line.
    """
    text = path.read_text()
    plan_context = text  # Use full log as plan context

    examples = []
    # Split on iteration headers
    iterations = re.split(r"(?=### Iteration \d+:)", text)

    for block in iterations:
        m = re.match(r"### Iteration (\d+):", block)
        if not m:
            continue
        iteration = int(m.group(1))

        # Extract findings from severity blocks
        findings = []
        severity_counts: dict[str, int] = {}

        for sev_match in re.finditer(
            r"\*\*(HIGH|MEDIUM|LOW)\s*\((\d+)\):\*\*", block
        ):
            severity = sev_match.group(1)
            count = int(sev_match.group(2))
            severity_counts[severity] = severity_counts.get(severity, 0) + count

            # Get the text after this severity header until next severity or Resolution
            start = sev_match.end()
            # Find next severity block or Resolution
            rest = block[start:]
            end_match = re.search(
                r"\*\*(HIGH|MEDIUM|LOW)\s*\(\d+\):\*\*|\*\*Resolution:\*\*", rest
            )
            section = rest[: end_match.start()] if end_match else rest

            for line in section.strip().splitlines():
                line = line.strip()
                if line.startswith("- "):
                    finding_text = line[2:].strip()
                    findings.append((severity, finding_text))

        if not findings:
            continue

        # Build review_output in standard format
        review_lines = []
        for sev, finding in findings:
            review_lines.append(f"- [{sev}] {finding}")
        review_output = "\n".join(review_lines)

        # Determine domain from finding content
        all_finding_text = " ".join(f for _, f in findings)
        domain = classify_domain(all_finding_text, profiles)

        # All findings were acted on (each iteration has Resolution confirming)
        example = ReviewExample(
            plan=plan_context,
            domain=domain,
            other_domains=[],
            security_level="internal",
            review_output=review_output,
            findings_acted_on=[f for _, f in findings],
            findings_ignored=[],
            missed_issues=[],
            stayed_in_lane=True,
            severity_gold=severity_counts,
            plan_id="zellij-bridge-phase2",
            iteration=iteration,
        )
        examples.append(example)

    return examples


def parse_jj_workspace(path: Path, profiles: dict[str, dict]) -> list[ReviewExample]:
    """Parse bacchus/jj-workspace-migration.md into training examples.

    Args:
        path: Path to the markdown file
        profiles: PROFILES dictionary with domain keyword mappings

    The plan body (lines before '## Addressed Codex Findings') is the plan context.
    Findings in '### SEVERITY - Title (vN finding)' blocks with '**Fix**:' lines.
    """
    text = path.read_text()

    # Split plan body from findings section
    findings_split = re.split(r"(?=## Addressed Codex Findings)", text, maxsplit=1)
    plan_context = findings_split[0].strip() if findings_split else text

    # Parse all findings with version info
    finding_pattern = re.compile(
        r"###\s+(HIGH|MEDIUM|LOW)\s+-\s+(.+?)\s+\(v(\d+)\s+finding\)\s*\n"
        r"\*\*(?:Fix|Decision)\*\*:\s*(.+?)(?=\n###|\n---|\n##|\Z)",
        re.DOTALL,
    )

    # Group findings by version
    version_findings: dict[int, list[tuple[str, str, str]]] = {}
    for m in finding_pattern.finditer(text):
        severity = m.group(1)
        title = m.group(2).strip()
        version = int(m.group(3))
        fix = m.group(4).strip()
        version_findings.setdefault(version, []).append((severity, title, fix))

    examples = []
    for version in sorted(version_findings):
        findings = version_findings[version]

        # Build review output
        review_lines = []
        severity_counts: dict[str, int] = {}
        finding_texts = []

        for sev, title, fix in findings:
            review_lines.append(f"- [{sev}] {title}")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            finding_texts.append(title)

        review_output = "\n".join(review_lines)

        # Classify domain from finding content
        all_text = " ".join(f"{title} {fix}" for _, title, fix in findings)
        domain = classify_domain(all_text, profiles)

        # Determine other domains present in this plan
        other_domains = []
        for d in PROFILES:
            if d != domain:
                # Check if domain is relevant to overall plan
                d_keywords = PROFILES[d]["keywords"]
                matches = sum(
                    1
                    for kw in d_keywords
                    if re.search(rf"\b{re.escape(kw)}\b", plan_context.lower())
                )
                if matches >= 2:
                    other_domains.append(d)

        # All findings have explicit **Fix**: → mark as acted on
        example = ReviewExample(
            plan=plan_context,
            domain=domain,
            other_domains=other_domains,
            security_level="internal",
            review_output=review_output,
            findings_acted_on=finding_texts,
            findings_ignored=[],
            missed_issues=[],
            stayed_in_lane=True,
            severity_gold=severity_counts,
            plan_id="jj-workspace-migration",
            iteration=version,
        )
        examples.append(example)

    return examples


def main():
    from detect_profiles import PROFILES
    from dspy_reviewers import ReviewExample, save_training_example, load_training_examples

    parser = argparse.ArgumentParser(
        description="Backfill training data from plan review logs"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without writing"
    )
    parser.add_argument(
        "--stats", action="store_true", help="Show results after backfill"
    )
    args = parser.parse_args()

    all_examples: list["ReviewExample"] = []

    # Parse zellij-bridge-phase2
    zellij_path = PLAN_REVIEWS_DIR / "willo" / "2026-01-19-zellij-bridge-phase2.md"
    if zellij_path.exists():
        try:
            examples = parse_zellij_bridge(zellij_path, PROFILES)
            print(f"Parsed {zellij_path.name}: {len(examples)} examples")
            for ex in examples:
                sev = ex.severity_gold
                print(
                    f"  Iteration {ex.iteration}: {len(ex.findings_acted_on)} findings "
                    f"({sev}) → domain={ex.domain}"
                )
            all_examples.extend(examples)
        except (OSError, UnicodeDecodeError) as e:
            print(f"Error: Failed to read {zellij_path}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"Not found: {zellij_path}")

    # Parse jj-workspace-migration
    jj_path = PLAN_REVIEWS_DIR / "bacchus" / "2026-01-20-jj-workspace-migration.md"
    if jj_path.exists():
        try:
            examples = parse_jj_workspace(jj_path, PROFILES)
            print(f"\nParsed {jj_path.name}: {len(examples)} examples")
            for ex in examples:
                sev = ex.severity_gold
                print(
                    f"  v{ex.iteration}: {len(ex.findings_acted_on)} findings "
                    f"({sev}) → domain={ex.domain}"
                )
            all_examples.extend(examples)
        except (OSError, UnicodeDecodeError) as e:
            print(f"Error: Failed to read {jj_path}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"Not found: {jj_path}")

    print(f"\nTotal: {len(all_examples)} examples")

    if args.dry_run:
        print("\n[DRY RUN] No files written.")
        return

    # Write examples
    written = 0
    for ex in all_examples:
        path = save_training_example(ex)
        print(f"  Saved: {path.name}")
        written += 1

    print(f"\nWrote {written} training examples")

    if args.stats:
        print("\n--- Training Data Stats ---")
        examples = load_training_examples()
        domains: dict[str, int] = {}
        for ex in examples:
            domains[ex.domain] = domains.get(ex.domain, 0) + 1
        print(f"Total: {len(examples)}")
        for domain in sorted(domains):
            print(f"  {domain}: {domains[domain]}")


if __name__ == "__main__":
    main()
