"""HTTP: WorldSnapshot API + the 3D diorama static files."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .config import PORT
from .snapshot import SNAP_DIR, WEB_PUBLIC, build_snapshot, load_parameters, write_world_files

WEB = Path(__file__).resolve().parents[2] / "web"
MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".gltf": "model/gltf+json",
    ".bin": "application/octet-stream",
    ".png": "image/png",
}


def snapshot_for(keyframe: str | None = None, ts: str | None = None) -> dict:
    params = load_parameters()
    kf = keyframe
    if ts and not kf:
        t0 = params["chronology"]["demo_t0"]["value"]
        rec = params["chronology"]["bridge_B7_corroborated_recorded_at"]["value"]
        if ts <= t0:
            kf = "t0"
        elif ts < rec:
            kf = "b7"
        else:
            kf = "b7"
    kf = kf or "t0"
    if kf not in ("t0", "b7", "reroute"):
        kf = "t0"
    path = SNAP_DIR / f"{kf}.json"
    base = json.loads(path.read_text(encoding="utf-8")) if path.exists() else build_snapshot(params, kf)
    try:
        from .agentic import replay_projection
        from .graph import run_replay
        projected = replay_projection(run_replay(kf))
        projected.update({key: value for key, value in base.items() if key not in projected})
        return projected
    except Exception as exc:
        print(f"[agentic] projection unavailable: {exc}")
        return base


def resolve_static(path: str) -> Path | None:
    rel = unquote(path.split("?", 1)[0])
    if rel in ("/", "/index.html"):
        p = WEB / "index.html"
        return p if p.is_file() else None
    candidates = [
        WEB / rel.lstrip("/"),
        WEB / "src" / Path(rel).name if rel.startswith("/src/") else None,
        WEB_PUBLIC / rel.lstrip("/"),
        WEB_PUBLIC / "data" / Path(rel).name if rel.startswith("/data/") and not rel.startswith("/data/snapshots") else None,
        WEB_PUBLIC / rel.lstrip("/"),
    ]
    if rel.startswith("/data/snapshots/"):
        candidates.insert(0, WEB_PUBLIC / rel.lstrip("/"))
        candidates.insert(0, SNAP_DIR / Path(rel).name)
    if rel.startswith("/assets/"):
        candidates.insert(0, WEB_PUBLIC / rel.lstrip("/"))
    for p in candidates:
        if p and p.is_file():
            return p
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print("[http]", args[0] if args else fmt)

    def _json(self, obj: object, code: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ("/api/state", "/api/world-state"):
            self._json(snapshot_for((q.get("keyframe") or [None])[0]))
            return
        if u.path in ("/api/state_at", "/api/world-state/population"):
            ts = (q.get("ts") or q.get("timestamp") or [None])[0]
            kf = (q.get("keyframe") or [None])[0]
            snap = snapshot_for(kf, ts)
            self._json(snap["population"] if u.path.endswith("population") else snap)
            return
        if u.path == "/api/health":
            self._json({"ok": True})
            return
        p = resolve_static(u.path)
        if p:
            data = p.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", MIME.get(p.suffix, "application/octet-stream"))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._json({"error": "not found", "path": u.path}, 404)


def main() -> None:
    if not (SNAP_DIR / "t0.json").exists():
        write_world_files()
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Crisis OS  http://127.0.0.1:{PORT}/", flush=True)
    print(f"           http://127.0.0.1:{PORT}/api/state?keyframe=t0", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
