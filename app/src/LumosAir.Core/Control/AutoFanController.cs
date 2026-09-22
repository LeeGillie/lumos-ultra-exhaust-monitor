using LumosAir.Core.Config;
using LumosAir.Core.Diagnostics;

namespace LumosAir.Core.Control;

public enum FanMode { Manual, Auto }

/// <summary>What the controller decided, and why — the UI shows the reason verbatim.</summary>
public sealed record FanDecision(int? TargetLevel, string Reason, bool Urgent = false);

/// <summary>
/// Turns the diagnostics engine's "recommended level" into an actual set-point.
///
/// Raising speed is treated as a safety action and happens immediately; lowering
/// has to be justified for a while first, so the fan doesn't hunt up and down
/// while a job's smoke load varies. A critical finding pins the fan at maximum.
/// </summary>
public sealed class AutoFanController
{
    private readonly FanControlConfig _cfg;
    private DateTimeOffset _lastChange = DateTimeOffset.MinValue;
    private DateTimeOffset _lowerSince = DateTimeOffset.MinValue;
    private int? _lastSent;

    public AutoFanController(FanControlConfig cfg) => _cfg = cfg;

    public int? LastSentLevel => _lastSent;

    public void Reset()
    {
        _lastSent = null;
        _lastChange = DateTimeOffset.MinValue;
        _lowerSince = DateTimeOffset.MinValue;
    }

    /// <summary>Returns the level to send, or null to leave the fan alone.</summary>
    public FanDecision Evaluate(DiagnosticSnapshot snap, int currentLevel, DateTimeOffset now)
    {
        if (!_cfg.Enabled) return new FanDecision(null, "automatic control is off");

        int min = Math.Max(0, _cfg.MinLevel);
        int max = Math.Max(min, _cfg.MaxLevel);

        // A critical finding (clogged run, no capture, fan can't reach transport speed)
        // is not the moment to be economical.
        if (snap.Findings.Any(f => f.Severity == Severity.Critical))
        {
            if (currentLevel >= max) return new FanDecision(null, "already at maximum for a critical finding");
            return Send(max, now, "critical finding — running at maximum", urgent: true);
        }

        if (snap.RecommendedLevel is not { } rec)
            return new FanDecision(null, "no recommendation yet");

        int target = Math.Clamp(rec, min, max);

        if (target > currentLevel)
        {
            _lowerSince = DateTimeOffset.MinValue;
            return Send(target, now, $"needs level {target} for the current material", urgent: true);
        }

        if (target < currentLevel)
        {
            // Only step down once the lower recommendation has held for the dwell time,
            // and only when it is comfortably below the current level.
            if (currentLevel - target < _cfg.MinStepDown)
                return new FanDecision(null, $"level {currentLevel} is only slightly high — holding");
            if (_lowerSince == DateTimeOffset.MinValue)
            {
                _lowerSince = now;
                return new FanDecision(null, $"could drop to {target}; confirming");
            }
            if ((now - _lowerSince).TotalSeconds < _cfg.DwellSeconds)
                return new FanDecision(null,
                    $"could drop to {target} in {_cfg.DwellSeconds - (int)(now - _lowerSince).TotalSeconds}s");
            return Send(target, now, $"steady below level {currentLevel} — easing back to {target}");
        }

        _lowerSince = DateTimeOffset.MinValue;
        return new FanDecision(null, $"level {currentLevel} is right");
    }

    private FanDecision Send(int level, DateTimeOffset now, string reason, bool urgent = false)
    {
        if (_lastSent == level && (now - _lastChange).TotalSeconds < _cfg.RepeatSeconds)
            return new FanDecision(null, reason);
        _lastSent = level;
        _lastChange = now;
        _lowerSince = DateTimeOffset.MinValue;
        return new FanDecision(level, reason, urgent);
    }
}
