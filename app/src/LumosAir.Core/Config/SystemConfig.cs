using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace LumosAir.Core.Config;

public enum ElementType { Source, Duct, Fitting, Cyclone, Fan, Exit }

/// <summary>Where an element sits relative to the separator. Drives which transport-velocity rule applies.</summary>
public enum Zone { PreSeparator, Separator, PostSeparator }

public enum ChannelRole
{
    /// <summary>Static pressure difference across the cyclone (inlet tap − outlet tap).</summary>
    CycloneDp,
    /// <summary>Dust-bin suction relative to the room.</summary>
    BinSuction,
    /// <summary>Pitot-static velocity pressure.</summary>
    PitotVp,
    /// <summary>Static suction at the start of the long run.</summary>
    RunStartSuction,
    /// <summary>Static suction at the fan inlet.</summary>
    FanInletSuction,
    /// <summary>Suction inside the laser enclosure / at its outlet.</summary>
    EnclosureSuction,
    /// <summary>Any other differential; shown but not used by rules.</summary>
    Generic
}

public sealed class SystemConfig
{
    public string Name { get; set; } = "Lumos Ultra exhaust";
    public AirConfig Air { get; set; } = new();
    public string ActiveProfileId { get; set; } = "metal";
    public List<MaterialProfile> Profiles { get; set; } = new();
    /// <summary>Elements in airflow order, from the laser to the outside.</summary>
    public List<ElementConfig> Elements { get; set; } = new();
    /// <summary>Sensor channels published by the ESP32 nodes.</summary>
    public List<ChannelConfig> Channels { get; set; } = new();
    public Thresholds Thresholds { get; set; } = new();
    public TransportConfig Transport { get; set; } = new();

    public MaterialProfile ActiveProfile =>
        Profiles.FirstOrDefault(p => p.Id == ActiveProfileId) ?? Profiles.FirstOrDefault() ?? new MaterialProfile();

    public static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        ReadCommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.CamelCase) }
    };

    public static SystemConfig Load(string path) =>
        JsonSerializer.Deserialize<SystemConfig>(File.ReadAllText(path), JsonOptions)
        ?? throw new InvalidDataException($"Could not parse {path}");

    public void Save(string path) => File.WriteAllText(path, JsonSerializer.Serialize(this, JsonOptions));

    public ElementConfig? Fan => Elements.FirstOrDefault(e => e.Type == ElementType.Fan);
    public ElementConfig? Cyclone => Elements.FirstOrDefault(e => e.Type == ElementType.Cyclone);
}

public sealed class AirConfig
{
    public double TemperatureC { get; set; } = 20;
    public double RelativeHumidity { get; set; } = 40;
    /// <summary>Barometric pressure used when no BME280 reading is available (Spokane ≈ 94.6 kPa).</summary>
    public double PressurePa { get; set; } = 94_600;
}

public sealed class MaterialProfile
{
    public string Id { get; set; } = "metal";
    public string Name { get; set; } = "Metal (fiber) – brass, steel, aluminium";
    /// <summary>Particle density, kg/m³ (brass ≈ 8500).</summary>
    public double ParticleDensity { get; set; } = 8500;
    /// <summary>Minimum duct velocity before the separator so coarse particles stay airborne.</summary>
    public double MinPreSeparatorFpm { get; set; } = 3500;
    /// <summary>Minimum duct velocity after the separator. Only fume/fines remain, which don't settle by gravity; this is a residue/cleaning guide, not a hard limit.</summary>
    public double MinPostSeparatorFpm { get; set; } = 500;
    /// <summary>Largest acceptable cyclone 50 % cut size, µm. Cyclone speed advice is driven by this.</summary>
    public double TargetCutSizeMicron { get; set; } = 5;
    /// <summary>Enclosure suction needed to keep fumes from escaping, Pa.</summary>
    public double MinEnclosureSuctionPa { get; set; } = 3;
}

public sealed class ElementConfig
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public ElementType Type { get; set; }
    public Zone Zone { get; set; } = Zone.PostSeparator;
    /// <summary>Diameter the element's velocity (and K) is referenced to.</summary>
    public double DiameterIn { get; set; } = 6;
    public double LengthFt { get; set; }
    public bool Flex { get; set; }
    /// <summary>Friction multiplier for flex duct vs smooth pipe. ~1.5 stretched taut, 2.5 typical, 4+ sagging/compressed.</summary>
    public double FlexFactor { get; set; } = 2.5;
    /// <summary>Wall roughness, mm (galvanized ≈ 0.09, PVC ≈ 0.0015).</summary>
    public double RoughnessMm { get; set; } = 0.09;
    /// <summary>Sum of minor-loss coefficients (bends, transitions, entries) in velocity heads.</summary>
    public double KSum { get; set; }
    public CycloneConfig? Cyclone { get; set; }
    public FanConfig? Fan { get; set; }
}

public sealed class CycloneConfig
{
    public string Model { get; set; } = "Generic 4\" inlet cyclone";
    /// <summary>Inlet dimensions. For a round inlet set width = height = diameter and Round = true.</summary>
    public double InletWidthIn { get; set; } = 4;
    public double InletHeightIn { get; set; } = 4;
    public bool RoundInlet { get; set; } = true;
    /// <summary>Pressure drop in inlet velocity heads (Shepherd–Lapple K; conventional designs ≈ 6–8, measure yours).</summary>
    public double K { get; set; } = 6;
    /// <summary>Effective vortex turns for the Lapple cut-size estimate.</summary>
    public double Turns { get; set; } = 5;
    /// <summary>Where the dust-bin pressure sits between inlet (0) and outlet (1) static; refined by baseline capture.</summary>
    public double BinFraction { get; set; } = 0.5;
    /// <summary>Below this the vortex is weak regardless of particle size.</summary>
    public double MinInletFpm { get; set; } = 1000;
    public double MaxInletFpm { get; set; } = 4500;
}

public sealed class FanConfig
{
    public string Model { get; set; } = "AC Infinity CLOUDLINE S6";
    /// <summary>Full-speed fan curve. Default is an ESTIMATE from the published 425 CFM / 503 Pa end points — replace with measured data.</summary>
    public double[] CurveCfm { get; set; } = { 0, 100, 200, 300, 350, 400, 425 };
    public double[] CurvePa { get; set; } = { 503, 480, 420, 300, 200, 80, 0 };
    public int Levels { get; set; } = 10;
    /// <summary>Speed fraction for each level 1..Levels. Null = linear (level/Levels).</summary>
    public double[]? LevelFractions { get; set; }
    public int CurrentLevel { get; set; } = 10;
}

public sealed class ChannelConfig
{
    /// <summary>Node id as published by the firmware, e.g. "laser".</summary>
    public string Node { get; set; } = "";
    /// <summary>Channel id inside the node payload, e.g. "cyc_dp".</summary>
    public string Channel { get; set; } = "";
    public string Label { get; set; } = "";
    public ChannelRole Role { get; set; }
    /// <summary>Tap on the sensor's + port: "after:&lt;elementId&gt;", "before:&lt;elementId&gt;", "bin:&lt;cycloneId&gt;", "inside:&lt;elementId&gt;" (still-air plenum) or "room".</summary>
    public string HighTap { get; set; } = "room";
    /// <summary>Tap on the sensor's − port.</summary>
    public string LowTap { get; set; } = "room";
    /// <summary>For pitot channels: ratio of mean to centreline velocity (≈0.9 fully developed turbulent flow).</summary>
    public double ProfileFactor { get; set; } = 0.9;
    /// <summary>For pitot channels: element the probe sits in.</summary>
    public string? PitotElementId { get; set; }
    /// <summary>Sensor full-scale, Pa; readings beyond 98 % are flagged as saturated.</summary>
    public double FullScalePa { get; set; } = 500;
}

public sealed class Thresholds
{
    public double StaleSeconds { get; set; } = 5;
    public double PersistSeconds { get; set; } = 3;
    public double FanOffSuctionPa { get; set; } = 5;
    public double FlowMismatchFraction { get; set; } = 0.20;
    public double DriftWarnFraction { get; set; } = 0.30;
    public double DriftCriticalFraction { get; set; } = 0.60;
    public double BinLeakDropFraction { get; set; } = 0.30;
    /// <summary>Extra velocity margin used when recommending a fan level.</summary>
    public double VelocityMargin { get; set; } = 0.10;
    /// <summary>Smoothing time constant for readings, seconds.</summary>
    public double SmoothingSeconds { get; set; } = 1.5;
}

public sealed class TransportConfig
{
    public bool UdpEnabled { get; set; } = true;
    public int UdpPort { get; set; } = 47810;
    public int NodeCommandPort { get; set; } = 47811;
    public bool MqttEnabled { get; set; }
    public string MqttHost { get; set; } = "homeassistant.local";
    public int MqttPort { get; set; } = 1883;
    public string? MqttUser { get; set; }
    public string? MqttPassword { get; set; }
    public string MqttTopicRoot { get; set; } = "lumosair";
}
