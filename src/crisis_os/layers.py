"""Layer functions: Perception → Verification → World Model → … → Memory.

Deterministic demo spine. LLM is never the numerical engine. mint_permit requires
a HumanDecision (invariant #14).
"""
from __future__ import annotations

from . import db
from .models import HumanDecision, Permit
from .snapshot import build_snapshot, load_parameters, pv, write_world_files


def perception(inbox: list[dict]) -> list[dict]:
    """Observations only — never truth."""
    out = []
    for i, rec in enumerate(inbox):
        oid = f"obs-{i}-{rec.get('source_id')}"
        db.get_db().execute(
            "INSERT OR REPLACE INTO observations VALUES(?,?,?,?,?)",
            (oid, rec.get("source_id"), rec.get("raw_content"), rec.get("observed_at"), "{}"),
        )
        out.append({**rec, "observation_id": oid, "verification_status": "unverified"})
    db.get_db().commit()
    return out


def verification(observations: list[dict], min_sources: int = 2) -> dict | None:
    """Promote only when independent sources meet the threshold."""
    sources = {o.get("source_id") for o in observations}
    status = "verified" if len(sources) >= min_sources else "unverified"
    subject = "bridge:B7"
    rec_id = f"vr-{subject}-{status}"
    db.get_db().execute(
        "INSERT OR REPLACE INTO verification_records VALUES(?,?,?,?,?)",
        (rec_id, subject, status, len(sources), "{}"),
    )
    db.get_db().commit()
    if status != "verified":
        return None
    return {"verified_event_id": "ve-b7-1", "subject": subject, "new_state": "inaccessible"}


def world_model_apply(event: dict, params: dict) -> None:
    if not event:
        return
    rec = pv(params, "chronology", "bridge_B7_corroborated_recorded_at")
    vf = pv(params, "chronology", "bridge_B7_collapse_valid_from")
    db.append_state("state-b7-down", event["subject"], event["new_state"],
                    source_event_id=event["verified_event_id"],
                    valid_from=vf, recorded_at=rec, confidence=0.92)
    db.append_state("state-r14-down", "route:R14", "inaccessible",
                    source_event_id=event["verified_event_id"],
                    valid_from=vf, recorded_at=rec)
    db.deactivate_relationship("route:R14", "bridge:B7", "reachable_from")


def greedy_allocate(available: float, floors: dict[str, float]) -> dict[str, float]:
    total = sum(floors.values())
    if total > available:
        return {z: 0.0 for z in floors}
    out = dict(floors)
    rem = available - total
    # remainder by floor weight
    for z, f in floors.items():
        out[z] += rem * (f / total)
    return out


def check_equity(amounts: dict[str, float], floors: dict[str, float]) -> tuple[bool, list[str]]:
    viol = [f"EQUITY VIOLATION: {z} {amounts.get(z, 0):.0f} < floor {fl:.0f}"
            for z, fl in floors.items() if amounts.get(z, 0) + 1e-6 < fl]
    return (not viol, viol)


def mint_permit(plan: dict, human: HumanDecision, floors: dict[str, float]) -> Permit:
    db.insert_audit_if_new(
        human.actor,
        f"coordinator.{human.action}",
        "plan",
        plan["plan_id"],
        human.decided_at,
        human.model_dump_json(),
    )
    db.get_db().commit()
    if human.action not in ("approve", "modify"):
        raise PermissionError("no human approve/modify → no permit")
    if human.role not in ("logistics_lead", "coordinator", "named_authority"):
        raise PermissionError("role cannot mint this tier")
    proposal_version = plan.get("proposal_version", 1)
    if human.proposal_id != plan["plan_id"] or human.proposal_version != proposal_version:
        raise PermissionError("decision is not bound to this proposal version")
    amounts = dict(plan.get("amounts", {}))
    if human.action == "modify" and human.modifications:
        amounts.update(human.modifications)
    ok, viol = check_equity(amounts, floors)
    if not ok:
        raise PermissionError("; ".join(viol))
    if not human.reason:
        raise PermissionError("MODIFY/APPROVE requires a reason")
    p = Permit(
        permit_id=f"permit-{plan['plan_id']}",
        plan_id=plan["plan_id"],
        status="active",
        authorized_actions=["deliver_water"],
        approved_by=human.actor,
        authorized_route=plan["via"],
    )
    db.get_db().execute(
        "INSERT OR REPLACE INTO permits VALUES(?,?,?,?,?)",
        (p.permit_id, p.plan_id, p.status, p.approved_by, p.model_dump_json()),
    )
    db.get_db().commit()
    return p


def authorize(task: dict, permit: Permit, plan: dict) -> str:
    for dep in plan.get("depends_on", []):
        st = db.current_state(dep)
        if st and st["state"] in ("inaccessible", "critical") and permit.authorized_route == "route:R14":
            permit.status = "revoked"
            return "SUSPENDED"
    if permit.status != "active":
        return "BLOCKED"
    if task.get("action", "deliver_water") not in permit.authorized_actions:
        return "BLOCKED"
    return "IN_PROGRESS"


def run_demo() -> dict:
    """Closed loop using the same three WorldSnapshots the diorama already plays."""
    from .seed import seed_world
    params = load_parameters()
    seed_world(reset=True)
    sphere = pv(params, "humanitarian_standards", "water_l_per_person_day")
    floors = {
        "zone:B": pv(params, "zones", "zone_B_population") * sphere,
        "zone:C": pv(params, "zones", "zone_C_population") * sphere,
    }
    available = pv(params, "supply", "warehouse_W1_staging_l_per_day")
    fair = greedy_allocate(available, floors)
    efficient = {"zone:B": available, "zone:C": 0.0}
    ok_e, viol = check_equity(efficient, floors)
    assert not ok_e, "efficient plan must fail equity"
    ok_f, _ = check_equity(fair, floors)
    assert ok_f
    modify_qty = pv(params, "governance", "human_modify_zone_B_qty_l")
    plan = {
        "plan_id": "plan-1048", "proposal_version": 1, "via": "route:R14",
        "depends_on": ["bridge:B7", "route:R14"],
        "amounts": {"zone:B": modify_qty, "zone:C": floors["zone:C"]},
    }
    d1 = HumanDecision(
        actor="Coordinator Diaz", role="logistics_lead", action="modify",
        reason="partner NGO covering the remainder to Zone B",
        modifications={"zone:B": modify_qty},
        proposal_id="plan-1048", proposal_version=1,
    )
    permit = mint_permit(plan, d1, floors)
    task = {"action": "deliver_water"}
    st = authorize(task, permit, plan)
    assert st == "IN_PROGRESS"

    perception([{"source_id": "responder-3", "raw_content": "Twin Span looks out — B7 may be impassable"}])
    assert verification([{"source_id": "responder-3"}], 2) is None

    obs = [
        {"source_id": "responder-3", "raw_content": "Twin Span looks out"},
        {"source_id": "community-sms", "raw_content": "the north bridge is gone"},
    ]
    perception(obs)
    ev = verification(obs, pv(params, "verification", "corroboration_min_independent_sources"))
    assert ev
    world_model_apply(ev, params)
    st = authorize(task, permit, plan)
    assert st == "SUSPENDED"

    plan2 = {"plan_id": "plan-1052", "proposal_version": 1, "via": "route:R22", "depends_on": ["route:R22"],
             "amounts": plan["amounts"]}
    d2 = HumanDecision(actor="Coordinator Diaz", role="logistics_lead", action="approve",
                       reason="southern reroute confirmed clear",
                       proposal_id="plan-1052", proposal_version=1)
    p2 = mint_permit(plan2, d2, floors)
    st2 = authorize(task, p2, plan2)
    assert st2 == "IN_PROGRESS"

    db.get_db().execute(
        "INSERT OR REPLACE INTO episodes VALUES(?,?,?)",
        ("katrina-nola-2005", pv(params, "chronology", "demo_t0"),
         '{"lesson":"candidate","confidence":"low"}'),
    )
    db.get_db().commit()
    write_world_files()
    return {
        "equity_blocked_efficient": viol[0],
        "fair": fair,
        "truck": ["IN_PROGRESS", "SUSPENDED", "IN_PROGRESS"],
        "snapshots": ["t0", "b7", "reroute"],
    }


if __name__ == "__main__":
    print(run_demo())
