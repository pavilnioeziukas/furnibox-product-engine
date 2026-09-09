# Furnibox Product Engine — AI Project Context

## Purpose
This repository supports Furnibox product/BOM/pricing workflows and related web tooling around Odoo data.

## Runtime
- Python 3.12 container.
- Web process starts with `deploy/start-web.sh` and serves `webapp.app:app` through Gunicorn.
- Railway is the current hosting/deployment platform; exact deployment trigger and target must be verified per task rather than assumed.

## Existing domain gates
`ACCEPTANCE_RULES.md` is authoritative for BOM Release acceptance. Do not duplicate or weaken those rules here.

## Default operating model
Every change follows:

REQUEST → UNDERSTAND → PLAN → IMPLEMENT → VERIFY → ADVERSARIAL REVIEW → PRODUCTION GUARD → RELEASE → PRODUCTION VERIFY → DONE

## Definition of success
A change is not DONE because code was written, committed, merged, or tests passed. DONE means the task-specific acceptance criteria have been verified in the intended environment and the result is recorded with evidence.
