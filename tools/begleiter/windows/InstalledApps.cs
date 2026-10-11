namespace SparkBegleiter;

/// <summary>
/// Teil "act": Liste der installierten Programme für das Panel (dort wählt man aus, statt Name und Pfad zu tippen).
/// Gelesen werden nur die Startmenü-Verknüpfungen (*.lnk) aus %ProgramData% und %AppData%
/// (…\Microsoft\Windows\Start Menu\Programs, mit Unterordnern): Name = Dateiname ohne .lnk, Pfad = voller Pfad der
/// Verknüpfung. Deinstallieren-, Hilfe- und Liesmich-Verknüpfungen werden übersprungen. Höchstens 600, nach Namen
/// sortiert, ohne Doppelte.
/// </summary>
internal static class InstalledApps
{
    public const int MaxApps = 600;

    private static readonly string[] Skip =
    {
        "uninstall", "deinstall", "entfernen", "help", "hilfe", "readme", "read me", "liesmich", "lies mich", "documentation", "dokumentation",
    };

    public static List<(string Name, string Path)> Scan()
    {
        var roots = new[]
        {
            Environment.GetFolderPath(Environment.SpecialFolder.CommonStartMenu),
            Environment.GetFolderPath(Environment.SpecialFolder.StartMenu),
        };

        var byName = new Dictionary<string, (string Name, string Path)>(StringComparer.OrdinalIgnoreCase);
        foreach (string root in roots.Where(r => !string.IsNullOrEmpty(r)))
        {
            string programs = Path.Combine(root, "Programs");
            if (!Directory.Exists(programs))
            {
                continue;
            }

            IEnumerable<string> files;
            try
            {
                files = Directory.EnumerateFiles(programs, "*.lnk", new EnumerationOptions
                {
                    RecurseSubdirectories = true,
                    IgnoreInaccessible = true,
                    MaxRecursionDepth = 6,
                    AttributesToSkip = FileAttributes.Hidden | FileAttributes.System,
                }).ToList();
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                continue;
            }

            foreach (string file in files)
            {
                string name = Path.GetFileNameWithoutExtension(file).Trim();
                if (name.Length is 0 or > 40 || file.Length > 300 || Skip.Any(s => name.Contains(s, StringComparison.OrdinalIgnoreCase)))
                {
                    continue;
                }

                byName.TryAdd(name, (name, file));
            }
        }

        return byName.Values.OrderBy(a => a.Name, StringComparer.CurrentCultureIgnoreCase).Take(MaxApps).ToList();
    }
}
