# LumosAir node firmware (MicroPython)

Runs on an ESP32-WROOM-32. Both boxes run this same code; `config.py` is the only
difference between them.

```
main.py                 entry point, runs on boot
config_example.py       copy to config.py and edit (git-ignored)
lib/lumosair/
  sensors.py            SDP8xx, XGZP6897D, BME280, TCA9548A
  st7789.py             2.0" 240x320 display driver (stripe buffer + 7-segment)
  display_ui.py         what the box screen shows
  net.py                Wi-Fi, UDP telemetry/commands/status, optional MQTT
  fan.py                fan level output (disabled until the UIS pinout is verified)
  ota.py                pull updates over Wi-Fi
  node.py               sampling loop and command handling
  benchsim.py           bench mode: model-predicted readings when no sensors are wired
tools/upload.py         copy the firmware to a board over USB (mpremote)
tools/serve_update.py   serve this folder to the nodes for OTA
tools/send_command.py   zero / set_level / update / watch telemetry from a PC
tools/simulate_node.py  run a node on the PC and render its screen to a PNG
tests/test_firmware.py  host tests (plain CPython, no hardware)
```

## Set up VS Code

1. `mpremote` does everything from the terminal; the **MicroPico** extension is optional.
2. Flash MicroPython once over USB:
   ```
   pip install esptool mpremote
   esptool --chip esp32 --port COM5 erase-flash
   esptool --chip esp32 --port COM5 write-flash -z 0x1000 ESP32_GENERIC-<version>.bin
   ```
   esptool 5.x spells these with hyphens; the old `erase_flash` / `write_flash`
   are deprecated. Find the port with `python -m serial.tools.list_ports -v`:
   the board shows as a CP210x (VID 10C4) or CH340 (VID 1A86). If nothing new
   appears when you plug it in, suspect a charge-only cable first.
3. Copy `config_example.py` to `config.py`, set your Wi-Fi, node id and channel map.
   On the bench set `WATCHDOG_MS = 0`: once started, the ESP32 watchdog can't be
   stopped, so it resets the board 20 s after you break into the REPL.
4. Upload:
   ```
   python tools/upload.py --port COM5
   ```
   It copies `lib/`, `config.py` and `main.py` (last), skips `__pycache__` and files
   that haven't changed, then resets. In VS Code: *Run Task → device: upload firmware (USB)*.
5. `mpremote connect COM5 repl` (or *device: REPL (USB)*) attaches; Ctrl+C stops
   `main.py`, Ctrl+D soft-reboots and shows the boot log, where each channel should
   print `ok`. Ctrl+] leaves.

## Bench wiring (screw-terminal adapter)

On the bench the DevKit sits in a generic "FOR ESP32 TERMINAL ADAPTER". Its labels
are right, but only under three conditions; each one cost an evening:

- **USB connector at the 5V/CLK end**, antenna at the 3V3/GND end. The vendor's
  product photo shows it rotated 180°. Seated that way, "3V3" is the flash clock,
  the left "GND" is GPIO21 and "P13" is RX: boot loops, I²C timeouts, a dead REPL
  and a reverse-powered display.
- **Wire the screw terminals, never the spare header sockets.** The terminals are
  3.5 mm apart and the sockets 2.54 mm, so a label drifts 1–3 sockets from its pin.
- **Leave SD0–SD3, CND, CLK, P12, TX and RX empty.** "CND" is CMD (GPIO11, a flash
  pin), not ground. P12 high at reset drops the flash to 1.8 V.

The display (NULLLAB SWIFT-LCD-20) — go by the labels at its connector, not by
wire colour; on the supplied pigtail red is CS and blue is power:

| Display | Terminal | GPIO |
|---|---|---|
| V | 5V | — (module has its own 3.3 V regulator) |
| G | GND | — |
| SCL | P14 | 14 (SCK) |
| SDA | P13 | 13 (MOSI) |
| DC | P27 | 27 |
| CS | P15 | 15 |

The sourced write-up is in
[docs/research/ESP32 display wiring verification.md](../../docs/research/ESP32%20display%20wiring%20verification.md).

## Bench mode

With no sensors wired, set `BENCH_SIMULATE = True` in `config.py`. Each channel then
reports what the app's model predicts it reads at the fan level in the app's
status broadcast (`lib/lumosair/benchsim.py`, profile `BENCH_PROFILE` = `A` or
`C`). Telemetry, Wi-Fi, the display and commands all stay real, so the real box,
a simulated fan box (`tools/simulate_node.py --live --node fan --config A`) and the
app with the matching `system.optionA.json` show normal operation end to end.
**Turn it off before a box goes on the duct.**

## Updating over Wi-Fi

Once a box is mounted on the duct, don't take it down for a USB cable:

```
python tools/serve_update.py             # on the PC, in this folder
python tools/send_command.py laser update # or the Update button in the app
```

The node fetches `manifest.json`, downloads only the files whose SHA-256 changed,
writes them and reboots. Set `OTA_URL` in `config.py` to the address the tool prints.

## What the box screen shows

The 2.0" ST7789 is read from across the room, so it shows only what you act on:

- a full-width status band: ALL GOOD / ADVICE / CHECK / PROBLEM, or **NO PC**
  when no status has arrived from the app for 10 s,
- the system airflow in CFM and the fan level, 100 px tall,
- **SET n** in amber under the fan level when the app wants the dial moved,
- the app's top finding in plain words, on two large lines,
- one block per sensor along the bottom: green responding, orange not.

The app sends its status straight to each box it has heard from (a plain
255.255.255.255 broadcast leaves Windows by one adapter only, which on a PC with
Hyper-V or a VPN is often not the LAN).

## Fan control

`fan.py` accepts `{"cmd":"set_level","level":7}` and reports the level in telemetry.
It only drives a pin once you set `FAN_OUTPUT_ENABLED = True` in `config.py`: the
CLOUDLINE UIS pinout is community-reverse-engineered, so check it with a meter
first. Until then the app's Auto mode still works as an advisory — it tells you
(and the box screen) which level to set.

## Running a node without a node

`tools/simulate_node.py` runs the box on your PC and draws what the panel would
show. It is not a mock of the UI: it imports the real `st7789` and `display_ui`
and decodes the SPI command stream the driver emits (CASET / RASET / RAMWR) into
a framebuffer, so the PNG is the panel pixel for pixel — layout bugs included.
Standard library only.

```
python tools/simulate_node.py --window         # a window; arrows walk the screens
python tools/simulate_node.py --live --window  # a live box, on screen
python tools/simulate_node.py                  # every scenario -> out/*.png
python tools/simulate_node.py --live           # headless; one PNG per frame
```

`--window` opens a real window (tkinter, standard library) showing the panel at
2x. Without `--live` it shows one scenario and **Left/Right** walk through all
eight, so you can flick between states and compare layouts; Esc closes it.

![The box screen, healthy](../../docs/screenshots/node-screen-healthy.png)

![The box screen, clogged run](../../docs/screenshots/node-screen-clog.png)

Scenarios: `healthy`, `clog`, `binleak`, `pitot`, `slow`, `sensorfault`, `nopc`
(the desktop app isn't running) and `fannode` (the one-channel box).

`--live` makes it a stand-in for a real box: it publishes telemetry on UDP 47810,
accepts commands on 47811, and listens for the app's status broadcast on 47812.
Start it, then run the desktop app with **Source = Udp** and **Connect** — the app
sees a node that isn't there, and the screen reacts to what the app concludes.
Add `--window` to watch it live; without it each frame is written to
`out/screen_live_<node>.png` (written to a temp file and renamed, so a preview
can never catch a half-written frame).

The 8x8 font it uses stands in for MicroPython's built-in one. The cell is the
same fixed 8x8, so anything that fits here fits on the panel; individual glyph
shapes differ slightly.

**This is how the seven-segment bug was found** — every digit with an asymmetric
shape (3, 4, 6, 7, 9) rendered mirrored, because `_DIGITS` is written LSB-first
and `seg7` was reading it MSB-first. Nothing caught it, because the old test only
asserted that `seg7` wrote *some* pixels. There are now eight checks on which
bars each digit lights.

## Host tests

```
python tests/test_firmware.py
```

51 checks covering the CRC and scaling maths, the multiplexer, channel averaging
and zero offsets, the fan level mapping, the telemetry payload the PC app parses,
the display driver — which segments each digit lights, and that fills and text
reach the panel in the same byte order — and bench mode. Only the pin wiggling
needs hardware.
