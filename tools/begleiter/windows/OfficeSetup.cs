using System.Diagnostics;
using System.Reflection;
using Microsoft.Win32;

namespace SparkBegleiter;

/// <summary>
/// Teil "office": richtet die Knöpfe des Spark in Office ein, nur für das eigene Konto (HKCU), ohne Administratorrechte.
/// <list type="bullet">
/// <item>Outlook classic: das mitgebrachte COM-Add-in (tools/begleiter/outlook-classic) nach
/// %LOCALAPPDATA%\SparkBegleiter\Office legen und eintragen. Es schickt nur ein festes Wort an den Begleiter.</item>
/// <item>Word und Excel: das Manifest des Office-Add-ins vom Spark holen und unter WEF\Developer eintragen.</item>
/// <item>Neues Outlook und Outlook im Web: Datei holen, im Explorer zeigen und die Seite „Aus Datei hinzufügen“
/// öffnen – das letzte Hinzufügen macht die Person selbst (Microsoft lässt es nicht anders zu).</item>
/// </list>
/// Teil aus oder "Entfernen": alles wieder austragen.
/// </summary>
internal static class OfficeSetup
{
    public const string Clsid = "{6F4E0B57-2C61-4B8A-9C3E-5A7D1E2F9B40}";
    public const string ProgId = "SparkBegleiter.OutlookAddin";
    private const string AddinName = "SparkOutlook";
    private const string AddinClass = "SparkOutlook.Connect";
    private const string Resource = "SparkBegleiter.SparkOutlook.dll";
    private const string OutlookAddins = @"Software\Microsoft\Office\Outlook\Addins\" + ProgId;
    private const string Wef = @"Software\Microsoft\Office\16.0\WEF\Developer";
    private const string Resiliency = @"Software\Microsoft\Office\16.0\Outlook\Resiliency";
    private const string WefPrefix = "SparkSchreibhilfe";
    public const string SideloadPage = "https://aka.ms/olksideload";

    /// <summary>Word und Excel: Name im Spark (/api/desk/office/&lt;app&gt;.xml) → Name des Eintrags.</summary>
    public static readonly (string App, string Value)[] WebApps = { ("word", WefPrefix + "Word"), ("excel", WefPrefix + "Excel") };

    public static string Folder => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "SparkBegleiter", "Office");

    /// <summary>Die DLL für Outlook classic ist in dieser Version enthalten (beim Bauen auf GitHub immer).</summary>
    public static bool HasClassic => typeof(OfficeSetup).Assembly.GetManifestResourceInfo(Resource) is not null;

    public static bool ClassicInstalled()
    {
        using RegistryKey? key = Registry.CurrentUser.OpenSubKey(OutlookAddins);
        return key is not null;
    }

    public static bool WebInstalled()
    {
        using RegistryKey? key = Registry.CurrentUser.OpenSubKey(Wef);
        return key is not null && key.GetValueNames().Any(n => n.StartsWith(WefPrefix, StringComparison.Ordinal));
    }

    /// <summary>Outlook classic: DLL ablegen und als Add-in eintragen (32 und 64 Bit). Wirkt beim nächsten Start von Outlook.</summary>
    public static void InstallClassic()
    {
        using Stream source = typeof(OfficeSetup).Assembly.GetManifestResourceStream(Resource)
            ?? throw new InvalidOperationException("Diese Version bringt das Outlook-Add-in nicht mit.");
        Directory.CreateDirectory(Folder);
        string dll = Path.Combine(Folder, AddinName + ".dll");
        byte[] data = new byte[source.Length];
        source.ReadExactly(data);
        if (!File.Exists(dll) || !File.ReadAllBytes(dll).AsSpan().SequenceEqual(data))
        {
            try
            {
                File.WriteAllBytes(dll, data);
            }
            catch (IOException)
            {
                throw new InvalidOperationException("Outlook benutzt das Add-in gerade. Outlook schließen und noch einmal versuchen.");
            }
        }

        string codeBase = new Uri(dll).AbsoluteUri;
        string assembly = AddinName + ", Version=1.0.0.0, Culture=neutral, PublicKeyToken=null";
        foreach (RegistryView view in new[] { RegistryView.Registry64, RegistryView.Registry32 })
        {
            using RegistryKey root = RegistryKey.OpenBaseKey(RegistryHive.CurrentUser, view);
            using (RegistryKey prog = root.CreateSubKey(@"Software\Classes\" + ProgId))
            {
                prog.SetValue("", "Spark");
                using RegistryKey cls = prog.CreateSubKey("CLSID");
                cls.SetValue("", Clsid);
            }

            using RegistryKey clsid = root.CreateSubKey(@"Software\Classes\CLSID\" + Clsid);
            clsid.SetValue("", AddinClass);
            using (RegistryKey p = clsid.CreateSubKey("ProgId"))
            {
                p.SetValue("", ProgId);
            }

            using (RegistryKey cat = clsid.CreateSubKey(@"Implemented Categories\{62C8FE65-4EBB-45e7-B440-6E39B2CDBF29}"))
            {
                // .NET-Komponente
            }

            using RegistryKey inproc = clsid.CreateSubKey("InprocServer32");
            foreach (RegistryKey k in new[] { inproc, inproc.CreateSubKey("1.0.0.0") })
            {
                k.SetValue("", "mscoree.dll");
                k.SetValue("ThreadingModel", "Both");
                k.SetValue("Class", AddinClass);
                k.SetValue("Assembly", assembly);
                k.SetValue("RuntimeVersion", "v4.0.30319");
                k.SetValue("CodeBase", codeBase);
            }
        }

        ForgetOutlookBlock();
        using RegistryKey addin = Registry.CurrentUser.CreateSubKey(OutlookAddins);
        addin.SetValue("FriendlyName", "Spark");
        addin.SetValue("Description", "Knopf „Spark“: verbessern, Antwort entwerfen, übersetzen (über den Spark-Begleiter)");
        addin.SetValue("LoadBehavior", 3, RegistryValueKind.DWord);
    }

    /// <summary>
    /// Hat Outlook das Spark-Add-in einmal gesperrt (nach einem Hänger oder Absturz, „Deaktivierte Elemente“), bleibt
    /// es aus, auch wenn man das Häkchen setzt. Beim Einrichten nur die Sperren für Spark aufheben, andere Add-ins nicht.
    /// </summary>
    internal static void ForgetOutlookBlock()
    {
        using RegistryKey? res = Registry.CurrentUser.OpenSubKey(Resiliency, writable: true);
        if (res is null)
        {
            return;
        }

        using (RegistryKey? crashing = res.OpenSubKey("CrashingAddinList", writable: true))
        {
            crashing?.DeleteValue(ProgId, throwOnMissingValue: false);
        }

        using RegistryKey? disabled = res.OpenSubKey("DisabledItems", writable: true);
        if (disabled is null)
        {
            return;
        }

        foreach (string name in disabled.GetValueNames())
        {
            if (disabled.GetValue(name) is byte[] data && IsOurs(data))
            {
                disabled.DeleteValue(name, throwOnMissingValue: false);
            }
        }
    }

    /// <summary>Ein Eintrag unter DisabledItems nennt Pfad oder ProgId des Add-ins in UTF-16.</summary>
    internal static bool IsOurs(byte[] data)
    {
        string text = System.Text.Encoding.Unicode.GetString(data);
        return text.Contains(AddinName + ".dll", StringComparison.OrdinalIgnoreCase)
            || text.Contains(ProgId, StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>Word und Excel: die Manifeste ablegen und eintragen (wirkt beim nächsten Start).</summary>
    public static void InstallWeb(IReadOnlyDictionary<string, byte[]> manifests)
    {
        Directory.CreateDirectory(Folder);
        using RegistryKey wef = Registry.CurrentUser.CreateSubKey(Wef);
        foreach ((string app, string value) in WebApps)
        {
            if (manifests.TryGetValue(app, out byte[]? xml))
            {
                string path = Path.Combine(Folder, $"spark-{app}.xml");
                File.WriteAllBytes(path, xml);
                wef.SetValue(value, path);
            }
        }
    }

    /// <summary>Neues Outlook: Datei ablegen, im Explorer zeigen und die Seite zum Hinzufügen öffnen.</summary>
    public static void OfferOutlook(byte[] manifest)
    {
        Directory.CreateDirectory(Folder);
        string path = Path.Combine(Folder, "spark-outlook.xml");
        File.WriteAllBytes(path, manifest);
        Process.Start(new ProcessStartInfo("explorer.exe") { ArgumentList = { "/select,", path }, UseShellExecute = false });
        Process.Start(new ProcessStartInfo(SideloadPage) { UseShellExecute = true });
    }

    /// <summary>Alles austragen (Teil aus, "--entfernen"); Dateien, die Outlook gerade hält, bleiben liegen.</summary>
    public static void Uninstall()
    {
        try
        {
            Registry.CurrentUser.DeleteSubKeyTree(OutlookAddins, throwOnMissingSubKey: false);
            foreach (RegistryView view in new[] { RegistryView.Registry64, RegistryView.Registry32 })
            {
                using RegistryKey root = RegistryKey.OpenBaseKey(RegistryHive.CurrentUser, view);
                root.DeleteSubKeyTree(@"Software\Classes\CLSID\" + Clsid, throwOnMissingSubKey: false);
                root.DeleteSubKeyTree(@"Software\Classes\" + ProgId, throwOnMissingSubKey: false);
            }

            using (RegistryKey? wef = Registry.CurrentUser.OpenSubKey(Wef, writable: true))
            {
                foreach (string name in wef?.GetValueNames().Where(n => n.StartsWith(WefPrefix, StringComparison.Ordinal)).ToArray() ?? Array.Empty<string>())
                {
                    wef!.DeleteValue(name, throwOnMissingValue: false);
                }
            }
        }
        catch (Exception ex) when (ex is UnauthorizedAccessException or System.Security.SecurityException or IOException)
        {
            // nichts eingetragen oder nicht änderbar
        }

        try
        {
            if (Directory.Exists(Folder))
            {
                foreach (string f in Directory.GetFiles(Folder))
                {
                    try
                    {
                        File.Delete(f);
                    }
                    catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
                    {
                        // Outlook hält die DLL noch: beim nächsten Mal
                    }
                }
            }
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            // egal
        }
    }
}
