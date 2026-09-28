import smtplib
from unittest.mock import MagicMock
from test_reform_workspace import setup, post
from webapp.reform_workspace import db
from webapp.reform_notifications import deliver


def test_submission_queues_email_until_enabled(setup, monkeypatch):
    app, client = setup
    monkeypatch.delenv('REFORM_EMAIL_ENABLED', raising=False)
    smtp = MagicMock()
    monkeypatch.setattr(smtplib, 'SMTP', smtp)
    post(client, 'save', action='product', new='1', sku='MAIL-TEST', name='Test product', uom='vnt.', revision='0')
    response = post(client, 'submit', revision='1', confirm='yes')
    assert 'submission is saved' in response.text
    smtp.assert_not_called()
    with app.app_context(), db() as conn:
        row = conn.execute('SELECT * FROM notification_outbox').fetchone()
        assert row['recipient'] == 'edgaras@furnix.lt'
        assert row['status'] == 'pending'
        assert 'MAIL-TEST' in row['body']
        assert conn.execute('SELECT count(*) FROM submissions').fetchone()[0] == 1
    for key,value in {'REFORM_EMAIL_ENABLED':'true','REFORM_SMTP_HOST':'smtp.example.test',
                      'REFORM_EMAIL_FROM':'review@example.test','REFORM_SMTP_USERNAME':'user',
                      'REFORM_SMTP_PASSWORD':'test'}.items():
        monkeypatch.setenv(key,value)
    with app.app_context():
        assert deliver(row['submission_id']) == 'sent'
        assert deliver(row['submission_id']) == 'sent'
    smtp.return_value.__enter__.return_value.send_message.assert_called_once()


def test_mail_failure_keeps_submission(setup, monkeypatch):
    app, client = setup
    monkeypatch.setenv('REFORM_EMAIL_ENABLED','true')
    monkeypatch.setenv('REFORM_SMTP_HOST','smtp.example.test')
    monkeypatch.setenv('REFORM_EMAIL_FROM','review@example.test')
    monkeypatch.setattr(smtplib,'SMTP',MagicMock(side_effect=OSError('unavailable')))
    post(client, 'save', action='product', new='1', sku='MAIL-TEST', name='Test product', uom='vnt.', revision='0')
    assert 'submission is saved' in post(client,'submit',revision='1',confirm='yes').text
    with app.app_context(), db() as conn:
        assert conn.execute('SELECT status FROM notification_outbox').fetchone()[0] == 'failed'
        assert conn.execute('SELECT count(*) FROM submissions').fetchone()[0] == 1
