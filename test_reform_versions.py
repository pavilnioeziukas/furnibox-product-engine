import json
from test_reform_workspace import setup, post, sample
from webapp.reform_workspace import db, baseline, unpack
from webapp.reform_versions import next_revision, schema, bom_revision_plan, record_bom_revisions


def test_alphabetic_bom_revision_sequence_and_immutable_history(setup):
    app, client = setup
    assert next_revision(None) == 'A'
    assert next_revision('A') == 'B'
    assert next_revision('Z') == 'AA'
    existing = sample()['boms']['1']
    changed = json.loads(json.dumps(existing))
    changed['components'][0]['quantity'] = 3
    new_bom = {**json.loads(json.dumps(existing)), 'id': 'new-1', 'sku': 'NEW-PRODUCT'}
    delta = [
        {'kind': 'boms', 'key': '1', 'before': existing, 'after': changed},
        {'kind': 'boms', 'key': 'new-1', 'before': None, 'after': new_bom},
    ]
    with app.app_context(), db() as conn:
        schema(conn)
        plan = bom_revision_plan(conn, delta)
        assert plan['1'] == {'product_code': 'CAB-01', 'current': 'A', 'proposed': 'B'}
        assert plan['new-1'] == {'product_code': 'NEW-PRODUCT', 'current': None, 'proposed': 'A'}
        record_bom_revisions(conn, 'v11.1', delta, plan)
        rows = conn.execute('''SELECT product_code,revision,status,snapshot FROM reform_bom_revisions
            ORDER BY product_code,revision''').fetchall()
        assert [(r['product_code'], r['revision'], r['status']) for r in rows] == [
            ('CAB-01', 'A', 'superseded'), ('CAB-01', 'B', 'current'),
            ('NEW-PRODUCT', 'A', 'current')]
        assert unpack(rows[0]['snapshot'])['components'][0]['quantity'] == 2
        assert unpack(rows[1]['snapshot'])['components'][0]['quantity'] == 3


def test_existing_bom_change_displays_next_plm_revision(setup):
    app, client = setup
    post(client, 'save', action='bom', bom_id='1', quantity='1', code='Spintelės komplektacija',
         component_sku=['PANEL-01'], component_quantity=['3'], component_id=['10'], revision='0')
    post(client, 'versions/save', number='v11.1', description='BOM revision', revision='1')
    page = client.get('/reform/versions').text
    assert 'PLM changes and BOM revisions' in page
    assert 'A → B' in page
    assert 'Proposed by:</strong> paul' in page


def test_change_and_bom_revision_history_display_proposer(setup):
    app, client = setup
    existing = sample()['boms']['1']
    changed = json.loads(json.dumps(existing))
    changed['components'][0]['quantity'] = 3
    delta = [{'kind': 'boms', 'key': '1', 'before': existing, 'after': changed}]
    with app.app_context(), db() as conn:
        schema(conn)
        conn.execute('INSERT INTO reform_versions VALUES (?,?,?,?,?,?,?,?)',
                     ('v11.1', 'paul', 'BOM update', 'implemented', None,
                      '2026-10-07T08:00:00+00:00', '2026-10-07T08:00:00+00:00', ''))
        record_bom_revisions(conn, 'v11.1', delta, bom_revision_plan(conn, delta))
    page = client.get('/reform/versions').text
    assert 'Proposed by paul' in page
    assert 'Source: Odoo production baseline' in page
    assert 'BOM update · Proposed by paul' in page


def test_other_reform_user_can_review_but_not_edit_open_version(setup):
    app, owner_client = setup
    post(owner_client, 'versions/save', number='v11.1', description='Shared review', revision='0')
    post(owner_client, 'save', action='product', sku='CAB-01', name='Updated cabinet', revision='0')
    reviewer = app.test_client()
    reviewer.get('/reform/login')
    with reviewer.session_transaction() as sess:
        token = sess['reform_csrf']
    reviewer.post('/reform/login', data={'csrf': token, 'username': 'other', 'password': 'other-password'})
    version_page = reviewer.get('/reform/versions').text
    assert 'Proposed by:</strong> paul' in version_page
    assert 'Updated cabinet' in version_page
    files_page = reviewer.get('/reform/?view=files').text
    assert 'only its owner can add files' in files_page
    assert 'Review this version' in files_page


def test_batch_submit_return_resubmit_and_admin_review(setup):
    app, client = setup
    assert 'Version draft saved' in post(client,'versions/save',number='v11.1',description='Cabinet update',revision='0').text
    post(client,'save',action='product',new='1',sku='NEW-ONE',name='One',uom='vnt.',revision='0')
    post(client,'save',action='product',new='1',sku='NEW-TWO',name='Two',uom='vnt.',revision='1')
    assert '2 changed records' in client.get('/reform/versions').text
    assert 'submitted' in post(client,'submit',version='v11.1',revision='2',confirm='yes').text
    with app.app_context(), db() as conn:
        first = conn.execute('SELECT * FROM submissions').fetchone()
        original = first['payload']
        assert len(unpack(original)['changes']) == 2
        assert conn.execute('SELECT count(*) FROM notification_outbox').fetchone()[0] == 1
    assert post(client,'save',action='product',new='1',sku='BLOCKED',name='Blocked',uom='vnt.',revision='0').status_code == 409
    assert post(client,'versions/review',number='v11.1',submission_id=first['id'],action='accepted').status_code == 403
    app.config['REFORM_ADMIN_ENABLED'] = True
    admin = app.test_client()
    with admin.session_transaction() as sess:
        sess['authenticated']=True
        sess['reform_csrf']='admin-token'
    response = post(admin,'versions/review',number='v11.1',submission_id=first['id'],action='returned',note='Correct product name')
    assert response.status_code == 200
    assert 'returned' in client.get('/reform/versions').text
    post(client,'save',action='product',sku='NEW-ONE',name='Corrected',revision='3')
    post(client,'submit',version='v11.1',revision='4',confirm='yes')
    with app.app_context(), db() as conn:
        assert conn.execute('SELECT payload FROM submissions WHERE id=?',(first['id'],)).fetchone()[0] == original
        second = conn.execute('SELECT max(id) FROM submissions').fetchone()[0]
        assert second != first['id']
    assert post(admin,'versions/review',number='v11.1',submission_id=first['id'],action='accepted').status_code == 409
    assert post(admin,'versions/review',number='v11.1',submission_id=second,action='accepted').status_code == 400
    assert post(admin,'versions/review',number='v11.1',submission_id=second,action='accepted',
                approve_odoo_sync='yes',note='Furnibox approved production synchronization').status_code == 200
    assert post(admin,'versions/review',number='v11.1',submission_id=second,action='implemented',note='Checked',verified='yes').status_code == 409
    with app.app_context(), db() as conn:
        applied=unpack(conn.execute('SELECT payload FROM submissions WHERE id=?',(second,)).fetchone()[0])['target']
        applied['captured_at']='2026-09-29T10:00:00+00:00'
        conn.execute('UPDATE state SET payload=? WHERE id=1',(json.dumps(applied),))
    assert post(admin,'versions/review',number='v11.1',submission_id=second,action='implemented',note='Odoo verified',verified='yes').status_code == 200
    assert post(client,'versions/save',number='v11.1',description='Reused',revision='0').status_code == 409
    assert post(client,'versions/save',number='v11.2',description='Next release',revision='0').status_code == 200


def test_submit_requires_explicit_version_and_stale_draft_rejected(setup):
    app,client=setup
    with client.session_transaction() as sess:
        token=sess['reform_csrf']
    response=client.post('/reform/submit',data={'csrf':token,'confirm':'yes','revision':'0'},follow_redirects=True)
    assert 'Save and review a version draft' in response.text
    assert post(client,'save',action='product',new='1',sku='NEW-ONE',name='One',uom='vnt.',revision='0',_skip_version=True).status_code==409
    assert post(client,'versions/save',number='v11.1',description='Update',revision='0').status_code==200
    post(client,'save',action='product',new='1',sku='NEW-ONE',name='One',uom='vnt.',revision='0')
    assert post(client,'submit',version='v11.1',revision='0',confirm='yes').status_code==409


def test_two_distinct_reform_users_must_approve_same_revision(setup):
    app, owner_client = setup
    app.config['REFORM_APPROVALS_REQUIRED'] = 2
    post(owner_client, 'versions/save', number='v11.1', description='Two-person review', revision='0')
    post(owner_client, 'save', action='product', new='1', sku='NEW-ONE', name='One', uom='vnt.', revision='0')

    first = post(owner_client, 'submit', version='v11.1', revision='1', confirm='yes')
    assert '1 more Reform representative' in first.text
    assert '1 of 2 Reform approvals recorded' in first.text
    duplicate = post(owner_client, 'submit', version='v11.1', revision='1', confirm='yes')
    assert '1 more Reform representative' in duplicate.text
    with app.app_context(), db() as conn:
        assert conn.execute('SELECT count(*) FROM submissions').fetchone()[0] == 0

    second_client = app.test_client()
    second_client.get('/reform/login')
    with second_client.session_transaction() as sess:
        token = sess['reform_csrf']
    assert second_client.post('/reform/login', data={
        'csrf': token, 'username': 'other', 'password': 'other-password'}).status_code == 302
    page = second_client.get('/reform/versions')
    assert '1 of 2 Reform approvals recorded' in page.text
    assert 'NEW-ONE' in page.text
    assert 'Proposed by:</strong> paul' in page.text
    files = second_client.get('/reform/?view=files')
    assert 'Proposed by:</strong> paul' in files.text
    assert 'only its owner can add files' in files.text
    final = post(second_client, 'submit', version='v11.1', revision='1', confirm='yes')
    assert 'submitted to Furnibox' in final.text
    with app.app_context(), db() as conn:
        payload = unpack(conn.execute('SELECT payload FROM submissions').fetchone()['payload'])
        assert payload['approved_by'] == ['paul', 'other']

