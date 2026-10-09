"""Writes the App Store Connect API key from the secret ASC_KEY as a clean .p8 (PEM) file.

GitHub secrets often lose the line breaks or get pasted with \\n, Windows line ends, without the
BEGIN/END lines or as base64 of the whole file. All of these are accepted; the key itself never goes
to the log, only what was wrong with it.

    python3 asc_key.py pem  OUT     the .p8 for xcodebuild
    python3 asc_key.py json OUT     the JSON file for fastlane (with ASC_KEY_ID, ASC_ISSUER_ID)
"""
import base64
import binascii
import json
import os
import re
import sys

HEAD, FOOT = "-----BEGIN PRIVATE KEY-----", "-----END PRIVATE KEY-----"


def fail(msg):
    print(f"::error::ASC_KEY: {msg} (see docs/de/iphone-veroeffentlichen.md)")
    sys.exit(1)


def body_of(raw):
    s = raw.replace("\\n", "\n").replace("\r", "").strip().strip('"').strip("'")
    if "BEGIN" not in s:
        # maybe base64 of the whole .p8 file
        try:
            inner = base64.b64decode(re.sub(r"\s+", "", s), validate=True).decode("ascii")
            if "BEGIN PRIVATE KEY" in inner:
                s = inner
        except (binascii.Error, UnicodeDecodeError, ValueError):
            pass
    if "BEGIN" in s and "BEGIN PRIVATE KEY" not in s:
        fail("this is not an App Store Connect key (.p8 starts with BEGIN PRIVATE KEY)")
    s = re.sub(r"-----(BEGIN|END) PRIVATE KEY-----", "", s)
    s = re.sub(r"\s+", "", s)
    if not s:
        fail("empty")
    if not re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", s):
        fail("contains characters that do not belong in a .p8 file")
    try:
        der = base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError):
        fail("incomplete, the text of the .p8 file is cut off")
    if len(der) < 100 or der[0] != 0x30:
        fail(f"incomplete or not a key ({len(der)} bytes); copy the whole .p8 file")
    return s


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("pem", "json"):
        fail("usage: asc_key.py pem|json OUT")
    body = body_of(os.environ.get("ASC_KEY", ""))
    pem = HEAD + "\n" + "\n".join(body[i:i + 64] for i in range(0, len(body), 64)) + "\n" + FOOT + "\n"
    out = sys.argv[2]
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        if sys.argv[1] == "pem":
            f.write(pem)
        else:
            json.dump({"key_id": os.environ["ASC_KEY_ID"].strip(), "issuer_id": os.environ["ASC_ISSUER_ID"].strip(),
                       "key": pem, "in_house": False}, f)
    print("ASC_KEY ok")


if __name__ == "__main__":
    main()
