"""Background voices never become a question (fixed rule, no switch).

After an answer the browser opens the microphone by itself: barge-in while the answer plays, the follow-up
window ("Rückfrage ohne Weckwort") and hands-free listening. With the TV on, the voices from the TV went to
the assistant as a question nobody asked, and while that answer played they cut it off again (Dominik
2026-10-13, Anfrage d80a75). A tapped "Sprechen" or "Hey Spark" is the person's own decision and is never
checked here.

The panel decides with a fixed rule, never the model:

1. Only recordings the page opened by itself count here (OPEN: "barge", "follow", "hands"); the page says
   which one with the field "opened". A page could leave it out, but it only protects its own profile from
   noise, it opens nothing.
2. Only when the profile taught its voice and the admin has speaker recognition on (chat.speaker_id).
   Without a voiceprint nobody can tell the TV from the person; then the page's own level rules
   (chat.js: the room level learned while the answer plays) are all there is.
3. The voice is compared with the profile's voiceprints (speakers.verify, the profile's strictness).
   A recording counts when it is the profile's voice, or clearly the voice of another profile in the
   household. Too little speech to tell ("Und morgen?") also counts, so a short follow-up is never lost.
   Anything else is "foreign voice": no text, the question is never asked.
4. The car is never checked: the iPhone app sends "car" for its hands-free follow-ups in CarPlay, which is not
   in OPEN. Through the car's microphone the own voice did not match the voiceprint, so every follow-up was
   dropped as a foreign voice (Dominik 2026-10-21); in the closed car there is no TV, the radio is paused
   while Spark talks, and the conversation began with a tap on the car's screen.

Only the decision and its numbers go to the journal, never the words, the voiceprint or a name."""
import re

OPEN = ("barge", "follow", "hands")
WHAT = {"barge": "barge-in", "follow": "follow-up window", "hands": "hands-free"}
SHORT = "too little speech to check the voice"


def opened(value):
    """The page's own word for how the microphone opened, only one of the known ones (else "")."""
    v = str(value or "").strip().lower()[:12]
    return v if v in OPEN else ""


def applies(cfg, uid, how):
    """Whether this recording is checked at all (no voiceprint, no check)."""
    if not uid or not opened(how) or not (cfg or {}).get("chat", {}).get("speaker_id", False):
        return False
    import speakers
    return speakers.has_voice(uid)


def check(uid, data, threshold):
    """(why, verify numbers): why is "foreign voice" when nobody of the household spoke, else None."""
    import speakers
    v = speakers.verify(uid, data, threshold)
    if v.get("ok") or v.get("why") == SHORT:
        return None, v
    if v.get("why") == "the profile has not taught its voice":
        return None, v
    # clearly another profile of the household (the margin is the one speakers.identify uses)
    if v.get("other", -1.0) >= threshold and v.get("other", -1.0) - v.get("score", 0.0) >= 0.05:
        return None, v
    if v.get("score", 0.0) >= threshold:     # the profile's voice, only close to another one: still a known voice
        return None, v
    return "foreign voice", v


def note(why, how, v, client):
    """The journal line: decision, how the microphone opened, the numbers; never words or names."""
    import speakers
    dev = re.sub(r"[^a-z0-9]", "", str(client))[:12] or "device"
    nums = speakers.numbers(v) if isinstance(v, dict) and "score" in v else "no numbers"
    if why:
        print(f"chat: ignored ({why}, {WHAT.get(how, 'open microphone')}) from {dev} | {nums}", flush=True)
        try:
            import live
            live.mark("Sprechererkennung", "Fremde Stimme überhört, kein Wort weitergegeben")
        except Exception:
            pass
    else:
        reason = "too short to check" if v.get("why") == SHORT else "known voice"
        print(f"chat: open microphone voice checked ({WHAT.get(how, 'open microphone')}) from {dev} | {reason} | {nums}",
              flush=True)
