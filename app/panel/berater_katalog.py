"""The Einstellungs-Assistent's catalog (plan einstellungs-assistent.md, Punkt 2): everything it may ever propose.

The language model never names a setting itself: berater.py builds candidates from this table by fixed rules and the
model may only pick one of them (a JSON schema whose enum are the candidates' ids). What is not in this table can not
be proposed, and what is under NEVER is never touched, not even by the admin's own „Übernehmen“ from here.

Stufen:
    A   rules of the Weiche, test sentences, pronunciation, words for the speech recognition, quality cases:
        changes nothing the Spark does outside; undo with one tap
    B   fine values in a narrow range, at most one step at a time (STEP), never past LO..HI
    C   a switch or a way of working: needs a second step (berater.confirm) and is never taken by the autopilot
    P   a profile's own settings: proposed to the profile on Ich → Gespräch, only the profile takes them

Each entry: key -> dict(stufe, art, sec, key, de, en, way, [lo, hi, step], [choices], restart)
    art   weiche (route_words / route_not), test (route_tests), pflicht (tool_words), pron (tts.pronunciation),
          asr (asr.context), quality (quality.add_own), value (a number), switch (bool), choice, profile
    way   where the admin finds the setting by hand (a jump link, way.js)
    restart  the service that starts again when it changes ("" none)
"""

A, B, C, P = "A", "B", "C", "P"

ENTRIES = {
    # ---- A: the Weiche and what the Spark hears and says
    "weiche_wort": dict(stufe=A, art="weiche", sec="chat", key="route_words",
                        de="Eigenes Wort für eine Gruppe", en="Own word for a group",
                        way="Funktionen → Weiche", restart=""),
    "weiche_nicht": dict(stufe=A, art="weiche", sec="chat", key="route_not",
                         de="Wort, das nicht in eine Gruppe führt", en="Word that does not lead into a group",
                         way="Funktionen → Weiche", restart=""),
    "weiche_test": dict(stufe=A, art="test", sec="chat", key="route_tests",
                        de="Testsatz für die Weiche", en="Test sentence for the Weiche",
                        way="Funktionen → Weiche", restart=""),
    "pflicht_wort": dict(stufe=A, art="pflicht", sec="chat", key="tool_words",
                         de="Wort, bei dem ein Werkzeug Pflicht ist", en="Word that makes a tool a must",
                         way="Einstellungen → Sprachmodell", restart=""),
    "aussprache": dict(stufe=A, art="pron", sec="tts", key="pronunciation",
                       de="Aussprache eines Wortes", en="Pronunciation of a word",
                       way="Einstellungen → Sprachausgabe", restart="tts"),
    "hoer_wort": dict(stufe=A, art="asr", sec="asr", key="context",
                      de="Wort für die Spracherkennung", en="Word for the speech recognition",
                      way="Einstellungen → Spracherkennung", restart="asr"),
    "qualitaet_fall": dict(stufe=A, art="quality", sec="", key="",
                           de="Frage in den Qualitätstest", en="Question into the quality test",
                           way="Zustand → Prüfen", restart=""),
    # ---- B: fine values, one step at a time
    "suchtreffer": dict(stufe=B, art="value", sec="chat", key="search_results", lo=3, hi=8, step=1,
                        de="Treffer der Websuche", en="Web search results", way="Funktionen", restart=""),
    "suchseiten": dict(stufe=B, art="value", sec="chat", key="search_pages", lo=0, hi=3, step=1,
                       de="Gelesene Seiten der Websuche", en="Pages read by the web search",
                       way="Funktionen", restart=""),
    "nachschlagen": dict(stufe=B, art="value", sec="chat", key="max_searches", lo=1, hi=3, step=1,
                         de="Nachschlagen pro Frage", en="Lookups per question", way="Einstellungen → Sprachmodell",
                         restart=""),
    "lokal_ms": dict(stufe=B, art="value", sec="chat", key="local_first_ms", lo=300, hi=900, step=100,
                     de="Wartezeit für eigene Quellen (ms)", en="Wait for own sources (ms)",
                     way="Funktionen", restart=""),
    "verlauf": dict(stufe=B, art="value", sec="chat", key="history_chars", lo=12000, hi=32000, step=4000,
                    de="Gesprächsverlauf (Zeichen)", en="Conversation history (characters)",
                    way="Einstellungen → Sprachmodell", restart=""),
    "temperatur": dict(stufe=B, art="value", sec="chat", key="temperature", lo=0.1, hi=0.6, step=0.1,
                       de="Temperatur der Antworten", en="Temperature of answers", way="Einstellungen → Sprachmodell",
                       restart=""),
    "werkzeug_temperatur": dict(stufe=B, art="value", sec="chat", key="tool_temperature", lo=0.0, hi=0.3, step=0.05,
                                de="Temperatur der Werkzeugwahl", en="Temperature of the tool choice",
                                way="Einstellungen → Sprachmodell", restart=""),
    "erster_ton": dict(stufe=B, art="value", sec="tts", key="initial_chunk_frames", lo=6, hi=14, step=2,
                       de="Erster Ton nach (Frames)", en="First sound after (frames)",
                       way="Einstellungen → Sprachausgabe", restart="tts"),
    # ---- C: switches and ways of working (second step, never the autopilot)
    "weiche_modell": dict(stufe=C, art="choice", sec="chat", key="route_model", choices=("off", "lean", "on", "systemone"),
                          de="Unklare Fragen an das Sprachmodell", en="Unclear questions to the language model",
                          way="Funktionen", restart=""),
    "schneller_beginn": dict(stufe=C, art="switch", sec="chat", key="prompt_cache",
                             de="Schneller Antwortbeginn", en="Faster first words", way="Einstellungen → Sprachmodell", restart=""),
    "antwort_pruefen": dict(stufe=C, art="switch", sec="chat", key="answer_check",
                            de="Antworten prüfen", en="Check answers", way="Einstellungen → Sprachmodell", restart=""),
    "sofort_satz": dict(stufe=C, art="switch", sec="chat", key="instant_ack",
                        de="Sofortige Rückmeldung", en="Instant reply", way="Funktionen", restart=""),
    "erst_lokal": dict(stufe=C, art="switch", sec="chat", key="local_first",
                       de="Erst lokal suchen", en="Look locally first", way="Funktionen", restart=""),
    # ---- P: a profile's own settings (Ich → Gespräch); `need` is the function the Spark must allow
    "p_laenge": dict(stufe=P, art="profile", key="length", choices=("short", "normal", "long"), need="",
                     de="Antwortlänge", en="Answer length", way="Ich → Gespräch", restart=""),
    "p_tempo": dict(stufe=P, art="profile", key="speed", lo=0.8, hi=1.3, step=0.1, need="",
                    de="Sprechtempo", en="Speaking speed", way="Ich → Gespräch", restart=""),
    "p_gezielt": dict(stufe=P, art="profile", key="route", need="routing",
                      de="Gezielte Werkzeugwahl", en="Targeted tool choice", way="Ich → Gespräch", restart=""),
    "p_sofort": dict(stufe=P, art="profile", key="instant_ack", need="ack",
                     de="Sofortige Rückmeldung", en="Instant reply", way="Ich → Gespräch", restart=""),
    "p_lokal": dict(stufe=P, art="profile", key="local_first", need="lokal",
                    de="Erst lokal suchen", en="Look locally first", way="Ich → Gespräch", restart=""),
}

# D: never, whatever a case says (shown on the page so the admin sees the border)
NEVER = (
    ("Passwörter, Schlüssel und Zugangsdaten", "Passwords, keys and credentials"),
    ("Adresse und Schlüssel des Sprachmodells, qwen38", "Address and key of the language model, qwen38"),
    ("Notaus und Wächter (netguard)", "Notaus and Wächter (netguard)"),
    ("Zweiter Anmeldeschritt, Rollen und Rechte", "Second sign-in step, roles and rights"),
    ("Ports, Netz und Gastzugang", "Ports, network and guest access"),
    ("Mail senden, MCP nach außen, Probleme melden", "Sending mail, MCP to the outside, reporting problems"),
    ("Updates und Sicherungen", "Updates and backups"),
)
NEVER_KEYS = {("chat", k) for k in ("llm_url", "llm_key", "public", "mfa", "report", "report_repo", "mail_send",
                                    "mcp_server_extern", "dev_updates", "telegram_api")} \
    | {("api", "key"), ("panel", "port"), ("panel", "https_port")}

ARTS = {"weiche", "test", "pflicht", "pron", "asr", "quality", "value", "switch", "choice", "profile", "umgebung", "issue"}


def entry(key):
    return ENTRIES.get(key)


def stufe(key):
    e = ENTRIES.get(key)
    return e["stufe"] if e else ""


def check_table():
    """The table holds together (a self-test calls it): known kinds, ranges, never a key from NEVER_KEYS."""
    for k, e in ENTRIES.items():
        assert e["stufe"] in (A, B, C, P), k
        assert e["art"] in ARTS, k
        assert (e.get("sec"), e.get("key")) not in NEVER_KEYS, k
        if e["art"] == "value" or (e["art"] == "profile" and "lo" in e):
            assert e["lo"] < e["hi"] and 0 < e["step"] <= e["hi"] - e["lo"], k
        assert e["way"].split(" → ")[0] in ("Funktionen", "Einstellungen", "Zustand", "Ich"), k
    return True


# Every setting is classified (rule in docs/de/richtlinien.md, „Einstellungs-Assistent“; test_einstellungs_assistent
# checks it): in ENTRIES (A–C, P), in NEVER_KEYS (D) or here, in OHNE: settings the assistant deliberately leaves
# alone (addresses, accounts, looks, features of their own, limits nobody tunes from a case). A new key in
# config.default.json or profiles.SETTINGS goes into one of the three in the same commit.
OHNE = {
    "asr": (
        "aligner_model", "backend", "default_language", "dtype", "enabled", "engine_max_seqs", "engine_mem",
        "engine_port", "host", "max_batch_size", "max_new_tokens", "model", "port", "recognizer", "timestamps",
    ),
    "chat": (
        "telegram_panel_url",
        "agent", "agent_mcp", "android", "berater", "berater_auto", "berater_calls", "berater_chat",
        "berater_check_h", "berater_env", "berater_explain", "berater_issue", "berater_me", "berater_notify",
        "berater_off", "bewerten", "bewerten_back", "calendar", "contacts", "datetime", "defaults", "desk",
        "desk_act", "desk_meeting", "dev_updates_night", "dev_updates_night_at", "dev_updates_upstream",
        "direct_read", "doc_brief", "doc_make", "doc_make_templates", "doc_max_mb", "doc_night", "doc_night_from",
        "doc_night_to", "doc_originals", "doc_pictures", "doc_quota_mb", "doc_semantic", "doc_shared", "documents",
        "esp32", "esp32_ota_http", "esp32_repo", "esp32_url", "face", "face_life", "feature_tips",
        "feature_tips_push", "follow_up", "geocode_url", "ha_camera", "ha_events", "ha_live", "ha_loud",
        "ha_voice_rules", "history", "homeassistant", "images", "iphone", "iphone_panel", "iphone_push",
        "iphone_update", "kiwix", "kiwix_books", "kiwix_url", "learn_fixes", "llm_key_from", "llm_model",
        "llm_timeout", "mail", "mail_tidy", "max_tokens", "mcp_own", "mcp_own_jobs", "mcp_own_oauth", "mcp_server",
        "mcp_server_act", "memory", "messages", "messages_all", "messages_announce", "messages_voice", "my_status",
        "new_profile_on", "no_self_echo", "own_style", "parcels", "pebble", "person_priority",
        "person_priority_wait", "prefetch", "presence_penalty", "proactive", "remarkable", "remarkable_fresh",
        "remarkable_plus", "remarkable_send", "reminders", "report_notify", "roles", "room", "room_ha",
        "room_remote", "room_voices", "route_extra", "route_off", "routing", "search", "search_url",
        "self_echo_mode", "spark_drawer", "spark_help", "spark_suggest", "speaker_code", "speaker_id",
        "speaker_strictness", "svc_watch", "svc_watch_users", "system_prompt", "systemone", "systemone_mail",
        "systemone_quality", "systemone_tidy", "tasks", "telegram", "thinking", "tool_thinking", "top_p", "transit",
        "transit_url", "weather", "weather_url", "wiki", "wiki_url", "write_apps", "write_help", "wyoming",
        "wyoming_allow", "wyoming_port", "wyoming_voice",
    ),
    "logs": (
        "keep_days", "live", "live_monitor", "live_names", "live_screens", "max_mb", "trace",
    ),
    "memory": (
        "guard", "reserve_gib",
    ),
    "panel": (
        "allow_lan", "host", "notaus_auto", "notaus_profiles", "session_days", "trust_days", "trusted_proxies",
        "update_night",
    ),
    "tts": (
        "backend", "calm", "clean_text", "default_instruct", "default_language", "default_voice", "dtype",
        "enabled", "engine_max_model_len", "engine_max_seqs", "engine_mem_code2wav", "engine_mem_talker",
        "engine_port", "host", "model", "numbers", "port", "seed", "temperature", "top_p", "voicedesign_enabled",
        "voicedesign_model", "voicedesign_port",
    ),
    "watch": (
        "warn_gib", "watchdog",
    ),
}
OHNE_PROFIL = (
        "agent_doc", "agent_on", "android_on", "app_accounts", "app_act", "app_admin", "app_auto", "app_car_ha",
        "app_docs", "app_docs_edit", "app_ha", "app_images", "app_ios", "app_listen", "app_mine", "app_on",
        "app_push", "app_room", "app_security", "app_voice", "auto", "barge", "barge_level", "berater_ask",
        "berater_me", "berater_note", "berater_skip", "briefing_at", "con_bday", "con_on", "daily", "desk_on",
        "devup_night", "devup_on", "direct_read", "doc_brief", "doc_deliver", "doc_due", "doc_make",
        "doc_make_templates", "doc_originals", "doc_pictures", "doc_semantic", "doc_sender", "doc_shared", "echo",
        "esp_on", "fix_learn", "follow", "hands", "images_on", "kiwix_on", "learn", "live", "mcps_on", "msg_all",
        "msg_announce", "msg_from", "msg_on", "msg_speaker", "my_status", "mymcp_on", "par_on", "pebble_on",
        "prefetch", "pro_bday", "pro_events", "pro_follow", "pro_greet", "pro_ha", "pro_ha_cam", "pro_ha_events",
        "pro_ha_live", "pro_ha_loud", "pro_ha_me", "pro_ha_voice", "pro_lead", "pro_learn", "pro_mail",
        "pro_mail_from", "pro_mail_smart", "pro_max", "pro_on", "pro_parcel", "pro_place", "pro_quiet", "pro_tidy",
        "pro_tips", "pro_transit", "pro_weather", "pro_weather_at", "rate_back", "rate_on", "report_notify",
        "report_on", "rm_ask", "rm_fresh", "rm_guide", "rm_inbox", "rm_meet", "rm_morning", "rm_morning_at",
        "rm_on", "rm_send", "rm_todo", "rm_web", "rm_week", "role", "roles", "roles_on", "room_remote", "room_tell",
        "spark_help", "speak", "spk_code", "style", "svc_device", "svc_hint", "svc_night", "svc_note",
        "systemone_on", "tasks_on", "tg_ha", "tg_images", "tg_private", "tg_push", "tg_voice", "timing", "tips_on",
        "tool_think", "trace_name", "transit_on", "turn", "tz", "voice", "wiki_on", "write_apps", "write_on",
        "wx_on",
)


def unclassified(config, settings):
    """Settings that are in none of ENTRIES, NEVER_KEYS and OHNE (for the self-test)."""
    have = {(e.get("sec"), e.get("key")) for e in ENTRIES.values() if e.get("art") != "profile"} | set(NEVER_KEYS)
    have |= {(s, k) for s, keys in OHNE.items() for k in keys}
    mine = {e["key"] for e in ENTRIES.values() if e.get("art") == "profile"} | set(OHNE_PROFIL)
    keys = {(s, k) for s, v in config.items() if isinstance(v, dict) for k in v}
    return sorted(f"{s}.{k}" for s, k in keys - have) + sorted(f"Profil.{k}" for k in set(settings) - mine)
