using System.Collections.Concurrent;
using System.Net;
using System.Net.Sockets;
using System.Text;

namespace LumosAir.Core.Telemetry;

/// <summary>
/// Zero-setup transport: nodes broadcast JSON datagrams on the LAN; no broker required.
/// Commands go back as unicast datagrams to the node's address on <c>commandPort</c>.
/// </summary>
public sealed class UdpTelemetrySource : ITelemetrySource
{
    private readonly int _port;
    private readonly int _commandPort;
    private readonly ConcurrentDictionary<string, IPAddress> _nodeAddresses = new(StringComparer.OrdinalIgnoreCase);
    private UdpClient? _client;
    private CancellationTokenSource? _cts;
    private Task? _loop;

    public UdpTelemetrySource(int port = 47810, int commandPort = 47811)
    {
        _port = port;
        _commandPort = commandPort;
    }

    public string Name => $"UDP :{_port}";
    public event Action<TelemetryFrame>? FrameReceived;
    public event Action<string>? StatusChanged;

    public Task StartAsync(CancellationToken ct)
    {
        _client = new UdpClient(AddressFamily.InterNetwork);
        _client.Client.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true);
        _client.Client.Bind(new IPEndPoint(IPAddress.Any, _port));
        _client.EnableBroadcast = true;
        _cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        _loop = Task.Run(() => ReceiveLoop(_cts.Token));
        StatusChanged?.Invoke($"Listening for sensor nodes on UDP port {_port}");
        return Task.CompletedTask;
    }

    private async Task ReceiveLoop(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                var result = await _client!.ReceiveAsync(ct);
                if (TelemetryFrame.TryParse(result.Buffer, out var frame) && frame is not null)
                {
                    _nodeAddresses[frame.Node] = result.RemoteEndPoint.Address;
                    FrameReceived?.Invoke(frame);
                }
            }
            catch (OperationCanceledException) { break; }
            catch (ObjectDisposedException) { break; }
            catch (SocketException ex)
            {
                StatusChanged?.Invoke($"UDP error: {ex.Message}");
                await Task.Delay(500, ct).ConfigureAwait(false);
            }
        }
    }

    public async Task SendCommandAsync(string node, string json, CancellationToken ct)
    {
        if (_client is null) throw new InvalidOperationException("Not started.");
        var bytes = Encoding.UTF8.GetBytes(json);
        if (_nodeAddresses.TryGetValue(node, out var addr))
            await _client.SendAsync(bytes, new IPEndPoint(addr, _commandPort), ct);
        else
            await _client.SendAsync(bytes, new IPEndPoint(IPAddress.Broadcast, _commandPort), ct);
    }

    public async ValueTask DisposeAsync()
    {
        _cts?.Cancel();
        _client?.Dispose();
        if (_loop is not null) { try { await _loop; } catch { /* shutting down */ } }
        _cts?.Dispose();
    }
}
