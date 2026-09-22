using System;
using System.Windows;
using System.Windows.Threading;

namespace LumosAir.Desktop;

public partial class App : Application
{
    private static string? _lastMessage;
    private static DateTime _lastShown = DateTime.MinValue;
    private static int _suppressed;

    protected override void OnStartup(StartupEventArgs e)
    {
        DispatcherUnhandledException += OnUnhandled;
        base.OnStartup(e);
    }

    /// <summary>
    /// Show the problem once, not once per tick. Most of this app's work happens on a
    /// timer, so a fault in the update loop used to open a modal every second until the
    /// desktop was full of them — and each one blocks the loop that is producing them.
    /// </summary>
    private static void OnUnhandled(object sender, DispatcherUnhandledExceptionEventArgs e)
    {
        e.Handled = true;
        string message = e.Exception.Message;

        if (message == _lastMessage && (DateTime.Now - _lastShown).TotalMinutes < 5)
        {
            _suppressed++;
            return;
        }

        string text = message;
        if (_suppressed > 0)
            text += $"\n\n({_suppressed} further identical errors were hidden.)";
        _lastMessage = message;
        _lastShown = DateTime.Now;
        _suppressed = 0;

        MessageBox.Show(text, "LumosAir error", MessageBoxButton.OK, MessageBoxImage.Warning);
    }
}
