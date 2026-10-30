import re

import pytest

from test_reform_workspace import setup, post, sample
from test_reform_shared import start, shared, book
from test_reform_excel import upload_book
from webapp.reform_workspace import db, baseline, pack, unpack


def cancel(client, **overrides):
    page = client.get('/reform/?view=review').text
    match = re.search(r'name="package_digest" value="([^"]+)"', page)
    return post(client, 'cancel-all', **{'version': 'v3.0', 'revision': '1', 'confirm': 'yes',
                'package_digest': match.group(1) if match else '', **overrides})


def test_any_contributor_can_cancel_all_and_return_to_newest_source(setup):
    app, coordinator, contributor = start(setup)
    old_file = book(contributor)
    post(coordinator, 'save', action='product', sku='CAB-01', name='Proposed', revision='0')
    post(coordinator, 'submit', version='v3.0', revision='1', confirm='yes')
    source = sample()
    source['captured_at'] = '2026-10-30T12:00:00+00:00'
    with app.app_context(), db() as conn:
        conn.execute('UPDATE state SET payload=? WHERE id=1', (pack(source),))
    page = contributor.get('/reform/?view=review').text
    assert 'Cancel all proposed changes' in page and 'return confirm(' in page
    assert 'All proposed changes in the shared version were cancelled' in cancel(contributor).text
    work, revision = shared(app)
    assert work == {'base': source, 'target': source} and revision == 2
    with app.app_context(), db() as conn:
        assert baseline(conn) == source
        assert conn.execute('SELECT count(*) FROM reform_version_approvals').fetchone()[0] == 0
        saved = conn.execute('SELECT * FROM reform_cancelled_drafts').fetchone()
        assert saved['actor'] == 'other' and unpack(saved['payload'])['target']['products']['CAB-01']['name'] == 'Proposed'
        assert conn.execute('SELECT count(*) FROM submissions').fetchone()[0] == 0
    assert 'Source data has changed' in upload_book(contributor, old_file).text
    assert book(contributor)['Products']['B2'].value == sample()['products']['CAB-01']['name']


@pytest.mark.parametrize('mode', ['unconfirmed', 'stale', 'locked'])
def test_cancel_guards_preserve_the_shared_changes(setup, mode):
    app, coordinator, contributor = start(setup)
    post(coordinator, 'save', action='product', sku='CAB-01', name='Proposed', revision='0')
    if mode == 'locked':
        with app.app_context(), db() as conn:
            conn.execute("UPDATE reform_versions SET status='submitted'")
    overrides = {'confirm': ''} if mode == 'unconfirmed' else {'package_digest': 'old'}
    if mode == 'locked':
        overrides = {}
    response = cancel(contributor, **overrides)
    assert response.status_code == (400 if mode == 'unconfirmed' else 409)
    with app.app_context(), db() as conn:
        row = conn.execute('SELECT payload FROM drafts').fetchone()
        assert unpack(row[0])['target']['products']['CAB-01']['name'] == 'Proposed'
