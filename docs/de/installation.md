# Installation im Detail

← [README](../../README.de.md)

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
| `sudo speech-spark logs tts -n 100` | letzte Log-Zeilen (asr, tts, asr-engine, tts-engine, tts-design, watch, update, all) |
| `sudo speech-spark panel enable` | Webportal nachrüsten; Modelle und API-Schlüssel bleiben |
| `sudo speech-spark panel disable` | Webportal entfernen; Profile und Daten bleiben auf der Platte |

Den Wächter für hängende Dienste, der sonst im Portal läuft, übernimmt ohne Portal der Dienst `speech-spark-watch` mit denselben Regeln. Nach einem Update spricht die Sprachausgabe einen Satz, und die Spracherkennung muss ihn verstehen; klappt das nicht, spielt das Update die vorige Version wieder ein. Die Selbsttests laufen in beiden Arten vor jedem Update. Das Chat-Modell (qwen38) gehört nicht zu diesem Repo und bleibt davon unberührt. Läuft Open WebUI in Docker auf derselben Spark, müssen die APIs im Netz erreichbar sein (`127.0.0.1` im Container ist der Container selbst).

## Aktualisieren

Im Panel unter **System**: Dort steht die installierte Version, und es wird angezeigt, wenn auf GitHub eine neuere liegt (mit der Liste der Änderungen). **Update installieren** holt den neuen Stand und installiert ihn. Einstellungen, Modelle und Stimmen bleiben, das Protokoll läuft live mit. Schon installierte Pakete werden dabei nicht aktualisiert; nachgeladen wird nur, was die neue Version braucht. Bevor die neue Version live geht, läuft der Selbsttest. Schlägt er oder ein Schritt davor fehl (Download, Pakete), bricht das Update ab, und die Dienste laufen unverändert mit der alten Version weiter. Geht nach dem Umschalten etwas schief, spielt `update.sh` die vorige Version wieder ein und sagt das im Protokoll. Während das Update läuft, sperrt ein Fortschrittsfenster das Panel (auch andere Tabs und Handys: der Server nimmt keine Änderungen an, der Assistent antwortet weiter); über den Neustart des Panels verbindet sich die Seite neu und lädt am Ende von selbst. Ist es nach 20 Minuten nicht fertig, gibt es „Neu laden“ und „Update abbrechen“.

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

## Deinstallieren

```bash
sudo ./uninstall.sh            # Dienste, Code, venvs und sudoers-Regel entfernen; Konfig, Modelle und Stimmen bleiben
sudo ./uninstall.sh --purge    # zusätzlich Konfig, Modelle, Stimmen und den Benutzer speech löschen
sudo ./uninstall.sh --yes      # ohne Rückfrage
```

dgx-spark-qwen38 wird dabei nicht angefasst.
