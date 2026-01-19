# Verification Prompts

## Main Verification Prompt

You are verifying an implementation against its plan.

Compare each item in the plan against the actual implementation (git diff).

For each planned item, categorize it:
- **[MATCH]** - Implemented exactly as planned
- **[IMPROVEMENT]** - Implemented differently, but the deviation is *better* (more robust, more secure, cleaner, better error handling)
- **[REGRESSION]** - Implemented differently, and the deviation is *worse* (missing functionality, less secure, harder to maintain, incomplete)
- **[MISSING]** - Planned but not implemented at all

Also note any:
- **[UNPLANNED]** - Implemented but not mentioned in the plan (may be supporting code, necessary infrastructure, or scope creep)

## Response Format

Format your response as:

```
## Verification Results

- [MATCH] <item description> - <brief explanation of how it matches>
- [IMPROVEMENT] <item description> - <what was different and why it's better>
- [REGRESSION] <item description> - <what was different and why it's worse>
- [MISSING] <item description> - <what was expected but not found>
- [UNPLANNED] <item description> - <what was added and whether it's necessary>

## Summary
X matches, Y improvements, Z regressions, W missing, V unplanned.

## Assessment
- If there are regressions or missing items: List which ones need attention and why
- If all matches/improvements: "Implementation looks good!"
```

## Guidelines

1. **Be specific**: Reference actual code, function names, file paths where relevant
2. **Explain deviations**: For improvements and regressions, explain *why* the change is better or worse
3. **Consider context**: Unplanned items may be necessary (error handling, types, utilities) - note if they're reasonable additions
4. **Focus on substance**: Minor style differences are not regressions
5. **Security matters**: Missing security features from the plan are always regressions

## Example Output

```
## Verification Results

- [MATCH] User model with password hashing - Uses bcrypt with cost factor 12 as planned
- [MATCH] Login endpoint returns JWT - POST /auth/login returns { token, refreshToken } as specified
- [IMPROVEMENT] Refresh tokens - Added token family ID to enable "logout from all devices" feature, not in plan but valuable security enhancement
- [REGRESSION] Rate limiting - Implemented at 10 requests/minute instead of planned 5/minute, could allow more aggressive attacks
- [MISSING] Token blacklist - Plan called for Redis-based token blacklist for secure logout, not implemented
- [UNPLANNED] /whoami endpoint - Returns current user info, reasonable addition for frontend needs

## Summary
2 matches, 1 improvement, 1 regression, 1 missing, 1 unplanned.

## Assessment
Attention needed:
- Rate limiting is looser than planned (10/min vs 5/min) - consider tightening
- Token blacklist not implemented - this is required for secure logout functionality; users cannot invalidate tokens
```
