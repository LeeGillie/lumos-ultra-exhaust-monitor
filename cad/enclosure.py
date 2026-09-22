"""
LumosAir sensor-node enclosure — parametric fitment model (stacked two-board design).

    pip install cadquery
    python cad/enclosure.py                      # laser box, auto-chooses the enclosure
    python cad/enclosure.py --populate fan
    python cad/enclosure.py --box F --mcu module # force a size / a soldered ESP32 module
    python cad/enclosure.py --compare            # table of which boxes fit

How it is arranged, bottom to top:

    floor ── standoffs ── PCB-A (all the parts that need hoses, ports facing UP)
                              │  silicone tubes arc over to the bulkheads
          ── spacers ──── PCB-B (ESP32 + display hat, read through the clear lid)

Every hose is modelled as a real tube from the sensor port to its bulkhead, so the
report can check the bend radius and whether PCB-B would crush anything.

Outputs land in cad/out/. All dimensions are millimetres, measured from the INSIDE
floor at the inside back-left corner. Part sizes come from docs/datasheets/.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cadquery as cq

# ======================================================================================
# Enclosures — Hammond 1554 family, clear polycarbonate lid ("2GYCL")
# Only the H size has a confirmed drawing (docs/datasheets/Hammond_1554H2GYCL_drawing.pdf);
# the others use the same wall/flange offsets, so treat their insides as ±1 mm.
# ======================================================================================
WALL = 3.0
LID_T = 3.0
CORNER_BOSS_R = 7.0
RIB_H = 6.0                      # moulded ribs along the inside walls


@dataclass(frozen=True)
class Box:
    code: str
    out: tuple[float, float, float]

    @property
    def inside(self) -> tuple[float, float, float]:
        return (self.out[0] - 7.09, self.out[1] - 11.09, self.out[2] - 6.0)


BOXES = {
    "F": Box("1554F2GYCL", (120.0, 90.0, 60.5)),
    "G": Box("1554G2GYCL", (120.0, 90.0, 80.5)),
    "J": Box("1554J2GYCL", (160.0, 90.0, 60.5)),
    "H": Box("1554H2GYCL", (180.0, 120.0, 60.5)),
}

# ======================================================================================
# Bulkhead pattern — identical on both boxes; one row if the wall is wide enough
# ======================================================================================
N_PORTS = 8
PORT_DIA = 8.0                   # panel hole for a 1/8" barbed bulkhead union
PORT_PITCH_1ROW = 18.0           # one row of 8, if the wall is wide enough
PORT_PITCH_2ROW = 22.0           # otherwise two rows of 4
PORT_EDGE_KEEPOUT = 11.0         # corner bosses + nut clearance
USE_ONE_ROW = False              # see one_row()

# Where the rows sit depends on how the hose leaves the sensor.
#   "straight" — the hose goes onto the sensor barb and leaves pointing UP. To turn
#                into a wall port without kinking it needs a full bend radius of
#                height, so the ports have to be high and the box has to be tall.
#   "elbow"    — a push-on 90 deg barbed elbow turns the hose at the sensor, so it
#                leaves pointing at the wall and the run is almost straight.
PORT_Z = {"elbow": {1: 22.0, 2: (13.0, 27.0)},
          "straight": {1: 38.0, 2: (16.0, 38.0)}}
ELBOW_ARM = 12.0                 # how far the elbow outlet sits in front of the barb
ELBOW_RISE = 4.0                 # outlet centreline, below the barb tip
BULK_HEX_AF = 11.0               # across flats, outside the wall
BULK_BARB_LEN = 12.0             # barb length each side
HOSE_ZONE = 22.0                 # free depth between the bulkhead barbs and PCB-A
GLAND_DIA = 12.5
SWITCH_DIA = 12.0                # 12 mm anti-vandal latching switch, illuminated ring
SWITCH_BODY_DIA = 15.0
SWITCH_BODY_LEN = 22.0
# The switch shares the marked front face with the ports — centred, above the hose
# runs, clear of the corner bosses. The gland goes in the left end wall, in the strip
# beside the hoses. Neither fits on the back wall of a 90 mm-deep box without
# fouling PCB-B.
SWITCH_Z = 44.0
GLAND_Z = 28.0
GLAND_Y = 20.0
GLAND_BODY_LEN = 18.0

# ======================================================================================
# Parts (sizes from the datasheets)
# ======================================================================================
SDP_BODY = (29.0, 18.0, 10.25)          # SDP81x, tube version
SDP_BARB_DIA, SDP_BARB_LEN, SDP_BARB_PITCH = 5.2, 9.65, 12.6
XGZP_SENSOR = (11.0, 10.8, 9.61)        # soldered straight to PCB-A, no carrier board
XGZP_PORT_PITCH = 6.19
MUX = (8.0, 6.5, 1.2)                   # TCA9548A, TSSOP-24
BME = (4.0, 4.0, 1.2)                   # BME280 LGA, with keep-out
PCB_T = 1.6
DISPLAY_PCB = (56.0, 40.0, 1.6)         # NULLLAB 2.0" ST7789 240x320
DISPLAY_GLASS = (49.0, 33.0, 2.6)       # LCD stack above the display PCB
DEVKIT = (55.0, 28.0, 13.0)             # ESP32-WROOM-32 DevKit in a socket strip
MODULE = (18.0, 25.5, 3.1)              # bare ESP32-WROOM-32E soldered to PCB-B

PCB_A_STANDOFF = 4.0                    # floor to PCB-A underside (nothing hangs below it)
TUBE_OD = 8.0                           # 3/16" ID silicone, ~1.5 mm wall
TUBE_MIN_BEND_R = 12.0                  # don't kink it
DISPLAY_STANDOFF = 6.0                  # PCB-B top to display underside (min; raised to clear the MCU)


@dataclass
class Part:
    name: str
    size: tuple[float, float, float]
    pos: tuple[float, float, float]
    color: tuple[float, float, float] = (0.4, 0.5, 0.6)
    note: str = ""

    @property
    def x2(self): return self.pos[0] + self.size[0]
    @property
    def y2(self): return self.pos[1] + self.size[1]
    @property
    def z2(self): return self.pos[2] + self.size[2]

    def solid(self) -> cq.Workplane:
        return cq.Workplane("XY").box(*self.size, centered=False).translate(self.pos)


@dataclass
class Tube:
    """One hose: sensor port -> bulkhead, as a polyline the report can measure."""
    label: str
    points: list[tuple[float, float, float]]
    radius: float = TUBE_OD / 2

    def length(self) -> float:
        return sum(_dist(a, b) for a, b in zip(self.points, self.points[1:]))

    def min_bend_radius(self) -> float:
        best = math.inf
        for a, b, c in zip(self.points, self.points[1:], self.points[2:]):
            best = min(best, _circumradius(a, b, c))
        return best

    def top(self) -> float:
        return max(p[2] for p in self.points) + self.radius

    def solid(self, step: int = 4) -> cq.Workplane:
        # A compound of short cylinders, not a boolean union: building it this way is
        # a few hundred times faster than fusing the segments, and keeps the STEP
        # small. The path is measured at full resolution and only drawn decimated.
        pts = self.points[::step]
        if pts[-1] != self.points[-1]:
            pts.append(self.points[-1])
        segs = []
        for a, b in zip(pts, pts[1:]):
            v = cq.Vector(*b) - cq.Vector(*a)
            if v.Length > 1e-6:
                segs.append(cq.Solid.makeCylinder(self.radius, v.Length, cq.Vector(*a), v))
        return cq.Workplane("XY").add(cq.Compound.makeCompound(segs))


@dataclass
class Design:
    box: Box
    populate: str
    mcu: str
    parts: list[Part] = field(default_factory=list)
    tubes: list[Tube] = field(default_factory=list)
    pcb_b_z: float = 0.0
    fittings: str = "elbow"
    display_standoff: float = DISPLAY_STANDOFF
    switch_z: float = SWITCH_Z
    port_labels: list[tuple[float, float, str]] = field(default_factory=list)   # x, z, label


# ======================================================================================
# helpers
# ======================================================================================
def _dist(a, b) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _circumradius(a, b, c) -> float:
    ab, bc, ca = _dist(a, b), _dist(b, c), _dist(c, a)
    s = (ab + bc + ca) / 2
    area2 = s * (s - ab) * (s - bc) * (s - ca)
    if area2 <= 1e-12:
        return math.inf
    return ab * bc * ca / (4 * math.sqrt(area2))


def _cyl_between(a, b, r) -> cq.Workplane:
    start = cq.Vector(*a)
    v = cq.Vector(*b) - start
    if v.Length < 1e-6:
        return cq.Workplane("XY").sphere(r).translate(a)
    return cq.Workplane("XY").add(cq.Solid.makeCylinder(r, v.Length, start, v))


_cylinder = _cyl_between


def bezier3(p0, p1, p2, p3, n=48) -> list[tuple[float, float, float]]:
    """Cubic Bezier, sampled."""
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append(tuple(u ** 3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t ** 3 * dd
                         for a, b, c, dd in zip(p0, p1, p2, p3)))
    return out


def route_tube(start, start_dir, end, lift_range=range(4, 31, 2), pull_range=range(4, 31, 2)):
    """A hose leaving a sensor along start_dir and arriving at a bulkhead along -Y.

    Tries a family of cubic Beziers: anything that clears the minimum bend radius
    wins on lowest apex (height is what decides the box); if nothing clears it, the
    roundest route wins so the report can say how short it falls.
    """
    n = math.sqrt(sum(c * c for c in start_dir))
    u = tuple(c / n for c in start_dir)
    best = None
    for lift in lift_range:
        p1 = tuple(a + b * lift for a, b in zip(start, u))
        for pull in pull_range:
            p2 = (end[0], end[1] + pull, end[2])
            pts = bezier3(start, p1, p2, end)
            r = min((_circumradius(a, b, c)
                     for a, b, c in zip(pts, pts[1:], pts[2:])), default=math.inf)
            apex = max(p[2] for p in pts)
            ok = r >= TUBE_MIN_BEND_R
            key = (0, round(apex, 2), -r) if ok else (1, -r, round(apex, 2))
            if best is None or key < best[0]:
                best = (key, pts)
    return best[1]


# ======================================================================================
# geometry
# ======================================================================================
def one_row(box: Box) -> bool:
    """One row of 8 needs a wide wall AND makes every hose fan out sideways, which
    costs more bend radius than it saves. Kept behind a flag; two rows always win."""
    return (USE_ONE_ROW
            and (N_PORTS - 1) * PORT_PITCH_1ROW + 2 * PORT_EDGE_KEEPOUT <= box.inside[0])


def port_positions(box: Box, fittings: str = "elbow") -> list[tuple[float, float]]:
    """(x, z) of every bulkhead, row by row (row 0 lowest)."""
    inside_l = box.inside[0]
    if one_row(box):
        span = (N_PORTS - 1) * PORT_PITCH_1ROW
        x0 = (inside_l - span) / 2
        return [(x0 + i * PORT_PITCH_1ROW, PORT_Z[fittings][1]) for i in range(N_PORTS)]
    cols, rows = N_PORTS // 2, PORT_Z[fittings][2]
    span = (cols - 1) * PORT_PITCH_2ROW
    x0 = (inside_l - span) / 2
    return [(x0 + c * PORT_PITCH_2ROW, rows[r]) for r in range(2) for c in range(cols)]


def assign_ports(exits, slots) -> list[int]:
    """Which bulkhead each sensor uses. Exhaustive — there are only 8 holes.

    Cost is the squared sideways + vertical offset the hose has to absorb; the
    depth of the box is fixed, so that is what sets how hard each bend is.
    """
    import itertools
    best, best_cost = None, math.inf
    for perm in itertools.permutations(range(len(slots)), len(exits)):
        cost = sum((e[0] - slots[i][0]) ** 2 + 1.6 * (e[2] - slots[i][1]) ** 2
                   for e, i in zip(exits, perm))
        if cost < best_cost:
            best, best_cost = perm, cost
    return list(best)


def box_shell(box: Box, switch_z: float = SWITCH_Z, fittings: str = "elbow") -> cq.Workplane:
    il, iw, ih = box.inside
    outer = (cq.Workplane("XY").box(*box.out, centered=False)
             .translate((-(box.out[0] - il) / 2, -(box.out[1] - iw) / 2, -WALL)))
    shell = outer.cut(cq.Workplane("XY").box(il, iw, ih + WALL, centered=False))

    for x, y in ((0, 0), (il, 0), (0, iw), (il, iw)):
        boss = cq.Workplane("XY").circle(CORNER_BOSS_R).extrude(ih).translate((x, y, 0))
        shell = shell.union(boss.intersect(cq.Workplane("XY").box(il, iw, ih, centered=False)))

    for (x, z) in port_positions(box, fittings):            # bulkheads through the front wall
        shell = shell.cut(cq.Workplane("XZ").circle(PORT_DIA / 2).extrude(WALL + 4)
                          .translate((x, 2.0, z)))
    # power switch: front wall, centred, above the hose runs — same face as the labels
    shell = shell.cut(cq.Workplane("XZ").circle(SWITCH_DIA / 2).extrude(WALL + 4)
                      .translate((il / 2, 2.0, switch_z)))
    # cable gland: left end wall, clear of the hoses
    shell = shell.cut(cq.Workplane("YZ").circle(GLAND_DIA / 2).extrude(-(WALL + 4))
                      .translate((2.0, GLAND_Y, GLAND_Z)))
    return shell


def bulkhead(box: Box, x: float, z: float) -> cq.Workplane:
    """Barbed bulkhead union: hex outside, barbs both sides."""
    y_wall = -WALL
    body = (cq.Workplane("XZ", origin=(x, y_wall - 3.0, z)).polygon(6, BULK_HEX_AF / math.cos(math.pi / 6))
            .extrude(6.0))
    inner = _cyl_between((x, 0.0, z), (x, BULK_BARB_LEN, z), 2.6)
    outer = _cyl_between((x, y_wall - 3.0, z), (x, y_wall - 3.0 - BULK_BARB_LEN, z), 2.6)
    return body.union(inner).union(outer)


def bulkhead_inner_end(x: float, z: float) -> tuple[float, float, float]:
    return (x, BULK_BARB_LEN, z)


# ======================================================================================
# the stack
# ======================================================================================
def build(populate: str, box_code: str, mcu: str, fittings: str = "elbow") -> Design:
    box = BOXES[box_code]
    il, iw, ih = box.inside
    d = Design(box=box, populate=populate, mcu=mcu, fittings=fittings)

    # ---------------- PCB-A: everything that needs a hose ----------------
    # It sits BACK from the port wall: the strip in front of it is the hose zone,
    # which is what lets each tube make a real 12 mm bend into its bulkhead.
    pa_y = BULK_BARB_LEN + HOSE_ZONE
    pa_w, pa_d = il - 8.0, iw - pa_y - 4.0
    pa_x = (il - pa_w) / 2
    d.parts.append(Part("PCB-A (sensor board)", (pa_w, pa_d, PCB_T), (pa_x, pa_y, PCB_A_STANDOFF),
                        (0.08, 0.32, 0.14), f"screws to the floor on {PCB_A_STANDOFF:.0f} mm standoffs"))
    a_top = PCB_A_STANDOFF + PCB_T
    for sx, sy in ((pa_x + 3, pa_y + 3), (pa_x + pa_w - 3, pa_y + 3),
                   (pa_x + 3, pa_y + pa_d - 3), (pa_x + pa_w - 3, pa_y + pa_d - 3)):
        d.parts.append(Part("standoff", (3.0, 3.0, PCB_A_STANDOFF), (sx - 1.5, sy - 1.5, 0.0),
                            (0.75, 0.7, 0.4)))

    ports: list[tuple[str, tuple[float, float, float]]] = []     # label -> port top, facing up

    # Sensors line up with the port columns: each SDP810 is turned 90 deg so its two
    # barbs are one behind the other at the SAME x as a column of bulkheads, which is
    # what keeps the hoses nearly straight.
    # A two-row wall has four columns of two, so one sensor sits behind one column.
    # A one-row wall spreads the eight holes out, so a two-port sensor straddles the
    # pair of holes it feeds.
    xs = sorted({x for x, _ in port_positions(box, fittings)})
    if one_row(box):
        cols = [(xs[2 * k] + xs[2 * k + 1]) / 2 for k in range(len(xs) // 2)]
    else:
        cols = xs
    sdp = (SDP_BODY[1], SDP_BODY[0], SDP_BODY[2])          # turned 90 deg

    def add_sdp(name, col, labels):
        cx = cols[col]
        bx, by = cx - sdp[0] / 2, pa_y + 3
        d.parts.append(Part(f"SDP810 {name}", sdp, (bx, by, a_top), (0.85, 0.85, 0.88),
                            "turned 90 deg; tube ports face up"))
        cy = by + sdp[1] / 2
        for sign, lab in zip((-1, 1), labels):
            p = (cx, cy + sign * SDP_BARB_PITCH / 2, a_top + sdp[2] + SDP_BARB_LEN)
            d.parts.append(Part(f"barb {name}{sign:+d}", (SDP_BARB_DIA, SDP_BARB_DIA, SDP_BARB_LEN),
                                (p[0] - SDP_BARB_DIA / 2, p[1] - SDP_BARB_DIA / 2,
                                 a_top + sdp[2]), (0.93, 0.78, 0.2)))
            if lab:
                ports.append((lab, p))

    def add_xgzp(name, col, lab, row):
        sx = cols[col] - XGZP_SENSOR[0] / 2
        sy = pa_y + 4 + row * (XGZP_SENSOR[1] + 8)
        d.parts.append(Part(f"XGZP {name} sensor", XGZP_SENSOR, (sx, sy, a_top),
                            (0.3, 0.3, 0.35), "soldered to PCB-A; port faces up"))
        ports.append((lab, (cols[col], sy + XGZP_SENSOR[1] / 2, a_top + XGZP_SENSOR[2])))

    if populate == "laser":
        add_sdp("cyc_dp", 0, ("CYC +", "CYC −"))
        add_sdp("pitot", 1, ("PITOT T", "PITOT S"))
        add_sdp("encl", 2, (None, "ENCL"))
        add_xgzp("bin", 3, "BIN", 0)
        add_xgzp("run_in", 3, "RUN", 1)
    else:
        add_xgzp("fan_in", 0, "FAN IN", 0)

    # ---------------- hoses: sensor port -> bulkhead ----------------
    # With elbows the hose leaves pointing at the wall; without them, straight up.
    # The holes are identical on both boxes, but WHICH hole a sensor uses is free,
    # so pick the assignment with the least sideways and vertical offset — that is
    # what decides whether the hoses bend gently or kink.
    slot_xz = port_positions(box, fittings)
    exits = [(lab, (p[0], p[1] - ELBOW_ARM, p[2] - ELBOW_RISE) if fittings == "elbow" else p)
             for lab, p in ports]
    order = assign_ports([e[1] for e in exits], slot_xz)
    slots = {lab: slot_xz[i] for (lab, _), i in zip(exits, order)}
    used = set(order)
    vent = next(i for i in range(len(slot_xz)) if i not in used)
    wall_labels = ["PLUG"] * len(slot_xz)
    for (lab, _), i in zip(exits, order):
        wall_labels[i] = lab
    wall_labels[vent] = "VENT"
    labels = wall_labels

    for lab, p in ports:
        x, z = slots[lab]
        if fittings == "elbow":
            d.parts.append(Part(f"elbow {lab}", (SDP_BARB_DIA + 2, ELBOW_ARM, SDP_BARB_DIA + 2),
                                (p[0] - (SDP_BARB_DIA + 2) / 2, p[1] - ELBOW_ARM,
                                 p[2] - ELBOW_RISE - (SDP_BARB_DIA + 2) / 2),
                                (0.93, 0.78, 0.2), "push-on 90 deg barbed elbow"))
            start, sdir = (p[0], p[1] - ELBOW_ARM, p[2] - ELBOW_RISE), (0.0, -1.0, 0.0)
        else:
            start, sdir = p, (0.0, 0.0, 1.0)
        d.tubes.append(Tube(lab, route_tube(start, sdir, bulkhead_inner_end(x, z))))

    # ---------------- PCB-B: processor + display hat ----------------
    tube_top = max([t.top() for t in d.tubes], default=a_top)
    sensor_top = max(p.z2 for p in d.parts)
    pcb_b_z = max(tube_top, sensor_top) + 3.0
    d.pcb_b_z = pcb_b_z
    # PCB-B shares PCB-A's outline, so the spacers are a straight vertical stack
    pb_w, pb_d, pb_x, pb_y = pa_w, pa_d, pa_x, pa_y
    d.parts.append(Part("PCB-B (processor + display hat)", (pb_w, pb_d, PCB_T), (pb_x, pb_y, pcb_b_z),
                        (0.10, 0.12, 0.32), "spacers up from PCB-A; display on top"))
    for sx, sy in ((pb_x + 3, pb_y + 3), (pb_x + pb_w - 3, pb_y + 3),
                   (pb_x + 3, pb_y + pb_d - 3), (pb_x + pb_w - 3, pb_y + pb_d - 3)):
        d.parts.append(Part("spacer", (3.0, 3.0, pcb_b_z - PCB_A_STANDOFF - PCB_T),
                            (sx - 1.5, sy - 1.5, PCB_A_STANDOFF + PCB_T), (0.75, 0.7, 0.4)))
    b_top = pcb_b_z + PCB_T

    # The display takes almost the whole depth of PCB-B, so everything else lives in
    # the strip beside it — or, if the MCU is too wide for that, underneath it.
    msz = DEVKIT if mcu == "devkit" else MODULE
    dx, dy = pb_x + 4.0, pb_y + (pb_d - DISPLAY_PCB[1]) / 2
    strip_x, strip_w = dx + DISPLAY_PCB[0] + 3.0, pb_x + pb_w - 3.0 - (dx + DISPLAY_PCB[0] + 3.0)
    side_by_side = msz[0] + 3.0 + MUX[0] <= strip_w        # MCU, then mux and BME
    if side_by_side:
        mx0, my0 = strip_x, pb_y + 2.0
        free_x = strip_x + msz[0] + 3.0
    else:
        dx = pb_x + (pb_w - DISPLAY_PCB[0]) / 2            # MCU tucks under the display
        mx0, my0 = dx + (DISPLAY_PCB[0] - msz[0]) / 2, pb_y + (pb_d - msz[1]) / 2
        strip_x = dx + DISPLAY_PCB[0] + 3.0
        free_x = strip_x
    d.parts.append(Part("ESP32 DevKit (socketed)" if mcu == "devkit" else "ESP32-WROOM-32E (soldered)",
                        msz, (mx0, my0, b_top), (0.15, 0.15, 0.2),
                        "beside the display" if side_by_side else "under the display"))
    # neither of these needs a hose, so they ride on PCB-B
    if populate == "laser":
        d.parts.append(Part("TCA9548A mux", MUX, (free_x, pb_y + 3.0, b_top),
                            (0.2, 0.5, 0.25), "I2C multiplexer — the sensors share one address"))
    d.parts.append(Part("BME280", BME, (free_x, pb_y + pb_d - BME[1] - 3.0, b_top),
                        (0.2, 0.5, 0.25), "box air: density correction"))

    stand = DISPLAY_STANDOFF if side_by_side else max(DISPLAY_STANDOFF, msz[2] + 1.5)
    d.display_standoff = stand
    dz = b_top + stand
    d.parts.append(Part("2.0\" ST7789 display", DISPLAY_PCB, (dx, dy, dz), (0.15, 0.2, 0.3),
                        f"on {stand:.1f} mm standoffs; reads through the clear lid"))
    d.parts.append(Part("display glass", DISPLAY_GLASS,
                        (dx + 3.5, dy + 3.5, dz + PCB_T), (0.05, 0.05, 0.08)))

    # ---------------- power switch and cable gland ----------------
    # The switch sits on the front face above the hose runs, so every marking Lee
    # engraves is on one panel; the gland goes in the end wall, out of the hose zone.
    sz = max(SWITCH_Z, max((t.top() for t in d.tubes), default=0) + SWITCH_BODY_DIA / 2 + 3.0)
    d.switch_z = sz
    d.parts.append(Part("latching switch body", (SWITCH_BODY_DIA, SWITCH_BODY_LEN, SWITCH_BODY_DIA),
                        (il / 2 - SWITCH_BODY_DIA / 2, 0.0, sz - SWITCH_BODY_DIA / 2),
                        (0.55, 0.55, 0.6),
                        "Ø12 mm illuminated latching push button — the ring is the power LED"))
    d.parts.append(Part("cable gland body", (GLAND_BODY_LEN, GLAND_DIA + 3, GLAND_DIA + 3),
                        (0.0, GLAND_Y - (GLAND_DIA + 3) / 2, GLAND_Z - (GLAND_DIA + 3) / 2),
                        (0.35, 0.35, 0.38), "USB supply lead, left end wall"))
    d.port_labels = [(x, z, lab) for lab, (x, z) in zip(labels, port_positions(box, fittings))]
    return d


# ======================================================================================
# checks
# ======================================================================================
def _mates(a: str, b: str) -> bool:
    """Parts that are meant to touch: a sensor and its barb, a barb and its elbow."""
    pairs = (("SDP810", "barb"), ("module", "sensor"), ("barb", "elbow"),
             ("sensor", "elbow"), ("SDP810", "elbow"))
    return any((x in a and y in b) or (x in b and y in a) for x, y in pairs)


def report(d: Design) -> tuple[str, bool]:
    il, iw, ih = d.box.inside
    ok = True
    L: list[str] = []
    L.append(f"LumosAir stacked node — {d.populate} box, {d.box.code}, MCU: {d.mcu}")
    L.append(f"outside {d.box.out[0]:.0f} x {d.box.out[1]:.0f} x {d.box.out[2]:.1f} mm, "
             f"inside {il:.1f} x {iw:.1f} x {ih:.1f} mm\n")

    L.append("Stack")
    L.append(f"  PCB-A underside       {PCB_A_STANDOFF:5.1f} mm (standoffs off the floor)")
    L.append(f"  PCB-B underside       {d.pcb_b_z:5.1f} mm (spacers off PCB-A)")
    tallest = max(d.parts, key=lambda p: p.z2)
    L.append(f"  tallest item          {tallest.z2:5.1f} mm  ({tallest.name})")
    head = ih - tallest.z2
    L.append(f"  headroom under lid    {head:5.1f} mm")
    if head < 2:
        ok = False
        L.append("  ** the stack does not fit under the lid **")

    L.append("\nParts")
    for p in sorted(d.parts, key=lambda p: (p.pos[2], p.name)):
        if p.name in ("standoff", "spacer"):
            continue
        L.append(f"  {p.name:34} x {p.pos[0]:6.1f}–{p.x2:6.1f}  y {p.pos[1]:6.1f}–{p.y2:6.1f}"
                 f"  z {p.pos[2]:5.1f}–{p.z2:5.1f}")

    L.append("\nHoses (sensor port -> bulkhead, inside the box)")
    if not d.tubes:
        L.append("  none")
    for t in d.tubes:
        r = t.min_bend_radius()
        flag = "" if r >= TUBE_MIN_BEND_R else "  ** tighter than %.0f mm **" % TUBE_MIN_BEND_R
        if r < TUBE_MIN_BEND_R:
            ok = False
        L.append(f"  {t.label:9} length {t.length():5.1f} mm   min bend R {r:5.1f} mm"
                 f"   highest point {t.top():5.1f} mm{flag}")
    if d.tubes:
        worst = min(t.min_bend_radius() for t in d.tubes)
        clear = d.pcb_b_z - max(t.top() for t in d.tubes)
        L.append(f"  tightest bend {worst:.1f} mm; clearance from the tubes to PCB-B {clear:.1f} mm")
        if clear < 1.0:
            ok = False
            L.append("  ** PCB-B would sit on the hoses **")

    L.append("\nCollisions")
    clashes = 0
    interesting = [p for p in d.parts if p.name not in ("standoff", "spacer")]
    for i, a in enumerate(interesting):
        for b in interesting[i + 1:]:
            ox = min(a.x2, b.x2) - max(a.pos[0], b.pos[0])
            oy = min(a.y2, b.y2) - max(a.pos[1], b.pos[1])
            oz = min(a.z2, b.z2) - max(a.pos[2], b.pos[2])
            if ox > 0.5 and oy > 0.5 and oz > 0.5:
                if b.pos[2] >= a.z2 - 0.2 or a.pos[2] >= b.z2 - 0.2:
                    continue
                if _mates(a.name, b.name):
                    continue
                clashes += 1
                ok = False
                L.append(f"  ** {a.name} ∩ {b.name}: {ox:.1f} x {oy:.1f} x {oz:.1f} mm **")
    if clashes == 0:
        L.append("  none")

    if one_row(d.box):
        pattern = (f"one row of {N_PORTS} at {PORT_PITCH_1ROW:.0f} mm pitch, "
                   f"z = {PORT_Z[d.fittings][1]:.0f} mm")
    else:
        rows = PORT_Z[d.fittings][2]
        pattern = (f"two rows of {N_PORTS // 2} at {PORT_PITCH_2ROW:.0f} mm pitch, "
                   f"z = {rows[0]:.0f} and {rows[1]:.0f} mm")
    L.append("\nBulkheads (identical on both boxes)")
    L.append(f"  {N_PORTS} x Ø{PORT_DIA:.0f} mm — {pattern}")
    for x, z, lab in d.port_labels:
        L.append(f"    x {x:6.1f}  z {z:4.1f}   {lab}")
    L.append(f"  gland Ø{GLAND_DIA} mm at y {GLAND_Y:.0f}, z {GLAND_Z:.0f} (left end wall)")
    L.append(f"  switch Ø{SWITCH_DIA} mm at x {il / 2:.1f}, z {d.switch_z:.0f} (front wall, above the ports)")

    lid_area = d.box.out[0] * d.box.out[1] / 100.0
    disp = DISPLAY_PCB[0] * DISPLAY_PCB[1] / 100.0
    pcb_b = next(p for p in d.parts if p.name.startswith("PCB-B"))
    L.append("\nHow much bigger is the box than the display?")
    L.append(f"  lid           {lid_area:5.1f} cm²")
    L.append(f"  PCB-B         {pcb_b.size[0] * pcb_b.size[1] / 100:5.1f} cm² "
             f"({pcb_b.size[0] * pcb_b.size[1] / (d.box.out[0] * d.box.out[1]):.0%} of the lid)")
    L.append(f"  display       {disp:5.1f} cm² ({disp / lid_area:.0%} of the lid)")

    L.append("\nNotes")
    L.append("  • PCB-A carries everything with a hose; its sensor ports face UP.")
    L.append("  • Each hose is a short silicone tube from a sensor port to one bulkhead.")
    L.append("  • The VENT port keeps the box interior at room pressure, which is the")
    L.append("    reference side for the bin, run and enclosure channels — so those")
    L.append("    sensors need only one tube each.")
    L.append("  • The lid is clear, so the display needs no cut-out.")
    L.append("  • Verify the floor boss pattern for this box size before drilling PCB-A.")
    return "\n".join(L), ok


def compare() -> str:
    rows = ["box         outside (mm)     mcu     fittings  tallest  headroom  tightest bend  fits",
            "-" * 92]
    for code in ("F", "G", "J", "H"):
        b = BOXES[code]
        for mcu in ("module", "devkit"):
            for fit in ("elbow", "straight"):
                d = build("laser", code, mcu, fit)
                _, ok = report(d)
                ih = d.box.inside[2]
                tallest = max(p.z2 for p in d.parts)
                bend = min((t.min_bend_radius() for t in d.tubes), default=math.inf)
                rows.append(f"{b.code:11} {b.out[0]:4.0f}x{b.out[1]:.0f}x{b.out[2]:.1f}  {mcu:8}{fit:10}"
                            f"{tallest:7.1f} {ih - tallest:9.1f} {bend:14.1f}   {'yes' if ok else 'NO'}")
    rows.append("")
    rows.append("Read it as: elbows on the sensor barbs are what let the hoses run almost")
    rows.append("straight to the wall, and that is what lets the box be the small one.")
    return "\n".join(rows)


def pick_box(populate: str, mcu: str, fittings: str = "elbow") -> str:
    """Smallest box (by volume) that passes every check."""
    for code in sorted(BOXES, key=lambda c: BOXES[c].out[0] * BOXES[c].out[1] * BOXES[c].out[2]):
        if report(build(populate, code, mcu, fittings))[1]:
            return code
    return "H"


# ======================================================================================
# exports
# ======================================================================================
def assembly(d: Design) -> cq.Assembly:
    asm = cq.Assembly(name=f"LumosAir {d.populate} node")
    asm.add(box_shell(d.box, d.switch_z, d.fittings), name="enclosure", color=cq.Color(0.55, 0.55, 0.58, 0.35))
    il, iw, ih = d.box.inside
    asm.add(cq.Workplane("XY").box(d.box.out[0], d.box.out[1], LID_T, centered=False)
            .translate((-(d.box.out[0] - il) / 2, -(d.box.out[1] - iw) / 2, ih)),
            name="clear lid", color=cq.Color(0.8, 0.85, 0.9, 0.25))
    for x, z, lab in d.port_labels:
        asm.add(bulkhead(d.box, x, z), name=f"bulkhead {lab} @{x:.0f},{z:.0f}", color=cq.Color(0.7, 0.68, 0.6))
    for i, p in enumerate(d.parts):
        asm.add(p.solid(), name=f"{p.name} #{i}", color=cq.Color(*p.color))
    for t in d.tubes:
        asm.add(t.solid(), name=f"hose {t.label}", color=cq.Color(0.9, 0.55, 0.2, 0.9))
    return asm


def export_drill_template(d: Design, out: Path) -> None:
    il, iw, ih = d.box.inside
    wall = cq.Workplane("XY").box(d.box.out[0], d.box.out[2], 1.0, centered=False)
    for x, z, _ in d.port_labels:
        wall = wall.cut(cq.Workplane("XY").circle(PORT_DIA / 2).extrude(2)
                        .translate((x + (d.box.out[0] - il) / 2, z + WALL, 0)))
    cq.exporters.export(wall, str(out / "drill_template_front.svg"), exportType="SVG",
                        opt={"width": 900, "height": 500, "projectionDir": (0, 0, 1),
                             "showAxes": False, "strokeWidth": 0.4})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--populate", choices=["laser", "fan"], default="laser")
    ap.add_argument("--box", choices=list(BOXES) + ["auto"], default="auto")
    ap.add_argument("--mcu", choices=["devkit", "module"], default="module")
    ap.add_argument("--fittings", choices=["elbow", "straight"], default="elbow")
    ap.add_argument("--compare", action="store_true", help="print the box comparison and exit")
    ap.add_argument("--out", default=str(Path(__file__).parent / "out"))
    args = ap.parse_args()

    if args.compare:
        print(compare())
        return 0

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    code = pick_box(args.populate, args.mcu, args.fittings) if args.box == "auto" else args.box
    d = build(args.populate, code, args.mcu, args.fittings)
    text, ok = report(d)
    print(text)
    (out / f"fitment_report_{args.populate}.txt").write_text(text + "\n", encoding="utf-8")

    stem = f"lumosair_{args.populate}_{code}_{args.mcu}"
    asm = assembly(d)
    cq.exporters.export(asm.toCompound(), str(out / f"{stem}.step"))
    cq.exporters.export(asm.toCompound(), str(out / f"{stem}.stl"))
    export_drill_template(d, out)
    print(f"\nWrote {stem}.step / .stl and drill_template_front.svg to {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
