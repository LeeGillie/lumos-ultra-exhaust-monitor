using LumosAir.Core.Config;

namespace LumosAir.Core.Model;

/// <summary>Physics of the duct path: losses, fan operating point, tap pressures and cyclone performance.</summary>
public sealed class SystemModel
{
    public SystemConfig Config { get; }
    public IReadOnlyList<ElementConfig> Elements => Config.Elements;

    public SystemModel(SystemConfig config)
    {
        Config = config;
        if (config.Elements.Count == 0) throw new ArgumentException("System has no elements.");
        var ids = new HashSet<string>();
        foreach (var e in config.Elements)
            if (!ids.Add(e.Id)) throw new ArgumentException($"Duplicate element id '{e.Id}'.");
    }

    // ---------- geometry ----------

    public static double Area(ElementConfig e)
    {
        if (e.Type == ElementType.Cyclone && e.Cyclone is { } c) return CycloneInletArea(c);
        return Units.CircleArea(Units.FromInches(e.DiameterIn));
    }

    public static double CycloneInletArea(CycloneConfig c) => c.RoundInlet
        ? Units.CircleArea(Units.FromInches(c.InletWidthIn))
        : Units.FromInches(c.InletWidthIn) * Units.FromInches(c.InletHeightIn);

    public static double Velocity(ElementConfig e, double q) => q / Area(e);

    /// <summary>Velocity in the connecting duct (ignores cyclone inlet throat).</summary>
    public static double DuctVelocity(ElementConfig e, double q) => q / Units.CircleArea(Units.FromInches(e.DiameterIn));

    // ---------- losses ----------

    /// <summary>Darcy friction factor (Swamee–Jain, laminar below Re 2300).</summary>
    public static double FrictionFactor(double reynolds, double relRoughness)
    {
        if (reynolds <= 0) return 0;
        if (reynolds < 2300) return 64.0 / reynolds;
        double t = Math.Log10(relRoughness / 3.7 + 5.74 / Math.Pow(reynolds, 0.9));
        return 0.25 / (t * t);
    }

    /// <summary>Total-pressure loss of one element at flow q (m³/s), Pa.</summary>
    public double ElementLoss(ElementConfig e, double q, AirState air)
    {
        q = Math.Abs(q);
        if (q == 0) return 0;
        switch (e.Type)
        {
            case ElementType.Fan:
                return 0;
            case ElementType.Cyclone:
            {
                var c = e.Cyclone ?? new CycloneConfig();
                double vi = q / CycloneInletArea(c);
                return c.K * air.VelocityPressure(vi) + e.KSum * air.VelocityPressure(DuctVelocity(e, q));
            }
            default:
            {
                double d = Units.FromInches(e.DiameterIn);
                double v = q / Units.CircleArea(d);
                double vp = air.VelocityPressure(v);
                double friction = 0;
                if (e.LengthFt > 0)
                {
                    double re = air.Density * v * d / air.Viscosity;
                    double f = FrictionFactor(re, e.RoughnessMm / 1000.0 / d);
                    friction = f * Units.FromFeet(e.LengthFt) / d * vp * (e.Flex ? e.FlexFactor : 1.0);
                }
                return friction + e.KSum * vp;
            }
        }
    }

    public double TotalLoss(double q, AirState air) => Elements.Sum(e => ElementLoss(e, q, air));

    // ---------- fan ----------

    public FanConfig FanConfig => Config.Fan?.Fan ?? new FanConfig();

    public double SpeedFraction(int level)
    {
        var f = FanConfig;
        level = Math.Clamp(level, 0, f.Levels);
        if (level == 0) return 0;
        if (f.LevelFractions is { Length: > 0 } lf && level - 1 < lf.Length) return lf[level - 1];
        return (double)level / f.Levels;
    }

    /// <summary>Fan pressure at flow q and speed fraction s (fan laws: Q∝s, P∝s²). Density-corrected from 1.2 kg/m³.</summary>
    public double FanPressure(double q, double s, AirState air)
    {
        if (s <= 0) return 0;
        var f = FanConfig;
        double q0 = Units.Cfm(q) / s; // equivalent full-speed flow, CFM
        double p0 = Interp(f.CurveCfm, f.CurvePa, q0);
        return p0 * s * s * (air.Density / 1.2);
    }

    /// <summary>Max flow the fan can move at speed s against zero pressure.</summary>
    public double FanFreeAir(double s) => Units.FromCfm(FanConfig.CurveCfm.Max() * s);

    /// <summary>Flow the fan moves against a given total pressure rise (inverse of the curve).</summary>
    public double FanFlowAtPressure(double pressurePa, double s, AirState air)
    {
        if (s <= 0) return 0;
        return Bisect(q => FanPressure(q, s, air) - pressurePa, 0, FanFreeAir(s));
    }

    /// <summary>Operating flow where the fan curve meets the system curve.</summary>
    public double OperatingFlow(int level, AirState air, double resistanceScale = 1.0)
    {
        double s = SpeedFraction(level);
        if (s <= 0) return 0;
        return Bisect(q => FanPressure(q, s, air) - resistanceScale * TotalLoss(q, air), 0, FanFreeAir(s));
    }

    // ---------- taps ----------

    /// <summary>
    /// Static gauge pressure (relative to the room) at a tap, Pa. Tap syntax: "room", "after:id", "before:id".
    /// Upstream of the fan this is negative (suction).
    /// </summary>
    public double TapStatic(string tap, double q, AirState air)
    {
        if (string.IsNullOrWhiteSpace(tap) || tap.Equals("room", StringComparison.OrdinalIgnoreCase)) return 0;
        if (tap.StartsWith("bin:", StringComparison.OrdinalIgnoreCase))
        {
            // Dust-bin pressure: somewhere between cyclone inlet and outlet static (BinFraction, calibrated by baseline).
            string id = tap[4..];
            var cyc = Elements.FirstOrDefault(e => e.Id == id) ?? throw new ArgumentException($"Tap '{tap}' references unknown element.");
            double inlet = TapStatic("before:" + id, q, air);
            return inlet - (cyc.Cyclone?.BinFraction ?? 0.5) * ElementLoss(cyc, q, air);
        }
        if (tap.StartsWith("inside:", StringComparison.OrdinalIgnoreCase))
        {
            // A still-air plenum (e.g. the laser enclosure) just downstream of an element: no velocity-pressure term.
            int idx = Config.Elements.FindIndex(e => e.Id == tap[7..]);
            if (idx < 0) throw new ArgumentException($"Tap '{tap}' references unknown element.");
            double loss = 0;
            for (int i = 0; i <= idx; i++) loss += ElementLoss(Elements[i], q, air);
            return -loss;
        }
        var (index, after) = ParseTap(tap);
        int fanIndex = Config.Elements.FindIndex(e => e.Type == ElementType.Fan);
        // Boundary index b: the point between element b-1 and element b.
        int b = after ? index + 1 : index;
        var el = Elements[Math.Min(index, Elements.Count - 1)];
        // Taps are drilled in the connecting duct, so use the element's duct diameter (not a cyclone throat).
        double vp = air.VelocityPressure(DuctVelocity(el, q));
        if (fanIndex < 0 || b <= fanIndex)
        {
            double lossUpstream = 0;
            for (int i = 0; i < b; i++) lossUpstream += ElementLoss(Elements[i], q, air);
            return -lossUpstream - vp;
        }
        double lossDownstream = 0;
        for (int i = b; i < Elements.Count; i++) lossDownstream += ElementLoss(Elements[i], q, air);
        return lossDownstream - vp;
    }

    public (int index, bool after) ParseTap(string tap)
    {
        var parts = tap.Split(':', 2);
        if (parts.Length != 2) throw new ArgumentException($"Bad tap '{tap}'. Use room, before:<id> or after:<id>.");
        bool after = parts[0].Equals("after", StringComparison.OrdinalIgnoreCase);
        if (!after && !parts[0].Equals("before", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException($"Bad tap '{tap}'.");
        int idx = Config.Elements.FindIndex(e => e.Id == parts[1]);
        if (idx < 0) throw new ArgumentException($"Tap '{tap}' references unknown element.");
        return (idx, after);
    }

    /// <summary>What a channel should read in a healthy system at flow q. Sign convention: suctions reported positive.</summary>
    public double PredictReading(ChannelConfig ch, double q, AirState air)
    {
        switch (ch.Role)
        {
            case ChannelRole.PitotVp:
            {
                var el = Elements.FirstOrDefault(e => e.Id == ch.PitotElementId) ?? Elements[0];
                double vMean = DuctVelocity(el, q);
                double vCenter = vMean / Math.Max(0.5, ch.ProfileFactor);
                return air.VelocityPressure(vCenter);
            }
            case ChannelRole.BinSuction:
            case ChannelRole.RunStartSuction:
            case ChannelRole.FanInletSuction:
            case ChannelRole.EnclosureSuction:
                // Sensor + port on room, − port on the duct => reads positive suction.
                return TapStatic(ch.HighTap, q, air) - TapStatic(ch.LowTap, q, air);
            default:
                return TapStatic(ch.HighTap, q, air) - TapStatic(ch.LowTap, q, air);
        }
    }

    /// <summary>Invert a (monotonic) channel prediction to get the flow that explains a reading.</summary>
    public double FlowFromReading(ChannelConfig ch, double reading, AirState air, double correction = 1.0)
    {
        double qMax = FanFreeAir(1.0) * 1.5;
        double top = correction * PredictReading(ch, qMax, air);
        if (Math.Abs(top) < 1e-9) return double.NaN;
        if (reading / top <= 0) return 0;
        if (Math.Abs(reading) >= Math.Abs(top)) return qMax;
        return Bisect(q => Math.Abs(reading) - Math.Abs(correction * PredictReading(ch, q, air)), 0, qMax);
    }

    /// <summary>Flow directly from pitot velocity pressure (no model needed).</summary>
    public double FlowFromPitot(ChannelConfig ch, double vpPa, AirState air)
    {
        var el = Elements.FirstOrDefault(e => e.Id == ch.PitotElementId) ?? Elements[0];
        double vCenter = air.VelocityFromPressure(vpPa);
        return vCenter * ch.ProfileFactor * Units.CircleArea(Units.FromInches(el.DiameterIn));
    }

    // ---------- cyclone ----------

    /// <summary>Lapple 50 % cut diameter, metres.</summary>
    public static double CycloneCutSize(CycloneConfig c, double q, double particleDensity, AirState air)
    {
        double vi = q / CycloneInletArea(c);
        if (vi <= 0) return double.PositiveInfinity;
        double b = Units.FromInches(c.RoundInlet ? c.InletWidthIn * Math.Sqrt(Math.PI) / 2 : c.InletWidthIn);
        double dRho = particleDensity - air.Density;
        return Math.Sqrt(9 * air.Viscosity * b / (2 * Math.PI * c.Turns * vi * dRho));
    }

    /// <summary>Lapple fractional efficiency for particle diameter dp.</summary>
    public static double CycloneEfficiency(double dp, double d50) =>
        double.IsInfinity(d50) ? 0 : 1.0 / (1.0 + Math.Pow(d50 / dp, 2));

    /// <summary>Lowest fan level whose operating point meets <paramref name="minVelocity"/> in every element of the zone.</summary>
    public int? LevelForVelocity(Zone zone, double minVelocityMs, AirState air, double resistanceScale = 1.0)
    {
        for (int lvl = 1; lvl <= FanConfig.Levels; lvl++)
        {
            double q = OperatingFlow(lvl, air, resistanceScale);
            if (MinVelocityInZone(zone, q) >= minVelocityMs) return lvl;
        }
        return null;
    }

    public double MinVelocityInZone(Zone zone, double q)
    {
        // Only real duct runs matter for settling; adapters and outlets are too short to collect debris.
        var els = Elements.Where(e => e.Zone == zone && e.Type == ElementType.Duct).ToList();
        return els.Count == 0 ? double.PositiveInfinity : els.Min(e => DuctVelocity(e, q));
    }

    // ---------- helpers ----------

    public static double Interp(double[] xs, double[] ys, double x)
    {
        if (xs.Length == 0) return 0;
        if (x <= xs[0]) return ys[0];
        for (int i = 1; i < xs.Length; i++)
            if (x <= xs[i])
            {
                double t = (x - xs[i - 1]) / (xs[i] - xs[i - 1]);
                return ys[i - 1] + t * (ys[i] - ys[i - 1]);
            }
        return Math.Max(0, ys[^1]); // beyond free-air: no pressure
    }

    /// <summary>Root of a function that is positive at lo and negative at hi (or returns the closer end).</summary>
    public static double Bisect(Func<double, double> f, double lo, double hi, int iterations = 80)
    {
        double flo = f(lo), fhi = f(hi);
        if (flo <= 0) return lo;
        if (fhi >= 0) return hi;
        for (int i = 0; i < iterations; i++)
        {
            double mid = 0.5 * (lo + hi);
            if (f(mid) > 0) lo = mid; else hi = mid;
        }
        return 0.5 * (lo + hi);
    }
}
