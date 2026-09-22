using System.Text.Json;
using LumosAir.Core.Config;
using LumosAir.Core.Model;

namespace LumosAir.Core.Telemetry;

/// <summary>Fault knobs for the simulator. 1.0 / 0.0 = healthy.</summary>
public sealed class SimulationFaults
{
    /// <summary>Multiplier on the long run's resistance (&gt;1 clog/kink, &lt;1 leak).</summary>
    public double RunResistance { get; set; } = 1.0;
    /// <summary>Multiplier on cyclone K (&gt;1 build-up).</summary>
    public double CycloneResistance { get; set; } = 1.0;
    /// <summary>0..1 — fraction of bin suction lost to a lid leak.</summary>
    public double BinLeak { get; set; }
    /// <summary>0..1 — fraction of pitot signal lost to a clogged tip.</summary>
    public double PitotClog { get; set; }
    /// <summary>Extra velocity heads at the outlet (stuck damper, clogged screen).</summary>
    public double OutletBlockK { get; set; }
    /// <summary>Lid open: reduces enclosure resistance.</summary>
    public bool LidOpen { get; set; }
    public double NoisePa { get; set; } = 0.4;
    public bool FanNodeOffline { get; set; }
}

/// <summary>Generates realistic telemetry from the physics model so the app can be exercised without hardware.</summary>
public sealed class SimulatedTelemetrySource : ITelemetrySource
{
    private readonly SystemConfig _config;
    private readonly Random _rng = new(42);
    private CancellationTokenSource? _cts;
    private Task? _loop;
    private long _seq;
    private readonly Dictionary<string, double> _zero = new();

    public SimulationFaults Faults { get; } = new();
    public int FanLevel { get; set; }
    public AirState Air { get; set; } = AirState.Default;
    public TimeSpan Period { get; set; } = TimeSpan.FromMilliseconds(250);

    public SimulatedTelemetrySource(SystemConfig config)
    {
        _config = config;
        FanLevel = config.Fan?.Fan?.CurrentLevel ?? 10;
    }

    public string Name => "Simulator";
    public event Action<TelemetryFrame>? FrameReceived;
    public event Action<string>? StatusChanged;

    public Task StartAsync(CancellationToken ct)
    {
        _cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        _loop = Task.Run(async () =>
        {
            StatusChanged?.Invoke("Simulator running");
            while (!_cts.IsCancellationRequested)
            {
                foreach (var f in Generate(DateTimeOffset.UtcNow)) FrameReceived?.Invoke(f);
                try { await Task.Delay(Period, _cts.Token); } catch (OperationCanceledException) { break; }
            }
        });
        return Task.CompletedTask;
    }

    /// <summary>Build a faulted copy of the system and compute what each sensor would read.</summary>
    public IReadOnlyList<TelemetryFrame> Generate(DateTimeOffset now)
    {
        var json = JsonSerializer.Serialize(_config, SystemConfig.JsonOptions);
        var faulted = JsonSerializer.Deserialize<SystemConfig>(json, SystemConfig.JsonOptions)!;
        foreach (var e in faulted.Elements)
        {
            if (e.Type == ElementType.Duct && e.Zone == Zone.PostSeparator && e.LengthFt >= 10)
            {
                e.FlexFactor *= Faults.RunResistance;
                e.KSum *= Faults.RunResistance;
                if (!e.Flex) e.RoughnessMm *= Faults.RunResistance;
            }
            if (e.Type == ElementType.Cyclone && e.Cyclone is not null) e.Cyclone.K *= Faults.CycloneResistance;
            if (e.Type == ElementType.Exit) e.KSum += Faults.OutletBlockK;
            if (e.Type == ElementType.Source && Faults.LidOpen) e.KSum *= 0.05;
        }
        var model = new SystemModel(faulted);
        double q = model.OperatingFlow(FanLevel, Air);

        var nodes = new Dictionary<string, Dictionary<string, ChannelReading>>(StringComparer.OrdinalIgnoreCase);
        foreach (var ch in faulted.Channels)
        {
            if (Faults.FanNodeOffline && ch.Node == "fan") continue;
            double v = model.PredictReading(ch, q, Air);
            if (ch.Role == ChannelRole.PitotVp) v *= 1 - Faults.PitotClog;
            if (ch.Role == ChannelRole.BinSuction) v *= 1 - Faults.BinLeak;
            v += Noise() + (_zero.TryGetValue($"{ch.Node}/{ch.Channel}", out var z) ? z : 0);
            v = Math.Clamp(v, -ch.FullScalePa, ch.FullScalePa);
            if (!nodes.TryGetValue(ch.Node, out var list)) nodes[ch.Node] = list = new(StringComparer.OrdinalIgnoreCase);
            list[ch.Channel] = new ChannelReading(Math.Round(v, 2), Air.TemperatureC, true);
        }
        _seq++;
        return nodes.Select(kv => new TelemetryFrame
        {
            Node = kv.Key,
            Seq = _seq,
            UptimeMs = _seq * (long)Period.TotalMilliseconds,
            ReceivedAt = now,
            Channels = kv.Value,
            Env = new EnvReading(Air.TemperatureC, Air.RelativeHumidity, Air.PressurePa),
            FanLevel = kv.Key == "fan" ? FanLevel : null,
            FanDriven = kv.Key == "fan" && FollowFanCommands
        }).ToList();
    }

    private double Noise()
    {
        // Box–Muller
        double u1 = 1.0 - _rng.NextDouble(), u2 = _rng.NextDouble();
        return Faults.NoisePa * Math.Sqrt(-2 * Math.Log(u1)) * Math.Cos(2 * Math.PI * u2);
    }

    /// <summary>Commands the app has sent, so tests (and the UI) can see what would go out.</summary>
    public List<(string Node, string Json)> Commands { get; } = new();
    public string? LastStatusBroadcast { get; private set; }

    public Task SendCommandAsync(string node, string json, CancellationToken ct)
    {
        Commands.Add((node, json));
        if (json.Contains("\"set_level\"") && FollowFanCommands)
        {
            int i = json.IndexOf("\"level\"", StringComparison.Ordinal);
            if (i >= 0 && int.TryParse(new string(json[(i + 7)..].Where(char.IsDigit).ToArray()), out var lvl))
                FanLevel = Math.Clamp(lvl, 0, 10);
        }
        StatusChanged?.Invoke($"Simulator: command to {node}: {json}");
        return Task.CompletedTask;
    }

    /// <summary>When true the simulated fan obeys set_level, so Auto mode can be exercised.</summary>
    public bool FollowFanCommands { get; set; } = true;

    public Task BroadcastStatusAsync(string json, CancellationToken ct)
    {
        LastStatusBroadcast = json;
        return Task.CompletedTask;
    }

    public async ValueTask DisposeAsync()
    {
        _cts?.Cancel();
        if (_loop is not null) { try { await _loop; } catch { /* ignore */ } }
        _cts?.Dispose();
    }
}
