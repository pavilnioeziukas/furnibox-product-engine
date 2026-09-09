# AI Development Rules

1. Start from the user's requested business outcome, not from a guessed implementation.
2. Before code changes, write explicit acceptance criteria, scope, and non-goals.
3. Prefer the smallest change that satisfies the acceptance criteria.
4. Do not silently change adjacent business rules, pricing rules, BOM logic, data mappings, or deployment behavior.
5. Reuse existing project mechanisms and documentation instead of creating parallel processes.
6. `ACCEPTANCE_RULES.md` remains authoritative for BOM Release validation.
7. Run relevant automated tests and inspect the final git diff before release.
8. Perform an adversarial review after implementation: actively look for regressions, edge cases, incorrect assumptions, unsafe writes, and mismatches with the requested business outcome.
9. Production Odoo is READ ONLY by default. Any write-capable action requires explicit task-level authorization and must be narrowly scoped.
10. Do not expose secrets, credentials, tokens, or `.env` contents in logs, commits, PRs, or reports.
11. Do not mark a task DONE until Production verification is completed when the task is intended for Production.
12. If Production verification cannot be performed, report the task as NOT VERIFIED rather than DONE.
13. Deployment must follow the repository's actual current Railway/GitHub process; never invent or assume a trigger.
14. Record evidence for completion: tests executed, diff reviewed, deployment result, and concrete Production checks.
