"""Seed SQLite from the Katrina catalog. B7 starts uncertain (bitemporal)."""
from __future__ import annotations

from . import db
from .catalog import BASE_STATES, ENTITIES_SPEC, RELATIONSHIPS
from .snapshot import load_parameters, pv


def seed_world(reset: bool = True) -> None:
    params = load_parameters()
    if reset:
        db.reset_db()
    t0 = pv(params, "chronology", "demo_t0")
    b7_from = pv(params, "chronology", "bridge_B7_collapse_valid_from")
    for spec in ENTITIES_SPEC:
        db.upsert_entity(
            spec["entity_id"], spec["type"], spec["name"],
            geometry={"lon": spec["lon"], "lat": spec["lat"]},
            attributes={"synthetic": spec.get("synthetic", False)},
            aliases=spec.get("aliases", []),
        )
    for a, b, t in RELATIONSHIPS:
        db.add_relationship(a, b, t)
    for eid, st in BASE_STATES.items():
        vf = b7_from if eid == "bridge:B7" else t0
        db.append_state(f"seed-{eid}", eid, st, source_event_id="seed",
                        valid_from=vf, recorded_at=t0,
                        label="uncertain" if st == "uncertain" else "known",
                        confidence=0.7 if st == "uncertain" else 1.0)
    print(f"Seeded {len(ENTITIES_SPEC)} entities")


if __name__ == "__main__":
    seed_world()
