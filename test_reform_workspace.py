import copy
import json

import pytest
from werkzeug.security import generate_password_hash
from webapp.reform_workspace import db, draft, baseline, read_odoo, validate, validate_proposal, changes
from test_webapp import load_webapp


def sample():
    return {'source': 'Demonstraciniai duomenys', 'captured_at': '2026-09-28T10:00:00+00:00',
        'external_usage': {}, 'products': {
            'CAB-01': {'sku': 'CAB-01', 'name': 'Spintelė 600', 'active': True, 'uom': 'vnt.', 'uom_id': 1},
            'PANEL-01': {'sku': 'PANEL-01', 'name': 'Šoninė plokštė', 'active': True, 'uom': 'vnt.', 'uom_id': 1},
            'HINGE-01': {'sku': 'HINGE-01', 'name': 'Lankstas', 'active': True, 'uom': 'vnt.', 'uom_id': 1}},
        'boms': {'1': {'id': '1', 'sku': 'CAB-01', 'code': 'Spintelės komplektacija', 'quantity': 1,
            'uom': 'vnt.', 'uom_id': 1, 'active': True, 'type': 'normal', 'components': [
                {'id': '10', 'sku': 'PANEL-01', 'quantity': 2, 'uom': 'vnt.', 'uom_id': 1},
                {'id': '11', 'sku': 'HINGE-01', 'quantity': 4, 'uom': 'vnt.', 'uom_id': 1}]}}}


@pytest.fixture
def setup(monkeypatch, tmp_path):
    web = load_webapp(monkeypatch, tmp_path)
    app = web.app
    app.config.update(TESTING=True, REFORM_USERS={'paul': generate_password_hash('test-password'), 'other': generate_password_hash('other-password')})
    with app.app_context(), db() as conn:
        conn.execute('INSERT INTO state VALUES (1,?)', (json.dumps(sample()),))
    client = app.test_client()
    client.get('/reform/login')
    with client.session_transaction() as sess:
        token = sess['reform_csrf']
    assert client.post('/reform/login', data={'csrf': token, 'username': 'paul', 'password': 'test-password'}).status_code == 302
    client.get('/reform/')
    return app, client


def post(client, path, **data):
    with client.session_transaction() as sess:
        token = sess['reform_csrf']
    if path == 'submit' and 'version' not in data:
        from webapp.reform_versions import schema, active
        with client.application.app_context(), db() as conn:
            schema(conn)
            version = active(conn)
        if not version:
            client.post('/reform/versions/save', data={'csrf': token, 'number': 'v1.0', 'description': 'Test release', 'revision': data.get('revision', '0')})
        data['version'] = version['number'] if version else 'v1.0'
    return client.post('/reform/' + path, data={'csrf': token, **data}, follow_redirects=True)


def test_initialize_requires_admin_and_empty_catalogue(setup):
    import io
    app, client = setup
    payload = json.dumps({'schema': 'reform-catalogue-seed-v1', 'catalogue': sample(), 'reserved_skus': ['CAB-01']}).encode()
    def upload(token=True):
        with client.session_transaction() as sess:
            csrf = sess['reform_csrf']
        return client.post('/reform/initialize', data={'csrf': csrf if token else '', 'file': (io.BytesIO(payload), 'catalogue.json')})
    assert upload().status_code == 403
    app.config['REFORM_ADMIN_ENABLED'] = True
    with client.session_transaction() as sess:
        sess.pop('reform_user')
        sess['authenticated'] = True
    assert upload().status_code == 409
    with app.app_context(), db() as conn:
        conn.execute('DELETE FROM state')
    assert upload(False).status_code == 400
    assert upload().status_code == 302
    assert upload().status_code == 409
    with app.app_context(), db() as conn:
        assert baseline(conn) == sample()


def test_access_boundaries_and_csrf(setup):
    app, client = setup
    for path in ['/', '/pricing-control', '/reports', '/login', '/bootstraps', '/jobs/anything']:
        assert client.get(path).status_code == 403
    assert post(client, 'refresh', skus='CAB-01').status_code == 403
    assert client.post('/reform/save', data={}).status_code == 400
    anon = app.test_client()
    assert anon.get('/reform/').status_code == 302
    with anon.session_transaction() as sess:
        sess['authenticated'] = True
    assert anon.get('/reform/').status_code == 302  # No configured admin password.
    with app.app_context():
        app.config['REFORM_USERS'].pop('paul')
    assert client.get('/reform/').status_code == 302


def test_new_product_and_bom_submit_immutable_and_private(setup):
    app, client = setup
    response = post(client, 'save', action='product', new='1', sku='NEW', name='New product', uom='vnt.', revision='0')
    assert 'New product' in response.text
    post(client, 'save', action='bom', sku='NEW', quantity='1', code='New BOM',
         component_sku=['PANEL-01'], component_quantity=['3'], component_id=[''], revision='1')
    response = post(client, 'submit', confirm='yes', revision='2')
    assert 'submitted to Furnibox' in response.text
    bundle = client.get('/reform/submissions/1').get_json()
    assert 'New product' in client.get('/reform/submissions/1/view').text
    assert len(bundle['changes']) == 2
    assert bundle['submitted_by'] == 'paul'
    with app.app_context(), db() as conn:
        assert baseline(conn) == sample()
        assert conn.execute('SELECT count(*) FROM drafts').fetchone()[0] == 0
    with client.session_transaction() as sess:
        sess['reform_user'] = 'other'
    assert client.get('/reform/submissions/1').status_code == 404
    assert client.get('/reform/submissions/1/view').status_code == 404


def test_bom_edit_remove_and_retire(setup):
    app, client = setup
    post(client, 'save', action='bom', bom_id='1', quantity='1', code='Spintelės komplektacija',
         component_sku=['PANEL-01'], component_quantity=['3'], component_id=['10'], revision='0')
    post(client, 'save', action='retire', sku='HINGE-01', revision='1')
    response = post(client, 'submit', confirm='yes', revision='2')
    assert 'submitted to Furnibox' in response.text
    bundle = client.get('/reform/submissions/1').get_json()
    bom = next(c for c in bundle['changes'] if c['kind'] == 'boms')
    assert len(bom['before']['components']) == 2
    assert bom['after']['components'] == [{'id': '10', 'sku': 'PANEL-01', 'quantity': 3.0, 'uom': 'vnt.', 'uom_id': 1}]


def test_retirement_usage_and_cycles_block_confirmation(setup):
    app, client = setup
    post(client, 'save', action='retire', sku='HINGE-01', revision='0')
    response = post(client, 'submit', confirm='yes', revision='1')
    assert 'has been retired' in response.text
    with app.app_context(), db() as conn:
        assert conn.execute('SELECT count(*) FROM submissions').fetchone()[0] == 0
    cycle = sample()
    cycle['boms']['1']['components'][0]['sku'] = 'CAB-01'
    with pytest.raises(ValueError, match='cycle'):
        validate(cycle)


def test_stale_revision_snapshot_and_duplicate_codes(setup):
    app, client = setup
    response = post(client, 'save', action='product', new='1', sku='cab-01', name='Duplicate', uom='vnt.', revision='0')
    assert 'already exists' in response.text
    post(client, 'save', action='product', sku='CAB-01', name='Updated', revision='0')
    assert post(client, 'save', action='product', sku='CAB-01', name='Lost update', revision='0').status_code == 409
    with app.app_context(), db() as conn:
        current = sample()
        current['captured_at'] = '2026-09-29T10:00:00+00:00'
        conn.execute('UPDATE state SET payload=?', (json.dumps(current),))
    assert 'The source data has changed' in post(client, 'submit', revision='1', confirm='yes').text
    assert client.get('/reform/draft/download').get_json()['changes'][0]['after']['name'] == 'Updated'


def test_existing_private_sku_rejected_without_exposing_catalogue(setup):
    app, client = setup
    with app.app_context(), db() as conn:
        conn.execute('INSERT INTO state VALUES (2,?)', (json.dumps(['PRIVATE-SKU']),))
    response = post(client, 'save', action='product', new='1', sku='private-sku', name='Duplicate', uom='vnt.', revision='0')
    assert 'code is already in use' in response.text
    assert 'PRIVATE-SKU' not in client.get('/reform/draft/download').text


def test_login_rate_limit_and_admin_view(setup):
    app, client = setup
    stranger = app.test_client()
    stranger.get('/reform/login')
    for _ in range(5):
        post(stranger, 'login', username='other', password='wrong')
    assert 'Sign-in failed' in post(stranger, 'login', username='other', password='other-password').text
    post(client, 'save', action='product', sku='CAB-01', name='Updated', revision='0')
    post(client, 'submit', revision='1', confirm='yes')
    app.config['REFORM_ADMIN_ENABLED'] = True
    with stranger.session_transaction() as sess:
        sess.clear()
        sess['authenticated'] = True
    assert 'paul' in stranger.get('/reform/?view=sent').text
    assert 'Updated' in stranger.get('/reform/submissions/1/view').text


def test_duplicate_pending_proposal_is_blocked(setup):
    app, client = setup
    post(client, 'save', action='product', sku='CAB-01', name='Updated', revision='0')
    post(client, 'submit', revision='1', confirm='yes')
    post(client, 'save', action='product', sku='CAB-01', name='Updated again', revision='0')
    assert 'Save and review a version draft' in post(client, 'submit', revision='1', confirm='yes').text


def test_catalogue_search_pagination_and_existing_bom(setup):
    app, client = setup
    data = sample()
    for i in range(105):
        data['products'][f'EXISTING-{i:03d}'] = {'sku': f'EXISTING-{i:03d}', 'name': f'Esamas gaminys {i}', 'active': True, 'uom': 'vnt.', 'uom_id': 1}
    with app.app_context(), db() as conn:
        conn.execute('UPDATE state SET payload=? WHERE id=1', (json.dumps(data),))
    home = client.get('/reform/?view=catalogue').text
    assert 'Products' in home and '108' in home
    assert 'EXISTING-104' not in home
    result = client.get('/reform/?q=EXISTING-104').text
    assert 'EXISTING-104' in result and 'Found: 1' in result
    assert 'EXISTING-104' in client.get('/reform/?page=4').text
    selected = client.get('/reform/?product=CAB-01').text
    assert 'EXISTING BOM' in selected
    assert 'Spintelės komplektacija' in selected
    assert 'Edit this BOM' in selected
    assert 'Save and review changes' not in selected


def test_home_actions_and_specific_bom_edit_flow(setup):
    app, client = setup
    home = client.get('/reform/').text
    for text in ['What would you like to do?', 'Browse products and BOMs', 'Edit an existing BOM',
                 'Create a new product', 'Create a new BOM']:
        assert text in home
    listing = client.get('/reform/?view=bom-list&intent=edit&q=Spintel').text
    assert 'Spintelės komplektacija' in listing
    assert 'Edit this BOM' in listing
    editor = client.get('/reform/?view=edit-bom&bom_id=1').text
    assert 'Edit selected BOM' in editor
    assert 'Save and review changes' in editor
    assert 'name="bom_id" value="1"' in editor
    assert client.get('/reform/?view=edit-bom&bom_id=unknown').status_code == 404
    response = post(client, 'save', action='bom', bom_id='1', quantity='1', code='Spintelės komplektacija',
        component_sku=['PANEL-01'], component_quantity=['3'], component_id=['10'],
        return_view='review', return_product='CAB-01', revision='0')
    assert 'Save to version draft / review complete version' in response.text
    assert 'PANEL-01 — 3.0' in response.text


def test_edit_screen_does_not_mix_two_boms(setup):
    app, client = setup
    data = sample()
    other = copy.deepcopy(data['boms']['1'])
    other.update(id='2', code='Kita komplektacija')
    data['boms']['2'] = other
    with app.app_context(), db() as conn:
        conn.execute('UPDATE state SET payload=? WHERE id=1', (json.dumps(data),))
    editor = client.get('/reform/?view=edit-bom&bom_id=1').text
    assert 'Spintelės komplektacija' in editor
    assert 'Kita komplektacija' not in editor
    listing = client.get('/reform/?view=bom-list').text
    assert 'Spintelės komplektacija' in listing and 'Kita komplektacija' in listing


def test_preexisting_unrelated_invalid_bom_does_not_block_edit():
    base = sample()
    base['boms']['old-invalid'] = copy.deepcopy(base['boms']['1'])
    base['boms']['old-invalid']['id'] = 'old-invalid'
    base['boms']['old-invalid']['components'][0]['sku'] = 'MISSING'
    target = copy.deepcopy(base)
    target['boms']['1']['components'][0]['quantity'] = 3
    validate_proposal(target, changes(base, target))
    target['boms']['1']['components'][0]['sku'] = 'CAB-01'
    with pytest.raises(ValueError):
        validate_proposal(target, changes(base, target))


def test_read_only_bom_cannot_be_modified_via_post(setup):
    app, client = setup
    data = sample()
    data['boms']['1']['read_only'] = 'Variantų BOM rodomas tik peržiūrai.'
    with app.app_context(), db() as conn:
        conn.execute('UPDATE state SET payload=? WHERE id=1', (json.dumps(data),))
    result = post(client, 'save', action='bom', bom_id='1', quantity='2', revision='0')
    assert 'Variantų BOM rodomas tik peržiūrai' in result.text
    with app.app_context(), db() as conn:
        assert conn.execute('SELECT count(*) FROM drafts').fetchone()[0] == 0


def test_read_only_product_cannot_receive_new_bom(setup):
    app, client = setup
    data = sample()
    data['products']['CAB-01']['read_only'] = 'Product code kartojasi.'
    with app.app_context(), db() as conn:
        conn.execute('UPDATE state SET payload=? WHERE id=1', (json.dumps(data),))
    result = post(client, 'save', action='bom', sku='CAB-01', quantity='1', revision='0')
    assert 'Product code kartojasi' in result.text
    with app.app_context(), db() as conn:
        assert conn.execute('SELECT count(*) FROM drafts').fetchone()[0] == 0


@pytest.mark.parametrize('quantity', ['NaN', 'inf', '-1', '0', 'oops'])
def test_invalid_quantities_do_not_save(setup, quantity):
    app, client = setup
    post(client, 'save', action='bom', bom_id='1', code='', quantity=quantity, revision='0')
    with app.app_context(), db() as conn:
        assert conn.execute('SELECT count(*) FROM drafts').fetchone()[0] == 0


def test_external_usage_blocks_retirement(setup):
    app, client = setup
    with app.app_context(), db() as conn:
        current = sample()
        current['external_usage'] = {'CAB-01': 1}
        conn.execute('UPDATE state SET payload=?', (json.dumps(current),))
    post(client, 'save', action='retire', sku='CAB-01', revision='0')
    assert 'outside the pilot scope' in post(client, 'submit', revision='1', confirm='yes').text


def test_read_only_odoo_scope_units_and_external_usage():
    class Client:
        def search_read_all(self, model, domain, fields, **kwargs):
            assert not any('price' in f for f in fields)
            if model == 'product.product':
                return [{'id': i, 'default_code': sku, 'name': sku, 'active': True, 'product_tmpl_id': [i, sku], 'uom_id': [1, 'Units']} for i, sku in [(1, 'ROOT'), (2, 'PART'), (3, 'OTHER')]]
            if model == 'mrp.bom':
                return [{'id': i, 'product_id': [p, ''], 'product_tmpl_id': [p, ''], 'product_qty': 2, 'product_uom_id': [1, 'Units'], 'type': 'normal', 'code': ''} for i, p in [(10, 1), (20, 3)]]
            return [{'id': i, 'bom_id': [b, ''], 'product_id': [2, ''], 'product_qty': 3, 'product_uom_id': [1, 'Units'], 'bom_product_template_attribute_value_ids': []} for i, b in [(100, 10), (200, 20)]]
    data = read_odoo(Client(), ['ROOT'])
    assert set(data['products']) == {'ROOT', 'PART'}
    assert set(data['boms']) == {'10'}
    assert data['boms']['10']['quantity'] == 2
    assert data['external_usage'] == {'PART': 1}
    complete = read_odoo(Client())
    assert set(complete['products']) == {'ROOT', 'PART', 'OTHER'}
    assert set(complete['boms']) == {'10', '20'}
    assert complete['scope'] == 'production_catalogue'

def test_reform_hides_assembly_products_and_keeps_fpack(setup):
    app, client = setup
    with app.app_context(), db() as conn:
        data = sample()
        for sku in ('APACK-EU-BOX', 'CAB-01-A', 'FPACK-EU-BOX'):
            data['products'][sku] = {**data['products']['CAB-01'], 'sku': sku, 'name': sku}
            data['boms'][sku] = {**copy.deepcopy(data['boms']['1']), 'id': sku, 'sku': sku, 'code': sku}
        conn.execute('UPDATE state SET payload=? WHERE id=1', (json.dumps(data),))
    for path in ('?view=catalogue', '?view=bom-list', '?view=new-bom', '?product=CAB-01'):
        page = client.get('/reform/' + path).text
        assert 'APACK-EU-BOX' not in page and 'CAB-01-A' not in page
        assert 'FPACK-EU-BOX' in page
    assert client.get('/reform/?view=edit-bom&bom_id=APACK-EU-BOX').status_code == 404
    result = post(client, 'save', action='retire', sku='CAB-01-A', revision='0')
    assert 'managed by Furnibox' in result.text
    with app.app_context(), db() as conn:
        assert baseline(conn)['products']['CAB-01-A']['active']


def test_current_bom_uses_lowest_sequence_then_latest_date():
    class Client:
        def search_read_all(self, model, domain, fields, **kwargs):
            if model == 'product.product':
                return [{'id': i, 'default_code': sku, 'name': sku, 'active': True,
                         'product_tmpl_id': [i, sku], 'uom_id': [1, 'Units']}
                        for i, sku in [(1, 'CAB'), (2, 'PART')]]
            if model == 'mrp.bom':
                assert 'sequence' in fields and 'write_date' in fields
                return [{'id': i, 'product_id': [1, ''], 'product_tmpl_id': [1, ''],
                         'product_qty': 1, 'product_uom_id': [1, 'Units'], 'type': 'normal',
                         'code': str(i), 'sequence': seq, 'write_date': date}
                        for i, seq, date in [(10, 5, '2026-09-28'), (11, 0, '2026-01-01'), (12, 0, '2026-02-01')]]
            return [{'id': i, 'bom_id': [i, ''], 'product_id': [2, ''], 'product_qty': 2,
                     'product_uom_id': [1, 'Units'], 'bom_product_template_attribute_value_ids': []}
                    for i in (10, 11, 12)]
    data = read_odoo(Client())
    assert set(data['boms']) == {'12'}
    assert data['boms']['12']['sequence'] == 0
    assert data['external_usage'] == {}


def test_hidden_component_does_not_get_deleted_by_edit(setup):
    app, client = setup
    with app.app_context(), db() as conn:
        data = sample()
        data['products']['PART-A'] = {**data['products']['PANEL-01'], 'sku': 'PART-A'}
        data['boms']['1']['components'].append({'id': 'hidden', 'sku': 'PART-A', 'quantity': 1, 'uom': 'vnt.'})
        conn.execute('UPDATE state SET payload=? WHERE id=1', (json.dumps(data),))
    page = client.get('/reform/?view=edit-bom&bom_id=1').text
    assert 'PART-A' not in page
    assert 'Furnibox must review' in page
    result = post(client, 'save', action='bom', bom_id='1', quantity='1', revision='0',
                  component_sku=['PANEL-01'], component_quantity=['3'], component_id=['10'])
    assert 'requires Furnibox review' in result.text
    with app.app_context(), db() as conn:
        assert baseline(conn)['boms']['1']['components'][-1]['sku'] == 'PART-A'
        assert conn.execute('SELECT count(*) FROM drafts').fetchone()[0] == 0
