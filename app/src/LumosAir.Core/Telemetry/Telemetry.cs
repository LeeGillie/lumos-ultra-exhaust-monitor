using System.Text.Json;

namespace LumosAir.Core.Telemetry;

/// <summary>One reading from one sensor channel.</summary>
public readonly record struct ChannelReading(double Pa, double? TemperatureC, bool Ok);

/// <summary>Ambient conditions from a node's BME280 (optional).</summary>
public readonly record struct EnvReading(double TemperatureC, double RelativeHumidity, double PressurePa);

/// <summary>A decoded telemetry packet from an ESP32 node.</summary>
public sealed class TelemetryFrame
{
    public string Node { get; init; } = "";
    public long Seq { get; init; }
    public long UptimeMs { get; init; }
    public DateTimeOffset ReceivedAt { get; init; } = DateTimeOffset.UtcNow;
    public Dictionary<string, ChannelReading> Channels { get; init; } = new();
    public EnvReading? Env { get; init; }
    /// <summary>Fan level reported by a fan node (optional, phase 2).</summary>
    public int? FanLevel { get; init; }
    public int? FanRpm { get; init; }

    /// <summary>
    /// Wire format (UDP datagram or MQTT payload):
    /// {"node":"laser","seq":1,"up":1234,
    ///  "ch":{"cyc_dp":{"pa":212.4,"t":24.1,"ok":true}},
    ///  "env":{"t":24.0,"rh":41.2,"p":94412.0},
    ///  "fan":{"level":7,"rpm":2100}}
    /// </summary>
    public static bool TryParse(ReadOnlySpan<byte> utf8, out TelemetryFrame? frame, DateTimeOffset? receivedAt = null)
    {
        frame = null;
        try
        {
            using var doc = JsonDocument.Parse(utf8.ToArray());
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object || !root.TryGetProperty("node", out var nodeEl)) return false;
            var channels = new Dictionary<string, ChannelReading>(StringComparer.OrdinalIgnoreCase);
            if (root.TryGetProperty("ch", out var ch) && ch.ValueKind == JsonValueKind.Object)
            {
                foreach (var p in ch.EnumerateObject())
                {
                    if (p.Value.ValueKind != JsonValueKind.Object) continue;
                    if (!p.Value.TryGetProperty("pa", out var pa) || pa.ValueKind != JsonValueKind.Number)
                    {
                        channels[p.Name] = new ChannelReading(double.NaN, null, false);
                        continue;
                    }
                    double? t = p.Value.TryGetProperty("t", out var te) && te.ValueKind == JsonValueKind.Number ? te.GetDouble() : null;
                    bool ok = !p.Value.TryGetProperty("ok", out var okEl) || okEl.ValueKind != JsonValueKind.False;
                    channels[p.Name] = new ChannelReading(pa.GetDouble(), t, ok);
                }
            }
            EnvReading? env = null;
            if (root.TryGetProperty("env", out var e) && e.ValueKind == JsonValueKind.Object
                && e.TryGetProperty("t", out var et) && e.TryGetProperty("p", out var ep))
            {
                double rh = e.TryGetProperty("rh", out var erh) && erh.ValueKind == JsonValueKind.Number ? erh.GetDouble() : 40;
                env = new EnvReading(et.GetDouble(), rh, ep.GetDouble());
            }
            int? level = null, rpm = null;
            if (root.TryGetProperty("fan", out var fan) && fan.ValueKind == JsonValueKind.Object)
            {
                if (fan.TryGetProperty("level", out var l) && l.ValueKind == JsonValueKind.Number) level = l.GetInt32();
                if (fan.TryGetProperty("rpm", out var r) && r.ValueKind == JsonValueKind.Number) rpm = r.GetInt32();
            }
            frame = new TelemetryFrame
            {
                Node = nodeEl.GetString() ?? "",
                Seq = root.TryGetProperty("seq", out var s) && s.ValueKind == JsonValueKind.Number ? s.GetInt64() : 0,
                UptimeMs = root.TryGetProperty("up", out var u) && u.ValueKind == JsonValueKind.Number ? u.GetInt64() : 0,
                ReceivedAt = receivedAt ?? DateTimeOffset.UtcNow,
                Channels = channels,
                Env = env,
                FanLevel = level,
                FanRpm = rpm
            };
            return frame.Node.Length > 0;
        }
        catch (JsonException)
        {
            return false;
        }
    }
}

/// <summary>Anything that produces telemetry frames: UDP listener, MQTT client, simulator.</summary>
public interface ITelemetrySource : IAsyncDisposable
{
    string Name { get; }
    event Action<TelemetryFrame>? FrameReceived;
    event Action<string>? StatusChanged;
    Task StartAsync(CancellationToken ct);
    /// <summary>Send a command (e.g. {"cmd":"zero"}) to a node.</summary>
    Task SendCommandAsync(string node, string json, CancellationToken ct);
}
