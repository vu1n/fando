# Skill: /fando-plan

Automates the workflow of creating a plan, sending it to OpenAI Codex for review, and iterating until the plan is refined. Part of the Fando toolkit - Claude and Codex working together as the "odd couple" of AI-assisted development.

## Trigger

User runs `/fando-plan [--security=<level>] <task description>`

**Options:**
- `--security=personal` - Minimal security review (side projects)
- `--security=internal` - Standard security (internal tools)
- `--security=public` - Strict security (customer-facing) [default]
- `--security=enterprise` - Maximum security (regulated/compliance)

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

2. **Explore codebase** to inform the plan (see [Codebase Exploration Strategy](#codebase-exploration-strategy) below)

3. **Create initial plan** for the user's task using insights from exploration

4. **Scan for secrets** before proceeding:
   ```bash
   python3 ~/.claude/skills/fando-plan/scripts/secrets.py --mode=check <<< "$PLAN"
   ```
   - If secrets found, show warning and offer options:
     - [Redact and proceed] - mask secrets before sending
     - [Cancel] - abort the review
     - [I understand, send anyway] - proceed with secrets (user acknowledges risk)

5. **Detect or confirm security level:**
   ```bash
   python3 ~/.claude/skills/fando-plan/scripts/detect_security_level.py <<< "$PLAN"
   ```

   - If `--security=X` flag provided: use that level
   - If auto-detected with high confidence (>0.7): use detected level
   - Otherwise: show detected level and ask user to confirm:
     ```
     Detected security level: internal (matched: "admin dashboard", "employee")

     Options:
     1. Yes, use internal
     2. Change to: personal / public / enterprise
     ```

   Display the level being used:
   ```
   Security level: internal
   └─ Auth issues flagged, compliance checks skipped
   ```

6. **Show consent prompt:**
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

### Phase 2: Parallel Specialist Reviews (NEW)

After initial plan creation, run specialized reviewers in parallel for domain-specific feedback.

#### 2.1 Detect Relevant Profiles

```bash
python3 ~/.claude/skills/fando-plan/scripts/detect_profiles.py <<< "$PLAN"
```

Returns profiles based on plan content (e.g., `["security", "frontend", "api"]`).

**Available Profiles:**

| Profile | Trigger Keywords | Focus Areas |
|---------|------------------|-------------|
| **Security** | auth, password, token, jwt, encrypt, secret, permission, role | Auth, authz, input validation, secrets, OWASP |
| **Frontend** | react, vue, component, css, ui, ux, form, modal, state, hook | Components, state, accessibility, UX patterns |
| **Data** | database, schema, migration, query, sql, table, index, postgres | Schema design, queries, indexes, consistency |
| **API** | endpoint, rest, graphql, route, request, response, http, webhook | Contract design, versioning, error handling |
| **DevOps** | deploy, ci/cd, docker, k8s, pipeline, terraform, aws, monitoring | Infrastructure, deployment, observability |
| **Performance** | cache, optimize, latency, throughput, scale, load, memory | Bottlenecks, caching, optimization strategies |

#### 2.2 Display Selected Reviewers

```
Detected plan components: authentication, React UI, REST endpoints

Running specialist reviewers in parallel:
  ├─ Security Reviewer
  ├─ Frontend Architect
  └─ API Designer
```

#### 2.3 Parallel-then-Merge Iteration Loop (max 5 iterations)

**FOR EACH ITERATION:**

1. **Run ALL selected reviewers in parallel:**
   ```bash
   python3 ~/.claude/skills/fando-plan/scripts/run_parallel_reviews.py \
     --security-level=$SECURITY_LEVEL \
     security frontend api <<< "$PLAN"
   ```

2. **Aggregate findings from all reviewers:**
   ```bash
   python3 ~/.claude/skills/fando-plan/scripts/aggregate_findings.py <<< "$PARALLEL_RESULTS"
   ```

3. **Display findings grouped by reviewer:**
   ```
   ━━━ Iteration 1/5 Findings ━━━

   Security Reviewer:
   - [HIGH] Missing CSRF protection on auth endpoints
   - [MEDIUM] JWT expiry too long (24h → recommend 1h)

   Frontend Architect:
   - [MEDIUM] No loading states defined for async operations

   API Designer:
   - [MEDIUM] Missing rate limiting on public endpoints

   ⚠️  Potential Conflict Detected:
   - Security: "Strict rate limit 10/min"
   - Performance: "Rate limit too aggressive"
   💡 Will resolve in architect review
   ```

4. **Claude updates plan ONCE to address ALL findings**

5. **Check stop conditions:**

   | Condition | Action |
   |-----------|--------|
   | 0 HIGH + 0 MEDIUM from all reviewers | **Stop** - proceed to Phase 2.4 (Architect Review) |
   | HIGH or MEDIUM findings remain | **Continue** - loop back to step 1 |
   | Same findings repeated 2x | **Stop** - surface to user |
   | 5 iterations reached | **Stop** - proceed to architect with remaining issues |

6. **Track what was addressed:**
   ```
   ━━━ Iteration 1 → 2 Changes ━━━
   ✓ [ADDRESSED] CSRF protection → Added to auth middleware spec
   ✓ [ADDRESSED] JWT expiry → Changed to 1h with refresh tokens
   ✓ [ADDRESSED] Loading states → Added UX section with states
   ✓ [ADDRESSED] Rate limiting → Added to API spec
   ```

7. **Collect training data** (if logging enabled):
   For each reviewer profile, save a training example:
   ```bash
   python3 ~/.claude/skills/fando-plan/scripts/collect_training.py \
     --domain $PROFILE --other-domains "$OTHER_PROFILES" \
     --security-level $SECURITY_LEVEL \
     --plan-id "$PROJECT-$DATE" --iteration $ITER \
     --plan-before $PLAN_BEFORE_FILE \
     --plan-after $PLAN_AFTER_FILE \
     <<< "$REVIEW_OUTPUT_FOR_PROFILE"
   ```

#### 2.4 Final Systems Architect Review

After all specialists are satisfied (0 HIGH/MEDIUM findings):

1. **Run architect final pass:**
   ```bash
   python3 ~/.claude/skills/fando-plan/scripts/call_codex.py \
     "$(cat ~/.claude/skills/fando-plan/references/profiles/architect.md)" <<< "$PLAN"
   ```

2. **Architect reviews:**
   - Complete aggregated plan
   - Conflicts between specialist recommendations
   - Cross-cutting concerns
   - Overall coherence

3. **If conflicts detected, resolve them:**
   ```
   ⚠️  Conflict Detected:
   - Security: "Strict rate limit 10/min"
   - Performance: "Rate limit too aggressive for expected load"

   Architect Resolution: "Use 30/min with burst allowance of 50"
   ```

4. **Final LGTM or one more iteration**

### Phase 2 (Legacy): Single Reviewer Loop

**Note:** The legacy single-reviewer loop is still available for simpler plans or when specialist profiles aren't detected.

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

Detecting relevant reviewers...
Found: Security, Frontend, API

━━━ Parallel Review Loop ━━━

━━━ Iteration 1/5 ━━━
Running reviewers in parallel...
  Security Reviewer: reviewing...
  Frontend Architect: reviewing...
  API Designer: reviewing...

Findings:
  Security:
  - [HIGH] Missing CSRF protection on auth endpoints
  - [MEDIUM] JWT expiry too long (24h)

  Frontend:
  - [MEDIUM] No loading states defined

  API:
  - [MEDIUM] Missing rate limiting

Addressing 4 findings...
[Shows key plan changes]

━━━ Iteration 2/5 ━━━
Running reviewers in parallel...

Findings:
  Security:
  - [LOW] Consider refresh token rotation

  Frontend:
  - [LOW] Consider optimistic updates

  API:
  ✓ No issues

All HIGH/MEDIUM addressed. Proceeding to final review.

━━━ Systems Architect (Final Pass) ━━━
Reviewing complete plan...
Checking for conflicts...
No conflicts detected.

Remaining LOW findings (optional):
- [LOW] Security: refresh token rotation
- [LOW] Frontend: optimistic updates

✓ LGTM - Plan approved

━━━ Final Result ━━━
Plan approved after 2 specialist iterations + 1 architect pass.
Documentation saved to: ~/.claude/plan-reviews/my-project/2026-01-21-jwt-dashboard.md

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

## Reviewer Focus Strategy

Each specialist reviewer receives the **full plan** for context understanding, but is instructed to only flag issues in their specific domain. This approach:

- **Preserves reasoning**: Reviewers understand WHY decisions were made
- **Prevents duplicates**: Each specialist stays in their lane
- **Enables cross-domain awareness**: Reviewers can note dependencies without flagging other domains' choices

A focus preamble is automatically added to each reviewer prompt explaining their role in the multi-reviewer setup.

## Codebase Exploration Strategy

Before creating a plan, Claude should explore the codebase to understand existing architecture, patterns, and relevant code. Use the appropriate tool based on codebase size and query type.

### Decision Framework

```
┌─────────────────────────────────────────────────────────────┐
│  Is the codebase large (>1000 files)?                       │
│     ↓ Yes                              ↓ No                 │
│  ┌─────────────────────┐    ┌─────────────────────────────┐ │
│  │ Use Canopy          │    │ Use native tools            │ │
│  │ (token-efficient)   │    │ (Grep, Glob, Read)          │ │
│  └─────────────────────┘    └─────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Tool Selection Guide

| Query Type | Large Repo (>1000 files) | Small Repo (<500 files) |
|------------|--------------------------|-------------------------|
| "How does X work?" | `canopy_query` with pattern | Grep + Read |
| Find symbol definition | `canopy_query` with symbol | Grep for function/class |
| Cross-file tracing | `canopy_query` → `canopy_expand` | Grep + manual Read |
| Known file path | Read directly | Read directly |
| Literal text search | Grep | Grep |
| File name pattern | Glob | Glob |

### Using Canopy (Large Codebases)

**Step 1: Check if indexed**
```
mcp__canopy__canopy_status(path="/path/to/repo")
```

**Step 2: Query for relevant code**
```
# Symbol search (functions, classes)
mcp__canopy__canopy_query(path="/path/to/repo", symbol="AuthController")

# Pattern search (concepts, keywords)
mcp__canopy__canopy_query(path="/path/to/repo", pattern="authentication")

# Scoped search
mcp__canopy__canopy_query(path="/path/to/repo", pattern="login", glob="src/**/*.ts")
```

**Step 3: Expand relevant handles**
```
mcp__canopy__canopy_expand(path="/path/to/repo", handle_ids=["h1a2b3c4d5e6"])
```

### Benefits of Canopy for Planning

- **68% token reduction** through handle-based previews vs full file reads
- **2.3x more detailed** symbol discovery
- **Cross-file tracing** without reading entire files
- **Predictive indexing** - no blocking on first query

### When to Skip Canopy

- Codebase under 500 files (native tools are fast enough)
- Looking for literal text patterns (Grep is faster)
- Reading known file paths (Read directly)
- Simple file discovery (Glob is sufficient)

## DSPy Review Backend

The default review backend uses DSPy Signatures with per-domain docstrings encoding
reviewer expertise. This replaces the legacy markdown prompt approach with structured,
optimizable prompts.

### Backend Selection

```bash
# DSPy backend (default) — structured Signatures via CodexLM adapter
echo "$PLAN" | python3 run_parallel_reviews.py --backend=dspy security api

# Legacy codex backend — hand-crafted markdown prompts
echo "$PLAN" | python3 run_parallel_reviews.py --backend=codex security api

# DSPy without GEPA-optimized modules
echo "$PLAN" | python3 run_parallel_reviews.py --backend=dspy --no-optimized security api
```

If DSPy is not installed, the CLI falls back to the codex backend automatically.

### Architecture

```
detect_profiles → DSPy DomainReviewModule.forward()
                    → CodexLM adapter
                      → codex exec (subprocess)
                    → dspy.Prediction
                  → prediction_to_review_output()
                    → parse_findings() (unchanged)
```

Each domain has its own DSPy Signature class with a rich docstring derived from
`references/profiles/*.md`. The docstrings are the source of truth for reviewer
behavior; the markdown files are kept as human-readable documentation.

### GEPA Prompt Optimization

Training data is collected automatically during plan review sessions. Once you
have enough labeled examples (10+ per domain, 50+ recommended), you can optimize
reviewer prompts using GEPA.

```bash
# Check training data status
python3 optimize.py --stats

# Optimize a single domain
python3 optimize.py --domain security --reflection-model openai/gpt-4o --auto light

# Optimize all domains with sufficient data
python3 optimize.py --all --reflection-model openai/gpt-4o

# Export optimized instructions to markdown for inspection
python3 optimize.py --export
```

**Note:** GEPA requires an API key for the reflection model (one-time optimization
cost). Runtime inference uses Codex CLI — no API keys needed.

### Training Data & Optimized Modules

| Path | Purpose |
|------|---------|
| `~/.claude/skills/fando-plan/training_data/*.json` | Labeled training examples |
| `~/.claude/skills/fando-plan/optimized/{domain}.json` | GEPA-optimized module state |

## Files

| File | Purpose |
|------|---------|
| `scripts/call_codex.py` | Safe Codex invocation via stdin |
| `scripts/parse_findings.py` | Extract risk counts from response |
| `scripts/secrets.py` | Secret detection and redaction |
| `scripts/detect_profiles.py` | Analyze plan, return relevant reviewer profiles |
| `scripts/detect_security_level.py` | Detect security level from plan content |
| `scripts/run_parallel_reviews.py` | Orchestrate parallel Codex calls with focus prompts |
| `scripts/aggregate_findings.py` | Merge and dedupe findings from all reviewers |
| `scripts/dspy_reviewers.py` | DSPy Signatures, Modules, metrics, training data collection |
| `scripts/codex_lm.py` | CodexLM adapter — DSPy LM provider wrapping codex exec |
| `scripts/optimize.py` | GEPA optimization CLI for reviewer prompts |
| `scripts/backfill_training.py` | Backfill training data from existing plan review logs |
| `scripts/collect_training.py` | Collect training data during plan review iterations |
| `pyproject.toml` | Project dependencies (dspy optional) |
| `references/review_prompts.md` | Generic prompt templates (legacy reference) |
| `references/profiles/security.md` | Security reviewer prompt |
| `references/profiles/frontend.md` | Frontend architect prompt |
| `references/profiles/data.md` | Data architect prompt |
| `references/profiles/api.md` | API designer prompt |
| `references/profiles/devops.md` | DevOps engineer prompt |
| `references/profiles/performance.md` | Performance engineer prompt |
| `references/profiles/architect.md` | Final systems architect prompt |
| `examples/sample_session.md` | Example workflow |

### Project-level Files

| File | Purpose |
|------|---------|
| `.claude/settings.local.json` | Claude Code project settings (if needed) |
