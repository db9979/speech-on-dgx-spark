#!/usr/bin/env python3
"""Makes an interruption silent at once (run in the firmware workflow, before the build).

    patch_unterbrechen.py <xiaozhi dir>

Upstream XiaoZhi stops speaking on the wake word, but in the auto listening mode it first plays what is
still in its play queue (up to 1.2 s, more with the wait=true patch) and only then listens. Here the wake
word while speaking drops that queue right away, so the board is quiet at once and listens. What the
person says next goes to the Spark as usual; "Stopp" there ends without an answer (esp32.STOP_WORDS).
"""
import os
import sys

OLD = ("        } else {\n"
       "            // Play popup sound and start listening again\n"
       "            play_popup_on_listening_ = true;\n")
NEW = ("        } else {\n"
       "            // Spark: quiet at once, drop what is still queued for playing (firmware/patch_unterbrechen.py)\n"
       "            audio_service_.ResetDecoder();\n"
       "            // Play popup sound and start listening again\n"
       "            play_popup_on_listening_ = true;\n")


def main(src):
    path = os.path.join(src, "main", "application.cc")
    s = open(path, encoding="utf-8").read()
    if NEW in s:
        return
    assert s.count(OLD) == 1, f"{path}: wake word while speaking not found"
    open(path, "w", encoding="utf-8").write(s.replace(OLD, NEW))


if __name__ == "__main__":
    main(sys.argv[1])
