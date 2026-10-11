#!/usr/bin/env python3
"""Adds the Notaus button to the XiaoZhi source (run in the firmware workflow, before the build).

    patch_notaus.py <xiaozhi dir> <board dir under main/boards>

Holding the board's BOOT button for 5 seconds sends the fixed wake word "spark-notaus" to the own Spark
({"type": "listen", "state": "detect", "text": "spark-notaus"}). Only the firmware sends that text (the wake
word engine, never speech recognition); the Spark decides what it may do (esp32.py: the big Notaus, stage 2,
only for a speaker of an admin profile). A short press stays what it was.
"""
import glob
import os
import sys

WORD = "spark-notaus"


def edit(path, old, new, count=1):
    s = open(path, encoding="utf-8").read()
    if new in s:
        return
    assert s.count(old) == count, f"{path}: expected {count}x {old!r}"
    open(path, "w", encoding="utf-8").write(s.replace(old, new))


def main(src, board):
    common = os.path.join(src, "main", "boards", "common")
    # Button::OnHold: a long press with its own time, beside the board's own long press (iot_button ~4.2)
    edit(os.path.join(common, "button.h"), "    void OnMultipleClick(std::function<void()> callback, uint8_t click_count = 3);\n",
         "    void OnMultipleClick(std::function<void()> callback, uint8_t click_count = 3);\n"
         "    void OnHold(std::function<void()> callback, uint16_t press_ms);\n")
    edit(os.path.join(common, "button.h"), "    std::function<void()> on_multiple_click_;\n",
         "    std::function<void()> on_multiple_click_;\n    std::function<void()> on_hold_;\n")
    with open(os.path.join(common, "button.cc"), "a", encoding="utf-8") as f:
        f.write("""
// the Spark's Notaus button (firmware/patch_notaus.py)
void Button::OnHold(std::function<void()> callback, uint16_t press_ms) {
    if (button_handle_ == nullptr) {
        return;
    }
    on_hold_ = callback;
    button_event_args_t event_args = {
        .long_press = {
            .press_time = press_ms
        }
    };
    iot_button_register_cb(button_handle_, BUTTON_LONG_PRESS_START, &event_args, [](void* handle, void* usr_data) {
        Button* button = static_cast<Button*>(usr_data);
        if (button->on_hold_) {
            button->on_hold_();
        }
    }, this);
}
""")
    app_h = os.path.join(src, "main", "application.h")
    edit(app_h, "    void WakeWordInvoke(const std::string& wake_word);\n",
         "    void WakeWordInvoke(const std::string& wake_word);\n    void SparkNotaus();\n")
    with open(os.path.join(src, "main", "application.cc"), "a", encoding="utf-8") as f:
        f.write(f"""
// the Spark's Notaus button: tell the own Spark, whatever the device is doing (firmware/patch_notaus.py)
void Application::SparkNotaus() {{
    Schedule([this]() {{
        if (!protocol_) {{
            return;
        }}
        if (!protocol_->IsAudioChannelOpened() && !protocol_->OpenAudioChannel()) {{
            return;
        }}
        ESP_LOGW(TAG, "Notaus button held");
        protocol_->SendWakeWordDetected("{WORD}");
    }});
}}
""")
    files = glob.glob(os.path.join(src, "main", "boards", board, "*.cc"))
    hit = 0
    for p in files:
        s = open(p, encoding="utf-8").read()
        if "void InitializeButtons() {\n" in s and "boot_button_" in s:
            edit(p, "    void InitializeButtons() {\n",
                 "    void InitializeButtons() {\n"
                 "        boot_button_.OnHold([]() { Application::GetInstance().SparkNotaus(); }, 5000);   // Spark Notaus\n")
            hit += 1
    assert hit == 1, f"{board}: InitializeButtons with boot_button_ found {hit}x"


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
