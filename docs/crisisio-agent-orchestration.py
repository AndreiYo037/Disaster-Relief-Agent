"""Render the CrisisIO agent orchestration diagram as a 16:9 PDF.

Run:
    python docs/crisisio-agent-orchestration.py
"""
from __future__ import annotations

import math
from pathlib import Path


W, H = 960, 540
OUT = Path(__file__).with_suffix(".pdf")

NAVY = "#15314B"
INK = "#243746"
MUTED = "#65788A"
PAPER = "#F7FAFC"
LINE = "#D7E1E8"
WHITE = "#FFFFFF"
BLUE = "#3E85B8"
TEAL = "#167C80"
AMBER = "#C98325"
PURPLE = "#7657A8"
CORAL = "#C84B4B"
GREEN = "#2E8B6C"
PALE_BLUE = "#EAF3F9"
PALE_TEAL = "#E8F5F3"
PALE_AMBER = "#FBF3E5"
PALE_PURPLE = "#F0ECF8"
PALE_CORAL = "#FBEAEC"


def rgb(color: str) -> tuple[float, float, float]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) / 255 for i in (0, 2, 4))


def esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class Pdf:
    def __init__(self) -> None:
        self.ops: list[str] = []

    def _xy(self, x: float, y: float) -> tuple[float, float]:
        return x, H - y

    def fill(self, color: str) -> None:
        r, g, b = rgb(color)
        self.ops.append(f"{r:.4f} {g:.4f} {b:.4f} rg")

    def stroke(self, color: str) -> None:
        r, g, b = rgb(color)
        self.ops.append(f"{r:.4f} {g:.4f} {b:.4f} RG")

    def width(self, value: float) -> None:
        self.ops.append(f"{value:.2f} w")

    def dash(self, pattern: tuple[float, ...] | None = None) -> None:
        self.ops.append("[] 0 d" if pattern is None else f"[{' '.join(map(str, pattern))}] 0 d")

    def rect(self, x: float, y: float, w: float, h: float, fill: str, stroke: str | None = None) -> None:
        px, py = self._xy(x, y + h)
        self.fill(fill)
        self.ops.append(f"{px:.2f} {py:.2f} {w:.2f} {h:.2f} re f")
        if stroke:
            self.stroke(stroke)
            self.ops.append(f"{px:.2f} {py:.2f} {w:.2f} {h:.2f} re S")

    def round_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        radius: float,
        fill: str,
        stroke: str | None = None,
        line_width: float = 1,
    ) -> None:
        k = 0.55228475
        r = min(radius, w / 2, h / 2)
        p = [
            self._xy(x + r, y),
            self._xy(x + w - r, y),
            self._xy(x + w, y + r),
            self._xy(x + w, y + h - r),
            self._xy(x + w - r, y + h),
            self._xy(x + r, y + h),
            self._xy(x, y + h - r),
            self._xy(x, y + r),
        ]
        self.fill(fill)
        self.ops.append(f"{p[0][0]:.2f} {p[0][1]:.2f} m")
        self.ops.append(f"{p[1][0]:.2f} {p[1][1]:.2f} l")
        self.ops.append(
            f"{self._xy(x + w - r + k * r, y)[0]:.2f} {self._xy(x + w - r + k * r, y)[1]:.2f} "
            f"{self._xy(x + w, y + r - k * r)[0]:.2f} {self._xy(x + w, y + r - k * r)[1]:.2f} "
            f"{p[2][0]:.2f} {p[2][1]:.2f} c"
        )
        self.ops.append(f"{p[3][0]:.2f} {p[3][1]:.2f} l")
        self.ops.append(
            f"{self._xy(x + w, y + h - r + k * r)[0]:.2f} {self._xy(x + w, y + h - r + k * r)[1]:.2f} "
            f"{self._xy(x + w - r + k * r, y + h)[0]:.2f} {self._xy(x + w - r + k * r, y + h)[1]:.2f} "
            f"{p[4][0]:.2f} {p[4][1]:.2f} c"
        )
        self.ops.append(f"{p[5][0]:.2f} {p[5][1]:.2f} l")
        self.ops.append(
            f"{self._xy(x + r - k * r, y + h)[0]:.2f} {self._xy(x + r - k * r, y + h)[1]:.2f} "
            f"{self._xy(x, y + h - r + k * r)[0]:.2f} {self._xy(x, y + h - r + k * r)[1]:.2f} "
            f"{p[6][0]:.2f} {p[6][1]:.2f} c"
        )
        self.ops.append(f"{p[7][0]:.2f} {p[7][1]:.2f} l")
        self.ops.append(
            f"{self._xy(x, y + r - k * r)[0]:.2f} {self._xy(x, y + r - k * r)[1]:.2f} "
            f"{self._xy(x + r - k * r, y)[0]:.2f} {self._xy(x + r - k * r, y)[1]:.2f} "
            f"{p[0][0]:.2f} {p[0][1]:.2f} c h f"
        )
        if stroke:
            self.stroke(stroke)
            self.width(line_width)
            self.ops.append(f"{p[0][0]:.2f} {p[0][1]:.2f} m")
            self.ops.append(f"{p[1][0]:.2f} {p[1][1]:.2f} l")
            self.ops.append(
                f"{self._xy(x + w - r + k * r, y)[0]:.2f} {self._xy(x + w - r + k * r, y)[1]:.2f} "
                f"{self._xy(x + w, y + r - k * r)[0]:.2f} {self._xy(x + w, y + r - k * r)[1]:.2f} "
                f"{p[2][0]:.2f} {p[2][1]:.2f} c"
            )
            self.ops.append(f"{p[3][0]:.2f} {p[3][1]:.2f} l")
            self.ops.append(
                f"{self._xy(x + w, y + h - r + k * r)[0]:.2f} {self._xy(x + w, y + h - r + k * r)[1]:.2f} "
                f"{self._xy(x + w - r + k * r, y + h)[0]:.2f} {self._xy(x + w - r + k * r, y + h)[1]:.2f} "
                f"{p[4][0]:.2f} {p[4][1]:.2f} c"
            )
            self.ops.append(f"{p[5][0]:.2f} {p[5][1]:.2f} l")
            self.ops.append(
                f"{self._xy(x + r - k * r, y + h)[0]:.2f} {self._xy(x + r - k * r, y + h)[1]:.2f} "
                f"{self._xy(x, y + h - r + k * r)[0]:.2f} {self._xy(x, y + h - r + k * r)[1]:.2f} "
                f"{p[6][0]:.2f} {p[6][1]:.2f} c"
            )
            self.ops.append(f"{p[7][0]:.2f} {p[7][1]:.2f} l")
            self.ops.append(
                f"{self._xy(x, y + r - k * r)[0]:.2f} {self._xy(x, y + r - k * r)[1]:.2f} "
                f"{self._xy(x + r - k * r, y)[0]:.2f} {self._xy(x + r - k * r, y)[1]:.2f} "
                f"{p[0][0]:.2f} {p[0][1]:.2f} c S"
            )

    def line(self, x1: float, y1: float, x2: float, y2: float, color: str = LINE, line_width: float = 1) -> None:
        self.stroke(color)
        self.width(line_width)
        start = self._xy(x1, y1)
        end = self._xy(x2, y2)
        self.ops.append(
            f"{start[0]:.2f} {start[1]:.2f} m {end[0]:.2f} {end[1]:.2f} l S"
        )

    def arrow(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: str = MUTED,
        line_width: float = 1.1,
        dashed: bool = False,
    ) -> None:
        self.dash((4, 3) if dashed else None)
        self.line(x1, y1, x2, y2, color, line_width)
        angle = math.atan2(y2 - y1, x2 - x1)
        size = 5.5
        left = (x2 - size * math.cos(angle - math.pi / 6), y2 - size * math.sin(angle - math.pi / 6))
        right = (x2 - size * math.cos(angle + math.pi / 6), y2 - size * math.sin(angle + math.pi / 6))
        p1 = self._xy(x2, y2)
        p2 = self._xy(*left)
        p3 = self._xy(*right)
        self.fill(color)
        self.ops.append(
            f"{p1[0]:.2f} {p1[1]:.2f} m {p2[0]:.2f} {p2[1]:.2f} l "
            f"{p3[0]:.2f} {p3[1]:.2f} l h f"
        )
        self.dash()

    def text(
        self,
        x: float,
        top: float,
        value: str,
        size: float,
        color: str = INK,
        font: str = "F1",
        align: str = "left",
    ) -> None:
        lines = value.split("\n")
        leading = size * 1.18
        r, g, b = rgb(color)
        for index, line in enumerate(lines):
            line_width = len(line) * size * (0.52 if font == "F2" else 0.49)
            tx = x
            if align == "center":
                tx = x - line_width / 2
            elif align == "right":
                tx = x - line_width
            baseline = H - top - size - index * leading
            self.ops.append(
                f"BT /{font} {size:.2f} Tf {r:.4f} {g:.4f} {b:.4f} rg "
                f"1 0 0 1 {tx:.2f} {baseline:.2f} Tm ({esc(line)}) Tj ET"
            )

    def build(self) -> bytes:
        stream = "\n".join(self.ops).encode("latin-1")
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W} {H}] "
            "/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>".encode(),
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        ]
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for index, obj in enumerate(objects, 1):
            offsets.append(len(out))
            out.extend(f"{index} 0 obj\n".encode())
            out.extend(obj)
            out.extend(b"\nendobj\n")
        xref = len(out)
        out.extend(f"xref\n0 {len(objects) + 1}\n".encode())
        out.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            out.extend(f"{offset:010d} 00000 n \n".encode())
        out.extend(
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n".encode()
        )
        return bytes(out)


def label(p: Pdf, x: float, y: float, value: str, color: str) -> None:
    p.text(x, y, value.upper(), 6.5, color, "F2")


def card(
    p: Pdf,
    x: float,
    y: float,
    w: float,
    h: float,
    name: str,
    description: str,
    accent: str,
    fill: str,
    name_size: float = 8.1,
) -> None:
    p.round_rect(x, y, w, h, 6, fill, LINE, 0.8)
    p.rect(x, y, 4, h, accent)
    p.text(x + 12, y + 9, name, name_size, NAVY, "F2")
    p.text(x + 12, y + h - 19, description, 6.6, MUTED)


def build() -> bytes:
    p = Pdf()
    p.rect(0, 0, W, H, PAPER)
    p.rect(0, 0, W, 56, NAVY)
    p.text(30, 15, "CrisisIO Agent Orchestration", 21, WHITE, "F2")
    p.text(30, 39, "From scattered disaster signals to human-approved action", 8.5, "#C9D8E5")
    p.round_rect(746, 14, 182, 28, 7, "#244862")
    p.text(837, 20, "REPLAY: t0  ->  b7  ->  reroute", 7.1, WHITE, "F2", "center")

    label(p, 30, 74, "Four evidence lanes run in parallel", TEAL)
    p.text(30, 84, "Each lane keeps its own provenance while the shared spine turns results into an operational picture.", 7.2, MUTED)

    label(p, 42, 107, "Source", BLUE)
    label(p, 211, 107, "Verify", TEAL)
    label(p, 379, 107, "Evaluate", PURPLE)
    label(p, 615, 107, "Shared operational spine", NAVY)

    source_x, verify_x, eval_x = 38, 205, 372
    card_w, card_h = 141, 58
    rows = [
        (132, "SatelliteSource\nAgent", "imagery -> flood / damage claims", BLUE, PALE_BLUE),
        (207, "TelemetrySource\nAgent", "gauges -> measurements", TEAL, PALE_TEAL),
        (282, "FieldReportSource\nAgent", "responders -> access / need", AMBER, PALE_AMBER),
        (357, "CommunityReportSource\nAgent", "public reports -> local need", CORAL, PALE_CORAL),
    ]
    verification_names = [
        "SatelliteVerification\nAgent",
        "TelemetryVerification\nAgent",
        "FieldReportVerification\nAgent",
        "CommunityReportVerification\nAgent",
    ]
    evaluation_names = [
        "SatelliteEvaluation\nAgent",
        "TelemetryEvaluation\nAgent",
        "FieldReportEvaluation\nAgent",
        "CommunityReportEvaluation\nAgent",
    ]
    accents = [BLUE, TEAL, AMBER, CORAL]
    fills = [PALE_BLUE, PALE_TEAL, PALE_AMBER, PALE_CORAL]
    for index, (y, source_name, source_desc, accent, fill) in enumerate(rows):
        card(p, source_x, y, card_w, card_h, source_name, source_desc, accent, fill)
        card(
            p,
            verify_x,
            y,
            card_w,
            card_h,
            verification_names[index],
            "5 deterministic checks",
            accents[index],
            fills[index],
            7.5,
        )
        card(
            p,
            eval_x,
            y,
            card_w,
            card_h,
            evaluation_names[index],
            "utility + harm score",
            accents[index],
            fills[index],
            7.5,
        )
        p.arrow(source_x + card_w + 7, y + card_h / 2, verify_x - 7, y + card_h / 2)
        p.arrow(verify_x + card_w + 7, y + card_h / 2, eval_x - 7, y + card_h / 2)

    # A join bus makes the parallel-to-shared transition obvious.
    bus_x = 550
    p.line(bus_x, 161, bus_x, 386, "#A7BBC9", 1.4)
    for y in (161, 236, 311, 386):
        p.arrow(eval_x + card_w + 7, y, bus_x - 2, y, "#A7BBC9", 1.1)
    p.text(512, 401, "four lanes join", 6.4, MUTED, "F2", "center")
    p.arrow(bus_x, 162, 604, 162, NAVY, 1.5)

    shared_x, shared_w = 604, 292
    card(p, shared_x, 132, shared_w, 61, "DispatchResourcePlanning\nAgent", "dedupe claims  |  prioritize  |  suggest routes", NAVY, "#E7EEF4", 8.0)
    card(p, shared_x, 215, shared_w, 61, "Orchestrator\nAgent", "merge state  |  request evidence  |  track lifecycle", NAVY, "#E7EEF4", 8.3)
    card(p, shared_x, 298, shared_w, 61, "Summariser\nAgent", "one traceable incident brief", NAVY, "#E7EEF4", 8.3)
    p.arrow(shared_x + shared_w / 2, 193, shared_x + shared_w / 2, 215, NAVY, 1.4)
    p.arrow(shared_x + shared_w / 2, 276, shared_x + shared_w / 2, 298, NAVY, 1.4)

    # Human safety checkpoint is deliberately not an agent.
    gate_x, gate_y, gate_w, gate_h = 604, 378, 292, 54
    p.dash((5, 3))
    p.round_rect(gate_x, gate_y, gate_w, gate_h, 6, PALE_CORAL, CORAL, 1.1)
    p.dash()
    p.round_rect(gate_x + 11, gate_y + 12, 29, 29, 14, CORAL)
    p.text(gate_x + 25.5, gate_y + 17, "H", 12, WHITE, "F2", "center")
    p.text(gate_x + 53, gate_y + 9, "HUMAN COORDINATOR CHECKPOINT", 7, CORAL, "F2")
    p.text(gate_x + 53, gate_y + 23, "approve, modify, or reject physical action proposals", 7.1, INK)
    p.text(gate_x + 53, gate_y + 36, "no approval -> no physical dispatch", 6.7, CORAL, "F2")
    p.dash((4, 3))
    p.line(shared_x + shared_w, 162, 912, 162, CORAL, 1.2)
    p.line(912, 162, 912, gate_y + gate_h / 2, CORAL, 1.2)
    p.arrow(912, gate_y + gate_h / 2, gate_x + gate_w, gate_y + gate_h / 2, CORAL, 1.2, True)
    p.dash()
    p.text(918, 207, "physical\nproposal", 6.2, CORAL, "F2", "right")

    # Projection is shown as an output, not as a 16th agent.
    projection_x, projection_y, projection_w, projection_h = 604, 455, 292, 42
    p.round_rect(projection_x, projection_y, projection_w, projection_h, 6, PALE_PURPLE, PURPLE, 1)
    p.text(projection_x + 14, projection_y + 8, "WorldSnapshot projection", 8, PURPLE, "F2")
    p.text(projection_x + 14, projection_y + 23, "structured state for the existing 3D world model", 6.9, INK)
    projection_center = projection_x + projection_w / 2
    p.line(shared_x + shared_w / 2, 359, 590, 359, PURPLE, 1)
    p.line(590, 359, 590, 445, PURPLE, 1)
    p.arrow(590, 445, projection_x, projection_y, PURPLE, 1)

    # Bounded feedback loop from the orchestrator back to the relevant source lane.
    p.dash((4, 3))
    p.line(590, 245, 558, 245, PURPLE, 1)
    p.line(558, 245, 558, 430, PURPLE, 1)
    p.arrow(558, 430, 108, 430, PURPLE, 1, True)
    p.arrow(108, 430, 108, 415, PURPLE, 1, True)
    p.dash()
    p.text(319, 433, "bounded evidence request (max 3 cycles)", 6.7, PURPLE, "F2", "center")

    # Bottom legend and audience-friendly summary.
    p.line(30, 493, 930, 493, LINE, 0.8)
    p.text(30, 505, "Solid arrows = data flow", 6.8, MUTED)
    p.dash((4, 3))
    p.line(160, 510, 185, 510, MUTED, 1)
    p.dash()
    p.text(193, 505, "dotted outline = human checkpoint / bounded loop", 6.8, MUTED)
    p.round_rect(512, 503, 12, 12, 3, PALE_BLUE, LINE, 0.5)
    p.text(532, 505, "parallel lane", 6.8, MUTED)
    p.text(930, 505, "Exactly 15 named agents + deterministic projection", 6.8, NAVY, "F2", "right")

    return p.build()


if __name__ == "__main__":
    OUT.write_bytes(build())
    print(f"Wrote {OUT}")
