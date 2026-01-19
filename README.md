# Fando

**F**elix **and** **O**scar - a pair of complementary Claude Code skills for plan refinement and implementation verification.

Like the odd couple, these skills work together: one creates refined plans, the other verifies implementations match those plans.

## Skills

### `/refine-plan-codex`

Iteratively refines implementation plans using OpenAI Codex as a reviewer. Creates a plan, sends it for review, and iterates until approved.

**Features:**
- Automated plan review with risk classification (HIGH/MEDIUM/LOW)
- Secret detection and redaction before sending to external API
- Iteration tracking with configurable limits
- Plan history saved to `~/.claude/plan-reviews/`

### `/verify-implementation-codex`

Verifies an implementation against its plan, categorizing each item as:

| Category | Description |
|----------|-------------|
| **MATCH** | Implemented exactly as planned |
| **IMPROVEMENT** | Deviation that's better than planned |
| **REGRESSION** | Deviation that's worse than planned |
| **MISSING** | Planned but not implemented |
| **UNPLANNED** | Implemented but not in plan |

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

Or if you already have a skills directory:

```bash
cd ~/.claude/skills
git remote add origin https://github.com/vu1n/fando.git
```

## Requirements

- Python 3.10+
- [OpenAI Codex CLI](https://github.com/openai/codex) installed and configured
- Git (for implementation verification)

## Usage

### Refine a Plan

```
/refine-plan-codex Add JWT authentication with refresh tokens
```

### Verify Implementation

```
/verify-implementation-codex
```

Or with explicit plan path:

```
/verify-implementation-codex --path=~/.claude/plan-reviews/my-project/2026-01-19-auth.md
```

## Shared Components

Both skills share common utilities in `refine-plan-codex/scripts/`:

- `call_codex.py` - Safe Codex CLI invocation via stdin
- `secrets.py` - Secret detection and redaction

## License

MIT
