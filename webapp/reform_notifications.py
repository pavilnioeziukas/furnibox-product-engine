"""Submission notifications; disabled until the recipient/template are approved."""
import os
import smtplib
import ssl
import json
import urllib.request
import urllib.parse
from email.message import EmailMessage

RECIPIENT = 'edgaras@furnix.lt'


def send_graph(row):
    tenant = urllib.parse.quote(os.environ['REFORM_MS_TENANT_ID'], safe='')
    form = urllib.parse.urlencode({
        'client_id': os.environ['REFORM_MS_CLIENT_ID'],
        'client_secret': os.environ['REFORM_MS_CLIENT_SECRET'],
        'scope': 'https://graph.microsoft.com/.default', 'grant_type': 'client_credentials',
    }).encode()
    with urllib.request.urlopen(f'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token', data=form, timeout=15) as response:
        token = json.load(response)['access_token']
    sender = urllib.parse.quote(os.environ['REFORM_EMAIL_FROM'], safe='')
    data = {'message': {'subject': row['subject'], 'body': {'contentType': 'Text', 'content': row['body']},
                       'toRecipients': [{'emailAddress': {'address': row['recipient']}}]}, 'saveToSentItems': True}
    request = urllib.request.Request(f'https://graph.microsoft.com/v1.0/users/{sender}/sendMail',
        data=json.dumps(data).encode(), headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status != 202:
            raise ValueError('Mail provider did not accept notification.')


def enqueue(conn, sid, owner, created, payload):
    conn.execute('''CREATE TABLE IF NOT EXISTS notification_outbox (
        submission_id INTEGER PRIMARY KEY, recipient TEXT NOT NULL,
        subject TEXT NOT NULL, body TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', sent_at TEXT)''')
    subject = f'Reform: pateikta versija {payload["version"]}'
    base_url = os.getenv('REFORM_PUBLIC_URL', '').rstrip('/')
    lines = [
        'Sveiki,', '', 'Reform įrankyje pateikta visa pakeitimų versija Furnibox peržiūrai.',
        f'Versija: {payload["version"]}', f'Aprašymas: {payload["description"]}',
        f'Pateikimas: #{sid}', f'Pateikė: {owner}', f'Laikas (UTC): {created}',
        f'Pakeistų įrašų: {len(payload["changes"])}', '', 'Pakeisti produktai ir BOM:',
    ]
    for change in payload['changes']:
        item = change['after']
        lines.append(f'- {"Produktas" if change["kind"] == "products" else "BOM"}: {item["sku"]}')
    lines += ['', 'Peržiūrėkite pateikimą įrankio skiltyje „Submitted to Furnibox“.']
    if base_url.startswith('https://'):
        lines += [f'{base_url}/reform/submissions/{sid}/view']
    lines += ['', 'Pakeitimai dar neįgyvendinti Odoo. Reikalinga Furnibox peržiūra.', '', 'Furnibox Product Engine']
    conn.execute('INSERT INTO notification_outbox(submission_id,recipient,subject,body) VALUES (?,?,?,?)',
                 (sid, RECIPIENT, subject, '\n'.join(lines)))


def deliver(sid):
    """Send after submission commit. Failures never roll back the proposal."""
    from webapp.reform_workspace import db, now
    if os.getenv('REFORM_EMAIL_ENABLED') != 'true':
        return 'pending'
    with db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM notification_outbox WHERE submission_id=?', (sid,)).fetchone()
        if not row or row['status'] != 'pending':
            return row['status'] if row else 'missing'
        conn.execute("UPDATE notification_outbox SET status='sending' WHERE submission_id=?", (sid,))
    try:
        if os.getenv('REFORM_EMAIL_PROVIDER') == 'microsoft':
            send_graph(row)
        else:
            send_smtp(row)
        status = 'sent'
    except Exception:
        # A timeout can occur after server acceptance. Do not auto-retry duplicates.
        status = 'failed'
    with db() as conn:
        conn.execute('UPDATE notification_outbox SET status=?,sent_at=? WHERE submission_id=?',
                     (status, now() if status == 'sent' else None, sid))
    return status


def send_smtp(row):
        host, sender = os.environ['REFORM_SMTP_HOST'], os.environ['REFORM_EMAIL_FROM']
        message = EmailMessage()
        message['From'], message['To'], message['Subject'] = sender, row['recipient'], row['subject']
        message.set_content(row['body'])
        with smtplib.SMTP(host, int(os.getenv('REFORM_SMTP_PORT', '587')), timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(os.environ['REFORM_SMTP_USERNAME'], os.environ['REFORM_SMTP_PASSWORD'])
            smtp.send_message(message)
