#!/usr/bin/env python3
""""Stopp beim Vorlesen" (run in the firmware workflow, before the build).

    patch_stoppwort.py <xiaozhi dir>

Upstream XiaoZhi turns the microphone off while it speaks (only the wake word listens there). With this
patch the own Spark can ask a board to keep its microphone on while speaking: the MCP tool
"self.spark.stop_word" {"on": true} (sent by esp32.py at every connection when the admin and the profile
switched "Stopp beim Vorlesen" on). Only boards with a playback reference channel do it (their echo
cancelling takes the own voice out, e.g. the Waveshare ESP32-S3-AUDIO-Board); the others keep the mic off.
The Spark decides with a fixed word list whether "Stopp" was said and then sends {"type": "tts", "state":
"stop", "spark_quiet": true}: the board drops what is still queued for playing and listens.
The flag lives only in memory: after a restart the board is as upstream until the Spark asks again.
"""
import os
import sys

MARK = "firmware/patch_stoppwort.py"


def edit(path, old, new):
    s = open(path, encoding="utf-8").read()
    if new in s:
        return
    assert s.count(old) == 1, f"{path}: expected 1x {old!r}"
    open(path, "w", encoding="utf-8").write(s.replace(old, new))


def main(src):
    app_h = os.path.join(src, "main", "application.h")
    app_cc = os.path.join(src, "main", "application.cc")
    edit(app_h, "    void SetAecMode(AecMode mode);\n",
         "    void SetAecMode(AecMode mode);\n    void SetSparkStopWord(bool on);\n")
    edit(app_h, "    bool aborted_ = false;\n",
         "    bool aborted_ = false;\n    bool spark_stop_word_ = false;  // " + MARK + "\n")
    # while speaking: the microphone stays on (echo cancelled) when the Spark asked for it
    edit(app_cc,
         "            if (listening_mode_ != kListeningModeRealtime) {\n"
         "                audio_service_.EnableVoiceProcessing(false);\n",
         "            if (listening_mode_ != kListeningModeRealtime && spark_stop_word_ &&\n"
         "                audio_service_.IsAudioProcessorRunning() && board.GetAudioCodec()->input_reference()) {\n"
         "                // Spark: microphone stays on while speaking, the Spark listens for \"Stopp\" (" + MARK + ")\n"
         "                audio_service_.EnableWakeWordDetection(audio_service_.IsAfeWakeWord());\n"
         "            } else if (listening_mode_ != kListeningModeRealtime) {\n"
         "                audio_service_.EnableVoiceProcessing(false);\n")
    # the Spark heard "Stopp": quiet at once instead of playing the queue empty
    edit(app_cc,
         "            } else if (strcmp(state->valuestring, \"stop\") == 0) {\n"
         "                Schedule([this]() {\n"
         "                    if (GetDeviceState() == kDeviceStateSpeaking) {\n",
         "            } else if (strcmp(state->valuestring, \"stop\") == 0) {\n"
         "                bool spark_quiet = cJSON_IsTrue(cJSON_GetObjectItem(root, \"spark_quiet\"));\n"
         "                Schedule([this, spark_quiet]() {\n"
         "                    if (spark_quiet && GetDeviceState() == kDeviceStateSpeaking) {\n"
         "                        audio_service_.ResetDecoder();  // Spark heard \"Stopp\" (" + MARK + ")\n"
         "                    }\n"
         "                    if (GetDeviceState() == kDeviceStateSpeaking) {\n")
    s = open(app_cc, encoding="utf-8").read()
    if "void Application::SetSparkStopWord(" not in s:
        with open(app_cc, "a", encoding="utf-8") as f:
            f.write("""
// "Stopp beim Vorlesen": the own Spark asks to keep the microphone on while speaking (firmware/patch_stoppwort.py)
void Application::SetSparkStopWord(bool on) {
    Schedule([this, on]() {
        spark_stop_word_ = on;
        ESP_LOGI(TAG, "Spark stop word %s", on ? "on" : "off");
    });
}
""")
    mcp = os.path.join(src, "main", "mcp_server.cc")
    edit(mcp, "    auto backlight = board.GetBacklight();\n",
         "    AddTool(\"self.spark.stop_word\",\n"
         "            \"Only for the own Spark server: keep the echo-cancelled microphone on while speaking.\",\n"
         "            PropertyList({Property(\"on\", kPropertyTypeBoolean)}),\n"
         "            [](const PropertyList& properties) -> ReturnValue {\n"
         "                Application::GetInstance().SetSparkStopWord(properties[\"on\"].value<bool>());\n"
         "                return true;\n"
         "            });   // " + MARK + "\n\n"
         "    auto backlight = board.GetBacklight();\n")


if __name__ == "__main__":
    main(sys.argv[1])
