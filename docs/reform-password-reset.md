# Reform password recovery

The sign-in page links to `/reform/forgot-password`. Recovery sends a single-use,
30-minute link only to the email on a configured `PRODUCT_ENGINE_REFORM_USERS`
account. Responses do not disclose whether an account exists. Requests are limited
to five per address and source IP per 30 minutes. Password changes invalidate all
recovery links and previous sessions. New password hashes live in
`REFORM_STATE_DIR/reform.sqlite3` on the existing persistent volume; keep that volume
when deploying and include it in backups. Removing an account from the environment
configuration still disables it. Existing environment password hashes remain the
initial credentials until an account completes recovery.

## Activation

Recovery is disabled until `REFORM_PASSWORD_RESET_ENABLED=true` is configured.
Set `REFORM_PUBLIC_URL=https://reform-review-reform-review.up.railway.app` (origin,
without `/reform`). Never derive email links from incoming Host headers.

Configure one of the existing mail transports:

* Microsoft Graph: `REFORM_EMAIL_PROVIDER=microsoft`, `REFORM_MS_TENANT_ID`,
  `REFORM_MS_CLIENT_ID`, `REFORM_MS_CLIENT_SECRET`, and `REFORM_EMAIL_FROM`.
* SMTP: `REFORM_EMAIL_PROVIDER=smtp`, `REFORM_SMTP_HOST`, `REFORM_SMTP_PORT`
  (default 587), `REFORM_SMTP_USERNAME`, `REFORM_SMTP_PASSWORD`, and
  `REFORM_EMAIL_FROM`. SMTP requires STARTTLS.

This flag is independent of submission notifications (`REFORM_EMAIL_ENABLED`).
Approve the sender, recipient rule, and following exact email template before
activation. Do not send a real recovery message as a test without approval.

Subject: Reset your Reform workspace password

Hi,

We received a request to reset your Reform workspace password.

{single-use HTTPS reset link}

This link can be used once and expires in 30 minutes.
If you did not request this, ignore this email. Your password remains unchanged.

Furnibox

## Validation

Run `python -m pytest test_reform_passwords.py test_reform_workspace.py`.
After configuring transport, use an approved test recipient to verify delivery and
completion in a browser before inviting Poul to reset his password.

Recovery fails closed on delivery failure and never logs tokens or passwords.
Restrict reset-path access logs at the reverse proxy because the URL contains a
temporary bearer token. Responses set no-store and no-referrer headers.
