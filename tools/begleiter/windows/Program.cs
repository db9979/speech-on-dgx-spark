namespace SparkBegleiter;

internal static class Program
{
    /// <summary>Name des Mutex, der eine zweite Instanz in derselben Windows-Sitzung verhindert.</summary>
    private const string MutexName = @"Local\SparkBegleiter.SingleInstance";

    [STAThread]
    private static int Main(string[] args)
    {
        // Als neue Version gestartet, um die alte zu ersetzen (siehe Updater): ohne Oberfläche, ohne Mutex.
        if (args.Length > 0 && args[0] == UpdateInstaller.InstallArgument)
        {
            return UpdateInstaller.Run(args);
        }

        string? startup = args.FirstOrDefault(a => a is UpdateInstaller.UpdatedArgument or UpdateInstaller.FailedArgument);

        using var mutex = new Mutex(initiallyOwned: false, MutexName);
        bool owned;
        try
        {
            // Nach einem Update kann die alte Instanz noch kurz laufen – dann etwas warten.
            owned = mutex.WaitOne(startup is null ? TimeSpan.Zero : TimeSpan.FromSeconds(15));
        }
        catch (AbandonedMutexException)
        {
            owned = true; // vorherige Instanz ohne Aufräumen beendet
        }

        if (!owned)
        {
            MessageBox.Show(
                "Der Spark-Begleiter läuft bereits – das Symbol ist im Infobereich der Taskleiste.",
                TrayContext.Title, MessageBoxButtons.OK, MessageBoxIcon.Information);
            return 0;
        }

        try
        {
            Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            using var context = new TrayContext(startup);
            Application.Run(context);
        }
        finally
        {
            mutex.ReleaseMutex();
        }

        return 0;
    }
}
