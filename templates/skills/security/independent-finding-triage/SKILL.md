---
name: independent-finding-triage
description: Independently reproduce a submitted finding and classify it as confirmed, intended, known, duplicate, fixed, or unsupported.
---

# Independent finding triage

1. Check out the exact reported revision and reconstruct the documented build and runtime environment.
2. Run the submitted PoC as provided and verify that the observed result demonstrates the claimed impact.
3. Independently trace the root cause, attacker-controlled path, privileges, prerequisites, affected versions, and mitigations from source.
4. Review relevant commits, pull requests, reviews, issues, release notes, documentation, source comments, author explanations, and NatSpec where applicable.
5. Determine whether the behavior is intended, already known, duplicated, already fixed, or invalidated by an unmet prerequisite.
6. Preserve source references and reproduction evidence for every part of the classification.

Do not create, repair, or extend the submitted PoC. If it cannot independently demonstrate its claim, classify the finding as unsupported and identify the missing
evidence for the originating researcher.
