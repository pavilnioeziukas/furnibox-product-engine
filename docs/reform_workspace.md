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
4. Expand **Atnaujinti sąrašą iš Odoo** and refresh with the SKU field empty to read
   the entire active production product catalogue, its active BOMs and referenced
   components. Optional root SKUs restrict the catalogue. It does not mutate Odoo.
   Missing/duplicate SKUs and variant-specific BOMs remain visible but locked.
5. Give each approved Reform user their individual login through your existing
   secure credential-sharing process. No public signup is exposed.

Persistent data lives in `STATE_DIR/reform/reform.sqlite3`; keep this directory on
the existing persistent volume and include it in backups. SQLite transactions and
revision checks prevent overwritten drafts from stale tabs. Every draft records
its baseline; refreshing source data blocks submission from an older baseline.
Download the draft before discarding it if the baseline changes. New payloads are
compressed to keep full catalogue drafts and submissions reasonably small; old
uncompressed records remain readable.

## Pilot boundaries

- The starting screen offers four explicit tasks: browse products and BOMs, edit
  a specific existing BOM, create a product, or create a BOM. Product and BOM lists
  have server-side search and 30 records per page. The BOM editor opens exactly
  the selected BOM; saving takes the user directly to the before/after review.
- Shared multi-variant BOMs and component applicability conditions remain visible
  read-only instead of blocking the full catalogue import. They require a richer editor.
- Product metadata editing initially covers name only. SKU/unit migration is not
  exposed; new products use units already present in the curated catalogue.
- Component usage outside the curated set is recorded as a blocking count, without
  exposing unrelated product names to Reform users.
- Overlapping proposals from the same baseline are blocked pending Furnibox review.
- Submission status is **awaiting Furnibox**; this pilot does not mark imports
  complete or apply packages. The existing implementation/import workflow remains
  a Furnibox operation. Refresh from Odoo after the changes have been implemented.
- Freshness means the timestamped imported snapshot, not a continuously live feed.
- The local pilot can use a freshly read production snapshot. Its test credentials
  are local-only; no demo account, production snapshot or credentials are committed.
- Confirmation checks the edited BOM subtrees and retirement dependencies. Existing
  invalid BOMs elsewhere in the catalogue do not block an unrelated correction.

## Three-minute demo

1. Log in as a Reform user and choose **Pakeisti konkretų BOM**.
2. Find a BOM by product or reference, then select **Keisti šį BOM**.
3. Change a component quantity or remove a component, then save and review.
4. Compare both versions, confirm and open the submitted package.

The separate browse task presents the production products and their BOMs. The
new product and new BOM tasks open dedicated creation forms.

## Validation

`python -m pytest -q test_reform_workspace.py test_webapp.py`

Run the full suite on Linux. Two pre-existing job process-group tests depend on
`os.killpg`, which is not available on Windows. The Reform tests cover access
boundaries, CSRF, persistence, immutable submissions, user isolation, stale tabs
and snapshots, quantities, cycles, retirement usage and read-only Odoo scope.

## Full-catalogue verification on 2026-09-28

Read-only production snapshot: 6,594 products (active products plus referenced
components), 10,967 active BOMs belonging to 4,319 products. The snapshot also
revealed pre-existing inactive-component references; these are not silently fixed.
On the local machine the first catalogue page rendered in about 0.52 seconds and
returned 13.5 KB of HTML. An existing APACK BOM quantity change was saved, reviewed
and confirmed in an isolated local test database, with the baseline unchanged.
The resulting full-catalogue proposal occupied about 535 KB of compressed storage.
42 local tests passed; two pre-existing Linux process-group tests were excluded
on Windows. Live Odoo was only read, never modified.
