using System.ComponentModel;
using System.Globalization;
using System.Windows;
using System.Windows.Data;
using LumosAir.Desktop.ViewModels;

namespace LumosAir.Desktop
{
    public partial class MainWindow : Window
    {
        private readonly MainViewModel _vm;

        public MainWindow()
        {
            InitializeComponent();
            _vm = new MainViewModel();
            DataContext = _vm;
            Trend.Data = () => _vm.History.Select(h => (h.t, h.cfm, h.cycFpm)).ToList();
            _vm.HistoryUpdated += Trend.InvalidateVisual;

            var args = Environment.GetCommandLineArgs();
            int i = Array.IndexOf(args, "--selftest");
            if (i >= 0 && i + 1 < args.Length) Loaded += async (_, _) => await SelfTestAsync(args[i + 1]);
        }

        /// <summary>
        /// Headless smoke test / documentation screenshots:
        /// LumosAir.exe --selftest out.png [--scenario healthy|clog|pitot|slow|outlet]
        /// Simulator → baseline → inject the scenario's fault → save a screenshot → exit.
        /// </summary>
        private async Task SelfTestAsync(string pngPath)
        {
            var args = Environment.GetCommandLineArgs();
            int si = Array.IndexOf(args, "--scenario");
            string scenario = si >= 0 && si + 1 < args.Length ? args[si + 1] : "clog";
            Trend.Window = TimeSpan.FromSeconds(30);
            _vm.SourceKind = SourceKind.Simulator;
            _vm.ConnectCommand.Execute(null);
            await Task.Delay(9000);
            _vm.CaptureBaselineCommand.Execute(null);
            await Task.Delay(2000);
            switch (scenario)
            {
                case "clog": _vm.SimRun = 2.0; _vm.SimBin = 0.6; break;
                case "pitot": _vm.SimPitot = 0.6; break;
                case "slow": _vm.ManualFanLevel = 4; break;
                case "outlet": _vm.SimOutlet = 15; break;
            }
            await Task.Delay(scenario == "healthy" ? 8000 : 12000);
            UpdateLayout();
            var dpi = System.Windows.Media.VisualTreeHelper.GetDpi(this);
            var root = (FrameworkElement)Content;
            var bmp = new System.Windows.Media.Imaging.RenderTargetBitmap(
                (int)(root.ActualWidth * dpi.DpiScaleX), (int)(root.ActualHeight * dpi.DpiScaleY),
                dpi.PixelsPerInchX, dpi.PixelsPerInchY, System.Windows.Media.PixelFormats.Pbgra32);
            bmp.Render(root);
            var enc = new System.Windows.Media.Imaging.PngBitmapEncoder();
            enc.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(bmp));
            using (var fs = System.IO.File.Create(pngPath)) enc.Save(fs);
            Application.Current.Shutdown();
        }

        protected override async void OnClosing(CancelEventArgs e)
        {
            base.OnClosing(e);
            await _vm.DisposeAsync();
        }
    }
}

namespace LumosAir.Desktop.Controls
{
    /// <summary>Boolean negation for bindings.</summary>
    public sealed class Not : IValueConverter
    {
        public static readonly Not Instance = new();
        public object Convert(object value, Type targetType, object parameter, CultureInfo culture) => value is bool b ? !b : value;
        public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) => value is bool b ? !b : value;
    }
}
