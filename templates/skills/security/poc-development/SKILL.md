---
name: poc-development
description: Build a minimal, reproducible Proof of Concept that demonstrates a supported exploit path and security impact.
---

# PoC development

1. Use an isolated environment and pin the target source revision and all relevant dependencies.
2. Exercise the real attacker-controlled entry point with the fewest components needed to preserve the exploit path.
3. Demonstrate the claimed security effect, not merely a warning, error, crash, or undefined behavior.
4. Remove unrelated setup and nondeterminism while retaining realistic prerequisites and mitigations.
5. Record exact build and run commands, expected result, observed result, and attributed execution evidence.
6. Reproduce from a clean state before considering the PoC complete.

Do not probe live or third-party systems. This skill governs PoC construction and reproduction evidence; it does not define the finding report format or handoff.
