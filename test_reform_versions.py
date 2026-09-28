import json
from test_reform_workspace import setup, post
from webapp.reform_workspace import db, baseline, unpack


def test_batch_submit_return_resubmit_and_admin_review(setup):
    app, client = setup
    post(client,'save',action='product',new='1',sku='NEW-ONE',name='One',uom='vnt.',revision='0')
    assert 'Version draft saved' in post(client,'versions/save',number='v11.1',description='Cabinet update',revision='1').text
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
    assert post(admin,'versions/review',number='v11.1',submission_id=second,action='accepted').status_code == 200
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
    post(client,'save',action='product',new='1',sku='NEW-ONE',name='One',uom='vnt.',revision='0')
    assert post(client,'versions/save',number='v11.1',description='Update',revision='0').status_code==409
    assert post(client,'versions/save',number='v11.1',description='Update',revision='1').status_code==200
    assert post(client,'submit',version='v11.1',revision='0',confirm='yes').status_code==409
