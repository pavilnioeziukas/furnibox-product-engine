from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, String, create_engine, event, select
from sqlalchemy.orm import DeclarativeBase, Mapped, joinedload, mapped_column, relationship, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash


ROLES = {"production_manager", "management", "administrator", "system_reader"}
EVENT_TYPES = {
    "DailyAssemblyCapacityConfirmed",
    "ReadinessCheckStarted",
    "ReadinessConfirmed",
    "ReadinessRevokedBeforeStart",
    "ReadinessBlockerOpened",
    "ReadinessBlockerClosed",
    "DailyPriorityPlanGenerated",
    "DailyPriorityPlanApproved",
    "PriorityOverrideRecorded",
}
READINESS_BLOCKER_REASONS = {
    "FURNIX_PARTS_MISSING": "Trūksta Furnix detalių",
    "SUBCONTRACTOR_FRONTS_MISSING": "Neatvežti subrangovo fasadai",
    "SUBCONTRACTOR_DRAWERS_MISSING": "Neatvežti subrangovo stalčiai",
    "OTHER_PURCHASED_COMPONENTS_MISSING": "Trūksta kitų perkamų komponentų",
    "COMPONENTS_NOT_FOUND": "Komponentų nepavyksta fiziškai rasti",
    "COMPONENT_ORDER_UNKNOWN": "Neaišku, kuriam užsakymui skirti komponentai",
    "OTHER": "Kita priežastis",
}


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "toc_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    events: Mapped[list["DecisionEvent"]] = relationship(back_populates="actor")


class DecisionEvent(Base):
    __tablename__ = "decision_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    business_date: Mapped[date] = mapped_column(Date, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("toc_users.id"), index=True)
    organization_scope: Mapped[str] = mapped_column(String(80), default="furnibox")
    rule_version: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    corrects_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("decision_events.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[User] = relationship(back_populates="events")


def _deny_event_mutation(*_args: Any, **_kwargs: Any) -> None:
    raise ValueError("Decision events are immutable; record a correction event instead.")


event.listen(DecisionEvent, "before_update", _deny_event_mutation)
event.listen(DecisionEvent, "before_delete", _deny_event_mutation)


class TocStore:
    def __init__(self, database_url: str):
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def has_users(self) -> bool:
        with self.sessions() as db:
            return db.scalar(select(User.id).limit(1)) is not None

    def create_user(self, username: str, password: str, role: str) -> User:
        username = username.strip().lower()
        if not username or not password:
            raise ValueError("Username and password are required.")
        if role not in ROLES:
            raise ValueError(f"Unknown role: {role}")
        with self.sessions.begin() as db:
            if db.scalar(select(User).where(User.username == username)):
                raise ValueError("User already exists.")
            user = User(
                id=str(uuid.uuid4()), username=username,
                password_hash=generate_password_hash(password), role=role,
                active=True, created_at=datetime.now(timezone.utc),
            )
            db.add(user)
        return user

    def bootstrap_admin(self, username: str, password: str) -> User | None:
        if not username or not password:
            return None
        with self.sessions() as db:
            if db.scalar(select(User.id).limit(1)):
                return None
        return self.create_user(username, password, "administrator")

    def authenticate(self, username: str, password: str) -> User | None:
        with self.sessions() as db:
            user = db.scalar(select(User).where(User.username == username.strip().lower()))
            if not user or not user.active or not check_password_hash(user.password_hash, password):
                return None
            db.expunge(user)
            return user

    def get_user(self, user_id: str) -> User | None:
        with self.sessions() as db:
            user = db.get(User, user_id)
            if user and user.active:
                db.expunge(user)
                return user
            return None

    def append_event(
        self, *, event_type: str, business_date: date, actor_id: str,
        rule_version: str, payload: dict[str, Any],
        corrects_event_id: str | None = None,
    ) -> DecisionEvent:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Unknown event type: {event_type}")
        if not rule_version:
            raise ValueError("Rule version is required.")
        now = datetime.now(timezone.utc)
        with self.sessions.begin() as db:
            actor = db.get(User, actor_id)
            if not actor or not actor.active:
                raise ValueError("Active actor is required.")
            if corrects_event_id and not db.get(DecisionEvent, corrects_event_id):
                raise ValueError("Corrected event does not exist.")
            item = DecisionEvent(
                id=str(uuid.uuid4()), event_type=event_type,
                business_date=business_date, occurred_at=now, actor_id=actor_id,
                organization_scope="furnibox", rule_version=rule_version,
                payload=dict(payload), corrects_event_id=corrects_event_id, created_at=now,
            )
            db.add(item)
        return item

    def active_readiness_blockers(self, so_reference: str) -> list[DecisionEvent]:
        events = self.list_events()
        closed_ids = {
            item.payload.get("blocker_id")
            for item in events
            if item.event_type == "ReadinessBlockerClosed"
        }
        return [
            item for item in events
            if item.event_type == "ReadinessBlockerOpened"
            and item.payload.get("so_reference") == so_reference
            and item.id not in closed_ids
        ]

    def readiness_states(self) -> dict[str, dict[str, Any]]:
        states: dict[str, dict[str, Any]] = {}
        blocker_to_so: dict[str, str] = {}
        for item in self.list_events():
            so_reference = str(item.payload.get("so_reference") or "")
            if item.event_type == "ReadinessBlockerOpened" and so_reference:
                state = states.setdefault(so_reference, {"status": "unchecked", "reasons": {}})
                state["reasons"][item.id] = item.payload.get("reason_code")
                state["status"] = "not_ready"
                blocker_to_so[item.id] = so_reference
            elif item.event_type == "ReadinessBlockerClosed":
                blocker_id = str(item.payload.get("blocker_id") or "")
                blocked_so = blocker_to_so.get(blocker_id, so_reference)
                state = states.get(blocked_so)
                if state:
                    state["reasons"].pop(blocker_id, None)
                    state["status"] = "not_ready" if state["reasons"] else "unchecked"
            elif item.event_type == "ReadinessConfirmed" and so_reference:
                states[so_reference] = {"status": "ready", "reasons": {}}
        return states

    def record_readiness(
        self, *, so_reference: str, business_date: date, actor_id: str,
        ready: bool, reason_codes: list[str] | None = None, comment: str = "",
    ) -> list[DecisionEvent]:
        so_reference = so_reference.strip().upper()
        if not so_reference:
            raise ValueError("SO reference is required.")
        reasons = list(dict.fromkeys(reason_codes or []))
        unknown = set(reasons) - READINESS_BLOCKER_REASONS.keys()
        if unknown:
            raise ValueError(f"Unknown readiness reason: {sorted(unknown)[0]}")
        if not ready and not reasons:
            raise ValueError("At least one NOT READY reason is required.")
        if "OTHER" in reasons and not comment.strip():
            raise ValueError("A comment is required for OTHER.")

        written: list[DecisionEvent] = []
        active = self.active_readiness_blockers(so_reference)
        if ready:
            for blocker in active:
                written.append(self.append_event(
                    event_type="ReadinessBlockerClosed", business_date=business_date,
                    actor_id=actor_id, rule_version="readiness-v1",
                    payload={"so_reference": so_reference, "blocker_id": blocker.id},
                ))
            written.append(self.append_event(
                event_type="ReadinessConfirmed", business_date=business_date,
                actor_id=actor_id, rule_version="readiness-v1",
                payload={"so_reference": so_reference},
            ))
            return written

        active_reasons = {item.payload.get("reason_code") for item in active}
        for reason_code in reasons:
            if reason_code in active_reasons:
                continue
            written.append(self.append_event(
                event_type="ReadinessBlockerOpened", business_date=business_date,
                actor_id=actor_id, rule_version="readiness-v1",
                payload={
                    "so_reference": so_reference,
                    "reason_code": reason_code,
                    "comment": comment.strip() if reason_code == "OTHER" else "",
                },
            ))
        return written

    def list_events(self, business_date: date | None = None) -> list[DecisionEvent]:
        with self.sessions() as db:
            query = (
                select(DecisionEvent)
                .options(joinedload(DecisionEvent.actor))
                .order_by(DecisionEvent.occurred_at, DecisionEvent.id)
            )
            if business_date:
                query = query.where(DecisionEvent.business_date == business_date)
            return list(db.scalars(query))
