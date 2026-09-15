---
name: attack-surface-analysis
description: Map attacker-controlled entry points, trust boundaries, privileged effects, and unexplored security paths in source code.
---

# Attack-surface analysis

1. Pin the repository revision and enumerate externally reachable entry points.
2. For each entry point, identify attacker-controlled fields, parsers, validators, authentication checks, authorization checks, and state transitions.
3. Trace paths to memory-unsafe operations, interpreters, command execution, filesystem access, sensitive data, cryptographic decisions, and privileged actions.
4. Record process, sandbox, namespace, thread, ownership, and privilege boundaries crossed by each path.
5. Mark each surface as reviewed, partially reviewed, or unexplored at the pinned revision, with source references supporting that state.
6. Split broad surfaces into bounded hypotheses that can reach a supported conclusion.

Generated files, tests, and documentation may reveal entry points but are not proof
of runtime reachability. Validate every mapped path against production code.
