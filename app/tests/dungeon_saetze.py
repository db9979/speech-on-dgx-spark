"""KI-Dungeon-Master: the Satz-Prüfstand's sentences (Dominik 2026-10-28 „es kommen zu viele fehler“, Vorschlag 1).

Fixed player actions with what they do. The one sorting of a typed action (dungeon_einordnung.kind, Vorschlag 7) gives
every one of them exactly its kind here (test_dungeon_saetze), and the helpers of the callers (fight, asks, typed,
everyday) follow from it; a sentence sorted wrong at the table comes in here with the fix. Data only, read by the tests.

The kinds (dungeon_einordnung.ARTEN, in their fixed order):
  angriff  attacks on its own
  bezug    attacks the foe it names
  flucht   runs away
  frieden  asks for peace
  alltag   everyday acts only (no check)
  frage    only asks or talks
  verkauf, kauf, rast   typed as that (the panel's own buttons)
  gehen    plain going
  sonst    none of these (kind "")
"""

SAETZE = {
    "angriff": [
        "hau die Wache", "Ich haue der Wache eins über", "Ich kämpfe gegen die Wache", "Ich bekämpfe die Wache",
        "Ich ersteche ihn", "Ich erdolche ihn", "Ich ramme ihn", "Ich trete zu", "Ich prügle auf ihn ein",
        "Ich toete ihn",
        "Ich spieße ihn auf", "Ich schlitze ihn auf", "Ich greife an", "Angriff!", "Ich schlage zu", "Ich steche zu",
        "Ich greife die Wache an", "Ich greife Meervolk-Späher 2 an", "Ich töte den Ork", "Ich trete die Wache",
        "Ich schlage die Wache", "Ich schlage auf den Ork ein", "Ich schieße einen Pfeil auf den Ork",
        "I fight", "I punch him", "I kick", "I swing at it", "I attack", "I stab the guard",
        # Nachprüfung V01.1.130
        "Ich schlage dich nieder", "Ich schlage euch nieder, Banditen", "Ich trete ein paar Mal nach der Wache",
        # Review 27.10. T19: the children's table's „besiegen“ (dungeon_rueckfrage.milder)
        "Ich besiege den Goblin.", "Wir besiegen die Ratten.",
        # Kampf-Audit M6: the attack words win over running away
        "Ich schlage den verfluchten Ork", "Ich greife an und fliehe dann",
        # Satz-Prüfstand 2026-10-28
        "Ich schlage mit meinem Stab nach dem Goblin", "Ich steche mit dem Dolch nach der Ratte", "Ich kämpfe weiter",
        "Ich schieße auf die Wache", "Ich ramme dem Ork die Schulter in die Seite", "I strike the goblin",
        "I hit the rat",
        "I shoot the bandit", "I slash at the wolf", "I bash the skeleton with my shield", "I kick the door guard",
        # Satz-Prüfstand 2026-10-28
        "Ich greife mit meinem Stab an", "Ich schlage mit dem Stab zu", "Ich attackiere den Kobold",
        "Ich haue mit der Axt auf den Troll ein", "Ich steche dem Banditen in die Seite", "Ich erschlage die Ratte",
        "Ich kämpfe mit dem Ork", "Ich töte das Skelett", "Ich schieße mit der Armbrust auf den Wolf",
        "Ich schlage dem Goblin auf den Kopf", "Ich trete dem Zombie gegen das Knie", "Ich stoße mit dem Speer zu",
        "I attack the orc with my sword", "I hit the goblin with my staff", "I kill the rat", "I fight the bandits",
        "I punch the thug", "I shoot an arrow at the wolf", "I strike at the skeleton", "I smite the undead",
        "Ich verpasse dem Ork eins", "Ich prügel auf den Banditen ein",
        "Ich ramme dem Troll mein Schwert in den Bauch", "Ich schieße einen Bolzen auf die Spinne",
        "Ich hau dem Kobold eine rein",
    ],
    "bezug": [
        "Ich ziele auf die Wache", "Ich werfe meinen Dolch auf die Wache", "boxe die Wache", "feuere auf die Wache",
        "stürme auf die Wache los", "gehe auf die Wache los", "schneide der Wache die Kehle durch",
        "I charge the guard", "I throw my dagger at the guard", "I aim at the guard", "Gebt Feuer auf die Wache",
        "Gebt Feuer!",
        # Satz-Prüfstand 2026-10-28
        "Ich werfe einen Stein auf den Goblin", "Ich ziele mit dem Bogen auf den Ork", "I throw a rock at the goblin",
        "I aim my bow at the orc", "Ich stürze mich auf den Banditen", "Ich schleudere meinen Speer auf den Wolf",
    ],
    "frieden": [
        "Ergebt euch!", "Ich verhandle mit den Orks", "Lasst uns reden", "Ich biete Frieden an", "We surrender",
        "I parley",
        # Satz-Prüfstand 2026-10-28
        "Wir ergeben uns", "Ich biete den Banditen Frieden an", "Lasst uns verhandeln", "We offer a truce",
    ],
    "flucht": [
        "Ich trete den Rückzug an", "I retreat", "Ich haue ab", "Wir fliehen durch die Tür!", "Ich flüchte in den Gang",
        "Ich renne so schnell ich kann weg", "Wir ziehen uns zurück", "I run away", "We flee", "I try to escape",
        # Satz-Prüfstand 2026-10-28
        "Wir fliehen!", "Ich renne weg", "Ich laufe davon", "We run away from the troll", "Ich flüchte zum Ausgang",
    ],
    "gehen": [
        "Ich gehe zur Tür", "betrete die biblithek", "Ich betrete die Halle", "Ich trete in die Halle ein",
        "Wir gehen nach Osten",
        "Ich laufe zum Brunnen", "Wir wandern weiter Richtung Hafen", "Ich gehe in die Taverne", "I walk to the gate",
        "I enter the hall", "We travel north", "I go to the inn", "Ich trete ein", "Ich trete ein und schaue mich um",
        # Satz-Prüfstand 2026-10-28
        "Ich gehe nach Norden", "Wir gehen zurück ins Dorf", "Ich laufe die Straße entlang",
        "Wir reisen weiter nach Süden", "Ich gehe zum Markt", "I head to the harbour", "We walk back to the village",
        "I move to the door", "Ich betrete den Tempel", "Wir betreten die Höhle", "Ich trete in den Laden ein",
        "I go north", "We head east",
    ],
    "frage": [
        "Ich frage Silas danach.", "Ich frage den Wirt nach dem Weg", "Ich rede mit der Wache", "Ich spreche Grimma an",
        "Ich frage, was er gerade macht.", "I ask the innkeeper about the tower", "I talk to the guard",
        # Satz-Prüfstand 2026-10-28
        "Ich frage die Wache, wer hier wohnt", "Ich frage nach dem Turm", "Ich spreche mit dem Händler",
        "Ich rede mit Silas über den Fluch", "Ich frage Grimma, was in der Truhe ist",
        "I ask the guard who lives here", "I talk to Silas about the curse", "I ask about the tower",
        "Ich sage dem Wirt, dass wir bleiben",
        # Einordnung 2026-10-29: „gehe ich los“ was an attack on a foe named
        "Ich frage den Wirt nach dem Weg. Dann gehe ich los.", "Ich schlage vor, wir reden",
    ],
    "kauf": [
        "Ich kaufe einen Heiltrank", "Ich kaufe Proviant beim Händler", "I buy a rope",
        # Satz-Prüfstand 2026-10-28
        "Ich kaufe ein Seil", "Ich kaufe zwei Fackeln", "I buy two torches", "Ich bezahle den Händler für den Trank",
        "I purchase a shield",
    ],
    "verkauf": [
        "Ich verkaufe mein altes Schwert", "I sell the gem",
        # Satz-Prüfstand 2026-10-28
        "Ich verkaufe den Ring", "Ich verkaufe die Felle beim Händler", "I sell my old armour",
    ],
    "rast": [
        "Wir rasten hier", "Ich schlafe eine Runde", "Wir schlagen das Lager auf", "We make camp",
        "I rest for the night",
        # Satz-Prüfstand 2026-10-28
        "Ich ruhe mich aus", "Wir übernachten im Gasthaus", "Wir machen Rast", "I sleep", "We rest here",
        "Ich lege eine kurze Rast ein",
        # Einordnung 2026-10-29: „schlagen hier“ was an attack, „by the fire“ an attack on a foe named
        "Wir schlagen hier unser Lager auf und rasten.", "We rest by the fire.",
    ],
    "alltag": [
        "Ich wünsche den anderen einen guten Morgen und packe mein Brot aus.", "Ich grüße den Wirt.",
        "Ich lächle und nicke.",
        "Ich esse und trinke.", "I greet the others and unpack my bread.",
        # Satz-Prüfstand 2026-10-28
        "Ich trinke ein Bier", "Ich esse mein Brot", "Ich bedanke mich beim Wirt", "Ich winke den anderen zu",
        "Ich gähne und strecke mich", "I thank the innkeeper", "I eat my bread", "I drink my ale",
        "I wave at the others", "Ich lache", "Hallo zusammen!", "Ich packe meine Sachen aus",
        # Einordnung 2026-10-29: everyday acts come before talking („sage“), so no check
        "Ich sage Hallo", "Ich sage dem Wirt guten Morgen",
    ],
    "sonst": [
        # Kampf-Audit, Nachprüfung Welle 1 and V01.1.130: stepping, proposing, a look, a light, a door
        "Ich greife nach dem Seil neben der Wache", "Ich stoße die Tür auf und rufe die Wache",
        "Ich mache ein Lagerfeuer",
        "Ich halte mich bereit", "Ich verstecke mich", "Ich helfe Bela auf", "I reach for the rope",
        "Ich trete zur Seite, weg von der Wache", "Ich schlage mich in die Büsche",
        "Ich werfe der Wache einen Blick zu", "Ich gebe der Wache Feuer für ihre Pfeife", "I step back",
        "I throw the guard a glance", "Ich schlage Alarm", "Ich trete die Tür ein", "Ich werfe der Wache Gold zu",
        "I strike a deal with the guard", "Ich verfluche die Wache", "Ich bete um Zuflucht",
        "Ich breche das Siegel der Truhe", "Ich lese die Siegesinschrift", "Ich trinke einen Trank",
        "Ich trete zurück und trinke einen Heiltrank", "I hit the road",
        # Satz-Prüfstand 2026-10-28 (Dominik: „es kommen zu viele fehler“): a staff, a book, a headline, an idiom
        "Ich hebe meinen Stab und sehe mich um.", "Ich stütze mich auf meinen Stab.",
        "Ich lese das Stichwort auf dem Zettel.",
        "Ich schaue mir die Schlagzeile an.", "Ich schlage das Buch auf.", "Ich schlage den Folianten auf",
        "Ich ramme den Pfahl in den Boden.", "Ich besiege meine Angst.", "Ich kämpfe mich durch das Gestrüpp.",
        "Ich steche in See.", "Ich töte die Zeit mit Lesen.", "I look at the battle map.", "I kick off my boots.",
        "I swing the door open.", "I strike a match.", "Ich untersuche die Schriftrolle",
        "Ich klettere die Wand hinauf",
        "Ich durchsuche die Truhe", "Ich öffne die Tür", "Ich lausche an der Tür", "Ich zünde eine Fackel an",
        "I search the chest", "I climb the wall", "I open the door",
        # Satz-Prüfstand 2026-10-28
        "Ich untersuche die Wand nach Geheimtüren", "Ich lese die Inschrift", "Ich durchsuche den Schreibtisch",
        "Ich schaue aus dem Fenster", "Ich zünde die Laterne an", "Ich nehme das Buch aus dem Regal",
        "Ich verstecke mich hinter dem Fass", "Ich schleiche an der Wache vorbei", "Ich klettere auf den Baum",
        "Ich springe über den Graben", "Ich schwimme ans andere Ufer", "Ich heile Bela", "Ich bete zu meinem Gott",
        "Ich halte Wache", "Ich warte ab", "Ich beobachte die Straße", "Ich lausche nach Geräuschen",
        "Ich prüfe die Falle", "Ich knacke das Schloss", "Ich entschärfe die Falle", "Ich lese die Schriftrolle",
        "Ich nehme den Schlüssel", "Ich hebe die Münze auf", "Ich gebe Bela meinen Trank", "I examine the wall",
        "I read the inscription", "I pick the lock", "I hide behind the barrel", "I sneak past the guard",
        "I climb the tree", "I heal Bela", "I wait", "I watch the street", "I listen at the door",
        "I light the lantern", "I take the key", "I search the desk", "Ich schlage die Karte auf",
        "Ich hebe meinen Stab in die Höhe", "Ich lehne mich an meinen Stab", "Ich schlage unser Zelt auf",
        "Ich stoße das Fenster auf", "Ich werfe einen Blick auf die Karte", "Ich greife nach der Fackel",
        "Ich mache einen Vorschlag", "Ich trete näher an das Feuer", "Ich ziehe mein Schwert", "I draw my sword",
        "I raise my battle axe",
    ],
}
