"""Authenticated two-person approval workflow against isolated SQLite state."""
import copy
import io
import re
from concurrent.futures import ThreadPoolExecutor

import pytest
from openpyxl import load_workbook
from test_reform_workspace import setup, post, sample
from webapp.reform_workspace import db, baseline, unpack
from webapp.reform_versions import schema


def login(app, username, password):
    client = app.test_client()
    client.get('/reform/login')
    with client.session_transaction() as session:
        csrf = session['reform_csrf']
    assert client.post('/reform/login', data={'csrf': csrf, 'username': username,
                                             'password': password}).status_code == 302
    return client


def fingerprint(client):
    match = re.search(r'name="package_digest" value="([^"]+)"', client.get('/reform/versions').text)
    assert match
    return match.group(1)


@pytest.fixture
def pair(setup, monkeypatch):
    monkeypatch.delenv('REFORM_EMAIL_ENABLED', raising=False)
    app, author = setup
    app.config['REFORM_APPROVALS_REQUIRED'] = 2
    reviewer = login(app, 'other', 'other-password')
    assert post(author, 'versions/save', number='v2.0', description='BOM pilot', revision='0').status_code == 200
    assert post(author, 'save', action='bom', bom_id='1', quantity='1',
                code=sample()['boms']['1']['code'],
                component_sku=['PANEL-01', 'HINGE-01'], component_quantity=['3', '4'],
                component_id=['10', '11'], revision='0').status_code == 200
    return app, author, reviewer


def approve(client, revision='1', **extra):
    return post(client, 'submit', version='v2.0', revision=revision, confirm='yes', **extra)


def snapshot(app):
    with app.app_context(), db() as conn:
        return {
            'approvals': conn.execute('SELECT count(*) FROM reform_version_approvals').fetchone()[0],
            'submissions': conn.execute('SELECT count(*) FROM submissions').fetchone()[0],
            'status': conn.execute("SELECT status FROM reform_versions WHERE number='v2.0'").fetchone()[0],
            'source': baseline(conn),
        }


def test_approval_workflow_two_logins_one_immutable_submission(pair):
    app, author, reviewer = pair
    assert '3' in reviewer.get('/reform/versions').text
    assert '1 more Reform representative' in approve(author).text
    assert snapshot(app)['submissions'] == 0
    assert 'Already approved' in author.get('/reform/versions').text
    assert '1 more Reform representative' in approve(author).text
    assert snapshot(app)['approvals'] == 1
    assert 'submitted to Furnibox' in approve(reviewer).text
    result = snapshot(app)
    assert result['submissions'] == 1 and result['status'] == 'submitted'
    assert result['source'] == sample()
    with app.app_context(), db() as conn:
        payload = unpack(conn.execute('SELECT payload FROM submissions').fetchone()[0])
        original = copy.deepcopy(payload)
        assert set(payload['approved_by']) == {'paul', 'other'}
        assert payload['approval_digest']
        assert payload['target']['boms']['1']['components'][0]['quantity'] == 3
        assert conn.execute('SELECT count(*) FROM notification_outbox').fetchone()[0] == 1
    approve(reviewer)
    assert snapshot(app)['submissions'] == 1
    assert post(author, 'save', action='product', sku='CAB-01', name='Locked', revision='0').status_code == 409
    with app.app_context(), db() as conn:
        assert unpack(conn.execute('SELECT payload FROM submissions').fetchone()[0]) == original


@pytest.mark.parametrize('change', ['product', 'description', 'discard', 'excel'])
def test_approval_workflow_edits_reset_approvals_and_reject_old_page(pair, change):
    app, author, reviewer = pair
    old_digest = fingerprint(reviewer)
    approve(author)
    revision = '2'
    if change == 'product':
        post(author, 'save', action='product', sku='CAB-01', name='Changed', revision='1')
    elif change == 'description':
        post(author, 'versions/save', number='v2.0', description='New explanation', revision='1')
        revision = '1'
    elif change == 'discard':
        post(author, 'discard', revision='1')
        post(author, 'save', action='product', sku='CAB-01', name='Different package', revision='0')
        revision = '1'
    else:
        book = load_workbook(io.BytesIO(author.get('/reform/excel/download?scope=all').data))
        book['BOM']['C2'] = 5
        data = io.BytesIO()
        book.save(data)
        book.close()
        data.seek(0)
        with author.session_transaction() as session:
            csrf = session['reform_csrf']
        response = author.post('/reform/excel/upload', data={'csrf': csrf, 'file': (data, 'update.xlsx')}, follow_redirects=True)
        assert 'Excel changes saved' in response.text
    assert snapshot(app)['approvals'] == 0
    stale = approve(reviewer, revision=revision, package_digest=old_digest)
    assert stale.status_code == 409
    assert snapshot(app)['submissions'] == 0
    assert '1 more Reform representative' in approve(reviewer, revision=revision).text
    assert 'submitted to Furnibox' in approve(author, revision=revision).text
    assert snapshot(app)['submissions'] == 1


def test_approval_workflow_access_and_source_change(pair):
    app, author, reviewer = pair
    with reviewer.session_transaction() as session:
        csrf = session['reform_csrf']
    assert reviewer.post('/reform/submit', data={'csrf': csrf, 'version':'v2.0',
                         'revision':'1', 'package_digest':fingerprint(reviewer)}).status_code == 302
    assert snapshot(app)['approvals'] == 0
    assert reviewer.post('/reform/submit', data={}).status_code == 400
    anonymous = app.test_client()
    anonymous.get('/reform/login')
    with anonymous.session_transaction() as session:
        token = session['reform_csrf']
    assert anonymous.post('/reform/submit', data={'csrf': token}).status_code == 302
    app.config['REFORM_ADMIN_ENABLED'] = True
    admin = app.test_client()
    with admin.session_transaction() as session:
        session['authenticated'] = True
        session['reform_csrf'] = 'admin-token'
    assert post(admin, 'submit', version='v2.0', revision='1', confirm='yes',
                package_digest=fingerprint(author)).status_code == 403
    approve(author)
    with app.app_context(), db() as conn:
        from webapp.reform_workspace import pack
        source = baseline(conn)
        source['captured_at'] = '2026-10-29T12:00:00+00:00'
        conn.execute('UPDATE state SET payload=? WHERE id=1', (pack(source),))
    assert 'source data has changed' in approve(reviewer).text
    assert snapshot(app)['submissions'] == 0


def test_approval_workflow_concurrent_final_clicks_submit_once(pair):
    app, author, reviewer = pair
    approve(author)
    second_session = login(app, 'other', 'other-password')
    token = fingerprint(reviewer)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda client: approve(client, package_digest=token), [reviewer, second_session]))
    assert all(result.status_code == 200 for result in results)
    assert snapshot(app)['submissions'] == 1
    with app.app_context(), db() as conn:
        assert conn.execute('SELECT count(*) FROM notification_outbox').fetchone()[0] == 1


def test_approval_workflow_old_schema_approvals_do_not_count(pair):
    app, author, reviewer = pair
    with app.app_context(), db() as conn:
        conn.execute("INSERT INTO reform_version_approvals(number,actor,revision,created) VALUES ('v2.0','paul',1,'old')")
    assert '0 of 2 Reform approvals recorded' in reviewer.get('/reform/versions').text
    assert '1 more Reform representative' in approve(reviewer).text
    assert snapshot(app)['submissions'] == 0
    assert 'submitted to Furnibox' in approve(author).text
