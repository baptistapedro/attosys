---
name: change-risk-screening
description: Assess a repository change for attacker exposure and plausible security impact before deep analysis.
---

# Change risk screening

Use this method for a commit, pull request, release diff, or related change set.

1. Pin the base and head revisions and list every changed symbol and file.
2. Expand beyond the diff to callers, callees, configuration, tests, and trust-boundary code.
3. Identify attacker-controlled inputs, exposed entry points, privilege changes, dangerous operations, and security-sensitive state.
4. Describe the highest plausible impact and the exact code path that makes it plausible.
5. Distinguish evidence from uncertainty; keywords, contributor history, and change size never prove security relevance.
6. Produce a compact screening record containing revisions, affected surface, attacker input, suspected sink or invariant, impact rationale, and required deep-analysis scope.

Do not call the change vulnerable. If no attacker path or trust-boundary effect is supported, record why the change does not warrant priority analysis.
