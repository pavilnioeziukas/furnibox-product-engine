# AI Development Workflow v1

## 1. REQUEST
Capture the requested business outcome and source of truth.

## 2. UNDERSTAND
Before editing code, state:
- problem to solve;
- acceptance criteria;
- scope;
- non-goals;
- affected business rules;
- unknowns that materially affect correctness.

Do not implement while acceptance criteria are ambiguous.

## 3. PLAN
Identify:
- files/components likely to change;
- data sources involved;
- relevant existing tests and validation scripts;
- Production/Odoo write risk;
- rollback path if applicable.

## 4. IMPLEMENT
- Work on a dedicated branch unless explicitly instructed otherwise.
- Make the smallest coherent change.
- Do not mix unrelated cleanup or refactoring into the task.

## 5. VERIFY
Run the relevant checks available in the repository. At minimum:
- task-specific tests/checks;
- existing acceptance scripts when the change affects their domain;
- syntax/startup checks where relevant;
- final git diff review against scope.

For BOM Release work, `ACCEPTANCE_RULES.md` gates remain mandatory when applicable.

## 6. ADVERSARIAL REVIEW
Review the completed change as if trying to reject it. Ask:
- What assumption could be wrong?
- What valid input could break this?
- Could this change unrelated pricing/BOM behavior?
- Could it write to Production Odoo unexpectedly?
- Could old or incomplete data produce a false PASS?
- Does the implementation satisfy the business outcome, not merely the test?

Resolve findings or record them as explicit release blockers/known risks.

## 7. PRODUCTION GUARD
Apply `.ai/PRODUCTION_GUARD.md` before any action touching Production systems.

## 8. RELEASE
Before release:
- tests/checks are green or exceptions are explicitly accepted;
- diff is reviewed;
- scope matches acceptance criteria;
- no secrets are included;
- Production guard passes.

Then use the repository's actual GitHub/Railway release process. Verify the current target/trigger instead of assuming it.

## 9. PRODUCTION VERIFY
After deploy, verify the acceptance criteria in Production using read-only checks unless explicit write authorization exists.

Record:
- deployed commit/PR;
- deployment status;
- health/startup result;
- concrete business-function check(s);
- discrepancies.

## 10. DONE
DONE requires all of the following:
- requested scope implemented;
- verification completed;
- adversarial review completed;
- Production guard passed;
- intended deployment completed;
- Production acceptance criteria verified.

If any required Production check is unavailable, status is `NOT VERIFIED`, not `DONE`.
