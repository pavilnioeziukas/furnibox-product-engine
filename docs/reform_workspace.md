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

The Reform workspace interface is in English, including login, forms, validation messages and submission review.

## Reform catalogue scope

The catalogue reader selects one current active BOM per product: lowest sequence, then latest write_date, then highest ID for an exact tie. Archived alternatives are excluded. APACK codes and codes ending in -A (case-insensitive, whitespace trimmed) are hidden from Reform lists and component choices; FPACK remains visible. Server-side saves reject these internal products. Internal dependencies remain intact in stored data. A visible BOM containing hidden assembly components is read-only to avoid submitting a partial replacement. Refresh source data to apply the BOM selection to existing installations.

Verified locally: BAS001 search returns 12 products; EUB-C-CAB02-BAS001 shows only 20260415_Cabinet(F), sequence 0. The visible catalogue contains 4,657 products and 2,480 current BOMs.

## Excel exchange

`/reform/?view=files` supports download/edit/return. A product export includes its
current BOM and all editable descendant BOMs. An empty product selects a blank
new-product/BOM template. Existing row IDs are retained; REMOVE is explicit and
missing exported rows are rejected. New BOM keys use NEW-. Products supports name,
category and new product creation with category/unit lists from the visible
catalogue. Catalogue is reference-only. Prices and internal assembly products are
excluded. Existing SKU/unit changes and product retirement are not Excel actions.

The application uses its existing openpyxl dependency for runtime XLSX generation
and parsing. Export records store the account, source and draft server-side in
file_exports. Uploads validate ownership, source freshness and draft revision,
then validate all rows before saving the draft in one transaction. Formulas,
duplicate or forged IDs, unknown cards, invalid categories/units, non-positive
quantities, hidden assembly components and cycles are rejected. Files are capped
at 5 MB, 50 MB expanded ZIP content and 20,000 data rows per editable sheet.
No Odoo writes or external notifications occur. Submission uses the existing
explicit confirmation and immutable proposal workflow.

Validation: 52 local tests passed (two existing Linux process-group tests excluded
on Windows). Real BAS001 export: 14 cards, 3 BOMs, 13 component rows. An unchanged
return, quantity edit, comparison and submission were verified in an isolated
copy of the preview database. All six visible workbook sheets were rendered and
reviewed. Linux CI now includes test_reform_excel.py.

## Full catalogue export

Excel exchange offers a distinct `Download full catalogue` action (`/reform/excel/download?scope=all`). It exports all products and current BOMs in the Reform-visible snapshot, including component rows and products without BOMs. Existing APACK / -A filters remain in effect. Read-only records are identified in a separate reference sheet. Unchanged historical records and internal dependencies are preserved on return; edits to read-only BOMs are rejected. The source capture timestamp remains visible: downloading is an export of the workspace snapshot, not a new Odoo read.

Validated 2026-09-28: full snapshot roundtrip without changes, editable quantity changes and rejection of read-only BOM changes. 8 Excel exchange tests pass. Fresh Odoo read at 14:10 UTC confirms the displayed product and BOM data match the deployed snapshot.

## Catalogue release batches

Use `/reform/versions` to name the current draft (for example v11.1) and describe the release. The first number is intentionally not preselected. Product edits and Excel returns continue to update that draft. The My changes screen links to the version summary; only the summary submits the complete version.

One open version is allowed across the Reform workspace, with one editing owner. Other accounts cannot modify it. Submission records the version number, description, original baseline and draft revision, retains an immutable submission, and locks further changes until Furnibox review. An administrator can accept or return the version with a correction note. Returning restores the same owner's draft with a higher revision and retains previous submission payloads. The version number stays unchanged on resubmission. Stale review forms are rejected by submission ID. Version history records each transition.

Implemented requires an administrator's verification reference, an explicit confirmation, and a refreshed source whose product/BOM values match every proposed change. No operation here writes to Odoo. A later version must have a higher numeric major/minor number; minor releases remain a human business choice.

Notification records are created only for complete version submissions in the same SQLite transaction. Email is disabled unless REFORM_EMAIL_ENABLED=true. Do not enable until the user approves the version email template and automatic dispatch and the mailbox administrator configures sending access. Recipient is edgaras@furnix.lt; intended sender is info@furnibox.lt. Microsoft Graph configuration uses REFORM_EMAIL_PROVIDER=microsoft, REFORM_EMAIL_FROM, REFORM_MS_TENANT_ID, REFORM_MS_CLIENT_ID, REFORM_MS_CLIENT_SECRET and REFORM_PUBLIC_URL. Scope the mail application to the approved sender mailbox. Secrets belong in Railway variables, never Git. No production sending credentials have been configured.

A provider failure preserves the submission and records failure. Ambiguous failures are not automatically retried to avoid duplicate messages. Pending/failed notifications currently require administrator follow-up; old pending items are not dispatched automatically when enabling email.
