# "FOR ESP32 TERMINAL ADAPTER" screw-terminal board vs ESP32-DevKitC V4 38-pin pinout

## Q1. Do the silkscreen labels match the ESP32-DevKitC V4 J2/J3 headers pin for pin? Label → GPIO mapping; is "CND" CMD?

### Takeaway
Yes. Both columns match Espressif's DevKitC V4 J2 (left) and J3 (right) tables exactly, in order, pin 1 to pin 19. "CND" sits where J2 pin 18 is **CMD = GPIO11**, a SPI-flash line. It is a misprint of CMD and is **not ground**.

### Cited Findings
- Espressif DevKitC V4 **J2** (pins 1 to 19): 3V3, EN (CHIP_PU/reset), VP (GPIO36), VN (GPIO39), IO34, IO35, IO32, IO33, IO25, IO26, IO27, IO14 (MTMS), IO12 (MTDI), GND, IO13 (MTCK), D2 (GPIO9), D3 (GPIO10), CMD (GPIO11), 5V — [Espressif ESP32-DevKitC V4 user guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html)
- Espressif DevKitC V4 **J3** (pins 1 to 19): GND, IO23, IO22, TX (GPIO1, U0TXD), RX (GPIO3, U0RXD), IO21, GND, IO19, IO18, IO5, IO17, IO16, IO4, IO0 (Boot), IO2, IO15 (MTDO), D1 (GPIO8), D0 (GPIO7), CLK (GPIO6) — [Espressif DevKitC V4 user guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html)
- "The pins D0, D1, D2, D3, CMD and CLK are used internally for communication between ESP32 and SPI flash memory" — [Espressif DevKitC V4 user guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html)
- GPIO16/17 are available only on WROOM/SOLO-1 DevKitC boards. On WROVER boards they are taken by PSRAM — [Espressif DevKitC V4 user guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html)
- Listing/review, not primary: one Amazon UK review of a DIYables 38-pin screw-terminal adapter says "the labels on the breakout board are all wrong" (quoted in the search-result summary; the page itself returned 503 and could not be read) — [Amazon UK DIYables listing](https://www.amazon.co.uk/Screw-Terminal-Breakout-Board-38-pin/dp/B0CRKJX66W)

Label-by-label mapping (adapter silkscreen → DevKitC pin → GPIO):

| # | Left label | DevKitC J2 | GPIO | | Right label | DevKitC J3 | GPIO |
|---|---|---|---|---|---|---|---|
| 1 | 3V3 | 3V3 | power | | GND | GND | ground |
| 2 | EN | EN | CHIP_PU (reset) | | P23 | IO23 | 23 |
| 3 | SVP | VP | 36 (input only) | | P22 | IO22 | 22 |
| 4 | SVN | VN | 39 (input only) | | TX | TX | 1 (U0TXD) |
| 5 | P34 | IO34 | 34 (input only) | | RX | RX | 3 (U0RXD) |
| 6 | P35 | IO35 | 35 (input only) | | P21 | IO21 | 21 |
| 7 | P32 | IO32 | 32 | | GND | GND | ground |
| 8 | P33 | IO33 | 33 | | P19 | IO19 | 19 |
| 9 | P25 | IO25 | 25 | | P18 | IO18 | 18 |
| 10 | P26 | IO26 | 26 | | P5 | IO5 | 5 (strap) |
| 11 | P27 | IO27 | 27 | | P17 | IO17 | 17 |
| 12 | P14 | IO14 | 14 (MTMS) | | P16 | IO16 | 16 |
| 13 | P12 | IO12 | 12 (MTDI, strap) | | P4 | IO4 | 4 |
| 14 | GND | GND | ground | | P0 | IO0 | 0 (strap/BOOT) |
| 15 | P13 | IO13 | 13 (MTCK) | | P2 | IO2 | 2 (strap) |
| 16 | SD2 | D2 | 9 (flash) | | P15 | IO15 | 15 (MTDO, strap) |
| 17 | SD3 | D3 | 10 (flash) | | SD1 | D1 | 8 (flash) |
| 18 | **CND** | **CMD** | **11 (flash)** | | SD0 | D0 | 7 (flash) |
| 19 | 5V | 5V | power | | CLK | CLK | 6 (flash) |

### Inferences
- The silkscreen is the DevKitC V4 order copied exactly, with short names ("P"+number, "SD" in place of "D"). "CND" is in the CMD slot (pin 18, between SD3/GPIO10 and 5V). The only grounds are J2 pin 14 and J3 pins 1 and 7, so CND is GPIO11, not GND. **Never use CND as a ground return.** Tying GPIO11 to GND holds the flash CMD line low and stops the chip from reading flash.
- The user's board is an "ESP32-WROOM-32 DevKit" (38-pin, CP2102). Such boards are normally DevKitC-V4 clones with the same J2/J3 order. The user should still check the silkscreen printed on the DevKit itself: if its left row reads 3V3, EN, VP, VN… from the antenna end, it matches.

### Gaps
- I could not read the actual product photos or reviews on Amazon or AliExpress (Amazon pages returned only scripts or a 503), so I cannot confirm how common silkscreen errors are on this black-PCB variant beyond the one DIYables review.

## Q2. Which way must the DevKit face? What happens if it is rotated 180° or put in the wrong-width socket pair?

### Takeaway
The DevKit's pin 1 (3V3 on J2, GND on J3) must sit at the adapter's 3V3/GND end. That puts the antenna toward 3V3/GND and the **micro-USB toward the 5V/CLK end**, with the J2 side (3V3…5V) under the left column. If it is rotated 180°, every label is wrong and power goes onto signal pins.

### Cited Findings
- On the DevKitC V4, the flash pins (D0 to D3, CMD, CLK) are the pin-16 to pin-19 group next to the micro-USB connector. Pin 19 of J2 is 5V and pin 19 of J3 is CLK — [Espressif DevKitC V4 user guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html)
- Espressif J2/J3 numbering starts at 3V3 (J2-1) and GND (J3-1). Those are at the module/antenna end, opposite the USB — [Espressif DevKitC V4 user guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html)
- These adapters are made for "0.9 in / 1.0 in size" 38-pin boards, meaning two row spacings, which is why each side has two socket rows — [Amazon listing title, naughtystarts](https://www.amazon.com/Breakout-Terminal-Expansion-ESP-WROOM-32-ESP32-DevKitC/dp/B0BYS6THLF); [Amazon listing title, risingsaplings](https://www.amazon.com/risingsaplings-Terminal-Expansion-Compatible-ESP32-DevKitC/dp/B0C3QM5ZHP); a similar open design supports "both the wide (1") and Narrow (.8") 38 pin ESP32 dev boards" — [Home Assistant community post](https://community.home-assistant.io/t/esp32-38-pin-dev-board-terminal-breakout-for-esphome/565560)
- Listing/review, not primary: one reviewer reports that one side of the ESP32 pins does not line up with the board's sockets and that the board does not use the standard ESP32 pin width. Another says it does not fit every ESP32 board. DIYables says its adapter fits only 38-pin boards with no mounting holes and no pin names printed on top — [Amazon UK DIYables listing, search summary](https://www.amazon.co.uk/Screw-Terminal-Breakout-Board-38-pin/dp/B0CRKJX66W); [DIYables product page](https://diyables.io/products/screw-terminal-adapter-for-38-pin-esp32-board)

### Inferences
- **Rotated 180°:** J2-1 (3V3) would land under the right column's CLK terminal, J2-19 (5V) under GND, J3-1 (GND) under 5V, and so on. Powering from the adapter's 5V terminal would then short 5V to the DevKit's GND. Power from a terminal fed through the rotated board would also reach flash or IO pins. Either way there is a real risk of damage. Both the adapter and the DevKit are symmetric, so nothing mechanical stops you from inserting it backwards.
- **Wrong width:** a DevKit is one fixed width, so only one socket pair fits both rows. Forcing a board into the other pair would bend pins or leave one row unconnected. It cannot line up with the wrong pins on both sides at once. The more realistic mistake is **one row off by one position lengthwise**. Check that 19 pins are fully seated on each side and none are left over.
- Quick check after insertion: with USB power only, measure 3.3 V between the adapter's "3V3" and "GND" terminals and about 5 V (minus the diode drop) at "5V". This confirms both orientation and alignment.

### Gaps
- No primary source (the adapter has no datasheet) states the USB direction. The conclusion above follows from matching pin-1 positions.

## Q3. Do the terminal screws line up with the header sockets?

### Takeaway
No, not one-for-one in position. There are 19 terminals per side at 3.5 mm pitch (some variants use 3.81 or 3.96 mm), against 19 sockets at 2.54 mm. The terminal row is about 66 mm long and the socket row about 48 mm, so they drift apart along the board. Each label belongs to its **terminal**, and the PCB traces fan out to the matching socket.

### Cited Findings
- The DIYables 38-pin adapter uses 3.5 mm pitch terminals — [DIYables product page](https://diyables.io/products/screw-terminal-adapter-for-38-pin-esp32-board)
- Other variants are sold with 3.5 mm, 3.81 mm and 3.96 mm terminals and 2.54 mm headers — [naughtystarts 3.5 mm](https://www.amazon.com/Breakout-Terminal-Expansion-ESP-WROOM-32-ESP32-DevKitC/dp/B0BYS6THLF); [3.81 mm "Super Breakout"](https://www.amazon.com/Breakout-Terminal-Expansion-ESP-WROOM-32-ESP32-DevKitC/dp/B0BHZVRSZF); [3.96 mm wide version](https://www.amazon.com/Screw-Terminal-Breakout-38-pin-Pieces/dp/B0DYDK4LBS) (listing titles)
- "The outer connectors are the screw terminals where you would connect your external components" — [Fritzing forum](https://forum.fritzing.org/t/38-pin-screw-terminal-adapter-for-esp32/27449)

### Inferences
- The arithmetic: 18 gaps × 2.54 mm = 45.7 mm, against 18 gaps × 3.5 mm = 63 mm. The end terminals sit about 8.6 mm beyond the end sockets, so any label in the middle half of the board sits roughly 1 to 3 socket positions away from its own socket. Read the label next to the **screw**, never the one nearest a socket, and use a meter to check any terminal that matters (5V, GND, 3V3, strapping pins).
- Many of these boards also have a row of 2.54 mm male pins beside each terminal (the "GPIO 1 into 2" wording means one pin is broken out twice). Those follow the terminal numbering, not the socket numbering.

### Gaps
- I found no photo or teardown of this exact black-PCB board showing its traces. The 3.5 mm pitch comes from similar products, so measure the board in hand.

## Q4. Known variants and errors (30-pin DOIT V1 vs 38-pin; mislabeled boards)

### Takeaway
This adapter is for 38-pin DevKitC-layout boards only. A 30-pin DOIT DevKit V1 has no flash pins (SD0 to SD3, CMD, CLK), puts power in different places (VIN/GND at the USB end on one side, 3V3/GND on the other) and has a different pin order. Plugged into this adapter, it would put power and ground on the wrong terminals.

### Cited Findings
- ESP32 DEVKIT boards exist in "30, 36, and 38" pin versions — [Random Nerd Tutorials](https://randomnerdtutorials.com/getting-started-with-esp32/)
- Separate adapters exist for 30-pin boards (for example a "Green ESP32 Breakout Board… for 30-Pin") — [Tomson Electronics](https://www.tomsonelectronics.com/products/green-esp32-breakout-board-30pin-screw-terminal)
- Listing/review: "labels… all wrong", "one side misaligned", "not the standard ESP32 pin width", "does not work for all ESP32 boards" — [Amazon UK DIYables listing](https://www.amazon.co.uk/Screw-Terminal-Breakout-Board-38-pin/dp/B0CRKJX66W)
- DIYables requires 38 pins, no mounting holes and no pin names printed on top — [DIYables](https://diyables.io/products/screw-terminal-adapter-for-38-pin-esp32-board)

### Inferences
- In this case the labels do match DevKitC V4 (see Q1), so the risk lies in orientation and seating, not the silkscreen.

### Gaps
- No primary Espressif document covers the DOIT 30-pin order (DOIT is a third-party board). From memory and unverified: left side EN, VP, VN, D34, D35, D32, D33, D25, D26, D27, D14, D12, D13, GND, VIN; right side D23, D22, TX0, RX0, D21, D19, D18, D5, TX2, RX2, D4, D2, D15, GND, 3V3.

## Q5. SPI-flash pins GPIO6 to GPIO11: what happens if anything is connected?

### Takeaway
SD0, SD1, SD2, SD3, CND/CMD and CLK are the live flash bus. **Leave all six terminals unconnected.** A load, a pull, or a short to GND/3V3 on any of them corrupts flash reads. The result is boot failure such as `invalid header: 0xffffffff` loops, failed flashing, or crashes.

### Cited Findings
- "GPIO6-11 and GPIO16-17 are usually connected to the SPI flash and PSRAM integrated on the module and therefore should not be used for other purposes" — [ESP-IDF GPIO reference (ESP32)](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/gpio.html)
- The datasheet marks these GPIOs as "allocated for communication with in-package flash/PSRAM and NOT recommended for other" use — [ESP32 Series Datasheet v5.3](https://documentation.espressif.com/esp32_datasheet_en.pdf)
- esptool: GPIO6 and GPIO11 are used for SPI flash in all modes, GPIO7/8 in dual mode, and GPIO7 to GPIO10 in quad mode; "flashing will usually fail completely if these pins are connected incorrectly" — [esptool troubleshooting](https://docs.espressif.com/projects/esptool/en/latest/esp32/troubleshooting.html)
- `invalid header: 0xffffffff` is what the ROM prints when it boots from flash and reads all 0xFF (blank or unreadable flash) — [esp-idf issue #9005 (GitHub)](https://github.com/espressif/esp-idf/issues/9005)
- RNT: GPIO6 to GPIO11 "are not recommended for other uses" and are among the pins that toggle at boot — [Random Nerd Tutorials pinout](https://randomnerdtutorials.com/esp32-pinout-reference-gpios/)

### Inferences
- `0xffffffff` means the ROM read all ones. That happens when the flash does not answer (floating MISO) or is under-powered. Loading or shorting GPIO6 to GPIO11 produces this symptom, and so does GPIO12 held high (Q6).

### Gaps
- I did not find an Espressif document that names "invalid header: 0xffffffff" as the specific symptom of loading GPIO6 to GPIO11. That link comes from community reports and inference.

## Q6. Strapping pins GPIO0, 2, 5, 12 (MTDI), 15 (MTDO): exact effects at boot

### Takeaway
The pins are sampled once at reset and latched. Defaults: GPIO0 pull-up = 1 (flash boot), GPIO2 pull-down = 0, MTDI/GPIO12 pull-down = 0 (3.3 V flash), MTDO/GPIO15 pull-up = 1 (boot log on), GPIO5 pull-up = 1 (SDIO timing). On this user's chip the VDD_SDIO eFuse is not burned, so **GPIO12 high at reset powers the flash at 1.8 V**, the flash browns out, and the chip boot-loops. GPIO15 low only silences the ROM boot log (and changes SDIO-slave timing), which is harmless for a display chip-select.

### Cited Findings
- Strapping pins and their functions: boot mode (GPIO0, GPIO2), VDD_SDIO voltage (MTDI, with the eFuses EFUSE_SDIO_FORCE/TIEH), U0TXD printing (MTDO), SDIO slave timing (MTDO, GPIO5) — [ESP32 Datasheet v5.3 §3](https://documentation.espressif.com/esp32_datasheet_en.pdf)
- Defaults (Table 3-1): GPIO0 pull-up = 1, GPIO2 pull-down = 0, MTDI pull-down = 0, MTDO pull-up = 1, GPIO5 pull-up = 1. The latches sample at reset and "the pins are freed up to be used as regular IO pins after reset". Minimum hold time is 1 ms after CHIP_PU goes high — [ESP32 Datasheet v5.3](https://documentation.espressif.com/esp32_datasheet_en.pdf)
- Boot mode: GPIO0 = 1 gives SPI (flash) boot with GPIO2 "any value". GPIO0 = 0 with GPIO2 = 0 gives download boot — [ESP32 Datasheet v5.3 Table 3-3](https://documentation.espressif.com/esp32_datasheet_en.pdf); GPIO2 must be floating or low to enter the serial bootloader — [esptool boot-mode selection](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/boot-mode-selection.html)
- "MTDI = 0 (by default), VDD_SDIO… powered directly from VDD3P3_RTC… 3.3 V"; "MTDI = 1, VDD_SDIO… powered from internal 1.8 V LDO" — [ESP32 Datasheet v5.3 §3.2](https://documentation.espressif.com/esp32_datasheet_en.pdf)
- If GPIO12 is pulled high with 3.3 V flash, "it may prevent flashing or booting due to flash brownout" — [esptool boot-mode selection](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/boot-mode-selection.html)
- Fix: `espefuse set-flash-voltage 3.3V` permanently sets VDD_SDIO to 3.3 V, after which GPIO12 is no longer a strapping pin. This is irreversible and must not be done on a 1.8 V-flash (WROVER) module — [ESP-IDF SD pull-up requirements](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/sd_pullup_requirements.html)
- Real case (GitHub, community): a CC1101 output wired to GPIO12 held it high at boot, the flash was powered at 1.8 V, and the board boot-looped. Fixed with `espefuse set_flash_voltage 3.3V` or by moving the wire — [ESPSomfy-RTS issue #34](https://github.com/cjkas/ESPSomfy-RTS/issues/34)
- MTDO (GPIO15): 1 = U0TXD printing enabled (default), 0 = disabled; "If driven Low, silences boot messages printed by the ROM bootloader" — [ESP32 Datasheet v5.3 §3.3](https://documentation.espressif.com/esp32_datasheet_en.pdf); [esptool boot-mode selection](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/boot-mode-selection.html)
- Espressif hardware guidelines: GPIO0, GPIO2, GPIO5, MTDI and MTDO are strapping pins. Also: "Do not add high-capacitors at GPIO0, or the chip may enter download mode" — [ESP32 schematic checklist](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/schematic-checklist.html)
- Conflict: RNT also lists GPIO4 as a strapping pin — [RNT](https://randomnerdtutorials.com/esp32-pinout-reference-gpios/). The Espressif datasheet and ESP-IDF list only GPIO0, 2, 5, 12 and 15 — [ESP-IDF GPIO](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/gpio.html). Treat GPIO4 as a normal pin.

### Inferences
- For this user, anything attached to P12 that can source current at reset is the biggest hidden risk: a pull-up resistor, a module output, or a display pin driven by a separately powered display. Keep P12 unconnected, or use it only as an input from something that is guaranteed low or high-impedance at reset. Burning the 3.3 V eFuse is the permanent fix if P12 must be used.
- On a DevKitC, P0 is wired to the BOOT button and the auto-reset circuit. Anything that pulls it low at reset sends the chip into download mode ("waiting for download"). P2 must not be pulled high while flashing.
- GPIO15 low at reset: the ROM log disappears (it looks as if "TX is dead" until the app starts printing) and SDIO-slave edge timing changes. Nothing else is affected, and flash boot still works. A display CS with its own pull-up, or left undriven, keeps the default high.

### Gaps
- I did not find a primary source for the exact console text printed when GPIO12 is high on 3.3 V flash. Community reports show `invalid header: 0xffffffff` / flash read errors, but the text can vary.

## Q7. What causes random garbage characters on UART0 RX (GPIO3)?

### Takeaway
There is no single primary source for this. Espressif reserves GPIO1/GPIO3 for flashing and the console. On a DevKitC the CP2102 already drives GPIO3, so any extra wire on the RX terminal fights it or picks up noise. That wire then shows up as garbage bytes in the REPL or console input and can break flashing.

### Cited Findings
- GPIO1 (TXD) and GPIO3 (RXD) are "usually used for flashing and debugging" — [ESP-IDF GPIO reference](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/gpio.html)
- RNT lists GPIO1 and GPIO3 among pins that output signals or go high at boot — [RNT pinout](https://randomnerdtutorials.com/esp32-pinout-reference-gpios/)
- esptool: "Download mode successfully detected, but getting no sync reply: The serial TX path seems to be down" means the host-to-ESP line, which is GPIO3/RX, is broken or overridden — [esptool troubleshooting](https://docs.espressif.com/projects/esptool/en/latest/esp32/troubleshooting.html)

### Inferences
- Likely causes, in order: (1) a device on the RX terminal driving it (TX of another module, or a display/sensor pin) and contending with the CP2102's TX; (2) a long unterminated wire on the RX terminal picking up switching noise from a fan/PWM/relay while the USB-UART is idle (the CP2102 TX holds it high, but weakly through its series path, so fast edges couple in); (3) mismatched ground between the bench supply and USB; (4) a board rotated or misaligned in the adapter so a signal lands on GPIO3. Remedy: leave TX and RX terminals unconnected.

### Gaps
- No Espressif or forum source found that specifically describes garbage input from a wire on GPIO3. The DevKitC schematic (series resistor value between CP2102 TXD and GPIO3) was not checked.

## Q8. Is SCK=14, MOSI=13, CS=15, DC=27 on HSPI safe for an SPI display?

### Takeaway
Yes, with small caveats. 13, 14 and 15 are the native HSPI IO_MUX pins (MOSI, CLK, CS0), and 27 is a plain GPIO. GPIO15 is a strapping pin, but the only effect of it being low at reset is a silent ROM log. GPIO14 toggles/outputs a signal at boot, which may show as a brief flicker. None of these pins affects flash voltage or boot mode. **Do not use GPIO12 (HSPI MISO) as a display line**, since most displays don't need MISO anyway.

### Cited Findings
- HSPI defaults: GPIO13 MOSI, GPIO12 MISO, GPIO14 CLK, GPIO15 CS — [RNT pinout](https://randomnerdtutorials.com/esp32-pinout-reference-gpios/)
- GPIO12 to GPIO15 are the JTAG pins (MTDI, MTMS, MTCK, MTDO) "usually used for inline debug" — [ESP-IDF GPIO reference](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/gpio.html); pin functions IO14 = MTMS, IO13 = MTCK, IO15 = MTDO, IO27 = plain GPIO/ADC2_CH7/TOUCH7 — [DevKitC V4 guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html)
- GPIO14 and GPIO15 "output PWM signals or go HIGH during boot"; outputs connected to them "may get unexpected results when the ESP32 resets or boots" — [RNT pinout](https://randomnerdtutorials.com/esp32-pinout-reference-gpios/)
- GPIO15 low at reset only disables ROM U0TXD printing (and sets SDIO slave timing) — [ESP32 Datasheet v5.3](https://documentation.espressif.com/esp32_datasheet_en.pdf)
- 27, 13, 14 and 15 are ADC2 channels, and ADC2 is unusable while Wi-Fi is on. That doesn't matter for digital SPI use — [DevKitC V4 guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html)

### Inferences
- The only realistic GPIO15 risk is a display CS line held low by the display module at power-up. The consequence is a missing ROM boot log, not a failed boot. A 10 k pull-up on CS keeps the log and also keeps the display deselected during reset.
- GPIO14's boot-time activity can clock junk into the display while CS is high. A controller ignores it when CS is deselected, and the display is re-initialised anyway.
- Pins to leave unconnected on the bench, in order of risk: SD0, SD1, SD2, SD3, **CND (CMD)**, CLK (GPIO6 to 11, flash); **P12** (sets flash to 1.8 V on this chip); TX and RX (console/flashing); P0 (boot mode; a button only); P2 (must be low or floating for flashing); 5V and 3V3 terminals must never be fed from a bench supply while USB is also connected, unless you know the DevKit's power path. P5 and P15 are fine if nothing holds them low at reset (SDIO timing / log only). P34, P35, SVP and SVN are input-only with no internal pulls.

### Gaps
- Whether the user's display module pulls CS or DC in any direction at power-up is not covered here.
- Back-feed behaviour of the DevKitC 5V/USB power path (a diode between USB VBUS and the 5V pin) was not checked against the schematic.
