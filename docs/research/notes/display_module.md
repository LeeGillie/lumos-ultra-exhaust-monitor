# SWIFT-LCD-20 (2.0" ST7789 240x320, 4-SPI) display module: fact sheet

Short answer: the module has been identified. SWIFT-LCD-20 is a NULLLAB product, and its schematic lists Emakefun as the design house. NULLLAB publishes the module on GitHub at https://github.com/nulllaborg/swift-lcd, with a README, a schematic image (drawn for the sister board SWIFT-LCD-13), a dimension drawing and ESP32 Arduino demos. Most answers below come from that repo (the primary source) and the Sitronix ST7789V datasheet. Anything that comes only from other modules or general practice is marked **[inference]**.

## Q1. Who makes/sells it; is there a datasheet, schematic or repo?

### Takeaway
SWIFT-LCD-20 is sold by NULLLAB (Amazon listings B0GVF8R5ZL for one, B0H2Y83TYG for a 2-pack). NULLLAB's GitHub repo `nulllaborg/swift-lcd` has the spec table, pinout, a KiCad schematic, a dimension drawing and ESP32 demos. The schematic's title block says "Emakefun", "SWIFT-LCD-13", Rev V0.1, dated 2025-10-23. There is no separate schematic for the 2.0" board.

### Cited Findings
- The repo covers two products: SWIFT-LCD-13 (1.3", 240x240) and SWIFT-LCD-20 (2.0", 240x320). Both use the "Standard 4-wire SPI" interface, an ST7789 driver IC, an IPS panel and an LED backlight. — [nulllaborg/swift-lcd README](https://github.com/nulllaborg/swift-lcd)
- SWIFT-LCD-20 spec: operating voltage "3.3V ~ 5V", power consumption "80mA", operating temperature -20 to 70 °C, module size "56 * 40mm, LEGO compatible". — [swift-lcd README](https://raw.githubusercontent.com/nulllaborg/swift-lcd/main/README.md)
- The repo's file tree has `picture/schematic_diagram.png`, `picture/dimension_drawing_swift_lcd_20.png` and `picture/swift_lcd_20.jpg`. Release V1.0.0 has `helloWorld.zip` and `swift_lcd_20_display_time.zip`. — [swift-lcd repo](https://github.com/nulllaborg/swift-lcd), [release V1.0.0](https://github.com/nulllaborg/swift-lcd/releases/tag/V1.0.0)
- The schematic title block reads "Emakefun / File: SWIFT-LCD-13.kicad_sch / Title: SWIFT-LCD-13 / Rev: V0.1 / Date 2025-10-23 / KiCad 8.0.3". — [schematic_diagram.png](https://github.com/nulllaborg/swift-lcd/blob/main/picture/schematic_diagram.png)
- Amazon titles:
  - Single: "NULLLAB 2.0 Inch LCD Display Module, 240x320 Full Color TFT IPS Screen, ST7789 Driver 4-Wire SPI Interface, 3.3V-5V Compatible…" — [Amazon B0GVF8R5ZL](https://www.amazon.com/NULLLAB-Interface-Compatible-Embedded-Projects/dp/B0GVF8R5ZL)
  - 2-pack: "NULLLAB 2-Pack 2.0 Inch …" — [Amazon B0H2Y83TYG](https://www.amazon.com/NULLLAB-Interface-Compatible-Embedded-Projects/dp/B0H2Y83TYG)
- Amazon listing text, as seen only in search-engine snippets: "The internal circuitry automatically pulls the RES (Reset) and BLK (Backlight Control) pins high". Module size 56 mm x 40 mm. — [Amazon B0H2Y83TYG](https://www.amazon.com/NULLLAB-Interface-Compatible-Embedded-Projects/dp/B0H2Y83TYG) (the page body did not render when fetched)
- NULLLAB's GitHub org (`nulllaborg`) also hosts other maker modules, such as maker-esp32 and a 4-digit clock display. — [github.com/nulllaborg](https://github.com/nulllaborg)
- For MicroPython, the README only links to Adafruit_CircuitPython_ST7789, which is a displayio driver. It does not supply a MicroPython driver of its own. — [swift-lcd README](https://github.com/nulllaborg/swift-lcd)

### Inferences
- The schematic is labelled for the 1.3" board. The 2.0" board very likely uses the same circuit: same LDO, same backlight MOSFET and same 6-pin interface. The README gives the two boards the same pin table, voltage and "RES/BLK pulled high" note, and your photos show the same connector and pad sets. The part values on your board (103, 102, 01X) are not all on the 1.3" schematic, so the resistor values probably differ.
- NULLLAB seems to be the brand and Emakefun the design house.

### Gaps
- There is no schematic specific to SWIFT-LCD-20 and no bare-panel datasheet (for example which FPC panel is used, or the backlight LED current).
- Amazon Q&A and reviews could not be retrieved; the page body did not render.

## Q2. Pinout and connectors

### Takeaway
Six signals: G, V, SCL (SPI clock), SDA (MOSI), DC, CS (active low). The same signals appear on three footprints: a 6-pin GH1.25 connector, a 6-pin 0.1" through-hole row, and a 2x3 pad block. The README says GH1.25 (1.25 mm pitch). The cable is described two ways: GH1.25-to-PH2.0 (README) or GH1.25-to-Dupont (Amazon).

### Cited Findings
- Pin table: G = Ground; V = Power Supply (3.3V ~ 5V); SCL = Serial Clock; SDA = "SPI Data Input/Output"; DC = Data/Command; CS = Chip Select (Active Low). — [swift-lcd README](https://github.com/nulllaborg/swift-lcd)
- Schematic, J1 "Conn_01x06_Pin": 1 GND, 2 VIN, 3 LCD_SCLK, 4 LCD_SDA, 5 LCD_DC, 6 LCD_CS. J2 "Conn_01x06_Pin-PZ/NC" has the same order and is marked optional/NC. J3 "Conn_02x03 NC": 1 CS / 2 SDA, 3 DC / 4 SCLK, 5 GND / 6 VIN. — [schematic](https://github.com/nulllaborg/swift-lcd/blob/main/picture/schematic_diagram.png)
- README: "Interface: GH1.25 pitch connector". "Connection Method: GH1.25 to PH2.0 6-pin anti-reverse cable". — [swift-lcd README](https://raw.githubusercontent.com/nulllaborg/swift-lcd/main/README.md)
- The Amazon text in search snippets says it "includes a GH1.25 interface and comes with a GH1.25 to Dupont 6-pin anti-reverse cable". — [Amazon B0H2Y83TYG](https://www.amazon.com/NULLLAB-Interface-Compatible-Embedded-Projects/dp/B0H2Y83TYG). This conflicts with the README (PH2.0 vs Dupont on the far end).
- Dimension drawing: board 56 x 40 mm. There are two groups of three pads (square pad = pin 1) along one 40 mm edge, with mounting holes 30 mm apart, 2.5 mm from the edge. — [dimension_drawing_swift_lcd_20.png](https://github.com/nulllaborg/swift-lcd/blob/main/picture/dimension_drawing_swift_lcd_20.png)
- Example ESP32 wiring from the vendor: CS→GPIO14, DC→GPIO15, SDA→GPIO16, SCL→GPIO17, V→5V, G→GND. — [swift-lcd README](https://github.com/nulllaborg/swift-lcd)

### Inferences
- The connector order you photographed (CS, DC, SDA, SCL, V, G) is J1 read from pin 6 back to pin 1. The through-hole split (G/V/SCL on one side, SDA/DC/CS on the other) matches the two 3-pad groups in the dimension drawing.
- The pin is labelled "SDA", but it is a write-only MOSI input to the ST7789. MISO is not needed.

### Gaps
- The exact connector part (JST GH vs a GH-compatible clone) is not stated. Check the pitch with calipers: 1.25 mm for GH, 1.0 mm for SH, 2.0 mm for PH.

## Q3. Supply voltage, regulator and 5 V logic tolerance

### Takeaway
V accepts 3.3 to 5 V. It feeds a Torex XC6206P332MR ("662K") 3.3 V LDO that powers the panel and backlight. The SPI/DC/CS lines go straight to the ST7789 with no level shifter, so the logic is 3.3 V only and is not 5 V tolerant. That is fine for an ESP32.

### Cited Findings
- The schematic power section is titled "Power VIN->3.3V". U1 is "662k(HXY)" (VDD=VIN, VOUT=3V3), with 10 µF/10 V capacitors on input and output. — [schematic](https://github.com/nulllaborg/swift-lcd/blob/main/picture/schematic_diagram.png)
- The "662K" marking is the XC6206P332MR: 3.3 V output, maximum input 6 V, dropout about 250 mV, 200 mA. — [Sunrom XC6206P332MR (662K)](https://www.sunrom.com/p/xc6206p332mr-662k), [iFuture](https://ifuturetech.org/product/xc6206p332mr-662k-xc6206-3-3v-0-5a-sot-23/)
- The schematic wires LCD_SCLK, LCD_SDA, LCD_DC and LCD_CS directly from the connectors to FPC U3 pins 9, 10, 7 and 8. No buffers or dividers are drawn. — [schematic](https://github.com/nulllaborg/swift-lcd/blob/main/picture/schematic_diagram.png)
- ST7789V absolute maximums: VDD and VDDI -0.3 to +4.6 V. Logic input voltage -0.3 to VDDI + 0.5 V. Recommended VDD is 2.4 to 3.3 V and VDDI is 1.65 to 3.3 V. — [ST7789V datasheet v1.3 (Newhaven mirror)](https://newhavendisplay.com/content/datasheets/ST7789V.pdf)
- Power consumption spec: 80 mA. — [swift-lcd README](https://github.com/nulllaborg/swift-lcd)

### Inferences
- **[inference]** "3.3V-5V compatible" in the listing applies to the supply only. Driving the pins from a 5 V MCU would put about 5 V on inputs rated to about 3.8 V (VDDI 3.3 + 0.5), which is out of spec. ESP32 3.3 V GPIO is correct.
- **[inference]** With V = 3.3 V, the rail after the LDO drops by roughly 0.1 to 0.25 V (dropout at ~80 mA), to about 3.05 to 3.2 V. That is still inside the ST7789's VDD range. Feeding 5 V gives a clean 3.3 V rail, and that is what the vendor example does. The 80 mA figure is mostly backlight.

### Gaps
- There is no measured current at 3.3 V vs 5 V input.

## Q4. Internal tie-offs: reset and backlight

### Takeaway
RES has a 2 kΩ pull-up to 3V3 and no capacitor is drawn, so it is not an RC reset. The panel relies on the ST7789's own power-on reset. Software should send SWRESET (0x01) and wait at least 5 ms (120 ms is conventional). The backlight is switched by a P-MOSFET (AO3401A) whose gate is tied to GND through a 0 Ω resistor, so it is always on at full brightness. A 10 Ω resistor limits LED current on the cathode side. Software cannot control brightness.

### Cited Findings
- Schematic, reset: LCD_RST (FPC pin 11 "RES") connects to 3V3 through R3 = 2K. No capacitor is shown on that net. — [schematic](https://github.com/nulllaborg/swift-lcd/blob/main/picture/schematic_diagram.png)
- Schematic, backlight: U2 AO3401A (P-channel). S goes to 3V3 and D goes to LED_A (FPC pin 3, LEDA). Gate net LCD_BL has R1 = 0R to GND and R2 = "0R/NC" to 3V3; R2 is not fitted. LED_K (FPC pin 2) goes through R4 = 10R to GND. R5 "10R/NC" is an optional bypass from 3V3 to LEDA. — [schematic](https://github.com/nulllaborg/swift-lcd/blob/main/picture/schematic_diagram.png)
- README: "The RES (Reset) and BLK (Backlight) pins are internally pulled high and do not require external wiring." — [swift-lcd README](https://github.com/nulllaborg/swift-lcd)
- ST7789V hardware reset: the reset pulse must be at least 10 µs. The datasheet says "It is necessary to wait 5msec after releasing RESX before sending commands. Also Sleep Out command cannot be sent for 120msec." — [ST7789V datasheet §7.4.5](https://newhavendisplay.com/content/datasheets/ST7789V.pdf)
- ST7789V SWRESET (01h): "It will be necessary to wait 5msec before sending new command following software reset… If software reset is sent during sleep in mode, it will be necessary to wait 120msec before sending sleep out command." — [ST7789V datasheet §9.1.2](https://newhavendisplay.com/content/datasheets/ST7789V.pdf)
- The vendor's 2.0" demo uses Arduino_GFX with rst = -1. In that library, `tftInit()` always sends `ST7789_SWRESET` followed by `delay(120)`, and pulses RST only when a pin is defined. — [demo swift_lcd_20_display_time.zip](https://github.com/nulllaborg/swift-lcd/releases/download/V1.0.0/swift_lcd_20_display_time.zip), [Arduino_ST7789.cpp](https://github.com/moononournation/Arduino_GFX/blob/master/src/display/Arduino_ST7789.cpp)

### Inferences
- The "BLK pulled high" wording in the marketing text is loose. In the schematic the backlight is simply always on (the PMOS gate is grounded). Full brightness is the only mode unless you rework R1/R2.
- **[inference]** The "01X" resistor you saw is probably EIA-96 code 01 (100) with multiplier X (0.1), which gives 10 Ω. That matches R4 = 10R. 103 = 10 kΩ and 102 = 1 kΩ are likely the reset pull-up and/or MOSFET gate parts. The 2.0" board may use 10k or 1k instead of the 2K on the 1.3" schematic. The SOT-23 parts you saw would be the 662K LDO and the AO3401A.
- **[inference]** In MicroPython, pass `reset=None` (st7789py and russhughes drivers accept this). Call `soft_reset()`/SWRESET and sleep ≥120 ms, then send SLPOUT (0x11) and wait 120 ms before further init. If the ESP32 reboots without cycling power, the panel keeps its old state, which is another reason SWRESET is required.

### Gaps
- Whether the 2.0" board fits a capacitor on RES is not documented.

## Q5. SPI mode and clock speed

### Takeaway
The ST7789 samples SDA on the rising edge of SCL. With a real CS line, "at the falling edge of CSX, SCL can be high or low", so SPI mode 0 and mode 3 both work. The vendor demos use mode 0 (Adafruit default) and Arduino_GFX defaults. The datasheet write-cycle minimum is 66 ns, about 15 MHz. Much faster clocks are common in practice but are out of spec.

### Cited Findings
- "When CSX is 'high', SCL clock is ignored… At the falling edge of CSX, SCL can be high or low. SDA is sampled at the rising edge of SCL." D/CX is sampled on the 8th rising edge in 4-line mode. — [ST7789V datasheet §8.4](https://newhavendisplay.com/content/datasheets/ST7789V.pdf)
- Serial timing (write): TSCYCW = 66 ns min; TSHW and TSLW = 15 ns min; TCSS (CS setup, write) = 15 ns. Read cycle TSCYCR = 150 ns. — [ST7789V datasheet §7.4](https://newhavendisplay.com/content/datasheets/ST7789V.pdf)
- Adafruit `Adafruit_ST7789::init(width, height, spiMode = SPI_MODE0)`. Its comment says "certain ST7789 displays are the only thing that may need a non-default SPI mode". — [Adafruit_ST7789.h/.cpp](https://github.com/adafruit/Adafruit-ST7735-Library/blob/master/Adafruit_ST7789.cpp)
- The vendor hello-world calls `g_display.init(240, 240)` with no SPI mode argument, so it runs in mode 0 on this module. It uses `Adafruit_ST7789 g_display(&SPI, kDisplayCs, kDisplayDc, -1)`. — [swift-lcd README](https://github.com/nulllaborg/swift-lcd)

### Inferences
- **[inference]** Mode 3 (polarity=1, phase=1) is only needed on ST7789 boards without a CS pin, where CS is tied low and the idle clock level matters. Many MicroPython ST7789 examples are written for those boards and use polarity=1, phase=1. Here either mode works. Mode 0 matches the vendor.
- **[inference]** Practical ESP32 clocks: start at 20–40 MHz with hardware SPI (SPI(1)/SPI(2) with pins given). Try 60–80 MHz only if the image stays clean with the GH cable length you use. Spec-safe is ≤15 MHz. The cable adds capacitance, so drop to 10–20 MHz if you see garbage.

### Gaps
- The vendor documents no SPI clock. The Arduino_GFX `Arduino_ESP32SPI` default frequency used by the 2.0" demo was not checked. No reliability reports specific to this board were found.

## Q6. ST7789 driver parameters: offsets, inversion, colour order, rotation

### Takeaway
Use 240x320 with column and row offsets of 0,0. Turn display inversion ON (INVON 0x21), because it is an IPS panel. Use RGB order (MADCTL bit 3 = 0). The vendor's demo does exactly this: `Arduino_ST7789(bus, -1 /*rst*/, 0 /*rotation*/, true /*ips*/, 240, 320, 0, 0, 0, 0)`. For landscape, MADCTL is 0x60 or 0xA0; for portrait, 0x00 or 0xC0.

### Cited Findings
- The vendor 2.0" demo calls `g_gfx = std::make_unique<Arduino_ST7789>(g_bus.get(), -1, 0, true, kScreenWidth, kScreenHeight, 0, 0, 0, 0);` with kScreenWidth = 240 and kScreenHeight = 320. — [swift_lcd_20_display_time.ino](https://github.com/nulllaborg/swift-lcd/releases/download/V1.0.0/swift_lcd_20_display_time.zip)
- Arduino_GFX constructor signature: `(bus, rst, r, bool ips=false, w, h, col_offset1, row_offset1, col_offset2, row_offset2)`. `invertDisplay(i)` sends `(_ips ^ i) ? INVON : INVOFF`, and `tftInit()` ends with `invertDisplay(false)`. So `ips = true` gives INVON. Its rotations all OR in `ST7789_MADCTL_RGB`. — [Arduino_ST7789.h](https://github.com/moononournation/Arduino_GFX/blob/master/src/display/Arduino_ST7789.h), [Arduino_ST7789.cpp](https://github.com/moononournation/Arduino_GFX/blob/master/src/display/Arduino_ST7789.cpp)
- The Adafruit generic_st7789 init list includes `ST77XX_INVON` (commented "hack"), and `ST77XX_MADCTL_RGB` is 0x00. For 240x320, `init()` computes offsets of 0. The vendor hello-world uses this library with `setRotation(2)`. — [Adafruit_ST7789.cpp](https://github.com/adafruit/Adafruit-ST7735-Library/blob/master/Adafruit_ST7789.cpp), [Adafruit_ST77xx.h](https://github.com/adafruit/Adafruit-ST7735-Library/blob/master/Adafruit_ST77xx.h)
- MADCTL (36h) bits: D7 MY (row order), D6 MX (column order), D5 MV (row/column exchange), D4 ML, D3 RGB/BGR (1 = BGR), D2 MH. — [ST7789V datasheet §9.1.28](https://newhavendisplay.com/content/datasheets/ST7789V.pdf)
- russhughes st7789py_mpy (pure-Python MicroPython) 240x320 rotation table as (madctl, w, h, xstart, ystart):
  - (0x00, 240, 320, 0, 0)
  - (0x60, 320, 240, 0, 0)
  - (0xC0, 240, 320, 0, 0)
  - (0xA0, 320, 240, 0, 0)

  Its default init includes INVON (0x21). Its constructor defaults to `color_order=BGR` and ORs 0x08 into MADCTL when BGR is set. It accepts `reset=None` and has `soft_reset()` (SWRESET). — [st7789py.py](https://github.com/russhughes/st7789py_mpy/blob/master/lib/st7789py.py)

### Inferences
- **[inference]** With st7789py_mpy, pass `color_order=st7789.RGB` to match the vendor's RGB setting. With the default BGR, red and blue will be swapped. If colours still look wrong, the usual fixes are: toggle BGR if red and blue are swapped; toggle INVON/INVOFF if the image looks like a negative (white shows as black).
- **[inference]** Landscape: use MADCTL 0x60 (MV|MX) or 0xA0 (MY|MV), rotation 1 or 3 in st7789py. Which one is "right side up" depends on where the connector sits (it is on a short edge). Test both.
- **[inference]** Offsets are 0,0 because a 240x320 panel uses the whole ST7789 240x320 frame memory. 135x240 and 240x240 panels need offsets; this one does not.

### Gaps
- There is no user report confirming colour behaviour on this exact board beyond the vendor code. The vendor's Adafruit sample passes 240x240 for both models (the comment says to use 240x320 for the 2.0").

## Q7. Known issues and practical notes

### Takeaway
No community issue reports specific to SWIFT-LCD-20 were found; the product dates from late 2025 and 2026. The design-level caveats are:
- no hardware reset line, so SWRESET is mandatory
- no backlight dimming or off control
- 3.3 V-only logic
- about 80 mA draw
- the vendor points MicroPython users to a CircuitPython-only driver

### Cited Findings
- 80 mA power consumption and 3.3–5 V supply. — [swift-lcd README](https://github.com/nulllaborg/swift-lcd)
- The backlight PMOS gate is hard-wired to GND via R1 0R. — [schematic](https://github.com/nulllaborg/swift-lcd/blob/main/picture/schematic_diagram.png)
- The README's MicroPython link is Adafruit_CircuitPython_ST7789 ("CircuitPython DisplayIO Driver"). — [swift-lcd README](https://github.com/nulllaborg/swift-lcd)
- The vendor repo shows 1 fork, 0 stars and 0 issues. — [nulllaborg repositories](https://github.com/orgs/nulllaborg/repositories?q=lcd)

### Inferences
- **[inference]** Suitable MicroPython drivers on ESP32 are russhughes `st7789py_mpy` (pure Python, easy) or the `st7789_mpy` C module (faster; needs custom firmware). Set width 240, height 320, reset=None, cs=Pin(CS), dc=Pin(DC), backlight=None, color_order=RGB, and keep inversion on.
- **[inference]** To dim or blank the screen, the only software option is DISPOFF (0x28) or SLPIN (0x10). Real dimming needs hardware rework: fit R2 0R, remove R1, and drive the LCD_BL net, which is not exposed.
- **[inference]** Power it from 5 V (as the vendor does) if the ESP32 board's 3.3 V regulator is marginal, because the module's own LDO then carries the 80 mA.

### Gaps
- No Amazon reviews or Q&A could be read to confirm field issues such as dead pixels, colour inversion or cable pinout mismatches.
