namespace LumosAir.Core.Config;

/// <summary>Ready-made descriptions of Lee's exhaust path. Edit the generated system.json to match reality.</summary>
public static class DefaultSystems
{
    public static List<MaterialProfile> Profiles() => new()
    {
        new MaterialProfile
        {
            Id = "metal", Name = "Metal – fiber (brass, steel, aluminium)",
            ParticleDensity = 8500, TargetCutSizeMicron = 5, MinPreSeparatorFpm = 3500, MinPostSeparatorFpm = 500, MinEnclosureSuctionPa = 3
        },
        new MaterialProfile
        {
            Id = "organic", Name = "Organic – UV (wood, leather, acrylic, paper)",
            ParticleDensity = 1000, TargetCutSizeMicron = 10, MinPreSeparatorFpm = 2000, MinPostSeparatorFpm = 500, MinEnclosureSuctionPa = 3
        },
        new MaterialProfile
        {
            Id = "coated", Name = "Coated metal / anodized / painted",
            ParticleDensity = 2700, TargetCutSizeMicron = 7, MinPreSeparatorFpm = 3000, MinPostSeparatorFpm = 500, MinEnclosureSuctionPa = 3
        }
    };

    private static List<ElementConfig> Front() => new()
    {
        new() { Id = "enclosure", Name = "Lumos Ultra enclosure (air inlets)", Type = ElementType.Source, Zone = Zone.PreSeparator,
                DiameterIn = 6, KSum = 2.5 },
        new() { Id = "outlet3", Name = "Lumos 3\" exhaust outlet", Type = ElementType.Fitting, Zone = Zone.PreSeparator,
                DiameterIn = 3, KSum = 0.5 },
        new() { Id = "adapt34", Name = "3\"→4\" adapter", Type = ElementType.Fitting, Zone = Zone.PreSeparator,
                DiameterIn = 3, KSum = 0.3 },
        new() { Id = "cyclone", Name = "Cyclone separator", Type = ElementType.Cyclone, Zone = Zone.Separator,
                DiameterIn = 4, Cyclone = new CycloneConfig() },
    };

    private static List<ElementConfig> Back() => new()
    {
        new() { Id = "run6", Name = "6\" flex run (30 ft)", Type = ElementType.Duct, Zone = Zone.PostSeparator,
                DiameterIn = 6, LengthFt = 30, Flex = true, FlexFactor = 2.5, KSum = 2.0 },
        new() { Id = "fan", Name = "CLOUDLINE S6", Type = ElementType.Fan, Zone = Zone.PostSeparator,
                DiameterIn = 6, Fan = new FanConfig() },
        new() { Id = "out6", Name = "6\" to wall (1 ft)", Type = ElementType.Duct, Zone = Zone.PostSeparator,
                DiameterIn = 6, LengthFt = 1, Flex = true },
        new() { Id = "exit", Name = "Wall cap / damper", Type = ElementType.Exit, Zone = Zone.PostSeparator,
                DiameterIn = 6, KSum = 2.0 },
    };

    /// <summary>Option A: cyclone at the laser, then 5 ft of smooth 4" (pitot here), then 4"→6".</summary>
    public static SystemConfig OptionA()
    {
        var els = Front();
        els.Add(new() { Id = "duct4", Name = "4\" smooth pipe (5 ft, pitot)", Type = ElementType.Duct, Zone = Zone.PostSeparator,
                        DiameterIn = 4, LengthFt = 5, KSum = 0 });
        els.Add(new() { Id = "adapt46", Name = "4\"→6\" adapter", Type = ElementType.Fitting, Zone = Zone.PostSeparator,
                        DiameterIn = 4, KSum = 0.25 });
        els.AddRange(Back());
        return Build("Lumos Ultra exhaust – Option A (4\" section)", els, pitotIn: "duct4", runStartTap: "before:run6");
    }

    /// <summary>Option B: cyclone at the laser, straight into a 5 ft smooth 6" measuring section, then the flex run.</summary>
    public static SystemConfig OptionB()
    {
        var els = Front();
        els.Add(new() { Id = "adapt46", Name = "Cyclone outlet 4\"→6\"", Type = ElementType.Fitting, Zone = Zone.PostSeparator,
                        DiameterIn = 4, KSum = 0.25 });
        els.Add(new() { Id = "duct6", Name = "6\" smooth pipe (5 ft, pitot)", Type = ElementType.Duct, Zone = Zone.PostSeparator,
                        DiameterIn = 6, LengthFt = 5 });
        els.AddRange(Back());
        return Build("Lumos Ultra exhaust – Option B (straight to 6\")", els, pitotIn: "duct6", runStartTap: "before:run6");
    }

    private static SystemConfig Build(string name, List<ElementConfig> els, string pitotIn, string runStartTap) => new()
    {
        Name = name,
        Profiles = Profiles(),
        ActiveProfileId = "metal",
        Elements = els,
        Channels = new()
        {
            new() { Node = "laser", Channel = "cyc_dp", Label = "Cyclone ΔP", Role = ChannelRole.CycloneDp,
                    HighTap = "before:cyclone", LowTap = "after:cyclone" },
            new() { Node = "laser", Channel = "bin", Label = "Dust-bin suction", Role = ChannelRole.BinSuction,
                    HighTap = "room", LowTap = "bin:cyclone" , FullScalePa = 1000 },
            new() { Node = "laser", Channel = "pitot", Label = "Pitot velocity pressure", Role = ChannelRole.PitotVp,
                    PitotElementId = pitotIn, ProfileFactor = 0.9 },
            new() { Node = "laser", Channel = "run_in", Label = "Run-start suction", Role = ChannelRole.RunStartSuction,
                    HighTap = "room", LowTap = runStartTap , FullScalePa = 1000 },
            new() { Node = "laser", Channel = "encl", Label = "Enclosure suction", Role = ChannelRole.EnclosureSuction,
                    HighTap = "room", LowTap = "inside:enclosure" },
            new() { Node = "fan", Channel = "fan_in", Label = "Fan-inlet suction", Role = ChannelRole.FanInletSuction,
                    HighTap = "room", LowTap = "before:fan" , FullScalePa = 1000 },
        }
    };
}
