"""Tonteile: the one helper that has the Spark's own speech output speak one part (plan open-notebook 5.3, Push 5a).

sprich(text, voice, klang, ref, stufe, frist, grenze, sprache, art) posts one part to POST /v1/audio/speech (OpenAI form,
response_format pcm) and returns the bytes as they came: 16-bit mono PCM at 24 kHz, or a WAV when the speech output
ignores response_format. klang is a voice made from a description (VoiceDesign) instead of a named one, ref (data URL,
words) has the Base model clone that recording. stufe "hinten" sends stufe.headers("hinten"): with the panel's key
the speech output lets it wait behind every person and common.SpeechMark does not take it for speech (common.signed_low,
V01.1.336); without stufe nothing changes against before (the Dungeon's reading aloud, a person listening).

art (the Hörstück as a discussion, V01.1.364) is a fixed English addition of the caller for how a part is spoken
("curious, lively and interested"), never a word of a model: with klang it is added to the description, with a named
or the standard voice it goes as instructions (1.7B-CustomVoice follows them, 0.6B and Base ignore them), with ref
never. Without art the body is exactly as before (the Dungeon's calls).

A 503 of the speech output says why in its body; the error is RuntimeError("tts 503 loading") and the like (NICHT),
so a caller can let the fixed voice stand in. Above grenze bytes the part is given up (RuntimeError("tts")).

Users: dungeon.ask_tts (a thin call, unchanged behaviour), hoerstueck.py (one line of a Hörstück per step) and
stimmdesign.py (the sample of a designed voice, with its seed).
"""
import re

from common import load_config, model_url

NICHT = re.compile(r"TTS engine (loading|stopped|error|blocked)|TTS (busy)")   # why the speech output said 503
GRENZE = 32 * 1024 * 1024    # bytes of one part at most (about 11 min of 24 kHz PCM)
FRIST = 150                  # seconds one part may take


async def sprich(text, voice="", klang="", ref=None, stufe="", frist=FRIST, grenze=GRENZE, sprache="", art="", seed=None):
    """One part spoken by the Spark's speech output (bytes as they came; tests replace the callers' wrappers).
    sprache: "German" or "English" when the caller knows the part's language (the Hörstück), else the speech
    output's own default. seed: a whole number for VoiceDesign (Eigene Stimmen gestalten, „Neu würfeln“: another
    number, another voice for the same description); without it the speech output's own (tts.seed)."""
    import httpx
    from core import api_headers
    cfg = load_config()
    body = {"input": text, "response_format": "pcm"}
    if sprache in ("German", "English"):
        body["language"] = sprache
    if isinstance(seed, int) and not isinstance(seed, bool) and 0 <= seed < 2 ** 31:
        body["seed"] = seed
    if ref:
        body.update(ref_audio=ref[0], ref_text=ref[1])
    elif klang:
        body.update(task_type="VoiceDesign", instructions=f"{klang}, {art}" if art else klang)
    else:
        if voice:
            body["voice"] = voice
        if art:
            body["instructions"] = art
    headers = api_headers()
    if stufe:
        import stufe as _stufe
        headers = dict(headers, **_stufe.headers(stufe))
    out = bytearray()
    async with httpx.AsyncClient(timeout=httpx.Timeout(frist, connect=5)) as c:
        async with c.stream("POST", model_url("tts", "/v1/audio/speech", cfg), json=body, headers=headers) as r:
            if r.status_code != 200:
                m = NICHT.search((await r.aread())[:400].decode("utf-8", "replace"))
                raise RuntimeError(f"tts {r.status_code}" + (f" {m.group(1) or m.group(2)}" if m else ""))
            async for part in r.aiter_bytes():
                out += part
                if len(out) > grenze:
                    raise RuntimeError("tts")
    return bytes(out)
