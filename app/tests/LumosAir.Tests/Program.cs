using System.Globalization;
using System.Net;
using System.Net.Sockets;
using System.Text;
using LumosAir.Core.Config;
using LumosAir.Core.Control;
using LumosAir.Core.Diagnostics;
using LumosAir.Core.Model;
using LumosAir.Core.Telemetry;

CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;
int passed = 0, failed = 0;

async Task Test(string name, Func<Task> body)
{
    try { await body(); passed++; Console.WriteLine($"  PASS  {name}"); }
    catch (Exception ex) { failed++; Console.WriteLine($"  FAIL  {name}: {ex.Message}"); }
}
Task T(string name, Action body) => Test(name, () => { body(); return Task.CompletedTask; });
static void Near(double actual, double expected, double tol, string what)
{
    if (double.IsNaN(actual) || Math.Abs(actual - expected) > tol)
        throw new Exception($"{what}: expected {expected}±{tol}, got {actual}");
}
static void True(bool cond, string what) { if (!cond) throw new Exception(what); }

var std = new AirState(20, 50, 101_325);
var spokane = AirState.Default;

Console.WriteLine("Physics");
await T("unit conversions", () =>
{
    Near(Units.Cfm(Units.FromCfm(123)), 123, 1e-9, "cfm roundtrip");
    Near(Units.FromInWc(1), 249.09, 0.01, "inWC");
    Near(Units.Fpm(Units.FromFpm(4005)), 4005, 1e-9, "fpm");
});
await T("air density: sea level ≈1.20, Spokane ≈1.12", () =>
{
    Near(std.Density, 1.199, 0.005, "sea level");
    Near(spokane.Density, 1.120, 0.01, "Spokane");
});
await T("velocity pressure matches VP = (V/4005)² inWC at standard air", () =>
{
    var air = new AirState(21, 0, 101_325); // ≈0.075 lb/ft³
    double vp = Units.InWc(air.VelocityPressure(Units.FromFpm(4005)));
    Near(vp, 1.0, 0.01, "VP at 4005 fpm");
});
await T("friction factor: smooth pipe Re=1e5 ≈ 0.018", () => Near(SystemModel.FrictionFactor(1e5, 0), 0.018, 0.0005, "f"));
await T("6\" galvanized @ 200 CFM ≈ 0.3 inWC/100 ft (duct chart)", () =>
{
    var cfg = new SystemConfig { Elements = { new ElementConfig { Id = "d", Type = ElementType.Duct, DiameterIn = 6, LengthFt = 100, RoughnessMm = 0.09 } } };
    var m = new SystemModel(cfg);
    double loss = Units.InWc(m.ElementLoss(cfg.Elements[0], Units.FromCfm(200), new AirState(21, 0, 101_325)));
    Near(loss, 0.30, 0.05, "loss per 100 ft");
});
await T("Lapple cut size hand calc (brass, 2.5\" wide inlet, 1270 fpm) ≈ 2.45 µm", () =>
{
    var c = new CycloneConfig { RoundInlet = false, InletWidthIn = 2.5, InletHeightIn = 1, Turns = 5 };
    var air = new AirState(20, 0, 101_325);
    double area = SystemModel.CycloneInletArea(c);
    double q = Units.FromFpm(1270) * area;
    // Hand calc used μ = 1.81e-5 and ignored gas density — allow 3 %.
    Near(SystemModel.CycloneCutSize(c, q, 8500, air) * 1e6, 2.45, 0.08, "d50");
    Near(SystemModel.CycloneEfficiency(2.45e-6, 2.45e-6), 0.5, 1e-9, "η at d50");
});
await T("operating point: fan pressure equals system loss", () =>
{
    var m = new SystemModel(DefaultSystems.OptionA());
    foreach (int lvl in new[] { 3, 7, 10 })
    {
        double q = m.OperatingFlow(lvl, spokane);
        Near(m.FanPressure(q, m.SpeedFraction(lvl), spokane), m.TotalLoss(q, spokane), 0.5, $"balance L{lvl}");
    }
    True(m.OperatingFlow(10, spokane) > m.OperatingFlow(5, spokane), "flow rises with level");
});
await T("fan laws: flow ≈ proportional to level for a quadratic system", () =>
{
    var m = new SystemModel(DefaultSystems.OptionA());
    double r = m.OperatingFlow(5, spokane) / m.OperatingFlow(10, spokane);
    Near(r, 0.5, 0.03, "Q5/Q10");
});
await T("channel inversion: FlowFromReading(PredictReading(q)) == q", () =>
{
    var cfg = DefaultSystems.OptionA();
    var m = new SystemModel(cfg);
    double q = Units.FromCfm(117);
    foreach (var ch in cfg.Channels.Where(c => c.Role is not ChannelRole.PitotVp and not ChannelRole.EnclosureSuction))
        Near(Units.Cfm(m.FlowFromReading(ch, m.PredictReading(ch, q, spokane), spokane)), 117, 0.2, ch.Channel);
    var pitot = cfg.Channels.First(c => c.Role == ChannelRole.PitotVp);
    Near(Units.Cfm(m.FlowFromPitot(pitot, m.PredictReading(pitot, q, spokane), spokane)), 117, 0.01, "pitot");
});
await T("tap signs: suction positive, cyclone ΔP positive, bin between inlet and outlet", () =>
{
    var cfg = DefaultSystems.OptionA();
    var m = new SystemModel(cfg);
    double q = Units.FromCfm(140);
    foreach (var ch in cfg.Channels) True(m.PredictReading(ch, q, spokane) > 0, $"{ch.Channel} should be > 0");
    double inlet = -m.TapStatic("before:cyclone", q, spokane), bin = -m.TapStatic("bin:cyclone", q, spokane), outlet = -m.TapStatic("after:cyclone", q, spokane);
    True(inlet < bin && bin < outlet, "bin suction between inlet and outlet");
    True(m.TapStatic("after:exit", q, spokane) < 0.01, "downstream end ≈ atmosphere");
});

Console.WriteLine("Config & telemetry");
await T("config JSON round-trip", () =>
{
    var path = Path.Combine(Path.GetTempPath(), $"lumosair-{Guid.NewGuid():N}.json");
    DefaultSystems.OptionB().Save(path);
    var back = SystemConfig.Load(path);
    File.Delete(path);
    True(back.Elements.Count == DefaultSystems.OptionB().Elements.Count, "element count");
    True(back.Cyclone?.Cyclone?.K == 6, "cyclone K");
    True(back.Channels.Any(c => c.Role == ChannelRole.PitotVp && c.PitotElementId == "duct6"), "pitot channel");
    True(back.Fan?.Fan?.CurvePa.Length == 7, "fan curve");
});
await T("telemetry parse: full frame", () =>
{
    var json = """{"node":"laser","seq":7,"up":1234,"ch":{"cyc_dp":{"pa":212.5,"t":24.1,"ok":true},"bin":{"ok":false}},"env":{"t":22.5,"rh":35,"p":94500},"fan":{"level":6,"rpm":1500}}""";
    True(TelemetryFrame.TryParse(Encoding.UTF8.GetBytes(json), out var f) && f is not null, "parsed");
    True(f!.Node == "laser" && f.Seq == 7 && f.UptimeMs == 1234, "header");
    Near(f.Channels["cyc_dp"].Pa, 212.5, 1e-9, "pa");
    True(!f.Channels["bin"].Ok, "bin not ok");
    True(f.Env?.PressurePa == 94500 && f.FanLevel == 6 && f.FanRpm == 1500, "env/fan");
});
await T("telemetry parse: garbage rejected", () =>
{
    True(!TelemetryFrame.TryParse("not json"u8, out _), "garbage");
    True(!TelemetryFrame.TryParse("""{"seq":1}"""u8, out _), "no node");
});
await T("MQTT remaining-length encoding", () =>
{
    True(MqttTelemetrySource.Frame(0x30, new List<byte>(new byte[127]))[1] == 127, "127");
    var f = MqttTelemetrySource.Frame(0x30, new List<byte>(new byte[321]));
    True(f[1] == 0xC1 && f[2] == 0x02, "321 → C1 02");
});
await Test("UDP loopback delivers frames and commands", async () =>
{
    int port = FreeUdpPort();
    int cmdPort = FreeUdpPort();
    await using var src = new UdpTelemetrySource(port, cmdPort);
    var got = new TaskCompletionSource<TelemetryFrame>();
    src.FrameReceived += f => got.TrySetResult(f);
    await src.StartAsync(CancellationToken.None);
    using var node = new UdpClient(new IPEndPoint(IPAddress.Loopback, cmdPort));
    await node.SendAsync(Encoding.UTF8.GetBytes("""{"node":"laser","ch":{"pitot":{"pa":40}}}"""), new IPEndPoint(IPAddress.Loopback, port));
    var frame = await got.Task.WaitAsync(TimeSpan.FromSeconds(3));
    Near(frame.Channels["pitot"].Pa, 40, 1e-9, "pitot pa");
    await src.SendCommandAsync("laser", """{"cmd":"zero"}""", CancellationToken.None);
    var cmd = await node.ReceiveAsync().WaitAsync(TimeSpan.FromSeconds(3));
    True(Encoding.UTF8.GetString(cmd.Buffer).Contains("zero"), "command received by node");
});
await Test("MQTT client against a fake broker", async () =>
{
    var listener = new TcpListener(IPAddress.Loopback, 0);
    listener.Start();
    int port = ((IPEndPoint)listener.LocalEndpoint).Port;
    var broker = Task.Run(async () =>
    {
        using var client = await listener.AcceptTcpClientAsync();
        var s = client.GetStream();
        var connect = await ReadPacket(s);
        if (connect.type != 1) throw new Exception("expected CONNECT");
        await s.WriteAsync(new byte[] { 0x20, 0x02, 0x00, 0x00 });
        var sub = await ReadPacket(s);
        if (sub.type != 8) throw new Exception("expected SUBSCRIBE");
        string filter = Encoding.UTF8.GetString(sub.body, 4, (sub.body[2] << 8) | sub.body[3]);
        if (filter != "lumosair/+/telemetry") throw new Exception("filter " + filter);
        await s.WriteAsync(new byte[] { 0x90, 0x03, sub.body[0], sub.body[1], 0x00 });
        var payload = Encoding.UTF8.GetBytes("""{"node":"fan","ch":{"fan_in":{"pa":321.5}}}""");
        var body = new List<byte>();
        var topic = Encoding.UTF8.GetBytes("lumosair/fan/telemetry");
        body.Add(0); body.Add((byte)topic.Length); body.AddRange(topic);
        body.Add(0); body.Add(9); // QoS1 packet id
        body.AddRange(payload);
        await s.WriteAsync(MqttTelemetrySource.Frame(0x32, body));
        var ack = await ReadPacket(s);
        if (ack.type != 4) throw new Exception("expected PUBACK");
        var cmd = await ReadPacket(s);
        if (cmd.type != 3) throw new Exception("expected PUBLISH cmd");
        return Encoding.UTF8.GetString(cmd.body);
    });
    await using var src = new MqttTelemetrySource("127.0.0.1", port);
    var got = new TaskCompletionSource<TelemetryFrame>();
    src.FrameReceived += f => got.TrySetResult(f);
    await src.StartAsync(CancellationToken.None);
    var frame = await got.Task.WaitAsync(TimeSpan.FromSeconds(5));
    Near(frame.Channels["fan_in"].Pa, 321.5, 1e-9, "fan_in");
    await Task.Delay(100);
    await src.SendCommandAsync("fan", """{"cmd":"zero"}""", CancellationToken.None);
    var cmdText = await broker.WaitAsync(TimeSpan.FromSeconds(5));
    True(cmdText.Contains("lumosair/fan/cmd") && cmdText.Contains("zero"), "command topic/payload");
    listener.Stop();
});

Console.WriteLine("Diagnostics (simulated faults)");
foreach (var (fault, expect, forbid) in new (string, string?, string[])[]
{
    ("none", null, new[] { "run-", "bin-leak", "cyclone-", "pitot-suspect", "fan-underperforming", "enclosure-capture" }),
    ("clog", "run-clogged", new[] { "run-leak", "pitot-suspect" }),
    ("leak", "run-leak", new[] { "run-clogged" }),
    ("binleak", "bin-leak", new[] { "run-", "pitot-suspect" }),
    ("pitot", "pitot-suspect", new[] { "run-clogged", "cyclone-restricted", "fan-underperforming" }),
    ("outlet", "fan-underperforming", new[] { "run-clogged", "pitot-suspect" }),
    ("cyclone", "cyclone-restricted", new[] { "run-clogged", "run-leak", "pitot-suspect" }),
    ("lid", "enclosure-capture", new[] { "run-" }),
    ("slow", "cyclone-slow", new[] { "run-" }),
})
{
    await T($"fault '{fault}' → {expect ?? "no faults"}", () =>
    {
        var codes = RunScenario(DefaultSystems.OptionA(), fault).Findings.Select(f => f.Code).ToList();
        if (expect is not null) True(codes.Contains(expect), $"missing {expect}; got [{string.Join(", ", codes)}]");
        foreach (var bad in forbid)
            True(!codes.Any(c => c.StartsWith(bad)), $"unexpected {bad}; got [{string.Join(", ", codes)}]");
    });
}
await T("Option B detects a clog too", () =>
    True(RunScenario(DefaultSystems.OptionB(), "clog").Findings.Any(f => f.Code == "run-clogged"), "run-clogged"));
await T("5 ft of 4\" hose BEFORE the cyclone triggers the transport-velocity rule", () =>
{
    var cfg = DefaultSystems.OptionA();
    int idx = cfg.Elements.FindIndex(e => e.Type == ElementType.Cyclone);
    cfg.Elements.Insert(idx, new ElementConfig { Id = "hose4", Name = "4\" hose before cyclone", Type = ElementType.Duct, Zone = Zone.PreSeparator, DiameterIn = 4, LengthFt = 5, Flex = true });
    var snap = RunScenario(cfg, "none");
    True(snap.Findings.Any(f => f.Code is "velocity-low-pre" or "fan-undersized"), string.Join(",", snap.Findings.Select(f => f.Code)));
});
await T("Option C (today, no separator): every duct is dirty-side and too slow for brass", () =>
{
    var cfg = DefaultSystems.Current();
    True(cfg.Cyclone is null, "no cyclone element");
    True(cfg.Channels.All(c => c.Role is not (ChannelRole.CycloneDp or ChannelRole.BinSuction)), "no cyclone channels");
    var m = new SystemModel(cfg);
    double q = m.OperatingFlow(10, spokane);
    True(Units.Cfm(q) is > 150 and < 260, $"flow {Units.Cfm(q):0} CFM");
    // The 6" run cannot carry brass at any fan level -> the monitor must say so.
    var snap = RunScenario(cfg, "none");
    True(snap.Findings.Any(f => f.Code is "fan-undersized" or "velocity-low-pre"),
        string.Join(",", snap.Findings.Select(f => f.Code)));
});
await T("Option C pitot still inverts to the right flow", () =>
{
    var cfg = DefaultSystems.Current();
    var m = new SystemModel(cfg);
    var pitot = cfg.Channels.First(c => c.Role == ChannelRole.PitotVp);
    True(pitot.PitotElementId == "spool4", "pitot in the rigid spool");
    double q = Units.FromCfm(180);
    Near(Units.Cfm(m.FlowFromPitot(pitot, m.PredictReading(pitot, q, spokane), spokane)), 180, 0.02, "pitot");
});
await T("recommended level restores cyclone performance after 'slow'", () =>
{
    var snap = RunScenario(DefaultSystems.OptionA(), "slow");
    True(snap.RecommendedLevel is > 4 and <= 10, $"recommended {snap.RecommendedLevel}");
    var cfg = DefaultSystems.OptionA();
    var m = new SystemModel(cfg);
    double q = m.OperatingFlow(snap.RecommendedLevel!.Value, spokane);
    True(Units.Fpm(q / SystemModel.CycloneInletArea(cfg.Cyclone!.Cyclone!)) >= cfg.Cyclone.Cyclone!.MinInletFpm, "vortex speed reached");
});
await T("stale node raises a critical finding", () =>
{
    var cfg = DefaultSystems.OptionA();
    var sim = new SimulatedTelemetrySource(cfg);
    var engine = new DiagnosticsEngine(cfg);
    var clock = DateTimeOffset.UtcNow;
    engine.Clock = () => clock;
    for (int i = 0; i < 20; i++) { clock = clock.AddMilliseconds(250); foreach (var f in sim.Generate(clock)) engine.Ingest(f); engine.Evaluate(); }
    sim.Faults.FanNodeOffline = true;
    for (int i = 0; i < 40; i++) { clock = clock.AddMilliseconds(250); foreach (var f in sim.Generate(clock)) engine.Ingest(f); engine.Evaluate(); }
    True(engine.Evaluate().Findings.Any(f => f.Code == "node-stale:fan" && f.Severity == Severity.Critical), "node-stale:fan");
});
await T("fan off is reported as info only", () =>
{
    var snap = RunScenario(DefaultSystems.OptionA(), "off");
    True(snap.Findings.Any(f => f.Code == "fan-off"), "fan-off");
    True(snap.Overall <= Severity.Info, $"overall {snap.Overall}");
});

Console.WriteLine("Fan control");
static (DiagnosticSnapshot snap, AutoFanController ctl, FanControlConfig cfg) FanFixture(
    int recommended, Severity worst = Severity.Ok, int dwell = 30)
{
    var cfg = new FanControlConfig { Enabled = true, MinLevel = 3, MaxLevel = 10, DwellSeconds = dwell, MinStepDown = 1 };
    var findings = worst == Severity.Ok
        ? new List<Finding>()
        : new List<Finding> { new("x", worst, "t", "d") };
    var snap = new DiagnosticSnapshot { RecommendedLevel = recommended, Findings = findings, FanLevel = 5 };
    return (snap, new AutoFanController(cfg), cfg);
}

await T("auto raises the fan immediately when more is needed", () =>
{
    var (snap, ctl, _) = FanFixture(8);
    var d = ctl.Evaluate(snap, 5, DateTimeOffset.UtcNow);
    True(d.TargetLevel == 8 && d.Urgent, $"{d.TargetLevel} {d.Reason}");
});
await T("auto does not step down until the dwell time has passed", () =>
{
    var (snap, ctl, cfg) = FanFixture(4);
    var t0 = DateTimeOffset.UtcNow;
    True(ctl.Evaluate(snap, 8, t0).TargetLevel is null, "should confirm first");
    True(ctl.Evaluate(snap, 8, t0.AddSeconds(cfg.DwellSeconds - 5)).TargetLevel is null, "still waiting");
    var d = ctl.Evaluate(snap, 8, t0.AddSeconds(cfg.DwellSeconds + 1));
    True(d.TargetLevel == 4 && !d.Urgent, $"{d.TargetLevel} {d.Reason}");
});
await T("a rise cancels a pending step down", () =>
{
    var (low, ctl, cfg) = FanFixture(4);
    var t0 = DateTimeOffset.UtcNow;
    ctl.Evaluate(low, 8, t0);
    var high = new DiagnosticSnapshot { RecommendedLevel = 9, Findings = Array.Empty<Finding>() };
    True(ctl.Evaluate(high, 8, t0.AddSeconds(5)).TargetLevel == 9, "should raise");
    True(ctl.Evaluate(low, 9, t0.AddSeconds(6)).TargetLevel is null, "dwell restarts");
});
await T("a critical finding pins the fan at maximum", () =>
{
    var (snap, ctl, cfg) = FanFixture(4, Severity.Critical);
    var d = ctl.Evaluate(snap, 5, DateTimeOffset.UtcNow);
    True(d.TargetLevel == cfg.MaxLevel && d.Urgent, $"{d.TargetLevel} {d.Reason}");
});
await T("auto respects the configured level limits", () =>
{
    var cfg = new FanControlConfig { Enabled = true, MinLevel = 4, MaxLevel = 7 };
    var ctl = new AutoFanController(cfg);
    var snap = new DiagnosticSnapshot { RecommendedLevel = 10, Findings = Array.Empty<Finding>() };
    True(ctl.Evaluate(snap, 5, DateTimeOffset.UtcNow).TargetLevel == 7, "clamped to MaxLevel");
});
await T("automatic control can be switched off entirely", () =>
{
    var ctl = new AutoFanController(new FanControlConfig { Enabled = false });
    var snap = new DiagnosticSnapshot { RecommendedLevel = 9, Findings = Array.Empty<Finding>() };
    True(ctl.Evaluate(snap, 3, DateTimeOffset.UtcNow).TargetLevel is null, "no command when disabled");
});
await T("the same level is not re-sent every tick", () =>
{
    var (snap, ctl, _) = FanFixture(8);
    var t0 = DateTimeOffset.UtcNow;
    True(ctl.Evaluate(snap, 5, t0).TargetLevel == 8, "first send");
    True(ctl.Evaluate(snap, 5, t0.AddSeconds(1)).TargetLevel is null, "no repeat");
});
await T("status payload carries what the box displays need", () =>
{
    var cfg = DefaultSystems.OptionA();
    var snap = RunScenario(cfg, "clog");
    string json = StatusPayload.Build(snap, FanMode.Auto, 7, "auto: holding");
    using var doc = System.Text.Json.JsonDocument.Parse(json);
    var root = doc.RootElement;
    True(root.GetProperty("t").GetString() == "status", "type");
    True(root.GetProperty("cfm").GetDouble() > 50, "cfm");
    True(root.GetProperty("sev").GetString() == "critical", root.GetProperty("sev").GetString()!);
    True(root.GetProperty("fan").GetProperty("level").GetInt32() == 7, "level");
    True(root.GetProperty("fan").GetProperty("mode").GetString() == "auto", "mode");
    True(root.GetProperty("msg").GetString()!.Length is > 0 and <= 38, "headline fits the screen");
    True(json.Length < 300, $"payload {json.Length} bytes fits one datagram");
});
await T("a tap that cannot be inverted does not poison the flow estimate", () =>
{
    // FlowFromReading hands back NaN for "this tap cannot tell us". That must not
    // become the system flow: everything downstream (segment velocities, cyclone cut
    // size, the status broadcast) is derived from it.
    var cfg = DefaultSystems.OptionA();
    var engine = new DiagnosticsEngine(cfg);
    var now = DateTimeOffset.UtcNow;
    engine.Clock = () => now;
    engine.ManualFanLevel = 7;
    // No channel readings at all: it should fall through to the model, not NaN.
    var snap = engine.Evaluate();
    True(double.IsFinite(snap.FlowCfm), $"flow is a real number, got {snap.FlowCfm}");
    True(snap.FlowCfm > 0, $"and a positive one, got {snap.FlowCfm}");
    string json = StatusPayload.Build(snap, FanMode.Manual, 7);
    True(!json.Contains("NaN") && !json.Contains("Infinity"), json);
});
await T("the node simulator's frames read as a healthy system", () =>
{
    // These are the exact datagrams tools/simulate_node.py puts on the wire at fan
    // level 10, for Option A and Option C. They are generated from the app's own
    // PredictReading table, so they describe a real operating point; earlier the
    // simulator invented plausible-looking constants with the suction channels
    // negative, and the app - correctly - concluded every tap implied zero flow and
    // announced that the exhaust fan was off.
    var cases = new (string Opt, string Laser, string Fan)[]
    {
        ("A", "{\"node\": \"laser\", \"seq\": 5, \"up\": 5000, \"rssi\": -61, \"ch\": {\"bin\": {\"pa\": 268.78, \"t\": 24.0, \"ok\": true}, \"cyc_dp\": {\"pa\": 229.65, \"t\": 24.0, \"ok\": true}, \"encl\": {\"pa\": 18.9, \"t\": 24.0, \"ok\": true}, \"pitot\": {\"pa\": 47.26, \"t\": 24.0, \"ok\": true}, \"run_in\": {\"pa\": 376.09, \"t\": 24.0, \"ok\": true}}, \"env\": {\"t\": 23.9, \"rh\": 41.0, \"p\": 94412}}",
              "{\"node\": \"fan\", \"seq\": 5, \"up\": 5000, \"rssi\": -61, \"ch\": {\"fan_in\": {\"pa\": 418.91, \"t\": 24.0, \"ok\": true}}, \"env\": {\"t\": 23.9, \"rh\": 41.0, \"p\": 94412}, \"fan\": {\"level\": 10}}"),
        ("C", "{\"node\": \"laser\", \"seq\": 5, \"up\": 5000, \"rssi\": -61, \"ch\": {\"encl\": {\"pa\": 38.05, \"t\": 24.0, \"ok\": true}, \"pitot\": {\"pa\": 95.13, \"t\": 24.0, \"ok\": true}, \"run_in\": {\"pa\": 293.57, \"t\": 24.0, \"ok\": true}}, \"env\": {\"t\": 23.9, \"rh\": 41.0, \"p\": 94412}}",
              "{\"node\": \"fan\", \"seq\": 5, \"up\": 5000, \"rssi\": -61, \"ch\": {\"fan_in\": {\"pa\": 376.53, \"t\": 24.0, \"ok\": true}}, \"env\": {\"t\": 23.9, \"rh\": 41.0, \"p\": 94412}, \"fan\": {\"level\": 10}}"),
    };
    foreach (var (opt, laser, fan) in cases)
    {
        var cfg = opt == "A" ? DefaultSystems.OptionA() : DefaultSystems.Current();
        var eng = new DiagnosticsEngine(cfg) { ManualFanLevel = 10 };
        var now = DateTimeOffset.UtcNow;
        eng.Clock = () => now;
        TelemetryFrame.TryParse(System.Text.Encoding.UTF8.GetBytes(laser), out var lf, now);
        TelemetryFrame.TryParse(System.Text.Encoding.UTF8.GetBytes(fan), out var ff, now);
        eng.Ingest(lf!); eng.Ingest(ff!);
        var snap = eng.Evaluate();
        True(double.IsFinite(snap.FlowCfm) && snap.FlowCfm > 100,
             $"Option {opt}: expected a real flow, got {snap.FlowCfm:0.0} from {snap.FlowSource}");
        True(snap.FanLevel == 10, $"Option {opt}: fan level reported as {snap.FanLevel}");
        True(!snap.Findings.Any(f => f.Code == "fan-off"),
             $"Option {opt}: reported the fan off at level 10");
        True(!snap.Findings.Any(f => f.Severity == Severity.Critical),
             $"Option {opt}: " + string.Join(", ", snap.Findings.Select(f => f.Code)));
    }
});
await T("status payload survives the values the model legitimately produces", () =>
{
    // CycloneCutSize returns +infinity on purpose when the inlet velocity is zero,
    // and a flow solved from inconsistent readings can be NaN. Both used to reach
    // JsonSerializer, which throws on them - from an async void timer handler, so
    // the app opened one modal dialog per tick until the desktop was full.
    var snap = new DiagnosticSnapshot
    {
        FlowCfm = double.NaN,
        FlowSource = "pitot",
        CutSizeMicron = double.PositiveInfinity,
        CycloneInletFpm = double.NegativeInfinity,
        Findings = Array.Empty<Finding>(),
    };
    string json = StatusPayload.Build(snap, FanMode.Auto, 7, "auto: holding");
    using var doc = System.Text.Json.JsonDocument.Parse(json);
    var root = doc.RootElement;
    True(root.GetProperty("cfm").ValueKind == System.Text.Json.JsonValueKind.Null,
         "a non-finite cfm is sent as null, which the box renders as ---");
    True(!root.TryGetProperty("d50", out _), "an infinite cut size is left out");
    True(!root.TryGetProperty("cyc_fpm", out _), "an infinite inlet velocity is left out");
    True(!json.Contains("Infinity") && !json.Contains("NaN"),
         "nothing the nodes' json module would choke on: " + json);
});
await Test("auto mode drives the simulated fan back up after a drop", async () =>
{
    var cfg = DefaultSystems.OptionA();
    cfg.FanControl.DwellSeconds = 1;
    var sim = new SimulatedTelemetrySource(cfg) { FanLevel = 3 };
    var engine = new DiagnosticsEngine(cfg);
    var ctl = new AutoFanController(cfg.FanControl);
    var clock = DateTimeOffset.UtcNow;
    engine.Clock = () => clock;
    int level = 3;
    for (int i = 0; i < 120; i++)
    {
        clock = clock.AddMilliseconds(250);
        sim.FanLevel = level;
        foreach (var f in sim.Generate(clock)) engine.Ingest(f);
        var snap = engine.Evaluate();
        var d = ctl.Evaluate(snap, level, clock);
        if (d.TargetLevel is { } t)
        {
            await sim.SendCommandAsync("fan", $"{{\"cmd\":\"set_level\",\"level\":{t}}}", CancellationToken.None);
            level = sim.FanLevel;
        }
    }
    True(level >= 7, $"auto should have raised the fan, ended at {level}");
    True(sim.Commands.Any(c => c.Json.Contains("set_level")), "a set_level command was sent");
});

Console.WriteLine();
Console.WriteLine($"{passed} passed, {failed} failed");
return failed == 0 ? 0 : 1;

static DiagnosticSnapshot RunScenario(SystemConfig cfg, string fault)
{
    var sim = new SimulatedTelemetrySource(cfg) { FanLevel = 10 };
    var engine = new DiagnosticsEngine(cfg);
    var clock = DateTimeOffset.UtcNow;
    engine.Clock = () => clock;
    void Run(int seconds)
    {
        for (int i = 0; i < seconds * 4; i++)
        {
            clock = clock.AddMilliseconds(250);
            foreach (var f in sim.Generate(clock)) engine.Ingest(f);
            engine.Evaluate();
        }
    }
    Run(5);
    engine.CaptureBaseline();
    switch (fault)
    {
        case "clog": sim.Faults.RunResistance = 2.0; break;
        case "leak": sim.Faults.RunResistance = 0.4; break;
        case "binleak": sim.Faults.BinLeak = 0.6; break;
        case "pitot": sim.Faults.PitotClog = 0.6; break;
        case "outlet": sim.Faults.OutletBlockK = 15; break;
        case "cyclone": sim.Faults.CycloneResistance = 1.8; break;
        case "lid": sim.Faults.LidOpen = true; break;
        case "slow": sim.FanLevel = 4; break;
        case "off": sim.FanLevel = 0; engine.ManualFanLevel = 0; break;
    }
    Run(10);
    return engine.Evaluate();
}

static int FreeUdpPort()
{
    using var u = new UdpClient(new IPEndPoint(IPAddress.Loopback, 0));
    return ((IPEndPoint)u.Client.LocalEndPoint!).Port;
}

static async Task<(int type, byte[] body)> ReadPacket(NetworkStream s)
{
    var h = new byte[1];
    await s.ReadExactlyAsync(h);
    int len = 0, mul = 1;
    var b = new byte[1];
    do { await s.ReadExactlyAsync(b); len += (b[0] & 0x7F) * mul; mul *= 128; } while ((b[0] & 0x80) != 0);
    var body = new byte[len];
    await s.ReadExactlyAsync(body);
    return (h[0] >> 4, body);
}
