namespace LumosAir.Core.Model;

/// <summary>Unit conversions. Everything inside the model is SI (m, m/s, m³/s, Pa, kg/m³).</summary>
public static class Units
{
    public const double CfmToM3s = 0.00047194745;
    public const double FpmToMs = 0.00508;
    public const double InWcToPa = 249.08891;
    public const double InchToM = 0.0254;
    public const double FootToM = 0.3048;

    public static double Cfm(double m3s) => m3s / CfmToM3s;
    public static double FromCfm(double cfm) => cfm * CfmToM3s;
    public static double Fpm(double ms) => ms / FpmToMs;
    public static double FromFpm(double fpm) => fpm * FpmToMs;
    public static double InWc(double pa) => pa / InWcToPa;
    public static double FromInWc(double inwc) => inwc * InWcToPa;
    public static double Inches(double m) => m / InchToM;
    public static double FromInches(double inch) => inch * InchToM;
    public static double FromFeet(double ft) => ft * FootToM;

    public static double CircleArea(double diameterM) => Math.PI * diameterM * diameterM / 4.0;
}

/// <summary>Moist-air properties.</summary>
public readonly record struct AirState(double TemperatureC, double RelativeHumidity, double PressurePa)
{
    /// <summary>Spokane-ish default: ~580 m elevation, 20 °C, 40 %RH.</summary>
    public static AirState Default => new(20.0, 40.0, 94_600.0);

    /// <summary>Density of moist air, kg/m³.</summary>
    public double Density
    {
        get
        {
            double tK = TemperatureC + 273.15;
            // Magnus-Tetens saturation vapour pressure, Pa
            double psat = 610.94 * Math.Exp(17.625 * TemperatureC / (TemperatureC + 243.04));
            double pv = Math.Clamp(RelativeHumidity, 0, 100) / 100.0 * psat;
            double pd = PressurePa - pv;
            return pd / (287.058 * tK) + pv / (461.495 * tK);
        }
    }

    /// <summary>Dynamic viscosity (Sutherland), Pa·s.</summary>
    public double Viscosity
    {
        get
        {
            double tK = TemperatureC + 273.15;
            return 1.458e-6 * Math.Pow(tK, 1.5) / (tK + 110.4);
        }
    }

    public double VelocityPressure(double velocityMs) => 0.5 * Density * velocityMs * velocityMs;
    public double VelocityFromPressure(double vpPa) => vpPa <= 0 ? 0 : Math.Sqrt(2 * vpPa / Density);
}
