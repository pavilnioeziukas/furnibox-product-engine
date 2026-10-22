"""Single-use email recovery for explicitly configured Reform accounts."""
import hashlib
import os
import secrets
import time
from urllib.parse import urlsplit

from flask import current_app, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash


def schema(conn):
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS reform_passwords (
            username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, version TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reform_reset_tokens (
            digest TEXT PRIMARY KEY, username TEXT NOT NULL, expires REAL NOT NULL);
    ''')


def credential(conn, username, configured):
    schema(conn)
    row = conn.execute('SELECT * FROM reform_passwords WHERE username=?', (username,)).fetchone()
    original = configured.get('password_hash') if isinstance(configured, dict) else configured
    return (row['password_hash'], row['version']) if row else (original, 'initial')


def enabled():
    return os.getenv('REFORM_PASSWORD_RESET_ENABLED') == 'true'


def forgot():
    from webapp.reform_workspace import db, digest
    message = None
    if request.method == 'POST':
        message = 'If this email has a workspace account, a password reset link will be sent. Check your inbox and spam folder.'
        username = request.form.get('email', '').strip().lower()[:254]
        configured = current_app.config.get('REFORM_USERS', {}).get(username)
        base = os.getenv('REFORM_PUBLIC_URL', '').rstrip('/')
        parsed = urlsplit(base)
        ready = enabled() and parsed.scheme == 'https' and bool(parsed.netloc) and not parsed.query and not parsed.fragment
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        allowed = True
        with db() as conn:
            schema(conn)
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('DELETE FROM reform_reset_tokens WHERE expires<=?', (time.time(),))
            for identity in ('reset-email:' + digest(username), 'reset-ip:' + digest(request.remote_addr or '')):
                row = conn.execute('SELECT * FROM attempts WHERE identity=?', (identity,)).fetchone()
                if row and time.time() - row['started'] < 1800 and row['count'] >= 5:
                    allowed = False
                count = row['count'] + 1 if row and time.time() - row['started'] < 1800 else 1
                conn.execute('INSERT OR REPLACE INTO attempts VALUES (?,?,?)',
                             (identity, count, row['started'] if row and count > 1 else time.time()))
            # Only deliver to the configured address, never arbitrary form input.
            if ready and allowed and isinstance(configured, dict) and configured.get('email', '').lower() == username:
                conn.execute('INSERT INTO reform_reset_tokens VALUES (?,?,?)', (token_hash, username, time.time() + 1800))
            else:
                ready = False
        if ready:
            from webapp.reform_notifications import send_graph, send_smtp
            mail = {'recipient': configured['email'], 'subject': 'Reset your Reform workspace password',
                    'body': 'Hi,\n\nWe received a request to reset your Reform workspace password.\n\n'
                    + base + url_for('reform.reset_password', token=token)
                    + '\n\nThis link can be used once and expires in 30 minutes.\n'
                    'If you did not request this, ignore this email. Your password remains unchanged.\n\nFurnibox'}
            try:
                (send_graph if os.getenv('REFORM_EMAIL_PROVIDER') == 'microsoft' else send_smtp)(mail)
            except Exception:
                current_app.logger.warning('Reform password reset delivery failed')
                with db() as conn:
                    conn.execute('DELETE FROM reform_reset_tokens WHERE digest=?', (token_hash,))
    return render_template('reform_forgot_password.html', message=message, enabled=enabled())


def reset(token):
    from webapp.reform_workspace import db, digest
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    error = None
    valid = False
    with db() as conn:
        schema(conn)
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM reform_reset_tokens WHERE digest=? AND expires>?',
                           (token_hash, time.time())).fetchone()
        valid = bool(enabled() and row and row['username'] in current_app.config.get('REFORM_USERS', {}))
        if valid and request.method == 'POST':
            password = request.form.get('password', '')
            if not 12 <= len(password) <= 256:
                error = 'Use a password between 12 and 256 characters.'
            elif password != request.form.get('confirm_password', ''):
                error = 'The passwords do not match.'
            else:
                username = row['username']
                conn.execute('INSERT OR REPLACE INTO reform_passwords VALUES (?,?,?)',
                             (username, generate_password_hash(password), secrets.token_hex(16)))
                conn.execute('DELETE FROM reform_reset_tokens WHERE username=?', (username,))
                conn.execute('DELETE FROM attempts WHERE identity=?', (digest(username),))
                session.clear()
                return redirect(url_for('reform.login', password_reset='1'))
    response = current_app.make_response(render_template('reform_reset_password.html', valid=valid, error=error))
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response
