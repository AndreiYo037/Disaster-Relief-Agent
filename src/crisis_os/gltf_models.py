"""Procedural semantic glTF + ground-footprint solids. One silhouette per type.

Each type is an assembly of boxes (metres: +X east, +Y up, +Z north). The same
parts are written as (1) a merged-triangle glTF and (2) lon/lat extruded rings
for the CDN diorama, which cannot rely on ScenegraphLayer.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

# name -> (r,g,b)
COLORS: dict[str, tuple[float, float, float]] = {
    "bridge": (0.55, 0.58, 0.62), "bridge.failed": (0.72, 0.22, 0.20),
    "hospital": (0.92, 0.93, 0.96), "clinic": (0.82, 0.88, 0.94),
    "shelter": (0.80, 0.72, 0.52), "school": (0.70, 0.66, 0.54),
    "power": (0.92, 0.74, 0.18), "water": (0.22, 0.52, 0.82), "pump": (0.32, 0.48, 0.52),
    "breach": (0.48, 0.42, 0.36), "breach.open": (0.78, 0.28, 0.16),
    "port": (0.50, 0.52, 0.46), "airport": (0.62, 0.64, 0.68), "comm": (0.55, 0.60, 0.72),
    "gauge": (0.18, 0.72, 0.86), "warehouse": (0.55, 0.46, 0.34), "vehicle": (0.12, 0.42, 0.82),
    "personnel": (0.28, 0.55, 0.32), "food": (0.78, 0.55, 0.18), "medicine": (0.86, 0.34, 0.40),
    "fuel": (0.38, 0.38, 0.32), "camp": (0.68, 0.58, 0.38), "landslide": (0.48, 0.36, 0.24),
}

# Far-field unique symbols (every mesh type — no shared glyphs)
SYMBOLS: dict[str, str] = {
    "bridge": "⊓", "bridge.failed": "✕",
    "hospital": "✚", "clinic": "†",
    "shelter": "⌂", "school": "▣",
    "power": "⚡", "water": "◉", "pump": "◎",
    "breach": "▽", "breach.open": "▼",
    "port": "⚓", "airport": "✈", "comm": "⌖",
    "gauge": "▮", "warehouse": "▦", "vehicle": "▸",
    "personnel": "☰", "food": "▤", "medicine": "⊕",
    "fuel": "⬤", "camp": "△", "landslide": "◢",
}

# UI grouping for the diorama legend and label plates
CATEGORIES: dict[str, str] = {
    "bridge": "transport", "route": "transport", "route_segment": "transport",
    "road": "transport", "port": "transport", "airport": "transport", "vehicle": "transport",
    "hospital": "health", "clinic": "health", "medicine": "health",
    "shelter": "humanitarian", "school": "humanitarian", "camp": "humanitarian",
    "personnel": "humanitarian", "zone": "humanitarian",
    "power": "utilities", "water": "utilities", "pump": "utilities",
    "comm": "utilities", "gauge": "utilities",
    "breach": "hazard", "flood": "hazard", "cyclone": "hazard",
    "fire": "hazard", "landslide": "hazard",
    "warehouse": "supply", "food": "supply", "fuel": "supply",
    "region": "geography", "district": "geography", "settlement": "geography",
    "hazard_area": "geography", "operational_area": "geography", "service_area": "geography",
}

NONMESH_SYMBOLS: dict[str, str] = {
    "zone": "○", "route": "═", "road": "─",
}

# parts: list of (cx, cy, cz, sx, sy, sz) — centre and size in metres
PARTS: dict[str, list[tuple[float, float, float, float, float, float]]] = {
    # Twin Span schematic: thin deck, parapets, T-piers, approach ramps
    "bridge": [
        (0, 16.0, 0, 260, 2.4, 7.0),       # roadway
        (0, 17.7, -3.9, 260, 1.5, 0.7),    # south parapet
        (0, 17.7, 3.9, 260, 1.5, 0.7),     # north parapet
        (-100, 8.0, 0, 3.4, 16.0, 3.4),    # pier columns
        (-50, 8.0, 0, 3.4, 16.0, 3.4),
        (0, 8.0, 0, 3.4, 16.0, 3.4),
        (50, 8.0, 0, 3.4, 16.0, 3.4),
        (100, 8.0, 0, 3.4, 16.0, 3.4),
        (-100, 15.5, 0, 11.0, 1.8, 9.0),   # T-caps
        (-50, 15.5, 0, 11.0, 1.8, 9.0),
        (0, 15.5, 0, 11.0, 1.8, 9.0),
        (50, 15.5, 0, 11.0, 1.8, 9.0),
        (100, 15.5, 0, 11.0, 1.8, 9.0),
        (-142, 9.0, 0, 28.0, 2.0, 7.0),    # west approach
        (142, 9.0, 0, 28.0, 2.0, 7.0),     # east approach
    ],
    "bridge.failed": [
        (-72, 7.5, 5.0, 108, 2.4, 7.0),    # west deck dropped and yawed
        (-72, 9.0, 1.2, 108, 1.4, 0.7),
        (-72, 9.0, 8.6, 108, 1.4, 0.7),
        (78, 2.8, -11.0, 96, 2.4, 7.0),    # east deck in the water
        (78, 4.0, -14.4, 96, 1.2, 0.7),
        (-100, 8.0, 0, 3.4, 16.0, 3.4),
        (-100, 15.5, 0, 11.0, 1.8, 9.0),
        (-50, 5.5, 3.0, 3.4, 11.0, 3.4),   # leaning pier
        (0, 3.0, 0, 4.5, 6.0, 4.5),        # snapped pier
        (50, 7.0, -3.0, 3.4, 14.0, 3.4),
        (50, 13.5, -3.0, 11.0, 1.8, 9.0),
        (100, 8.0, 0, 3.4, 16.0, 3.4),
        (100, 15.5, 0, 11.0, 1.8, 9.0),
        (6, 1.6, -5.0, 24.0, 2.2, 11.0),   # debris
    ],
    # Cruciform + roof mast
    "hospital": [
        (0, 14, 0, 42, 28, 14),
        (0, 14, 0, 14, 28, 42),
        (0, 32, 0, 3, 12, 3),
    ],
    "clinic": [
        (0, 7, 0, 18, 14, 8),
        (0, 7, 0, 8, 14, 18),
    ],
    "shelter": [
        (0, 8, 0, 52, 16, 22),      # span roof mass
        (0, 18, 0, 56, 3, 26),      # roof slab
    ],
    "school": [
        (0, 9, 0, 28, 18, 28),
        (-8, 5, -8, 8, 10, 8),      # courtyard bite as lower inner (visual U via extra wing)
        (10, 9, 0, 8, 18, 22),
    ],
    "power": [
        (0, 6, 0, 18, 12, 18),      # switchyard
        (0, 28, 0, 6, 36, 6),       # stack
        (8, 10, 8, 4, 8, 4),
    ],
    "water": [
        (0, 8, 0, 22, 16, 22),      # tank
        (12, 4, 0, 10, 8, 10),      # basin
    ],
    "pump": [
        (0, 5, 0, 14, 10, 12),
        (10, 3, 0, 12, 4, 6),       # outfall
    ],
    "breach": [
        (0, 5, 0, 36, 10, 4),       # wall
        (0, 5, 0, 8, 6, 6),         # notch block
    ],
    "breach.open": [
        (-12, 5, 0, 14, 10, 4),
        (12, 5, 0, 14, 10, 4),      # gap in the middle
    ],
    "port": [
        (0, 3, 0, 55, 6, 14),       # quay
        (10, 14, 0, 4, 22, 4),      # crane mast
        (10, 22, 8, 18, 3, 4),      # crane jib
    ],
    "airport": [
        (0, 1.5, 0, 80, 3, 10),     # runway
        (20, 10, 6, 6, 20, 6),      # tower
    ],
    "comm": [
        (0, 3, 0, 8, 6, 8),
        (0, 22, 0, 2.5, 36, 2.5),   # mast
        (0, 38, 0, 8, 2, 8),        # dishes
    ],
    "gauge": [
        (0, 9, 0, 1.6, 18, 1.6),
        (0, 1, 0, 4, 2, 4),
    ],
    "warehouse": [
        (0, 8, 0, 48, 16, 28),
        (0, 17, 0, 50, 2, 30),
    ],
    "vehicle": [
        (0, 2.4, 0, 14, 4.2, 5.5),  # tanker body
        (-6, 2.0, 0, 4, 3.2, 5.2),  # cab
        (5, 4.8, 0, 3, 2, 3),       # tank hump
    ],
    "personnel": [
        (-4, 2, -3, 5, 4, 5),
        (4, 2, 3, 5, 4, 5),
        (0, 2.5, 0, 6, 5, 4),
    ],
    "food": [
        (0, 3, 0, 8, 6, 8),
        (0, 8, 0, 7, 5, 7),
        (0, 12, 0, 6, 4, 6),
    ],
    "medicine": [
        (0, 4, 0, 16, 8, 10),
        (0, 10, 0, 18, 3, 12),      # tent ridge
    ],
    "fuel": [
        (0, 10, 0, 12, 20, 12),     # cylinder approximated as tall box
        (8, 4, 0, 8, 8, 8),
    ],
    "camp": [
        (-6, 3, -4, 7, 6, 7),
        (6, 3, 4, 7, 6, 7),
        (0, 2.5, 6, 6, 5, 6),
    ],
    "landslide": [
        (0, 2, 0, 36, 4, 10),
        (8, 3, -6, 16, 5, 8),
    ],
}


def _add_box(verts: list[float], indices: list[int],
             cx: float, cy: float, cz: float, sx: float, sy: float, sz: float) -> None:
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    base = len(verts) // 3
    for dy in (-hy, hy):
        for dz in (-hz, hz):
            for dx in (-hx, hx):
                verts.extend([cx + dx, cy + dy, cz + dz])
    # winding for +Y-up
    faces = [
        0, 1, 3, 0, 3, 2,
        4, 6, 7, 4, 7, 5,
        0, 4, 5, 0, 5, 1,
        2, 3, 7, 2, 7, 6,
        0, 2, 6, 0, 6, 4,
        1, 5, 7, 1, 7, 3,
    ]
    indices.extend(base + i for i in faces)


def write_gltf(path: Path, name: str) -> None:
    parts = PARTS.get(name) or [(0, 5, 0, 10, 10, 10)]
    r, g, b = COLORS.get(name, (0.6, 0.6, 0.6))
    verts: list[float] = []
    indices: list[int] = []
    for cx, cy, cz, sx, sy, sz in parts:
        _add_box(verts, indices, cx, cy, cz, sx, sy, sz)
    nvert = len(verts) // 3
    vmin = [min(verts[i::3]) for i in range(3)]
    vmax = [max(verts[i::3]) for i in range(3)]
    vbytes = struct.pack("<" + "f" * len(verts), *verts)
    ibytes = struct.pack("<" + "H" * len(indices), *indices)
    pad = (4 - (len(vbytes) % 4)) % 4
    vbytes += b"\x00" * pad
    blob = vbytes + ibytes
    gltf = {
        "asset": {"version": "2.0", "generator": "crisis-os-semantic-v2"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}],
        "materials": [{"pbrMetallicRoughness": {
            "baseColorFactor": [r, g, b, 1], "metallicFactor": 0.08, "roughnessFactor": 0.72}}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": nvert, "type": "VEC3",
             "min": vmin, "max": vmax},
            {"bufferView": 1, "componentType": 5123, "count": len(indices), "type": "SCALAR"},
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(vbytes)},
            {"buffer": 0, "byteOffset": len(vbytes), "byteLength": len(ibytes)},
        ],
        "buffers": [{"uri": f"{name}.bin", "byteLength": len(blob)}],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.parent / f"{name}.bin").write_bytes(blob)
    path.write_text(json.dumps(gltf), encoding="utf-8")


def solids_catalog() -> dict:
    """Ground rings in local metres (x east, z north) + height for SolidPolygonLayer."""
    out = {}
    for name, parts in PARTS.items():
        rgb = COLORS.get(name, (0.6, 0.6, 0.6))
        rings = []
        for cx, cy, cz, sx, sy, sz in parts:
            hx, hz = sx / 2, sz / 2
            rings.append({
                "ring_m": [
                    [cx - hx, cz - hz], [cx + hx, cz - hz],
                    [cx + hx, cz + hz], [cx - hx, cz + hz],
                ],
                "h": round(cy + sy / 2, 2),
            })
        out[name] = {
            "symbol": SYMBOLS.get(name, "•"),
            "color": [round(rgb[0] * 255), round(rgb[1] * 255), round(rgb[2] * 255)],
            "parts": rings,
        }
    return out


def write_all(gltf_dir: Path, catalog_path: Path) -> None:
    gltf_dir.mkdir(parents=True, exist_ok=True)
    for name in PARTS:
        write_gltf(gltf_dir / f"{name}.gltf", name)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps(solids_catalog(), indent=2), encoding="utf-8")
