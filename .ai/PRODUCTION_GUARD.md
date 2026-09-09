# Production Guard

## Default policy
Production Odoo is READ ONLY by default.

## Allowed without additional write authorization
- read/search/query operations;
- exports and reports that do not mutate Odoo data;
- comparing Odoo data with generated datasets/files;
- health/status checks;
- post-deploy verification that is read-only.

## Blocked by default
Do not perform any Production Odoo action that can create, update, delete, confirm, cancel, post, reserve, unreserve, import, activate, archive, or otherwise mutate business data or configuration.

This includes indirect writes through scripts, API calls, test helpers, browser automation, imports, server actions, or jobs.

## Exception rule
A Production write is allowed only when the current task contains explicit authorization for that exact class of write. Authorization from an older task or general project context is not sufficient for a materially different write.

When explicitly authorized:
1. define the exact records/actions in scope;
2. identify expected side effects;
3. prefer a dry-run or read-only preview when possible;
4. verify the target environment before execution;
5. perform the narrowest possible write;
6. verify the result immediately;
7. record what changed.

## Stop conditions
Stop before execution if:
- environment identity is uncertain;
- credentials/endpoint may point to Production unexpectedly;
- the script mixes reads and writes and write behavior is not fully understood;
- scope is broader than the explicit authorization;
- rollback/recovery is unclear for a high-impact change.

## BOM Release rule
Where `ACCEPTANCE_RULES.md` applies, Production activation is blocked unless all required Dataset and Odoo acceptance gates PASS exactly as defined there.
