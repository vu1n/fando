# Skill: /fando-plan

Automates the workflow of creating a plan, sending it to OpenAI Codex for review, and iterating until the plan is refined. Part of the Fando toolkit - Claude and Codex working together as the "odd couple" of AI-assisted development.

## Trigger

User runs `/fando-plan <task description>`

## Autonomous Iteration (Ralph-style)

**IMPORTANT**: This skill uses autonomous iteration. Once the user consents to start, Claude should:

1. **Iterate automatically** - Do NOT ask for user input between iterations
2. **Keep looping** - Continue refining the plan until a stop condition is met
3. **Show progress** - Display each iteration's feedback and plan updates as you go
4. **Only pause when necessary** - See stop conditions below

This follows the "Ralph method" philosophy: iterate continuously, accept imperfection, refine until done.

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
   python3 ~/.claude/skills/fando-plan/scripts/secrets.py --mode=check <<< "$PLAN"
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

### Phase 2: Autonomous Iteration Loop (max 5 iterations)

**Loop automatically without user input.** For each iteration:

1. **Build the review prompt** with:
   - Current plan (inline)
   - Previous feedback summary (last 2-3 iterations)
   - Risk-level classification instructions

2. **Call Codex for review:**
   ```bash
   python3 ~/.claude/skills/fando-plan/scripts/call_codex.py "$REVIEW_PROMPT" <<< "$PLAN"
   ```

3. **Parse the response:**
   ```bash
   python3 ~/.claude/skills/fando-plan/scripts/parse_findings.py <<< "$CODEX_RESPONSE"
   ```

4. **Display iteration results** to user (but do NOT wait for input):
   ```
   Iteration 2/5 - Codex feedback:
   - [HIGH] Missing error handling for network failures
   - [MEDIUM] Consider rate limiting

   Addressing feedback...
   ```

5. **Check stop conditions:**

   | Condition | Action |
   |-----------|--------|
   | LGTM or 0 HIGH + 0 MEDIUM | **Stop** - plan approved, proceed to Phase 3 |
   | HIGH or MEDIUM findings | **Continue automatically** - update plan and loop |
   | Only LOW/NITPICK remaining | **Stop** - plan approved (minor issues noted) |
   | Same HIGH/MEDIUM repeated 2x | **Stop** - Codex is stuck, surface to user |
   | 5 iterations reached | **Stop** - ask user if they want to continue |

6. **If continuing:** Update the plan to address feedback, then **immediately loop back to step 1**

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

Show progress continuously (no pausing for input during iteration):

```
Creating initial plan for "{task}"...
[Shows plan]

Starting autonomous review loop...

━━━ Iteration 1/5 ━━━
Sending to Codex...

Codex feedback:
- [HIGH] Missing authentication on admin endpoints
- [MEDIUM] No rate limiting specified

Addressing feedback...
[Shows key changes to plan]

━━━ Iteration 2/5 ━━━
Sending to Codex...

Codex feedback:
- [LOW] Consider adding request logging

✓ Plan approved (only minor findings remain)

━━━ Final Result ━━━
Plan approved after 2 iterations.
Documentation saved to: ~/.claude/plan-reviews/my-project/2026-01-19-auth.md

[Shows final plan]
```

## Error Handling

| Error | Action |
|-------|--------|
| Codex CLI not found | Show installation instructions |
| Codex timeout (>10min) | Retry once, then ask user |
| Codex returns error | Show error, ask user how to proceed |
| Parsing fails | Show raw response, continue with manual review |
| Secrets detected | Block by default, offer redact option |

## Configuration

- **Max iterations**: 5 (configurable)
- **Timeout**: 10 minutes per Codex call
- **Min Codex version**: v0.85.0

## Files

| File | Purpose |
|------|---------|
| `scripts/call_codex.py` | Safe Codex invocation via stdin |
| `scripts/parse_findings.py` | Extract risk counts from response |
| `scripts/secrets.py` | Secret detection and redaction |
| `references/review_prompts.md` | Prompt templates |
| `examples/sample_session.md` | Example workflow |
