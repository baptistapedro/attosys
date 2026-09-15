---
name: patch-diff-variant-analysis
description: Derive sibling-vulnerability searches from a project CVE's root cause and fix without treating unrelated bugs as variants.
---

# Patch-diff variant analysis

Use this method only after an active CVE work item has already been proven to affect
the configured repository.

1. Compare vulnerable and fixed revisions in full context and reconstruct the original attacker path and impact.
2. Express the violated security invariant and the semantic condition enforced by the fix.
3. Derive searches for copied code, equivalent dangerous operations, alternate entry points, missing checks, partial backports, incomplete fixes, and patch bypasses.
4. Inspect each match in its complete control-flow and data-flow context at the current target revision.
5. For every candidate, record a direct derivation from the source CVE: CVE ID, shared root cause or invariant, derived search, matching code, and divergent trigger path.
6. Compare the candidate's repository, source location, attacker path, and root cause with active and completed work and prior candidate records.

An incidental vulnerability with no direct CVE-derived search path is outside this method. A candidate matching existing researcher work is a duplicate. Record either
disposition, but do not treat it as a new variant finding.
