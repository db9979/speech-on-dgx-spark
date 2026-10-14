using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.IO.Pipes;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

namespace SparkOutlook;

/// <summary>
/// Die Schnittstelle, über die Office ein COM-Add-in lädt (Extensibility, IDTExtensibility2), genau wie in
/// Extensibility.dll deklariert: "custom" ist ein SAFEARRAY von VARIANTs. Ohne diese Angabe macht .NET daraus eine
/// _Array-Schnittstelle, und Outlook blieb beim Laden der Add-ins hängen (V01.0.433 bis 533).
/// </summary>
[ComImport, Guid("B65AD801-ABAF-11D0-BB8B-00A0C90F2744"), InterfaceType(ComInterfaceType.InterfaceIsDual)]
public interface IDTExtensibility2
{
    [DispId(1)]
    void OnConnection([In, MarshalAs(UnmanagedType.IDispatch)] object application, [In] int connectMode,
        [In, MarshalAs(UnmanagedType.IDispatch)] object addInInst,
        [In, MarshalAs(UnmanagedType.SafeArray, SafeArraySubType = VarEnum.VT_VARIANT)] ref Array custom);

    [DispId(2)]
    void OnDisconnection([In] int removeMode,
        [In, MarshalAs(UnmanagedType.SafeArray, SafeArraySubType = VarEnum.VT_VARIANT)] ref Array custom);

    [DispId(3)]
    void OnAddInsUpdate([In, MarshalAs(UnmanagedType.SafeArray, SafeArraySubType = VarEnum.VT_VARIANT)] ref Array custom);

    [DispId(4)]
    void OnStartupComplete([In, MarshalAs(UnmanagedType.SafeArray, SafeArraySubType = VarEnum.VT_VARIANT)] ref Array custom);

    [DispId(5)]
    void OnBeginShutdown([In, MarshalAs(UnmanagedType.SafeArray, SafeArraySubType = VarEnum.VT_VARIANT)] ref Array custom);
}

/// <summary>Die Schnittstelle für eigene Knöpfe im Menüband (Office, IRibbonExtensibility).</summary>
[ComImport, Guid("000C0396-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsDual)]
public interface IRibbonExtensibility
{
    [DispId(1)]
    [return: MarshalAs(UnmanagedType.BStr)]
    string GetCustomUI([In, MarshalAs(UnmanagedType.BStr)] string ribbonId);
}

/// <summary>
/// Das Add-in: eine Gruppe "Spark" im Menüband (Hauptfenster, Lesen, Verfassen). Ein Klick schickt das feste Wort
/// des Knopfs an den Spark-Begleiter; das Add-in liest keine Mails, hat keinen Schlüssel und spricht nie mit dem Spark.
/// </summary>
[ComVisible(true)]
[Guid(Ids.Clsid)]
[ProgId(Ids.ProgId)]
[ClassInterface(ClassInterfaceType.AutoDispatch)]
public sealed class Connect : IDTExtensibility2, IRibbonExtensibility
{
    public void OnConnection(object application, int connectMode, object addInInst, ref Array custom)
    {
    }

    public void OnDisconnection(int removeMode, ref Array custom)
    {
    }

    public void OnAddInsUpdate(ref Array custom)
    {
    }

    public void OnStartupComplete(ref Array custom)
    {
    }

    public void OnBeginShutdown(ref Array custom)
    {
    }

    public string GetCustomUI(string ribbonId)
    {
        try
        {
            return Ribbon.For(ribbonId);
        }
        catch (Exception)
        {
            return "";   // nie Outlook stören
        }
    }

    /// <summary>onAction eines Knopfs (Office ruft es über IDispatch mit dem IRibbonControl auf).</summary>
    public void OnSpark(object control)
    {
        try
        {
            string? word = Ribbon.WordFor(ControlId(control));
            if (word is null)
            {
                return;
            }

            if (!Bridge.Send(word))
            {
                MessageBox.Show("Der Spark-Begleiter läuft nicht. Bitte starten und noch einmal klicken.",
                    "Spark", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
        }
        catch (Exception)
        {
            // Ein Fehler hier darf Outlook nicht stören.
        }
    }

    /// <summary>getImage: das Bild eines Knopfs (eigene kleine Zeichnung, kein Office-Symbol).</summary>
    public object? GetImage(object control)
    {
        try
        {
            return Icons.For(ControlId(control));
        }
        catch (Exception)
        {
            return null;
        }
    }

    private static string ControlId(object control) =>
        control.GetType().InvokeMember("Id", BindingFlags.GetProperty, null, control, null) as string ?? "";

    // Eintragen macht der Spark-Begleiter (HKCU, ohne Administratorrechte), nicht regasm.
}

/// <summary>Die festen Kennungen; der Begleiter trägt dieselben ein (OfficeSetup.cs).</summary>
public static class Ids
{
    public const string Clsid = "6F4E0B57-2C61-4B8A-9C3E-5A7D1E2F9B40";
    public const string ProgId = "SparkBegleiter.OutlookAddin";
}

/// <summary>Die Knöpfe je Fenster von Outlook classic.</summary>
public static class Ribbon
{
    private const string Ns = "http://schemas.microsoft.com/office/2009/07/customui";

    /// <summary>Knopf-Id → das Wort an den Begleiter. Nur diese drei gibt es.</summary>
    public static string? WordFor(string id) => id switch
    {
        "sparkWrite" => "verbessern",
        "sparkReply" => "antwort",
        "sparkTranslate" => "uebersetzen",
        _ => null,
    };

    public static string For(string ribbonId) => ribbonId switch
    {
        "Microsoft.Outlook.Explorer" => Xml("TabMail", Reply + Translate),
        "Microsoft.Outlook.Mail.Read" => Xml("TabReadMessage", Reply + Translate),
        "Microsoft.Outlook.Mail.Compose" => Xml("TabNewMailMessage", Write + Translate),
        _ => "",
    };

    private const string Write =
        "<button id=\"sparkWrite\" label=\"Text verbessern\" size=\"large\" getImage=\"GetImage\" onAction=\"OnSpark\" " +
        "screentip=\"Markierten Text mit dem Spark verbessern\" supertip=\"Ohne Markierung wie das Tastenkürzel der Schreibhilfe. Du prüfst den Vorschlag, bevor er übernommen wird.\"/>";

    private const string Reply =
        "<button id=\"sparkReply\" label=\"Antwort entwerfen\" size=\"large\" getImage=\"GetImage\" onAction=\"OnSpark\" " +
        "screentip=\"Antwort auf diese Mail entwerfen\" supertip=\"Der Spark schreibt einen Entwurf. Gesendet wird nie.\"/>";

    private const string Translate =
        "<button id=\"sparkTranslate\" label=\"Übersetzen\" size=\"large\" getImage=\"GetImage\" onAction=\"OnSpark\" " +
        "screentip=\"Markierten Text oder die Mail übersetzen\" supertip=\"Ohne Markierung die ganze Mail.\"/>";

    private static string Xml(string tab, string buttons) =>
        $"<customUI xmlns=\"{Ns}\"><ribbon><tabs><tab idMso=\"{tab}\"><group id=\"sparkGroup\" label=\"Spark\">{buttons}</group></tab></tabs></ribbon></customUI>";
}

/// <summary>Die Verbindung zum laufenden Begleiter: dieselbe Named Pipe wie das Explorer-Menü "Mit Spark".</summary>
public static class Bridge
{
    public static string PipeName =>
        $"SparkBegleiter.{System.Diagnostics.Process.GetCurrentProcess().SessionId}.{Environment.UserName}";

    /// <summary>Schickt <c>{"office":"&lt;wort&gt;"}</c>; wartet höchstens 1,5 s auf den Begleiter.</summary>
    public static bool Send(string word)
    {
        byte[] payload = Encoding.UTF8.GetBytes("{\"office\":\"" + word + "\"}\n");
        try
        {
            using var client = new NamedPipeClientStream(".", PipeName, PipeDirection.Out);
            client.Connect(1500);
            client.Write(payload, 0, payload.Length);
            client.Flush();
            return true;
        }
        catch (Exception ex) when (ex is TimeoutException or IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }
}

/// <summary>Die Bilder der Knöpfe: Kreis in der Farbe des Spark mit einem Zeichen.</summary>
internal static class Icons
{
    public static object? For(string id)
    {
        string glyph = id switch
        {
            "sparkWrite" => "✎",
            "sparkReply" => "↩",
            "sparkTranslate" => "A",
            _ => "S",
        };
        using var bmp = new Bitmap(32, 32);
        using (Graphics g = Graphics.FromImage(bmp))
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAliasGridFit;
            g.Clear(Color.Transparent);
            using var fill = new SolidBrush(Color.FromArgb(0x5B, 0x5B, 0xF0));
            g.FillEllipse(fill, 1, 1, 30, 30);
            using var font = new Font("Segoe UI Symbol", 15f, FontStyle.Bold, GraphicsUnit.Pixel);
            using var fmt = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
            g.DrawString(glyph, font, Brushes.White, new RectangleF(0, 0, 32, 32), fmt);
        }

        return PictureConverter.ToPicture(bmp);
    }

    /// <summary>Bitmap → IPictureDisp, wie Office es für getImage braucht.</summary>
    private sealed class PictureConverter : AxHost
    {
        private PictureConverter()
            : base(string.Empty)
        {
        }

        public static object ToPicture(Image image) => GetIPictureDispFromPicture(image);
    }
}
