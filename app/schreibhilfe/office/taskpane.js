/* Spark Schreibhilfe – Office-Aufgabenbereich (Outlook, Word, Excel).
 * Wird vom Spark-Panel unter {base}/office/taskpane.js ausgeliefert; die API liegt auf demselben Ursprung.
 * Keine Protokollierung von Texten oder Schlüssel, keine Telemetrie, kein eval.
 */
(function () {
  "use strict";

  var BASE = window.location.origin;
  var KEY_STORE = "spark-schreib-key";
  var PROFILE_STORE = "spark-schreib-profil";
  var PREF_STORE = "spark-schreib-wahl";
  var TIMEOUT_MS = 180000;
  var NAME_RE;
  try { NAME_RE = new RegExp("^[\\p{L}\\p{N} ._-]{1,40}$", "u"); } catch (e) { NAME_RE = /^[A-Za-z0-9\u00C0-\u024F ._-]{1,40}$/; }

  var FALLBACK_ARTS = [
    { id: "korrigieren", de: "Korrigieren" },
    { id: "glaetten", de: "Glätten" },
    { id: "kuerzer", de: "Kürzer" },
    { id: "freundlicher", de: "Freundlicher" },
    { id: "foermlicher", de: "Förmlicher" },
    { id: "uebersetzen", de: "Übersetzen" },
    { id: "antwort", de: "Antwort entwerfen" }
  ];
  var FALLBACK_LANGS = [
    { id: "de", de: "Deutsch" },
    { id: "en", de: "Englisch" },
    { id: "fr", de: "Französisch" },
    { id: "es", de: "Spanisch" },
    { id: "it", de: "Italienisch" },
    { id: "nl", de: "Niederländisch" }
  ];

  // Zustand
  var mode = "none";          // outlook-read | outlook-compose | outlook-reply | word | excel | none
  var arts = FALLBACK_ARTS;
  var langs = FALLBACK_LANGS;
  var maxLen = 20000;
  var busy = false;
  var quelle = null;          // woher der Text kam (für "Übernehmen")
  var itemHandlerSet = false;

  function $(id) { return document.getElementById(id); }

  // ---------- Speicher (localStorage kann fehlen oder werfen) ----------
  function load(name) {
    try { return window.localStorage.getItem(name); } catch (e) { return null; }
  }
  function save(name, value) {
    try {
      if (value === null || value === undefined) window.localStorage.removeItem(name);
      else window.localStorage.setItem(name, value);
    } catch (e) { /* ohne Speicher weiter */ }
  }
  function loadPrefs() {
    try { return JSON.parse(load(PREF_STORE) || "{}") || {}; } catch (e) { return {}; }
  }
  function savePrefs(p) { save(PREF_STORE, JSON.stringify(p)); }

  // ---------- Meldungen ----------
  function meldung(el, text, art) {
    if (!text) { el.hidden = true; el.textContent = ""; return; }
    el.textContent = text;
    el.className = "meldung" + (art ? " " + art : "");
    el.hidden = false;
  }

  // ---------- API ----------
  function ApiError(status, detail) {
    this.status = status;
    this.detail = detail;
  }

  function detailText(status, data) {
    var d = data && data.detail;
    if (typeof d === "string" && d) return d;
    if (Array.isArray(d) && d.length) {
      return d.map(function (x) { return (x && x.msg) ? x.msg : String(x); }).join("; ");
    }
    switch (status) {
      case 400: return "Die Anfrage wurde abgelehnt.";
      case 401: return "Dieses Gerät ist nicht (mehr) gekoppelt. Bitte neu koppeln.";
      case 403: return "Die Schreibhilfe ist für dieses Profil oder in anderen Programmen ausgeschaltet.";
      case 413: return "Der Text ist zu lang.";
      case 429: return "Der Spark ist gerade beschäftigt. Bitte gleich noch einmal versuchen.";
      case 503: return "Der Spark ist gerade nicht verfügbar (Notaus).";
      default: return "Fehler vom Spark (" + status + ").";
    }
  }

  function api(method, path, body, withKey) {
    var ctrl = new AbortController();
    var timer = setTimeout(function () { ctrl.abort(); }, TIMEOUT_MS);
    var headers = { "Accept": "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (withKey) headers["X-Speech-Device"] = load(KEY_STORE) || "";
    return fetch(BASE + path, {
      method: method,
      headers: headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
      credentials: "omit",
      cache: "no-store"
    }).then(function (res) {
      return res.text().then(function (raw) {
        var data = null;
        try { data = raw ? JSON.parse(raw) : null; } catch (e) { data = null; }
        if (!res.ok) throw new ApiError(res.status, detailText(res.status, data));
        return data || {};
      });
    }, function (err) {
      if (err && err.name === "AbortError") {
        throw new ApiError(0, "Keine Antwort vom Spark nach 180 Sekunden.");
      }
      throw new ApiError(0, "Der Spark ist nicht erreichbar. Netzwerk prüfen.");
    }).finally(function () { clearTimeout(timer); });
  }

  // Fehler anzeigen; bei 401 Schlüssel löschen und Koppeln zeigen.
  function fehler(err, el) {
    var text = (err instanceof ApiError) ? err.detail : ((err && err.message) || "Unerwarteter Fehler.");
    if (err instanceof ApiError && err.status === 401) {
      save(KEY_STORE, null);
      save(PROFILE_STORE, null);
      zeigeKoppeln(text);
      return;
    }
    meldung(el, text, "fehler");
  }

  // ---------- Office-Hilfen ----------
  function officeAsync(starter) {
    return new Promise(function (resolve, reject) {
      starter(function (r) {
        if (r.status === Office.AsyncResultStatus.Succeeded) resolve(r.value);
        else reject(new Error((r.error && r.error.message) || "Office-Fehler"));
      });
    });
  }

  function norm(s) {
    return String(s || "").replace(/\r\n|\r|\v/g, "\n").replace(/ /g, " ").trim();
  }

  function textZuHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;")
      .replace(/\r\n|\r|\n/g, "<br>");
  }

  function erkenneModus(info) {
    if (!window.Office || !Office.HostType) return "none";
    var host = (info && info.host) || (Office.context && Office.context.host);
    if (host === Office.HostType.Outlook) {
      var item = Office.context.mailbox && Office.context.mailbox.item;
      if (!item) return "outlook-leer";
      if (typeof item.displayReplyForm === "function") return "outlook-read";
      return item.conversationId ? "outlook-reply" : "outlook-compose";
    }
    if (host === Office.HostType.Word) return "word";
    if (host === Office.HostType.Excel) return "excel";
    return "none";
  }

  // ---------- Text holen ----------
  function holeOutlookCompose() {
    var item = Office.context.mailbox.item;
    return officeAsync(function (cb) { item.body.getTypeAsync(cb); }).catch(function () { return "text"; })
      .then(function (typ) {
        var html = (typ === Office.CoercionType.Html || typ === "html");
        return officeAsync(function (cb) {
          item.getSelectedDataAsync(Office.CoercionType.Text, cb);
        }).then(function (sel) {
          var t = sel && sel.data ? String(sel.data) : "";
          if (t.trim()) {
            return { kind: "selection", text: t, original: t, html: html && sel.sourceProperty !== "subject" };
          }
          return officeAsync(function (cb) { item.body.getAsync(Office.CoercionType.Text, cb); })
            .then(function (body) {
              return { kind: "body", text: String(body || ""), original: String(body || ""), html: html };
            });
        });
      });
  }

  function holeMailText() {
    var item = Office.context.mailbox.item;
    return officeAsync(function (cb) { item.body.getAsync(Office.CoercionType.Text, cb); })
      .then(function (b) { return String(b || ""); });
  }

  function holeWord() {
    return Word.run(function (ctx) {
      var sel = ctx.document.getSelection();
      sel.load("text");
      return ctx.sync().then(function () {
        var t = sel.text || "";
        if (!norm(t)) return null;
        return { kind: "word", text: norm(t), original: t };
      });
    });
  }

  function holeExcel() {
    return Excel.run(function (ctx) {
      var r = ctx.workbook.getSelectedRange();
      r.load(["values", "formulas", "valueTypes"]);
      return ctx.sync().then(function () {
        var treffer = [];
        for (var i = 0; i < r.values.length; i++) {
          for (var j = 0; j < r.values[i].length; j++) {
            var v = r.values[i][j];
            if (v !== "" && v !== null) treffer.push([i, j]);
          }
        }
        if (treffer.length === 0) return { fehler: "Die markierte Zelle ist leer." };
        if (treffer.length > 1) return { fehler: "Bitte nur eine einzelne Zelle mit Text markieren." };
        var i0 = treffer[0][0], j0 = treffer[0][1];
        var f = r.formulas[i0][j0];
        if (typeof f === "string" && f.charAt(0) === "=") return { fehler: "Die Zelle enthält eine Formel – nur Text-Zellen werden bearbeitet." };
        if (r.valueTypes[i0][j0] !== "String") return { fehler: "Die Zelle enthält keinen Text." };
        var cell = r.getCell(i0, j0);
        cell.load("address");
        return ctx.sync().then(function () {
          var t = String(r.values[i0][j0]);
          return { kind: "excel", text: t, original: t, address: cell.address };
        });
      });
    });
  }

  // ---------- Übernehmen ----------
  function uebernehmeOutlook(text) {
    var item = Office.context.mailbox.item;
    if (quelle.kind === "readmail") {
      item.displayReplyForm(textZuHtml(text));
      return Promise.resolve("Antwort geöffnet.");
    }
    if (quelle.kind === "cursor") {
      return officeAsync(function (cb) {
        if (quelle.html) item.body.setSelectedDataAsync(textZuHtml(text), { coercionType: Office.CoercionType.Html }, cb);
        else item.body.setSelectedDataAsync(text, { coercionType: Office.CoercionType.Text }, cb);
      }).then(function () { return "Eingefügt."; });
    }
    if (quelle.kind === "selection") {
      return officeAsync(function (cb) { item.getSelectedDataAsync(Office.CoercionType.Text, cb); })
        .then(function (sel) {
          if (norm(sel && sel.data) !== norm(quelle.original)) {
            throw new Error("Die Markierung hat sich geändert. Bitte den ursprünglichen Text wieder markieren oder „Kopieren“ nutzen.");
          }
          return officeAsync(function (cb) {
            if (quelle.html) item.setSelectedDataAsync(textZuHtml(text), { coercionType: Office.CoercionType.Html }, cb);
            else item.setSelectedDataAsync(text, { coercionType: Office.CoercionType.Text }, cb);
          });
        }).then(function () { return "Übernommen."; });
    }
    // ganzer Text
    return officeAsync(function (cb) {
      if (quelle.html) item.body.setAsync(textZuHtml(text), { coercionType: Office.CoercionType.Html }, cb);
      else item.body.setAsync(text, { coercionType: Office.CoercionType.Text }, cb);
    }).then(function () { return "Ganzer Text ersetzt."; });
  }

  function uebernehmeWord(text) {
    return Word.run(function (ctx) {
      var sel = ctx.document.getSelection();
      sel.load("text");
      return ctx.sync().then(function () {
        if (norm(sel.text) !== norm(quelle.original)) {
          throw new Error("Die Markierung hat sich geändert. Bitte den ursprünglichen Text wieder markieren oder „Kopieren“ nutzen.");
        }
        sel.insertText(text, "Replace");
        return ctx.sync();
      });
    }).then(function () { return "Übernommen."; });
  }

  function teileAdresse(adr) {
    var k = adr.lastIndexOf("!");
    var blatt = adr.slice(0, k);
    if (blatt.charAt(0) === "'" && blatt.charAt(blatt.length - 1) === "'") {
      blatt = blatt.slice(1, -1).replace(/''/g, "'");
    }
    return { blatt: blatt, zelle: adr.slice(k + 1) };
  }

  function uebernehmeExcel(text) {
    var a = teileAdresse(quelle.address);
    return Excel.run(function (ctx) {
      var r = ctx.workbook.worksheets.getItem(a.blatt).getRange(a.zelle);
      r.load("values");
      return ctx.sync().then(function () {
        if (String(r.values[0][0]) !== quelle.original) {
          throw new Error("Die Zelle " + a.zelle + " wurde inzwischen geändert. Bitte neu starten.");
        }
        r.values = [[text]];
        return ctx.sync();
      });
    }).then(function () { return "In Zelle " + a.zelle + " geschrieben."; });
  }

  // ---------- Diff ----------
  function zeigeDiff(diff, changes) {
    var box = $("diffBox"), ziel = $("diff");
    while (ziel.firstChild) ziel.removeChild(ziel.firstChild);
    ziel.classList.remove("veraltet");
    if (!Array.isArray(diff)) { box.hidden = true; return; }
    var vorher = "";
    diff.forEach(function (teil) {
      if (!Array.isArray(teil) || teil.length < 2) return;
      var op = teil[0], t = String(teil[1]);
      if (!t) return;
      if (vorher && !/\s$/.test(vorher) && !/^\s/.test(t)) ziel.appendChild(document.createTextNode(" "));
      var el;
      if (op === "-") el = document.createElement("del");
      else if (op === "+") el = document.createElement("ins");
      else el = document.createElement("span");
      el.textContent = t;
      ziel.appendChild(el);
      vorher = t;
    });
    $("anzahl").textContent = (typeof changes === "number")
      ? "(" + changes + (changes === 1 ? " Änderung)" : " Änderungen)") : "";
    box.hidden = false;
  }

  // ---------- Oberfläche ----------
  function zeigeKoppeln(text) {
    $("laden").hidden = true;
    $("haupt").hidden = true;
    $("koppeln").hidden = false;
    meldung($("koppelnMeldung"), text || "", text ? "fehler" : "");
    $("code").focus();
  }

  function artErlaubt(id) {
    if (mode === "outlook-read") return id === "antwort" || id === "uebersetzen";
    if (id === "antwort") return mode === "outlook-reply";
    return true;
  }

  function fuelleArten() {
    var sel = $("art"), prefs = loadPrefs();
    while (sel.firstChild) sel.removeChild(sel.firstChild);
    arts.filter(function (a) { return a && a.id && artErlaubt(a.id); }).forEach(function (a) {
      var o = document.createElement("option");
      o.value = a.id;
      o.textContent = (a.id === "uebersetzen" && mode === "outlook-read") ? "Mail übersetzen" : (a.de || a.id);
      sel.appendChild(o);
    });
    var wunsch = mode === "outlook-read" ? "antwort" : prefs.art;
    if (wunsch && sel.querySelector('option[value="' + wunsch + '"]')) sel.value = wunsch;
    artGeaendert();
  }

  function fuelleSprachen(art) {
    var sel = $("sprache"), prefs = loadPrefs();
    var alt = sel.value;
    while (sel.firstChild) sel.removeChild(sel.firstChild);
    if (art === "antwort") {
      var o = document.createElement("option");
      o.value = "auto";
      o.textContent = "Wie die Mail";
      sel.appendChild(o);
    }
    langs.forEach(function (l) {
      var o2 = document.createElement("option");
      o2.value = l.id;
      o2.textContent = l.de || l.id;
      sel.appendChild(o2);
    });
    var bevorzugt = art === "antwort" ? (prefs.spracheAntwort || "auto") : (prefs.sprache || alt || "en");
    if (sel.querySelector('option[value="' + bevorzugt + '"]')) sel.value = bevorzugt;
  }

  function losText(art) {
    if (art === "antwort") return "Antwort entwerfen";
    if (mode === "outlook-read") return "Mail übersetzen";
    if (mode === "excel") return art === "uebersetzen" ? "Zelle übersetzen" : "Zelle verbessern";
    return art === "uebersetzen" ? "Markierten Text übersetzen" : "Markierten Text verbessern";
  }

  function artGeaendert() {
    var art = $("art").value;
    var mitSprache = art === "uebersetzen" || art === "antwort";
    $("spracheZeile").hidden = !mitSprache;
    if (mitSprache) fuelleSprachen(art);
    $("notizenZeile").hidden = art !== "antwort";
    $("vorschlaegeZeile").hidden = art !== "antwort";
    $("los").textContent = losText(art);
  }

  function kontextText() {
    switch (mode) {
      case "outlook-read": return "Gelesene Mail: Antwort entwerfen oder übersetzen.";
      case "outlook-reply": return "Antwort verfassen: Text markieren (sonst ganzer Text) – oder Antwort entwerfen.";
      case "outlook-compose": return "Text in der Mail markieren. Ohne Markierung wird der ganze Text bearbeitet.";
      case "word": return "Text im Dokument markieren.";
      case "excel": return "Eine Zelle mit Text markieren.";
      case "outlook-leer": return "Bitte eine Mail öffnen oder auswählen.";
      default: return "Bitte in Outlook, Word oder Excel öffnen.";
    }
  }

  function zeigeHaupt() {
    $("laden").hidden = true;
    $("koppeln").hidden = true;
    $("haupt").hidden = false;
    $("kontext").textContent = kontextText();
    var profil = load(PROFILE_STORE);
    $("verbunden").textContent = profil ? "Gekoppelt als " + profil : "Gekoppelt";
    var nutzbar = mode !== "none" && mode !== "outlook-leer";
    $("los").disabled = !nutzbar;
    $("art").disabled = !nutzbar;
    fuelleArten();
  }

  function setzeErgebnisZurueck() {
    quelle = null;
    $("umformen").hidden = true;
    $("ergebnis").hidden = true;
    $("text").value = "";
    meldung($("ergebnisMeldung"), "");
    meldung($("status"), "");
  }

  function ladeInfo() {
    return api("GET", "/api/write", undefined, true).then(function (info) {
      if (info && Array.isArray(info.arts) && info.arts.length) arts = info.arts;
      if (info && Array.isArray(info.langs) && info.langs.length) langs = info.langs;
      if (info && typeof info.max === "number" && info.max > 0) maxLen = info.max;
      zeigeHaupt();
      if (info && info.on === false) {
        meldung($("status"), "Die Schreibhilfe ist auf dem Spark ausgeschaltet.", "fehler");
      }
    }, function (err) {
      if (err instanceof ApiError && err.status === 401) { fehler(err, $("status")); return; }
      zeigeHaupt();
      fehler(err, $("status"));
    });
  }

  // ---------- Koppeln ----------
  function koppeln() {
    var el = $("koppelnMeldung");
    var eingabe = $("code").value.trim();
    var name = $("geraet").value.trim() || "Office";
    var code = eingabe;
    var pos = eingabe.indexOf("#schreib=");
    if (pos >= 0) {
      var basis = eingabe.slice(0, pos).trim().replace(/\/+$/, "");
      code = eingabe.slice(pos + 9).trim();
      if (basis && basis.toLowerCase() !== BASE.toLowerCase()) {
        meldung(el, "Diese Zeile gehört zu einem anderen Spark (" + basis + "). Dieses Add-in ist mit " + BASE + " verbunden.", "fehler");
        return;
      }
    }
    if (!/^[A-Za-z0-9]{8}$/.test(code.replace(/[-\s]/g, ""))) {
      meldung(el, "Bitte den Code im Format XXXX-XXXX eingeben.", "fehler");
      return;
    }
    if (!NAME_RE.test(name)) {
      meldung(el, "Gerätename: 1–40 Zeichen, nur Buchstaben, Ziffern, Leerzeichen und . - _", "fehler");
      return;
    }
    $("koppelnBtn").disabled = true;
    meldung(el, "Kopple …", "laeuft");
    api("POST", "/api/write/pair", { code: code, name: name, kind: "office" }, false).then(function (r) {
      if (!r || typeof r.key !== "string" || !r.key) throw new ApiError(0, "Unerwartete Antwort vom Spark.");
      save(KEY_STORE, r.key);
      save(PROFILE_STORE, r.profile ? String(r.profile) : null);
      $("code").value = "";
      meldung(el, "");
      setzeErgebnisZurueck();
      return ladeInfo();
    }).catch(function (err) {
      var text = err instanceof ApiError ? err.detail : "Koppeln fehlgeschlagen.";
      if (err instanceof ApiError && err.status === 429) text = err.detail || "Zu viele Versuche. Bitte später erneut.";
      meldung(el, text, "fehler");
    }).finally(function () {
      $("koppelnBtn").disabled = false;
    });
  }

  // ---------- Los ----------
  function holeQuelle(art) {
    if (mode === "outlook-read") {
      return holeMailText().then(function (mail) {
        if (!norm(mail)) throw new Error("Die Mail enthält keinen Text.");
        return { kind: art === "antwort" ? "readmail" : "nurlesen", text: mail, mail: mail };
      });
    }
    if (mode === "outlook-reply" && art === "antwort") {
      var item = Office.context.mailbox.item;
      return officeAsync(function (cb) { item.body.getTypeAsync(cb); }).catch(function () { return "text"; })
        .then(function (typ) {
          return holeMailText().then(function (mail) {
            if (!norm(mail)) throw new Error("Keine Mail zum Beantworten gefunden.");
            return { kind: "cursor", text: "", mail: mail, html: typ === Office.CoercionType.Html || typ === "html" };
          });
        });
    }
    if (mode === "outlook-compose" || mode === "outlook-reply") {
      return holeOutlookCompose().then(function (q) {
        if (!norm(q.text)) throw new Error("Kein Text gefunden. Bitte Text schreiben oder markieren.");
        return q;
      });
    }
    if (mode === "word") {
      return holeWord().then(function (q) {
        if (!q) throw new Error("Nichts markiert. Bitte Text im Dokument markieren.");
        return q;
      });
    }
    if (mode === "excel") {
      return holeExcel().then(function (q) {
        if (q.fehler) throw new Error(q.fehler);
        return q;
      });
    }
    return Promise.reject(new Error(kontextText()));
  }

  function los() {
    if (busy) return;
    var art = $("art").value;
    var sprache = $("sprache").value;
    var wunsch = $("wunsch").value.trim().slice(0, 300);
    var status = $("status");
    var prefs = loadPrefs();
    if (mode !== "outlook-read") prefs.art = art;
    if (art === "antwort") prefs.spracheAntwort = sprache;
    else if (art === "uebersetzen") prefs.sprache = sprache;
    savePrefs(prefs);

    setzeErgebnisZurueck();
    busy = true;
    $("los").disabled = true;
    var start = Date.now();
    meldung(status, "Der Spark schreibt …", "laeuft");
    var uhr = setInterval(function () {
      meldung(status, "Der Spark schreibt … (" + Math.round((Date.now() - start) / 1000) + " s)", "laeuft");
    }, 1000);

    holeQuelle(art).then(function (q) {
      var body = { art: art, text: q.text };
      if (art === "antwort") {
        body.text = $("notizen").value;
        body.mail = q.mail;
      }
      if (art === "uebersetzen" || art === "antwort") body.sprache = sprache;
      if (wunsch) body.wunsch = wunsch;
      if (body.text.length > maxLen) throw new Error("Der Text ist zu lang (höchstens " + maxLen + " Zeichen).");
      if (body.mail && body.mail.length > maxLen) body.mail = body.mail.slice(0, maxLen);
      quelle = q;
      return api("POST", "/api/write/assist", body, true);
    }).then(function (r) {
      var text = (r && typeof r.text === "string") ? r.text : "";
      meldung(status, (r && r.ms) ? "Fertig in " + (r.ms / 1000).toFixed(1).replace(".", ",") + " s." : "Fertig.", "ok");
      zeigeErgebnis(text, r && r.diff, r && r.changes);
    }).catch(function (err) {
      quelle = null;
      fehler(err, status);
    }).finally(function () {
      clearInterval(uhr);
      busy = false;
      $("los").disabled = false;
    });
  }

  // Antwortvorschläge (Begleiter nachziehen 6a): drei Antworten zur gelesenen Mail (/api/write/suggest), eine wählen,
  // dann frei ändern oder umformen (kürzer, freundlicher, förmlicher, Englisch über /api/write/assist). Nie gesendet:
  // „Als Antwort öffnen“ öffnet nur das Antwortfenster.
  function vorschlaege() {
    if (busy) return;
    var status = $("status");
    busy = true;
    $("vorschlaegeBtn").disabled = true;
    meldung(status, "Der Spark sucht drei Antworten …", "laeuft");
    holeQuelle("antwort").then(function (q) {
      quelle = q;
      return api("POST", "/api/write/suggest", { mail: String(q.mail || "").slice(0, maxLen) }, true);
    }).then(function (r) {
      var box = $("vorschlaege");
      while (box.firstChild) box.removeChild(box.firstChild);
      var items = (r && Array.isArray(r.items)) ? r.items.slice(0, 3) : [];
      items.forEach(function (x) {
        if (!x || typeof x.text !== "string" || !x.text.trim()) return;
        var b = document.createElement("button");
        b.type = "button";
        b.textContent = String(x.label || "Vorschlag").slice(0, 24);   // nur Text, nie Markup
        b.title = x.text.slice(0, 300);
        b.addEventListener("click", function () {
          zeigeErgebnis(x.text.slice(0, 2000), null, null);
          $("umformen").hidden = false;
          meldung(status, "Ändern, kürzen oder übersetzen – gesendet wird nichts.", "ok");
        });
        box.appendChild(b);
      });
      meldung(status, box.firstChild ? "Einen Vorschlag wählen oder Stichpunkte schreiben und „Los“." : "Keine Vorschläge – Stichpunkte schreiben.", "ok");
    }).catch(function (err) {
      quelle = null;
      $("vorschlaegeBtn").disabled = false;
      fehler(err, status);
    }).finally(function () { busy = false; });
  }

  // eine andere Mail: wieder nur der Knopf „3 Vorschläge“
  function vorschlaegeZurueck() {
    var box = $("vorschlaege");
    while (box.firstChild) box.removeChild(box.firstChild);
    var b = document.createElement("button");
    b.type = "button";
    b.id = "vorschlaegeBtn";
    b.textContent = "3 Vorschläge";
    b.addEventListener("click", vorschlaege);
    box.appendChild(b);
  }

  function umformen(art) {
    var text = $("text").value;
    if (busy || !text.trim()) return;
    var el = $("ergebnisMeldung");
    busy = true;
    meldung(el, "Der Spark formt die Antwort um …", "laeuft");
    var body = { art: art, text: text.slice(0, maxLen) };
    if (art === "uebersetzen") body.sprache = "en";
    api("POST", "/api/write/assist", body, true).then(function (r) {
      if (r && typeof r.text === "string") $("text").value = r.text;
      meldung(el, "Ändern, kürzen oder übersetzen – gesendet wird nichts.", "ok");
    }).catch(function (err) { fehler(err, el); }).finally(function () { busy = false; });
  }

  function zeigeErgebnis(text, diff, changes) {
    $("text").value = text;
    zeigeDiff(diff, changes);
    var knopf = $("uebernehmen");
    var k = quelle && quelle.kind;
    knopf.hidden = (k === "nurlesen");
    knopf.textContent =
      k === "readmail" ? "Als Antwort öffnen" :
      k === "cursor" ? "Am Cursor einfügen" :
      k === "body" ? "Übernehmen (ganzer Text)" :
      k === "excel" ? "In Zelle schreiben" : "Übernehmen";
    meldung($("ergebnisMeldung"), k === "body" && quelle.html
      ? "Hinweis: Beim Übernehmen des ganzen Texts geht die Formatierung verloren." : "", "");
    $("ergebnis").hidden = false;
  }

  function uebernehmen() {
    if (!quelle) return;
    var text = $("text").value;
    var el = $("ergebnisMeldung");
    var p;
    if (mode.indexOf("outlook") === 0) p = uebernehmeOutlook(text);
    else if (mode === "word") p = uebernehmeWord(text);
    else if (mode === "excel") p = uebernehmeExcel(text);
    else return;
    $("uebernehmen").disabled = true;
    p.then(function (msg) { meldung(el, msg, "ok"); },
      function (err) { meldung(el, (err && err.message) || "Übernehmen fehlgeschlagen.", "fehler"); })
      .finally(function () { $("uebernehmen").disabled = false; });
  }

  function kopieren() {
    var ta = $("text"), el = $("ergebnisMeldung");
    var text = ta.value;
    function alt() {
      ta.focus();
      ta.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      meldung(el, ok ? "Kopiert." : "Kopieren nicht möglich – bitte Text markieren und Strg+C drücken.", ok ? "ok" : "fehler");
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { meldung(el, "Kopiert.", "ok"); }, alt);
    } else {
      alt();
    }
  }

  function neuKoppeln() {
    save(KEY_STORE, null);
    save(PROFILE_STORE, null);
    setzeErgebnisZurueck();
    zeigeKoppeln("");
  }

  function itemGewechselt() {
    mode = erkenneModus(null);
    setzeErgebnisZurueck();
    vorschlaegeZurueck();
    if (!$("haupt").hidden) zeigeHaupt();
  }

  function start(info) {
    if (typeof window.fetch !== "function" || typeof window.Promise !== "function" ||
        typeof window.AbortController !== "function") {
      $("laden").textContent = "Diese Office-Version ist zu alt für die Schreibhilfe. Bitte Microsoft 365, das neue Outlook oder Outlook im Web verwenden.";
      return;
    }
    mode = erkenneModus(info);
    $("art").addEventListener("change", artGeaendert);
    $("los").addEventListener("click", los);
    $("uebernehmen").addEventListener("click", uebernehmen);
    $("kopieren").addEventListener("click", kopieren);
    vorschlaegeZurueck();
    Array.prototype.forEach.call($("umformen").querySelectorAll("button"), function (b) {
      b.addEventListener("click", function () { umformen(b.getAttribute("data-art")); });
    });
    $("neuKoppeln").addEventListener("click", neuKoppeln);
    $("koppelnBtn").addEventListener("click", koppeln);
    $("code").addEventListener("keydown", function (e) { if (e.key === "Enter") koppeln(); });
    $("geraet").addEventListener("keydown", function (e) { if (e.key === "Enter") koppeln(); });
    $("text").addEventListener("input", function () { $("diff").classList.add("veraltet"); });

    // Angehefteter Bereich in Outlook: auf Mailwechsel reagieren (Mailbox 1.5).
    if (mode.indexOf("outlook") === 0 && !itemHandlerSet && Office.context.mailbox.addHandlerAsync) {
      itemHandlerSet = true;
      try {
        Office.context.mailbox.addHandlerAsync(Office.EventType.ItemChanged, itemGewechselt);
      } catch (e) { /* ältere Clients */ }
    }

    if (!load(KEY_STORE)) zeigeKoppeln("");
    else ladeInfo();
  }

  if (window.Office && typeof Office.onReady === "function") {
    Office.onReady(start);
  } else {
    document.addEventListener("DOMContentLoaded", function () { start(null); });
  }
})();
