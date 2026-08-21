from datetime import date

import pytest
from webapp.toc_foundation import DecisionEvent, TocStore


@pytest.fixture
def store(tmp_path):
    value = TocStore(f"sqlite:///{(tmp_path / 'toc.db').as_posix()}")
    value.create_schema()
    return value


def test_individual_user_authentication_and_role(store):
    user = store.create_user("Vadove", "safe-password", "production_manager")

    authenticated = store.authenticate("vadove", "safe-password")

    assert authenticated.id == user.id
    assert authenticated.role == "production_manager"
    assert store.authenticate("vadove", "wrong") is None


def test_event_has_actor_business_date_rule_and_payload(store):
    user = store.create_user("vadove", "safe-password", "production_manager")

    item = store.append_event(
        event_type="DailyAssemblyCapacityConfirmed",
        business_date=date(2026, 8, 21),
        actor_id=user.id,
        rule_version="capacity-v1",
        payload={"employee_count": 4, "capacity_hours": 32},
    )

    assert item.actor_id == user.id
    assert item.organization_scope == "furnibox"
    assert store.list_events(date(2026, 8, 21))[0].payload["capacity_hours"] == 32


def test_decision_event_cannot_be_updated_or_deleted(store):
    user = store.create_user("vadove", "safe-password", "production_manager")
    item = store.append_event(
        event_type="ReadinessCheckStarted",
        business_date=date(2026, 8, 21), actor_id=user.id,
        rule_version="readiness-v1", payload={},
    )

    with store.sessions.begin() as db:
        persisted = db.get(DecisionEvent, item.id)
        persisted.payload = {"changed": True}
        with pytest.raises(ValueError, match="immutable"):
            db.flush()

    with store.sessions.begin() as db:
        persisted = db.get(DecisionEvent, item.id)
        db.delete(persisted)
        with pytest.raises(ValueError, match="immutable"):
            db.flush()


def test_correction_references_original_event(store):
    user = store.create_user("vadove", "safe-password", "production_manager")
    original = store.append_event(
        event_type="ReadinessConfirmed", business_date=date(2026, 8, 21),
        actor_id=user.id, rule_version="readiness-v1", payload={"so": "S001"},
    )
    correction = store.append_event(
        event_type="ReadinessRevokedBeforeStart", business_date=date(2026, 8, 21),
        actor_id=user.id, rule_version="readiness-v1",
        payload={"so": "S001", "reason": "Defective component"},
        corrects_event_id=original.id,
    )

    assert correction.corrects_event_id == original.id
