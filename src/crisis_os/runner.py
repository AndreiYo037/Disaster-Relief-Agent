"""Demo spine: guaranteed path, no cloud required."""
import json
from .graph import run_all_replay
from .layers import run_demo

if __name__ == "__main__":
    result = run_demo()
    projections = run_all_replay()
    for keyframe, snapshot in projections.items():
        from .snapshot import SNAP_DIR
        (SNAP_DIR / f"{keyframe}.json").write_text(json.dumps(snapshot), encoding="utf-8")
    print("CRISIS OS — demo spine complete")
    for k, v in result.items():
        print(f"  {k}: {v}")
    print(f"  agentic: {sum(len(s['agentic']['verified_incidents']) + len(s['agentic']['unverified_incidents']) for s in projections.values())} incidents projected")
