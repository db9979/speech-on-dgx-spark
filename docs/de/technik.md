# Technik und Fehlersuche

← [README](../../README.de.md)

## Was installiert wird

| Teil | Wo | Port |
|---|---|---|
| Knacken oder abgeschnittene Wortenden im Assistenten | Seit V01.0.124 blendet der Browser jedes Ende und jeden Aussetzer 5 ms lang aus. Bleibt ein Wort abgeschnitten, liegt es an der Engine selbst: denselben Text über Telegram oder `curl` an Port 31012 (ohne Streaming) anhören. Zeigt der Assistent unter der Antwort „Aussetzer bei …“, kam die Sprachausgabe nicht nach. |
| ASR-Dienst `speech-spark-asr` (nimmt Anfragen an, reicht sie an die Engine durch) | `/opt/speech-spark/venv-panel` | 31001 |
| ASR-Engine `speech-spark-asr-engine` (vLLM) | `/opt/speech-spark/venv-engine` | 31011, nur lokal |
| TTS-Dienst `speech-spark-tts` (nimmt Anfragen an, reicht sie an die Engine durch) | `/opt/speech-spark/venv-panel` | 31002 |
| TTS-Engine `speech-spark-tts-engine` (vllm-omni) | `/opt/speech-spark/venv-engine` | 31012, nur lokal |
| optional VoiceDesign-Engine `speech-spark-tts-design` | `/opt/speech-spark/venv-engine` | 31013, nur lokal |
| Update `speech-spark-update` (läuft nur auf Knopfdruck) | `/opt/speech-spark/src` | |
| Panel `speech-spark-panel` (nur komplett) | `/opt/speech-spark/venv-panel` | 31080, https 31443 |
| Wächter `speech-spark-watch` (nur ohne Portal) | `/opt/speech-spark/venv-panel` | |
| Befehl `speech-spark` | `/usr/local/bin` | |
| Messskript `speech-spark-bench` | `/usr/local/bin` | |
| Konfiguration | `/etc/speech-spark/config.json`, Installationsart in `mode`, Verbindungsdaten in `connection.txt`, Passwort in `panel.env` (ein im Panel geändertes Passwort liegt als Hash in `/var/lib/speech-spark/state/panel-password` und hat Vorrang) | |
| Modelle, geklonte Stimmen | `/var/lib/speech-spark/hf`, `/var/lib/speech-spark/voices` | |

Alle Dienste laufen als Systembenutzer `speech`. Per sudoers darf das Panel die Speech-Dienste und Engines starten, stoppen und neu starten und das Update anstoßen, sonst nichts.

## Leistung messen

Im Panel unter **Zustand → Prüfen → Leistung messen** oder auf der Konsole:

```bash
sudo speech-spark-bench                 # Zeit bis zum ersten Ton, Tempo einzeln und parallel, Speicher je Dienst
sudo speech-spark-bench --parallel 8    # mehr gleichzeitige Anfragen
sudo speech-spark-bench --audio a.wav   # Spracherkennung mit eigener Aufnahme
```

Seit V01.0.163 bekommt jeder Wert eine Stufe (sehr gut, gut, knapp, zu langsam) und einen Satz, ab wann er gut ist; oben steht ein Gesamturteil, und neben dem Wert die letzte Messung. Die Grenzen sind feste Regeln in `bench.rate()`:

| Wert | sehr gut | gut | knapp |
|---|---|---|---|
| Erster Ton (eine Anfrage) | bis 0,5 s | bis 1 s | bis 2 s |
| Tempo der Stimme | ab 2× Echtzeit | ab 1,3× | ab 1× (darunter stockt sie) |
| Mehrere gleichzeitig (gesamt / Anzahl) | ab 1,5 | ab 1 | ab 0,7 |
| Erster Ton bei mehreren (spätester) | bis 1 s | bis 1,5 s | bis 3 s |
| Testsatz erkannt in | bis 1,5 s | bis 3 s | bis 5 s |
| Richtig verstanden (Wörter des Testsatzes) | ab 95 % | ab 90 % | ab 85 % |
| Frei auf dem Spark | | ab 14 GiB | ab 10 GiB (darunter kritisch) |

„Richtig verstanden“ fehlt bei `--audio`, weil der Text der eigenen Aufnahme unbekannt ist. Die Kennzahlen der letzten zehn Messungen stehen in `bench-history.json`.

Die Messung geht über die öffentlichen Ports, misst also das, was Apps sehen. Das letzte Ergebnis steht in `/var/lib/speech-spark/state/bench-latest.json`. Die Speicheranteile der Engines (Konfiguration) sind Startwerte: nach der Messung passend einstellen.

## Neben dgx-spark-qwen38

- **Ports**: qwen38 nutzt 30000 bis 30099 (Engine 30000, Proxy 30001, Bild 30020, Video 30022, Cockpit 30090/30091). Speech nutzt 31001, 31002, 31080 und 31443 (Panel über https); die Engines auf 31011, 31012 und 31013 hören nur auf 127.0.0.1. Das Panel lehnt Ports im Bereich von qwen38 ab, und das Installationsskript bricht ab, wenn ein Port schon belegt ist.
- **Speicher**: Die GB10 hat einen gemeinsamen Pool von 128 GB für CPU und GPU. Die qwen38-Lanes reservieren davon einen festen Anteil: 50 % bei `stock`/`fp8`, 76 % im 1M-Modus und 85 % bei `flash`. Laut qwen38-Doku bleiben bei `flash` im Leerlauf nur ~16,6 GiB frei, und unter ~8 GiB beendet earlyoom von DGX OS Prozesse. Deshalb gilt:
  - Erkennt das Skript eine flash- oder 1M-Lane, wählt es automatisch die 0.6B-Modelle.
  - Bevor ein Dienst sein Modell lädt, prüft er, ob danach noch die Reserve frei bleibt (Standard 10 GiB). Wenn nicht, lädt er nicht und zeigt im Panel `blocked` mit Begründung.
  - Wird der Speicher trotzdem knapp, beendet das System zuerst die Speech-Dienste (`OOMScoreAdjust=900`), nicht die LLM-Lane und nicht sshd.
  - Speech startet nach den qwen38-Lanes, damit diese ihren festen Anteil zuerst belegen.
  - Die Engines starten nacheinander, weil vLLM beim Start den freien Speicher misst und parallele Starts sich gegenseitig den Anteil wegnehmen.
- **Lane-Wechsel**: Wechselst du im Cockpit auf `flash`, bleiben die schon geladenen Speech-Modelle im Speicher. Mit 1.7B-Modellen kann das zu knapp werden. Dann vorher ASR und TTS im Panel stoppen oder auf 0.6B umstellen.
- **GPU-Zeit**: ASR und TTS teilen sich die GPU mit dem LLM. Während einer Transkription oder Sprachausgabe wird das LLM etwas langsamer.

## Warum die Installation so aussieht

- **PyTorch aus dem cu130-Index**: Das aarch64-torch auf PyPI hat kein CUDA. Ein einfaches `pip install qwen-tts` würde also auf der CPU laufen. torch und torchaudio müssen außerdem aus demselben Index kommen, sonst lädt `libtorchaudio.so` nicht.
- **Kein flash-attn**: Es gibt kein ARM-Wheel, und für sm_121 lässt es sich laut Berichten nicht bauen. Beide Modelle laufen stattdessen mit PyTorch-SDPA.
- **Getrennte venvs**: qwen-asr verlangt `transformers==4.57.6`, qwen-tts `transformers==4.57.3`.
- **ASR mit vLLM**: vLLM 0.30 kann Qwen3-ASR selbst, mit `/v1/audio/transcriptions`, Streaming und mehreren Anfragen gleichzeitig. Es läuft in derselben Umgebung wie die TTS-Engine. `qwen-asr[vllm]` wird nicht gebraucht (es würde vllm 0.14 erzwingen).
- **TTS mit vllm-omni**: `qwen-tts` kann nicht stückweise ausgeben. Das Qwen-Team verweist für Streaming auf vllm-omni. vllm 0.30.0 und vllm-omni 0.30.0 haben ARM-Pakete auf PyPI (CUDA 13) und werden nativ in einer eigenen Umgebung installiert, ohne Docker.
- **Engine-Speicher**: vLLM reserviert beim Start einen festen Anteil des *gesamten* Speicherpools, bei TTS pro Stufe (Talker und Code2Wav) getrennt. Die Voreinstellungen (ASR 1.7B 0,06, 0.6B 0,035; TTS 0,04 + 0,025) sind knapp gewählt, damit Speech neben der qwen38-`stock`-Lane Platz findet. Ist ein Anteil zu klein, bricht die Engine beim Start mit „No available memory for the cache blocks“ ab. Dann im Panel den Anteil erhöhen.

## Aufbau des Chats

Eine Antwort des Assistenten läuft in drei Dateien unter `app/panel/`:

- `chat_turn.py` (`prepare`): wer spricht und was er darf (Profil, erkannte Stimme, Geräteschlüssel, Telegram, iPhone-App), der Systemprompt, Antworten auf wartende Vorschläge („Ja“ zu Termin, Mail, Korrektur …), die angebotenen Werkzeuge und die Sperren nach fremdem Text. Ergebnis ist ein `Turn` mit allen Werten.
- `chat_tools.py` (`run`): was beim Aufruf eines Werkzeugs passiert (Websuche, Home Assistant, Mail, Kalender, Erinnerungen …). Nur angebotene Werkzeuge laufen, die Sperren werden hier noch einmal geprüft.
- `chat.py` (`_answer`): fragt das Sprachmodell in Runden, führt Werkzeugaufrufe über `chat_tools.run` aus, prüft die Antwort und streamt Text und Ton. Werkzeug-Definitionen und Sperrlisten (`READS_OUTSIDE`, `LOCKED_OUTSIDE` …) stehen weiter in `chat.py`.

Neue Rechte oder Hinweise gehören nach `chat_turn.py`, neue Werkzeuge nach `chat_tools.py` (Definition und Sperrliste in `chat.py`).

## Tests

`app/tests/` enthält die Selbsttests, die bei jedem Update laufen (`cd app && python -m unittest discover -s tests`). Alle Dienste sind dabei nachgebaut (`tests/helpers.py`), kein Test spricht echte Modelle oder Home Assistant an. `tests/test_ui_browser.py` öffnet das Panel zusätzlich in Chromium (Playwright) am Rechner und in Handybreite: jede Seite ohne Skriptfehler und ohne seitliches Scrollen, die Einstellungssuche, das Ich-Fenster. Ohne Playwright (wie im Selbsttest auf dem Spark) wird er übersprungen; auf GitHub läuft er im Workflow „Tests“ bei jedem Push.

## Fehlersuche

| Symptom | Lösung |
|---|---|
| Installer: „torch in venv-… has no CUDA“ | `sudo ./install.sh` erneut ausführen. Hilft das nicht, `/opt/speech-spark/venv-*` löschen und neu installieren. |
| Panel zeigt `blocked` | Zu wenig Speicher neben der laufenden qwen38-Lane. Auf 0.6B umstellen, die Reserve senken (auf eigenes Risiko) oder die große Lane stoppen. |
| Panel zeigt `error` | Fehlertext im Panel und unter Logs ansehen. |
| `no kernel image is available` | Ein Paket wurde ohne Blackwell-Kernel gebaut. Prüfen mit `/opt/speech-spark/venv-asr/bin/python -c "import torch; print(torch.cuda.get_arch_list())"`. |
| TTS-Engine startet nicht | Panel → Logs → TTS-Engine. Bei „not enough KV cache“ o. Ä. die Speicheranteile der Engine im Panel erhöhen. Der erste Start lädt das Modell und dauert länger. |
| Update schlägt fehl | Panel → Zustand → System und Update → Update-Protokoll. Die alte Version läuft weiter oder wird wieder eingespielt; das Protokoll sagt, was passiert ist. |
| Port belegt | Port in `/etc/speech-spark/config.json` ändern und das Skript erneut ausführen. |

Die Speicherschätzungen pro Modell (`MODEL_GIB` in `app/common.py`) sind grobe Annahmen und noch nicht auf einer Spark gemessen. Nach dem ersten Lauf sollten sie mit den Werten aus dem Panel korrigiert werden.
