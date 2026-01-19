# Sample Verification Session

This example shows a typical `/verify-implementation-codex` workflow.

## Scenario

User implemented a JWT authentication system based on a plan created with `/refine-plan-codex`.

## Session

```
User: /verify-implementation-codex

Claude: Looking for plan to verify against...
Found: ~/.claude/plan-reviews/my-api/2026-01-15-jwt-auth.md

Plan summary:
- JWT-based authentication with refresh tokens
- bcrypt password hashing (cost 12)
- Rate limiting (5 req/min on auth endpoints)
- Token blacklist via Redis for secure logout
- Login, logout, refresh, and password reset endpoints

Gathering implementation diff (comparing to main)...
Found 12 files changed, 487 additions, 23 deletions.

Changed files:
  src/models/User.ts
  src/routes/auth.ts
  src/middleware/authenticate.ts
  src/middleware/rateLimit.ts
  src/services/token.ts
  src/services/password.ts
  src/config/auth.ts
  tests/auth.test.ts
  ... (4 more)

This will send your plan and code diff to Codex for verification.
[Yes, proceed] [No, cancel]

User: Yes, proceed

Claude: Sending to Codex for verification...

## Verification Results

- [MATCH] User model with password hashing - Uses bcrypt with cost factor 12 as planned in src/services/password.ts
- [MATCH] Login endpoint - POST /auth/login implemented correctly in src/routes/auth.ts, returns JWT and refresh token
- [MATCH] Refresh token endpoint - POST /auth/refresh validates and rotates tokens as specified
- [MATCH] Authentication middleware - src/middleware/authenticate.ts correctly validates JWT and attaches user to request
- [IMPROVEMENT] Refresh tokens - Added token family tracking (familyId) to enable "logout all devices" feature. Not in original plan but significantly improves security posture
- [IMPROVEMENT] Password validation - Added zxcvbn strength checking beyond the basic requirements, rejects weak passwords
- [REGRESSION] Rate limiting - Configured at 10 requests/minute instead of planned 5/minute in src/middleware/rateLimit.ts
- [MISSING] Token blacklist - Redis integration for token blacklist not implemented. Currently tokens remain valid until expiry
- [MISSING] Password reset endpoint - POST /auth/reset-password not implemented
- [UNPLANNED] GET /auth/whoami endpoint - Returns current user profile, reasonable addition for frontend
- [UNPLANNED] Token expiry configuration - Added AUTH_TOKEN_EXPIRY env var, good for deployment flexibility

## Summary
4 matches, 2 improvements, 1 regression, 2 missing, 2 unplanned

## Attention Needed

1. **Rate limiting is looser than planned** (10/min vs 5/min)
   - Location: src/middleware/rateLimit.ts:15
   - Risk: Allows more aggressive credential stuffing attempts
   - Action: Change RATE_LIMIT_MAX from 10 to 5

2. **Token blacklist not implemented**
   - This was a key security feature in the plan
   - Without it, users cannot securely log out (tokens valid until expiry)
   - Compromised tokens cannot be revoked
   - Action: Implement Redis-based blacklist as planned

3. **Password reset not implemented**
   - POST /auth/reset-password endpoint missing
   - Users have no way to recover accounts
   - Action: Implement password reset flow with email verification

---

Verification saved to: ~/.claude/plan-reviews/my-api/2026-01-15-jwt-auth-verify.md

Would you like me to:
1. Address the regressions and missing items?
2. Update the plan to match the implementation (if deviations are intentional)?
3. Show the full verification report?
```

## Verification Report File

The saved verification report at `~/.claude/plan-reviews/my-api/2026-01-15-jwt-auth-verify.md`:

```markdown
# Verification: JWT Authentication

**Date**: 2026-01-15
**Plan**: 2026-01-15-jwt-auth.md
**Base**: abc1234 (merge-base with main)
**Head**: def5678

## Results

| Category | Count |
|----------|-------|
| Matches | 4 |
| Improvements | 2 |
| Regressions | 1 |
| Missing | 2 |
| Unplanned | 2 |

## Details

### Matches (4)
- User model with password hashing - bcrypt cost 12
- Login endpoint - JWT + refresh token response
- Refresh token endpoint - validation and rotation
- Authentication middleware - JWT validation

### Improvements (2)
- Refresh token family tracking for "logout all devices"
- Password strength validation with zxcvbn

### Regressions (1)
- Rate limiting: 10/min instead of 5/min

### Missing (2)
- Token blacklist (Redis)
- Password reset endpoint

### Unplanned (2)
- GET /auth/whoami endpoint
- AUTH_TOKEN_EXPIRY configuration

## Action Items

1. [ ] Fix rate limiting (10 → 5 req/min)
2. [ ] Implement token blacklist with Redis
3. [ ] Implement password reset endpoint
```
