"""Revokes the signing certificates one TestFlight run made for itself (V01.0.330).

Xcode's automatic signing makes a new certificate in every run, because the run's keychain is new and
empty; its private key dies with that keychain at the end of the run. Apple allows only a few per
account, so after some dozen runs signing stopped ("reached the maximum number of certificates").
This revokes exactly the certificates whose private key was in the run's own keychain: their serial
numbers come from that keychain, nothing else is touched. Builds already uploaded stay valid
(Apple signs TestFlight and App Store builds again with its own certificate).

    python3 asc_certs.py KEYCHAIN P8     (env ASC_KEY_ID, ASC_ISSUER_ID)

Standard library and the openssl and security commands only. The key and the token never go to the log.
"""
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "https://api.appstoreconnect.apple.com/v1/certificates"


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def der_to_raw(der):
    """ECDSA signature from openssl (DER SEQUENCE of two INTEGERs) to the 64 bytes r||s a JWT wants."""
    if len(der) < 8 or der[0] != 0x30:
        raise ValueError("odd signature")
    i = 3 if der[1] & 0x80 else 2
    out = b""
    for _ in range(2):
        if der[i] != 0x02:
            raise ValueError("odd signature")
        n = der[i + 1]
        v = der[i + 2:i + 2 + n].lstrip(b"\0")
        if len(v) > 32:
            raise ValueError("odd signature")
        out += v.rjust(32, b"\0")
        i += 2 + n
    return out


def token(p8):
    kid, iss = os.environ["ASC_KEY_ID"].strip(), os.environ["ASC_ISSUER_ID"].strip()
    now = int(time.time())
    head = b64(json.dumps({"alg": "ES256", "kid": kid, "typ": "JWT"}).encode())
    body = b64(json.dumps({"iss": iss, "iat": now, "exp": now + 600, "aud": "appstoreconnect-v1"}).encode())
    msg = f"{head}.{body}".encode()
    sig = subprocess.run(["openssl", "dgst", "-sha256", "-sign", p8], input=msg, capture_output=True, check=True).stdout
    return f"{head}.{body}.{b64(der_to_raw(sig))}"


def norm(serial):
    s = re.sub(r"[^0-9A-Fa-f]", "", serial or "").upper().lstrip("0")
    return s


def own_serials(keychain):
    """Serial numbers of the certificates in the run's keychain."""
    pem = subprocess.run(["security", "find-certificate", "-a", "-p", keychain],
                         capture_output=True, text=True).stdout
    serials = set()
    for block in re.findall(r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", pem, re.S):
        r = subprocess.run(["openssl", "x509", "-noout", "-serial"], input=block, capture_output=True, text=True)
        m = re.match(r"serial=([0-9A-Fa-f]+)", r.stdout.strip())
        if m and norm(m.group(1)):
            serials.add(norm(m.group(1)))
    return serials


def call(method, url, tok):
    req = urllib.request.Request(url, method=method, headers={"Authorization": "Bearer " + tok})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read(4_000_000)
    return json.loads(data) if data else {}


def main():
    if len(sys.argv) != 3:
        print("usage: asc_certs.py KEYCHAIN P8")
        return 1
    mine = own_serials(sys.argv[1])
    if not mine:
        print("No certificate in this run's keychain, nothing to revoke.")
        return 0
    tok = token(sys.argv[2])
    found = call("GET", API + "?limit=200&fields[certificates]=serialNumber,name,certificateType", tok).get("data") or []
    done = 0
    for c in found:
        a = c.get("attributes") or {}
        cid = str(c.get("id", ""))
        if norm(a.get("serialNumber")) in mine and re.fullmatch(r"[A-Za-z0-9]{1,40}", cid):
            try:
                call("DELETE", f"{API}/{cid}", tok)
                done += 1
                print(f"Revoked {a.get('certificateType', '?')} {a.get('name', '')}")
            except urllib.error.HTTPError as e:
                print(f"::warning::Could not revoke {a.get('name', '')}: HTTP {e.code}")
    print(f"{done} of {len(mine)} certificate(s) of this run revoked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
