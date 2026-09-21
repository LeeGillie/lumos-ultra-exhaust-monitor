using System.Globalization;
using System.Windows;
using System.Windows.Media;

namespace LumosAir.Desktop.Controls;

/// <summary>Lightweight two-series trend chart (no external charting library).</summary>
public sealed class TrendChart : FrameworkElement
{
    public Func<IReadOnlyList<(DateTime t, double a, double b)>>? Data { get; set; }
    public string SeriesA { get; set; } = "CFM";
    public string SeriesB { get; set; } = "Cyclone inlet fpm";
    public TimeSpan Window { get; set; } = TimeSpan.FromMinutes(5);

    private static readonly Brush AxisBrush = Frozen(Color.FromRgb(0x8B, 0x95, 0xA1));
    private static readonly Pen GridPen = FrozenPen(Color.FromRgb(0x2C, 0x33, 0x3C), 1);
    private static readonly Pen PenA = FrozenPen(Color.FromRgb(0x4F, 0xA3, 0xE0), 2);
    private static readonly Pen PenB = FrozenPen(Color.FromRgb(0xD8, 0xB4, 0x3A), 1.5);

    protected override void OnRender(DrawingContext dc)
    {
        double w = ActualWidth, h = ActualHeight;
        if (w < 80 || h < 60) return;
        const double left = 44, right = 56, top = 22, bottom = 20;
        var plot = new Rect(left, top, Math.Max(10, w - left - right), Math.Max(10, h - top - bottom));
        dc.DrawRectangle(Brushes.Transparent, null, new Rect(0, 0, w, h));

        var all = Data?.Invoke() ?? Array.Empty<(DateTime, double, double)>();
        var now = DateTime.Now;
        var start = now - Window;
        var pts = all.Where(p => p.t >= start).ToList();

        double maxA = NiceMax(pts.Count == 0 ? 100 : pts.Max(p => p.a));
        // Series B (cyclone inlet) is absent in systems with no separator — hide it rather than drawing a flat zero.
        bool hasB = pts.Any(p => p.b > 0);
        double maxB = NiceMax(!hasB || pts.Count == 0 ? 2000 : pts.Max(p => p.b));

        for (int i = 0; i <= 4; i++)
        {
            double y = plot.Bottom - plot.Height * i / 4;
            dc.DrawLine(GridPen, new Point(plot.Left, y), new Point(plot.Right, y));
            Text(dc, (maxA * i / 4).ToString("0"), new Point(plot.Left - 6, y - 7), PenA.Brush, TextAlignment.Right);
            if (hasB) Text(dc, (maxB * i / 4).ToString("0"), new Point(plot.Right + 6, y - 7), PenB.Brush, TextAlignment.Left);
        }
        Text(dc, SeriesA, new Point(plot.Left, 2), PenA.Brush, TextAlignment.Left);
        if (hasB) Text(dc, SeriesB, new Point(plot.Right, 2), PenB.Brush, TextAlignment.Right);
        Text(dc, Window.TotalMinutes >= 1 ? $"−{Window.TotalMinutes:0} min" : $"−{Window.TotalSeconds:0} s", new Point(plot.Left, plot.Bottom + 3), AxisBrush, TextAlignment.Left);
        Text(dc, "now", new Point(plot.Right, plot.Bottom + 3), AxisBrush, TextAlignment.Right);

        if (pts.Count < 2) return;
        Point Map(DateTime t, double v, double max) => new(
            plot.Left + plot.Width * (t - start).TotalSeconds / Window.TotalSeconds,
            plot.Bottom - plot.Height * Math.Clamp(v / max, 0, 1));
        if (hasB) DrawSeries(dc, pts.Select(p => Map(p.t, p.b, maxB)), PenB);
        DrawSeries(dc, pts.Select(p => Map(p.t, p.a, maxA)), PenA);
    }

    private static void DrawSeries(DrawingContext dc, IEnumerable<Point> points, Pen pen)
    {
        var geo = new StreamGeometry();
        using (var ctx = geo.Open())
        {
            bool first = true;
            foreach (var p in points)
            {
                if (first) { ctx.BeginFigure(p, false, false); first = false; }
                else ctx.LineTo(p, true, false);
            }
        }
        geo.Freeze();
        dc.DrawGeometry(null, pen, geo);
    }

    private void Text(DrawingContext dc, string s, Point at, Brush brush, TextAlignment align)
    {
        var ft = new FormattedText(s, CultureInfo.CurrentUICulture, FlowDirection.LeftToRight,
            new Typeface("Segoe UI"), 11, brush, VisualTreeHelper.GetDpi(this).PixelsPerDip)
        { TextAlignment = align };
        dc.DrawText(ft, at);
    }

    private static double NiceMax(double v)
    {
        if (v <= 0) return 1;
        double mag = Math.Pow(10, Math.Floor(Math.Log10(v)));
        foreach (var m in new[] { 1, 2, 2.5, 5, 10 })
            if (m * mag >= v * 1.1) return m * mag;
        return 10 * mag;
    }

    private static Brush Frozen(Color c) { var b = new SolidColorBrush(c); b.Freeze(); return b; }
    private static Pen FrozenPen(Color c, double t) { var p = new Pen(Frozen(c), t); p.Freeze(); return p; }
}
