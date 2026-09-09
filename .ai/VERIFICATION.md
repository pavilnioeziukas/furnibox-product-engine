# Verification Standard

Use this checklist for every task. Mark each item PASS, FAIL, N/A, or NOT VERIFIED.

## Scope
- Acceptance criteria are explicit.
- Implemented diff matches the requested scope.
- No unrelated business rules changed.

## Automated verification
- Relevant tests/checks were identified.
- Relevant tests/checks passed.
- Existing domain acceptance scripts were run when applicable.

## Diff review
- Final diff reviewed line by line.
- Secrets/credentials absent.
- No unintended data-write path introduced.
- Error handling and edge cases reviewed.

## Adversarial review
Document at least one plausible failure mode considered and the result of checking it.

## Release verification
For Production-bound work:
- exact commit/PR identified;
- deployment target verified;
- deployment completed successfully;
- application health/startup checked;
- task-specific Production acceptance criteria checked using read-only methods unless explicit write authorization exists.

## Status rule
Use only:
- `DONE` — all required checks, including Production verification when applicable, passed;
- `NOT VERIFIED` — implementation/release may be complete but a required verification could not be performed;
- `BLOCKED` — a known issue prevents safe completion;
- `FAILED` — acceptance criteria or required verification failed.

Never convert `NOT VERIFIED` into `DONE` based on inference, expected behavior, a successful merge, or a green deployment alone.

## Completion evidence template

```text
Acceptance criteria: PASS/FAIL
Tests/checks: <commands/checks + result>
Diff review: PASS/FAIL
Adversarial review: <failure mode checked + result>
Production guard: PASS/FAIL/N/A
Released commit/PR: <identifier>
Deployment: PASS/FAIL/NOT VERIFIED
Production verification: PASS/FAIL/NOT VERIFIED
Final status: DONE / NOT VERIFIED / BLOCKED / FAILED
```
