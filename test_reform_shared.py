import io
from concurrent.futures import ThreadPoolExecutor

from openpyxl import load_workbook

from test_reform_workspace import setup, post, sample
from test_reform_approval_workflow import login
from test_reform_excel import upload_book
from webapp.reform_workspace import db, unpack, baseline, pack


def book(client):
    response = client.get('/reform/excel/download?scope=all')
    assert response.status_code == 200
    return load_workbook(io.BytesIO(response.data))


def shared(app):
    with app.app_context(), db() as conn:
        rows = conn.execute('SELECT * FROM drafts').fetchall()
        assert len(rows) == 1 and rows[0]['owner'] == 'paul'
        return unpack(rows[0]['payload']), rows[0]['revision']


def start(setup):
    app, coordinator = setup
    app.config['REFORM_APPROVALS_REQUIRED'] = 2
    post(coordinator, 'versions/save', number='v3.0', description='Shared version', revision='0')
    contributor = login(app, 'other', 'other-password')
    return app, coordinator, contributor


def test_every_user_uploads_to_same_draft_and_author_is_visible(setup):
    app, coordinator, contributor = start(setup)
    first, stale = book(contributor), book(coordinator)
    first['BOM']['C2'] = 3
    assert 'Excel changes saved' in upload_book(contributor, first).text
    work, revision = shared(app)
    assert revision == 1 and work['target']['boms']['1']['components'][0]['quantity'] == 3
    assert 'other' in coordinator.get('/reform/?view=review').text
    stale['BOM']['C2'] = 8
    assert 'Your draft has changed' in upload_book(coordinator, stale).text
    assert shared(app)[1] == 1
    fresh = book(coordinator)
    assert fresh['BOM']['C2'].value == 3
    assert post(coordinator, 'save', action='product', sku='CAB-01', name='Shared cabinet', revision='1').status_code == 200
    assert shared(app)[1] == 2
    with app.app_context(), db() as conn:
        assert baseline(conn) == sample()
        assert {r['actor'] for r in conn.execute("SELECT actor FROM reform_version_events WHERE status='edited'")} == {'paul', 'other'}


def test_other_user_edit_invalidates_both_approvals_then_locks_after_submit(setup):
    app, coordinator, contributor = start(setup)
    post(coordinator, 'save', action='product', sku='CAB-01', name='One', revision='0')
    assert '1 more Reform representative' in post(coordinator, 'submit', version='v3.0', revision='1', confirm='yes').text
    assert post(contributor, 'save', action='product', sku='CAB-01', name='Two', revision='1').status_code == 200
    with app.app_context(), db() as conn:
        assert conn.execute('SELECT count(*) FROM reform_version_approvals').fetchone()[0] == 0
    assert '1 more Reform representative' in post(contributor, 'submit', version='v3.0', revision='2', confirm='yes').text
    final = post(coordinator, 'submit', version='v3.0', revision='2', confirm='yes')
    assert 'submitted to Furnibox' in final.text
    with app.app_context(), db() as conn:
        payload = unpack(conn.execute('SELECT payload FROM submissions').fetchone()[0])
        assert payload['contributors'] == [{'kind': 'products', 'key': 'CAB-01', 'actor': 'other'}]
        assert set(payload['approved_by']) == {'paul', 'other'}
    for client in (coordinator, contributor):
        assert 'locked' in client.get('/reform/excel/download', follow_redirects=True).text
        assert post(client, 'save', action='product', sku='CAB-01', name='Blocked', revision='2').status_code == 409


def test_shared_file_can_be_uploaded_by_another_reform_account(setup):
    app, coordinator, contributor = start(setup)
    file = book(coordinator)
    file['BOM']['C2'] = 6
    assert 'Excel changes saved' in upload_book(contributor, file).text
    assert shared(app)[0]['target']['boms']['1']['components'][0]['quantity'] == 6
    assert post(contributor, 'discard', revision='1').status_code == 403
    assert shared(app)[1] == 1


def test_concurrent_uploads_accept_only_one_shared_revision(setup):
    app, coordinator, contributor = start(setup)
    first, second = book(coordinator), book(contributor)
    first['BOM']['C2'], second['BOM']['C2'] = 5, 9
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(upload_book, c, b) for c, b in [(coordinator, first), (contributor, second)]]
        pages = [f.result().text for f in futures]
    assert sum('Excel changes saved' in p for p in pages) == 1
    assert sum('Your draft has changed' in p for p in pages) == 1
    assert shared(app)[1] == 1


def test_file_cannot_cross_version_boundary_or_source_refresh(setup):
    app, coordinator, contributor = start(setup)
    file = book(contributor)
    with app.app_context(), db() as conn:
        conn.execute("UPDATE reform_versions SET number='v3.1'")
    assert 'another or older version' in upload_book(contributor, file).text
    fresh = book(contributor)
    with app.app_context(), db() as conn:
        source = baseline(conn)
        source['captured_at'] = '2026-10-30T12:00:00+00:00'
        conn.execute('UPDATE state SET payload=? WHERE id=1', (pack(source),))
    assert 'Source data has changed' in upload_book(coordinator, fresh).text

