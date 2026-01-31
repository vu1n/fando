# Fando

Claude and Codex - the odd couple of AI-assisted development.

Like Felix and Oscar from *The Odd Couple*, these two AI systems have different strengths and work better together:

- **Claude** (the orchestrator) - handles planning, user interaction, code generation, and workflow management
- **Codex** (the reviewer) - provides external review, catches blind spots, and validates implementations

Fando is a collection of Claude Code skills that leverage this collaboration.

## Skills

### `/fando-plan`

Iteratively refines implementation plans using Codex as a reviewer. Uses **autonomous iteration** ([Ralph-style](https://ghuntley.com/ralph/)) - once you consent, Claude loops automatically until the plan is approved.

**Workflow:**
1. Claude creates initial plan for your task
2. Codex reviews and flags issues (HIGH/MEDIUM/LOW risk)
3. Claude addresses feedback and resubmits
4. **Loop automatically** until LGTM or max iterations (no user input needed between iterations)

**Features:**
- Autonomous iteration - no babysitting required
- Risk classification (HIGH/MEDIUM/LOW)
- Parallel specialist reviewers (Security, Frontend, API, Data, DevOps, Performance)
- Focused prompts - reviewers get full context but stay in their lane
- Canopy integration for token-efficient codebase exploration (large repos)
- Secret detection and redaction before sending to external API
- Plan history saved to `~/.claude/plan-reviews/`

### `/fando-verify`

**Single-pass diagnostic** that verifies your implementation against its plan. Codex compares what you built to what you planned and categorizes each item.

**Categories:**

| Category | Description |
|----------|-------------|
| **MATCH** | Implemented exactly as planned |
| **IMPROVEMENT** | Deviation that's better than planned |
| **REGRESSION** | Deviation that's worse than planned |
| **MISSING** | Planned but not implemented |
| **UNPLANNED** | Implemented but not in plan |

**After verification, you decide:**
- Regressions/missing items? → Fix them, re-verify
- Major scope change needed? → Run `/fando-plan` again
- All good? → Ship it

**Features:**
- Auto-detects plans from `~/.claude/plan-reviews/`
- Gathers implementation diff via git
- Highlights items needing attention
- Saves verification reports

## Installation

Clone to your Claude Code skills directory:

```bash
git clone https://github.com/vu1n/fando.git ~/.claude/skills
```

Or add to an existing skills directory:

```bash
cd ~/.claude/skills
git remote add origin https://github.com/vu1n/fando.git
git pull origin main
```

## Requirements

- Python 3.10+
- [OpenAI Codex CLI](https://github.com/openai/codex) installed and configured
- Git (for implementation verification)

### Optional (Recommended for Large Codebases)

- [Canopy v0.1.0](https://github.com/vu1n/canopy/releases/tag/v0.1.0) - Token-efficient codebase indexing for repos >1000 files. Enables 68% token reduction through handle-based exploration vs full file reads.

## Usage

### Plan a Feature

```
/fando-plan Add JWT authentication with refresh tokens
```

Claude creates a plan, Codex reviews it, and they iterate until the plan is solid.

### Verify Your Implementation

After implementing, verify it matches the plan:

```
/fando-verify
```

Or with explicit plan path:

```
/fando-verify --path=~/.claude/plan-reviews/my-project/2026-01-19-auth.md
```

## Typical Workflow

```
┌─────────────────────────────────────────────────────────────┐
│  /fando-plan Add user authentication                        │
│      ↓                                                      │
│  [Autonomous loop - no user input needed]                   │
│      Claude creates plan → Codex reviews → Claude refines   │
│      ↓                                                      │
│  Plan approved & saved to ~/.claude/plan-reviews/           │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Implement the feature (with Claude's help)                 │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  /fando-verify                                              │
│      ↓                                                      │
│  [Single pass - diagnostic checkpoint]                      │
│      Codex compares implementation to plan                  │
│      ↓                                                      │
│  Results: matches, improvements, regressions, missing       │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  You decide:                                                │
│    • Regressions/missing? → Fix & re-verify                 │
│    • Major change needed? → /fando-plan again               │
│    • All good? → Ship it                                    │
└─────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
~/.claude/skills/
├── fando-plan/
│   ├── SKILL.md
│   ├── scripts/
│   │   ├── call_codex.py           # Codex CLI wrapper
│   │   ├── parse_findings.py       # Parse review response
│   │   ├── secrets.py              # Secret detection
│   │   └── run_parallel_reviews.py # Parallel reviewer orchestration
│   ├── references/
│   └── examples/
├── fando-verify/
│   ├── SKILL.md
│   ├── scripts/
│   │   ├── find_plan.py           # Auto-detect plans
│   │   ├── gather_implementation.py  # Git diff collector
│   │   └── parse_verification.py  # Parse verification
│   ├── references/
│   └── examples/
└── README.md
```

## Why "Fando"?

**F**elix **and** **O**scar - the characters from *The Odd Couple*. Claude and Codex are different AI systems with different approaches, but they complement each other well. One plans and builds, the other reviews and validates.

## License

MIT
