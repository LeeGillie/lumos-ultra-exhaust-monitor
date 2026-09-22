using System.Net.Sockets;
using System.Text;

namespace LumosAir.Core.Telemetry;

/// <summary>
/// Minimal MQTT 3.1.1 client (no dependencies): subscribes to <c>{root}/+/telemetry</c> and publishes
/// commands to <c>{root}/{node}/cmd</c>. Handles QoS 0/1 inbound, keep-alive and reconnect.
/// Use this to share one broker with Home Assistant (Mosquitto add-on).
/// </summary>
public sealed class MqttTelemetrySource : ITelemetrySource
{
    private readonly string _host;
    private readonly int _port;
    private readonly string? _user;
    private readonly string? _password;
    private readonly string _root;
    private readonly SemaphoreSlim _writeLock = new(1, 1);
    private TcpClient? _tcp;
    private NetworkStream? _stream;
    private CancellationTokenSource? _cts;
    private Task? _loop;
    private ushort _packetId = 1;
    private const ushort KeepAliveSeconds = 30;

    public MqttTelemetrySource(string host, int port = 1883, string? user = null, string? password = null, string topicRoot = "lumosair")
    {
        _host = host; _port = port; _user = user; _password = password; _root = topicRoot.TrimEnd('/');
    }

    public string Name => $"MQTT {_host}:{_port}";
    public event Action<TelemetryFrame>? FrameReceived;
    public event Action<string>? StatusChanged;

    public Task StartAsync(CancellationToken ct)
    {
        _cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        _loop = Task.Run(() => RunAsync(_cts.Token));
        return Task.CompletedTask;
    }

    private async Task RunAsync(CancellationToken ct)
    {
        var backoff = TimeSpan.FromSeconds(1);
        while (!ct.IsCancellationRequested)
        {
            try
            {
                StatusChanged?.Invoke($"Connecting to MQTT {_host}:{_port}…");
                _tcp = new TcpClient { NoDelay = true };
                await _tcp.ConnectAsync(_host, _port, ct);
                _stream = _tcp.GetStream();
                await SendAsync(BuildConnect(), ct);
                var (type, _, body) = await ReadPacketAsync(ct);
                if (type != 2 || body.Length < 2 || body[1] != 0)
                    throw new IOException($"MQTT connect refused (code {(body.Length > 1 ? body[1] : -1)})");
                await SendAsync(BuildSubscribe($"{_root}/+/telemetry"), ct);
                StatusChanged?.Invoke($"Connected to MQTT {_host}:{_port}");
                backoff = TimeSpan.FromSeconds(1);

                using var pingCts = CancellationTokenSource.CreateLinkedTokenSource(ct);
                var pinger = PingLoop(pingCts.Token);
                try
                {
                    while (!ct.IsCancellationRequested)
                    {
                        var (t, flags, payload) = await ReadPacketAsync(ct);
                        if (t == 3) await HandlePublish(flags, payload, ct);
                    }
                }
                finally
                {
                    pingCts.Cancel();
                    try { await pinger; } catch { /* ignore */ }
                }
            }
            catch (OperationCanceledException) { break; }
            catch (Exception ex)
            {
                StatusChanged?.Invoke($"MQTT disconnected: {ex.Message}. Retrying in {backoff.TotalSeconds:0}s");
            }
            finally
            {
                _stream?.Dispose(); _tcp?.Dispose();
                _stream = null; _tcp = null;
            }
            try { await Task.Delay(backoff, ct); } catch (OperationCanceledException) { break; }
            backoff = TimeSpan.FromSeconds(Math.Min(30, backoff.TotalSeconds * 2));
        }
    }

    private async Task PingLoop(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            await Task.Delay(TimeSpan.FromSeconds(KeepAliveSeconds / 2.0), ct);
            await SendAsync(new byte[] { 0xC0, 0x00 }, ct);
        }
    }

    private async Task HandlePublish(byte flags, byte[] body, CancellationToken ct)
    {
        int qos = (flags >> 1) & 0x03;
        int topicLen = (body[0] << 8) | body[1];
        string topic = Encoding.UTF8.GetString(body, 2, topicLen);
        int offset = 2 + topicLen;
        if (qos > 0)
        {
            ushort id = (ushort)((body[offset] << 8) | body[offset + 1]);
            offset += 2;
            if (qos == 1) await SendAsync(new byte[] { 0x40, 0x02, (byte)(id >> 8), (byte)id }, ct);
        }
        if (topic.EndsWith("/telemetry", StringComparison.Ordinal)
            && TelemetryFrame.TryParse(body.AsSpan(offset), out var frame) && frame is not null)
            FrameReceived?.Invoke(frame);
    }

    public Task SendCommandAsync(string node, string json, CancellationToken ct)
    {
        if (_stream is null) throw new InvalidOperationException("MQTT not connected.");
        return SendAsync(BuildPublish($"{_root}/{node}/cmd", Encoding.UTF8.GetBytes(json)), ct);
    }

    public Task BroadcastStatusAsync(string json, CancellationToken ct)
    {
        if (_stream is null) return Task.CompletedTask;   // nodes fall back to their own readings
        return SendAsync(BuildPublish($"{_root}/system/status", Encoding.UTF8.GetBytes(json)), ct);
    }

    // ---------- packet building ----------

    private byte[] BuildConnect()
    {
        var body = new List<byte>();
        WriteString(body, "MQTT");
        body.Add(4); // protocol level 3.1.1
        byte flags = 0x02; // clean session
        if (_user is not null) flags |= 0x80;
        if (_password is not null) flags |= 0x40;
        body.Add(flags);
        body.Add((byte)(KeepAliveSeconds >> 8)); body.Add((byte)KeepAliveSeconds);
        WriteString(body, $"lumosair-pc-{Environment.MachineName}-{Environment.ProcessId}");
        if (_user is not null) WriteString(body, _user);
        if (_password is not null) WriteString(body, _password);
        return Frame(0x10, body);
    }

    private byte[] BuildSubscribe(string filter)
    {
        var body = new List<byte>();
        ushort id = _packetId++;
        body.Add((byte)(id >> 8)); body.Add((byte)id);
        WriteString(body, filter);
        body.Add(0); // QoS 0
        return Frame(0x82, body);
    }

    private static byte[] BuildPublish(string topic, byte[] payload)
    {
        var body = new List<byte>();
        WriteString(body, topic);
        body.AddRange(payload);
        return Frame(0x30, body);
    }

    private static void WriteString(List<byte> buf, string s)
    {
        var b = Encoding.UTF8.GetBytes(s);
        buf.Add((byte)(b.Length >> 8)); buf.Add((byte)b.Length);
        buf.AddRange(b);
    }

    internal static byte[] Frame(byte header, List<byte> body)
    {
        var packet = new List<byte> { header };
        int len = body.Count;
        do
        {
            byte d = (byte)(len % 128);
            len /= 128;
            if (len > 0) d |= 0x80;
            packet.Add(d);
        } while (len > 0);
        packet.AddRange(body);
        return packet.ToArray();
    }

    private async Task SendAsync(byte[] data, CancellationToken ct)
    {
        var s = _stream ?? throw new IOException("Not connected");
        await _writeLock.WaitAsync(ct);
        try { await s.WriteAsync(data, ct); }
        finally { _writeLock.Release(); }
    }

    private async Task<(int type, byte flags, byte[] body)> ReadPacketAsync(CancellationToken ct)
    {
        var s = _stream ?? throw new IOException("Not connected");
        var header = await ReadExactAsync(s, 1, ct);
        int multiplier = 1, len = 0;
        byte d;
        do
        {
            d = (await ReadExactAsync(s, 1, ct))[0];
            len += (d & 0x7F) * multiplier;
            multiplier *= 128;
            if (multiplier > 128 * 128 * 128 * 128) throw new IOException("Malformed MQTT length");
        } while ((d & 0x80) != 0);
        var body = len == 0 ? Array.Empty<byte>() : await ReadExactAsync(s, len, ct);
        return (header[0] >> 4, (byte)(header[0] & 0x0F), body);
    }

    private static async Task<byte[]> ReadExactAsync(Stream s, int count, CancellationToken ct)
    {
        var buf = new byte[count];
        await s.ReadExactlyAsync(buf, ct);
        return buf;
    }

    public async ValueTask DisposeAsync()
    {
        _cts?.Cancel();
        if (_stream is not null)
        {
            try { await _stream.WriteAsync(new byte[] { 0xE0, 0x00 }); } catch { /* ignore */ }
        }
        _stream?.Dispose(); _tcp?.Dispose();
        if (_loop is not null) { try { await _loop; } catch { /* ignore */ } }
        _cts?.Dispose();
    }
}
