# Installation im Detail

← [README](../../README.de.md)

Geteilt installieren (Panel auf einem eigenen Rechner wie einem Raspberry Pi 5), umziehen und zurückholen: [Spark teilen](spark-teilen.md).

## Nur die Modelle bereitstellen (ohne Webportal)

Die erste Installation fragt im Terminal, was installiert werden soll:

1. **Komplett:** Modelle, APIs und das Webportal mit dem Assistenten (wie bisher).
2. **Nur die Modelle mit ihren APIs:** für andere Dienste (Open WebUI, eigene Apps, Home Assistant …), ohne Webportal, Passwort und Zertifikat.

Danach fragt sie, welche Modelle es sein sollen (Spracherkennung Qwen3-ASR 1.7B, 0.6B, Parakeet oder keine; Sprachausgabe Qwen3-TTS 0.6B, 1.7B oder keine; VoiceDesign ja oder nein, jeweils mit grob geschätztem Speicherbedarf) und ob die APIs im Netz erreichbar sein sollen oder nur auf der Spark selbst (`127.0.0.1`, z. B. hinter einem eigenen Reverse-Proxy). Ein API-Schlüssel wird immer erzeugt und ist Pflicht. Spätere Aufrufe und Updates fragen nicht noch einmal. Ohne Fragen geht es mit Optionen:

```bash
sudo ./install.sh --mode api --asr 1.7b --tts 0.6b --yes   # nur Modelle, im Netz erreichbar
sudo ./install.sh --mode api --asr parakeet --tts none --local --yes
```

Am Ende stehen Adressen, Schlüssel und fertige `curl`-Beispiele auf dem Bildschirm und in `/etc/speech-spark/connection.txt` (nur für root lesbar). Ohne Portal übernimmt der Befehl `speech-spark` dessen Aufgaben:

| Befehl | Wirkung |
|---|---|
| `sudo speech-spark status` | Dienste, Modelle, freier Speicher, letztes Update |
| `sudo speech-spark info` | Adressen, API-Schlüssel, Beispiele, Werte für Open WebUI |
| `sudo speech-spark key new` | neuer API-Schlüssel (der alte gilt sofort nicht mehr) |
| `sudo speech-spark models` | Modelle neu wählen, gleiche Fragen wie bei der Installation |
| `sudo speech-spark update` | Update wie der Knopf im Portal (`--check` zeigt nur, was neu ist) |
| `sudo speech-spark logs tts -n 100` | letzte Log-Zeilen (asr, tts, asr-engine, tts-engine, tts-design, bild, watch, update, messen, all) |
| `sudo speech-spark panel enable` | Webportal nachrüsten; Modelle und API-Schlüssel bleiben |
| `sudo speech-spark panel disable` | Webportal entfernen; Profile und Daten bleiben auf der Platte |
| `sudo speech-spark notzugang` | ausgesperrt: neues Panel-Passwort (einmal angezeigt), zweiter Schritt des Notzugangs aus (alte Datei als `.bak`), Haupt-Admin gelöst (Rollen bleiben); fragt vorher, steht im Änderungsprotokoll, Push an die Admins. Danach `https://…/#admin` ohne Code, zweiten Schritt neu einrichten, Haupt-Admin wieder wählen |
| `sudo speech-spark modelle liste` | der Modell-Katalog (`app/modelle.json`): Modelle, Art, Speicher, ob die Revision festgelegt ist |
| `sudo speech-spark modelle messen` | misst die Katalog-Modelle auf diesem Spark (Standard: Qwen3.8 27B NVFP4 und Qwen3-VL 8B; dazu `fp8`, `gemma`, `kolibri` auf Wunsch; Kolibri braucht vorher `--kolibri`). Lädt fehlende Modelle (Qwen3.8 kopiert es aus dem Speicher von qwen38 und prüft jede Datei), stoppt qwen38 mit Wartungspause, misst je Modell Tempo, erste Antwort, Speicher, Werkzeugaufruf und Testbilder und startet qwen38 danach immer wieder. Schaltet nichts um, löscht nichts. Ergebnis in *Zustand → Logs* (Bereich System) oder `sudo speech-spark logs messen` |
| `sudo speech-spark modelle llm uebernehmen` | zieht das Gespräch aufs eigene Sprachmodell um (vorher `sudo ./install.sh --llm` und einmal messen): notiert die laufenden qwen38-Dienste und die alte Adresse, stoppt und deaktiviert qwen38 (löscht nichts), startet das eigene Modell hinter dem LLM-Tor und prüft es (deutscher Satz, Werkzeugaufruf, Bild, System One). Erst dann zeigt das Gespräch auf das Tor; scheitert die Prüfung, geht alles von selbst zurück |
| `sudo speech-spark modelle llm zurueck` | eigenes Sprachmodell aus, die notierten qwen38-Dienste wieder an, alte Adresse zurück |
| `sudo speech-spark modelle qwen38-aufraeumen` | nur nach einem gelungenen Umzug und nur auf deinen Befehl: zeigt, was qwen38s eigene Deinstallation entfernt, fragt und ruft sie dann auf. Nie automatisch, auch nicht bei einem Update |
| `sudo speech-spark teilen [status]` | geteilte Installation (Panel auf einem anderen Rechner, seit V01.0.608): ob die Tür (TLS-Tor) offen ist, für wie viele Panel-Rechner, ob die Firewall steht, und der Fingerabdruck des Zertifikats |
| `sudo speech-spark teilen modelle-update` | Auf dem Panel-Rechner: das eigene Update des Modell-Rechners anstoßen und darauf warten (macht `update.sh` von selbst zuerst) |
| `sudo speech-spark teilen code` | Auf dem Modell-Rechner: Kopplungscode zeigen (10 Minuten, einmal nutzbar) und auf den Panel-Rechner warten |
| `sudo speech-spark teilen koppeln <name-oder-ip>` | Auf dem Panel-Rechner: mit dem Modell-Rechner koppeln (fragt nach dem Code, merkt sich sein Zertifikat) |
| `sudo speech-spark teilen rundlauf` | Auf dem Panel-Rechner: Wärter fragen, TTS spricht einen Satz, ASR hört ihn, alles über die Tür |
| `sudo speech-spark umziehen --code` | Auf dem Rechner, der das Panel jetzt hat: Umzug anbieten (Code, Umzugs-Sicherung mit Tresor-Schlüssel und Panel-Zertifikat); erst nach „fertig“ vom anderen Rechner wechselt er die Rolle |
| `sudo speech-spark umziehen --von <name-oder-ip>` | Auf dem neuen Panel-Rechner: Umzug holen, einspielen, prüfen (geht auch beim Koppeln mit `install.sh --mode panel`) |
| `sudo speech-spark zurueckholen --von <name-oder-ip>` | Auf dem Modell-Rechner: das Panel zurückholen, danach läuft wieder alles auf einem Rechner |
| `sudo speech-spark teilen firewall [aus]` | die Ports der Tür nur vom Panel-Rechner (`api.tls_from`) erreichbar machen (nftables, Tabelle `speech_spark_teilen`), oder wieder aus |

Den Wächter für hängende Dienste, der sonst im Portal läuft, übernimmt ohne Portal der Dienst `speech-spark-watch` mit denselben Regeln. Nach einem Update spricht die Sprachausgabe einen Satz, und die Spracherkennung muss ihn verstehen; klappt das nicht, spielt das Update die vorige Version wieder ein. Die Selbsttests laufen in beiden Arten vor jedem Update. Läuft das Sprachmodell noch über dgx-spark-qwen38, bleibt es davon unberührt; das eigene Sprachmodell aktualisiert sich mit. Läuft Open WebUI in Docker auf derselben Spark, müssen die APIs im Netz erreichbar sein (`127.0.0.1` im Container ist der Container selbst).

## Aktualisieren

Im Panel unter **System**: Dort steht die installierte Version, und es wird angezeigt, wenn auf GitHub eine neuere liegt (mit der Liste der Änderungen). **Update installieren** holt den neuen Stand und installiert ihn. Einstellungen, Modelle und Stimmen bleiben, das Protokoll läuft live mit. Schon installierte Pakete werden dabei nicht aktualisiert; nachgeladen wird nur, was die neue Version braucht. Bevor die neue Version live geht, läuft der Selbsttest. Schlägt er oder ein Schritt davor fehl (Download, Pakete), bricht das Update ab, und die Dienste laufen unverändert mit der alten Version weiter. Geht nach dem Umschalten etwas schief, spielt `update.sh` die vorige Version wieder ein und sagt das im Protokoll. Während das Update läuft, sperrt ein Fortschrittsfenster das Panel (auch andere Tabs und Handys: der Server nimmt keine Änderungen an, der Assistent antwortet weiter); Frage, Fortschritt und Neustart stehen in diesem einen Fenster: dahinter steht die Seite still (kein Band „Spark antwortet nicht“, keine Versionsleiste), der Balken läuft nur vorwärts, und über den Neustart des Panels wartet das Fenster ruhig. Am Ende lädt die Seite einmal und kommt an dieselbe Stelle zurück (Einstellungen → Update). Jeder Zustand zeigt nur seine Knöpfe: die Frage „Installieren“ und „Abbrechen“, ein laufendes Update keine; ist es nach 45 Minuten nicht fertig, gibt es „Neu laden“ und „Update abbrechen“, schlägt es fehl, „Schließen“ und „Protokoll kopieren“. Das Protokoll steht eingeklappt darunter.

**Was ist neu (Changelog)**: Alle Änderungen bis zur installierten Version, eine Zeile pro Version, neueste oben, mit Suche. Zu öffnen über „Was ist neu“ unten neben der Versionsnummer oder unter *Einstellungen → Update und Sicherung → Was ist neu (Changelog) → Ansehen*. Sehen kann es der Admin und jedes Profil in seiner eigenen Anmeldung im Browser (nicht Gäste, nicht Geräteschlüssel). Versionen, die neuer sind als beim letzten Öffnen in diesem Browser, tragen „neu“. Die Liste kommt aus `CHANGELOG.md` der installierten Version (das Update legt eine Kopie nach `app/`).

Auf der Konsole geht dasselbe mit:

```bash
sudo speech-spark update                       # aktualisieren (oder: sudo /opt/speech-spark/src/update.sh)
sudo /opt/speech-spark/src/update.sh --check   # nur anzeigen, was neu ist
```

Der Installer legt dafür eine eigene Git-Kopie unter `/opt/speech-spark/src` an. Wo du das Repo ursprünglich geklont hast, spielt danach keine Rolle mehr.

**Einmalig für Installationen vor dem Update-Button:** im geklonten Repo `git pull` und `sudo ./install.sh`. Danach geht es per Button.

| Option | Wirkung |
|---|---|
| `--mode full` / `--mode api` | komplett mit Webportal / nur die Modelle mit ihren APIs (siehe oben) |
| `--mode api --teilen` | Spark teilen, Modell-Rechner: nur die Modelle, Dienste nur auf 127.0.0.1, dazu TLS-Tor, Wärter, Firewall und ein eigenes Zertifikat der Tür (`tor-cert.pem`); zeigt am Ende den Kopplungscode |
| `--mode panel --modelle <name-oder-ip>` | Spark teilen, Panel-Rechner (z. B. Raspberry Pi 5): nur das Panel mit `venv-panel` und coturn, kein Modell, keine Engine; prüft 64 Bit und Python ≥ 3.11, fragt nach dem Code (oder `SPEECH_SPARK_CODE`) und macht danach den Rundlauf |
| `--asr 1.7b\|0.6b\|parakeet\|none`, `--tts 0.6b\|1.7b\|none`, `--voicedesign` | Modelle ohne Rückfrage wählen |
| `--local` / `--network` | APIs nur auf `127.0.0.1` / im ganzen Netz (Standard) |
| `--yes` | nichts fragen; was nicht angegeben ist, bleibt wie es ist (neu: komplett) |
| `--small` | 0.6B-Modelle statt 1.7B (weniger Speicher) |
| `--tts-backend transformers` | TTS ohne Streaming über `qwen-tts` statt vllm-omni (Standard: `vllm-omni`) |
| `--asr-backend transformers` | ASR über `qwen-asr` statt vLLM, eine Anfrage nach der anderen (Standard: `vllm`) |
| `--no-asr` / `--no-tts` | nur einen der beiden Dienste installieren |
| `--password XYZ` | Panel-Passwort setzen (sonst wird eins erzeugt) |
| `--no-download` | Modelle erst beim ersten Start laden |
| `--no-smoke` | Rundlauf-Test am Ende überspringen |
| `--uninstall` | wie `./uninstall.sh` (siehe unten) |

Ein erneuter Aufruf aktualisiert den Code und ergänzt in den Python-Umgebungen, was fehlt; schon installierte Pakete bleiben, wie sie sind. Die bestehende Konfiguration bleibt erhalten, neue Einstellungen werden ergänzt.

## Bilder malen (optional)

Mit `--bild` installiert die Installation zusätzlich das Bildmodell FLUX.2 [klein] (nur mit dem Webportal; die erste Installation fragt danach, Standard ist keins, `sudo speech-spark models` fragt erneut):

```bash
sudo ./install.sh --bild 4b-q8   # 4B, Q8: ~9 GB Platte, ~11 GiB beim Malen, Apache 2.0 (empfohlen)
sudo ./install.sh --bild 4b-q4   # 4B, Q4: weniger Speicher (~12 GiB)
sudo ./install.sh --bild 9b-q8   # 9B (auch 9b-q4): FLUX Non-Commercial, nur privat
sudo ./install.sh --bild none    # wieder aus (die Dateien bleiben in /var/lib/speech-spark/models/bild)
```

**Eigenes Sprachmodell (vorbereiten, ab V01.0.590):** `sudo ./install.sh --llm` legt `venv-llm` mit vLLM für das eigene Sprachmodell an, `sudo ./install.sh --kolibri` dazu `venv-kolibri` (vLLM 0.29 mit dem Aleph-Alpha-Plugin, fest über seine Prüfsumme). Beides bleibt bei jedem Update aktuell. Die Dienste `speech-spark-llm`, `speech-spark-llmtor` und `speech-spark-sehen` sind eingerichtet, laufen aber erst, wenn `sudo speech-spark modelle llm uebernehmen` (Stufe E3) das eigene Modell einschaltet; bis dahin bleibt qwen38 das Sprachmodell. Logs: `sudo speech-spark logs llm`, `llmtor`, `sehen`.

Sie baut einmal stable-diffusion.cpp (`sd-server`, fester Commit, CUDA für den GB10, braucht `nvcc` und `cmake`) nach `/opt/speech-spark/sdcpp`, lädt die Modelldateien mit SHA-256-Prüfung nach `/var/lib/speech-spark/models/bild` und richtet den Dienst `speech-spark-bild` ein (nur `127.0.0.1`, Ports `image.port` 31005 und `image.engine_port` 31015). Das Modell belegt nur beim Malen Speicher. Danach im Portal Funktionen → Bilder malen einschalten und „Bild testen“ drücken. Einzelheiten: [Assistent](assistent.md).

## Musik machen (optional)

Mit `--musik` installiert die Installation zusätzlich das Musikmodell ACE-Step 1.5 (MIT-Lizenz; auf dem Modell-Rechner, beim Teilen mit `--teilen`; die erste Installation fragt danach, Standard ist keins, `sudo speech-spark models` fragt erneut):

```bash
sudo ./install.sh --musik 2b         # 2B turbo + 1,7B-Planer: ~5,6 GB Platte, ~14 GiB beim Musikmachen (empfohlen)
sudo ./install.sh --musik 2b-klein   # 2B turbo + 0,6B-Planer: weniger Speicher
sudo ./install.sh --musik xl         # XL turbo (4B) + 1,7B: klingt besser, ~5,3 GB mehr Platte, ~20 GiB
sudo ./install.sh --musik none       # wieder aus (die Dateien bleiben in /var/lib/speech-spark/models/musik)
```

Sie baut einmal acestep.cpp (`ace-server`, fester Commit, ggml fest eingebunden, CUDA für den GB10, ohne torch und ohne Docker, braucht `nvcc` und `cmake`) nach `/opt/speech-spark/acestep`, lädt die GGUF-Dateien mit SHA-256-Prüfung nach `/var/lib/speech-spark/models/musik` und richtet den Dienst `speech-spark-musik` ein (nur `127.0.0.1`, beim Teilen über das TLS-Tor; Ports `music.port` 31004 und `music.engine_port` 31014). Die Engine lädt nur für ein Lied und gibt den Speicher nach 10 Minuten ohne Lied wieder frei; fehlt Speicher, lädt sie nicht. Mehrere Modelle nacheinander installieren geht, die Dateien bleiben alle. Zustand → Prüfen → „Musik testen“ misst jedes installierte Modell mit zwei festen Probestücken (30 s Klavier, 60 s mit deutschem Gesang) und zeigt Zeit, Speicher und die Stücke zum Anhören. Danach Funktionen → Musik machen einschalten und dort das Modell wählen; jedes freigegebene Profil macht dann Lieder im Gespräch und unter Ich → Musik. Logs: `sudo speech-spark logs musik`, Wartungspause: `sudo speech-spark pause musik 30`.

## Deinstallieren

```bash
sudo ./uninstall.sh            # Dienste, Code, venvs und sudoers-Regel entfernen; Konfig, Modelle und Stimmen bleiben
sudo ./uninstall.sh --purge    # zusätzlich Konfig, Modelle, Stimmen und den Benutzer speech löschen
sudo ./uninstall.sh --yes      # ohne Rückfrage
```

dgx-spark-qwen38 wird dabei nicht angefasst; das eigene Sprachmodell (`venv-llm`) entfernt `uninstall.sh` mit.
