"""Demo spine: guaranteed path, no cloud required."""
from .layers import run_demo

if __name__ == "__main__":
    result = run_demo()
    print("CRISIS OS — demo spine complete")
    for k, v in result.items():
        print(f"  {k}: {v}")
