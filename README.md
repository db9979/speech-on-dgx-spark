# Speech auf DGX Spark

Ein Skript installiert **Qwen3-ASR** (Spracherkennung) und **Qwen3-TTS** (Sprachausgabe) als systemd-Dienste auf einer NVIDIA DGX Spark (GB10). Dazu kommt eine Weboberfläche für Konfiguration und Monitoring. Das Setup läuft neben [dgx-spark-qwen38](https://github.com/hasso5703/dgx-spark-qwen38).

```bash
git clone https://github.com/db9979/speech-on-dgx-spark
cd speech-on-dgx-spark
sudo ./install.sh
```

Am Ende gibt das Skript die Adresse des Panels und das Passwort aus. Danach macht es einen Rundlauf-Test: TTS spricht einen Satz, ASR transkribiert ihn wieder.

| Option | Wirkung |
|---|---|
| `--small` | 0.6B-Modelle statt 1.7B (weniger Speicher) |
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
| TTS-Dienst `speech-spark-tts` | `/opt/speech-spark/venv-tts` | 31002 |
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
  -d '{"input":"Hallo Welt","voice":"Ryan","language":"German"}' -o hallo.wav
```

`GET /health` liefert bei beiden Diensten Status und Zähler, `GET /v1/voices` (TTS) die verfügbaren Stimmen, `GET /v1/models` das geladene Modell.

Die Dienste verhalten sich wie die OpenAI-Audio-API: TTS liefert standardmäßig mp3 (auch wav, flac, opus, pcm), STT versteht `response_format=text`, und die Sprache darf ein ISO-Code wie `de` sein. OpenAI-Stimmnamen wie `alloy` landen bei der Standardstimme. Ist im Panel ein API-Schlüssel gesetzt, müssen Apps `Authorization: Bearer <Schlüssel>` senden.

### Open WebUI

Admin-Panel → Einstellungen → Audio:

| Feld | STT | TTS |
|---|---|---|
| Engine | OpenAI | OpenAI |
| API Base URL | `http://SPARK:31001/v1` | `http://SPARK:31002/v1` |
| API Key | Schlüssel aus dem Panel oder beliebig | dito |
| Modell | beliebig | beliebig |
| Stimme | | z. B. `Ryan` |

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
- **Kein vLLM**: `qwen-asr[vllm]` erzwingt vllm 0.14 mit torch 2.9.1 und zieht auf ARM wieder das CPU-torch. Für die Modellgrößen hier reicht das transformers-Backend.

## Fehlersuche

| Symptom | Lösung |
|---|---|
| Installer: „torch in venv-… has no CUDA“ | `sudo ./install.sh` erneut ausführen. Hilft das nicht, `/opt/speech-spark/venv-*` löschen und neu installieren. |
| Panel zeigt `blocked` | Zu wenig Speicher neben der laufenden qwen38-Lane. Auf 0.6B umstellen, die Reserve senken (auf eigenes Risiko) oder die große Lane stoppen. |
| Panel zeigt `error` | Fehlertext im Panel und unter Logs ansehen. |
| `no kernel image is available` | Ein Paket wurde ohne Blackwell-Kernel gebaut. Prüfen mit `/opt/speech-spark/venv-asr/bin/python -c "import torch; print(torch.cuda.get_arch_list())"`. |
| Port belegt | Port in `/etc/speech-spark/config.json` ändern und das Skript erneut ausführen. |

Die Speicherschätzungen pro Modell (`MODEL_GIB` in `app/common.py`) sind grobe Annahmen und noch nicht auf einer Spark gemessen. Nach dem ersten Lauf sollten sie mit den Werten aus dem Panel korrigiert werden.
