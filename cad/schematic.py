"""
PCB-A (sensor board) schematic: one source for the drawing and the netlist.

    python cad/schematic.py        # -> docs/pcb-a/pcb_a_schematic.svg + pcb_a_netlist.md

The drawing is net-label style: every pin ends in the name of the net it belongs to,
and pins with the same net name are connected. That is how you would enter it in
Proteus (or any EDA tool) anyway, and it can't disagree with the netlist, because
both are printed from the PARTS table below. Standard library only.

Pin numbers for the SDP810 are from the Sensirion SDP8xx-Digital datasheet v1.1,
Table 1 (bottom view): 1 SCL, 2 VDD, 3 GND, 4 SDA. Modules (TCA9548A, BME280,
XGZP6897D) are shown by their silkscreen names; take their footprints from the
boards you actually have.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "pcb-a"


@dataclass
class Pin:
    num: str
    name: str
    net: str
    side: str = "L"          # L or R


@dataclass
class Comp:
    ref: str
    value: str
    x: float
    y: float
    pins: list[Pin]
    note: str = ""
    fit: str = "fit"         # fit / DNP / option
    w: float = 150.0


def P(num, name, net, side="L"):
    return Pin(str(num), name, net, side)


# --------------------------------------------------------------------------------------
# The board. Nets in capitals; +3V3 / +5V / GND are the rails.
# --------------------------------------------------------------------------------------
SDP = [("U1", "SDP810 cyc_dp", 0), ("U2", "SDP810 pitot", 2), ("U3", "SDP810 encl", 4)]
XGZ = [("U4", "XGZP6897D bin", 1), ("U5", "XGZP6897D run_in (fan box: fan_in)", 3)]

PARTS: list[Comp] = [
    # ---- power in (optional path) ----
    Comp("J1", "5V IN, 2-pin", 40, 60, [P(1, "+5V", "+5V_IN", "R"), P(2, "GND", "GND", "R")],
         "From the USB-C POWER socket (2-wire). Leave J1/F1/D1 off if the box is powered "
         "through the ESP32 board's own USB port.", "option", w=110),
    Comp("F1", "PTC fuse 0.5 A hold", 240, 60, [P(1, "", "+5V_IN"), P(2, "", "+5V", "R")],
         "e.g. MF-R050 / 1206L050. Trips if the 10 V fan lead goes into the power socket.",
         "option", w=120),
    Comp("D1", "SMBJ5.0A TVS", 240, 130, [P("K", "K", "+5V"), P("A", "A", "GND", "R")],
         "Clamps >5.6 V on +5V so F1 trips; cathode to +5V.", "option", w=120),
    Comp("C1", "10 uF", 420, 60, [P(1, "", "+5V"), P(2, "", "GND", "R")], "5 V bulk", w=90),
    Comp("C2", "10 uF", 420, 130, [P(1, "", "+3V3"), P(2, "", "GND", "R")], "3.3 V bulk", w=90),

    # ---- link to the ESP32 board ----
    Comp("J2", "ESP32 link, 8-pin 2.54", 40, 230, [
        P(1, "+5V", "+5V", "R"), P(2, "GND", "GND", "R"), P(3, "3V3", "+3V3", "R"),
        P(4, "GPIO21", "SDA", "R"), P(5, "GPIO22", "SCL", "R"),
        P(6, "GPIO33", "FAN_SENSE", "R"), P(7, "GPIO25", "FAN_CTRL", "R"),
        P(8, "GND", "GND", "R")],
        "Wires to the ESP32 board: 5V, GND, 3V3, P21, P22, P33, P25 terminals. "
        "Pin 1 +5V is fed FROM the ESP32 board when J1 is not fitted.", w=150),

    # ---- I2C mux ----
    Comp("U6", "TCA9548A breakout (0x70)", 330, 230, [
        P("VIN", "VIN", "+3V3"), P("GND", "GND", "GND"), P("SDA", "SDA", "SDA"),
        P("SCL", "SCL", "SCL"), P("RST", "RST", "+3V3"),
        P("A0", "A0", "GND"), P("A1", "A1", "GND"), P("A2", "A2", "GND"),
        P("SD0", "SD0", "SDA0", "R"), P("SC0", "SC0", "SCL0", "R"),
        P("SD1", "SD1", "SDA1", "R"), P("SC1", "SC1", "SCL1", "R"),
        P("SD2", "SD2", "SDA2", "R"), P("SC2", "SC2", "SCL2", "R"),
        P("SD3", "SD3", "SDA3", "R"), P("SC3", "SC3", "SCL3", "R"),
        P("SD4", "SD4", "SDA4", "R"), P("SC4", "SC4", "SCL4", "R"),
        P("SD5", "SD5", "SDA5", "R"), P("SC5", "SC5", "SCL5", "R")],
        "A0-A2 low = 0x70. Breakout already has 10k pull-ups on SDA/SCL and RST. "
        "SD6/SC6/SD7/SC7 unused.", w=170),
    Comp("C3", "100 nF", 330, 500, [P(1, "", "+3V3"), P(2, "", "GND", "R")], "at U6 VIN", w=90),

    # ---- BME280 on the main bus ----
    Comp("U7", "GY-BME280 3.3 V (0x76)", 330, 580, [
        P("VIN", "VIN", "+3V3"), P("GND", "GND", "GND"),
        P("SCL", "SCL", "SCL"), P("SDA", "SDA", "SDA")],
        "Main bus, not behind the mux. Keep it away from the ESP32 and the regulator.", w=170),

    # ---- spare mux channel ----
    Comp("J4", "Spare I2C ch5, 4-pin", 330, 700, [
        P(1, "3V3", "+3V3"), P(2, "GND", "GND"), P(3, "SDA", "SDA5"), P(4, "SCL", "SCL5")],
        "Unpopulated header for a future sensor.", "option", w=170),

    # ---- pull-ups on the XGZP channels go to the XGZP rail ----
    Comp("JP1", "XGZP supply select, 3-pin", 40, 520, [
        P(1, "3V3", "+3V3", "R"), P(2, "COM", "XGZP_VCC", "R"), P(3, "5V", "+5V", "R")],
        "Jumper 1-2 for a 3.3 V XGZP (part no. ends in 33), 2-3 for the default 5 V part. "
        "Sets both XGZP supplies AND their channel pull-ups; the TCA9548A translates.", w=150),
]

# sensors + their pull-ups + decoupling
y0 = 60
for i, (ref, val, ch) in enumerate(SDP):
    y = y0 + i * 150
    PARTS.append(Comp(ref, val, 700, y, [
        P(1, "SCL", f"SCL{ch}"), P(2, "VDD", "+3V3"), P(3, "GND", "GND"), P(4, "SDA", f"SDA{ch}")],
        f"0x25 on mux ch{ch}. Pins per datasheet Table 1 (BOTTOM view).", w=150))
    PARTS.append(Comp(f"R{10 + 2 * i}", "4.7k", 900, y, [P(1, "", "+3V3"), P(2, "", f"SDA{ch}", "R")],
                      f"ch{ch} SDA pull-up", w=90))
    PARTS.append(Comp(f"R{11 + 2 * i}", "4.7k", 900, y + 52, [P(1, "", "+3V3"), P(2, "", f"SCL{ch}", "R")],
                      f"ch{ch} SCL pull-up", w=90))
    PARTS.append(Comp(f"C{4 + i}", "100 nF", 1110, y, [P(1, "", "+3V3"), P(2, "", "GND", "R")],
                      f"at {ref} VDD", w=90))
for i, (ref, val, ch) in enumerate(XGZ):
    y = y0 + (3 + i) * 150
    PARTS.append(Comp(ref, val, 700, y, [
        P("VCC", "VCC", "XGZP_VCC"), P("GND", "GND", "GND"),
        P("SCL", "SCL", f"SCL{ch}"), P("SDA", "SDA", f"SDA{ch}")],
        f"0x6D on mux ch{ch}. Module pins by silkscreen; check before the footprint.", w=150))
    PARTS.append(Comp(f"R{16 + 2 * i}", "4.7k", 900, y, [P(1, "", "XGZP_VCC"), P(2, "", f"SDA{ch}", "R")],
                      f"ch{ch} SDA pull-up; DNP if the module has its own", "option", w=90))
    PARTS.append(Comp(f"R{17 + 2 * i}", "4.7k", 900, y + 52, [P(1, "", "XGZP_VCC"), P(2, "", f"SCL{ch}", "R")],
                      f"ch{ch} SCL pull-up; DNP if the module has its own", "option", w=90))
    PARTS.append(Comp(f"C{7 + i}", "100 nF", 1110, y, [P(1, "", "XGZP_VCC"), P(2, "", "GND", "R")],
                      f"at {ref} VCC", w=90))

# ---- fan (UIS) interface: isolated, on its own ground ----
FY = 880
PARTS += [
    Comp("J3", "UIS fan lead, 4-way screw terminal", 40, FY, [
        P(1, "V+", "UIS_V+", "R"), P(2, "GND", "UIS_GND", "R"),
        P(3, "CTRL", "UIS_CTRL", "R"), P(4, "SPARE", "UIS_SPARE", "R")],
        "Wires from the USB-C FAN socket / cut UIS cable. Which UIS contact is which is NOT "
        "verified: meter it and land each wire on its function here. UIS_GND is NOT board GND.",
        w=190),
    Comp("R1", "2.2k", 330, FY, [P(1, "", "UIS_V+"), P(2, "", "OK1_A", "R")],
         "LED current ~4 mA at 10 V", w=90),
    Comp("D2", "1N4148", 330, FY + 60, [P("K", "K", "OK1_A"), P("A", "A", "UIS_GND", "R")],
         "Reverse-polarity guard across the LED (anode to UIS_GND)", w=90),
    Comp("OK1", "PC817 (fan sense)", 520, FY, [
        P(1, "A", "OK1_A"), P(2, "K", "UIS_GND"),
        P(4, "C", "FAN_SENSE", "R"), P(3, "E", "GND", "R")],
        "FAN_SENSE reads LOW when a fan lead with its rail is plugged in (DESIGN 6a step 1).",
        w=150),
    Comp("R2", "10k", 790, FY, [P(1, "", "+3V3"), P(2, "", "FAN_SENSE", "R")], "pull-up", w=90),
    Comp("C9", "100 nF", 790, FY + 60, [P(1, "", "FAN_SENSE"), P(2, "", "GND", "R")],
         "filter; optional", "option", w=90),
    Comp("R3", "330", 330, FY + 150, [P(1, "", "FAN_CTRL"), P(2, "", "OK2_A", "R")],
         "~6 mA from GPIO25", "DNP", w=90),
    Comp("OK2", "PC817 (fan control)", 520, FY + 150, [
        P(1, "A", "OK2_A"), P(2, "K", "GND"),
        P(4, "C", "UIS_CTRL", "R"), P(3, "E", "UIS_GND", "R")],
        "DO NOT FIT until the UIS pinout and signalling are verified "
        "(FAN_OUTPUT_ENABLED stays False).", "DNP", w=150),
]

# mounting holes
for i in range(4):
    PARTS.append(Comp(f"H{i + 1}", "M3 mounting hole", 990 + (i % 2) * 180, 900 + (i // 2) * 70,
                      [P(1, "", "GND" if i == 0 else "NC")],
                      "H1 to GND (shield); others isolated", w=100))


# ======================================================================================
# output
# ======================================================================================
PITCH = 18
RAILS = {"+3V3": "#c0392b", "+5V": "#d35400", "XGZP_VCC": "#8e44ad", "GND": "#2c3e50",
         "UIS_GND": "#16a085", "UIS_V+": "#16a085"}


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def draw() -> str:
    W, H = 1400, 1200
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" font-family="Consolas, monospace" font-size="11">',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
         '<text x="20" y="28" font-size="18" font-weight="700">LumosAir PCB-A (sensor board) '
         '- net-label schematic</text>',
         '<text x="20" y="44" fill="#555">Pins with the same net name are connected. '
         'Grey = option, red dashed = do not fit. Generated by cad/schematic.py.</text>']
    for sec, (x, y, w, h) in {"POWER IN (optional) + BULK": (20, 50, 520, 150),
                             "ESP32 LINK / I2C MUX / BME280": (20, 205, 560, 580),
                             "PRESSURE SENSORS (each on its own mux channel)": (640, 50, 740, 800),
                             "FAN (UIS) INTERFACE - isolated": (20, 850, 950, 330)}.items():
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="#bbb" '
                 f'stroke-dasharray="4 3"/>')
        o.append(f'<text x="{x + 6}" y="{y + 14}" fill="#888" font-size="10">{esc(sec)}</text>')

    for c in PARTS:
        left = [p for p in c.pins if p.side == "L"]
        right = [p for p in c.pins if p.side == "R"]
        rows = max(len(left), len(right), 1)
        bx, by = c.x + 60, c.y + 22
        bh = rows * PITCH + 8
        stroke = {"fit": "#222", "option": "#999", "DNP": "#c0392b"}[c.fit]
        dash = ' stroke-dasharray="5 3"' if c.fit == "DNP" else ""
        o.append(f'<rect x="{bx}" y="{by}" width="{c.w - 60}" height="{bh}" fill="#fafafa" '
                 f'stroke="{stroke}" stroke-width="1.4"{dash}/>')
        o.append(f'<text x="{bx}" y="{by - 12}" font-weight="700">{esc(c.ref)}</text>')
        o.append(f'<text x="{bx}" y="{by - 2}" fill="#444" font-size="10">{esc(c.value)}</text>')
        for side, pins in (("L", left), ("R", right)):
            for k, p in enumerate(pins):
                py = by + 13 + k * PITCH
                colour = RAILS.get(p.net, "#1f5fa8")
                if side == "L":
                    x0, x1 = bx - 22, bx
                    o.append(f'<line x1="{x0}" y1="{py}" x2="{x1}" y2="{py}" stroke="#222"/>')
                    o.append(f'<text x="{x0 - 3}" y="{py + 4}" text-anchor="end" fill="{colour}" '
                             f'font-weight="700">{esc(p.net)}</text>')
                    o.append(f'<text x="{x0 + 2}" y="{py - 2}" font-size="8" fill="#777">{esc(p.num)}</text>')
                    if p.name:
                        o.append(f'<text x="{bx + 3}" y="{py + 4}" font-size="9">{esc(p.name)}</text>')
                else:
                    x0, x1 = bx + c.w - 60, bx + c.w - 38
                    o.append(f'<line x1="{x0}" y1="{py}" x2="{x1}" y2="{py}" stroke="#222"/>')
                    o.append(f'<text x="{x1 + 3}" y="{py + 4}" fill="{colour}" '
                             f'font-weight="700">{esc(p.net)}</text>')
                    o.append(f'<text x="{x0 + 2}" y="{py - 2}" font-size="8" fill="#777">{esc(p.num)}</text>')
                    if p.name:
                        o.append(f'<text x="{x0 - 3}" y="{py + 4}" text-anchor="end" '
                                 f'font-size="9">{esc(p.name)}</text>')
    o.append("</svg>")
    return "\n".join(o)


def netlist() -> str:
    nets: dict[str, list[str]] = {}
    for c in PARTS:
        for p in c.pins:
            if p.net != "NC":
                nets.setdefault(p.net, []).append(f"{c.ref}.{p.num}" + (f" ({p.name})" if p.name else ""))
    L = ["# PCB-A netlist", "",
         "Generated by `cad/schematic.py` from the same table as the drawing. "
         "Do not edit by hand.", "",
         "## Nets", "", "| Net | Connects |", "|---|---|"]
    for n in sorted(nets, key=lambda n: (n not in RAILS, n)):
        L.append(f"| `{n}` | {', '.join(nets[n])} |")
    L += ["", "## Parts", "", "| Ref | Value | Fit | Pins → net | Notes |", "|---|---|---|---|---|"]
    order = lambda c: ("JUHDFCROKP".find(c.ref.rstrip("0123456789")[0]), int("".join(ch for ch in c.ref if ch.isdigit()) or 0))
    for c in sorted(PARTS, key=order):
        pins = "; ".join(f"{p.num}{'/' + p.name if p.name and p.name != p.num else ''} → {p.net}"
                         for p in c.pins)
        L.append(f"| {c.ref} | {c.value} | {c.fit} | {pins} | {c.note} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pcb_a_schematic.svg").write_text(draw(), encoding="utf-8")
    (OUT / "pcb_a_netlist.md").write_text(netlist(), encoding="utf-8")
    print("wrote", OUT / "pcb_a_schematic.svg")
    print("wrote", OUT / "pcb_a_netlist.md")
