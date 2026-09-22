using System.Text.Json;
using LumosAir.Core.Config;
using LumosAir.Core.Model;
using LumosAir.Core.Telemetry;

namespace LumosAir.Core.Diagnostics;

public enum Severity { Ok = 0, Info = 1, Advice = 2, Warning = 3, Critical = 4 }

public sealed record Finding(string Code, Severity Severity, string Title, string Detail, string? Action = null);

public sealed record SegmentStatus(string ElementId, string Name, Zone Zone, ElementType Type,
    double DiameterIn, double VelocityFpm, double MinFpm, Severity Severity);

public sealed record ChannelStatus(string Key, string Label, ChannelRole Role, double? ReadingPa,
    double PredictedPa, double? Drift, double? FlowCfm, bool Stale, bool Ok);

public sealed class DiagnosticSnapshot
{
    public DateTimeOffset Time { get; init; }
    public AirState Air { get; init; }
    public double FlowCfm { get; init; }
    public string FlowSource { get; init; } = "";
    public int FanLevel { get; init; }
    public int? RecommendedLevel { get; init; }
    public double ModelFlowCfm { get; init; }
    public double? CycloneInletFpm { get; init; }
    public double? CycloneDpPa { get; init; }
    public double? CutSizeMicron { get; init; }
    public double? Efficiency5Micron { get; init; }
    public double? MinPreSeparatorFpm { get; init; }
    public IReadOnlyList<SegmentStatus> Segments { get; init; } = Array.Empty<SegmentStatus>();
    public IReadOnlyList<ChannelStatus> Channels { get; init; } = Array.Empty<ChannelStatus>();
    public IReadOnlyList<Finding> Findings { get; init; } = Array.Empty<Finding>();
    public bool BaselineCaptured { get; init; }
    public Severity Overall => Findings.Count == 0 ? Severity.Ok : Findings.Max(f => f.Severity);
}

/// <summary>Stored "known good" corrections, captured with a clean system (measured ÷ model).</summary>
public sealed class Baseline
{
    public DateTimeOffset CapturedAt { get; set; }
    public double FlowCfm { get; set; }
    public int FanLevel { get; set; }
    public Dictionary<string, double> Corrections { get; set; } = new();

    public void Save(string path) => File.WriteAllText(path, JsonSerializer.Serialize(this, SystemConfig.JsonOptions));
    public static Baseline? TryLoad(string path)
    {
        try { return File.Exists(path) ? JsonSerializer.Deserialize<Baseline>(File.ReadAllText(path), SystemConfig.JsonOptions) : null; }
        catch { return null; }
    }
}

/// <summary>
/// Turns raw telemetry into flow, velocities and findings. Thread-safe: call <see cref="Ingest"/> from any thread,
/// <see cref="Evaluate"/> from the UI timer.
/// </summary>
public sealed class DiagnosticsEngine
{
    private readonly object _gate = new();
    private readonly Dictionary<string, (double value, DateTimeOffset at, bool ok, double raw)> _readings = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, DateTimeOffset> _nodeSeen = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, DateTimeOffset> _pending = new();
    private EnvReading? _env;
    private int? _reportedFanLevel;
    private bool _reportedFanDriven;

    public SystemModel Model { get; private set; }
    public SystemConfig Config => Model.Config;
    public Baseline? Baseline { get; set; }
    public int ManualFanLevel { get; set; }
    public Func<DateTimeOffset> Clock { get; set; } = () => DateTimeOffset.UtcNow;

    public DiagnosticsEngine(SystemConfig config, Baseline? baseline = null)
    {
        Model = new SystemModel(config);
        Baseline = baseline;
        ManualFanLevel = config.Fan?.Fan?.CurrentLevel ?? 10;
    }

    public void Reconfigure(SystemConfig config)
    {
        lock (_gate) { Model = new SystemModel(config); _pending.Clear(); }
    }

    public static string Key(ChannelConfig c) => $"{c.Node}/{c.Channel}";

    public void Ingest(TelemetryFrame frame)
    {
        lock (_gate)
        {
            var now = frame.ReceivedAt;
            _nodeSeen[frame.Node] = now;
            if (frame.Env is { } env) _env = env;
            if (frame.FanLevel is { } lvl) { _reportedFanLevel = lvl; _reportedFanDriven = frame.FanDriven; }
            double tau = Math.Max(0.01, Config.Thresholds.SmoothingSeconds);
            foreach (var (name, r) in frame.Channels)
            {
                string key = $"{frame.Node}/{name}";
                if (!r.Ok || double.IsNaN(r.Pa))
                {
                    _readings[key] = (_readings.TryGetValue(key, out var old) ? old.value : double.NaN, now, false, r.Pa);
                    continue;
                }
                if (_readings.TryGetValue(key, out var prev) && prev.ok && !double.IsNaN(prev.value))
                {
                    double dt = Math.Clamp((now - prev.at).TotalSeconds, 0, 10);
                    double alpha = 1 - Math.Exp(-dt / tau);
                    _readings[key] = (prev.value + alpha * (r.Pa - prev.value), now, true, r.Pa);
                }
                else _readings[key] = (r.Pa, now, true, r.Pa);
            }
        }
    }

    /// <summary>
    /// The fan level to model with. A node's reported level counts only when it is
    /// actually driving the fan; with the output disabled it is echoing the last
    /// command and cannot see the physical dial, so the level you set here wins.
    /// </summary>
    public int CurrentFanLevel =>
        _reportedFanLevel is { } lvl && _reportedFanDriven ? lvl : ManualFanLevel;

    private AirState CurrentAir() => _env is { } e
        ? new AirState(e.TemperatureC, e.RelativeHumidity, e.PressurePa)
        : new AirState(Config.Air.TemperatureC, Config.Air.RelativeHumidity, Config.Air.PressurePa);

    private double Corr(string key) => Baseline?.Corrections.TryGetValue(key, out var c) == true && c > 0 ? c : 1.0;

    private bool TryGet(ChannelConfig? ch, DateTimeOffset now, out double value)
    {
        value = double.NaN;
        if (ch is null) return false;
        if (!_readings.TryGetValue(Key(ch), out var r) || !r.ok || double.IsNaN(r.value)) return false;
        if ((now - r.at).TotalSeconds > Config.Thresholds.StaleSeconds) return false;
        value = r.value;
        return true;
    }

    private ChannelConfig? Role(ChannelRole role) => Config.Channels.FirstOrDefault(c => c.Role == role);

    /// <summary>Estimate current flow from the best available evidence.</summary>
    private (double q, string source) EstimateFlow(DateTimeOffset now, AirState air)
    {
        // FlowFromReading returns NaN when a tap's predicted signal is too small to
        // invert. That is "this tap cannot tell us", not "the flow is NaN", so fall
        // through to the next source rather than handing a NaN to everything
        // downstream — the segment velocities, the cyclone cut size and the status
        // broadcast all derive from this number.
        var pitot = Role(ChannelRole.PitotVp);
        if (TryGet(pitot, now, out var vp) && Usable(Model.FlowFromPitot(pitot!, Math.Max(0, vp), air), out var qp))
            return (qp, "pitot");
        var cyc = Role(ChannelRole.CycloneDp);
        if (TryGet(cyc, now, out var dp)
            && Usable(Model.FlowFromReading(cyc!, dp, air, Corr(Key(cyc!))), out var qc))
            return (qc, "cyclone ΔP");
        var fanIn = Role(ChannelRole.FanInletSuction);
        if (TryGet(fanIn, now, out var fs)
            && Usable(Model.FlowFromReading(fanIn!, fs, air, Corr(Key(fanIn!))), out var qf))
            return (qf, "fan-inlet suction");
        return (Model.OperatingFlow(CurrentFanLevel, air), "model only");
    }

    private static bool Usable(double q, out double value)
    {
        value = q;
        return double.IsFinite(q);
    }

    public DiagnosticSnapshot Evaluate()
    {
        lock (_gate)
        {
            var now = Clock();
            var air = CurrentAir();
            var th = Config.Thresholds;
            var profile = Config.ActiveProfile;
            var raw = new List<Finding>();
            int level = CurrentFanLevel;
            double s = Model.SpeedFraction(level);

            // 1. Node health
            var expectedNodes = Config.Channels.Select(c => c.Node).Distinct(StringComparer.OrdinalIgnoreCase);
            foreach (var node in expectedNodes)
            {
                if (!_nodeSeen.TryGetValue(node, out var seen))
                    raw.Add(new Finding($"node-missing:{node}", Severity.Warning, $"No data from node “{node}”",
                        "The app has not received any telemetry from this node yet.", "Check the node is powered and on Wi-Fi, and the transport settings match."));
                else if ((now - seen).TotalSeconds > th.StaleSeconds)
                    raw.Add(new Finding($"node-stale:{node}", Severity.Critical, $"Node “{node}” went quiet",
                        $"Last packet {(now - seen).TotalSeconds:0}s ago.", "Check power / Wi-Fi on the node."));
            }

            var (q, source) = EstimateFlow(now, air);

            // Consensus check: every suction channel implies a flow (via its baseline-corrected model).
            // If the pitot disagrees with the others, trust the others.
            var implied = new Dictionary<ChannelRole, double>();
            foreach (var ch in Config.Channels)
            {
                if (ch.Role is ChannelRole.PitotVp or ChannelRole.EnclosureSuction or ChannelRole.Generic) continue;
                if (TryGet(ch, now, out var val)) implied[ch.Role] = Model.FlowFromReading(ch, val, air, Corr(Key(ch)));
            }
            bool pitotSuspect = false;
            string? mismatchNote = null;
            if (source == "pitot" && implied.Count >= 2)
            {
                double others = Median(implied.Values);
                double gap = Math.Abs(q - others) / Math.Max(Math.Max(q, others), 1e-9);
                if (gap > th.FlowMismatchFraction && Units.Cfm(Math.Max(q, others)) > 30)
                {
                    pitotSuspect = true;
                    mismatchNote = $"Pitot says {Units.Cfm(q):0} CFM but the pressure taps agree on ~{Units.Cfm(others):0} CFM.";
                    q = others;
                    source = "taps (pitot suspect)";
                }
                else if (implied.TryGetValue(ChannelRole.CycloneDp, out var qc))
                {
                    double cgap = Math.Abs(qc - q) / Math.Max(Math.Max(q, qc), 1e-9);
                    if (cgap > th.FlowMismatchFraction && Units.Cfm(Math.Max(q, qc)) > 30)
                        mismatchNote = $"Cyclone ΔP implies {Units.Cfm(qc):0} CFM while the pitot (and other taps) read {Units.Cfm(q):0} CFM.";
                }
            }
            double modelQ = Model.OperatingFlow(level, air);

            // 2. Channel health + drift
            var channelStatuses = new List<ChannelStatus>();
            var flows = new Dictionary<ChannelRole, double>();
            foreach (var ch in Config.Channels)
            {
                string key = Key(ch);
                bool have = _readings.TryGetValue(key, out var r);
                bool stale = !have || (now - r.at).TotalSeconds > th.StaleSeconds;
                double predicted = ch.Role == ChannelRole.PitotVp
                    ? Model.PredictReading(ch, q, air)
                    : Corr(key) * Model.PredictReading(ch, q, air);
                double? reading = have && r.ok && !double.IsNaN(r.value) ? r.value : null;
                double? drift = null, chFlow = null;
                if (have && !r.ok)
                    raw.Add(new Finding($"sensor-fault:{key}", Severity.Warning, $"Sensor fault: {ch.Label}",
                        "The node reports this sensor is not responding or failed its CRC.", "Check the I²C wiring / multiplexer port."));
                if (reading is { } v && !stale)
                {
                    if (Math.Abs(r.raw) >= 0.98 * ch.FullScalePa)
                        raw.Add(new Finding($"saturated:{key}", Severity.Warning, $"{ch.Label} is at full scale",
                            $"Reading {v:0} Pa is at the sensor limit (±{ch.FullScalePa:0} Pa); values above this are unknown.",
                            "Use a higher-range sensor on this tap, or check for a blockage causing unusually high suction."));
                    if (ch.Role == ChannelRole.PitotVp) chFlow = Units.Cfm(Model.FlowFromPitot(ch, Math.Max(0, v), air));
                    else if (ch.Role != ChannelRole.EnclosureSuction && ch.Role != ChannelRole.Generic)
                    {
                        chFlow = Units.Cfm(Model.FlowFromReading(ch, v, air, Corr(key)));
                        if (Math.Abs(predicted) > 2) drift = v / predicted - 1;
                    }
                    if (chFlow is { } cf) flows[ch.Role] = cf;
                }
                channelStatuses.Add(new ChannelStatus(key, string.IsNullOrEmpty(ch.Label) ? key : ch.Label, ch.Role,
                    reading, predicted, drift, chFlow, stale, have && r.ok));
            }

            // 3. Fan off?
            var fanInCh = Role(ChannelRole.FanInletSuction);
            bool fanOff = level == 0 || (TryGet(fanInCh, now, out var fanSuction) && fanSuction < th.FanOffSuctionPa && Units.Cfm(q) < 15);
            if (fanOff)
                raw.Add(new Finding("fan-off", Severity.Info, "Exhaust fan appears to be off",
                    "Almost no suction at the fan inlet.", "Turn the fan on before starting a job."));

            // 4. Segment velocities
            var segments = new List<SegmentStatus>();
            double minPre = double.PositiveInfinity;
            foreach (var e in Model.Elements)
            {
                if (e.Type is ElementType.Fan) continue;
                double v = Units.Fpm(SystemModel.DuctVelocity(e, q));
                double min = e.Zone switch
                {
                    Zone.PreSeparator => profile.MinPreSeparatorFpm,
                    Zone.PostSeparator => profile.MinPostSeparatorFpm,
                    _ => e.Cyclone?.MinInletFpm ?? 0
                };
                if (e.Type == ElementType.Cyclone && e.Cyclone is { } cc) v = Units.Fpm(q / SystemModel.CycloneInletArea(cc));
                bool isRun = e.Type == ElementType.Duct;
                if (!isRun && e.Type != ElementType.Cyclone) min = 0; // fittings/outlets: informational only
                if (e.Zone == Zone.PreSeparator && isRun) minPre = Math.Min(minPre, v);
                var sev = fanOff ? Severity.Info : v >= min ? Severity.Ok : e.Zone == Zone.PreSeparator || e.Type == ElementType.Cyclone ? Severity.Warning : Severity.Advice;
                segments.Add(new SegmentStatus(e.Id, e.Name, e.Zone, e.Type, e.DiameterIn, v, min, sev));
            }

            int? recommended = null;
            double? cycInlet = null, d50 = null, eff5 = null;

            if (!fanOff)
            {
                // Requirements expressed as a needed speed fraction (fan laws: Q ∝ speed for a fixed system).
                var needs = new List<double>();
                if (!double.IsInfinity(minPre) && minPre > 0 && s > 0)
                {
                    double vTarget = profile.MinPreSeparatorFpm * (1 + th.VelocityMargin);
                    needs.Add(s * vTarget / minPre);
                    if (minPre < profile.MinPreSeparatorFpm)
                    {
                        int? lvl = LevelForFraction(s * vTarget / minPre);
                        raw.Add(lvl is null
                            ? new Finding("fan-undersized", Severity.Critical, "Fan cannot reach safe transport velocity",
                                $"Slowest duct before the separator is at {minPre:0} fpm; {profile.MinPreSeparatorFpm:0} fpm is needed for {profile.Name}. Even level {Model.FanConfig.Levels} won't get there.",
                                "Move the cyclone right onto the laser outlet (no duct before it), reduce restrictions, or add fan pressure.")
                            : new Finding("velocity-low-pre", Severity.Warning, "Duct velocity too low before the separator",
                                $"{minPre:0} fpm vs {profile.MinPreSeparatorFpm:0} fpm minimum — heavy particles will settle in this duct.",
                                $"Raise fan to level {lvl} (currently {level})."));
                    }
                }

                var postMin = segments.Where(x => x.Zone == Zone.PostSeparator && x.Type == ElementType.Duct).Select(x => x.VelocityFpm).DefaultIfEmpty(double.PositiveInfinity).Min();
                if (postMin < profile.MinPostSeparatorFpm)
                    raw.Add(new Finding("velocity-low-post", Severity.Advice, "Slow air in the long run",
                        $"{postMin:0} fpm after the separator (target ≥ {profile.MinPostSeparatorFpm:0}). Fine residue will build up faster.",
                        "Raise the fan speed or plan periodic duct cleaning."));

                // Cyclone: separation quality (cut size ∝ 1/√v) and sane inlet speed.
                if (Config.Cyclone is { Cyclone: { } cy } && s > 0)
                {
                    double vi = Units.Fpm(q / SystemModel.CycloneInletArea(cy));
                    cycInlet = vi;
                    d50 = SystemModel.CycloneCutSize(cy, q, profile.ParticleDensity, air) * 1e6;
                    eff5 = SystemModel.CycloneEfficiency(5e-6, d50.Value * 1e-6);
                    double sCut = s * Math.Pow(d50.Value / profile.TargetCutSizeMicron, 2);
                    double sMin = s * cy.MinInletFpm / Math.Max(vi, 1);
                    double sNeed = Math.Max(sCut, sMin) * 1.02;
                    needs.Add(sNeed);
                    if (d50 > profile.TargetCutSizeMicron || vi < cy.MinInletFpm)
                    {
                        int? lvl = LevelForFraction(sNeed);
                        raw.Add(new Finding("cyclone-slow", Severity.Warning, "Cyclone too slow to separate well",
                            vi < cy.MinInletFpm
                                ? $"Inlet {vi:0} fpm is below the ~{cy.MinInletFpm:0} fpm needed for a stable vortex."
                                : $"Inlet {vi:0} fpm → estimated 50 % cut size {d50:0.0} µm (target ≤ {profile.TargetCutSizeMicron:0} µm for {profile.Name}).",
                            lvl is null ? "The fan can't get there; reduce restrictions or use a cyclone with a smaller inlet." : $"Raise fan to level {lvl}."));
                    }
                    else if (vi > cy.MaxInletFpm)
                    {
                        raw.Add(new Finding("cyclone-fast", Severity.Advice, "Cyclone running faster than needed",
                            $"Inlet velocity {vi:0} fpm (above {cy.MaxInletFpm:0}). Extra pressure is wasted and fines can re-entrain.",
                            "A lower fan level would separate just as well, if duct velocities allow."));
                    }
                }
                if (needs.Count > 0) recommended = LevelForFraction(needs.Max());

                // Flow cross-check
                if (mismatchNote is not null)
                    raw.Add(pitotSuspect
                        ? new Finding("pitot-suspect", Severity.Warning, "Pitot reading doesn't match the other sensors",
                            mismatchNote + " Using the tap consensus for now.",
                            "Blow out the pitot tip and tubing; check the probe still points straight into the airflow.")
                        : new Finding("cyclone-flow-mismatch", Severity.Warning, "Cyclone ΔP doesn't match measured flow",
                            mismatchNote, "Cyclone inlet may be partly blocked (reads high) or leaking (reads low); also check its tap holes."));

                foreach (var st in channelStatuses)
                {
                    if (st.Drift is not { } d || st.Stale) continue;
                    AddDriftFinding(raw, st, d, th);
                }

                // Long-run span: fan-inlet suction minus run-start suction.
                var runCh = Role(ChannelRole.RunStartSuction);
                if (TryGet(runCh, now, out var runS) && TryGet(fanInCh, now, out var fanS))
                {
                    double measured = fanS - runS;
                    double predicted = Corr("span:run") * (Model.PredictReading(fanInCh!, q, air) - Model.PredictReading(runCh!, q, air));
                    if (predicted > 3)
                    {
                        double d = measured / predicted - 1;
                        channelStatuses.Add(new ChannelStatus("span:run", "Long run ΔP (fan inlet − run start)", ChannelRole.Generic,
                            measured, predicted, d, null, false, true));
                        if (d >= th.DriftCriticalFraction)
                            raw.Add(new Finding("run-clogged", Severity.Critical, "Long duct run heavily restricted",
                                $"Run pressure drop is {d:P0} above normal for this flow.", "Look for a crushed/kinked section, a sagging low spot full of debris, or heavy residue build-up."));
                        else if (d >= th.DriftWarnFraction)
                            raw.Add(new Finding("run-restricted", Severity.Warning, "Long duct run restriction rising",
                                $"Run pressure drop is {d:P0} above normal for this flow.", "Schedule a duct inspection/cleaning; check for new kinks or sags."));
                        else if (d <= -th.DriftWarnFraction)
                            raw.Add(new Finding("run-leak", Severity.Warning, "Long duct run losing suction",
                                $"Run pressure drop is {-d:P0} below normal — air is probably entering through a leak.", "Check clamps and joints between the run start and the fan."));
                    }
                }

                // Outlet side: is the fan moving what it should at this suction?
                if (fanInCh is not null && TryGet(fanInCh, now, out var fis) && s > 0)
                {
                    double downstream = 0;
                    int fi = Config.Elements.FindIndex(e => e.Type == ElementType.Fan);
                    for (int i = fi + 1; i < Config.Elements.Count; i++) downstream += Model.ElementLoss(Config.Elements[i], q, air);
                    double qFan = Model.FanFlowAtPressure(fis + downstream, s, air) * Corr("fan");
                    if (qFan > Units.FromCfm(30) && q < (1 - th.FlowMismatchFraction) * qFan && Baseline is not null)
                        raw.Add(new Finding("fan-underperforming", Severity.Warning, "Less flow than the fan should be moving",
                            $"At {fis:0} Pa inlet suction the fan should move ~{Units.Cfm(qFan):0} CFM; measured {Units.Cfm(q):0} CFM.",
                            "Check the outside vent/back-draft damper and screen, the fan impeller for build-up, or a leak between the pitot and the fan."));
                }

                // Enclosure capture
                var encCh = Role(ChannelRole.EnclosureSuction);
                if (TryGet(encCh, now, out var enc) && enc < profile.MinEnclosureSuctionPa)
                    raw.Add(new Finding("enclosure-capture", Severity.Warning, "Laser enclosure not under enough suction",
                        $"{enc:0.0} Pa (need ≥ {profile.MinEnclosureSuctionPa:0.0} Pa) — fumes may escape into the room.",
                        "Close the lid, check the outlet connection, or raise fan speed."));
            }

            // Persistence filter: only report conditions that have held for PersistSeconds.
            var active = new HashSet<string>(raw.Select(f => f.Code));
            foreach (var k in _pending.Keys.Where(k => !active.Contains(k)).ToList()) _pending.Remove(k);
            var findings = new List<Finding>();
            foreach (var f in raw)
            {
                if (!_pending.TryGetValue(f.Code, out var first)) _pending[f.Code] = first = now;
                if (f.Severity == Severity.Critical && f.Code.StartsWith("node-") || (now - first).TotalSeconds >= th.PersistSeconds)
                    findings.Add(f);
            }

            return new DiagnosticSnapshot
            {
                Time = now,
                Air = air,
                FlowCfm = Units.Cfm(q),
                FlowSource = source,
                FanLevel = level,
                RecommendedLevel = recommended,
                ModelFlowCfm = Units.Cfm(modelQ),
                CycloneInletFpm = cycInlet,
                CycloneDpPa = TryGet(Role(ChannelRole.CycloneDp), now, out var cd) ? cd : null,
                CutSizeMicron = d50,
                Efficiency5Micron = eff5,
                MinPreSeparatorFpm = double.IsInfinity(minPre) ? null : minPre,
                Segments = segments,
                Channels = channelStatuses,
                Findings = findings.OrderByDescending(f => f.Severity).ToList(),
                BaselineCaptured = Baseline is not null
            };
        }
    }

    private static void AddDriftFinding(List<Finding> list, ChannelStatus st, double d, Thresholds th)
    {
        switch (st.Role)
        {
            case ChannelRole.CycloneDp when d >= th.DriftWarnFraction:
                list.Add(new Finding("cyclone-restricted", d >= th.DriftCriticalFraction ? Severity.Critical : Severity.Warning,
                    "Cyclone pressure drop above normal", $"{d:P0} higher than baseline for this flow.",
                    "Inspect the cyclone inlet and outlet tube for build-up; make sure the bin isn't over-full."));
                break;
            case ChannelRole.CycloneDp when d <= -th.DriftWarnFraction:
                list.Add(new Finding("cyclone-bypass", Severity.Warning, "Cyclone pressure drop below normal",
                    $"{-d:P0} lower than baseline for this flow.", "Check for leaks at the cyclone body, clamps and bin — or a clogged ΔP tap."));
                break;
            case ChannelRole.BinSuction when d <= -th.BinLeakDropFraction:
                list.Add(new Finding("bin-leak", Severity.Warning, "Dust bin appears to be leaking",
                    $"Bin suction is {-d:P0} below normal. Even a small bin leak stops a cyclone from separating.",
                    "Reseat the lid, check the gasket and any hose into the bin."));
                break;
            case ChannelRole.FanInletSuction when d >= th.DriftWarnFraction:
                list.Add(new Finding("fan-suction-high", Severity.Advice, "Fan inlet suction higher than normal for this flow",
                    $"{d:P0} above baseline — something upstream is adding restriction.", "See the cyclone/run findings to locate it."));
                break;
        }
    }

    private static double Median(IEnumerable<double> values)
    {
        var v = values.OrderBy(x => x).ToArray();
        return v.Length == 0 ? double.NaN : v.Length % 2 == 1 ? v[v.Length / 2] : 0.5 * (v[v.Length / 2 - 1] + v[v.Length / 2]);
    }

    /// <summary>Smallest fan level delivering at least <paramref name="fraction"/> of full speed.</summary>
    public int? LevelForFraction(double fraction, bool roundDown = false)
    {
        int levels = Model.FanConfig.Levels;
        if (roundDown)
        {
            for (int l = levels; l >= 1; l--) if (Model.SpeedFraction(l) <= fraction) return l;
            return 1;
        }
        for (int l = 1; l <= levels; l++) if (Model.SpeedFraction(l) >= fraction - 1e-9) return l;
        return null;
    }

    /// <summary>Record the current (known clean) state as the reference for drift detection.</summary>
    public Baseline CaptureBaseline()
    {
        lock (_gate)
        {
            var now = Clock();
            var air = CurrentAir();
            var (q, _) = EstimateFlow(now, air);
            if (Units.Cfm(q) < 30) throw new InvalidOperationException("Flow is too low to capture a baseline — run the fan at your normal speed first.");
            var b = new Baseline { CapturedAt = now, FlowCfm = Units.Cfm(q), FanLevel = CurrentFanLevel };
            foreach (var ch in Config.Channels.Where(c => c.Role is not ChannelRole.PitotVp and not ChannelRole.Generic))
            {
                if (!TryGet(ch, now, out var v)) continue;
                double p = Model.PredictReading(ch, q, air);
                if (Math.Abs(p) > 1e-6) b.Corrections[Key(ch)] = v / p;
            }
            var runCh = Role(ChannelRole.RunStartSuction);
            var fanCh = Role(ChannelRole.FanInletSuction);
            if (TryGet(runCh, now, out var rs) && TryGet(fanCh, now, out var fs))
            {
                double p = Model.PredictReading(fanCh!, q, air) - Model.PredictReading(runCh!, q, air);
                if (p > 1) b.Corrections["span:run"] = (fs - rs) / p;
            }
            if (TryGet(fanCh, now, out var fis))
            {
                double s = Model.SpeedFraction(CurrentFanLevel);
                double downstream = 0;
                int fi = Config.Elements.FindIndex(e => e.Type == ElementType.Fan);
                for (int i = fi + 1; i < Config.Elements.Count; i++) downstream += Model.ElementLoss(Config.Elements[i], q, air);
                double qFan = Model.FanFlowAtPressure(fis + downstream, s, air);
                if (qFan > 0) b.Corrections["fan"] = q / qFan;
            }
            Baseline = b;
            _pending.Clear();
            return b;
        }
    }
}
