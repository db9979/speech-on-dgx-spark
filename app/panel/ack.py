"""Instant acknowledgement (admin chat.instant_ack under "Gezielte Werkzeugwahl", off, released for every profile at once,
never guests; plan plaene/schnellere-antwort.md "Sofortige Rückmeldung").

Right after the question, before the model has read a word, the Spark says in a short ready-made sentence what it
is doing now ("Ich schau in deinen Kalender."). Never a result, never a yes or no: only what it does next. Which
sentence follows from fixed rules on the person's own words (the Weiche group of intent.py, "Erst lokal", a direct
fetch), never from the model. Small talk gets none (its answer is quick anyway, a "Moment" before it sounds odd).

The sentences are recorded once per voice (same voice, speed, instructions and language as the answer) in a pause
of the TTS (speech first, lowest stage, see record_missing) and kept in STATE/ack/ as raw PCM. Playing them costs no GPU. A sentence that
is not recorded yet is left out this time and recorded afterwards; the filler of a tool round (filler(), a sentence of
the tool's group in TOOL_GROUPS said through the TTS) then speaks instead. When the answer has not started after
BRIDGE_S seconds, one more short sentence bridges the wait (at most once; after a first sentence only when it has
been quiet for BRIDGE_AFTER_ACK_S since).

One opening sentence per answer, from the Spark only (Dominik 2026-11-18: in the car one was cut off and a second
followed): the apps say none of their own. Variety: about fifteen sentences per group, never one of the profile's
last RECENT, never starting with the same word as the one before, and about every third one (NAME_SHARE) names the
person (Dominik 2026-11-18: impersonal first and personal later sounded odd) with their spoken name (profiles.spoken_name:
the Rufname, else a profile name that reads like a first name, never an abbreviation like "db").

Growing the list: every Weiche group needs its sentences (self-test test_ack.Coverage fails for a new group
without any), and Zustand → Prüfen shows which kind of question went without a sentence most often today
(stats), so frequent cases get their sentences too. The log names only the group, never what was asked.
"""
import asyncio
import base64
import hashlib
import json
import os
import random
import re
import threading
import time

from common import STATE, ist_pistimme

BRIDGE_S = 6.0          # seconds after the question without any sound of the answer: the second sentence
BRIDGE_AFTER_ACK_S = 10.0   # after an opening sentence the second one only after this long without a sound
MAX_CLIPS = 2000        # recordings kept at most (oldest go first); one is ~1-2 s, 50-100 KB
NAME_SHARE = 0.34       # share of the sentences that name the person (when the profile has a spoken name)
NAME = "{name}"         # the place of the name in a sentence
MAX_CLIP_BYTES = 8 * 48000   # 8 s of 16-bit mono PCM at 24 kHz
CHUNK = 9600            # bytes per audio event (0.2 s)
NO_ACK = ("smarthome", "plaudern", "lean")   # a direct command is quick, small talk needs none

# Per Weiche group (intent.GROUPS) and a few panel ways: (German, English) variants. ack.pick takes one at random
# among the recorded ones, never one of the profile's last few (Dominik 2026-10-12: more variety, never monotonous;
# 2026-11-18: still too often the same, now about fifteen per group). "{name}" is the person's spoken name.
# The last ones of each group wink a little (Dominik 2026-10-12: about fifty funnier ones, a bit of sarcasm, never at
# the person's expense beyond a gentle tease).
PHRASES = {
    "kalender": (("Ich schau in deinen Kalender.", "Let me check your calendar."),
                 ("Moment, ich schau in den Kalender.", "One moment, checking your calendar."),
                 ("Ich werf mal einen Blick in den Kalender.", "Let me have a look at your calendar."),
                 ("Mal sehen, was im Kalender steht.", "Let's see what's in your calendar."),
                 ("Einen Augenblick, ich prüf deine Termine.", "Just a second, checking your appointments."),
                 ("Ich hol mir kurz deine Termine.", "Getting your appointments."),
                 ("Okay, ich schau, was ansteht.", "Okay, let me see what's coming up."),
                 ("Gleich, ich öffne deinen Kalender.", "Hang on, opening your calendar."),
                 ("Mal sehen, wie verplant du wieder bist.", "Let's see how booked up you are this time."),
                 ("Ich blätter durch dein volles Leben.", "Flipping through your busy, busy life."),
                 ("Kalender auf, Kaffee bereit, los geht's.", "Calendar open, coffee ready, here we go."),
                 ("Sekunde, ich geh deine Termine durch.", "One second, going through your appointments."),
                 ("Ich schlag mal deinen Terminplan auf.", "Opening your schedule."),
                 ("Kurz reinschauen, was du vorhast.", "Quick look at what you have planned."),
                 ("{name}, ich schau in deinen Kalender.", "{name}, let me check your calendar."),
                 ("Moment, {name}, ich hol deine Termine.", "One moment, {name}, getting your appointments."),
                 ("Klar, {name}, ich schau, was ansteht.", "Sure, {name}, let me see what's coming up.")),
    "mail": (("Ich schau in deine Mails.", "Let me check your e-mail."),
             ("Moment, ich schau ins Postfach.", "One moment, checking your inbox."),
             ("Ich werf einen Blick in dein Postfach.", "Let me have a look at your inbox."),
             ("Mal sehen, was an Mails da ist.", "Let's see what mail there is."),
             ("Einen Augenblick, ich hol deine Mails.", "Just a second, fetching your mail."),
             ("Okay, ich seh nach, was Neues da ist.", "Okay, let me see what's new."),
             ("Gleich, ich öffne dein Postfach.", "Hang on, opening your inbox."),
             ("Ich wühl mich durch dein Postfach.", "Digging through your inbox."),
             ("Mal sehen, wer dir alles was will.", "Let's see who wants something from you."),
             ("Postfach auf, Nerven bereit.", "Opening the inbox, bracing myself."),
             ("Sekunde, ich geh die neuen Mails durch.", "One second, going through the new mail."),
             ("Kurz reinschauen, was angekommen ist.", "Quick look at what has arrived."),
             ("Ich sortier mal, was im Postfach liegt.", "Sorting through what is in your inbox."),
             ("{name}, ich schau in deine Mails.", "{name}, let me check your e-mail."),
             ("Moment, {name}, ich öffne dein Postfach.", "One moment, {name}, opening your inbox."),
             ("Klar, {name}, ich seh nach, was da ist.", "Sure, {name}, let me see what's there.")),
    "websuche": (("Ich suche kurz im Netz.", "Let me search the web."),
                 ("Moment, ich schau im Internet nach.", "One moment, looking it up online."),
                 ("Ich frag mal kurz das Internet.", "Let me ask the internet."),
                 ("Einen Augenblick, ich recherchiere.", "Just a second, researching that."),
                 ("Mal sehen, was das Netz dazu sagt.", "Let's see what the web says."),
                 ("Okay, ich such dir das raus.", "Okay, I'll look that up for you."),
                 ("Gleich, ich schau online nach.", "Hang on, checking online."),
                 ("Gute Frage, ich such kurz.", "Good question, let me search."),
                 ("Ich frag mal das allwissende Internet.", "Let me ask the all-knowing internet."),
                 ("Ich google das, ganz unauffällig.", "Looking it up, very discreetly."),
                 ("Ich tauch kurz ins Netz ab.", "Diving into the web for a second."),
                 ("Sekunde, ich schau, was es dazu gibt.", "One second, seeing what's out there."),
                 ("Kurz recherchieren, dann weiß ich mehr.", "A quick search, then I'll know more."),
                 ("Ich klapper mal ein paar Seiten ab.", "Checking a few pages."),
                 ("{name}, ich such das kurz im Netz.", "{name}, let me search the web for that."),
                 ("Moment, {name}, ich schau online nach.", "One moment, {name}, checking online."),
                 ("Gute Frage, {name}, ich recherchiere kurz.", "Good question, {name}, let me look into it.")),
    "erinnerung": (("Okay, einen Moment.", "Okay, one moment."),
                   ("Moment.", "One moment."),
                   ("Alles klar, Augenblick.", "Alright, just a second."),
                   ("Gut, ich kümmere mich drum.", "Right, I'll see to it."),
                   ("Okay, ich schau mir das an.", "Okay, let me take care of that."),
                   ("Einen Augenblick bitte.", "Just a moment, please."),
                   ("Verstanden, kleinen Moment.", "Got it, one second."),
                   ("Ich bin quasi dein Knoten im Taschentuch.", "Consider me the string on your finger."),
                   ("Vergessen ist mein Job nicht, Augenblick.", "Forgetting isn't my job, one second."),
                   ("Notiert im Elefantengedächtnis, gleich.", "Filing it in my elephant memory."),
                   ("Sekunde, ich trag das ein.", "One second, noting that down."),
                   ("Kurz notieren, Augenblick.", "Just noting it, one moment."),
                   ("Ich schreib mir das hinter die Ohren.", "Making a mental note of it."),
                   ("{name}, kleinen Moment.", "{name}, just a second."),
                   ("Alles klar, {name}, Augenblick.", "Alright, {name}, one moment."),
                   ("Gut, {name}, ich kümmere mich drum.", "Fine, {name}, I'll take care of it.")),
    "liste": (("Moment, ich schau auf die Liste.", "One moment, checking the list."),
              ("Ich werf einen Blick auf die Liste.", "Let me look at the list."),
              ("Einen Augenblick, ich hol die Liste.", "Just a second, getting the list."),
              ("Okay, ich kümmere mich um die Liste.", "Okay, I'll see to the list."),
              ("Gleich, ich öffne die Liste.", "Hang on, opening the list."),
              ("Mal sehen, was auf der Liste steht.", "Let's see what's on the list."),
              ("Ich zück den digitalen Einkaufszettel.", "Pulling out the digital shopping list."),
              ("Listen sind meine Leidenschaft, Moment.", "Lists are my passion, one moment."),
              ("Sekunde, ich schau auf deine Listen.", "One second, looking at your lists."),
              ("Kurz die Liste aufschlagen.", "Opening the list for a second."),
              ("Okay, ich schau, was draufsteht.", "Okay, let me see what's on it."),
              ("Einen Moment, ich such die passende Liste.", "One moment, finding the right list."),
              ("{name}, ich schau auf die Liste.", "{name}, let me look at the list."),
              ("Moment, {name}, ich öffne die Liste.", "One moment, {name}, opening the list."),
              ("Klar, {name}, ich kümmere mich um die Liste.", "Sure, {name}, I'll see to the list.")),
    "wetter": (("Ich schau nach dem Wetter.", "Let me check the weather."),
               ("Moment, ich hol das Wetter.", "One moment, getting the weather."),
               ("Mal sehen, was das Wetter macht.", "Let's see what the weather's doing."),
               ("Einen Augenblick, ich prüf die Vorhersage.", "Just a second, checking the forecast."),
               ("Ich werf einen Blick auf die Vorhersage.", "Let me look at the forecast."),
               ("Okay, ich schau aus dem digitalen Fenster.", "Okay, peeking out the digital window."),
               ("Gleich, ich hol die Wetterdaten.", "Hang on, fetching the weather."),
               ("Ich halt mal den Finger in den Wind.", "Sticking a finger in the wind."),
               ("Mal sehen, ob du einen Schirm brauchst.", "Let's see if you need an umbrella."),
               ("Ich frag die Wolken persönlich.", "Asking the clouds personally."),
               ("Sekunde, ich frag den Wetterdienst.", "One second, asking the weather service."),
               ("Kurz nachsehen, was der Himmel vorhat.", "Quick look at what the sky has planned."),
               ("{name}, ich schau nach dem Wetter.", "{name}, let me check the weather."),
               ("Moment, {name}, ich hol die Vorhersage.", "One moment, {name}, getting the forecast."),
               ("Klar, {name}, ich schau raus.", "Sure, {name}, I'll look outside.")),
    "paket": (("Ich schau nach deinen Paketen.", "Let me check your parcels."),
              ("Moment, ich verfolge die Sendung.", "One moment, tracking the shipment."),
              ("Mal sehen, wo dein Paket steckt.", "Let's see where your parcel is."),
              ("Einen Augenblick, ich prüf die Sendungen.", "Just a second, checking your deliveries."),
              ("Okay, ich schau, was unterwegs ist.", "Okay, let me see what's on its way."),
              ("Ich spür dein Paket auf, Detektivmodus an.", "Tracking your parcel, detective mode on."),
              ("Mal sehen, wo der Bote gerade Pause macht.", "Let's see where the courier is taking a break."),
              ("Sekunde, ich schau in die Versandmails.", "One second, checking your shipping mails."),
              ("Ich geh deine Sendungen durch.", "Going through your deliveries."),
              ("Kurz nachsehen, was unterwegs ist.", "Quick look at what's on its way."),
              ("Einen Moment, ich such die Sendungsnummern.", "One moment, finding the tracking numbers."),
              ("Gleich, ich verfolge das Paket.", "Hang on, tracking the parcel."),
              ("{name}, ich schau nach deinen Paketen.", "{name}, let me check your parcels."),
              ("Moment, {name}, ich verfolge die Sendung.", "One moment, {name}, tracking the shipment."),
              ("Klar, {name}, ich schau, was kommt.", "Sure, {name}, let me see what's coming.")),
    "kontakt": (("Moment, ich schau in die Kontakte.", "One moment, checking your contacts."),
                ("Ich werf einen Blick ins Adressbuch.", "Let me look in your address book."),
                ("Einen Augenblick, ich such den Kontakt.", "Just a second, finding the contact."),
                ("Mal sehen, was im Adressbuch steht.", "Let's see what's in your address book."),
                ("Gleich, ich öffne deine Kontakte.", "Hang on, opening your contacts."),
                ("Ich blätter im digitalen Telefonbuch.", "Flipping through the digital phone book."),
                ("Moment, ich such in deinem Freundeskreis.", "One moment, searching your circle of friends."),
                ("Sekunde, ich schlag das Adressbuch auf.", "One second, opening the address book."),
                ("Kurz nachsehen, wen du meinst.", "Quick look at who you mean."),
                ("Okay, ich such die Person heraus.", "Okay, finding that person."),
                ("Gleich, ich schau in deine Kontakte.", "Hang on, checking your contacts."),
                ("Mal sehen, wer da passt.", "Let's see who fits."),
                ("{name}, ich schau in deine Kontakte.", "{name}, let me check your contacts."),
                ("Moment, {name}, ich such den Kontakt.", "One moment, {name}, finding the contact."),
                ("Klar, {name}, ich blätter im Adressbuch.", "Sure, {name}, flipping through the address book.")),
    "gedaechtnis": (("Okay, einen Moment.", "Okay, one moment."),
                    ("Alles klar, Augenblick.", "Alright, just a second."),
                    ("Moment, ich überleg kurz.", "One moment, let me think."),
                    ("Verstanden, kleinen Moment.", "Got it, one second."),
                    ("Gut, ich kümmere mich drum.", "Right, I'll see to it."),
                    ("Ich kram mal in meinem Gedächtnis.", "Rummaging through my memory."),
                    ("Besser als jeder Notizzettel, Moment.", "Better than any sticky note, one moment."),
                    ("Sekunde, ich merk mir das.", "One second, I'll remember that."),
                    ("Kurz nachdenken, Augenblick.", "Let me think for a second."),
                    ("Okay, ich schau, was ich weiß.", "Okay, let me see what I know."),
                    ("Einen Augenblick, ich sortier meine Notizen.", "Just a second, sorting my notes."),
                    ("Gleich, ich schau in meine Notizen.", "Hang on, checking my notes."),
                    ("{name}, kleinen Moment.", "{name}, just a second."),
                    ("Alles klar, {name}, ich merk's mir.", "Alright, {name}, I'll keep that in mind."),
                    ("Moment, {name}, ich überleg kurz.", "One moment, {name}, let me think.")),
    # Finden (fund.py): the own index over documents, NAS, reMarkable and the Wissensbuch
    "finden": (("Ich schau in all deinen Sachen nach.", "Let me look through all your things."),
               ("Moment, ich such das bei dir raus.", "One moment, finding it in your things."),
               ("Ich durchsuche deine Ablage.", "Searching your files."),
               ("Einen Augenblick, ich schau im Suchindex.", "Just a second, checking the index."),
               ("Mal sehen, wo das bei dir liegt.", "Let's see where that is."),
               ("Okay, ich such es dir heraus.", "Okay, digging it out for you."),
               ("Gleich, ich stöbere in deinen Unterlagen.", "Hang on, rummaging through your papers."),
               ("Sekunde, ich such in deinen Sachen.", "One second, searching your things."),
               ("Kurz suchen, Augenblick.", "Searching for a second."),
               ("Ich geh deine Unterlagen durch.", "Going through your papers."),
               ("Ich schau in allen Ecken nach.", "Checking every corner."),
               ("Das find ich, Moment.", "I'll find it, one moment."),
               ("{name}, ich such das bei dir raus.", "{name}, let me find that in your things."),
               ("Moment, {name}, ich durchsuche deine Ablage.", "One moment, {name}, searching your files."),
               ("Klar, {name}, ich schau, wo das liegt.", "Sure, {name}, let me see where that is.")),
    # Mappen (mappen.py): the own collections of documents, pages and notes
    "mappe": (("Ich schau in deine Mappen.", "Let me look at your collections."),
              ("Moment, ich öffne die Mappe.", "One moment, opening the collection."),
              ("Ich blätter kurz durch die Mappe.", "Let me leaf through the collection."),
              ("Gleich, ich schau, was drinliegt.", "Hang on, checking what is inside."),
              ("Okay, ich kümmere mich um die Mappe.", "Okay, seeing to the collection."),
              ("Einen Augenblick, ich sortiere das ein.", "Just a second, filing that."),
              ("Mal sehen, was in deinen Mappen steckt.", "Let's see what your collections hold."),
              ("Sekunde, ich hol die Mappe.", "One second, getting the collection."),
              ("Kurz in die Mappe schauen.", "A quick look into the collection."),
              ("Ich schlag die Mappe auf.", "Opening the collection."),
              ("Mal sehen, was die Mappe hergibt.", "Let's see what the collection has."),
              ("Einen Moment, ich ordne das ein.", "One moment, sorting that in."),
              ("{name}, ich schau in deine Mappen.", "{name}, let me look at your collections."),
              ("Moment, {name}, ich öffne die Mappe.", "One moment, {name}, opening the collection."),
              ("Klar, {name}, ich kümmere mich um die Mappe.", "Sure, {name}, I'll see to the collection.")),
    # Hörstück (hoerstueck.py): one queued from a Mappe, spoken later in quiet minutes
    "hoerstueck": (("Ich reihe das Hörstück ein.", "Queuing the audio overview."),
                   ("Moment, ich plane das Hörstück.", "One moment, planning the audio overview."),
                   ("Gleich, ich bereite das Hörstück vor.", "Hang on, preparing the audio overview."),
                   ("Okay, ich kümmere mich ums Hörstück.", "Okay, seeing to the audio overview."),
                   ("Einen Augenblick, ich merke es mir vor.", "Just a second, noting it down."),
                   ("Mal sehen, was die Mappe hergibt.", "Let's see what the collection offers."),
                   ("Sekunde, ich plane das Hörstück.", "One second, planning the audio overview."),
                   ("Kurz einreihen, Augenblick.", "Queuing it, one moment."),
                   ("Ich schreib das Hörstück auf die Liste.", "Putting the audio overview on the list."),
                   ("Gleich, ich such die passenden Stellen.", "Hang on, finding the right parts."),
                   ("Okay, ich stell das Hörstück zusammen.", "Okay, putting the audio overview together."),
                   ("Das Hörstück kommt auf den Plan.", "The audio overview goes on the plan."),
                   ("{name}, ich reihe das Hörstück ein.", "{name}, queuing the audio overview."),
                   ("Moment, {name}, ich plane das Hörstück.", "One moment, {name}, planning the audio overview."),
                   ("Klar, {name}, ich kümmere mich drum.", "Sure, {name}, I'll see to it.")),
    # Links als Dokument (doklink.py): a page fetched and kept as an own document
    "doklink": (("Ich hole die Seite.", "Fetching the page."),
                ("Moment, ich lege den Link ab.", "One moment, filing the link."),
                ("Gleich, ich speichere die Seite.", "Hang on, saving the page."),
                ("Okay, ich hole das für deine Dokumente.", "Okay, getting that for your documents."),
                ("Einen Augenblick, die Seite kommt.", "Just a second, the page is coming."),
                ("Mal sehen, ob die Seite antwortet.", "Let's see whether the page answers."),
                ("Sekunde, ich hol die Seite.", "One second, fetching the page."),
                ("Kurz abholen und ablegen.", "Fetching and filing it."),
                ("Ich leg die Seite bei deinen Dokumenten ab.", "Filing the page with your documents."),
                ("Gleich, ich lade die Seite.", "Hang on, loading the page."),
                ("Okay, ich hol den Inhalt der Seite.", "Okay, getting the page's content."),
                ("Einen Moment, ich speichere den Link.", "One moment, saving the link."),
                ("{name}, ich hole die Seite.", "{name}, fetching the page."),
                ("Moment, {name}, ich lege den Link ab.", "One moment, {name}, filing the link."),
                ("Klar, {name}, ich speichere die Seite.", "Sure, {name}, saving the page.")),
    "dokument": (("Ich schau in deinen Dokumenten nach.", "Let me check your documents."),
                 ("Moment, ich schau in die Dokumente.", "One moment, looking at your documents."),
                 ("Ich blätter kurz durch deine Unterlagen.", "Let me leaf through your papers."),
                 ("Einen Augenblick, ich such das Dokument.", "Just a second, finding the document."),
                 ("Mal sehen, was in deinen Unterlagen steht.", "Let's see what your documents say."),
                 ("Okay, ich durchsuche deine Dokumente.", "Okay, searching your documents."),
                 ("Gleich, ich schau in deine Ablage.", "Hang on, checking your files."),
                 ("Ich wühl mich durch den Papierkram.", "Digging through the paperwork."),
                 ("Ablage öffnen, Staub wegpusten, Moment.", "Opening the files, blowing off the dust."),
                 ("Sekunde, ich such in deinen Dokumenten.", "One second, searching your documents."),
                 ("Kurz in die Unterlagen schauen.", "A quick look at your papers."),
                 ("Ich schlag deine Ablage auf.", "Opening your files."),
                 ("{name}, ich schau in deinen Dokumenten nach.", "{name}, let me check your documents."),
                 ("Moment, {name}, ich such das Dokument.", "One moment, {name}, finding the document."),
                 ("Klar, {name}, ich schau in deine Ablage.", "Sure, {name}, checking your files.")),
    "erstellen": (("Moment, ich kümmere mich um das Dokument.", "One moment, I'll see to the document."),
                  ("Okay, einen Moment, ich bereite das vor.", "Okay, one moment, I'll prepare it."),
                  ("Alles klar, ich setz das auf.", "Alright, I'll draft that."),
                  ("Gut, ich mach mich an die Arbeit.", "Right, getting to work on it."),
                  ("Einen Augenblick, ich schreib das zusammen.", "Just a second, putting it together."),
                  ("Verstanden, ich fang gleich an.", "Got it, starting on it now."),
                  ("Ich spitz schon mal den digitalen Bleistift.", "Sharpening the digital pencil."),
                  ("Kreativmodus an, gleich wird's schön.", "Creative mode on, this will look nice."),
                  ("Ich hau in die virtuellen Tasten.", "Hammering away at the virtual keys."),
                  ("Sekunde, ich fang gleich an.", "One second, starting right away."),
                  ("Kurz sammeln, dann schreib ich los.", "Gathering things, then I'll start writing."),
                  ("Ich setz mich gleich dran.", "Getting right on it."),
                  ("{name}, ich setz das auf.", "{name}, I'll draft that."),
                  ("Moment, {name}, ich bereite das vor.", "One moment, {name}, preparing it."),
                  ("Klar, {name}, ich mach mich an die Arbeit.", "Sure, {name}, getting to work.")),
    "bild": (("Moment, ich hole Pinsel und Farben.", "One moment, getting brush and paints."),
             ("Alles klar, ich male das.", "Alright, I'll paint that."),
             ("Gute Idee, ich fang an zu malen.", "Nice idea, starting to paint."),
             ("Einen Augenblick, die Leinwand steht schon.", "Just a second, the canvas is ready."),
             ("Verstanden, das Bild kommt gleich.", "Got it, the picture is on its way."),
             ("Ich mische schon mal die Farben.", "Mixing the colours already."),
             ("Sekunde, ich skizziere schon.", "One second, sketching already."),
             ("Okay, ich male drauflos.", "Okay, painting away."),
             ("Ich such mir den passenden Pinsel.", "Finding the right brush."),
             ("Gleich, die Farbe ist schon auf der Palette.", "Hang on, the paint is on the palette."),
             ("Ein Bild, kommt sofort in Arbeit.", "A picture, going into work now."),
             ("Mal sehen, was ich daraus mache.", "Let's see what I make of it."),
             ("{name}, ich male das.", "{name}, I'll paint that."),
             ("Moment, {name}, ich hole Pinsel und Farben.", "One moment, {name}, getting brush and paints."),
             ("Klar, {name}, das Bild kommt gleich.", "Sure, {name}, the picture is on its way.")),
    "musik": (("Moment, ich stimme die Instrumente.", "One moment, tuning the instruments."),
              ("Alles klar, ich mache das Lied.", "Alright, I'll make the song."),
              ("Gute Idee, ich fang an zu komponieren.", "Nice idea, starting to compose."),
              ("Einen Augenblick, das Lied kommt gleich.", "Just a second, the song is on its way."),
              ("Ich zähle schon mal ein.", "Counting in already."),
              ("Sekunde, ich stimme noch die Gitarre.", "One second, still tuning the guitar."),
              ("Okay, ich schreib die Melodie.", "Okay, writing the melody."),
              ("Ich such den passenden Rhythmus.", "Finding the right rhythm."),
              ("Gleich, das Orchester sitzt schon.", "Hang on, the orchestra is seated."),
              ("Mal sehen, wie das klingt.", "Let's see how that sounds."),
              ("Ein Lied, kommt sofort in Arbeit.", "A song, going into work now."),
              ("Ich wärm schon mal die Stimme auf.", "Warming up my voice."),
              ("{name}, ich mache das Lied.", "{name}, I'll make the song."),
              ("Moment, {name}, ich stimme die Instrumente.", "One moment, {name}, tuning the instruments."),
              ("Klar, {name}, das Lied kommt gleich.", "Sure, {name}, the song is on its way.")),
    "nachricht": (("Moment.", "One moment."),
                  ("Einen Augenblick.", "Just a second."),
                  ("Alles klar, kleinen Moment.", "Alright, one second."),
                  ("Okay, ich kümmere mich drum.", "Okay, I'll see to it."),
                  ("Verstanden, Augenblick.", "Got it, just a moment."),
                  ("Ich spiel kurz Brieftaube.", "Playing carrier pigeon for a second."),
                  ("Moment, ich bin dein Bote.", "One moment, I'm your messenger."),
                  ("Sekunde, ich schreib das auf.", "One second, writing it down."),
                  ("Kurz aufsetzen, Augenblick.", "Drafting it, one moment."),
                  ("Gleich, ich bereite die Nachricht vor.", "Hang on, preparing the message."),
                  ("Mal sehen, wem das gilt.", "Let's see who that's for."),
                  ("Einen Moment, ich formuliere das.", "One moment, putting it into words."),
                  ("{name}, kleinen Moment.", "{name}, just a second."),
                  ("Moment, {name}, ich bereite das vor.", "One moment, {name}, getting it ready."),
                  ("Klar, {name}, ich kümmere mich drum.", "Sure, {name}, I'll see to it.")),
    "agent": (("Moment, ich frag kurz nach.", "One moment, I'll ask."),
              ("Einen Augenblick, ich kläre das.", "Just a second, sorting that out."),
              ("Okay, ich kümmere mich drum.", "Okay, I'll see to it."),
              ("Alles klar, ich frag mal herum.", "Alright, let me ask around."),
              ("Gleich, ich hol mir die Auskunft.", "Hang on, getting the details."),
              ("Ich setz meine Leute drauf an.", "Putting my people on it."),
              ("Ich schick einen kleinen Helfer los.", "Sending out a little helper."),
              ("Sekunde, ich frag den Dienst.", "One second, asking the service."),
              ("Kurz nachfragen, Augenblick.", "Asking around, one moment."),
              ("Mal sehen, was die anderen sagen.", "Let's see what the others say."),
              ("Ich hör mich kurz um.", "Listening around for a moment."),
              ("Einen Moment, ich hole die Antwort.", "One moment, getting the answer."),
              ("{name}, ich frag kurz nach.", "{name}, let me ask."),
              ("Moment, {name}, ich kläre das.", "One moment, {name}, sorting that out."),
              ("Klar, {name}, ich kümmere mich drum.", "Sure, {name}, I'll see to it.")),
    "iphone": (("Einen Moment.", "One moment."),
               ("Augenblick, ich schau aufs Handy.", "Just a second, checking the phone."),
               ("Okay, kleinen Moment.", "Okay, one second."),
               ("Alles klar, ich kümmere mich drum.", "Alright, I'll see to it."),
               ("Gleich, ich frag dein Handy.", "Hang on, asking your phone."),
               ("Ich klopf mal bei deinem Handy an.", "Knocking on your phone's door."),
               ("Moment, ich ruf dein Handy zur Ordnung.", "One moment, having a word with your phone."),
               ("Sekunde, ich sag deinem Handy Bescheid.", "One second, telling your phone."),
               ("Kurz ans Handy weitergeben.", "Passing it to your phone."),
               ("Mal sehen, was dein Handy sagt.", "Let's see what your phone says."),
               ("Ich schick das an dein Handy.", "Sending it to your phone."),
               ("Einen Augenblick, dein Handy übernimmt.", "Just a second, your phone takes over."),
               ("{name}, einen Moment.", "{name}, one moment."),
               ("Moment, {name}, ich frag dein Handy.", "One moment, {name}, asking your phone."),
               ("Klar, {name}, ich kümmere mich drum.", "Sure, {name}, I'll see to it.")),
    "spark": (("Moment, ich schau in der Anleitung nach.", "One moment, checking the guide."),
              ("Ich blätter kurz in meiner Anleitung.", "Let me flip through my guide."),
              ("Einen Augenblick, ich schau, wie das geht.", "Just a second, let me see how that works."),
              ("Mal sehen, was die Anleitung sagt.", "Let's see what the guide says."),
              ("Gute Frage, ich schau kurz nach.", "Good question, let me check."),
              ("Selbst ich muss mal nachlesen, Moment.", "Even I have to read up sometimes."),
              ("Ich schau in meine eigene Bedienungsanleitung.", "Checking my own instruction manual."),
              ("Sekunde, ich schlag das nach.", "One second, looking it up."),
              ("Kurz in die Hilfe schauen.", "A quick look at the help."),
              ("Okay, ich such die passende Stelle.", "Okay, finding the right page."),
              ("Gleich, ich schau in meine Hilfe.", "Hang on, checking my help."),
              ("Einen Moment, ich such dir den Weg raus.", "One moment, finding the way for you."),
              ("{name}, ich schau in der Anleitung nach.", "{name}, let me check the guide."),
              ("Moment, {name}, ich schau, wie das geht.", "One moment, {name}, let me see how that works."),
              ("Klar, {name}, ich schlag das nach.", "Sure, {name}, looking it up.")),
    "codeauftrag": (("Ich gebe den Auftrag an OpenCode.", "Handing the order to OpenCode."),
                    ("Moment, OpenCode bekommt den Auftrag.", "One moment, OpenCode gets the order."),
                    ("Ich setz OpenCode daran.", "Putting OpenCode on it."),
                    ("Einen Augenblick, ich richte den Auftrag ein.", "Just a second, setting up the order."),
                    ("Gut, OpenCode legt gleich los.", "Fine, OpenCode starts in a moment."),
                    ("Ich schreib den Auftrag für OpenCode auf.", "Writing the order down for OpenCode."),
                    ("Sekunde, ich bereite den Auftrag vor.", "One second, preparing the order."),
                    ("Kurz aufschreiben, dann geht's los.", "Writing it down, then off it goes."),
                    ("Okay, OpenCode bekommt Arbeit.", "Okay, OpenCode gets some work."),
                    ("Gleich, ich reiche das an OpenCode weiter.", "Hang on, passing it to OpenCode."),
                    ("Mal sehen, was OpenCode daraus macht.", "Let's see what OpenCode makes of it."),
                    ("Ich schick den Auftrag los.", "Sending the order off."),
                    ("{name}, ich gebe den Auftrag an OpenCode.", "{name}, handing the order to OpenCode."),
                    ("Moment, {name}, ich richte den Auftrag ein.", "One moment, {name}, setting up the order."),
                    ("Klar, {name}, OpenCode legt gleich los.", "Sure, {name}, OpenCode starts in a moment.")),
    "zustand": (("Moment, ich schau, wie es mir geht.", "One moment, checking how I am doing."),
                ("Ich prüf kurz meinen Zustand.", "Let me check my state."),
                ("Einen Augenblick, ich schau auf meine Anzeigen.", "Just a second, looking at my gauges."),
                ("Mal sehen, was bei mir alles läuft.", "Let's see what is running here."),
                ("Gute Frage, ich schau kurz nach.", "Good question, let me check."),
                ("Ich hör kurz in mich hinein.", "Let me listen to myself for a second."),
                ("Sekunde, ich schau auf meine Werte.", "One second, checking my readings."),
                ("Kurz durchchecken, Augenblick.", "Quick check-up, one moment."),
                ("Okay, ich schau, wie es läuft.", "Okay, let me see how things are running."),
                ("Gleich, ich frag meine Dienste.", "Hang on, asking my services."),
                ("Einen Moment, ich mach einen kurzen Rundgang.", "One moment, doing a quick round."),
                ("Ich fühl mir mal selbst den Puls.", "Taking my own pulse."),
                ("{name}, ich prüf kurz meinen Zustand.", "{name}, let me check my state."),
                ("Moment, {name}, ich schau auf meine Anzeigen.", "One moment, {name}, looking at my gauges."),
                ("Klar, {name}, ich schau, wie es mir geht.", "Sure, {name}, checking how I am doing.")),
    "wikipedia": (("Ich schau kurz in der Wikipedia nach.", "Let me check Wikipedia."),
                  ("Moment, ich frag die Wikipedia.", "One moment, asking Wikipedia."),
                  ("Mal sehen, was die Wikipedia weiß.", "Let's see what Wikipedia knows."),
                  ("Einen Augenblick, ich schlag das nach.", "Just a second, looking that up."),
                  ("Gute Frage, ich schlag kurz nach.", "Good question, let me look it up."),
                  ("Okay, ich schau im Lexikon.", "Okay, checking the encyclopedia."),
                  ("Ich frag das Lexikon meines Vertrauens.", "Asking my favourite encyclopedia."),
                  ("Besserwissermodus an, Moment.", "Know-it-all mode on, one moment."),
                  ("Sekunde, ich schlag das Lexikon auf.", "One second, opening the encyclopedia."),
                  ("Kurz nachschlagen, Augenblick.", "Looking it up, one moment."),
                  ("Mal sehen, was da steht.", "Let's see what it says."),
                  ("Gleich, ich such den Artikel.", "Hang on, finding the article."),
                  ("{name}, ich schau in der Wikipedia nach.", "{name}, let me check Wikipedia."),
                  ("Moment, {name}, ich schlag das nach.", "One moment, {name}, looking that up."),
                  ("Klar, {name}, ich frag die Wikipedia.", "Sure, {name}, asking Wikipedia.")),
    "archiv": (("Ich schau in deinem Archiv nach.", "Let me check your archive."),
               ("Moment, ich schlag im Archiv nach.", "One moment, looking it up in the archive."),
               ("Mal sehen, was das Archiv dazu hat.", "Let's see what the archive has."),
               ("Einen Augenblick, ich durchsuche das Archiv.", "Just a second, searching the archive."),
               ("Gute Frage, ich schau ins Archiv.", "Good question, checking the archive."),
               ("Okay, ich blätter im Archiv.", "Okay, browsing the archive."),
               ("Ich steig mal in den Keller ins Archiv.", "Heading down to the archive in the basement."),
               ("Ich puste den Staub von den alten Akten.", "Blowing the dust off the old files."),
               ("Sekunde, ich such im Archiv.", "One second, searching the archive."),
               ("Kurz im Archiv nachsehen.", "A quick look in the archive."),
               ("Gleich, ich hol die alten Bände.", "Hang on, getting the old volumes."),
               ("Mal sehen, was da früher stand.", "Let's see what it said back then."),
               ("{name}, ich schau in deinem Archiv nach.", "{name}, let me check your archive."),
               ("Moment, {name}, ich schlag im Archiv nach.", "One moment, {name}, looking it up in the archive."),
               ("Klar, {name}, ich durchsuche das Archiv.", "Sure, {name}, searching the archive.")),
    # Tagesstart (daily_briefing, fetched by the panel itself): „Gib mir mein Briefing“, the briefing on getting into the car
    "tag": (("Ich schau, was heute ansteht.", "Let me see what today holds."),
            ("Moment, ich stell deinen Tag zusammen.", "One moment, putting your day together."),
            ("Gleich, ich hol Termine, Wetter und Mails.", "Hang on, getting appointments, weather and mail."),
            ("Mal sehen, was der Tag bringt.", "Let's see what the day brings."),
            ("Einen Augenblick, ich sammel das Wichtigste.", "Just a second, gathering what matters."),
            ("Okay, ich mach dir den Überblick.", "Okay, making your overview."),
            ("Sekunde, ich schau auf den Tag.", "One second, looking at the day."),
            ("Ich blätter kurz durch deinen Tag.", "Flipping through your day."),
            ("Kurz sortieren, dann geht's los.", "Sorting things out, then off we go."),
            ("Der Überblick kommt gleich.", "Your overview is coming right up."),
            ("Kaffee hab ich keinen, aber den Überblick.", "Can't make coffee, but I can make your overview."),
            ("Ich sortier dir den Tag vor.", "Sorting your day for you."),
            ("{name}, ich schau, was heute ansteht.", "{name}, let me see what today holds."),
            ("Moment, {name}, ich stell deinen Tag zusammen.", "One moment, {name}, putting your day together."),
            ("Klar, {name}, der Überblick kommt gleich.", "Sure, {name}, your overview is coming up."),
            ("Gleich, {name}, ich sammel das Wichtigste.", "Hang on, {name}, gathering what matters.")),
    # Frühere Gespräche (history_search)
    "verlauf": (("Ich schau in unseren früheren Gesprächen nach.", "Let me look at our earlier conversations."),
                ("Moment, ich such in unserem Verlauf.", "One moment, searching our history."),
                ("Mal sehen, was wir dazu besprochen haben.", "Let's see what we said about it."),
                ("Einen Augenblick, ich blätter zurück.", "Just a second, leafing back."),
                ("Gleich, ich such das alte Gespräch.", "Hang on, finding the old conversation."),
                ("Okay, ich schau, was wir hatten.", "Okay, let me see what we had."),
                ("Sekunde, ich spul kurz zurück.", "One second, rewinding a bit."),
                ("Kurz zurückblättern, Augenblick.", "Leafing back, one moment."),
                ("Ich kram in unseren alten Gesprächen.", "Rummaging through our old talks."),
                ("Da war doch was, Moment.", "There was something, one moment."),
                ("{name}, ich schau in unseren Gesprächen nach.", "{name}, let me check our conversations."),
                ("Moment, {name}, ich blätter zurück.", "One moment, {name}, leafing back."),
                ("Klar, {name}, ich such das alte Gespräch.", "Sure, {name}, finding the old conversation.")),
    # panel ways, not Weiche groups
    "lokal": (("Ich schau kurz nach.", "Let me look that up."),
              ("Moment, ich schau nach.", "One moment, let me check."),
              ("Einen Augenblick, ich such das raus.", "Just a second, digging that out."),
              ("Mal sehen, was ich dazu finde.", "Let's see what I can find."),
              ("Gute Frage, ich schau mal.", "Good question, let me see."),
              ("Okay, ich schau in meine Unterlagen.", "Okay, checking my sources."),
              ("Gleich, ich such kurz.", "Hang on, searching."),
              ("Ich durchwühl mal meine Schubladen.", "Rummaging through my drawers."),
              ("Mal sehen, was ich hier so rumliegen hab.", "Let's see what I've got lying around."),
              ("Gute Frage, ich hab da was im Hinterkopf.", "Good question, I have something in mind."),
              ("Sekunde, ich schau, was ich habe.", "One second, seeing what I have."),
              ("Kurz nachsehen, Augenblick.", "A quick look, one moment."),
              ("Ich geh meine Quellen durch.", "Going through my sources."),
              ("{name}, ich schau kurz nach.", "{name}, let me look that up."),
              ("Moment, {name}, ich such das raus.", "One moment, {name}, digging that out."),
              ("Gute Frage, {name}, ich schau mal.", "Good question, {name}, let me see.")),
    "bridge": (("Dauert einen Moment länger.", "This takes a little longer."),
               ("Gleich hab ich's.", "Almost there."),
               ("Ich bin noch dran.", "Still on it."),
               ("Einen kleinen Moment noch.", "Just a little longer."),
               ("Fast fertig, gleich kommt's.", "Nearly ready, coming right up."),
               ("Noch einen Augenblick, bitte.", "One more moment, please."),
               ("Ich sortier das noch kurz.", "Just sorting it out."),
               ("Das braucht etwas länger als gedacht.", "This is taking a bit longer than expected."),
               ("Bleib dran, gleich geht's weiter.", "Stay with me, nearly there."),
               ("Ich hab's fast zusammen.", "I've almost got it together."),
               ("Gut Ding will Weile haben.", "Good things take time."),
               ("Die Hamster im Rad treten schon fester.", "The hamsters are running faster now."),
               ("Ich denk so schnell ich kann.", "Thinking as fast as I can."),
               ("Rom wurde auch nicht an einem Tag gebaut.", "Rome wasn't built in a day either."),
               ("Kurz durchatmen, gleich geht's weiter.", "Take a breath, nearly there."),
               ("Ich bin langsam, aber gründlich.", "I'm slow, but thorough."),
               ("Die Antwort ist unterwegs, versprochen.", "The answer is on its way, promise."),
               ("Das ist kniffliger als gedacht.", "This is trickier than I thought."),
               ("Mein Gehirn rattert noch.", "My brain is still whirring."),
               ("Gleich, ich poliere die Antwort noch.", "Hang on, polishing the answer."),
               ("Geduld ist eine Tugend, sagt man.", "Patience is a virtue, they say."),
               ("Die Grafikkarte schwitzt schon.", "The graphics card is sweating already."),
               ("Ich hol nur noch schnell Luft.", "Just catching my breath."),
               ("Fast fertig, ich schwöre.", "Nearly ready, I swear."),
               ("Ich hab gleich alles beisammen.", "I'll have it all together soon."),
               ("Noch ein paar Sekunden.", "Just a few more seconds."),
               ("Moment noch, ich prüfe das lieber genau.", "One moment, I'd rather check it properly."),
               ("Ich bin gleich so weit.", "I'm nearly there."),
               ("Dauert heute etwas, sorry.", "Taking a bit today, sorry."),
               ("Gleich, ich fasse das noch zusammen.", "Hang on, summing it up."),
               ("Noch kurz Geduld, bitte.", "A little patience, please."),
               ("Ich lass dich nicht hängen, gleich.", "I won't leave you hanging, coming up."),
               ("{name}, dauert einen Moment länger.", "{name}, this takes a little longer."),
               ("Gleich, {name}, ich bin noch dran.", "Hang on, {name}, still on it."),
               ("Fast fertig, {name}.", "Nearly there, {name}."),
               ("Noch einen Augenblick, {name}.", "One more moment, {name}.")),
}

_recent = {}            # uid -> the last sentences said to this profile, newest last (RAM only)
RECENT = 8              # never one of the last RECENT sentences while another is recorded
_making = set()         # cache keys being recorded right now
_lock = threading.Lock()
stats = {}              # day -> {"with": n, "without": n, "groups": {group: n}} (RAM only, for Zustand)


def _dir():
    return os.path.join(STATE, "ack")


def lang_of(english):
    return "English" if english else "German"


def key(tts_body, text, lang):
    """The recording's name: the same voice, speed, instructions and language as the answer, and the text."""
    k = {"v": str(tts_body.get("voice") or ""), "s": tts_body.get("speed") or 1.0,
         "i": str(tts_body.get("instructions") or ""), "l": lang, "t": text}
    return hashlib.sha256(json.dumps(k, sort_keys=True).encode()).hexdigest()[:40]


def _path(k):
    return os.path.join(_dir(), k + ".pcm") if re.fullmatch(r"[0-9a-f]{40}", k or "") else None


def clip(k):
    """The recorded PCM (bytes) or None."""
    p = _path(k)
    try:
        with open(p, "rb") as f:
            data = f.read(MAX_CLIP_BYTES + 1)
    except (OSError, TypeError):
        return None
    return data if 0 < len(data) <= MAX_CLIP_BYTES else None


def save(k, pcm):
    p = _path(k)
    if not p or not pcm or len(pcm) > MAX_CLIP_BYTES:
        return False
    os.makedirs(_dir(), mode=0o700, exist_ok=True)
    tmp = p + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "wb") as f:
        f.write(pcm)
    os.replace(tmp, p)
    _trim()
    return True


def _trim():
    try:
        files = [os.path.join(_dir(), n) for n in os.listdir(_dir()) if n.endswith(".pcm")]
    except OSError:
        return
    if len(files) <= MAX_CLIPS:
        return
    files.sort(key=lambda p: os.path.getmtime(p))
    for p in files[:len(files) - MAX_CLIPS]:
        try:
            os.remove(p)
        except OSError:
            pass


def chunks(pcm):
    """The recording as base64 pieces for {"type": "audio"} events (the browser plays them like the answer)."""
    for i in range(0, len(pcm), CHUNK):
        yield base64.b64encode(pcm[i:i + CHUNK]).decode()


def group_of(route_names, direct=None, local=False, web=False):
    """Which sentences fit this turn (fixed rules): the one Weiche group, else "lokal" for a "Erst lokal" look,
    else None (small talk, a smart home command, several groups at once, nothing recognised). web: „Auch im Internet
    suchen“ (lokal.web_chip), the panel searches the web with the question's own words: "websuche"."""
    if web:
        return "websuche"
    names = [n for n in (route_names or []) if n not in NO_ACK]
    if direct in TOOL_GROUPS:   # the one tool the panel fetches itself (intent.DIRECT)
        return TOOL_GROUPS[direct]
    if direct == "spark_hilfe":
        return "spark"
    if len(names) == 1 and names[0] in PHRASES and not set(route_names or []) & set(NO_ACK):
        return names[0]
    if len(names) == 2 and "finden" in names and not set(route_names or []) & set(NO_ACK):
        return "finden"   # „Such mir die Rechnung …“: Finden beside dokument, mail or paket
    if set(names) == {"hoerstueck", "mappe"} and not set(route_names or []) & set(NO_ACK):
        return "hoerstueck"   # „Mach ein Hörstück aus der Mappe Wohnung“: the Mappe it names beside it
    if local and not route_names:
        return "lokal"
    return None


def _first(text):
    """The first word, to never start two sentences in a row alike ("Moment, …" after "Moment, …")."""
    m = re.match(r"\W*([\wäöüÄÖÜß']+)", text or "")
    return m.group(1).lower() if m else ""


def _texts(group, english, name):
    """The group's sentences in one language, with the name in place; those with a name only when there is one."""
    out = []
    for v in PHRASES.get(group) or ():
        t = v[1 if english else 0]
        if NAME in t:
            if not name:
                continue
            t = t.replace(NAME, name)
        out.append(t)
    return out


def pick(group, uid, english=False, have=None, bump=True, name=""):
    """A sentence of the group for this profile: at random among the recorded ones (have(text) -> bool), never one
    of the profile's last RECENT sentences while another fits (so it does not sound like a recording), never starting
    with the same word as the last one when another fits, about every NAME_SHARE-th one with the name; else the one
    said longest ago. None when the group has none or none is recorded yet."""
    opts = _texts(group, english, name)
    if have is not None:
        opts = [t for t in opts if have(t)]
    if not opts:
        return None
    with _lock:
        last = _recent.get(uid or "", [])
        if last:   # never the same start as the last one while another fits
            opts = [t for t in opts if _first(t) != _first(last[-1])] or opts
        fresh = [t for t in opts if t not in last]
        if fresh and name:
            named = [t for t in fresh if name in t]
            plain = [t for t in fresh if name not in t]
            fresh = (named if random.random() < NAME_SHARE else plain) or fresh
        text = random.choice(fresh) if fresh else min(opts, key=last.index)
        if bump:
            _recent[uid or ""] = (last + [text])[-RECENT:]
            if len(_recent) > 500:
                _recent.clear()
    return text


def phrase(group, uid, english=False, bump=True, name=""):
    """pick() without looking at the recordings."""
    return pick(group, uid, english, None, bump, name)


# A tool the panel or the model calls that takes a moment: the sentence said through the TTS while it runs, when no
# recorded sentence came first (the fixed sentence of a tool's own module, extras "filler", only for tools not here)
TOOL_GROUPS = {"calendar_events": "kalender", "mail_list": "mail", "mail_search": "mail", "mail_read": "mail",
               "history_search": "verlauf", "document_search": "dokument", "daily_briefing": "tag",
               "weather": "wetter", "wikipedia": "wikipedia", "archive_search": "archiv", "parcels": "paket",
               "contacts_search": "kontakt", "spark_zustand": "zustand", "link_als_dokument": "doklink",
               "code_auftrag": "codeauftrag", "bild_malen": "bild"}


def filler(tool, own, uid, english=False, name=""):
    """The sentence while a tool runs: one of its group (varied like pick), else the tool module's own fixed one
    (own: {tool: (de, en)}), else None."""
    if tool in TOOL_GROUPS:
        return phrase(TOOL_GROUPS[tool], uid, english, name=name)
    fixed = (own or {}).get(tool)
    return fixed[1 if english else 0] if fixed else None


def all_texts(english=False, name=""):
    """Every sentence once, the first variant of each group first (recorded in this order, so every group soon
    has one); with a name also the sentences that name it."""
    rows = [_texts(g, english, name) for g in PHRASES]
    return list(dict.fromkeys(t for i in range(max(map(len, rows))) for r in rows if i < len(r) for t in [r[i]]))


def count(group, ok, now=None):
    """For Zustand → Prüfen: answers with and without a ready sentence today, and the groups that went without."""
    day = time.strftime("%Y-%m-%d", time.localtime(now if now is not None else time.time()))
    with _lock:
        for d in [d for d in stats if d != day]:
            del stats[d]
        s = stats.setdefault(day, {"with": 0, "without": 0, "groups": {}})
        s["with" if ok else "without"] += 1
        if not ok:
            s["groups"][group] = s["groups"].get(group, 0) + 1


def today(now=None):
    day = time.strftime("%Y-%m-%d", time.localtime(now if now is not None else time.time()))
    s = stats.get(day) or {"with": 0, "without": 0, "groups": {}}
    top = sorted(s["groups"].items(), key=lambda x: -x[1])[:3]
    return {"with": s["with"], "without": s["without"], "top": [{"group": g, "n": n} for g, n in top]}


def recorded(tts_body, lang):
    """For pick(): is this sentence recorded in this voice and language?"""
    return lambda t: os.path.exists(_path(key(tts_body, t, lang)))


def missing_ok(tts_body, lang, name=""):
    """True when every sentence of this voice and language (with this name) is recorded."""
    return all(os.path.exists(_path(key(tts_body, t, lang))) for t in all_texts(lang == "English", name))


_later = set()


def later(coro):
    """Runs coro in the background (the reference is kept until it ends)."""
    task = asyncio.ensure_future(coro)
    _later.add(task)
    task.add_done_callback(_later.discard)
    return task


async def _record(c, url, headers, body):
    """One sentence through the TTS (stream, PCM): the bytes or None."""
    pcm = b""
    async with c.stream("POST", url, json=dict(body, stream=True, response_format="pcm"), headers=headers) as r:
        if r.status_code != 200:
            return None
        async for line in r.aiter_lines():
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:])
            except ValueError:
                continue
            if ev.get("type") == "speech.audio.delta" and ev.get("audio"):
                try:
                    pcm += base64.b64decode(ev["audio"])
                except ValueError:
                    return None
                if len(pcm) > MAX_CLIP_BYTES:
                    return None
    return pcm or None


async def record_missing(url, headers, tts_body, lang, texts=None, sleep=asyncio.sleep, name=""):
    """Records every sentence of this voice and language that is missing, in a pause (speech first: it waits until
    nobody spoke for vorrang.GRACE seconds, asks the TTS with the lowest stage so a person's request goes first, and
    stops as soon as an answer streams again; the rest follows after the next answer that misses one)."""
    import httpx
    import stufe
    import vorrang
    if ist_pistimme(url):   # the Pi-Stimme: never kept as this voice's clip
        return 0
    texts = texts or all_texts(lang == "English", name)
    todo = []
    with _lock:
        for t in dict.fromkeys(texts):
            k = key(tts_body, t, lang)
            if k not in _making and clip(k) is None:
                _making.add(k)
                todo.append((k, t))
    if not todo:
        return 0
    made = 0
    body = {x: tts_body[x] for x in ("voice", "speed", "instructions") if tts_body.get(x)}
    hdrs = dict(headers, **stufe.headers("hinten"))
    try:
        await vorrang.quiet("Sätze für die Rückmeldung", sleep)
        start = time.time()
        _bg("run")
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=5)) as c:
            for k, t in todo:
                if vorrang._local[0] > start:   # an answer streams again: the rest in the next pause
                    break
                try:
                    pcm = await _record(c, url, hdrs, dict(body, input=t, language=lang))
                except Exception as e:   # the TTS restarting ...: next time again
                    print(f"ack: recording stopped ({type(e).__name__})", flush=True)
                    break
                if pcm and save(k, pcm):
                    made += 1
    finally:
        with _lock:
            for k, _ in todo:
                _making.discard(k)
        _bg(None, made, len(todo), start if "start" in locals() else None)
    print(f"ack: {made} of {len(todo)} sentence(s) recorded for one voice ({lang})", flush=True)
    return made


def _bg(state, made=0, n=0, start=None):
    """Zustand → Live: recording the sentences shows as background work while it runs, then a line with the count."""
    try:
        import live
        if state == "run":
            live.bg("Sätze für die Rückmeldung", "run")
        elif start is not None:
            live.bg_done("Sätze für die Rückmeldung", made == n, time.time() - start, f"{made} von {n} aufgenommen")
        else:
            live.bg("Sätze für die Rückmeldung", None)
    except Exception:
        pass
