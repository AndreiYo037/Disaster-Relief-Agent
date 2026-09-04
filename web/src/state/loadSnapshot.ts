import type { KeyframeId, SymbolRegistry, WorldSnapshot } from "./types";

const DATA = "/data";

export async function loadRegistry(): Promise<SymbolRegistry> {
  const r = await fetch(`${DATA}/symbol-registry.json`);
  return r.json();
}

export async function loadSnapshot(id: KeyframeId): Promise<WorldSnapshot> {
  try {
    const live = await fetch(`/api/state?keyframe=${id}`);
    if (live.ok) return live.json();
  } catch {
    /* frozen files */
  }
  const r = await fetch(`${DATA}/snapshots/${id}.json`);
  if (!r.ok) throw new Error(`snapshot ${id} missing`);
  return r.json();
}

export async function loadAllSnapshots(): Promise<Record<KeyframeId, WorldSnapshot>> {
  const [t0, b7, reroute] = await Promise.all([
    loadSnapshot("t0"),
    loadSnapshot("b7"),
    loadSnapshot("reroute"),
  ]);
  return { t0, b7, reroute };
}
