"""Stage pilot decision audit. Contains no Odoo mutation calls."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def decision_scope(data, review, case):
    if case not in ("led", "bom"):
        raise ValueError("Nežinomas piloto atvejis.")
    classification = review["led_classification" if case == "led" else "new_bom_classification"]
    target = classification.get("proposed_bom_id")
    boms = [b for b in data["boms"] if b["id"] in classification["bom_ids"]]
    bom_ids = {b["id"] for b in boms}
    lines = [l for l in data["lines"] if l["bom_id"][0] in bom_ids]
    template_ids = {b["product_tmpl_id"][0] for b in boms if b.get("product_tmpl_id")}
    product_ids = {l["product_id"][0] for l in lines if l.get("product_id")}
    if case == "led":
        product_ids.update(p["id"] for p in data["products"] if p.get("default_code") in
                           (review["led"]["old"], review["led"]["new"], review["led"]["target"]))
    products = [p for p in data["products"] if p["id"] in product_ids or
                (p.get("product_tmpl_id") and p["product_tmpl_id"][0] in template_ids)]
    change = review["led"] if case == "led" else review["new_bom"]
    blockers = []
    if not target:
        blockers.append("Neparinktas vienareikšmis tikslinis BOM.")
    if case == "led":
        old_ids = {p["id"] for p in products if p.get("default_code") == change["old"]}
        old_lines = [l for l in lines if l["bom_id"][0] == target and l["product_id"][0] in old_ids]
        new = review["new_components"]
        if len(old_lines) != 1 or len(new) != 1:
            blockers.append("Komponento pakeitimas nėra vienareikšmis.")
        else:
            unit = old_lines[0].get("product_uom_id")
            new_card = next((p for p in products if p["id"] == new[0]["id"]), {})
            if old_lines[0].get("product_qty") != change["qty"]:
                blockers.append("Esamas komponento kiekis nesutampa su Reform pakeitimo kiekiu.")
            if not unit or not new_card.get("uom_id") or unit[0] != new_card["uom_id"][0]:
                blockers.append("Nesutampa komponentų matavimo vienetai.")
    else:
        blockers.append("Šis skirtumų eksportas nepateikia visos BOM struktūros; turinio patvirtinimas blokuojamas.")
    payload = dict(rule_version="0.3", case=case, source=review["source"], target_bom_id=target,
                   change=change, boms=sorted(boms, key=lambda r: r["id"]),
                   lines=sorted(lines, key=lambda r: r["id"]),
                   products=sorted(products, key=lambda r: r["id"]), blockers=blockers,
                   environment="stage", execution_enabled=False)
    digest = hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()
    return dict(case=case, fingerprint=digest, payload=payload, selectable=bool(target),
                content_ready=not blockers, blockers=blockers)


class DecisionLog:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS pilot_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, case_key TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, action TEXT NOT NULL,
                    actor_id TEXT NOT NULL, actor_name TEXT NOT NULL, role TEXT NOT NULL,
                    occurred_at TEXT NOT NULL, note TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS pilot_decisions_no_update
                BEFORE UPDATE ON pilot_decisions BEGIN SELECT RAISE(ABORT,'Immutable audit'); END;
                CREATE TRIGGER IF NOT EXISTS pilot_decisions_no_delete
                BEFORE DELETE ON pilot_decisions BEGIN SELECT RAISE(ABORT,'Immutable audit'); END;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def history(self, case):
        with self.connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM pilot_decisions WHERE case_key=? ORDER BY id", (case,))]


    def observe(self, scope):
        """Persist snapshot changes so prior approvals cannot silently revive after a revert."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            last = db.execute("SELECT fingerprint FROM pilot_decisions WHERE case_key=? ORDER BY id DESC LIMIT 1",
                              (scope["case"],)).fetchone()
            if last and last["fingerprint"] == scope["fingerprint"]:
                return
            db.execute("""INSERT INTO pilot_decisions
                (case_key,fingerprint,action,actor_id,actor_name,role,occurred_at,note,payload)
                VALUES (?,?,?,?,?,?,?,?,?)""", (
                scope["case"], scope["fingerprint"], "observe", "stage-reader", "Stage duomenų patikra",
                "system_reader", datetime.now(timezone.utc).isoformat(),
                "Nuskaityta nauja susijusių duomenų momentinė kopija.", canonical(scope["payload"])))
            db.commit()

    @staticmethod
    def state(events, fingerprint):
        current = [e for e in events if e["fingerprint"] == fingerprint]
        state = dict(selection=None, content=None, release=None, rejected=False)
        # A changed snapshot invalidates the chain, even if its old fingerprint later returns.
        if events:
            last_other = max((e["id"] for e in events if e["fingerprint"] != fingerprint), default=0)
            current = [e for e in current if e["id"] > last_other]
        for event in current:
            if event["action"] == "select":
                state = dict(selection=event, content=None, release=None, rejected=False)
            elif event["action"] == "reject":
                state = dict(selection=None, content=None, release=None, rejected=True)
            elif event["action"] == "content" and state["selection"]:
                state["content"], state["release"] = event, None
            elif event["action"] == "release" and state["content"]:
                state["release"] = event
        state["stale_history"] = bool(any(e["fingerprint"] != fingerprint for e in events) and not state["selection"])
        return state

    def record(self, scope, expected, action, actor, note, content_ids=(), release_ids=()):
        if expected != scope["fingerprint"]:
            raise ValueError("Odoo duomenys pasikeitė. Atnaujinkite peržiūrą ir sprendimą priimkite iš naujo.")
        if not actor or not actor.get("id") or actor.get("role") not in (
                "administrator", "management", "production_manager"):
            raise PermissionError("Sprendimui reikia vardinės paskyros ir peržiūros teisių.")
        if action not in ("select", "content", "release", "reject"):
            raise ValueError("Nežinomas sprendimas.")
        if len(note) > 2000:
            raise ValueError("Pastaba viršija 2000 ženklų.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            events = [dict(r) for r in db.execute(
                "SELECT * FROM pilot_decisions WHERE case_key=? ORDER BY id", (scope["case"],))]
            state = self.state(events, scope["fingerprint"])
            if action == "select" and not scope["selectable"]:
                raise ValueError("BOM atranka neišspręsta.")
            if action in ("content", "release") and not scope["content_ready"]:
                raise ValueError("Turinio apimtis neparengta: " + "; ".join(scope["blockers"]))
            if action in ("content", "release") and actor["username"].strip().lower() in ("admin", "administrator"):
                raise PermissionError("Bendra admin paskyra negali pakeisti vardinio turinio ar galutinio leidimo tvirtintojo.")
            if action == "content":
                if actor["id"] not in content_ids:
                    raise PermissionError("Ši paskyra nepaskirta turinio tvirtintoja. Negalima tvirtinti Tamaros vardu.")
                if not state["selection"]:
                    raise ValueError("Pirmiausia užfiksuokite BOM ir pakeitimo pasirinkimą.")
            if action == "release":
                if actor["id"] not in release_ids:
                    raise PermissionError("Ši paskyra nepaskirta galutinio leidimo tvirtintoja.")
                if not state["content"]:
                    raise ValueError("Pirmiausia reikia turinio patvirtinimo.")
                if actor["id"] == state["content"]["actor_id"]:
                    raise PermissionError("Galutinį leidimą turi suteikti kitas asmuo.")
            if action == "reject" and not note.strip():
                raise ValueError("Atmetimui reikia priežasties.")
            db.execute("""INSERT INTO pilot_decisions
                (case_key,fingerprint,action,actor_id,actor_name,role,occurred_at,note,payload)
                VALUES (?,?,?,?,?,?,?,?,?)""", (
                scope["case"], scope["fingerprint"], action, actor["id"], actor["username"],
                actor["role"], datetime.now(timezone.utc).isoformat(), note.strip(),
                canonical(scope["payload"])))
            db.commit()
