# LumosAir – Exhaust Airflow Monitor for the Lumos Ultra

*Design document, rev 2 — September 2026* (rev 2: named the pitot probe, added the rigid measuring spool vs. flex duct distinction, two-axis traverse, and Option C — today's system)

LumosAir is a low-cost, fully local system that measures airflow along the Lumos Ultra exhaust path and tells you when to raise the fan speed. It also flags a clogged duct, a leaking joint, a failing separator or a leaking dust bin. It has three parts:

1. **Sensor nodes**: two ESP32 boards with differential-pressure sensors connected to small tap holes in the duct.
2. **Transport**: UDP broadcast on the LAN (no setup), or MQTT so the readings can also go into Home Assistant.
3. **LumosAir desktop app** (.NET / WPF). It holds a physics model of the duct path, shows live CFM and air speeds, and diagnoses problems. A built-in simulator lets you test all of this before any hardware exists.

![System diagram](system-diagram.svg)

---

## 1. Key findings (read this first)

The numbers below come from the model in `app/` (`lumosair model …`). Two inputs are **estimates**: the S6 fan curve (built from AC Infinity's published 425 CFM / 503 Pa end points) and the internal resistance of the Lumos. Treat the numbers as ±25 % until the sensors are installed and calibrated. The conclusions do not change within that range.

1. **The 3" steel Dust Deputy and the CLOUDLINE S6 are not a good match.** Oneida lists a **minimum of 200 CFM** for the Heavy-Duty 3" Dust Deputy. Pushing 200 CFM through a 2-7/8" cyclone inlet takes roughly **3.4–9 inWC across the cyclone alone** (range covers typical cyclone loss coefficients K = 3–8). The S6 tops out at about **2 inWC (503 Pa) with no airflow at all**. With that cyclone installed, the model predicts **80–120 CFM** at speed 10, well below Oneida's minimum. Getting 200 CFM through that cyclone would take a shop-vac or dust-collector class blower, not an inline fan.
   ```
   lumosair model --cyc-inlet 2.875 --cyc-k 4 --need-cfm 200
   → system needs 1525 Pa (6.1 inWC); fan gives 392 Pa → NOT ENOUGH
   ```
2. **Brass is much easier to separate than wood dust, so a low-velocity cyclone can still work well.** Cyclone cut size scales with 1/√(particle density), and brass is about 8.5 g/cm³. Even at a modest ~1,600 fpm inlet speed, a cyclone with a 4" inlet has an estimated 50 % cut size near **2.6 µm for brass** (7.5 µm for wood char). The better fit is a **larger-inlet, lower-pressure-drop cyclone** that the S6 can actually drive. Manufacturers' minimum-CFM ratings are written for wood dust; the monitor measures whether your cyclone is actually working.
3. **Put nothing but a short smooth adapter between the Lumos and the cyclone.** The 3" outlet runs at roughly 2,000–2,900 fpm with the S6. That is below the ~3,500 fpm needed to keep brass airborne. The only safe amount of duct before the separator is almost none, which matches the pile of brass found inside the old 35 ft temporary hose.
4. **After the cyclone, the 6" flex run is not the bottleneck.** It costs about 40 Pa when the flex is pulled taut and about 60 Pa if it sags (friction multiplier 1.5 → 4.0), which moves the operating point by only 143 → 139 CFM. The Lumos 3" outlet, the 3"→4" adapter and the cyclone cost about 320 Pa between them. Replacing the 6" flex with smooth pipe gains little; the cyclone choice matters far more.
5. **Measure flow in a rigid 4" spool (Option A), not in 6" (Option B), and never in flex.** At the same flow, a pitot tube in 4" pipe sees about 47 Pa versus about 10 Pa in 6", which gives five times the signal for the same sensor.
6. **Fan-inlet suction runs around 400 Pa**, close to the full scale of a 500 Pa sensor. Use ±1 kPa sensors for the high-suction taps (fan inlet, run start and bin) so that a clog does not push them off scale.

### Estimated operating points (Option A, generic 4" inlet cyclone, K = 6)

| S6 level | CFM | 3" outlet fpm | Cyclone inlet fpm | 4" fpm | 6" fpm | Cyclone ΔP | d50 brass | d50 wood |
|---|---|---|---|---|---|---|---|---|
| 4 | 56 | 1,143 | 643 | 643 | 286 | 36 Pa | 4.1 µm | 12.0 µm |
| 6 | 85 | 1,723 | 969 | 969 | 431 | 81 Pa | 3.3 µm | 9.8 µm |
| 8 | 113 | 2,303 | 1,295 | 1,295 | 576 | 146 Pa | 2.9 µm | 8.4 µm |
| 10 | 142 | 2,884 | 1,622 | 1,622 | 721 | 228 Pa | 2.6 µm | 7.5 µm |

The full tables are in `model-optionA.txt`, `model-optionB.txt` and `model-optionC.txt`.

### Today's system (Option C, no separator): the brass has nowhere to drop out

Modelled as it stands now — 3" outlet, 3"→4", ~5 ft of 4", 4"→6", 30 ft of 6" flex, S6, wall cap:

| S6 level | CFM | 3" outlet fpm | 4" fpm | 6" fpm |
|---|---|---|---|---|
| 6 | 120 | 2,437 | 1,371 | 609 |
| 8 | 160 | 3,264 | 1,836 | 816 |
| 10 | 201 | 4,092 | 2,302 | 1,023 |

Brass needs roughly 3,500 fpm to stay airborne. Even at level 10 the 4" section is at ~2,300 fpm and the 6" run at ~1,020 fpm, so **the duct itself is acting as the separator** — which is exactly what the brass pile in the old temporary hose showed. The monitor reports this as "fan cannot reach safe transport velocity", and no fan level fixes it. The fix is a separator at the laser, not more fan speed.

### Why the monitor is built before the separator

The separator is the expensive, hard-to-reverse decision, and every number that decides it (real CFM, available fan pressure, cyclone pressure drop) is currently an estimate. The sensors turn those estimates into measurements. They then stay in place to verify the separator once it is installed: cut size, bin leaks, and whether brass still reaches the long run.

Install the sensor nodes on the **current** system first (the pitot section and the fan-inlet tap are enough). Then:

- Record CFM at every S6 level.
- Replace the estimated fan curve in `system.json` with your measured one.
- Run `lumosair model --config system.json --cyc-inlet <in> --cyc-k <K> --need-cfm <x>` for each candidate cyclone.

The flow you would get with each cyclone becomes a measured-model prediction instead of a guess.

---

## 2. Physical layout

```
Lumos Ultra ─3"─► short smooth 3"→4" ─► CYCLONE ─► 5 ft RIGID 4" spool ─► 4"→6" ─► 30 ft 6" flex ─► S6 ─► 1 ft ─► wall cap
 [encl tap]                  [cyc in tap]  │  [cyc out tap]   [PITOT]          [run-start tap]    [fan-in tap]
                                           └─► sealed steel drum  [bin tap]
```

**Option A (recommended)** is shown above. **Option B** replaces the 4" spool with 5 ft of rigid 6" pipe right after the cyclone: it saves about 12 Pa but gives a much weaker pitot signal. **Option C** is the system as it stands today, with no separator (`lumosair init --option C`); use it to measure before buying anything.

### Flexible duct versus the one rigid section

The exhaust run is **4" and 6" flexible duct**, and it stays that way. The single exception is the **rigid measuring spool**: about 5 ft of smooth 4" galvanized pipe holding the pitot probe. It exists only to give one stable, known-geometry measuring station, and it is not representative of the rest of the ducting.

That matters because flex duct has corrugations that disturb the velocity profile, a less well defined inside diameter, and a centreline that moves when the hose is repositioned. A centreline reading taken in flex can be repeatable one day and wrong the next. Since the pitot is the primary CFM measurement that every other sensor is cross-checked against, its station is worth making rigid.

The model already treats the flex as flex: `flex: true` with a friction multiplier (`flexFactor`) of 2.5, roughly 2.5× the friction of smooth pipe. Use 1.5 if the run is pulled taut and 4.0 if it sags. The rigid spool is the only duct element modelled as smooth.

Everything before the cyclone is "dirty side" and must be short, smooth, metal and bonded to ground. The fan sits on the clean side.

---

## 3. What is measured, where, and why

| Channel | Node | Sensor | + port | − port | Tells you |
|---|---|---|---|---|---|
| `cyc_dp` | laser | SDP810-500Pa | cyclone inlet wall tap | cyclone outlet wall tap | Cyclone restriction. Also a second flow meter once calibrated (ΔP ∝ Q²). |
| `bin` | laser | XGZP6897D ±1 kPa | room | tap in drum lid | **Bin leaks.** A leaking bin stops a cyclone from separating. |
| `pitot` | laser | SDP810-500Pa + Dwyer 166-6-CF | pitot total (1/8" OD) | pitot static (1/4" OD) | Actual CFM. |
| `run_in` | laser | XGZP6897D ±1 kPa | room | 6" run start wall tap | With `fan_in`: resistance of the long run (clog, kink or leak). |
| `encl` | laser | SDP810-500Pa | room | tube into the enclosure | Fume capture: is the Lumos under negative pressure? |
| `fan_in` | fan | XGZP6897D ±1 kPa | room | fan inlet wall tap | Total suction. With the fan curve, reveals outlet-side problems. |
| `env` | laser | BME280 | – | – | Air density for accurate CFM (Spokane is about 7 % thinner than sea level). |

**Wall taps.** Drill a 1/8" hole square to the wall and **deburr the inside** (burrs cause large errors). Glue or print a small saddle with a barb, and run 3/16" ID silicone tubing to the sensor. Tubing a few feet long is fine for static pressure. Mount all laser-node sensors inside one enclosure and run tubes to them; do not run I²C wires out to the duct.

### The pitot station

**Probe: Dwyer 166-6-CF** (Series 160 pocket-size pitot-static tube). 304 stainless; 1/8" (3.18 mm) stem; 6" insertion length; 3" tip; ASME / AMCA / ASHRAE tip geometry, so the **probe coefficient is 1.000 — no probe calibration needed**. The `-CF` suffix adds a 1/8" male-NPT adjustable compression mounting fitting. Dwyer's own sizing rule is that the duct should be at least 30× the probe diameter, which for a 1/8" probe means **4" minimum** — exactly our 4" spool. (The 167-6-CF is the same probe with a shorter 1-1/2" tip.)

**Placement.** In the 5 ft rigid 4" spool, about **4 ft downstream** of the cyclone outlet and about 1 ft before the 4"→6" adapter. That is roughly 12 duct diameters upstream and 3 downstream, comfortably past Dwyer's minimum of 8.5 upstream and 1.5 downstream. Point the tip straight into the flow; the hemispherical tip tolerates about 15° of misalignment.

**Mounting.** The compression fitting has 1/8" *male* NPT threads, so the spool needs a matching 1/8" **FNPT boss** — a small welded or brazed boss, or a sealed bulkhead fitting. Don't try to thread NPT into thin duct wall. The fitting then sets insertion depth, allows rotation for alignment, locks the probe and seals around the stem. Set the sensing axis to the true **centreline: 2.000" from the inside wall** of a 4.000" ID spool — measured from the inside wall, not from the outside face of the fitting, since the wall and boss add offset.

Fit **two bosses 90° apart** at the same station: one carries the probe, the other takes a plug and is used for the second traverse axis during commissioning.

**Tubing.** The Dwyer's connections are not two matching barbs: **total pressure is 1/8" OD, static pressure is 1/4" OD**, both smooth tubing stubs. The SDP810's own ports are about 5.2 mm OD, which suits the 3/16" ID silicone used elsewhere in the system. So use short transition pieces at the probe:

- total (1/8" OD) → 1/8" ID silicone → reducer → 3/16" ID main line → SDP810 **+**
- static (1/4" OD) → 1/4" ID silicone → reducer → 3/16" ID main line → SDP810 **−**

These lines carry no continuous flow, so the diameter changes cost nothing.

**Two corrections that are easy to confuse.** They are independent and both apply:

| | What it corrects | Value |
|---|---|---|
| Probe coefficient `Cp` | The probe's own tip geometry | 1.000 for this Dwyer — nothing to apply |
| `profileFactor` | Centreline velocity is higher than the duct average | 0.9 default, measured during commissioning |

Dwyer says the same thing: a centreline reading times 0.9 is good to about ±5 % in the field, while a full traverse is needed for ±2 %.

**Calibration traverse (do this once).** Because the probe sits downstream of a cyclone, residual swirl or an asymmetric profile is plausible, and a single-diameter traverse could bias the result. Use a **two-axis, six-point equal-area traverse**: six depths along one diameter, then the same six through the second boss 90° away, 12 readings total. For a 4.000" ID spool the equal-area depths from the inside wall are:

| Point | Fraction of D | Depth |
|---|---|---|
| 1 | 0.043 | 0.172" |
| 2 | 0.146 | 0.584" |
| 3 | 0.296 | 1.184" |
| 4 | 0.704 | 2.816" |
| 5 | 0.854 | 3.416" |
| 6 | 0.957 | 3.828" |

Average the **square roots** of the 12 velocity-pressure readings (velocity ∝ √ΔP, so averaging raw pressures overstates the mean), then set `profileFactor` = mean velocity ÷ centreline velocity.

**Signal size.** The app's `pitot` channel predicts the *centreline* velocity pressure, which is the duct-average value divided by `profileFactor²`. At the flows this system reaches, the mean VP in the 4" spool runs about 6 Pa at 56 CFM to 38 Pa at 142 CFM; the centreline readings the sensor actually sees are about 7 and 47 Pa. An SDP810-500Pa has plenty of headroom there, with roughly 0.1 Pa of zero-point error. The SDP810-125Pa would fit the range more tightly but improves zero-point error only to about 0.08 Pa, which doesn't justify a second part number.

**Pitot tips clog.** The app cross-checks the pitot against the pressure taps and flags a suspect pitot automatically, falling back to the tap consensus for flow.

**Leaks between taps.** Seal every joint on the suction side with foil tape (a mastic seal is better). A leak lowers the reading at every downstream tap and shows up as "run losing suction".

---

## 4. Choosing the separator

Requirements derived from the model:

| Requirement | Target | Why |
|---|---|---|
| Inlet size | **4"–5" equivalent** (not 3") | Keeps cyclone ΔP within what the S6 can supply (≲ 150–250 Pa at your flow). |
| Pressure drop at 150 CFM | **< 1 inWC (250 Pa)** | The S6 makes less than 2 inWC at that flow, and about 0.8 inWC is already used by the Lumos, adapters, duct and wall cap. |
| Construction | Steel, grounded, sealed drum | Metal dust (combustible-dust practice). |
| Drum | 20–30 gal, sealed lid, tap for the `bin` sensor | Keeps the bin from leaking. |
| Verification | Measured with this system | Watch the cut size in the app and inspect the downstream duct after 25 and 50 coins. |

Candidates to evaluate (plug each into `lumosair model` with its real inlet size):
- **Oneida Heavy-Duty 3" Steel Dust Deputy** (~$400). Its 200 CFM minimum is not reachable with the S6 (see §1). It would suit a high-static-pressure blower instead.
- **Larger Oneida steel cyclones (4"/5" Super Dust Deputy class).** Oneida's FAQ describes the Super Dust Deputy as intended for systems above about 350 CFM, so ask Oneida about low-flow operation. For dense brass, the physics suggests separation can still be useful at lower speed, and the monitor will show whether it is.
- **A cyclone you design yourself (e.g. 3D printed, 4" inlet)**, sized for 120–180 CFM using the Lapple proportions in `SystemModel.CycloneCutSize`. For metal dust, use a conductive material or a metal liner and ground it.

If you want to keep the 3" steel Dust Deputy, the fan has to change: roughly **5–9 inWC at 200 CFM**, which means a dust-extractor or regenerative-blower class machine.

---

## 5. Hardware (BOM)

See `BOM.csv` for the full list. Prices are approximate as of September 2026; check before ordering.

| Item | Qty | Approx. |
|---|---|---|
| ESP32-WROOM-32 DevKit | 2 | $8–12 ea |
| Sensirion SDP810-500Pa (tube-connected, I²C) | 3 | ~$35–50 ea |
| CFSensor XGZP6897D, ±1 kPa, I²C | 3 | ~$8–15 ea |
| TCA9548A I²C multiplexer breakout | 1 | ~$5–8 |
| BME280 breakout | 1 | ~$5–10 |
| Dwyer 166-6-CF pitot-static probe | 1 | $160–220 |
| 1/8" FNPT boss / bulkhead fittings (probe + spare port) | 2 | ~$10–30 |
| 3/16" ID silicone tubing, 10 m (+ short 1/8" and 1/4" ID pieces and reducers) | 1 | ~$15–20 |
| Barbed tap fittings or printed saddles | 8 | ~$10 |
| 4" rigid galvanized pipe, 5 ft + couplers + foil tape | 1 | ~$20–35 |
| Enclosures, USB 5 V supplies, Dupont/JST leads | 2 | ~$30 |
| **Total (excluding cyclone)** | | **≈ $390–540** |

The Dwyer is the single largest line item outside the separator. It is worth it here because the pitot is the reference every other channel is compared against, and because at 1/8" it is one of the few probes rated for a 4" duct. New distributor pricing sits around $160–$220; surplus listings are sometimes half that. A generic probe will work, but then its coefficient is unknown and has to be calibrated against something else.

**Wiring (laser node).**
- ESP32 GPIO21 (SDA) and GPIO22 (SCL) go to the TCA9548A and the BME280. Each sensor goes on its own mux port 0–4.
- Both sensor types have fixed I²C addresses (SDP810 = 0x25, XGZP = 0x6D), which is why the mux is needed.
- Use 3.3 V for all parts.
- Keep I²C leads under 30 cm. Most breakouts already carry 4.7–10 kΩ pull-ups.

**Fan node:** one XGZP6897D wired directly to GPIO21/22. Set `TCA9548A_ADDR 0` if you leave out the mux.

---

## 6. Commissioning

1. **Flash** both nodes: `pio run -e laser -t upload`, then `-e fan`. Watch the serial monitor; every channel should print `ok`.
2. **Zero**: fan off, lid closed, wait 10 s, then click **Zero sensors** in the app. Offsets are stored on each node.
3. **Fan curve** (optional but valuable): record CFM and `fan_in` at levels 1–10. Put the measured points into `fan.curveCfm` / `fan.curvePa`. The fan's pressure is about `fan_in` plus the loss downstream of the fan.
4. **Cyclone K**: at level 10, K = `cyc_dp` ÷ (½ρV²) using the cyclone inlet velocity. Enter it in `cyclone.k`.
5. **Pitot traverse**: run the two-axis six-point traverse from §3 (12 readings), average the square roots of the readings, and set `profileFactor` = mean ÷ centreline. Then return the probe to the 2.000" centreline and lock the compression fitting.
6. **Baseline**: with a clean duct and an empty drum, run at your normal level and click **Capture baseline**. From then on, drift is measured against this known-good state.
7. **Verify**: engrave 25 coins, weigh the drum catch, and look inside the 6" run just after the 4"→6" expansion.

---

## 7. How the diagnostics work

Every sensor reading is converted into "the flow that would explain this reading" using the healthy model, corrected by the baseline. When they all agree, the system is healthy. The first one that disagrees points to where the problem is.

| Finding | Trigger | Typical cause |
|---|---|---|
| Duct velocity too low before separator | slowest pre-separator duct < material minimum | Duct between the Lumos and the cyclone, or fan too slow |
| Cyclone too slow to separate well | estimated cut size > material target, or inlet < ~1,000 fpm | Fan level too low |
| Cyclone ΔP above / below normal | ≥ 30 % drift | Build-up / leak, clogged tap |
| Dust bin leaking | bin suction ≥ 30 % below normal | Lid or gasket |
| Long run restricted / heavily restricted | run ΔP ≥ 30 % / 60 % above normal | Deposit, kink, crushed flex |
| Long run losing suction | run ΔP ≥ 30 % below normal | Loose joint or leak |
| Pitot doesn't match other sensors | pitot ≥ 20 % off the tap consensus | Clogged pitot (app switches to the consensus) |
| Less flow than the fan should move | measured flow ≥ 20 % below the fan curve at the measured suction | Outside damper stuck, screen clogged, impeller fouled |
| Enclosure not under enough suction | < 3 Pa | Lid open, outlet disconnected |
| Fan cannot reach safe transport velocity | even level 10 isn't enough | System redesign needed |
| Node offline / sensor fault / saturated | – | Power, Wi-Fi, wiring, sensor range |

**Recommended level** is the lowest S6 level that meets every requirement: duct velocity before the separator, cyclone cut size, and cyclone minimum speed. It uses the fan laws (flow ∝ speed).

All nine simulated faults are covered by automated tests (`app/tests`). Each is detected correctly, with no false alarms on the healthy system.

---

## 8. Phase 2 ideas

- **Automatic fan speed.** The community has reverse-engineered the CLOUDLINE UIS controller port for ESP32 control. Verify the pinout with a scope before connecting anything. The app already calculates the level to set.
- **Home Assistant.** Enable MQTT in the firmware; the telemetry topics can be added as MQTT sensors, and "Jim Bob" could announce "cyclone bin leaking".
- **Downstream dust check.** A PM sensor on a small sample line after the cyclone would give a direct "is brass getting through" signal.
- **Drum weight.** A load cell under the drum would log grams captured per job.

## 9. Assumptions and limits

- The fan curve and the Lumos internal resistance are estimates until measured (see §6).
- Cyclone K and cut size use the Shepherd–Lapple and Lapple correlations. They are good for trends and ±30 % absolute.
- Sub-micron fume is not separated by any cyclone. It goes outside with the exhaust, as it does today.
- Pressure-based flow needs air moving well above about 30 CFM to be meaningful. Below that the app reports "fan off" rather than diagnosing.
- Flex duct friction is modelled with a multiplier (`flexFactor`, default 2.5). Real flex varies from about 1.5 pulled taut to 4+ sagging; at this system's flows that whole range moves the operating point by only a few CFM, but it matters more if the run is ever lengthened.
- The pitot's `profileFactor` starts at Dwyer's field value of 0.9 and is only as good as the traverse that replaces it. Swirl downstream of a cyclone is the reason for the two-axis traverse.
