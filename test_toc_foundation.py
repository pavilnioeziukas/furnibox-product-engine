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


def test_not_ready_accepts_multiple_simultaneous_reasons(store):
    user = store.create_user("vadove", "safe-password", "production_manager")

    written = store.record_readiness(
        so_reference="s001", business_date=date(2026, 8, 21), actor_id=user.id,
        ready=False,
        reason_codes=["FURNIX_PARTS_MISSING", "SUBCONTRACTOR_FRONTS_MISSING"],
    )

    assert len(written) == 2
    assert {item.payload["reason_code"] for item in written} == {
        "FURNIX_PARTS_MISSING", "SUBCONTRACTOR_FRONTS_MISSING"
    }
    assert all(item.payload["so_reference"] == "S001" for item in written)


def test_repeated_not_ready_reason_does_not_duplicate_active_blocker(store):
    user = store.create_user("vadove", "safe-password", "production_manager")
    values = dict(
        so_reference="S001", business_date=date(2026, 8, 21), actor_id=user.id,
        ready=False, reason_codes=["FURNIX_PARTS_MISSING"],
    )

    assert len(store.record_readiness(**values)) == 1
    assert store.record_readiness(**values) == []
    assert len(store.active_readiness_blockers("S001")) == 1


def test_ready_closes_all_active_reasons_before_confirmation(store):
    user = store.create_user("vadove", "safe-password", "production_manager")
    store.record_readiness(
        so_reference="S001", business_date=date(2026, 8, 21), actor_id=user.id,
        ready=False, reason_codes=["FURNIX_PARTS_MISSING", "COMPONENTS_NOT_FOUND"],
    )

    written = store.record_readiness(
        so_reference="S001", business_date=date(2026, 8, 22), actor_id=user.id,
        ready=True,
    )

    assert [item.event_type for item in written] == [
        "ReadinessBlockerClosed", "ReadinessBlockerClosed", "ReadinessConfirmed"
    ]
    assert store.active_readiness_blockers("S001") == []


def test_other_reason_requires_comment(store):
    user = store.create_user("vadove", "safe-password", "production_manager")

    with pytest.raises(ValueError, match="comment"):
        store.record_readiness(
            so_reference="S001", business_date=date(2026, 8, 21), actor_id=user.id,
            ready=False, reason_codes=["OTHER"],
        )
