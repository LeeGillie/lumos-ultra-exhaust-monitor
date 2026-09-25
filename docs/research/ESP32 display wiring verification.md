# Wire the screw terminals, never the sockets

The silkscreen on the "FOR ESP32 TERMINAL ADAPTER" is **correct**. Both columns copy Espressif's ESP32-DevKitC V4 J2/J3 header order pin for pin, and the odd "CND" label is a misprint of **CMD (GPIO11, a live SPI-flash line), not ground**. The labels only hold if you meet three conditions. First, the DevKit must sit the right way round, with the antenna at the 3V3/GND end and micro-USB at the 5V/CLK end. Second, you must read each label against its **screw terminal**, not the header socket nearest it. Third, the six flash pins (SD0 to SD3, CND, CLK) and P12 must stay unconnected. Your two symptoms fit that picture. `invalid header: 0xffffffff` means the ROM read blank or unreadable flash, which is what a wire on GPIO6 to GPIO11 or on GPIO12 produces. Garbage on UART RX means something is driving or picking up noise on GPIO3. Both point to display wires landing in the wrong header sockets, because the 3.5 mm terminal row and the 2.54 mm socket row drift one to three positions apart along the board. The display is the NULLLAB/Emakefun SWIFT-LCD-20. Its vendor schematic confirms a six-pin G, V, SCL, SDA, DC, CS interface, an on-board 3.3 V LDO, reset and backlight tied off internally, and 3.3 V-only logic. Your firmware's pins (SCK 14, MOSI 13, CS 15, DC 27) are safe. The pigtail colour mapping is **plausible but undocumented**: the pin order matches the schematic, but no source publishes wire colours, so confirm it with a meter before you power up.

## The adapter labels are right, but position and orientation are not guaranteed

Espressif's DevKitC V4 guide lists J2 as 3V3, EN, VP, VN, IO34, IO35, IO32, IO33, IO25, IO26, IO27, IO14, IO12, GND, IO13, D2, D3, CMD, 5V. It lists J3 as GND, IO23, IO22, TX, RX, IO21, GND, IO19, IO18, IO5, IO17, IO16, IO4, IO0, IO2, IO15, D1, D0, CLK ([Espressif DevKitC V4](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html)). The adapter's left column (3V3, EN, SVP, SVN, P34 … P13, SD2, SD3, CND, 5V) and right column (GND, P23, P22, TX, RX … P15, SD1, SD0, CLK) follow that order exactly. The only grounds on the board are left pin 14 and right pins 1 and 7, so **CND is GPIO11**. Tying it to ground holds the flash command line low and the chip cannot boot. One Amazon reviewer of a similar DIYables adapter says "the labels… are all wrong" ([Amazon UK](https://www.amazon.co.uk/Screw-Terminal-Breakout-Board-38-pin/dp/B0CRKJX66W)). For this board the labels themselves check out, so that complaint more likely reflects the two traps below.

**Orientation.** J2-1 (3V3) and J3-1 (GND) sit at the antenna end, and the flash pins and 5V/CLK sit next to the micro-USB ([Espressif](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html)). So the DevKit goes in with the **antenna toward the 3V3/GND end and the USB toward 5V/CLK**, J2 under the left column. Nothing mechanical stops you from inserting it rotated 180°. If you do, 5V lands on the DevKit's GND and every label is wrong. Each side has two socket rows because these adapters accept both 0.9" and 1.0" wide boards ([Amazon listing](https://www.amazon.com/Breakout-Terminal-Expansion-ESP-WROOM-32-ESP32-DevKitC/dp/B0BYS6THLF)). A board fits only one pair. The realistic mistake is a row shifted one pin lengthwise, so check that each side has exactly 19 pins seated and none left over.

**Terminals drift away from sockets.** The terminals use 3.5 mm pitch (3.81 mm and 3.96 mm on some variants), while the sockets are 2.54 mm ([DIYables](https://diyables.io/products/screw-terminal-adapter-for-38-pin-esp32-board)). Across 18 gaps that is about 63 mm against 46 mm, so a mid-board label sits one to three socket positions away from the socket it is wired to. Each label belongs to its screw, and traces fan out to the correct socket. The spare socket row is **not** a labelled breakout. If you push a jumper into the socket that looks as if it lines up with "P13", it can land on IO12, GND or D2. That is the most likely cause of your boot loop.

## Six flash pins and P12 explain the 0xffffffff boot loop

ESP-IDF says GPIO6 to GPIO11 "are usually connected to the SPI flash… and therefore should not be used for other purposes" ([ESP-IDF GPIO](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/gpio.html)). esptool warns that "flashing will usually fail completely if these pins are connected incorrectly" ([esptool troubleshooting](https://docs.espressif.com/projects/esptool/en/latest/esp32/troubleshooting.html)). The `invalid header: 0xffffffff` message is the ROM reporting all-ones, meaning blank or unreadable flash ([esp-idf #9005](https://github.com/espressif/esp-idf/issues/9005)).

The second route to the same symptom is **GPIO12 (MTDI)**. It is a strapping pin: when high at reset it switches VDD_SDIO to 1.8 V ([ESP32 datasheet §3.2](https://documentation.espressif.com/esp32_datasheet_en.pdf)). With the 3.3 V flash on a WROOM-32, "it may prevent flashing or booting due to flash brownout" ([esptool boot-mode selection](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/boot-mode-selection.html)). A community case with a module output on GPIO12 boot-looped the same way ([ESPSomfy-RTS #34](https://github.com/cjkas/ESPSomfy-RTS/issues/34)). The permanent fix is `espefuse set-flash-voltage 3.3V`, which removes GPIO12 as a strapping pin. It cannot be undone and is wrong for 1.8 V-flash modules ([ESP-IDF](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/sd_pullup_requirements.html)). You don't need it if P12 stays empty. No Espressif document says that loading GPIO6 to GPIO11 prints exactly `0xffffffff`; that link comes from community reports and inference.

The other strapping pins matter less. GPIO0 low at reset forces download mode, and GPIO2 must be low or floating while flashing. **GPIO15 low at reset only silences the ROM boot log**; flash boot still works ([datasheet §3.3](https://documentation.espressif.com/esp32_datasheet_en.pdf)). The later **RX garbage** is less well documented. GPIO1 and GPIO3 carry the console and flashing link ([ESP-IDF GPIO](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/gpio.html)), and the CP2102 already drives GPIO3. Any wire landing on RX, whether a display clock, a floating jumper or a mis-seated pin, will fight the CP2102 or pick up noise. No source describes this exact symptom, but it is the obvious reading. Keep TX and RX empty.

| Terminal | GPIO | Rule |
|---|---|---|
| SD0, SD1, SD2, SD3, CND, CLK | 7, 8, 9, 10, 11, 6 | Never connect: live flash bus |
| P12 | 12 | Leave empty: high at reset browns out flash |
| TX, RX | 1, 3 | Leave empty: USB console and flashing |
| P0 | 0 | Boot button only |
| P2 | 2 | Nothing that pulls it high |
| P15, P5 | 15, 5 | OK if nothing holds them low at reset (only affects boot log and SDIO timing) |
| SVP, SVN, P34, P35 | 36, 39, 34, 35 | Input only, no pulls |

## The SWIFT-LCD-20 is a documented NULLLAB board with fixed tie-offs

NULLLAB sells the module (Amazon [B0GVF8R5ZL](https://www.amazon.com/NULLLAB-Interface-Compatible-Embedded-Projects/dp/B0GVF8R5ZL)) and publishes a README, schematic, dimension drawing and ESP32 demos at [nulllaborg/swift-lcd](https://github.com/nulllaborg/swift-lcd). The schematic's title block says **Emakefun, SWIFT-LCD-13, Rev V0.1**. It was drawn for the 1.3" sister board, but the README gives both boards the same pinout, supply range and tie-off notes ([schematic](https://github.com/nulllaborg/swift-lcd/blob/main/picture/schematic_diagram.png)). The specs are **3.3 to 5 V supply, 80 mA, 56 × 40 mm board, IPS panel, ST7789** ([README](https://raw.githubusercontent.com/nulllaborg/swift-lcd/main/README.md)).

The connector J1 runs **1 GND, 2 VIN, 3 SCLK, 4 SDA, 5 DC, 6 CS**. The same six signals also appear on a 0.1" through-hole row and a 2×3 pad block ([schematic](https://github.com/nulllaborg/swift-lcd/blob/main/picture/schematic_diagram.png)). The README calls the connector GH1.25 and the cable "GH1.25 to PH2.0". The Amazon text says the cable is GH1.25 to Dupont ([Amazon](https://www.amazon.com/NULLLAB-Interface-Compatible-Embedded-Projects/dp/B0H2Y83TYG)), so check what came in your box. SDA is write-only MOSI, so you don't need MISO.

Power goes through a **662K (XC6206P332MR) 3.3 V LDO** rated for 6 V maximum input ([Sunrom](https://www.sunrom.com/p/xc6206p332mr-662k)). The SPI, DC and CS lines connect **directly to the ST7789 with no level shifting**, and that chip's logic inputs are rated to VDDI + 0.5 V ([ST7789V datasheet](https://newhavendisplay.com/content/datasheets/ST7789V.pdf)). "3.3–5 V compatible" therefore applies to the supply pin only. ESP32 3.3 V logic is correct. Feeding V from 5V, as the vendor example does, gives the LDO headroom. Feeding it from 3V3 also works but leaves the panel about 0.1 to 0.25 V low.

**Reset** is a resistor pull-up to 3V3 with no RC network. **Backlight** is a P-MOSFET (AO3401A) whose gate is tied to GND through a 0 Ω resistor, so it is always on at full brightness and cannot be dimmed without rework ([schematic](https://github.com/nulllaborg/swift-lcd/blob/main/picture/schematic_diagram.png)). The driver therefore has to send SWRESET (0x01) and wait at least 5 ms, and wait 120 ms before SLPOUT ([ST7789V §9.1.2](https://newhavendisplay.com/content/datasheets/ST7789V.pdf)). **SPI mode:** the ST7789 samples SDA on the rising clock edge, and with a real CS line "SCL can be high or low" when CS falls. That means **mode 0 and mode 3 both work** ([ST7789V §8.4](https://newhavendisplay.com/content/datasheets/ST7789V.pdf)). The vendor demos use mode 0. **Clock:** the datasheet's minimum write cycle of 66 ns works out to about 15 MHz. Higher speeds usually work but are out of spec. **Driver settings:** use 240×320 with offsets 0,0, inversion ON, and RGB order. The vendor's own demo uses exactly this: `Arduino_ST7789(bus, -1, 0, true, 240, 320, 0, 0, 0, 0)` ([vendor demo](https://github.com/nulllaborg/swift-lcd/releases/download/V1.0.0/swift_lcd_20_display_time.zip)).

Your `lib/lumosair/st7789.py` already matches. It sends SWRESET with 150 ms, SLPOUT with 120 ms, INVON, and MADCTL 0x60 for landscape without the BGR bit, and uses `rst=None, bl=None`. The polarity=1/phase=1 setting is fine. If you see garbage pixels at 30 MHz, the fix is to drop to 20 MHz or lower, not to change mode. The docstring says "VCC -> 3V3". That works, but 5V gives the LDO more margin.

## The pigtail colours are probably right, and you still need to meter them

No source publishes a colour table for this cable. The Amazon listing gives only the signal set G, V, SCL, SDA, DC, CS ([Amazon](https://www.amazon.com/NULLLAB-Interface-Compatible-Embedded-Projects/dp/B0GVF8R5ZL)). Your photographed order (CS, DC, SDA, SCL, V, G) is the schematic's J1 read from pin 6 back to pin 1. That makes **red = CS, black = DC, yellow = SDA, green = SCL, blue = V, white = G** consistent with the board. The colour sequence looks like a generic rainbow kit (red, black, yellow, white, blue, green) inserted in stock order, not colours chosen per signal ([GH1.25 kit](https://www.amazon.com/Teansic-Connector-Temperature-pre-Crimped-Controller/dp/B0FHGN5Y22)). Colour conventions differ everywhere: Pololu puts black on pin 1 and red on pin 2 ([Pololu](https://www.pololu.com/product/5546)), Grove puts red on pin 3 ([Seeed](https://wiki.seeedstudio.com/Grove_System/)), and Qwiic puts red on pin 2 ([SparkFun](https://www.sparkfun.com/qwiic)).

The practical danger is habit. **Red and black are signals here, not power.** Wiring red to 3V3 and black to GND would back-power the panel through its CS input's protection diodes, and a GPIO would then be asked to supply the 80 mA module ([Hackaday on ESD diodes](https://hackaday.com/2025/06/19/hacker-tactic-esd-diodes/)). "Anti-reverse" keys only the GH end; the Dupont end has no keying.

## Recommended wiring for the current firmware

| Display pin | Pigtail colour (verify) | Adapter **screw terminal** | GPIO | Firmware |
|---|---|---|---|---|
| G | white | GND (left pin 14, or right pin 1/7) | — | — |
| V | blue | 5V (preferred) or 3V3 | — | — |
| SCL | green | **P14** (left pin 12) | 14 | SCK |
| SDA | yellow | **P13** (left pin 15) | 13 | MOSI |
| DC | black | **P27** (left pin 11) | 27 | DC |
| CS | red | **P15** (right pin 16) | 15 | CS |

Every signal except CS is on the left column, next to P12 (between P14 and GND) and just above SD2/SD3/CND. Those are the neighbours a one-slot slip lands on. An optional 10 kΩ pull-up from CS to 3V3 keeps the panel deselected, and the ROM log visible, while the ESP32 is in reset. MicroPython's HSPI (SPI id 1) may claim GPIO12 as MISO by default when you don't pass one. That is harmless as long as nothing is wired to P12. The notes did not verify it, so don't rely on P12 being free for anything else.

**Pre-power checklist**

| # | Check | Pass criterion |
|---|---|---|
| 1 | DevKit orientation | Antenna at 3V3/GND end, USB at 5V/CLK end, J2 (3V3…5V) under left column |
| 2 | Seating | 19 pins per side fully seated, no spare socket at either end of the used row |
| 3 | Nothing in header sockets | Every external wire goes into a **screw terminal**; sockets hold only the DevKit |
| 4 | Forbidden terminals empty | SD0–SD3, CND, CLK, P12, TX, RX, P0, P2 have nothing attached |
| 5 | Pigtail continuity (unpowered, cable plugged into module) | Each Dupont socket beeps to its labelled pad; blue = V, white = G; no two wires beep to each other |
| 6 | Module supply not shorted | Resistance V–G on the module clearly above 0 Ω |
| 7 | Mark power | Tape or heat-shrink on blue (V) and white (G) Dupont ends |
| 8 | USB-only power test, display disconnected | Meter reads 3.3 V at 3V3–GND terminals and about 5 V (less a diode drop) at 5V–GND |
| 9 | Don't double-feed | No bench supply on 5V/3V3 while USB is connected |
| 10 | First light | Connect display and power up. The ROM boot log should appear and the display should initialise. If it boot-loops, unplug the display wires one at a time and re-meter them against the terminals |

## Conclusion

The labels were never the problem. The adapter breaks the one-to-one link between screw position and socket position, and the spare socket rows look like a breakout but are not one. That makes it easy to put a display wire on the flash bus or on GPIO12 while believing it sits on P13 or P14. Both faults produce exactly the blank-flash boot loop you saw. Treat the header sockets as belonging to the DevKit alone and you remove that whole class of fault. The display side carries less risk. The vendor's own schematic and demo code match your driver's reset-free init, inversion and RGB settings, and your pin choice avoids every hazardous strap. The one thing still unconfirmed is the cable itself: a two-minute continuity check replaces an inference from a photo with a measurement, and it guards against the "red means power" reflex that this pigtail would punish.
