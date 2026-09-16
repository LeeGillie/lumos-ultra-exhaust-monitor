using System.Globalization;
using LumosAir.Core.Config;
using LumosAir.Core.Diagnostics;
using LumosAir.Core.Model;
using LumosAir.Core.Telemetry;

CultureInfo.DefaultThreadCurrentCulture = CultureInfo.InvariantCulture;
CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;

string cmd = args.Length > 0 ? args[0].ToLowerInvariant() : "help";
string? Opt(string name) { int i = Array.IndexOf(args, name); return i >= 0 && i + 1 < args.Length ? args[i + 1] : null; }

SystemConfig LoadConfig()
{
    var path = Opt("--config");
    if (path is not null) return SystemConfig.Load(path);
    return (Opt("--option") ?? "A").ToUpperInvariant() == "B" ? DefaultSystems.OptionB() : DefaultSystems.OptionA();
}

void ApplyOverrides(SystemConfig cfg)
{
    if (Opt("--cyc-k") is { } k && cfg.Cyclone?.Cyclone is { } c1) c1.K = double.Parse(k);
    if (Opt("--cyc-inlet") is { } d && cfg.Cyclone?.Cyclone is { } c2) { c2.InletWidthIn = c2.InletHeightIn = double.Parse(d); }
    if (Opt("--flex") is { } f) foreach (var e in cfg.Elements.Where(e => e.Flex)) e.FlexFactor = double.Parse(f);
    if (Opt("--profile") is { } p) cfg.ActiveProfileId = p;
    if (Opt("--series") is { } n && cfg.Fan?.Fan is { } fan) fan.CurvePa = fan.CurvePa.Select(p => p * int.Parse(n)).ToArray();
    if (args.Contains("--no-cyclone")) cfg.Elements.RemoveAll(e => e.Type == ElementType.Cyclone);
}

switch (cmd)
{
    case "init":
    {
        var cfg = LoadConfig();
        var outPath = Opt("--out") ?? "system.json";
        cfg.Save(outPath);
        Console.WriteLine($"Wrote {outPath} ({cfg.Name})");
        break;
    }
    case "model":
    {
        var cfg = LoadConfig();
        ApplyOverrides(cfg);
        var m = new SystemModel(cfg);
        var air = new AirState(cfg.Air.TemperatureC, cfg.Air.RelativeHumidity, cfg.Air.PressurePa);
        Console.WriteLine($"{cfg.Name}   air density {air.Density:0.000} kg/m³");
        var cyc = cfg.Cyclone?.Cyclone;
        if (cyc is not null) Console.WriteLine($"Cyclone: {cyc.InletWidthIn}\" {(cyc.RoundInlet ? "round" : "rect")} inlet, K={cyc.K}");
        Console.WriteLine();
        Console.WriteLine("Lvl   CFM  3\"out fpm  cycIn fpm  4\" fpm  6\" fpm  cycΔP Pa  totalΔP Pa  d50 brass µm  d50 wood µm");
        for (int lvl = 1; lvl <= m.FanConfig.Levels; lvl++)
        {
            double q = m.OperatingFlow(lvl, air);
            double cycDp = cfg.Cyclone is { } ce ? m.ElementLoss(ce, q, air) : 0;
            string d50b = cyc is null ? "-" : (SystemModel.CycloneCutSize(cyc, q, 8500, air) * 1e6).ToString("0.0");
            string d50w = cyc is null ? "-" : (SystemModel.CycloneCutSize(cyc, q, 1000, air) * 1e6).ToString("0.0");
            string cin = cyc is null ? "-" : Units.Fpm(q / SystemModel.CycloneInletArea(cyc)).ToString("0");
            Console.WriteLine($"{lvl,3} {Units.Cfm(q),5:0} {Units.Fpm(q / Units.CircleArea(Units.FromInches(3))),10:0} {cin,10} {Units.Fpm(q / Units.CircleArea(Units.FromInches(4))),7:0} {Units.Fpm(q / Units.CircleArea(Units.FromInches(6))),7:0} {cycDp,9:0} {m.TotalLoss(q, air),11:0} {d50b,13} {d50w,12}");
        }
        if (Opt("--need-cfm") is { } need)
        {
            double qn = Units.FromCfm(double.Parse(need, CultureInfo.InvariantCulture));
            double sys = m.TotalLoss(qn, air), fan = m.FanPressure(qn, 1.0, air);
            Console.WriteLine();
            Console.WriteLine($"To move {need} CFM the system needs {sys:0} Pa ({Units.InWc(sys):0.00} inWC); the fan gives {fan:0} Pa at full speed at that flow → {(fan >= sys ? "OK" : "NOT ENOUGH")}.");
            if (cfg.Cyclone is { } ce2) Console.WriteLine($"  of which cyclone: {m.ElementLoss(ce2, qn, air):0} Pa ({Units.InWc(m.ElementLoss(ce2, qn, air)):0.00} inWC)");
        }
        double qMax = m.OperatingFlow(m.FanConfig.Levels, air);
        Console.WriteLine();
        Console.WriteLine($"Loss breakdown at level {m.FanConfig.Levels} ({Units.Cfm(qMax):0} CFM):");
        foreach (var e in cfg.Elements)
            Console.WriteLine($"  {e.Name,-38} {m.ElementLoss(e, qMax, air),7:0.0} Pa  ({Units.InWc(m.ElementLoss(e, qMax, air)):0.00} inWC)");
        Console.WriteLine();
        Console.WriteLine($"Predicted sensor readings at level {m.FanConfig.Levels}:");
        foreach (var ch in cfg.Channels)
        {
            try { Console.WriteLine($"  {ch.Node}/{ch.Channel,-8} {ch.Label,-26} {m.PredictReading(ch, qMax, air),8:0.0} Pa"); }
            catch (ArgumentException ex) { Console.WriteLine($"  {ch.Node}/{ch.Channel,-8} (n/a: {ex.Message})"); }
        }
        break;
    }
    case "simulate":
    {
        var cfg = LoadConfig();
        ApplyOverrides(cfg);
        var sim = new SimulatedTelemetrySource(cfg) { FanLevel = int.Parse(Opt("--level") ?? "10") };
        var t0 = DateTimeOffset.UtcNow;
        var engine = new DiagnosticsEngine(cfg);
        var clock = t0;
        engine.Clock = () => clock;
        void Run(int seconds)
        {
            for (int i = 0; i < seconds * 4; i++)
            {
                clock = clock.AddMilliseconds(250);
                foreach (var f in sim.Generate(clock)) engine.Ingest(f);
                engine.Evaluate(); // keeps persistence timers running, as the UI timer would
            }
        }
        Run(5);
        engine.CaptureBaseline();
        Console.WriteLine($"Baseline captured at {engine.Baseline!.FlowCfm:0} CFM");
        string fault = Opt("--fault") ?? "none";
        double amount = double.Parse(Opt("--amount") ?? "0", CultureInfo.InvariantCulture);
        switch (fault)
        {
            case "clog": sim.Faults.RunResistance = amount > 0 ? amount : 2.0; break;
            case "leak": sim.Faults.RunResistance = amount > 0 ? amount : 0.4; break;
            case "binleak": sim.Faults.BinLeak = amount > 0 ? amount : 0.6; break;
            case "pitot": sim.Faults.PitotClog = amount > 0 ? amount : 0.6; break;
            case "outlet": sim.Faults.OutletBlockK = amount > 0 ? amount : 15; break;
            case "cyclone": sim.Faults.CycloneResistance = amount > 0 ? amount : 1.8; break;
            case "lid": sim.Faults.LidOpen = true; break;
            case "slow": sim.FanLevel = (int)(amount > 0 ? amount : 4); break;
            case "none": break;
            default: Console.Error.WriteLine($"Unknown fault '{fault}'"); return 2;
        }
        Run(10);
        Print(engine.Evaluate());
        break;
    }
    case "listen":
    {
        var cfg = LoadConfig();
        var engine = new DiagnosticsEngine(cfg, Baseline.TryLoad(Opt("--baseline") ?? "baseline.json"));
        if (Opt("--level") is { } lv) engine.ManualFanLevel = int.Parse(lv);
        ITelemetrySource src = Opt("--mqtt") is { } host
            ? new MqttTelemetrySource(host, int.Parse(Opt("--mqtt-port") ?? "1883"), Opt("--user"), Opt("--pass"))
            : new UdpTelemetrySource(int.Parse(Opt("--udp") ?? cfg.Transport.UdpPort.ToString()));
        src.FrameReceived += engine.Ingest;
        src.StatusChanged += s => Console.WriteLine($"[{src.Name}] {s}");
        using var cts = new CancellationTokenSource();
        Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };
        await src.StartAsync(cts.Token);
        while (!cts.IsCancellationRequested)
        {
            try { await Task.Delay(1000, cts.Token); } catch (OperationCanceledException) { break; }
            Print(engine.Evaluate());
        }
        await src.DisposeAsync();
        break;
    }
    default:
        Console.WriteLine("""
            lumosair – Lumos Ultra exhaust airflow tool

              lumosair init     [--option A|B] [--out system.json]
              lumosair model    [--option A|B | --config system.json] [--cyc-k 6] [--cyc-inlet 4] [--flex 2.5] [--series 2] [--no-cyclone] [--need-cfm 200]
              lumosair simulate [--option A|B] [--level 10] [--fault none|clog|leak|binleak|pitot|outlet|cyclone|lid|slow] [--amount x]
              lumosair listen   [--config system.json] [--udp 47810 | --mqtt host [--user u --pass p]] [--level 10]
            """);
        break;
}
return 0;

static void Print(DiagnosticSnapshot s)
{
    Console.WriteLine();
    Console.WriteLine($"{s.Time:HH:mm:ss}  {s.FlowCfm:0} CFM ({s.FlowSource})  fan L{s.FanLevel}  model {s.ModelFlowCfm:0} CFM  ρ={s.Air.Density:0.000}  status={s.Overall}");
    if (s.CycloneInletFpm is { } ci)
        Console.WriteLine($"  cyclone inlet {ci:0} fpm, d50 {s.CutSizeMicron:0.0} µm, η(5µm) {s.Efficiency5Micron:P0}; recommended level {s.RecommendedLevel?.ToString() ?? "n/a"}");
    foreach (var seg in s.Segments)
        Console.WriteLine($"  {seg.Severity,-8} {seg.Name,-38} {seg.VelocityFpm,6:0} fpm (min {seg.MinFpm:0})");
    foreach (var c in s.Channels)
        Console.WriteLine($"  {c.Label,-38} {(c.ReadingPa is { } r ? r.ToString("0.0") : "--"),7} Pa  model {c.PredictedPa,7:0.0}  drift {(c.Drift is { } d ? d.ToString("+0%;-0%;0%") : "--"),6}  {(c.FlowCfm is { } f ? f.ToString("0") + " CFM" : "")}");
    foreach (var f in s.Findings)
        Console.WriteLine($"  !! [{f.Severity}] {f.Title}: {f.Detail} → {f.Action}");
}
