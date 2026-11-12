"""Which function the assistant reaches how (plan werkzeug-abdeckung.md, Dominik 2026-10-13: „überprüfe ob es für
alle Dienste und Infos Werkzeuge gibt“; the reMarkable's morning sheet could not be sent again, no tool had it).

Every function in features.FEATURES stands here exactly once:
  TOOLS    its tools for the language model (internal names, werkzeuge.NAMES gives the readable ones);
  RULES    the panel's fixed rule that answers it without the model choosing (a sentence the panel recognizes);
  WITHOUT  why there is nothing to ask for: a setting of how answers come about, something the Spark does by itself,
           a channel or device, or deliberately not by voice (secrets, security, undoing the Notaus).
A function may have tools and a rule at once; WITHOUT stands alone.

tests/test_werkzeug_abdeckung.py checks: every function is here, every tool named here exists and every tool of the
chat sits in a group of the Weiche (intent.GROUPS), is always kept (intent.NARROW_KEEP) or kept when the person names
it (BY_WORD), and SENTENCES leads each grouped tool's typical request to its group. A new function adds its line
here in the same commit (guideline part 1, row 29)."""
import steckbrief

TOOLS = {
    # conversation and knowledge
    "search": ("web_search",),
    "wiki": ("wikipedia", "article_more"),
    "kiwix": ("archive_search", "article_more"),
    "hilfe": ("spark_hilfe",),
    "hilfevorschlag": ("spark_vorschlag",),
    "hilfeseite": ("spark_hilfe",),
    "tipps": ("spark_hilfe",),
    "tippssaetze": ("spark_hilfe",),   # „Was kannst du?“ with examples (saetze.py)
    "memory": ("memory_save", "memory_forget"),
    "history": ("history_search",),
    "documents": ("document_search", "document_list"),
    "fund": ("fund_suche",),
    "mappen": ("mappe_liste", "mappe_stand", "mappe_dazu"),
    "auswertungen": ("dokument_auswertung",),
    "docaudio": ("document_search",),
    "hoerstueck": ("hoerstueck_machen",),
    "hoerstueckdisk": ("hoerstueck_machen",),   # the same tool; the admin's switch decides the style of the script
    "doclink": ("link_als_dokument", "document_search"),
    "docyoutube": ("link_als_dokument", "document_search"),
    "docshared": ("document_search",),
    "docbrief": ("document_search",),
    "remarkable": ("document_search", "remarkable_library"),
    "rmtodo": ("remarkable_library",),
    "nasablage": ("nas_ablegen",),
    "naszustand": ("nas_zustand",),
    "vorgaenge": ("offen_zeigen",),   # „Was ist offen?“ (read only); the cards' buttons do the rest
    "rmsend": ("remarkable_note", "remarkable_sent"),
    "rmweb": ("remarkable_page", "remarkable_attachment"),
    "rmaufgaben": ("remarkable_sheet",),   # every sheet on request goes through it (rmplus.SHEETS)
    "erstellen": ("document_plan", "document_change", "document_status", "document_send"),
    "erstellenvorlagen": ("document_plan",),
    "erstellenbilder": ("document_plan",),
    "bilder": ("bild_malen",),
    "musik": ("musik_machen",),
    "musikbearbeiten": ("musik_bearbeiten",),
    "telefonanrufen": ("anruf_planen",),
    "tagebuch": ("spark_tagebuch",),
    "sparkzustand": ("spark_zustand",),
    "entwickelnauftrag": ("code_auftrag",),
    # everyday
    "reminders": ("reminder_set", "reminder_list", "reminder_cancel"),
    "tasks": ("tasks_show", "tasks_add", "tasks_change"),
    "agent": ("agent_list", "agent_task", "agent_schedule", "routine_save", "agent_change"),
    "beobachten": ("agent_watch", "agent_change"),
    "messages_all": ("message_send",),
    "chats": ("message_send", "message_read"),
    "calendar": ("calendar_events", "calendar_add", "calendar_change", "daily_briefing"),
    "weather": ("weather",),
    # mail and contacts
    "mail": ("mail_list", "mail_search", "mail_read", "mail_draft"),
    "tidy": ("mail_tidy_overview", "mail_tidy_propose"),
    "parcels": ("parcels",),
    "fuerdich": ("fuer_dich", "fuer_dich_tun"),
    "contacts": ("contacts_search",),
    # home and devices
    "ha": ("home_assistant", "home_assistant_action", "home_assistant_states", "home_assistant_history",
           "home_assistant_todo"),
    "hacam": ("camera_describe",),
    "proactive": ("home_rules_list", "home_rule_delete", "proactive_pause"),
    "esp32": ("speaker_volume",),
    "rueckgaengig": ("undo_last",),
    "messages_announce": ("message_announce",),
    "transit": ("transit",),
    "feeds": ("feeds_news",),
    "begleiter": ("pc_action", "pc_send"),
    "begleiterbedienen": ("pc_look",),
    "begleitertun": ("pc_action",),
    "iphone": ("iphone_action",),
    **steckbrief.abdeckung(),   # the functions with a Steckbrief (steckbrief.py)
}

RULES = {
    **steckbrief.ohne_werkzeug("regel"),   # the functions with a Steckbrief (steckbrief.py)
}

WITHOUT = {
    "schreib": "das Modell formuliert selbst",
    **steckbrief.ohne_werkzeug("ohne"),   # the functions with a Steckbrief (steckbrief.py)
}

# the panel's own steps under a tool's name, never offered to the model (lokal.py's quick look)
PANEL_STEPS = {"local_search"}

# tools a module offers only when the person's own words name it: the Weiche keeps them (extras "keep")
BY_WORD = {"remarkable_note": "remarkable", "remarkable_sent": "remarkable", "remarkable_page": "remarkable",
           "remarkable_attachment": "remarkable", "remarkable_library": "rmliste", "remarkable_sheet": "remarkable", "spark_zustand": "zustand_wz", "code_auftrag": "codeauftrag",
           "home_rules_list": "hamelden", "home_rule_delete": "hamelden", "speaker_volume": "aendern",
           "proactive_pause": "aendern", "undo_last": "aendern", "nas_ablegen": "nasablage",
           "nas_zustand": "naszustand", "offen_zeigen": "vorgaenge",
           # the computer (P4, review D-14): only when the own words name it or at the Begleiter itself
           "pc_action": "begleiter", "pc_send": "begleiter", "pc_look": "begleiter",
           **steckbrief.nur_eigenes_wort()}   # the functions with a Steckbrief (steckbrief.py)

# one typical request per tool of a Weiche group, German and English: it must reach that group
# (tests/test_werkzeug_abdeckung.py). The one list of example sentences: „Das kannst du auch sagen“ (saetze.py) shows
# them too, so each is a plain request a person could say as it stands
SENTENCES = {
    "web_search": ("Was gibt es Neues in den Nachrichten?", "What is new in the news?"),
    "wikipedia": ("Schau in Wikipedia nach Albert Einstein", "Look up Albert Einstein in Wikipedia"),
    "archive_search": ("Schau in meinem Archiv nach Sauerteig", "Look in my archive for sourdough"),
    "spark_hilfe": ("Wie stelle ich die Websuche ein?", "How do I set up the web search?"),
    "spark_vorschlag": ("Was empfiehlst du mir an Einstellungen?", "Which settings do you recommend?"),
    "memory_save": ("Merk dir, dass ich Tee mag", "Remember that I like tea"),
    "memory_forget": ("Vergiss, dass ich Tee mag", "Forget that I like tea"),
    "history_search": ("Haben wir schon mal darüber gesprochen?", "Did we talk about this before?"),
    "document_search": ("Wann läuft meine Versicherung ab?", "When does my insurance end?"),
    "document_list": ("Welche Dokumente habe ich?", "Which documents do I have?"),
    "fund_suche": ("Such meine Rechnung von Thomann", "Find my invoice from Thomann"),
    "mappe_liste": ("Welche Mappen habe ich?", "Which collections do I have?"),
    "mappe_stand": ("Was liegt in der Mappe Urlaub?", "What is in the collection Holiday?"),
    "mappe_dazu": ("Leg den Mietvertrag in die Mappe Wohnung", "Put the lease into the collection Flat"),
    "hoerstueck_machen": ("Mach ein Hörstück aus der Mappe Wohnung", "Make an audio overview of the collection Flat"),
    "link_als_dokument": ("Speicher https://example.org/artikel als Dokument", "Save https://example.org/article as a document"),
    "dokument_auswertung": ("Was sind die Kernaussagen im Mietvertrag?", "What are the key points of the lease?"),
    "document_plan": ("Mach eine Präsentation über den Mauerfall", "Make a presentation about the fall of the Berlin Wall"),
    "bild_malen": ("Mal mir eine Katze auf einem Skateboard", "Paint me a cat on a skateboard"),
    "musik_machen": ("Mach mir ein Lied über unsere Katze", "Make me a song about our cat"),
    "musik_bearbeiten": ("Mach mein letztes Lied 30 Sekunden länger", "Make my last song 30 seconds longer"),
    "anruf_planen": ("Ruf mich morgen um sieben an", "Call me tomorrow at seven"),
    "spark_tagebuch": ("Was hast du heute für mich gemacht?", "What did you do for me today?"),
    "reminder_set": ("Erinnere mich in zehn Minuten an den Tee", "Remind me about the tea in ten minutes"),
    "reminder_list": ("Welche Erinnerungen habe ich?", "Which reminders do I have?"),
    "reminder_cancel": ("Lösch die Erinnerung zum Ofen", "Delete the reminder about the oven"),
    "tasks_show": ("Was steht auf der Einkaufsliste?", "What is on the shopping list?"),
    "tasks_add": ("Setz Milch auf die Einkaufsliste", "Put milk on the shopping list"),
    "tasks_change": ("Hak Milch ab", "Tick off milk"),
    "agent_list": ("Was machen meine Agenten?", "What are my agents doing?"),
    "agent_schedule": ("Plane einen Agenten für jeden Montag", "Plan an agent for every Monday"),
    "message_send": ("Schick Anna eine Nachricht, dass ich später komme", "Send Anna a message that I will be late"),
    "message_read": ("Habe ich neue Nachrichten?", "Do I have new messages?"),
    "message_announce": ("Durchsage im Wohnzimmer: Essen ist fertig", "Announcement in the living room: dinner is ready"),
    "calendar_events": ("Welche Termine habe ich morgen?", "Which appointments do I have tomorrow?"),
    "calendar_add": ("Trag morgen um 10 einen Termin beim Zahnarzt ein", "Put a dentist appointment tomorrow at 10 in my calendar"),
    "daily_briefing": ("Was hab ich heute vor?", "What am I up to today?"),
    "weather": ("Wie wird das Wetter morgen?", "What will the weather be like tomorrow?"),
    "mail_list": ("Habe ich neue Mails?", "Do I have new mail?"),
    "mail_read": ("Lies mir die Mail von Anna vor", "Read me the mail from Anna"),
    "mail_tidy_overview": ("Räum mein Postfach auf", "Tidy up my inbox"),
    "parcels": ("Wann kommt meine Amazon-Bestellung?", "When does my Amazon order arrive?"),
    "fuer_dich": ("Was muss ich diese Woche erledigen?", "What do I have to do this week?"),
    "fuer_dich_tun": ("Die Rechnung von Nummer zwei ist erledigt", "Number two is done"),
    "contacts_search": ("Wie ist die Telefonnummer von Anna?", "What is Anna's phone number?"),
    "home_assistant": ("Mach das Licht im Wohnzimmer aus", "Switch off the light in the living room"),
    "home_assistant_states": ("Ist die Haustür zu?", "Is the front door closed?"),
    "home_assistant_history": ("Wann ist die Waschmaschine fertig?", "When is the washing machine done?"),
    "camera_describe": ("Was sieht die Kamera an der Haustür?", "What does the camera at the front door see?"),
    "calendar_change": ("Verschieb den Zahnarzttermin auf Freitag", "Move the dentist appointment to Friday"),
    "agent_change": ("Pausiere den Agenten mit dem Wochenbericht", "Pause the agent with the weekly report"),
    "agent_watch": ("Beobachte den Preis der Bauknecht B6R 88", "Watch the price of the Bauknecht B6R 88"),
    "transit": ("Wann fährt die nächste S-Bahn?", "When does the next S-Bahn leave?"),
    "feeds_news": ("Was gibt's Neues auf Reddit?", "What's new on Reddit?"),
    "spark_zustand": ("Wann wurde zuletzt gesichert?", "When was the last backup?"),
    "code_auftrag": ("Code-Auftrag: im Wetter soll die Windrichtung stehen", "Code order: show the wind direction in the weather"),
    "iphone_action": ("Ruf Mama an", "Call Mum"),
}
