using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Windows;
using System.Windows.Media;
using System.Windows.Threading;
using LumosAir.Core.Config;
using LumosAir.Core.Diagnostics;
using LumosAir.Core.Telemetry;

namespace LumosAir.Desktop.ViewModels;

public enum SourceKind { Simulator, Udp, Mqtt }

public sealed class SegmentRow : ObservableObject
{
    public string Name { get; init; } = "";
    public string Detail { get; init; } = "";
    public double VelocityFpm { get; init; }
    public double MinFpm { get; init; }
    /// <summary>0..1 bar fill (velocity relative to 1.5 × minimum).</summary>
    public double Fill => MinFpm <= 0 ? 0.5 : Math.Clamp(VelocityFpm / (MinFpm * 1.5), 0, 1);
    public double MinMark => MinFpm <= 0 ? -1 : 1 / 1.5;
    public Brush Color { get; init; } = Brushes.Gray;
    public string VelocityText => $"{VelocityFpm:0} fpm";
    public string MinText => MinFpm > 0 ? $"min {MinFpm:0}" : "";
}

public sealed class FindingRow
{
    public string Title { get; init; } = "";
    public string Detail { get; init; } = "";
    public string Action { get; init; } = "";
    public string SeverityText { get; init; } = "";
    public Brush Color { get; init; } = Brushes.Gray;
}

public sealed class ChannelRow
{
    public string Label { get; init; } = "";
    public string Reading { get; init; } = "";
    public string Model { get; init; } = "";
    public string Drift { get; init; } = "";
    public string Flow { get; init; } = "";
    public Brush DriftColor { get; init; } = Brushes.Gray;
}

public sealed class MainViewModel : ObservableObject, IAsyncDisposable
{
    public static readonly string DataDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "LumosAir");
    public static string ConfigPath => Path.Combine(DataDir, "system.json");
    public static string BaselinePath => Path.Combine(DataDir, "baseline.json");
    public static string LogPath => Path.Combine(DataDir, $"log-{DateTime.Now:yyyyMMdd}.csv");

    private readonly DispatcherTimer _timer;
    private SystemConfig _config;
    private DiagnosticsEngine _engine;
    private ITelemetrySource? _source;
    private CancellationTokenSource? _cts;
    private DateTime _lastLog = DateTime.MinValue;

    public ObservableCollection<SegmentRow> Segments { get; } = new();
    public ObservableCollection<FindingRow> Findings { get; } = new();
    public ObservableCollection<ChannelRow> Channels { get; } = new();
    public ObservableCollection<MaterialProfile> Profiles { get; } = new();
    public IReadOnlyList<int> FanLevels { get; }
    public Array SourceKinds { get; } = Enum.GetValues(typeof(SourceKind));

    /// <summary>Rolling history for the trend chart: (time, CFM, cyclone inlet fpm).</summary>
    public List<(DateTime t, double cfm, double cycFpm)> History { get; } = new();
    public event Action? HistoryUpdated;

    public RelayCommand ConnectCommand { get; }
    public RelayCommand CaptureBaselineCommand { get; }
    public RelayCommand ClearBaselineCommand { get; }
    public RelayCommand ZeroCommand { get; }
    public RelayCommand OpenConfigCommand { get; }
    public RelayCommand ReloadConfigCommand { get; }
    public RelayCommand OpenDataFolderCommand { get; }

    public MainViewModel()
    {
        Directory.CreateDirectory(DataDir);
        if (!File.Exists(ConfigPath)) DefaultSystems.OptionA().Save(ConfigPath);
        _config = SystemConfig.Load(ConfigPath);
        _engine = new DiagnosticsEngine(_config, Baseline.TryLoad(BaselinePath));
        FanLevels = Enumerable.Range(0, (_config.Fan?.Fan?.Levels ?? 10) + 1).ToList();
        foreach (var p in _config.Profiles) Profiles.Add(p);
        _selectedProfile = _config.ActiveProfile;
        _manualFanLevel = _engine.ManualFanLevel;
        _sourceKind = _config.Transport.MqttEnabled ? SourceKind.Mqtt : SourceKind.Simulator;
        _mqttHost = _config.Transport.MqttHost;

        ConnectCommand = new RelayCommand(ToggleConnectionAsync);
        CaptureBaselineCommand = new RelayCommand(CaptureBaseline, () => IsConnected);
        ClearBaselineCommand = new RelayCommand(ClearBaseline, () => _engine.Baseline is not null);
        ZeroCommand = new RelayCommand(ZeroSensorsAsync, () => IsConnected);
        OpenConfigCommand = new RelayCommand(() => Process.Start(new ProcessStartInfo("notepad.exe", $"\"{ConfigPath}\"") { UseShellExecute = true }));
        ReloadConfigCommand = new RelayCommand(ReloadConfig);
        OpenDataFolderCommand = new RelayCommand(() => Process.Start(new ProcessStartInfo(DataDir) { UseShellExecute = true }));

        _timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(500) };
        _timer.Tick += (_, _) => Refresh();
        _timer.Start();
        Refresh();
    }

    // ---------------- bindable state ----------------

    public string SystemName => _config.Name;

    private SourceKind _sourceKind;
    public SourceKind SourceKind
    {
        get => _sourceKind;
        set { if (Set(ref _sourceKind, value)) OnPropertyChanged(nameof(IsMqtt)); }
    }
    public bool IsMqtt => SourceKind == SourceKind.Mqtt;

    private string _mqttHost;
    public string MqttHost { get => _mqttHost; set => Set(ref _mqttHost, value); }

    private bool _isConnected;
    public bool IsConnected
    {
        get => _isConnected;
        private set
        {
            if (Set(ref _isConnected, value))
            {
                OnPropertyChanged(nameof(ConnectText));
                OnPropertyChanged(nameof(IsSimulator));
            }
        }
    }
    public string ConnectText => IsConnected ? "Disconnect" : "Connect";
    public bool IsSimulator => IsConnected && _source is SimulatedTelemetrySource;

    private string _status = "Not connected";
    public string Status { get => _status; set => Set(ref _status, value); }

    private MaterialProfile _selectedProfile;
    public MaterialProfile SelectedProfile
    {
        get => _selectedProfile;
        set
        {
            if (value is null || !Set(ref _selectedProfile, value)) return;
            _config.ActiveProfileId = value.Id;
            Refresh();
        }
    }

    private int _manualFanLevel;
    public int ManualFanLevel
    {
        get => _manualFanLevel;
        set
        {
            if (!Set(ref _manualFanLevel, value)) return;
            _engine.ManualFanLevel = value;
            if (_source is SimulatedTelemetrySource sim) sim.FanLevel = value;
        }
    }

    private string _flowText = "--";
    public string FlowText { get => _flowText; set => Set(ref _flowText, value); }
    private string _flowSource = "";
    public string FlowSource { get => _flowSource; set => Set(ref _flowSource, value); }
    private string _cycloneText = "--";
    public string CycloneText { get => _cycloneText; set => Set(ref _cycloneText, value); }
    private string _cycloneDetail = "";
    public string CycloneDetail { get => _cycloneDetail; set => Set(ref _cycloneDetail, value); }
    private string _recommendText = "--";
    public string RecommendText { get => _recommendText; set => Set(ref _recommendText, value); }
    private string _fanText = "";
    public string FanText { get => _fanText; set => Set(ref _fanText, value); }
    private string _overallText = "";
    public string OverallText { get => _overallText; set => Set(ref _overallText, value); }
    private Brush _overallColor = Brushes.Gray;
    public Brush OverallColor { get => _overallColor; set => Set(ref _overallColor, value); }
    private string _airText = "";
    public string AirText { get => _airText; set => Set(ref _airText, value); }
    private string _baselineText = "";
    public string BaselineText { get => _baselineText; set => Set(ref _baselineText, value); }

    // Simulator knobs
    public SimulationFaults? Faults => (_source as SimulatedTelemetrySource)?.Faults;
    public double SimRun { get => Faults?.RunResistance ?? 1; set { if (Faults is { } f) f.RunResistance = value; OnPropertyChanged(); } }
    public double SimCyclone { get => Faults?.CycloneResistance ?? 1; set { if (Faults is { } f) f.CycloneResistance = value; OnPropertyChanged(); } }
    public double SimBin { get => Faults?.BinLeak ?? 0; set { if (Faults is { } f) f.BinLeak = value; OnPropertyChanged(); } }
    public double SimPitot { get => Faults?.PitotClog ?? 0; set { if (Faults is { } f) f.PitotClog = value; OnPropertyChanged(); } }
    public double SimOutlet { get => Faults?.OutletBlockK ?? 0; set { if (Faults is { } f) f.OutletBlockK = value; OnPropertyChanged(); } }
    public bool SimLid { get => Faults?.LidOpen ?? false; set { if (Faults is { } f) f.LidOpen = value; OnPropertyChanged(); } }
    public bool SimFanOffline { get => Faults?.FanNodeOffline ?? false; set { if (Faults is { } f) f.FanNodeOffline = value; OnPropertyChanged(); } }

    // ---------------- actions ----------------

    private async Task ToggleConnectionAsync()
    {
        if (IsConnected)
        {
            await DisconnectAsync();
            return;
        }
        _cts = new CancellationTokenSource();
        var t = _config.Transport;
        _source = SourceKind switch
        {
            SourceKind.Udp => new UdpTelemetrySource(t.UdpPort, t.NodeCommandPort),
            SourceKind.Mqtt => new MqttTelemetrySource(MqttHost, t.MqttPort, t.MqttUser, t.MqttPassword, t.MqttTopicRoot),
            _ => new SimulatedTelemetrySource(_config) { FanLevel = ManualFanLevel }
        };
        _source.FrameReceived += _engine.Ingest;
        _source.StatusChanged += s => Application.Current?.Dispatcher.BeginInvoke(() => Status = s);
        try
        {
            await _source.StartAsync(_cts.Token);
            IsConnected = true;
            Status = $"Connected: {_source.Name}";
            foreach (var n in new[] { nameof(SimRun), nameof(SimCyclone), nameof(SimBin), nameof(SimPitot), nameof(SimOutlet), nameof(SimLid), nameof(SimFanOffline) })
                OnPropertyChanged(n);
        }
        catch (Exception ex)
        {
            Status = $"Could not start {_source.Name}: {ex.Message}";
            await _source.DisposeAsync();
            _source = null;
        }
    }

    private async Task DisconnectAsync()
    {
        _cts?.Cancel();
        if (_source is not null)
        {
            _source.FrameReceived -= _engine.Ingest;
            await _source.DisposeAsync();
        }
        _source = null;
        IsConnected = false;
        Status = "Disconnected";
    }

    private void CaptureBaseline()
    {
        try
        {
            var b = _engine.CaptureBaseline();
            b.Save(BaselinePath);
            Status = $"Baseline saved at {b.FlowCfm:0} CFM, level {b.FanLevel}";
        }
        catch (Exception ex) { Status = ex.Message; }
    }

    private void ClearBaseline()
    {
        _engine.Baseline = null;
        try { File.Delete(BaselinePath); } catch { /* ignore */ }
        Status = "Baseline cleared — drift checks use the model until you capture a new one.";
    }

    private async Task ZeroSensorsAsync()
    {
        if (_source is null) return;
        var r = MessageBox.Show("Turn the fan OFF and wait ~10 s for the air to stop.\n\nZero all pressure sensors now?",
            "Zero sensors", MessageBoxButton.OKCancel, MessageBoxImage.Question);
        if (r != MessageBoxResult.OK) return;
        foreach (var node in _config.Channels.Select(c => c.Node).Distinct())
        {
            try { await _source.SendCommandAsync(node, """{"cmd":"zero"}""", CancellationToken.None); }
            catch (Exception ex) { Status = $"Zero failed for {node}: {ex.Message}"; return; }
        }
        Status = "Zero command sent to all nodes.";
    }

    private void ReloadConfig()
    {
        try
        {
            _config = SystemConfig.Load(ConfigPath);
            _engine.Reconfigure(_config);
            Profiles.Clear();
            foreach (var p in _config.Profiles) Profiles.Add(p);
            SelectedProfile = _config.ActiveProfile;
            OnPropertyChanged(nameof(SystemName));
            Status = "Configuration reloaded. Reconnect to apply transport changes.";
        }
        catch (Exception ex) { Status = $"Config error: {ex.Message}"; }
    }

    // ---------------- refresh ----------------

    private void Refresh()
    {
        var snap = _engine.Evaluate();
        bool live = IsConnected;

        FlowText = live ? $"{snap.FlowCfm:0}" : "--";
        FlowSource = live ? $"CFM · {snap.FlowSource}" : "CFM";
        FanText = $"Fan level {snap.FanLevel}" + (snap.FanLevel != ManualFanLevel ? " (reported by node)" : "");
        RecommendText = snap.RecommendedLevel is { } r ? r.ToString() : "—";
        CycloneText = snap.CycloneInletFpm is { } ci && live ? $"{ci:0} fpm" : "--";
        CycloneDetail = snap.CutSizeMicron is { } d && live
            ? $"cut size ≈ {d:0.0} µm · catches ≈{snap.Efficiency5Micron:P0} of 5 µm" + (snap.CycloneDpPa is { } dp ? $" · ΔP {dp:0} Pa" : "")
            : "";
        AirText = $"ρ {snap.Air.Density:0.000} kg/m³ · {snap.Air.TemperatureC:0.0} °C · {snap.Air.PressurePa / 1000:0.0} kPa";
        BaselineText = _engine.Baseline is { } b ? $"Baseline {b.CapturedAt.ToLocalTime():g} @ {b.FlowCfm:0} CFM" : "No baseline yet — capture one with a clean system";

        var overall = live ? snap.Overall : Severity.Info;
        OverallText = !live ? "OFFLINE" : overall switch
        {
            Severity.Ok => "ALL GOOD",
            Severity.Info => "INFO",
            Severity.Advice => "ADVICE",
            Severity.Warning => "CHECK",
            _ => "PROBLEM"
        };
        OverallColor = live ? SeverityBrush(overall) : Brushes.DimGray;

        Segments.Clear();
        foreach (var s in snap.Segments)
            Segments.Add(new SegmentRow
            {
                Name = s.Name,
                Detail = $"{s.DiameterIn:0.#}\" · {s.Zone}",
                VelocityFpm = live ? s.VelocityFpm : 0,
                MinFpm = s.MinFpm,
                Color = live ? SeverityBrush(s.Severity) : Brushes.DimGray
            });

        Findings.Clear();
        if (live)
            foreach (var f in snap.Findings)
                Findings.Add(new FindingRow
                {
                    Title = f.Title, Detail = f.Detail, Action = f.Action ?? "",
                    SeverityText = f.Severity.ToString().ToUpperInvariant(), Color = SeverityBrush(f.Severity)
                });

        Channels.Clear();
        foreach (var c in snap.Channels)
            Channels.Add(new ChannelRow
            {
                Label = c.Label,
                Reading = c.Stale ? "stale" : c.ReadingPa is { } v ? $"{v:0.0}" : "--",
                Model = $"{c.PredictedPa:0.0}",
                Drift = c.Drift is { } d2 ? d2.ToString("+0%;-0%;0%") : "",
                Flow = c.FlowCfm is { } fl ? $"{fl:0}" : "",
                DriftColor = c.Drift is { } d3 ? Math.Abs(d3) >= 0.3 ? SeverityBrush(Severity.Warning) : Math.Abs(d3) >= 0.15 ? SeverityBrush(Severity.Advice) : SeverityBrush(Severity.Ok) : Brushes.Gray
            });

        if (live)
        {
            History.Add((DateTime.Now, snap.FlowCfm, snap.CycloneInletFpm ?? 0));
            var cutoff = DateTime.Now.AddMinutes(-10);
            History.RemoveAll(h => h.t < cutoff);
            HistoryUpdated?.Invoke();
            LogCsv(snap);
        }
    }

    private void LogCsv(DiagnosticSnapshot s)
    {
        if ((DateTime.Now - _lastLog).TotalSeconds < 5) return;
        _lastLog = DateTime.Now;
        try
        {
            bool header = !File.Exists(LogPath);
            using var w = File.AppendText(LogPath);
            if (header)
                w.WriteLine("time,cfm,source,fanLevel,cycInletFpm,d50um," + string.Join(",", s.Channels.Select(c => c.Key)) + ",findings");
            w.WriteLine(string.Join(",",
                s.Time.ToLocalTime().ToString("s"),
                s.FlowCfm.ToString("0.0"),
                s.FlowSource.Replace(',', ';'),
                s.FanLevel,
                s.CycloneInletFpm?.ToString("0") ?? "",
                s.CutSizeMicron?.ToString("0.00") ?? "",
                string.Join(",", s.Channels.Select(c => c.ReadingPa?.ToString("0.0") ?? "")),
                string.Join(" | ", s.Findings.Select(f => f.Code))));
        }
        catch { /* logging is best-effort */ }
    }

    public static Brush SeverityBrush(Severity s) => s switch
    {
        Severity.Ok => Freeze(new SolidColorBrush(Color.FromRgb(0x3F, 0xB9, 0x50))),
        Severity.Info => Freeze(new SolidColorBrush(Color.FromRgb(0x4F, 0xA3, 0xE0))),
        Severity.Advice => Freeze(new SolidColorBrush(Color.FromRgb(0xD8, 0xB4, 0x3A))),
        Severity.Warning => Freeze(new SolidColorBrush(Color.FromRgb(0xE8, 0x80, 0x2E))),
        _ => Freeze(new SolidColorBrush(Color.FromRgb(0xE0, 0x4A, 0x4A)))
    };

    private static Brush Freeze(SolidColorBrush b) { b.Freeze(); return b; }

    public async ValueTask DisposeAsync()
    {
        _timer.Stop();
        await DisconnectAsync();
    }
}
