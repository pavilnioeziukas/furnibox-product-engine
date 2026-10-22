import re
import time

import pytest
from flask import Flask
from werkzeug.security import generate_password_hash

from webapp.reform_workspace import reform, db


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    app = Flask('webapp', template_folder='templates', static_folder='static')
    app.config.update(TESTING=True, SECRET_KEY='test', REFORM_STATE_DIR=tmp_path,
                      REFORM_USERS={'poul@example.com': {'password_hash': generate_password_hash('old-password'),
                                                       'email': 'poul@example.com'}})
    app.register_blueprint(reform)
    monkeypatch.setenv('REFORM_PASSWORD_RESET_ENABLED', 'true')
    monkeypatch.setenv('REFORM_PUBLIC_URL', 'https://example.com')
    monkeypatch.setenv('REFORM_EMAIL_PROVIDER', 'smtp')
    mails = []
    monkeypatch.setattr('webapp.reform_notifications.send_smtp', lambda row: mails.append(row))
    return app, app.test_client(), mails


def post(client, path, **data):
    client.get('/reform/login')
    with client.session_transaction() as sess:
        csrf = sess['reform_csrf']
    return client.post(path, data={'csrf': csrf, **data})


def issue(client, mails):
    post(client, '/reform/forgot-password', email='poul@example.com')
    return re.search(r'https://example.com(/reform/reset-password/\S+)', mails[-1]['body'])[1]


def test_reset_persists_consumes_all_tokens_and_revokes_sessions(recovery):
    app, client, mails = recovery
    old_session = app.test_client()
    assert post(old_session, '/reform/login', username='poul@example.com', password='old-password').status_code == 302
    first = issue(client, mails)
    second = issue(client, mails)
    assert client.get(first).headers['Referrer-Policy'] == 'no-referrer'
    assert post(client, first, password='new-password-long', confirm_password='new-password-long').status_code == 302
    assert 'invalid or has expired' in client.get(second).text
    assert 'invalid or has expired' in client.get(first).text
    assert old_session.get('/reform/').status_code == 302
    assert 'Sign-in failed' in post(client, '/reform/login', username='poul@example.com', password='old-password').text
    assert post(client, '/reform/login', username='poul@example.com', password='new-password-long').status_code == 302
    with app.app_context(), db() as conn:
        assert conn.execute('SELECT password_hash FROM reform_passwords').fetchone()[0] != 'new-password-long'


def test_unknown_accounts_rate_limit_csrf_and_password_validation(recovery):
    app, client, mails = recovery
    known = post(client, '/reform/forgot-password', email='poul@example.com')
    unknown = post(client, '/reform/forgot-password', email='unknown@example.com')
    assert known.text == unknown.text
    assert len(mails) == 1
    path = re.search(r'https://example.com(/reform/reset-password/\S+)', mails[0]['body'])[1]
    assert client.post(path, data={'password': 'new-password-long'}).status_code == 400
    assert 'between 12 and 256' in post(client, path, password='short', confirm_password='short').text
    assert 'do not match' in post(client, path, password='new-password-long', confirm_password='different-password').text
    for _ in range(8):
        post(client, '/reform/forgot-password', email='poul@example.com')
    assert len(mails) == 4  # Five requests per IP, including the unknown address.
    with app.app_context(), db() as conn:
        conn.execute('UPDATE reform_reset_tokens SET expires=?', (time.time() - 1,))
    assert 'invalid or has expired' in client.get(path).text


def test_removed_account_disabled_delivery_and_host_header(recovery, monkeypatch):
    app, client, mails = recovery
    path = issue(client, mails)
    assert 'https://example.com/' in mails[0]['body']
    app.config['REFORM_USERS'].clear()
    assert 'invalid or has expired' in client.get(path).text
    monkeypatch.setenv('REFORM_PASSWORD_RESET_ENABLED', 'false')
    assert 'currently unavailable' in client.get('/reform/forgot-password').text


def test_mail_failure_discards_token(recovery, monkeypatch):
    app, client, mails = recovery
    def fail(row):
        raise RuntimeError('provider unavailable')
    monkeypatch.setattr('webapp.reform_notifications.send_smtp', fail)
    assert post(client, '/reform/forgot-password', email='poul@example.com').status_code == 200
    with app.app_context(), db() as conn:
        assert conn.execute('SELECT count(*) FROM reform_reset_tokens').fetchone()[0] == 0
