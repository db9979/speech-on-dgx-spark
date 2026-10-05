# Speech auf DGX Spark

Ein Skript installiert **Qwen3-ASR** (Spracherkennung) und **Qwen3-TTS** (Sprachausgabe) als systemd-Dienste auf einer NVIDIA DGX Spark (GB10). Dazu kommt eine Weboberfläche für Konfiguration und Monitoring. Das Setup läuft neben [dgx-spark-qwen38](https://github.com/hasso5703/dgx-spark-qwen38).

```bash
git clone https://github.com/db9979/speech-on-dgx-spark
cd speech-on-dgx-spark
sudo ./install.sh
```

Am Ende gibt das Skript die Adresse des Panels, das Passwort und den API-Schlüssel aus. Danach macht es einen Rundlauf-Test: TTS spricht einen Satz (auch gestreamt, mit Zeit bis zum ersten Ton), ASR transkribiert ihn wieder. Alles läuft nativ als systemd-Dienste, ohne Docker.

## Aktualisieren

Im Panel unter **System**: Dort steht die installierte Version, und es wird angezeigt, wenn auf GitHub eine neuere liegt (mit der Liste der Änderungen). **Update installieren** holt den neuen Stand und installiert ihn. Einstellungen, Modelle und Stimmen bleiben, das Protokoll läuft live mit. Schlägt die Installation fehl, laufen die Dienste mit der alten Version weiter.

Auf der Konsole geht dasselbe mit:

```bash
sudo /opt/speech-spark/src/update.sh           # aktualisieren
sudo /opt/speech-spark/src/update.sh --check   # nur anzeigen, was neu ist
```

Der Installer legt dafür eine eigene Git-Kopie unter `/opt/speech-spark/src` an. Wo du das Repo ursprünglich geklont hast, spielt danach keine Rolle mehr.

**Einmalig für Installationen vor dem Update-Button:** im geklonten Repo `git pull` und `sudo ./install.sh`. Danach geht es per Button.

| Option | Wirkung |
|---|---|
| `--small` | 0.6B-Modelle statt 1.7B (weniger Speicher) |
| `--tts-backend transformers` | TTS ohne Streaming über `qwen-tts` statt vllm-omni (Standard: `vllm-omni`) |
| `--no-asr` / `--no-tts` | nur einen der beiden Dienste installieren |
| `--password XYZ` | Panel-Passwort setzen (sonst wird eins erzeugt) |
| `--no-download` | Modelle erst beim ersten Start laden |
| `--no-smoke` | Rundlauf-Test am Ende überspringen |
| `--uninstall` | wie `./uninstall.sh` (siehe unten) |

Ein erneuter Aufruf aktualisiert Code und Python-Umgebungen. Die bestehende Konfiguration bleibt erhalten, neue Einstellungen werden ergänzt.

## Deinstallieren

```bash
sudo ./uninstall.sh            # Dienste, Code, venvs und sudoers-Regel entfernen; Konfig, Modelle und Stimmen bleiben
sudo ./uninstall.sh --purge    # zusätzlich Konfig, Modelle, Stimmen und den Benutzer speech löschen
sudo ./uninstall.sh --yes      # ohne Rückfrage
```

dgx-spark-qwen38 wird dabei nicht angefasst.

## Was installiert wird

| Teil | Wo | Port |
|---|---|---|
| ASR-Dienst `speech-spark-asr` | `/opt/speech-spark/venv-asr` | 31001 |
| TTS-Dienst `speech-spark-tts` (nimmt Anfragen an, reicht sie an die Engine durch) | `/opt/speech-spark/venv-panel` | 31002 |
| TTS-Engine `speech-spark-tts-engine` (vllm-omni) | `/opt/speech-spark/venv-engine` | 31012, nur lokal |
| optional VoiceDesign-Engine `speech-spark-tts-design` | `/opt/speech-spark/venv-engine` | 31013, nur lokal |
| Update `speech-spark-update` (läuft nur auf Knopfdruck) | `/opt/speech-spark/src` | |
| Panel `speech-spark-panel` | `/opt/speech-spark/venv-panel` | 31080 |
| Konfiguration | `/etc/speech-spark/config.json`, Passwort in `panel.env` | |
| Modelle, geklonte Stimmen | `/var/lib/speech-spark/hf`, `/var/lib/speech-spark/voices` | |

Alle Dienste laufen als Systembenutzer `speech`. Per sudoers darf das Panel genau diese beiden Dienste starten, stoppen und neu starten, sonst nichts.

## Die Oberfläche

- **Monitoring**: GPU-Auslastung, freier Unified Memory, Temperatur und Leistung, CPU, jeweils mit Verlauf. Für jeden Dienst gibt es Status, Anfragen, Latenz und Echtzeitfaktor (RTF) sowie Start, Stopp und Neustart. Außerdem siehst du, welche dgx-spark-qwen38-Lane gerade läuft und welchen Anteil des Speichers sie belegt.
- **Konfiguration**: Modell, Port, Standardsprache, Stimme, Zeitstempel und Speicherreserve. Beim Speichern werden die betroffenen Dienste neu gestartet.
- **Testen**: eine Audiodatei hochladen und transkribieren lassen oder Text eingeben und anhören.
- **Stimmen**: Referenzaufnahmen zum Klonen verwalten (nur mit einem `Base`-TTS-Modell).
- **Einbinden**: fertige Werte zum Kopieren für Open WebUI und andere OpenAI-kompatible Apps, dazu Beispiele für curl und Python.
- **Logs**: journald-Ausgabe der Dienste.

## APIs (OpenAI-ähnlich)

```bash
# Transkription
curl http://SPARK:31001/v1/audio/transcriptions -F file=@aufnahme.wav -F language=German
# -> {"text": "...", "language": "German", "duration": 4.2, "processing_s": 0.6}

# Sprachausgabe
curl http://SPARK:31002/v1/audio/speech -H 'Content-Type: application/json' \
  -d '{"input":"Hallo Welt","voice":"ryan","language":"German"}' -o hallo.mp3
```

`GET /health` liefert bei beiden Diensten Status und Zähler, `GET /v1/voices` (TTS) die verfügbaren Stimmen, `GET /v1/models` das geladene Modell.

### Gestreamte Sprachausgabe

Mit `"stream": true` (und `"response_format": "pcm"`, das ist dann der Standard) kommt die Antwort als Server-Sent Events, sobald die ersten Laute erzeugt sind:

```
event: speech.audio.delta
data: {"type": "speech.audio.delta", "audio": "<base64>", "response_format": "pcm"}
...
event: speech.audio.done
data: {"type": "speech.audio.done", "usage": {...}}
```

`audio` ist PCM, 16 bit, mono, 24 kHz. Bei einem Fehler kommt `speech.audio.error`. Das ist das Format von vllm-omni, der Dienst reicht es unverändert durch.

```bash
curl -N http://SPARK:31002/v1/audio/speech -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"input":"Hallo Welt","voice":"ryan","language":"German","stream":true,"response_format":"pcm"}'
```

**VoiceDesign** (Stimme per Beschreibung): `"task_type": "VoiceDesign"` und `"instructions": "tiefe, ruhige Männerstimme"`. Dafür braucht es ein eigenes Modell. Im Panel unter Konfiguration → TTS „VoiceDesign zusätzlich bereitstellen“ einschalten. Das startet eine zweite Engine mit nochmal demselben Speicherbedarf.

Im Panel unter **Testen** spielt „gestreamt“ den Ton schon während der Erzeugung ab und zeigt die Zeit bis zum ersten Ton.

### Allgemein

Die Dienste verhalten sich wie die OpenAI-Audio-API: TTS liefert standardmäßig mp3 (auch wav, flac, opus, pcm), STT versteht `response_format=text`, und die Sprache darf ein ISO-Code wie `de` sein. OpenAI-Stimmnamen wie `alloy` landen bei der Standardstimme. Ist im Panel ein API-Schlüssel gesetzt, müssen Apps `Authorization: Bearer <Schlüssel>` senden.

### Open WebUI

Admin-Panel → Einstellungen → Audio:

| Feld | STT | TTS |
|---|---|---|
| Engine | OpenAI | OpenAI |
| API Base URL | `http://SPARK:31001/v1` | `http://SPARK:31002/v1` |
| API Key | Schlüssel aus dem Panel oder beliebig | dito |
| Modell | beliebig | beliebig |
| Stimme | | z. B. `ryan` |

Läuft Open WebUI in Docker auf derselben Spark, statt `SPARK` entweder die LAN-IP oder `host.docker.internal` nehmen (Container mit `--add-host=host.docker.internal:host-gateway`). Das Panel zeigt diese Werte im Reiter „Einbinden“ zum Kopieren an.

## Neben dgx-spark-qwen38

- **Ports**: qwen38 nutzt 30000 bis 30099 (Engine 30000, Proxy 30001, Bild 30020, Video 30022, Cockpit 30090/30091). Speech nutzt 31001, 31002 und 31080. Das Panel lehnt Ports im Bereich von qwen38 ab, und das Installationsskript bricht ab, wenn ein Port schon belegt ist.
- **Speicher**: Die GB10 hat einen gemeinsamen Pool von 128 GB für CPU und GPU. Die qwen38-Lanes reservieren davon einen festen Anteil: 50 % bei `stock`/`fp8`, 76 % im 1M-Modus und 85 % bei `flash`. Laut qwen38-Doku bleiben bei `flash` im Leerlauf nur ~16,6 GiB frei, und unter ~8 GiB beendet earlyoom von DGX OS Prozesse. Deshalb gilt:
  - Erkennt das Skript eine flash- oder 1M-Lane, wählt es automatisch die 0.6B-Modelle.
  - Bevor ein Dienst sein Modell lädt, prüft er, ob danach noch die Reserve frei bleibt (Standard 10 GiB). Wenn nicht, lädt er nicht und zeigt im Panel `blocked` mit Begründung.
  - Wird der Speicher trotzdem knapp, beendet das System zuerst die Speech-Dienste (`OOMScoreAdjust=900`), nicht die LLM-Lane und nicht sshd.
  - Speech startet nach den qwen38-Lanes, damit diese ihren festen Anteil zuerst belegen.
- **Lane-Wechsel**: Wechselst du im Cockpit auf `flash`, bleiben die schon geladenen Speech-Modelle im Speicher. Mit 1.7B-Modellen kann das zu knapp werden. Dann vorher ASR und TTS im Panel stoppen oder auf 0.6B umstellen.
- **GPU-Zeit**: ASR und TTS teilen sich die GPU mit dem LLM. Während einer Transkription oder Sprachausgabe wird das LLM etwas langsamer.

## Warum die Installation so aussieht

- **PyTorch aus dem cu130-Index**: Das aarch64-torch auf PyPI hat kein CUDA. Ein einfaches `pip install qwen-tts` würde also auf der CPU laufen. torch und torchaudio müssen außerdem aus demselben Index kommen, sonst lädt `libtorchaudio.so` nicht.
- **Kein flash-attn**: Es gibt kein ARM-Wheel, und für sm_121 lässt es sich laut Berichten nicht bauen. Beide Modelle laufen stattdessen mit PyTorch-SDPA.
- **Getrennte venvs**: qwen-asr verlangt `transformers==4.57.6`, qwen-tts `transformers==4.57.3`.
- **ASR ohne vLLM**: `qwen-asr[vllm]` erzwingt vllm 0.14 mit torch 2.9.1 und zieht auf ARM wieder das CPU-torch. Für die Modellgröße reicht das transformers-Backend.
- **TTS mit vllm-omni**: `qwen-tts` kann nicht stückweise ausgeben. Das Qwen-Team verweist für Streaming auf vllm-omni. vllm 0.30.0 und vllm-omni 0.30.0 haben ARM-Pakete auf PyPI (CUDA 13) und werden nativ in einer eigenen Umgebung installiert, ohne Docker.
- **Engine-Speicher**: vLLM reserviert beim Start einen festen Anteil des *gesamten* Speicherpools, pro Stufe (Talker und Code2Wav) getrennt. Die Voreinstellung 0,05 + 0,05 (≈ 13 GiB inkl. Overhead) ist ein Startwert und noch nicht auf der Spark gemessen. Ist sie zu klein, bricht die Engine beim Start mit einem Hinweis im Log ab. Dann im Panel den Anteil erhöhen.

## Fehlersuche

| Symptom | Lösung |
|---|---|
| Installer: „torch in venv-… has no CUDA“ | `sudo ./install.sh` erneut ausführen. Hilft das nicht, `/opt/speech-spark/venv-*` löschen und neu installieren. |
| Panel zeigt `blocked` | Zu wenig Speicher neben der laufenden qwen38-Lane. Auf 0.6B umstellen, die Reserve senken (auf eigenes Risiko) oder die große Lane stoppen. |
| Panel zeigt `error` | Fehlertext im Panel und unter Logs ansehen. |
| `no kernel image is available` | Ein Paket wurde ohne Blackwell-Kernel gebaut. Prüfen mit `/opt/speech-spark/venv-asr/bin/python -c "import torch; print(torch.cuda.get_arch_list())"`. |
| TTS-Engine startet nicht | Panel → Logs → TTS-Engine. Bei „not enough KV cache“ o. Ä. die Speicheranteile der Engine im Panel erhöhen. Der erste Start lädt das Modell und dauert länger. |
| Update schlägt fehl | Panel → System → Update-Protokoll. Die alte Version läuft weiter. |
| Port belegt | Port in `/etc/speech-spark/config.json` ändern und das Skript erneut ausführen. |

Die Speicherschätzungen pro Modell (`MODEL_GIB` in `app/common.py`) sind grobe Annahmen und noch nicht auf einer Spark gemessen. Nach dem ersten Lauf sollten sie mit den Werten aus dem Panel korrigiert werden.
