# Skill: /verify-implementation-codex

Verifies an implementation against its plan using OpenAI Codex, identifying matches, improvements, regressions, and missing items. Closes the feedback loop with `/refine-plan-codex`.

## Trigger

User runs `/verify-implementation-codex [plan-path]`

If no plan path is provided, the skill auto-detects the plan from `~/.claude/plan-reviews/{project}/`.

## Workflow

### Phase 1: Plan Discovery

1. **Check Codex CLI availability:**
   ```bash
   codex --version
   ```
   If not installed, inform user: "Codex CLI not found. Install from https://github.com/openai/codex"

2. **Find the plan to verify against:**
   ```bash
   python3 ~/.claude/skills/verify-implementation-codex/scripts/find_plan.py [explicit-path]
   ```
   - If explicit path provided, use that
   - Otherwise, find latest plan in `~/.claude/plan-reviews/{project}/`
   - If no plan found, ask user to provide one

3. **Show discovered plan** to user for confirmation

### Phase 2: Implementation Gathering

1. **Gather implementation diff:**
   ```bash
   python3 ~/.claude/skills/verify-implementation-codex/scripts/gather_implementation.py [--ref=<commit>]
   ```
   - Default: diff against merge-base with main/master
   - Optional: diff against specific commit/ref

2. **Display summary** to user:
   ```
   Found: 8 files changed, 245 additions, 32 deletions
   Base: abc1234 (merge-base with main)
   ```

### Phase 3: Consent & Verification

1. **Scan for secrets** in both plan and diff:
   ```bash
   python3 ~/.claude/skills/refine-plan-codex/scripts/secrets.py --mode=check <<< "$CONTENT"
   ```
   - If secrets found, show warning and offer options:
     - [Redact and proceed] - mask secrets before sending
     - [Cancel] - abort verification
     - [I understand, send anyway] - proceed with secrets

2. **Show consent prompt:**
   ```
   This will send your plan and code diff to Codex for verification.

   - Plan: ~/.claude/plan-reviews/my-api/2026-01-19-jwt-auth.md
   - Diff: 8 files, 245 additions, 32 deletions

   Options:
   1. Yes, proceed
   2. No, cancel
   ```
   Only proceed if user consents.

3. **Build verification prompt** using `references/verification_prompts.md`:
   - Include original plan
   - Include implementation diff
   - Include categorization instructions

4. **Call Codex:**
   ```bash
   python3 ~/.claude/skills/refine-plan-codex/scripts/call_codex.py "$VERIFICATION_PROMPT" <<< "$PLAN_AND_DIFF"
   ```

5. **Parse results:**
   ```bash
   python3 ~/.claude/skills/verify-implementation-codex/scripts/parse_verification.py <<< "$CODEX_RESPONSE"
   ```

### Phase 4: Results & Documentation

1. **Display categorized results** to user:
   - MATCH items
   - IMPROVEMENT items (with explanation)
   - REGRESSION items (highlighted as needing attention)
   - MISSING items (planned but not implemented)
   - UNPLANNED items (implemented but not in plan)

2. **Show summary:**
   ```
   2 matches, 1 improvement, 1 regression, 1 missing, 1 unplanned
   ```

3. **Highlight attention items:**
   ```
   Attention needed:
   - Rate limiting is looser than planned (10/min vs 5/min)
   - Token blacklist not implemented (required for secure logout)
   ```

4. **Save verification report:**
   ```
   ~/.claude/plan-reviews/{project}/{YYYY-MM-DD}-{task-slug}-verify.md
   ```

## Verification Categories

| Category | Marker | Description |
|----------|--------|-------------|
| **MATCH** | `[MATCH]` | Implementation matches plan exactly |
| **IMPROVEMENT** | `[IMPROVEMENT]` | Deviation that's better than planned (more robust, secure, clean) |
| **REGRESSION** | `[REGRESSION]` | Deviation that's worse than planned (missing functionality, less secure) |
| **MISSING** | `[MISSING]` | Planned item not implemented at all |
| **UNPLANNED** | `[UNPLANNED]` | Implemented but not mentioned in plan |

## Output Format

Show progress to user throughout:
```
Looking for plan to verify against...
Found: ~/.claude/plan-reviews/my-api/2026-01-19-jwt-auth.md

Gathering implementation diff (comparing to main)...
Found 8 files changed, 245 additions, 32 deletions.

This will send your plan and code diff to Codex for verification.
[Yes, proceed] [No, cancel]

Sending to Codex for verification...

## Verification Results

- [MATCH] User model with password hashing - bcrypt implementation correct
- [MATCH] Login endpoint - Returns JWT as planned
- [IMPROVEMENT] Refresh tokens - Added token family ID for logout-all-devices
- [REGRESSION] Rate limiting - Only 10/min instead of planned 5/min
- [MISSING] Token blacklist - Redis integration not implemented
- [UNPLANNED] /whoami endpoint - Returns current user info

## Summary
2 matches, 1 improvement, 1 regression, 1 missing, 1 unplanned

Attention needed:
- Rate limiting is looser than planned (10/min vs 5/min)
- Token blacklist not implemented (required for secure logout)

Verification saved to: ~/.claude/plan-reviews/my-api/2026-01-19-jwt-auth-verify.md
```

## Error Handling

| Error | Action |
|-------|--------|
| Codex CLI not found | Show installation instructions |
| No plan found | Ask user to provide plan path or content |
| Not in git repo | Ask user to specify diff manually or provide file list |
| No changes found | Inform user, offer to compare working tree |
| Codex timeout (>120s) | Retry once, then ask user |
| Codex returns error | Show error, ask user how to proceed |
| Parsing fails | Show raw response, continue with manual review |
| Secrets detected | Block by default, offer redact option |

## Configuration

- **Timeout**: 120 seconds per Codex call
- **Plan search path**: `~/.claude/plan-reviews/{project}/`

## Files

| File | Purpose |
|------|---------|
| `scripts/find_plan.py` | Auto-detect plan file from project history |
| `scripts/gather_implementation.py` | Collect git diff for verification |
| `scripts/parse_verification.py` | Parse Codex verification response |
| `references/verification_prompts.md` | Prompt templates for verification |
| `examples/sample_verification.md` | Example verification workflow |

## Reused Scripts (from refine-plan-codex)

| Script | Path |
|--------|------|
| `call_codex.py` | `~/.claude/skills/refine-plan-codex/scripts/call_codex.py` |
| `secrets.py` | `~/.claude/skills/refine-plan-codex/scripts/secrets.py` |
