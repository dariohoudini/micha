<!-- CI/CD & VC doc CH7 — small, focused PRs get real review; large PRs get rubber-stamped. -->

## What & why
<!-- One logical change. What does this PR do, and why? -->

## Linked ticket
<!-- e.g. MICHA-123 — traceability commit → PR → ticket (CH6/CH7). -->
Refs:

## How to test
<!-- Steps a reviewer follows to verify. Note the commands / endpoints. -->

## Risk & rollback
<!-- Blast radius if this goes wrong. Is it behind a feature flag? How is it reverted? -->

---

### Reviewer checklist (CH7)
- [ ] **Correctness** — does what it claims; edge cases handled
- [ ] **Tests** — adequate coverage; for any endpoint change, the access-control matrix (anonymous→401, wrong-role→403, missing-perm→403, not-owner→404/IDOR, KYC/step-up gates) per IAM doc CH29
- [ ] **Security** — input validation, authz checks, no secrets committed, no IDOR/injection
- [ ] **Money correctness** — integer cents, idempotency, ledger invariants for any financial change
- [ ] **Migration safety** — backwards-compatible / expand-contract; no destructive change in one deploy; safe defaults; reviewed down path
- [ ] **Performance** — no N+1 queries, missing indexes, or unbounded result sets
- [ ] **Conventions** — Conventional Commit title (`type(scope): subject`); readable & maintainable

> Merge requires: green CI · ≥1 approval (≥2 + CODEOWNERS for payments / identity / migrations) · branch up to date · conversations resolved.
