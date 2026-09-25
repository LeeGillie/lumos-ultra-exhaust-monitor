# Pigtail cable wire colours on the NULLLAB / "SWIFT-LCD-20" 2.0" ST7789 module

Scope: can the colours on the 6-wire pigtail that ships with the module be trusted, and does the photo-derived mapping hold: red=CS, black=DC, yellow=SDA, green=SCL, blue=V (power), white=G (ground)?

Labels used below: **[PRODUCT]** = documented for this exact product; **[CONVENTION]** = general industry or ecosystem convention; **[INFERENCE]** = my reasoning, not directly sourced.

Research limits: Amazon product pages would not render through the fetch tool (only page scaffolding came back), so I could not read the listing images, Q&A or reviews directly. Product facts below come from search-engine extracts of the Amazon listing text. "SWIFT-LCD-20" returned no hits anywhere. It is probably a silkscreen or internal part number, not a searchable product name.

## 1. What is documented for this exact product (NULLLAB 2.0" ST7789, 240x320)

### Takeaway
The listing describes the board-side connector as **JST GH 1.25 mm** and the cable as a "GH1.25 to Dupont 6-pin anti-reverse cable". It gives the pin set as G, V, SCL, SDA, DC, CS, with RES and BLK tied internally. I found no published wire-colour table, and no review or Q&A that states the colours or warns that red is not VCC.

### Cited Findings
- [PRODUCT] NULLLAB 2.0" module: 240x320, ST7789 driver, 4-wire SPI, 3.3–5.0 V supply, typical supply current 80 mA, board 56 x 40 mm — [Amazon NULLLAB 2.0" (B0GVF8R5ZL)](https://www.amazon.com/NULLLAB-Interface-Compatible-Embedded-Projects/dp/B0GVF8R5ZL); the 2-pack is [B0H2Y83TYG](https://www.amazon.com/NULLLAB-Interface-Compatible-Embedded-Projects/dp/B0H2Y83TYG) (search-engine extract of the listing text; page not directly readable).
- [PRODUCT] Pin interface definitions listed as Ground (G), Power Supply (V), SPI clock (SCL), SPI data (SDA), Data/Command (DC), Chip Select (CS). RES and BLK are "pre-configured internally" (not brought out) — same listing extract as above.
- [PRODUCT] "The module includes a GH1.25 interface and comes with a GH1.25 to Dupont 6-pin anti-reverse cable" — same listing extract as above. There is also a sibling 1.3" 240x240 version from the same seller: [B0H2YCCDZC](https://www.amazon.com/NULLLAB-Interface-Compatible-Embedded-Projects/dp/B0H2YCCDZC), [B0GVFCF89S](https://www.amazon.com/NULLLAB-Interface-Compatible-Embedded-Projects/dp/B0GVFCF89S).
- [PRODUCT] Searching for "SWIFT-LCD-20 ST7789" returned no matching product, datasheet or documentation — [search results incl. Amazon ST7789 listing page](https://www.amazon.com/st7789/s?k=st7789).

### Inferences
- [INFERENCE] The listing names G, V, SCL, SDA, DC, CS. The photo labels read CS, DC, SDA, SCL, V, G from left to right. That is the same order, read from the other end. So the silkscreen order in the photo agrees with the listing, and either CS or G is physical pin 1.
- [INFERENCE] "Anti-reverse" only means the housing is keyed, so the plug cannot go into the board socket backwards. It says nothing about the colours at the Dupont end, which are loose single sockets. That end has no keying, so a user can put any wire on any header pin.
- [INFERENCE] The listing's own pin order puts power and ground at one end of the connector (G, V) and CS at the other. If the cable maker put the first colour of a stock kit (red) on the pin at the CS end, red ends up as CS. That is exactly what the photo shows.

### Gaps
- Could not read the Amazon listing images, Q&A or reviews (the page is rendered by JavaScript and the fetch tool got none of it). A listing image may show a colour-coded wiring diagram. This is worth checking by hand in a browser.
- No source says whether the module has an on-board LDO or level shifting (implied by "3.3V-5V compatible", but not documented), or what protection sits on the V pin.

## 2. Do generic pre-crimped JST cables follow a colour convention? Is red always pin 1?

### Takeaway
No. There is no single convention. Generic pre-crimped kits are sold as a bag of rainbow colours: red, black, yellow, white, blue, green. The assembler picks the order. Some branded cables put **black** on pin 1 (Pololu). Some ecosystems put **yellow** on pin 1 (Grove). Qwiic puts black (GND) on pin 1. The drone and Pixhawk world only requires that the VCC wire be red, wherever VCC sits. Red on pin 1 is common on cheap rainbow cables, but that is a manufacturing habit and says nothing about which signal the wire carries.

### Cited Findings
- [CONVENTION] Pololu 6-pin JST SH-style cable: "the black wire connects to pin 1 and the red wire connects to pin 2". The female-female cable is straight-through (same pin to same pin) — [Pololu 5546](https://www.pololu.com/product/5546); category page: [Pololu 6-pin JST SH cables](https://www.pololu.com/category/351/6-pin-jst-sh-style-cables).
- [CONVENTION] Generic GH1.25 pre-crimped wire kits are sold as loose colours ("Red, Black, Yellow, White, Blue, Green"), single-ended or double-ended, for the buyer to insert in any order — [Teansic GH1.25 kit](https://www.amazon.com/Teansic-Connector-Temperature-pre-Crimped-Controller/dp/B0FHGN5Y22); [JTSINERU GH kit](https://www.amazon.com/JTSINERU-JST-GH-Connector-Pre-Crimped-Housing/dp/B0D796WG12); GH-to-Dupont kits: [Ssighuyx](https://www.amazon.com/Ssighuyx-Dupont2-54-Connector-Pre-Crimped-Compatible/dp/B0CMZJ297H), [GH1.25-to-Dupont kit](https://www.amazon.com/Dupont2-54-Pre-Crimped-Connectors-Pixhawk4-Pixhawk2/dp/B087N4GY8Z) (search-engine extracts).
- [CONVENTION] Adafruit's JST GH 6-pin cable only says "the wires are even color coded!" and gives no colour-to-pin table — [Adafruit 5754](https://www.adafruit.com/product/5754).
- [CONVENTION] Pixhawk connector standard (JST GH): only the VCC wire must be red. Pin 1 on Pixhawk 6-pin ports is VCC and the last pin is GND (e.g. GPS: VCC/TX/RX/SCL/SDA/GND) — [Dronecode Pixhawk connector standard](https://wiki.dronecode.org/workgroup/connectors/start); [DS-009 Pixhawk Connector Standard](https://github.com/pixhawk/Pixhawk-Standards/blob/master/DS-009%20Pixhawk%20Connector%20Standard.pdf); PX4 cable tables list red as +5V for I2C/SPI/UART/CAN — [PX4 Cable Wiring](https://docs.px4.io/main/en/assembly/cable_wiring) (search-engine and fetch-tool extracts).
- [CONVENTION] A search-engine extract from the drone and GH-cable results carried the warning "the red wire may NOT be pin #1 (+Ve) – please carefully check the pin numbers printed on the PCB and do not rely on wire colors" — surfaced with [XTORI GH1.25 cable listing](https://www.amazon.com/Pixhawk2-Pixhack-Pixracer-Dronecode-connectors/dp/B07FKSPSF9) / [ArduSimple Pixhawk cable set](https://www.ardusimple.com/product/pixhawk-cable-set/). **I could not confirm which of these pages the sentence comes from.** Treat it as unverified.

### Inferences
- [INFERENCE] A JST-to-Dupont pigtail has only one keyed end, so "straight-through" has no meaning for it. The only thing that fixes which wire is pin 1 is the order the assembler (or crimping machine) put the wires into the JST housing. With stock rainbow kits, the first colour, often red, typically goes into housing cavity 1. Cavity 1 then lands on whatever signal the board designer put on pin 1. Here that appears to be CS, or G if the housing is numbered from the other side.
- [INFERENCE] The photo order red, black, yellow, green, blue, white is almost the same as the kit colour list red, black, yellow, white, blue, green, with green and white swapped. That fits "wires inserted in kit colour order", not "colours chosen per signal". So the colours carry no meaning and are only there to tell the wires apart.

### Gaps
- No manufacturer drawing for this specific pigtail was found, so the photo-derived mapping remains the only product-specific evidence.
- mattmillman.com's JST guide failed to fetch (TLS certificate error), so its notes on cable colour habits could not be used.

## 3. How common is the "red is not power" hazard? Examples

### Takeaway
It is common and well known. Even within one vendor, colour schemes change between product revisions. The major ecosystems all differ. Grove uses yellow/white/red/black with red on pin 3. Qwiic uses black/red/blue/yellow with red on pin 2. Pololu puts black on pin 1 and red on pin 2. On this NULLLAB cable, if the photo is right, red and black are CS and DC, so a "red = VCC, black = GND" habit would miswire every line.

### Cited Findings
- [CONVENTION] Seeed Grove: Pin 1 yellow (SCL / D0), Pin 2 white (SDA / D1), Pin 3 red (VCC), Pin 4 black (GND) — [Seeed Grove System wiki](https://wiki.seeedstudio.com/Grove_System/).
- [CONVENTION] SparkFun Qwiic: pin order GND / 3.3V / SDA / SCL, colours black / red / blue / yellow. Board connector SM04B-SRSS-TB, cable SHR-04V-S (JST SH, 1.0 mm) — [SparkFun Qwiic](https://www.sparkfun.com/qwiic). Note: the fetch-tool summary said "1.25mm pitch", but the SRSS/SHR part numbers it quoted are JST **SH (1.0 mm)**. I treat the 1.25 mm figure as a summarisation error. See also [Qwiic Adapter README](https://github.com/sparkfunX/Qwiic_Adapter/blob/master/README.md).
- [CONVENTION] The same vendor changed colours between versions: Adafruit's DS18B20 (3846) moved from orange/white/blue to red/black/white wires in May 2022, while model 642 uses yet another scheme — [DigiKey forum: Changed wiring colors for Adafruit DS18B20](https://forum.digikey.com/t/changed-wiring-colors-for-adafruit-ds18b20/25170).
- [CONVENTION] A forum thread about inconsistent I2C cable colours exists — [Adafruit forum: I2C wire-color convention??](https://forums.adafruit.com/viewtopic.php?t=186532) (found in search; not fetched).

### Inferences
- [INFERENCE] With the photo mapping, a user who trusts "red = +, black = −" and plugs red to 3V3 and black to GND would put 3.3 V on CS and 0 V on DC. The real V (blue) and G (white) wires would then go to GPIOs.
- [INFERENCE] In that miswiring the true supply is not reversed. The more likely failure is **back-powering**: the module runs through its CS input's protection diode (see Q4), and the GPIO wired to V would have to source the module's ~80 mA.

### Gaps
- I found no Reddit or Arduino-forum thread about this exact NULLLAB cable. Generic searches for "red wire not VCC" threads returned only product listings.

## 4. Consequences of reversed power or VCC on a data pin (ST7789 module + ESP32)

### Takeaway
Reversed supply polarity can destroy the module. VCC applied to a data pin while the module's own supply is off back-powers the chip through its I/O protection diodes. Those diodes are made for short ESD pulses, not a steady supply current. Sustained current can damage the diode or the IC. It can also load the ESP32's 3V3 rail or GPIO beyond its rating. These are general electronics points; I found no product-specific failure reports.

### Cited Findings
- [CONVENTION] Reversing the supply polarity on ST7789 modules may damage the display. Avoid hot-plugging and check wiring before powering up — [ikkaro ST7789 guide](https://www.ikkaro.net/how-to-use-an-st7789-tft-display-with-arduino/); [ComponentIndex ST7789](https://componentindex.net/components/st7789/) (search-engine extracts, not fetched).
- [CONVENTION] Reverse-polarity example for another small module: [Arduino Forum – Accidentally reversed VCC and GND on nRF24L01](https://forum.arduino.cc/t/accidentally-reversed-vcc-and-gnd-on-nrf24l01/1257965) (not fetched).
- [CONVENTION] Back-powering: "What if your GPIO is powered, but your VCC isn't? Power will flow from the GPIO into VCC" through the ESD diodes — [Hackaday: Hacker Tactic: ESD Diodes](https://hackaday.com/2025/06/19/hacker-tactic-esd-diodes/).
- [CONVENTION] ESD diodes run from the signal to VCC and to GND and conduct beyond about VCC+0.7 V or GND−0.7 V. Low-voltage, high-current (100+ mA), long-duration electrical overstress can damage them — [mbedded.ninja: Protecting IO lines from ESD](https://blog.mbedded.ninja/electronics/circuit-design/esd-protection/protecting-io-lines-from-esd/) (search-engine extract).

### Inferences
- [INFERENCE] Worst case, fully swapped: 3V3 on G and GND on V. Any on-board LDO or backlight-driver input would see reverse voltage, and the ESP32 3V3 rail could be pulled down by a short through the module's substrate diodes. That can brown out or reset the ESP32, or heat the dev board's regulator.
- [INFERENCE] The typical ~80 mA module draw (listing figure) is well above what a single GPIO should source. So if V is wired to a GPIO, expect a dead or dim display and a GPIO under stress, not a working screen.
- [INFERENCE] Since the pins run G, V, SCL, SDA, DC, CS, getting only the two power wires swapped is a realistic mistake. Swapping G and V keeps every signal in place, so the display "almost" works except for power. It is the most important pair to check.

### Gaps
- No source found on the NULLLAB board's input protection (reverse-polarity diode, LDO part number).
- ESP32 GPIO absolute-maximum source current and injection-current limits were not looked up in this pass (the ESP32 datasheet would be the source).

## 5. Recommended verification method

### Takeaway
Do not trust the colours. With nothing powered, plug the pigtail into the module and use a multimeter in continuity (beep) mode. Probe each Dupont socket against the module's labelled points and record the actual mapping. Mark power and ground clearly before connecting to the ESP32.

### Cited Findings
- [CONVENTION] Guidance in the drone and GH-cable ecosystem is to "carefully check the pin numbers printed on the PCB and do not rely on wire colors" — see Q2 (source page unconfirmed).
- [CONVENTION] General ST7789 advice is to double-check connections before powering up, since one miswire can damage the display, sensor or MCU pin — [ikkaro ST7789 pinout guide](https://www.ikkaro.net/st7789-tft-display-pinout/) (search-engine extract).

### Inferences
- [INFERENCE] Procedure:
  1. Leave everything unpowered and plug the cable into the module's GH socket.
  2. Set the meter to continuity. Put one probe into a Dupont socket; a pin or a short solid-core wire makes contact easier.
  3. Touch the other probe to each labelled point in turn. Use the 0.1" through-holes if the module has them. Otherwise use the solder joints of the GH socket, reading the silkscreen labels in the photo.
  4. Record wire colour → label for all 6 wires. Also check that no two wires beep to each other, which would show a crimp short.
  5. Measure resistance between the V and G points on the module. It should be well above 0 Ω (not a short). Note the reading for later comparison.
  6. Label the V and G sockets with tape or heat-shrink. Better still, re-pin them into a keyed 2-way Dupont housing so they cannot be swapped.
  7. First power-up: power V/G from a current-limited bench supply (e.g. 3.3 V, 150 mA limit) if one is available. Confirm the current is around the expected ~80 mA or less before connecting the ESP32 data lines.
- [INFERENCE] Expected result if the photo is right: red→CS, black→DC, yellow→SDA (MOSI), green→SCL (SCK), blue→V, white→G.

### Gaps
- Whether the module has separate 0.1" through-holes in addition to the GH socket is not documented in the sources found; check the physical board.

## 6. Connector identity (6-pin, ~1.25 mm vs ~2 mm pitch)

### Takeaway
The listing says **JST GH 1.25 mm** (or a GH-compatible clone). GH has a positive latch, which matches "anti-reverse / locking". SH (1.0 mm) and PH (2.0 mm) are friction-lock. A 6-pin GH housing is about 8.7 mm across its 6 pins (5 x 1.25 mm pitch plus housing walls). A PH 6-pin would be noticeably wider, about 10 mm pin-to-pin plus walls.

### Cited Findings
- [PRODUCT] The listing states a GH1.25 interface and a GH1.25-to-Dupont cable — [Amazon NULLLAB 2.0"](https://www.amazon.com/NULLLAB-Interface-Compatible-Embedded-Projects/dp/B0GVF8R5ZL) (search-engine extract).
- [CONVENTION] Pitches: SH 1.0 mm, GH 1.25 mm, ZH 1.5 mm, PH 2.0 mm. GH has a positive latching mechanism; SH, ZH and PH use friction retention. GH is typical of flight controllers and Pixhawk, PH of batteries and general sensors — [Keszoox JST connector types guide](https://keszoox.com/blogs/news/jst-connector-types-guide). Another search-engine extract said "SH has a side latch" and "ZH/PH top latch"; that conflicts with the fetched Keszoox page and with SH being friction-lock, so I discount it — [Keszoox GH guide](https://keszoox.com/blogs/news/jst-gh-connector-pixhawk-guide); [Telewiretech comparison](https://www.telewiretech.com/blogs/technical-resources/jst-connector-comparison-ph-vs-xh-vs-sh-vs-zh-vs-gh-for-board-to-wire-applications).
- [CONVENTION] Pixhawk chose JST GH as its default connector for its latch lock at small size — [Dronecode Pixhawk connector standard](https://wiki.dronecode.org/workgroup/connectors/start) (search-engine extract).

### Inferences
- [INFERENCE] If the housing measures about 1.25 mm between wires and has a small latch tab that must be pressed to unplug, it is GH, consistent with the listing. If it is about 2 mm with no latch, it would be PH, which would contradict the listing. A quick check with calipers or a ruler across the 6 contacts is enough: about 6.25 mm for GH versus about 10 mm for PH, measured between the outer contact centres.
- [INFERENCE] The pitch is not the same as a Dupont header's (GH is 1.25 mm, Dupont is 2.54 mm). So a GH pigtail is the practical way to connect to this module, and re-crimping the GH end is fiddly. Correct the colour meaning at the Dupont end by labelling or re-housing the sockets.

### Gaps
- Not physically measured; this relies on the listing text plus general JST dimensions.
