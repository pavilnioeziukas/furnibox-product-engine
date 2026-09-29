"""User-facing timestamps use fixed CET (UTC+1); stored timestamps stay UTC."""
from datetime import datetime, timedelta, timezone

CET = timezone(timedelta(hours=1), 'CET')


def cet_time(value):
    if not value:
        return ''
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return str(value)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(CET).strftime('%Y-%m-%d %H:%M CET')
