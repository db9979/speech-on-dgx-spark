"""Signed update manifests (Ed25519), optional until a key exists.

The release workflows (firmware.yml, begleiter-windows.yml, begleiter-mac.yml) sign manifest.json /
begleiter.json with the secret UPDATE_SIGNING_KEY of the GitHub environment "release" (main only) and
publish the signature next to it as <name>.sig (base64 of the 64 raw signature bytes). The Spark checks
it with the public keys below before it takes a firmware or a Begleiter build.

KEYS is empty until Dominik made a key pair (docs/de/sicherheit-und-betrieb.md, "Signierte Geräte-Updates"):
then nothing changes and only GitHub's https and the SHA-256 in the manifest protect an update. Once a key
is listed here, a manifest without a valid signature is refused (fail closed), also one built before.
The public keys live in the code on purpose: the configuration belongs to the service user.
"""
import base64
import binascii
import re

# base64 of raw 32-byte Ed25519 public keys (openssl pkey -pubout -outform DER | tail -c 32 | base64)
KEYS = ()

MAX_SIG = 512   # the .sig file is 88 characters; anything much bigger is not ours


class SignatureError(ValueError):
    """A fixed sentence the panel may show as it is."""


def required():
    """True once at least one public key is listed: then every manifest must be signed."""
    return bool(KEYS)


def _keys():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    out = []
    for k in KEYS:
        raw = base64.b64decode(k, validate=True)
        if len(raw) != 32:
            raise SignatureError("Öffentlicher Update-Schlüssel ist ungültig.")
        out.append(Ed25519PublicKey.from_public_bytes(raw))
    return out


def verify(data, sig):
    """Raises SignatureError unless `sig` (the .sig file's bytes, base64) is a valid signature of `data` by one
    of KEYS. Does nothing while no key is listed."""
    if not required():
        return
    from cryptography.exceptions import InvalidSignature
    if not sig:
        raise SignatureError("Die Version ist nicht signiert, nichts übernommen.")
    text = bytes(sig[:MAX_SIG + 1]).strip()
    if len(text) > MAX_SIG or not re.fullmatch(rb"[A-Za-z0-9+/=]+", text):
        raise SignatureError("Die Signatur ist ungültig, nichts übernommen.")
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise SignatureError("Die Signatur ist ungültig, nichts übernommen.")
    if len(raw) != 64:
        raise SignatureError("Die Signatur ist ungültig, nichts übernommen.")
    for key in _keys():
        try:
            key.verify(raw, bytes(data))
            return
        except InvalidSignature:
            continue
    raise SignatureError("Die Signatur passt nicht, nichts übernommen.")
