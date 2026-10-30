import copy

import pytest

from test_reform_workspace import setup, sample
from webapp.reform_workspace import db, baseline, pack, unpack, digest
from webapp.reform_sync import publish, already_done


def snapshot():
    return dict(sample(), source='Odoo Production', scope='production_catalogue',
                captured_at='2026-10-30T10:00:00+00:00', _reserved_skus=['CAB-01', 'PANEL-01', 'HINGE-01'])


def test_refresh_keeps_drafts_and_previous_source_and_is_idempotent(setup):
    app, client = setup
    data = snapshot()
    data['products']['PANEL-01']['supplier_codes'] = ['SUP-2']
    work = {'base': sample(), 'target': sample()}
    work['target']['boms']['1']['components'][0]['quantity'] = 3
    with app.app_context(), db() as conn:
        conn.execute('INSERT INTO drafts VALUES (?,?,?)', ('paul', 7, pack(work)))
    with app.app_context(), db() as conn:
        assert publish(conn, data, 'refresh-test')
    with app.app_context(), db() as conn:
        assert already_done(conn, 'refresh-test')
        assert baseline(conn)['captured_at'] == data['captured_at']
        assert unpack(conn.execute('SELECT payload FROM state WHERE id=2').fetchone()[0]) == data['_reserved_skus']
        assert unpack(conn.execute('SELECT payload FROM state WHERE id=3').fetchone()[0])['PANEL-01'] == ['SUP-2']
        row = conn.execute('SELECT * FROM drafts').fetchone()
        assert row['revision'] == 7 and unpack(row['payload']) == work
        old = conn.execute('SELECT payload FROM catalogue_snapshots WHERE digest=?', (digest(sample()),)).fetchone()
        assert unpack(old[0]) == sample()
    changed = copy.deepcopy(data)
    changed['products']['PANEL-01']['name'] = 'Must not replace'
    with app.app_context(), db() as conn:
        assert not publish(conn, changed, 'refresh-test')
        assert baseline(conn)['products']['PANEL-01']['name'] != 'Must not replace'


@pytest.mark.parametrize('field,value', [('products', {}), ('boms', {}), ('scope', 'selected'), ('source', 'Unverified')])
def test_invalid_refresh_keeps_existing_source(setup, field, value):
    app, client = setup
    data = snapshot()
    data[field] = value
    with app.app_context(), db() as conn:
        with pytest.raises(ValueError):
            publish(conn, data, 'invalid')
        assert baseline(conn) == sample()

