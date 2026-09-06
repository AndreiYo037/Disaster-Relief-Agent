"""Demo spine: guaranteed path, no cloud required."""
import json
from pathlib import Path

from .graph import run_all_replay
from .layers import run_demo

ROOT = Path(__file__).resolve().parents[2]
AGENTIC_OUT = ROOT / "artifacts" / "agentic"

if __name__ == "__main__":
    result = run_demo()
    projections = run_all_replay()
    AGENTIC_OUT.mkdir(parents=True, exist_ok=True)
    for keyframe, snapshot in projections.items():
        (AGENTIC_OUT / f"{keyframe}.json").write_text(
            json.dumps(snapshot, indent=2), encoding="utf-8"
        )
    print("CRISIS OS — demo spine complete")
    for k, v in result.items():
        print(f"  {k}: {v}")
    print(
        f"  agentic: {sum(len(s['agentic']['verified_incidents']) + len(s['agentic']['unverified_incidents']) for s in projections.values())} incidents projected"
    )
    print(f"  agentic wrote {AGENTIC_OUT} (does not rewrite data/katrina/snapshots)")
