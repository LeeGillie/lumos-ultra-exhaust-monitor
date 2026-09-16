using System.Globalization;
using System.Net;
using System.Net.Sockets;
using System.Text;
using LumosAir.Core.Config;
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
