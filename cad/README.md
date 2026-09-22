# Enclosure fitment model

Both nodes use the **same box with the same eight bulkheads** — the fan box just
plugs the ones it doesn't use. The model is a script, so moving a part is a one-line
change and the drawings, the STEP file, the panel artwork, the PCB outlines and the
clearance report all follow.

```
pip install cadquery matplotlib
python cad/enclosure.py                     # STEP + STL + fitment report (picks the box)
python cad/enclosure.py --populate fan      # the fan box's population
python cad/enclosure.py --compare           # which box fits, and why
python cad/artwork.py                       # 1:1 panel artwork + KiCad board outlines
python cad/render.py                        # shaded PNGs for the docs
```

Everything lands in `cad/out/`:

| File | What it's for |
|---|---|
| `lumosair_laser_F_module.step` / `.stl` | open in FreeCAD / Fusion / Blender |
| `render_iso.png`, `render_top.png`, `render_front.png`, `render_side.png` | the pictures in the docs |
| `panel_front_laser.svg`, `panel_front_fan.svg` | 1:1 laser-marking artwork for the port face |
| `panel_end.svg` | the end wall (cable gland) |
| `drill_template_front.svg` | 1:1 hole pattern with crosshairs |
| `pcb_a_outline.dxf`, `pcb_b_outline.dxf` | board edge + M3 mounting holes, for KiCad |
| `fitment_report_laser.txt` | part positions, hose lengths, bend radii, clearances, collisions |

![Isometric](out/render_iso.png)

## The box

Hammond **1554F2GYCL**: 120 × 90 × 60.5 mm outside, ~113 × 79 × 54.5 inside, 3 mm
walls, **clear polycarbonate lid**. The clear lid is why the display needs no
cut-out — it sits on standoffs facing up and reads through the lid, which keeps the
box sealed.

Only the 1554H has a confirmed drawing in `docs/datasheets/`; the others use the
same wall and flange offsets, so treat their insides as ±1 mm and check before you
drill.

## The stack

```
floor ── 4 mm standoffs ── PCB-A   every part that needs a hose, ports facing UP
                             │     hose zone: eight silicone runs, 6 → 31 mm
      ── 28 mm spacers ──── PCB-B   ESP32 + mux + BME280
                             │
      ── 6 mm standoffs ─── display reading up through the clear lid
                                    ~9 mm spare under the lid
```

| Board | Size | Carries |
|---|---|---|
| PCB-A | 105 × 41 mm | 3 × SDP810 (turned 90°), 2 × XGZP6897D soldered direct |
| PCB-B | 105 × 41 mm | ESP32-WROOM-32E, TCA9548A, BME280, the display on standoffs |

Both boards share an outline and a mounting pattern, so the spacers are one straight
vertical stack — see the two DXFs.

## How the hoses connect

Each SDP810 is turned 90° so its two barbs line up behind one column of bulkheads. A
**push-on 90° barbed elbow** on each barb turns the hose to point at the wall, and
from there it's a short, nearly straight run to its bulkhead.

That elbow is what makes the small box possible. `--compare`:

| fittings | tallest item | headroom in the 1554F | tightest bend |
|---|---|---|---|
| 90° elbows | 51.5 mm | 3.0 mm | 13.1 mm — fits |
| straight onto the barb | 65.1 mm | −10.6 mm | 3.3 mm — kinks |

A hose leaving a barb straight up has to climb a full bend radius before it can turn
into a wall port, which pushes the ports 25 mm higher and the lid with them.

Which sensor gets which hole is chosen by the model, not fixed: it tries every
assignment and keeps the one with the least sideways and vertical offset. The
labels follow, which is why the panel artwork is generated rather than drawn.

![Front view](out/render_front.png)

## Port assignments

Eight Ø8 mm holes, two rows of four, 22 mm pitch, rows at z = 13 and 27 mm.

| Column | Laser box (lower / upper) | Fan box |
|---|---|---|
| 1 | CYC + / CYC − | FAN IN / plug |
| 2 | PITOT T / PITOT S | plugs |
| 3 | VENT / ENCL | VENT / plug |
| 4 | BIN / RUN | plugs |

**VENT** is an open port that keeps the box interior at room pressure. That's the
reference side for the bin, run and enclosure channels, so each of those needs only
one hose.

A Ø12 mm illuminated latching push button sits centred on the same panel above the
hoses — power switch and power-on indicator in one hole. The Ø12.5 mm cable gland
is in the left end wall.

## Marking and drilling

`artwork.py` writes 1:1 SVG at true millimetre scale. Red (`#ff0000`) is
cut/drill, black is engrave; most laser software maps colour to operation.

![Panel](out/panel_front_laser.svg)

`drill_template_front.svg` is the same holes with crosshairs and a 100 mm check bar
— print it, check the bar, tape it on, centre-punch.

## Checking a change

`fitment_report_laser.txt` lists every part's extent, the headroom, each hose's
length and bend radius, and any collisions. `enclosure.py` exits non-zero when
something doesn't fit, so it can sit in a build script.
