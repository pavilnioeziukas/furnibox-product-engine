# Reform product and BOM pilot

The Product Engine menu now links to `/reform/`. Reform users log in at
`/reform/login` with individual usernames and password hashes configured by the
administrator. A Reform session cannot access internal Product Engine pages,
pricing endpoints, job actions or internal downloads.

## Supported scenarios

- Create a product (unique SKU, name, existing unit of measure).
- Change a product name while keeping its existing SKU and unit stable.
- Create a BOM for an existing or newly drafted product.
- Edit a BOM's reference, output quantity, components and component quantities.
- Remove a component from a BOM without retiring the component product.
- Propose retiring a product; reject confirmation if it is still referenced.
- Review before/after data, confirm and submit an immutable change package.
- Furnibox can view all submitted packages and download a structured JSON proposal.

Prices are neither requested from Odoo nor editable in this workspace. Existing
BOM/line IDs, quantities, units and BOM type are preserved. Proposals are not Odoo
import files: downstream processing must apply explicit deltas, retain fields
outside this editor (operations, byproducts, routing, etc.), and revalidate live
Odoo before applying changes. There is no Odoo write or automatic email here.

## Setup

1. Keep the existing internal web password enabled. Set a stable
   `PRODUCT_ENGINE_WEB_SECRET` (or its existing legacy equivalent).
2. Set `PRODUCT_ENGINE_REFORM_USERS` to a JSON mapping of lowercase usernames to
   Werkzeug password hashes. Generate hashes with `generate_password_hash` from
   `werkzeug.security`; do not store plaintext passwords in this variable or Git.
   An empty mapping disables Reform logins. Removing a username revokes its session.
3. Log in through the existing Furnibox login and open **Reform · Produktai ir BOM**.
4. Expand **Pateikti aktualius Odoo duomenis**, enter explicitly selected Reform
   root SKUs and refresh. This reads Odoo products, active BOMs and their component
   closure. It does not mutate Odoo. All roots/components must have unique SKUs.
5. Give each approved Reform user their individual login through your existing
   secure credential-sharing process. No public signup is exposed.

Persistent data lives in `STATE_DIR/reform/reform.sqlite3`; keep this directory on
the existing persistent volume and include it in backups. SQLite transactions and
revision checks prevent overwritten drafts from stale tabs. Every draft records
its baseline; refreshing source data blocks submission from an older baseline.
Download the draft before discarding it if the baseline changes.

## Pilot boundaries

- Start with a small, curated set. The current editor renders this set in one page.
- Shared multi-variant BOMs and component applicability conditions are rejected
  instead of being flattened. They require a richer editor.
- Product metadata editing initially covers name only. SKU/unit migration is not
  exposed; new products use units already present in the curated catalogue.
- Component usage outside the curated set is recorded as a blocking count, without
  exposing unrelated product names to Reform users.
- Overlapping proposals from the same baseline are blocked pending Furnibox review.
- Submission status is **awaiting Furnibox**; this pilot does not mark imports
  complete or apply packages. The existing implementation/import workflow remains
  a Furnibox operation. Refresh from Odoo after the changes have been implemented.
- Freshness means the timestamped imported snapshot, not a continuously live feed.
- The local demo uses synthetic data and local-only credentials, never production
  passwords. No demo account or fixture data is enabled in deployment.

## Three-minute demo

1. Log in as a Reform user and find an existing product.
2. Change a BOM component quantity and remove another component; save the draft.
3. Review both versions, confirm and open the submitted package.

## Validation

`python -m pytest -q test_reform_workspace.py test_webapp.py`

Run the full suite on Linux. Two pre-existing job process-group tests depend on
`os.killpg`, which is not available on Windows. The Reform tests cover access
boundaries, CSRF, persistence, immutable submissions, user isolation, stale tabs
and snapshots, quantities, cycles, retirement usage and read-only Odoo scope.
