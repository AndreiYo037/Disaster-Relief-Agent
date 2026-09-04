"""Generate frozen WorldSnapshot files + semantic glTF."""
from crisis_os.snapshot import write_world_files

if __name__ == "__main__":
    paths = write_world_files()
    print(f"Wrote {len(paths)} snapshots")
    for p in paths:
        print(" ", p)
