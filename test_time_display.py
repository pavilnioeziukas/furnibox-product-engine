from datetime import datetime, timezone
import pytest
from webapp.time_display import cet_time

@pytest.mark.parametrize('value,expected', [
    ('2026-09-28T09:48:00+00:00', '2026-09-28 10:48 CET'),
    ('2026-01-15T09:48:00Z', '2026-01-15 10:48 CET'),
    ('2026-12-31T23:30:00+00:00', '2027-01-01 00:30 CET'),
    ('2026-09-28T12:48:00+03:00', '2026-09-28 10:48 CET'),
    ('2026-09-28 09:48:00', '2026-09-28 10:48 CET'),
    (datetime(2026,9,28,9,48,tzinfo=timezone.utc), '2026-09-28 10:48 CET'),
    (None, ''), ('', ''), ('unknown', 'unknown'),
])
def test_cet_display(value, expected):
    assert cet_time(value) == expected
