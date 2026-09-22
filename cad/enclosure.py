"""
LumosAir sensor-node enclosure — parametric fitment model.

Both nodes use the SAME box with the SAME bulkhead pattern; the fan node simply
plugs the ports it doesn't use. Run this file to regenerate the model:

    pip install cadquery
    python cad/enclosure.py                 # writes everything into cad/out/
    python cad/enclosure.py --populate fan  # fan-node population instead of laser

Outputs (cad/out/):
    lumosair_enclosure_<pop>.step   assembly for FreeCAD / Fusion / SolidWorks
    lumosair_enclosure_<pop>.stl    mesh for Blender / Bambu Studio
    view_iso.svg / view_top.svg / view_front.svg
    drill_template_side.svg         1:1 hole pattern for the port wall
    fitment_report.txt              clearances, stack heights, collisions

All dimensions are millimetres, measured from the INSIDE floor of the box at the
inside back-left corner. Sources for the part sizes are in docs/datasheets/.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cadquery as cq

# --------------------------------------------------------------------------------------
# Enclosure — Hammond 1554H2GYCL (clear polycarbonate lid), docs/datasheets/Hammond_*.pdf
# --------------------------------------------------------------------------------------
BOX_OUT_L, BOX_OUT_W, BOX_OUT_H = 180.0, 120.0, 60.5
WALL = 3.0
BOX_IN_L, BOX_IN_W, BOX_IN_H = 172.91, 108.91, 54.5
CORNER_BOSS_R = 7.0          # corner screw bosses intrude on the interior
CORNER_BOSS_H = BOX_IN_H
LID_T = 3.0

# Keep-out above the floor for the moulded ribs along the inside walls.
RIB_H = 6.0

# --------------------------------------------------------------------------------------
# Bulkhead port pattern — identical on both boxes
# --------------------------------------------------------------------------------------
PORT_COUNT = 6               # 5 used by the laser node, 1 spare; fan node plugs 5
PORT_DIA = 8.0               # through-hole for a 1/8" NPT or push-fit bulkhead
PORT_PITCH = 24.0
PORT_Z = 14.0                # height above the inside floor
GLAND_DIA = 12.5             # cable gland for the USB supply lead
GLAND_Z = 20.0

# --------------------------------------------------------------------------------------
# Parts. size = (x, y, z); pos = (x, y, z) of the minimum corner, z above inside floor.
# --------------------------------------------------------------------------------------
@dataclass
class Part:
    name: str
    size: tuple[float, float, float]
    pos: tuple[float, float, float]
    color: tuple[float, float, float, float] = (0.4, 0.5, 0.6, 1.0)
    note: str = ""
    children: list["Part"] = field(default_factory=list)

    @property
    def x2(self) -> float: return self.pos[0] + self.size[0]
    @property
    def y2(self) -> float: return self.pos[1] + self.size[1]
    @property
    def z2(self) -> float: return self.pos[2] + self.size[2]

    def solid(self) -> cq.Workplane:
        return cq.Workplane("XY").box(*self.size, centered=False).translate(self.pos)


# Standoff heights chosen so tubing can run underneath the sensor carrier.
CARRIER_STANDOFF = 16.0      # SDP810 barbs hang 9.65 mm below the board
MCU_STANDOFF = 6.0
DISPLAY_STANDOFF = 34.0      # display looks up through the clear lid

SDP_BODY = (29.0, 18.0, 10.25)      # SDP81x tube version, Sensirion drawing fig. 2
SDP_BARB_DIA, SDP_BARB_LEN, SDP_BARB_PITCH = 5.2, 9.65, 12.6
XGZP_MOD = (22.0, 16.0, 1.6)        # small carrier board
XGZP_SENSOR = (11.0, 10.8, 9.61)    # CFSensor drawing
MUX = (26.0, 17.0, 1.6)             # TCA9548A breakout
BME = (16.0, 12.0, 1.6)
CARRIER = (120.0, 44.0, 1.6)        # sensor carrier / perfboard
MCU_PCB = (68.6, 53.4, 1.6)         # Handson MDU1156 expansion board
MCU_STACK = (58.0, 30.0, 20.0)      # ESP32 DevKit sitting in its headers
DISPLAY_PCB = (56.0, 40.0, 1.6)     # NULLLAB 2.0" ST7789 240x320
DISPLAY_GLASS = (49.0, 33.0, 4.0)


def build_parts(populate: str) -> list[Part]:
    """populate: 'laser' (5 channels + BME280) or 'fan' (1 channel)."""
    parts: list[Part] = []

    # --- sensor carrier along the port wall (y = 0 side) ---
    cx, cy = 46.0, 3.0
    parts.append(Part("sensor carrier board", CARRIER, (cx, cy, CARRIER_STANDOFF),
                      (0.1, 0.35, 0.15, 1.0), "perfboard or small PCB on M3 standoffs"))
    top = CARRIER_STANDOFF + CARRIER[2]

    sdp_count, xgzp_count, has_bme = (3, 2, True) if populate == "laser" else (0, 1, True)

    # SDP810s sit with their barbs pointing down, in a row facing the ports.
    for i in range(sdp_count):
        x = cx + 4 + i * (SDP_BODY[0] + 5)
        parts.append(Part(f"SDP810-500Pa #{i+1}", SDP_BODY, (x, cy + 4, top),
                          (0.85, 0.85, 0.88, 1.0), "barbs point down into the tubing space"))
    for i in range(xgzp_count):
        x = cx + 4 + i * (XGZP_MOD[0] + 6)
        y = cy + 25
        parts.append(Part(f"XGZP6897D module #{i+1}", XGZP_MOD, (x, y, top), (0.2, 0.5, 0.25, 1.0)))
        parts.append(Part(f"XGZP6897D sensor #{i+1}", XGZP_SENSOR,
                          (x + 5, y + 2, top + XGZP_MOD[2]), (0.3, 0.3, 0.35, 1.0)))
    if populate == "laser":
        parts.append(Part("TCA9548A mux", MUX, (cx + 4 + 2 * (XGZP_MOD[0] + 6), cy + 25, top),
                          (0.2, 0.5, 0.25, 1.0)))
    if has_bme:
        parts.append(Part("BME280", BME, (cx + CARRIER[0] - BME[0] - 4, cy + 26, top),
                          (0.2, 0.5, 0.25, 1.0)))

    # --- MCU board, opposite end, USB-C facing the gland wall ---
    mx, my = 4.0, BOX_IN_W - MCU_PCB[1] - 6.0
    parts.append(Part("ESP32 expansion board", MCU_PCB, (mx, my, MCU_STANDOFF),
                      (0.12, 0.12, 0.14, 1.0), "Handson MDU1156, 68.6 x 53.4, 4x M3"))
    parts.append(Part("ESP32-WROOM-32 DevKit", MCU_STACK,
                      (mx + 5, my + 11, MCU_STANDOFF + MCU_PCB[2]), (0.15, 0.15, 0.2, 1.0)))

    # --- display, upper level, over the MCU board, looking up through the clear lid ---
    dx, dy = 8.0, 56.0
    parts.append(Part("2.0\" ST7789 display PCB", DISPLAY_PCB, (dx, dy, DISPLAY_STANDOFF),
                      (0.15, 0.2, 0.3, 1.0), "56 x 40 module on tall standoffs"))
    parts.append(Part("display glass", DISPLAY_GLASS,
                      (dx + 3.5, dy + 3.5, DISPLAY_STANDOFF + DISPLAY_PCB[2]),
                      (0.05, 0.05, 0.08, 1.0), "visible through the clear lid — no cut-out"))
    return parts


# --------------------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------------------
def box_shell() -> cq.Workplane:
    """Box with the identical bulkhead pattern. Origin = inside floor, inside back-left."""
    outer = (cq.Workplane("XY")
             .box(BOX_OUT_L, BOX_OUT_W, BOX_OUT_H, centered=False)
             .translate((-WALL, -WALL, -WALL)))
    cavity = cq.Workplane("XY").box(BOX_IN_L, BOX_IN_W, BOX_IN_H + WALL, centered=False)
    shell = outer.cut(cavity)

    # corner bosses
    for x, y in ((0, 0), (BOX_IN_L, 0), (0, BOX_IN_W), (BOX_IN_L, BOX_IN_W)):
        boss = (cq.Workplane("XY").circle(CORNER_BOSS_R).extrude(CORNER_BOSS_H)
                .translate((x, y, 0)))
        shell = shell.union(boss.intersect(cq.Workplane("XY")
                                           .box(BOX_IN_L, BOX_IN_W, CORNER_BOSS_H, centered=False)))

    # bulkhead ports through the y = 0 wall
    for x in port_positions():
        hole = (cq.Workplane("XZ").circle(PORT_DIA / 2).extrude(WALL + 2)
                .translate((x, 1.0, PORT_Z)))
        shell = shell.cut(hole)

    # cable gland through the x = 0 wall
    gland = (cq.Workplane("YZ").circle(GLAND_DIA / 2).extrude(-(WALL + 2))
             .translate((1.0, BOX_IN_W / 2, GLAND_Z)))
    return shell.cut(gland)


def port_positions() -> list[float]:
    span = (PORT_COUNT - 1) * PORT_PITCH
    x0 = (BOX_IN_L - span) / 2
    return [x0 + i * PORT_PITCH for i in range(PORT_COUNT)]


def lid() -> cq.Workplane:
    return (cq.Workplane("XY").box(BOX_OUT_L, BOX_OUT_W, LID_T, centered=False)
            .translate((-WALL, -WALL, BOX_IN_H)))


def sdp_barbs(part: Part) -> cq.Workplane:
    """Two downward barbs under an SDP810 body."""
    cx = part.pos[0] + part.size[0] / 2
    cy = part.pos[1] + part.size[1] / 2
    res = None
    for dx in (-SDP_BARB_PITCH / 2, SDP_BARB_PITCH / 2):
        b = (cq.Workplane("XY").circle(SDP_BARB_DIA / 2).extrude(-SDP_BARB_LEN)
             .translate((cx + dx, cy, part.pos[2])))
        res = b if res is None else res.union(b)
    return res


def build_assembly(parts: list[Part]) -> cq.Assembly:
    asm = cq.Assembly(name="LumosAir node")
    asm.add(box_shell(), name="enclosure", color=cq.Color(0.55, 0.55, 0.58, 0.35))
    asm.add(lid(), name="clear lid", color=cq.Color(0.8, 0.85, 0.9, 0.25))
    for p in parts:
        asm.add(p.solid(), name=p.name, color=cq.Color(*p.color))
        if p.name.startswith("SDP810"):
            asm.add(sdp_barbs(p), name=p.name + " barbs", color=cq.Color(0.9, 0.9, 0.2, 1.0))
    return asm


# --------------------------------------------------------------------------------------
# Fitment checks
# --------------------------------------------------------------------------------------
def overlap(a: Part, b: Part) -> tuple[float, float, float]:
    return (min(a.x2, b.x2) - max(a.pos[0], b.pos[0]),
            min(a.y2, b.y2) - max(a.pos[1], b.pos[1]),
            min(a.z2, b.z2) - max(a.pos[2], b.pos[2]))


def in_corner_boss(x: float, y: float) -> bool:
    for bx, by in ((0, 0), (BOX_IN_L, 0), (0, BOX_IN_W), (BOX_IN_L, BOX_IN_W)):
        if (x - bx) ** 2 + (y - by) ** 2 < CORNER_BOSS_R ** 2:
            return True
    return False


def report(parts: list[Part], populate: str) -> tuple[str, bool]:
    lines: list[str] = []
    ok = True
    lines.append(f"LumosAir enclosure fitment report — {populate} node")
    lines.append(f"Hammond 1554H2GYCL, inside {BOX_IN_L} x {BOX_IN_W} x {BOX_IN_H} mm\n")

    lines.append(f"{'part':34} {'x':>16} {'y':>16} {'z':>14}")
    for p in parts:
        lines.append(f"{p.name:34} {p.pos[0]:6.1f}–{p.x2:6.1f} {p.pos[1]:6.1f}–{p.y2:6.1f} "
                     f"{p.pos[2]:5.1f}–{p.z2:5.1f}")

    lines.append("\nClearances")
    tallest = max(parts, key=lambda p: p.z2)
    head = BOX_IN_H - tallest.z2
    lines.append(f"  tallest item          : {tallest.name} at {tallest.z2:.1f} mm")
    lines.append(f"  headroom under lid    : {head:.1f} mm")
    if head < 2:
        ok = False
        lines.append("  ** does not fit under the lid **")

    for p in parts:
        edge = min(p.pos[0], p.pos[1], BOX_IN_L - p.x2, BOX_IN_W - p.y2)
        if edge < 2:
            ok = False
            lines.append(f"  ** {p.name} is {edge:.1f} mm from an inside wall **")
        for corner in ((p.pos[0], p.pos[1]), (p.x2, p.pos[1]), (p.pos[0], p.y2), (p.x2, p.y2)):
            if in_corner_boss(*corner) and p.pos[2] < CORNER_BOSS_H:
                ok = False
                lines.append(f"  ** {p.name} clashes with a corner boss **")

    lines.append("\nCollisions")
    clashes = 0
    for i, a in enumerate(parts):
        for b in parts[i + 1:]:
            if a.name.split("#")[0] == b.name.split("#")[0] and "sensor" in b.name:
                continue  # module and its own sensor body are stacked on purpose
            ox, oy, oz = overlap(a, b)
            if ox > 0.5 and oy > 0.5 and oz > 0.5:
                if a.name in b.note or b.pos[2] >= a.z2 - 0.1:
                    continue
                clashes += 1
                lines.append(f"  ** {a.name} ∩ {b.name}: {ox:.1f} x {oy:.1f} x {oz:.1f} mm **")
    if clashes == 0:
        lines.append("  none")
    else:
        ok = False

    lines.append("\nBulkhead ports (identical on both boxes)")
    lines.append(f"  {PORT_COUNT} x Ø{PORT_DIA} mm at {PORT_PITCH} mm pitch, {PORT_Z} mm above the inside floor")
    lines.append("  x positions from the inside back-left corner: " +
                 ", ".join(f"{x:.1f}" for x in port_positions()))
    lines.append(f"  cable gland Ø{GLAND_DIA} mm in the end wall at z = {GLAND_Z} mm")
    used = {"laser": ["cyc_dp +", "cyc_dp −", "bin", "pitot total", "pitot static", "encl"],
            "fan": ["fan_in", "plug", "plug", "plug", "plug", "plug"]}[populate]
    for x, u in zip(port_positions(), used):
        lines.append(f"    x={x:6.1f}  {u}")

    lines.append("\nNotes")
    lines.append("  • The lid is clear polycarbonate, so the display needs no cut-out.")
    lines.append("  • Tubing runs under the sensor carrier: "
                 f"{CARRIER_STANDOFF:.0f} mm of standoff, barbs hang {SDP_BARB_LEN:.1f} mm.")
    lines.append(f"  • Ribs along the inside walls are ~{RIB_H:.0f} mm tall; "
                 "standoffs clear them.")
    return "\n".join(lines), ok


# --------------------------------------------------------------------------------------
# Exports
# --------------------------------------------------------------------------------------
def export_views(asm: cq.Assembly, out: Path) -> None:
    compound = asm.toCompound()
    views = {
        "view_iso.svg": (1, -1, 1),
        "view_top.svg": (0, 0, 1),
        "view_front.svg": (0, -1, 0),
    }
    for fname, direction in views.items():
        cq.exporters.export(
            compound, str(out / fname), exportType="SVG",
            opt={"width": 1100, "height": 700, "marginLeft": 20, "marginTop": 20,
                 "showAxes": False, "projectionDir": direction,
                 "strokeWidth": 0.3, "strokeColor": (30, 30, 30),
                 "hiddenColor": (200, 200, 200), "showHidden": False})


def export_drill_template(out: Path) -> None:
    """1:1 drilling template for the port wall and the gland wall."""
    wall = (cq.Workplane("XY").box(BOX_OUT_L, BOX_OUT_H, 1, centered=False))
    for x in port_positions():
        wall = wall.cut(cq.Workplane("XY").circle(PORT_DIA / 2).extrude(2)
                        .translate((x, PORT_Z + WALL, 0)))
    cq.exporters.export(wall, str(out / "drill_template_side.svg"), exportType="SVG",
                        opt={"width": 900, "height": 400, "projectionDir": (0, 0, 1),
                             "showAxes": False, "strokeWidth": 0.4})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--populate", choices=["laser", "fan"], default="laser")
    ap.add_argument("--out", default=str(Path(__file__).parent / "out"))
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    parts = build_parts(args.populate)
    asm = build_assembly(parts)

    text, ok = report(parts, args.populate)
    (out / "fitment_report.txt").write_text(text + "\n", encoding="utf-8")
    print(text)

    stem = f"lumosair_enclosure_{args.populate}"
    asm.save(str(out / f"{stem}.step"))
    cq.exporters.export(asm.toCompound(), str(out / f"{stem}.stl"))
    export_views(asm, out)
    export_drill_template(out)
    print(f"\nWrote {stem}.step/.stl, three SVG views and the drill template to {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
