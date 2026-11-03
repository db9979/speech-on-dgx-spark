using System.Text.Json.Nodes;
using static SparkBegleiter.NativeMethods;

namespace SparkBegleiter;

/// <summary>Ein fester Knopf einer Karte unter „Offen“ (Kennung und Beschriftung vom Panel).</summary>
internal sealed record OffenAct(string K, string De);

/// <summary>Eine Karte unter „Offen“: ein offener Vorgang mit Stand (rev) und seinen direkten Knöpfen.</summary>
internal sealed record OffenCard(string Id, int Rev, string Art, string Titel, string Zeile, IReadOnlyList<OffenAct> Acts);

/// <summary>Antwort von GET /api/desk/offen: wie viele offen sind und die ersten drei Karten (nach einem Knopf mit Satz).</summary>
internal sealed record OffenResult(int N, IReadOnlyList<OffenCard> Cards, string? Text = null);

/// <summary>Ein Treffer von Finden: Kennung, Titel, Quelle und Datum (Sekunden seit 1970).</summary>
internal sealed record FundHit(long Id, string Titel, string Quelle, long Wann);

internal static partial class SparkClient
{
    /// <summary>GET /api/desk/offen – die offenen Vorgänge (Zahl und die ersten drei Karten).</summary>
    public static async Task<OffenResult> OffenAsync(string baseUrl, string key, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, baseUrl + "/api/desk/offen");
        return ParseOffen(await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(true));
    }

    /// <summary>POST /api/desk/offen/act – ein fester Knopf einer Karte; das Panel prüft ihn wie an der Karte selbst.</summary>
    public static async Task<OffenResult> OffenActAsync(string baseUrl, string key, OffenCard card, string act, CancellationToken ct)
    {
        var body = new JsonObject { ["id"] = card.Id, ["act"] = act, ["rev"] = card.Rev };
        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/offen/act") { Content = JsonContent(body) };
        return ParseOffen(await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(true));
    }

    /// <summary>POST /api/desk/fund – Finden in den eigenen Daten; höchstens acht Treffer (Titel und Quelle).</summary>
    public static async Task<IReadOnlyList<FundHit>> FundAsync(string baseUrl, string key, string worte, CancellationToken ct)
    {
        var body = new JsonObject { ["worte"] = worte };
        using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl + "/api/desk/fund") { Content = JsonContent(body) };
        JsonNode json = await SendAsync(request, key, pairing: false, ShortTimeout, ct).ConfigureAwait(true);
        var hits = new List<FundHit>();
        foreach (JsonNode? item in (json["treffer"] as JsonArray ?? new JsonArray()).Take(8))
        {
            if (item is JsonObject o && o["id"] is JsonValue v && v.TryGetValue(out long id) && id is > 0 and <= 999_999_999_999)
            {
                long wann = o["wann"] is JsonValue w && w.TryGetValue(out long t) && t > 0 ? t : 0;
                hits.Add(new FundHit(id, Clean(Json.Str(o["titel"]), 120), Clean(Json.Str(o["quelle"]), 40), wann));
            }
        }

        return hits;
    }

    /// <summary>Jeder Wert geprüft: Kennung nur v + 10 Hex-Zeichen (vorgaenge.ID), Knöpfe nur als Wort.</summary>
    private static OffenResult ParseOffen(JsonNode json)
    {
        int n = Json.Int(json["n"]) is int i && i >= 0 ? Math.Min(i, 99_999) : 0;
        var cards = new List<OffenCard>();
        foreach (JsonNode? item in (json["cards"] as JsonArray ?? new JsonArray()).Take(3))
        {
            if (item is not JsonObject o || Json.Str(o["id"]) is not { } id
                || !System.Text.RegularExpressions.Regex.IsMatch(id, "^v[0-9a-f]{10}$") || Json.Int(o["rev"]) is not int rev)
            {
                continue;
            }

            var acts = new List<OffenAct>();
            foreach (JsonNode? a in (o["acts"] as JsonArray ?? new JsonArray()).Take(4))
            {
                if (a is JsonObject x && Json.Str(x["k"]) is { } k && System.Text.RegularExpressions.Regex.IsMatch(k, "^[a-z0-9_]{1,20}$")
                    && Clean(Json.Str(x["de"]), 30) is { Length: > 0 } de)
                {
                    acts.Add(new OffenAct(k, de));
                }
            }

            cards.Add(new OffenCard(id, rev, Clean(Json.Str(o["art"]), 40), Clean(Json.Str(o["titel"]), 120), Clean(Json.Str(o["zeile"]), 160), acts));
        }

        string? text = Json.Str(json["text"]) is { } s ? Clean(s, 240) : null;
        return new OffenResult(n, cards, text);
    }
}

/// <summary>
/// Teil "offen" (Begleiter Paket B): Abschnitt „Offen“ im Reiter Heute mit der Zahl der offenen Vorgänge und den ersten
/// drei Karten samt ihren festen Knöpfen. Ein Knopf wirkt auf dem Spark über vorgaenge.act, das ihn prüft wie an der
/// Karte selbst; der Begleiter entscheidet nichts. Eine Karte ohne Knopf öffnet Offen im Panel (#me=vgbox).
/// Teil "find": Finden per Strg+Alt+F, Kachel „Finden“ oder Menü. Aus, bis das Panel die Teile einschaltet.
/// </summary>
internal sealed partial class TrayContext
{
    private readonly System.Windows.Forms.Timer _offenTimer = new() { Interval = 5 * 60 * 1000 };
    private OffenResult? _offen;
    private string? _offenError;
    private bool _offenLoading;
    private bool _offenHooked;
    private bool _offenBusy;
    private FindForm? _findForm;

    private void SyncOffen()
    {
        if (!_offenHooked)
        {
            _offenTimer.Tick += async (_, _) => await RefreshOffenAsync();
            _offenHooked = true;
        }

        if (IsOn(Parts.Offen))
        {
            if (!_offenTimer.Enabled)
            {
                _offenTimer.Start();
                _ = RefreshOffenAsync();
            }
        }
        else
        {
            StopOffen();
        }

        if (!IsOn(Parts.Find))
        {
            StopFind();
        }
    }

    private void StopOffen()
    {
        _offenTimer.Stop();
        _offen = null;
        _offenError = null;
    }

    private async Task RefreshOffenAsync()
    {
        if (_offenLoading || !IsOn(Parts.Offen) || Credentials() is not { } creds)
        {
            return;
        }

        _offenLoading = true;
        try
        {
            OffenResult result = await SparkClient.OffenAsync(creds.Base, creds.Key, CancellationToken.None);
            if (IsOn(Parts.Offen))
            {
                _offen = result;
                _offenError = null;
            }
        }
        catch (SparkException ex)
        {
            _offenError = ex.Status is null ? "Spark nicht erreichbar – Offen später." : ex.Message;
            if (ex.Status is 401 or 403 or 503)
            {
                Report(ex, fromPoll: false);
            }
        }
        finally
        {
            _offenLoading = false;
            RefreshPanel();
        }
    }

    /// <summary>„Offen“ im Tray-Fenster: je Vorgang eine Karte mit seinen festen Knöpfen. null = aus.</summary>
    private IReadOnlyList<PanelNote>? BuildOffenCards()
    {
        if (!IsOn(Parts.Offen))
        {
            return null;
        }

        bool canOpen = !string.IsNullOrEmpty(_config.Base);
        Action? open = canOpen ? () => OpenPanelPage("#me=vgbox") : null;
        if (_offen is not { Cards.Count: > 0 } offen)
        {
            return new[] { new PanelNote(0, _offenError ?? (_offen is null ? "Wird geladen …" : "Nichts offen."), "", null, null, open, OpenLabel: "Öffnen") };
        }

        var list = new List<PanelNote>();
        foreach (OffenCard card in offen.Cards)
        {
            var extra = card.Acts.Select(a => (a.De, (Action)(() => _ = OffenActAsync(card, a.K)))).ToList();
            string body = string.Join(" · ", new[] { card.Art, card.Zeile }.Where(s => s.Length > 0));
            list.Add(new PanelNote(0, Clip(card.Titel.Length > 0 ? card.Titel : card.Art, 80), Clip(body, 200), null, null,
                extra.Count == 0 ? open : null, Extra: extra, OpenLabel: "Ansehen"));
        }

        if (offen.N > offen.Cards.Count)
        {
            list.Add(new PanelNote(0, $"Alle {offen.N} ansehen", "", null, null, open, OpenLabel: "Öffnen"));
        }

        return list;
    }

    private int OffenCount() => IsOn(Parts.Offen) ? _offen?.N ?? 0 : 0;

    /// <summary>Ein fester Knopf einer Karte; die Antwort bringt gleich die neue Liste mit.</summary>
    private async Task OffenActAsync(OffenCard card, string act)
    {
        if (_offenBusy || Credentials() is not { } creds || !card.Acts.Any(a => a.K == act))
        {
            return;
        }

        _offenBusy = true;
        try
        {
            OffenResult result = await SparkClient.OffenActAsync(creds.Base, creds.Key, card, act, CancellationToken.None);
            _offen = result;
            _offenError = null;
            Notify(result.Text ?? "Erledigt.", ToolTipIcon.Info);
        }
        catch (SparkException ex)
        {
            Notify(ex.Message, ToolTipIcon.Warning);
            Report(ex, fromPoll: false);
            await RefreshOffenAsync();
            return;
        }
        finally
        {
            _offenBusy = false;
        }

        RefreshPanel();
    }

    private async Task OpenFindAsync(bool fromHotkey)
    {
        if (!IsOn(Parts.Find) || Credentials() is null)
        {
            return;
        }

        if (_findForm is { IsDisposed: false } open)
        {
            open.Bring();
            return;
        }

        string line = "";
        if (fromHotkey)
        {
            line = await ClipboardHelper.CopySelectionAsync(_config.GetHotkey(Parts.Find).VirtualKey) ?? "";
        }

        var form = new FindForm(line,
            worte => Credentials() is { } c ? SparkClient.FundAsync(c.Base, c.Key, worte, CancellationToken.None)
                : throw new SparkException(null, "Nicht gekoppelt."),
            OpenPanelPage);
        form.FormClosed += (_, _) =>
        {
            if (ReferenceEquals(_findForm, form))
            {
                _findForm = null;
            }
        };
        _findForm = form;
        form.Bring();
    }

    private void StopFind()
    {
        _findForm?.Close();
        _findForm = null;
    }
}

/// <summary>
/// Finden (Begleiter Paket B, Strg+Alt+F): ein Suchfeld; der Spark sucht im eigenen Index des Profils und gibt Titel,
/// Quelle und Datum. Ein Treffer öffnet den Eintrag im Panel (#fund=&lt;id&gt;), „In Finden ansehen“ die Seite Finden mit
/// dieser Suche (#fundq=&lt;Wörter&gt;). Markierter Text kommt als Suche mit; auf dem PC bleibt nichts.
/// </summary>
internal sealed class FindForm : ThemedForm
{
    private const int MaxText = 200;
    private const int MaxHits = 8;

    private readonly TextBox _line = new() { MaxLength = MaxText, AccessibleName = "Was soll ich finden?" };
    private readonly RoundedHost _lineHost;
    private readonly TLabel _status = new(TextRole.SmallMuted);
    private readonly SparkButton _search = new(ButtonKind.Primary, "Suchen");
    private readonly SparkButton _all = new(ButtonKind.Secondary, "In Finden ansehen");
    private readonly SparkButton _cancel = new(ButtonKind.Secondary, "Schließen");
    private readonly List<SparkButton> _rows = new();
    private readonly Func<string, Task<IReadOnlyList<FundHit>>> _find;
    private readonly Action<string> _open;
    private int _seq;
    private Rectangle _titleBox;

    public FindForm(string line, Func<string, Task<IReadOnlyList<FundHit>>> find, Action<string> open)
    {
        _find = find;
        _open = open;
        _lineHost = new RoundedHost(_line);
        Text = "Spark-Begleiter – Finden";
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        MinimizeBox = false;
        TopMost = true;
        ShowInTaskbar = true;
        StartPosition = FormStartPosition.CenterScreen;
        KeyPreview = true;
        _line.PlaceholderText = "z. B. Rechnung Stadtwerke";
        string clean = string.Concat(line.ReplaceLineEndings(" ").Where(c => !char.IsControl(c))).Trim();
        _line.Text = clean.Length > MaxText ? clean[..MaxText] : clean;
        Controls.AddRange(new Control[] { _lineHost, _status, _search, _all, _cancel });
        _line.TabIndex = 0;
        _search.TabIndex = 20;
        _all.TabIndex = 21;
        _cancel.TabIndex = 22;
        _line.KeyDown += (_, e) =>
        {
            if (e.KeyCode == Keys.Enter && e.Modifiers == Keys.None)
            {
                e.SuppressKeyPress = true;
                _ = SearchAsync();
            }
        };
        _search.Click += async (_, _) => await SearchAsync();
        _all.Click += (_, _) => OpenAll();
        _cancel.Click += (_, _) => Close();
        CancelButton = _cancel;
    }

    /// <summary>Zeigen und das Feld in den Vordergrund holen (auch aus einem anderen Programm heraus).</summary>
    public void Bring()
    {
        Show();
        Activate();
        _ = SetForegroundWindow(Handle);
        _line.Focus();
        _line.SelectionStart = _line.TextLength;
        if (_line.TextLength > 0)
        {
            _ = SearchAsync();
        }
        else
        {
            Show("Wörter eingeben, dann Enter.", error: false);
        }
    }

    private string Words => _line.Text.Trim() is { Length: > MaxText } w ? w[..MaxText] : _line.Text.Trim();

    private async Task SearchAsync()
    {
        string words = Words;
        if (words.Length == 0)
        {
            return;
        }

        int seq = ++_seq;
        Show("Sucht …", error: false);
        try
        {
            IReadOnlyList<FundHit> hits = await _find(words);
            if (seq != _seq || IsDisposed)
            {
                return;
            }

            SetHits(hits);
            Show(hits.Count == 0 ? "Nichts gefunden." : hits.Count == 1 ? "1 Treffer" : $"{hits.Count} Treffer", error: false);
        }
        catch (SparkException ex)
        {
            if (seq == _seq && !IsDisposed)
            {
                SetHits(Array.Empty<FundHit>());
                Show(ex.Message, error: true);
            }
        }
    }

    private void SetHits(IReadOnlyList<FundHit> hits)
    {
        foreach (SparkButton b in _rows)
        {
            Controls.Remove(b);
            b.Dispose();
        }

        _rows.Clear();
        int tab = 1;
        foreach (FundHit h in hits.Take(MaxHits))
        {
            string day = h.Wann > 0 ? DateTimeOffset.FromUnixTimeSeconds(h.Wann).LocalDateTime.ToString("d.M.yyyy", System.Globalization.CultureInfo.InvariantCulture) : "";
            string detail = string.Join(" · ", new[] { h.Quelle, day }.Where(s => s.Length > 0));
            string text = (h.Titel.Length > 0 ? h.Titel : "Ohne Titel") + (detail.Length > 0 ? " · " + detail : "");
            var row = new SparkButton(ButtonKind.Row, text) { FontSize = 9f, Verb = "Öffnen", TabIndex = tab++ };
            row.AccessibleName = text + ", Öffnen";
            long id = h.Id;
            row.Click += (_, _) =>
            {
                _open("#fund=" + id.ToString(System.Globalization.CultureInfo.InvariantCulture));
                Close();
            };
            _rows.Add(row);
            Controls.Add(row);
        }
    }

    /// <summary>Die Seite Finden im Panel mit denselben Wörtern.</summary>
    private void OpenAll()
    {
        string words = Words;
        if (words.Length == 0)
        {
            return;
        }

        _open("#fundq=" + Uri.EscapeDataString(words));
        Close();
    }

    private void Show(string status, bool error)
    {
        _status.Text = status;
        _status.ForeColor = error ? Palette.Light.Bad : P.Muted;
        if (IsHandleCreated)
        {
            LayoutContent();
            Invalidate();
        }
    }

    protected override void LayoutContent()
    {
        int pad = S(16);
        int w = S(460);
        int inner = w - (2 * pad);
        int y = pad;
        int th = Draw.Measure("Ag", F(11f, FontStyle.Bold)).Height;
        _titleBox = new Rectangle(pad, y, inner, th);
        y += th + S(10);
        _line.Font = F(10.5f);
        _lineHost.Bounds = new Rectangle(pad, y, inner, S(40));
        y += S(40) + S(8);
        y += _status.Fit(pad, y, inner) + S(8);
        foreach (SparkButton row in _rows)
        {
            int h = S(34);
            row.Bounds = new Rectangle(pad, y, inner, h);
            y += h + S(2);
        }

        y += _rows.Count > 0 ? S(8) : 0;
        int right = w - pad;
        int bh = 0;
        foreach (SparkButton b in new[] { _search, _all, _cancel })
        {
            Size size = b.Preferred();
            right -= size.Width;
            b.Bounds = new Rectangle(right, y, size.Width, size.Height);
            right -= S(8);
            bh = Math.Max(bh, size.Height);
        }

        y += bh + pad;
        ClientSize = new Size(w, y);
    }

    protected override void PaintContent(Graphics g)
    {
        Draw.Text(g, "Finden", F(11f, FontStyle.Bold), _titleBox, P.Fg);
    }
}
