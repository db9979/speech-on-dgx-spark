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
    art   weiche (route_words / route_not), test (route_tests), pflicht (tool_words), hinweis (tool_hints, a fixed
          sentence from chat.HINT_TPL), extra (route_extra), pron (tts.pronunciation),
          asr (asr.context), quality (quality.add_own), value (a number), switch (bool), choice, profile
    way   where the admin finds the setting by hand (a jump link, way.js)
    restart  the service that starts again when it changes ("" none)
"""

import profiles

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
                         way="Funktionen → Weiche", restart=""),
    # R2, R3 (plan vorschlaege-besser.md): a fixed sentence for a tool, a tool a group of the Weiche keeps as well
    "werkzeug_hinweis": dict(stufe=A, art="hinweis", sec="chat", key="tool_hints",
                             de="Hinweis zu einem Werkzeug", en="Hint for a tool",
                             way="Einstellungen → Sprachmodell", restart=""),
    "weiche_extra": dict(stufe=A, art="extra", sec="chat", key="route_extra",
                         de="Zusätzliches Werkzeug für eine Gruppe", en="Extra tool for a group",
                         way="Funktionen → Weiche", restart=""),
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
                          way="Funktionen → Weiche", restart=""),
    "schneller_beginn": dict(stufe=C, art="switch", sec="chat", key="prompt_cache",
                             de="Schneller Antwortbeginn", en="Faster first words", way="Einstellungen → Sprachmodell", restart=""),
    "antwort_pruefen": dict(stufe=C, art="switch", sec="chat", key="answer_check",
                            de="Antworten prüfen", en="Check answers", way="Einstellungen → Sprachmodell", restart=""),
    "sofort_satz": dict(stufe=C, art="switch", sec="chat", key="instant_ack",
                        de="Sofortige Rückmeldung", en="Instant reply", way="Funktionen", restart=""),
    "erst_lokal": dict(stufe=C, art="switch", sec="chat", key="local_first",
                       de="Erst lokal suchen", en="Look locally first", way="Funktionen", restart=""),
    # ---- P: a profile's own settings (Ich → Gespräch); `need` is the function the Spark must allow
    "p_laenge": dict(stufe=P, art="profile", key="length", choices=profiles.CHOICES["length"], need="",
                     de="Antwortlänge", en="Answer length", way="Ich → Gespräch", restart=""),
    "p_tempo": dict(stufe=P, art="profile", key="speed", lo=0.8, hi=1.3, step=0.1, need="",
                    de="Sprechtempo", en="Speaking speed", way="Ich → Gespräch", restart=""),
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
    | {("api", "key"), ("api", "tls_listen"), ("api", "tls_from"), ("panel", "port"), ("panel", "https_port"),
       ("models", "host"), ("models", "cert")}

ARTS = {"weiche", "test", "pflicht", "hinweis", "extra", "pron", "asr", "quality", "value", "switch", "choice", "profile", "umgebung", "issue"}


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
        "action_check", "loop_stop",
        "telegram_panel_url",
        "agent", "agent_mcp", "agent_watch", "android", "android_live", "android_update", "berater", "berater_auto", "berater_calls", "berater_chat",
        "berater_check_h", "berater_env", "berater_explain", "berater_ideas", "berater_analyse", "berater_auto_undo", "berater_issue", "berater_me", "berater_notify",
        "berater_off", "bewerten", "bewerten_back", "calendar", "chats", "chats_groups", "chats_media", "chats_invite", "chats_private", "chats_verbund", "verbund_media", "verbund_groups", "verbund_mode", "verbund_domain", "chats_calls", "calls_turn", "calls_turn_host", "contacts", "datetime", "defaults", "desk",
        "desk_act", "desk_meeting", "dev_updates_night", "dev_updates_night_at", "dev_updates_upstream",
        "direct_read", "doc_brief", "doc_make", "doc_make_templates", "doc_make_wikipics", "bilder", "doc_max_mb", "doc_night", "doc_night_from", "docling", "search_check", "search_check_auto", "search_check_day", "rerank", "rerank_model", "rerank_ms",
        "doc_night_to", "doc_originals", "doc_pictures", "doc_quota_mb", "doc_semantic", "doc_shared", "documents",
        "esp32", "esp32_ota_http", "esp32_repo", "esp32_stop", "esp32_url", "face", "face_life", "feature_tips", "tagebuch", "status_voice", "undo_voice", "berater_why",
        "feature_tips_push", "follow_up", "geocode_url", "ha_camera", "ha_events", "ha_live", "ha_loud",
        "ha_voice_rules", "history", "history_live", "history_offline", "history_one", "homeassistant", "images", "iphone", "iphone_panel", "iphone_push",
        "iphone_update", "kiwix", "kiwix_books", "kiwix_url", "klaeren", "klaeren_merken", "learn_fixes", "llm_key_from", "llm_model",
        "llm_timeout", "mail", "mail_style", "mail_tidy", "max_tokens", "mcp_own", "mcp_own_jobs", "mcp_own_oauth", "mcp_server",
        "mcp_server_act", "memory", "memory_ask", "memory_check", "memory_stale_months", "memory_topics", "messages_all", "messages_announce", "my_status", "nas_on", "nas_sources", "nas_shared", "nas_max_docs", "nas_sources_every", "nas_drop", "nas_drop_every", "nas_status", "nas_full_pct", "nas_temp_max",
        "deny", "no_self_echo", "own_style", "parcels", "pebble", "person_priority",
        "person_priority_wait", "prefetch", "presence_penalty", "proactive", "remarkable", "remarkable_fresh",
        "remarkable_paper", "remarkable_plus", "remarkable_tasks", "remarkable_send", "reminders", "report_notify", "roles", "room", "room_ha",
        "room_remote", "room_voices", "route_off", "routing", "search", "search_url",
        "self_echo_mode", "spark_drawer", "spark_help", "spark_suggest", "speaker_code", "speaker_id",
        "speaker_strictness", "storage_folder", "storage_lan", "storage_offload", "storage_own", "storage_root",
        "svc_watch", "svc_watch_users", "wartung", "wartung_auto", "notbetrieb_asr", "modelle_wechseln", "modelle_eigene", "system_prompt", "systemone", "systemone_berater",
        "systemone_check", "systemone_klage", "systemone_mail", "systemone_min", "systemone_quality", "systemone_tidy", "tasks", "telegram", "thinking", "tool_thinking", "top_p", "transit",
        "transit_url", "usage_count", "usage_quota", "usage_quota_k", "usage_quota_mk", "usage_quota_warn", "usage_quota_wk", "weather", "weather_url", "wiki", "wiki_url", "write_apps", "write_help", "wyoming",
        "wyoming_allow", "wyoming_port", "wyoming_voice", "telefon", "telefon_aussen", "telefon_gaeste", "telefon_max", "telefon_ton",
    ),
    # Bilder malen (bilder.py, bild_server.py): installed by install.sh, limits nobody tunes from a case
    "image": (
        "day_limit", "enabled", "engine_port", "idle_min", "max_side", "port", "store_mb", "variant",
    ),
    # Eigene Modelle (llm_tor.py, modelle.py): ports, model and the switch come from install and the model commands
    "llm": (
        "enabled", "engine_port", "host", "max_body_mb", "modell", "port", "sehen_leerlauf_min", "sehen_modell",
        "sehen_port",
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
        "agent_doc", "android_live", "app_act", "app_car_ha", "app_docs",
        "app_ha", "app_images", "app_ios", "app_listen", "app_push", "app_room",
        "auto", "barge", "barge_level", "berater_note", "berater_skip", "briefing_at",
        "chat_push_text", "chat_receipts", "con_bday", "daily", "devup_night", "doc_deliver", "doc_docling", "doc_due", "doc_sender",
        "echo", "face", "follow", "hands", "learn", "live", "msg_all", "msg_from", "msg_speaker", "pro_bday", "pro_events",
        "pro_follow", "pro_greet", "pro_ha", "pro_ha_cam", "pro_ha_events", "pro_ha_live", "pro_ha_loud", "pro_ha_me",
        "pro_lead", "pro_learn", "pro_mail", "pro_mail_from", "pro_mail_smart", "pro_max", "pro_on", "pro_parcel",
        "pro_place", "pro_quiet", "pro_tidy", "pro_tips", "pro_transit", "pro_weather", "pro_weather_at", "rate_back",
        "report_notify", "rm_inbox", "rm_morning", "rm_morning_at", "rm_week", "rm_tidy", "rm_model", "role", "roles",
        "room_tell", "speak", "style", "svc_device", "svc_night", "svc_note", "tg_ha", "tg_images", "tg_private",
        "tg_push", "tg_voice", "timing", "trace_name", "turn", "tz", "voice",
)


def unclassified(config, settings):
    """Settings that are in none of ENTRIES, NEVER_KEYS and OHNE (for the self-test)."""
    have = {(e.get("sec"), e.get("key")) for e in ENTRIES.values() if e.get("art") != "profile"} | set(NEVER_KEYS)
    have |= {(s, k) for s, keys in OHNE.items() for k in keys}
    mine = {e["key"] for e in ENTRIES.values() if e.get("art") == "profile"} | set(OHNE_PROFIL)
    keys = {(s, k) for s, v in config.items() if isinstance(v, dict) for k in v}
    return sorted(f"{s}.{k}" for s, k in keys - have) + sorted(f"Profil.{k}" for k in set(settings) - mine)
