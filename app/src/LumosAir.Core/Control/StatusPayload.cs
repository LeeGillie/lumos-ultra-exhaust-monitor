using System.Text.Encodings.Web;
using System.Text.Json;
using LumosAir.Core.Diagnostics;

namespace LumosAir.Core.Control;

/// <summary>
/// The small broadcast that drives the box displays (UDP 47812, or MQTT
/// <c>lumosair/system/status</c>). The nodes measure pressures; only the PC knows
/// the system-level answer, so it sends that back for the screens to show.
/// </summary>
public static class StatusPayload
{
    private static readonly JsonSerializerOptions Options = new()
    {
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    public static string Build(DiagnosticSnapshot snap, FanMode mode, int fanLevel,
                              string? controlNote = null)
    {
        var worst = snap.Findings.Count == 0 ? null : snap.Findings[0];
        var payload = new Dictionary<string, object?>
        {
            ["t"] = "status",
            ["cfm"] = Finite(snap.FlowCfm, 1),
            ["src"] = snap.FlowSource,
            ["sev"] = snap.Overall.ToString().ToLowerInvariant(),
            ["fan"] = new Dictionary<string, object?>
            {
                ["level"] = fanLevel,
                ["mode"] = mode == FanMode.Auto ? "auto" : "manual",
                ["rec"] = snap.RecommendedLevel,
            },
            ["msg"] = Headline(worst, controlNote),
        };
        if (Finite(snap.CycloneInletFpm, 0) is { } fpm) payload["cyc_fpm"] = fpm;
        if (Finite(snap.CutSizeMicron, 1) is { } d50) payload["d50"] = d50;
        return JsonSerializer.Serialize(payload, Options);
    }

    /// <summary>
    /// Rounded value, or null when it isn't a real number.
    /// <see cref="Model.SystemModel.CycloneCutSize"/> returns +infinity on purpose when
    /// the inlet velocity is zero — no flow, no separation — and a flow solved from
    /// inconsistent readings can land on NaN. Both are fine inside the model and fatal
    /// here: System.Text.Json throws on them, and the nodes' json module would not
    /// parse "Infinity" either. Null is what the box display already renders as "---".
    /// </summary>
    private static double? Finite(double? v, int digits) =>
        v is { } d && double.IsFinite(d) ? Math.Round(d, digits) : null;

    private static string Headline(Finding? worst, string? controlNote)
    {
        if (worst is not null) return Shorten(worst.Title, 38);
        return string.IsNullOrEmpty(controlNote) ? "All good" : Shorten(controlNote!, 38);
    }

    private static string Shorten(string s, int max) =>
        s.Length <= max ? s : s[..(max - 1)] + "…";
}
