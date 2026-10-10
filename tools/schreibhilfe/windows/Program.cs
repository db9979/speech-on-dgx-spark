namespace SparkSchreibhilfe;

internal static class Program
{
    /// <summary>Name des Mutex, der eine zweite Instanz in derselben Windows-Sitzung verhindert.</summary>
    private const string MutexName = @"Local\SparkSchreibhilfe.SingleInstance";

    [STAThread]
    private static void Main()
    {
        using var mutex = new Mutex(initiallyOwned: true, MutexName, out bool createdNew);
        if (!createdNew)
        {
            MessageBox.Show(
                "Die Spark Schreibhilfe läuft bereits – das Symbol ist im Infobereich der Taskleiste.",
                "Spark Schreibhilfe", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        using var context = new TrayContext();
        Application.Run(context);

        GC.KeepAlive(mutex);
    }
}
