# Skill: /refine-plan-codex

Automates the workflow of creating a plan, sending it to OpenAI Codex for review, and iterating until the plan is refined.

## Trigger

User runs `/refine-plan-codex <task description>`

## Workflow

### Phase 1: Consent & Initialization

1. **Check Codex CLI availability:**
   ```bash
   codex --version
   ```
   If not installed, inform user: "Codex CLI not found. Install from https://github.com/openai/codex"

2. **Create initial plan** for the user's task using standard planning approach

3. **Scan for secrets** before proceeding:
   ```bash
   python3 ~/.claude/skills/refine-plan-codex/scripts/secrets.py --mode=check <<< "$PLAN"
   ```
   - If secrets found, show warning and offer options:
     - [Redact and proceed] - mask secrets before sending
     - [Cancel] - abort the review
     - [I understand, send anyway] - proceed with secrets (user acknowledges risk)

4. **Show consent prompt:**
   ```
   This will send your plan to Codex for review.

   - The plan will be sent to OpenAI's Codex API
   - A copy will be saved to ~/.claude/plan-reviews/

   Options:
   1. Yes, proceed
   2. No, cancel
   3. Yes, but don't log
   ```
   Only proceed if user consents.

### Phase 2: Iteration Loop (max 5 iterations)

For each iteration:

1. **Build the review prompt** with:
   - Current plan (inline)
   - Previous feedback summary (last 2-3 iterations)
   - Risk-level classification instructions

2. **Call Codex for review:**
   ```bash
   python3 ~/.claude/skills/refine-plan-codex/scripts/call_codex.py "$REVIEW_PROMPT" <<< "$PLAN"
   ```

3. **Parse the response:**
   ```bash
   python3 ~/.claude/skills/refine-plan-codex/scripts/parse_findings.py <<< "$CODEX_RESPONSE"
   ```

4. **Check stop conditions:**
   | Condition | Action |
   |-----------|--------|
   | LGTM or 0 HIGH + 0 MEDIUM | **Stop** - plan approved |
   | Only LOW/NITPICK | **Ask user** - "Only minor findings. Continue?" |
   | Same HIGH/MEDIUM repeated | **Stop** - Codex is looping, surface to user |
   | 5 iterations reached | **Ask user** - "Cap reached. Continue?" |

5. **If continuing:** Update the plan based on Codex feedback, show changes to user

### Phase 3: Documentation

If user consented to logging:

1. Get project name:
   ```bash
   git remote get-url origin 2>/dev/null | sed 's/.*\///' | sed 's/\.git$//' || basename "$(pwd)"
   ```

2. Save documentation to:
   ```
   ~/.claude/plan-reviews/{project-name}/{YYYY-MM-DD}-{task-slug}.md
   ```

3. Include:
   - Original task
   - Each iteration's plan version
   - Each iteration's Codex feedback
   - How feedback was addressed
   - Final approved plan
   - Key learnings

## Review Prompt Template

Use the prompts from `references/review_prompts.md`:
- **Initial review**: Full architectural review
- **Iteration review**: Focus on whether previous concerns were addressed

## Output Format

Show progress to user throughout:
```
Creating initial plan for "{task}"...
[Shows plan]

Sending to Codex for review (iteration 1/5)...

Codex feedback:
- [HIGH] Finding 1...
- [MEDIUM] Finding 2...

Updating plan to address feedback...
[Shows updated plan with changes highlighted]

Sending to Codex for review (iteration 2/5)...

Codex: LGTM - no further changes needed

Plan approved after 2 iterations.
Documentation saved to: ~/.claude/plan-reviews/my-project/2026-01-19-auth.md

[Shows final plan]
```

## Error Handling

| Error | Action |
|-------|--------|
| Codex CLI not found | Show installation instructions |
| Codex timeout (>120s) | Retry once, then ask user |
| Codex returns error | Show error, ask user how to proceed |
| Parsing fails | Show raw response, continue with manual review |
| Secrets detected | Block by default, offer redact option |

## Configuration

- **Max iterations**: 5 (configurable)
- **Timeout**: 120 seconds per Codex call
- **Min Codex version**: v0.85.0

## Files

| File | Purpose |
|------|---------|
| `scripts/call_codex.py` | Safe Codex invocation via stdin |
| `scripts/parse_findings.py` | Extract risk counts from response |
| `scripts/secrets.py` | Secret detection and redaction |
| `references/review_prompts.md` | Prompt templates |
| `examples/sample_session.md` | Example workflow |
