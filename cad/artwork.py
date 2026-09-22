"""
1:1 artwork for the enclosure: panel markings to laser-engrave, and board outlines
for KiCad.

    python cad/artwork.py                 # both nodes, into cad/out/

Everything comes from the same parametric model as enclosure.py, so a moved port
moves its label, its hole and its PCB mounting hole together.

Written files
    panel_front_laser.svg / panel_front_fan.svg   front face, 1:1, mm
    panel_end.svg                                 left end wall (cable gland)
    drill_template_front.svg                      holes only, for marking out
    pcb_a_outline.dxf / pcb_b_outline.dxf         board edge + mounting holes

The SVGs use two colours by convention:
    red   (#ff0000)  cut / drill — the holes themselves
    black (#000000)  engrave     — text, frames, the power symbol
Most laser software maps colour to operation, so import and assign.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import cadquery as cq
import enclosure as enc

MM = 1.0
CUT, ENGRAVE = "#ff0000", "#000000"


# ======================================================================================
# a very small SVG writer — 1 user unit = 1 mm
# ======================================================================================
class Svg:
    def __init__(self, w: float, h: float, title: str):
        self.w, self.h = w, h
        self.body: list[str] = []
        self.title = title

    def circle(self, x, y, r, stroke=CUT, w=0.15):
        self.body.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{r:.3f}" fill="none" '
                         f'stroke="{stroke}" stroke-width="{w}"/>')

    def rect(self, x, y, w, h, stroke=ENGRAVE, sw=0.2, rx=0.0):
        self.body.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" '
                         f'rx="{rx:.2f}" fill="none" stroke="{stroke}" stroke-width="{sw}"/>')

    def line(self, x1, y1, x2, y2, stroke=ENGRAVE, sw=0.2):
        self.body.append(f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" '
                         f'stroke="{stroke}" stroke-width="{sw}"/>')

    def arc(self, cx, cy, r, a0, a1, stroke=ENGRAVE, sw=0.3):
        x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
        x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
        large = 1 if abs(a1 - a0) > math.pi else 0
        self.body.append(f'<path d="M {x0:.3f} {y0:.3f} A {r:.3f} {r:.3f} 0 {large} 1 '
                         f'{x1:.3f} {y1:.3f}" fill="none" stroke="{stroke}" stroke-width="{sw}"/>')

    def text(self, x, y, s, size=3.0, anchor="middle", fill=ENGRAVE, weight="600"):
        s = (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        self.body.append(f'<text x="{x:.3f}" y="{y:.3f}" font-family="DejaVu Sans, Arial, '
                         f'sans-serif" font-size="{size:.2f}" font-weight="{weight}" '
                         f'text-anchor="{anchor}" fill="{fill}">{s}</text>')

    def save(self, path: Path):
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w:.3f}mm" '
                f'height="{self.h:.3f}mm" viewBox="0 0 {self.w:.3f} {self.h:.3f}">\n'
                f'<title>{self.title}</title>\n')
        path.write_text(head + "\n".join(self.body) + "\n</svg>\n", encoding="utf-8")
        print("wrote", path)


# ======================================================================================
# panels
# ======================================================================================
def power_symbol(svg: Svg, cx: float, cy: float, r: float = 3.2):
    """IEC 5009 standby mark, engraved above the button."""
    svg.arc(cx, cy, r, math.radians(-65), math.radians(245))
    svg.line(cx, cy - r - 1.3, cx, cy + 0.3)


def panel_front(populate: str, out: Path, box_code: str, mcu: str, fittings: str) -> None:
    """The face the hoses and the power button come through, 1:1, seen from outside."""
    d = enc.build(populate, box_code, mcu, fittings)
    box = d.box
    ol, _, oh = box.out
    il = box.inside[0]
    dx, dz = (ol - il) / 2, enc.WALL            # inside origin -> outside panel origin

    svg = Svg(ol, oh, f"LumosAir {populate} node — front panel")
    svg.rect(0.15, 0.15, ol - 0.3, oh - 0.3, ENGRAVE, 0.2, rx=3)

    # seen from outside, x mirrors
    def px(x_inside: float) -> float:
        return ol - (x_inside + dx)

    def py(z_inside: float) -> float:
        return oh - (z_inside + dz)

    # labels go outward from the middle of the panel so the two rows never collide
    zs = sorted({z for _, z, _ in d.port_labels})
    ring = enc.BULK_HEX_AF / 2 + 1.3
    for x, z, lab in d.port_labels:
        cx, cy = px(x), py(z)
        svg.circle(cx, cy, enc.PORT_DIA / 2)
        svg.circle(cx, cy, ring, "#9a9a9a", 0.15)                      # nut witness ring
        ty = cy - ring - 1.6 if z == max(zs) else cy + ring + 3.4
        svg.text(cx, ty, lab, size=2.8,
                 fill=ENGRAVE if lab != "PLUG" else "#9a9a9a")

    sx, sy = px(box.inside[0] / 2), py(d.switch_z)
    svg.circle(sx, sy, enc.SWITCH_DIA / 2)
    power_symbol(svg, sx - enc.SWITCH_DIA / 2 - 6.5, sy)

    svg.text(ol - 6.0, 8.0, f"LumosAir · {populate} node", size=3.4, anchor="end")
    svg.save(out / f"panel_front_{populate}.svg")


def panel_end(out: Path, box_code: str, mcu: str, fittings: str) -> None:
    d = enc.build("laser", box_code, mcu, fittings)
    box = d.box
    _, ow, oh = box.out
    iw = box.inside[1]
    dy, dz = (ow - iw) / 2, enc.WALL

    svg = Svg(ow, oh, "LumosAir — left end wall")
    svg.rect(0.15, 0.15, ow - 0.3, oh - 0.3, ENGRAVE, 0.2, rx=3)
    cx, cy = enc.GLAND_Y + dy, oh - (enc.GLAND_Z + dz)
    svg.circle(cx, cy, enc.GLAND_DIA / 2)
    svg.text(cx, cy + enc.GLAND_DIA / 2 + 5.0, "5 V IN", size=3.2)
    svg.save(out / "panel_end.svg")


def drill_template(populate: str, out: Path, box_code: str, mcu: str, fittings: str) -> None:
    """Holes only, plus crosshairs — tape it to the box and centre-punch."""
    d = enc.build(populate, box_code, mcu, fittings)
    box = d.box
    ol, _, oh = box.out
    il = box.inside[0]
    dx, dz = (ol - il) / 2, enc.WALL

    svg = Svg(ol, oh, "LumosAir — front wall drill template (1:1)")
    svg.rect(0.1, 0.1, ol - 0.2, oh - 0.2, ENGRAVE, 0.2)
    for x, z, _ in d.port_labels:
        cx, cy = ol - (x + dx), oh - (z + dz)
        svg.circle(cx, cy, enc.PORT_DIA / 2)
        svg.line(cx - 5, cy, cx + 5, cy, ENGRAVE, 0.1)
        svg.line(cx, cy - 5, cx, cy + 5, ENGRAVE, 0.1)
    cx, cy = ol - (box.inside[0] / 2 + dx), oh - (d.switch_z + dz)
    svg.circle(cx, cy, enc.SWITCH_DIA / 2)
    svg.line(cx - 5, cy, cx + 5, cy, ENGRAVE, 0.1)
    svg.line(cx, cy - 5, cx, cy + 5, ENGRAVE, 0.1)
    svg.text(ol / 2, oh - 3, "1:1 — check this measures 100 mm across before drilling",
             size=2.6, weight="400", fill="#808080")
    svg.line(ol / 2 - 50, oh - 8, ol / 2 + 50, oh - 8, ENGRAVE, 0.3)
    svg.save(out / "drill_template_front.svg")


# ======================================================================================
# board outlines for KiCad
# ======================================================================================
def board_outlines(out: Path, box_code: str, mcu: str, fittings: str) -> None:
    d = enc.build("laser", box_code, mcu, fittings)
    pa = next(p for p in d.parts if p.name.startswith("PCB-A"))
    pb = next(p for p in d.parts if p.name.startswith("PCB-B"))
    for part, name in ((pa, "pcb_a"), (pb, "pcb_b")):
        w, dd = part.size[0], part.size[1]
        wp = (cq.Workplane("XY").rect(w, dd, centered=True)
              .pushPoints([(sx * (w / 2 - 3.0), sy * (dd / 2 - 3.0))
                           for sx in (-1, 1) for sy in (-1, 1)])
              .circle(1.6))            # M3 clearance
        cq.exporters.exportDXF(wp.wires(), str(out / f"{name}_outline.dxf"))
        print("wrote", out / f"{name}_outline.dxf",
              f"({w:.1f} x {dd:.1f} mm, M3 holes 3 mm in from each corner)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--box", choices=list(enc.BOXES) + ["auto"], default="auto")
    ap.add_argument("--mcu", choices=["module", "devkit"], default="module")
    ap.add_argument("--fittings", choices=["elbow", "straight"], default="elbow")
    ap.add_argument("--out", default=str(Path(__file__).parent / "out"))
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    code = enc.pick_box("laser", a.mcu, a.fittings) if a.box == "auto" else a.box
    for populate in ("laser", "fan"):
        panel_front(populate, out, code, a.mcu, a.fittings)
    panel_end(out, code, a.mcu, a.fittings)
    drill_template("laser", out, code, a.mcu, a.fittings)
    board_outlines(out, code, a.mcu, a.fittings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
