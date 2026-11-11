Hier ist die Zusammenfassung der gesamten Diskussion und des daraus resultierenden Plans: (Weiter untern die Diskussion)

### Ausgangslage & Rahmenbedingungen
*   **Unternehmen:** Chemieindustrie, 700 Mitarbeiter (500 Produktion, 250 Verwaltung, 50 Niederlassungen), 24/7-Betrieb.
*   **IT-Struktur:** 15 Personen (10 Entwickler für eigenes ERP, 5 Admins für Infrastruktur/Support). Alles On-Premise (200 VMs, 100 Switches).
*   **Hardware:** Anschaffung einer **NVIDIA DGX Station GB300** (Workstation, kein Cluster) für lokalen LLM-Betrieb.
*   **Strategische Ziele:**
    *   Tiefgreifende Integration eines KI-Assistenten in die Systemlandschaft.
    *   Aufbau eines modularen Systems für zukünftiges Wachstum.
    *   **Pilotbereich:** Vertrieb und Außendienst (wegen sichtbarem Nutzen und vorhandener Daten im ERP).
    *   **Produktion/IoT:** Wird vorerst ausgeklammert.
    *   **Budget:** Umstrukturierung muss **kostenneutral** erfolgen (kein neuer Headcount).

### Der angepasste Organisationsplan (Kostenneutral)
Um die Umstrukturierung ohne neue Stellen durchzuführen, muss die Roadmap für das ERP radikal gekürzt werden. Die 15 Personen verteilen sich wie folgt:

| Team | Besetzung | Fokus |
| :--- | :--- | :--- |
| **KI-Plattform** | 1 Admin (Vollzeit) + 1 Entwickler (50 %) | Betrieb DGX Station, Gateway, Rechte, Monitoring, Infrastruktur für KI. |
| **KI-Assistent** | 3 Entwickler | Entwicklung Assistent, RAG, Module, Umsetzung Vertriebs-Pilot. |
| **ERP-Team** | 6 Entwickler (davon 1 halbe Zeit für Plattform) | KI-fähige APIs, laufender Betrieb, eingefrorene Roadmap. |
| **Infrastruktur** | 4 Admins | IT-Betrieb, Support, Automatisierung. |

**Wichtige Hebel für die Kostenneutralität:**
1.  **ERP-Roadmap einfrieren:** Nur noch gesetzlich notwendige Änderungen und API-Arbeit für KI.
2.  **KI-Coding-Assistent:** Einführung für das ERP-Team, um Produktivität und damit Kapazität zu gewinnen.
3.  **Product Owner aus dem Fachbereich:** Eine Person aus dem Vertrieb (finanziert aus Vertriebsbudget, nicht IT), die die Anforderungen priorisiert.

### Der Vertriebs-Pilot (Roadmap)
Der Pilot läuft in vier Stufen über ca. 3–6 Monate:

1.  **Kundenbriefing (lesend):** Der Assistent bereitet auf Termine vor (Umsatz, offene Aufträge, Lieferstatus, Reklamationen).
2.  **Wissensdatenbank (lesend):** RAG über Datenblätter, Sicherheitsdatenblätter und Zulassungen. **Wichtig:** Immer mit Quellenangabe, keine eigenen Freigaben bei Sicherheitsfragen.
3.  **Besuchsberichte (schreibend):** Diktat im Auto $\rightarrow$ Transkription $\rightarrow$ LLM-Strukturierung $\rightarrow$ Bestätigung durch Mitarbeiter $\rightarrow$ ERP.
4.  **Angebotsentwürfe (schreibend):** Preisanfragen und Verfügbarkeit als Entwurf, finale Freigabe durch Mensch.

### Kritische Erfolgsfaktoren & Risiken
*   **Kapazität (GB300):** Da es eine Workstation ist, muss das Gateway Prioritäten setzen (Assistent vor Coding-Assistenz). Kein Ausfallschutz (keine Redundanz).
*   **Mobilität:** Sichere Anbindung des Außendienstes (MFA, Reverse Proxy) ist erste Aufgabe der Plattform-Admins.
*   **Betriebsrat:** Frühzeitige Einbindung ist essenziell, da es um Leistungsbeobachtung (Besuchsberichte) geht. Schriftliche Zusicherung, dass keine individuelle Auswertung stattfindet.
*   **Datenqualität:** Der Assistent darf nie mehr sehen als der Nutzer (Berechtigungen müssen im ERP liegen).

### Nächste Schritte
Um die technische Umsetzung vorzubereiten, müssen noch folgende Punkte geklärt sein:
1.  **Systemlandschaft:** Liegen Kundendaten im ERP oder in einem separaten CRM?
2.  **Hardware der Nutzer:** Womit arbeitet der Außendienst (Laptop, Tablet, Smartphone)?
3.  **Umfang:** Wie viele Personen sind im Vertrieb/Niederlassungen und in welchen Sprachen ist der Assistent gefordert?



Ich möchte mit dir in eine Diskussion gehen, um eine Firma KI-ready zu machen. Wo wir heute stehen: 700 Mitarbeiter in der Chemieindustrie, davon mit 24/7-Produktion. Davon 500 in der Produktion im Schichtbetrieb, Verwaltung 250 und diverse Niederlassungen weltweit nochmal plus 50 Mitarbeiter.

Die IT hat ein eigenes ERP-System programmiert und hat 10 Softwareentwickler, die das System weiterentwickeln und betreuen. Die Systemadministration sind 5 Admins, die die gesamte Infrastruktur betreiben und betreuen. Alles On-Premise, ca. 200 VMs auf 2 Nutanix-Hosts, ca. 100 Switches, die auch den 1. und 2. Level Support mit durchführen.

Es wird ein GB300 Server angeschafft, um llms lokal zu betreiben und zu verwenden.
Die Produktion und IoT lassen wir aktuell außen vor – das gehen wir zu einem späteren Zeitpunkt an.

Jetzt soll ein KI-Assistent tief in die Systemlandschaft integriert und mit Hilfe von KI entwickelt werden und diverse Module dazu entwickelt werden, damit das System wachsen kann. Es gibt aktuell aus der Administration 1–2 Personen, die sich mit KI-Entwicklung beschäftigen, und 3–5 aus der Softwareentwicklung. Ich möchte nun wissen, wie die Abteilung neu strukturiert und KI-ready gemacht wird. Wie würde deiner Meinung nach diese Abteilung umstrukturiert werden, um uns schnell nach vorne zu bringen?

Erste Ausgabe steht weiter untern, jetzt das Ergebnis nach erster Ausgabe mit Beantwortung der Rückfragen:


Fragen, um weiterzudiskutieren
•	Ist es eine DGX Station GB300 oder ein GB300-Rack-System? Das ändert die Kapazitätsrechnung erheblich.
•	Haben Sie Budget für 2–3 neue Stellen, oder muss die Umstrukturierung kostenneutral sein?
•	Welche Abteilung hat aus Ihrer Sicht den größten Schmerz, der sich als Pilot neben dem IT-Helpdesk eignet?

DGX Station, Umstrukturierung kostenneutral, Vertrieb und Außendienst.



Angepasster Plan: DGX Station, kostenneutral, Pilot Vertrieb und Außendienst
Diese drei Antworten verändern einiges. Kurz zur Bedeutung, dann der angepasste Plan.

Was die DGX Station bedeutet
Die DGX Station GB300 ist sehr leistungsfähig, aber sie ist ein einzelnes System mit einer GPU. Die rund 784 GB Speicher bestehen aus zwei Teilen: knapp 300 GB schnellem HBM auf der GPU und dem Rest als langsamerem CPU-Speicher. Für schnelle Inferenz zählt vor allem der HBM-Teil.
Daraus folgen drei Dinge:
•	Modellwahl: Ein mittelgroßes MoE-Modell (etwa 30–120 Mrd. Parameter, quantisiert) läuft dort schnell und mit Reserve für viele parallele Anfragen. Ein sehr großes Modell passt zwar hinein, frisst dann aber den Durchsatz.
•	Priorisierung: 250 Verwaltungsnutzer, der Außendienst und Coding-Assistenz für 10 Entwickler gleichzeitig werden eng. Ich würde die Coding-Assistenz anfangs nur begrenzt auf die Station legen und den Assistenten bevorzugen. Das Gateway braucht deshalb von Anfang an Quoten und Prioritäten.
•	Keine Redundanz: Es ist eine Workstation, kein Cluster. Fällt sie aus, ist die KI weg. Der Assistent muss daher anfangs so gebaut sein, dass ein Ausfall Arbeit verlangsamt, aber nicht stoppt. Kritische Prozesse sollten nicht allein von ihm abhängen.
Kostenneutrale Struktur (15 Personen)
Ohne neue Stellen funktioniert das nur, wenn Sie bewusst Arbeit weglassen. Sonst wird KI zum Zusatzjob, der nebenbei verhungert.
Team	Besetzung	Fokus
KI-Plattform	1 Admin (voll) + 1 Entwickler mit DevOps-Neigung (50 %)	DGX Station, Gateway, Rechte, Monitoring
KI-Assistent	3 Entwickler	Assistent, RAG, Module, Vertriebs-Pilot
ERP	6 Entwickler (einer davon halb in der Plattform)	KI-fähige APIs, laufender Betrieb, eingefrorene Roadmap
Infrastruktur	4 Admins	Betrieb, Support, Automatisierung
Damit das trägt, würde ich vier Dinge tun:
1.	ERP-Roadmap für 6 Monate radikal kürzen. Nur noch gesetzlich Notwendiges, Fehlerbehebung und die API-Arbeit für den Assistenten. Das muss die Geschäftsleitung beschließen, nicht die IT.
2.	Den Entwickler statt eines zweiten Admins in die Plattform holen. Das schützt das Infrastrukturteam und sichert trotzdem zwei Köpfe für die Station.
3.	KI-Coding-Assistenz früh einführen. Der Produktivitätsgewinn im ERP-Team ist Ihre einzige echte „neue Kapazität“.
4.	Product Owner aus dem Vertrieb stellen, nicht aus der IT. Eine erfahrene Person aus Vertrieb oder Innendienst mit 30–50 % ihrer Zeit, finanziert aus dem Vertriebsbudget. Das ist für die IT kostenneutral und sorgt für echte Verantwortung im Fachbereich.
Eine Frage, die oft hilft: „Kostenneutral“ heißt meist kein neuer Headcount. Ein einmaliges Projektbudget für externe Unterstützung beim Aufsetzen der Inferenz-Plattform (wenige Wochen) ist häufig trotzdem drin und spart Ihnen Monate Lernkurve.
Pilot Vertrieb und Außendienst
Der Bereich ist gut gewählt. Der Nutzen ist sichtbar, die Daten liegen größtenteils im ERP, und Sie können lesend starten. Ich würde in dieser Reihenfolge vorgehen:
Stufe 1 – Kundenbriefing (lesend, ca. 3 Monate)
Eine Abfrage wie „Bereite mich auf den Termin bei Kunde X vor“ liefert Umsatzentwicklung, offene Aufträge und Lieferstatus, Reklamationen, Konditionen und die letzten Besuchsberichte. Das spart dem Außendienst spürbar Vorbereitungszeit und braucht nur lesende ERP-Schnittstellen.
Stufe 2 – Produkt- und Regulatorik-Fragen (lesend)
RAG über technische Datenblätter, Sicherheitsdatenblätter und Zulassungen. Gerade in der Chemie gilt: jede Antwort mit Quelle und Dokumentversion. Bei Sicherheits- und Rechtsfragen verweist der Assistent auf das Originaldokument und formuliert keine eigene Freigabe. Das ist ein Haftungsthema.
Stufe 3 – Besuchsberichte per Sprache (schreibend mit Bestätigung)
Der Außendienst diktiert im Auto, ein lokales Spracherkennungsmodell transkribiert, das LLM strukturiert den Bericht und der Mitarbeitende bestätigt, bevor er ins ERP geht. Das wird oft der beliebteste Anwendungsfall, weil er lästige Arbeit abnimmt.
Stufe 4 – Angebotsentwürfe (schreibend mit Freigabe)
Preise, Verfügbarkeit und Konditionen als Entwurf, die Freigabe bleibt beim Menschen.
Zwei Punkte, die Sie von Anfang an klären sollten:
•	Mobiler Zugriff: Der Außendienst ist draußen, die Station steht on-premise. Sie brauchen einen sicheren Zugang von außen mit MFA, Reverse Proxy und ohne offene Ports. Das ist Arbeit für das Plattformteam in den ersten Wochen.
•	Betriebsrat: Besuchsberichte und Nutzungsdaten des Außendienstes sind genau der Bereich, in dem Leistungskontrolle befürchtet wird. Halten Sie früh schriftlich fest, dass keine Auswertung einzelner Mitarbeitender stattfindet. Das beschleunigt die Zustimmung enorm.
Erfolg messen: Vorbereitungszeit pro Kundentermin, Zeit für Berichte und Antwortzeit auf Kundenanfragen. Erheben Sie diese Werte vor dem Pilot, sonst fehlt Ihnen später der Vergleich.
Nächste Fragen
•	Liegen Kundendaten und Besuchsberichte im eigenen ERP oder in einem separaten CRM?
•	Womit arbeitet der Außendienst unterwegs, mit Laptop, Tablet oder Smartphone?
•	Wie viele Personen umfassen Vertrieb und Außendienst, inklusive der Niederlassungen, und in welchen Sprachen?





Erste Ausgabe vom ersten Promt:

KI-Readiness: Wie ich die IT umbauen würde
Bevor es um neue Teams geht, eine ehrliche Einschätzung der Ausgangslage. Mit 15 Leuten betreuen Sie 700 Mitarbeitende, ein selbst entwickeltes ERP, 200 VMs, rund 100 Switches und einen 24/7-Betrieb. Das ist schlank, eher zu schlank. Der eigentliche Engpass ist nicht die KI-Kompetenz, sondern die Kapazität der 5 Admins. Wenn Sie davon 1–2 Personen in ein KI-Team ziehen und zusätzlich einen GB300 in den Betrieb geben, wird es im Infrastrukturteam kritisch.
Ihr größter Vorteil ist das eigene ERP. Sie kennen Datenmodell, Prozesse und Schnittstellen selbst und hängen nicht an der Roadmap eines Herstellers. Ein KI-Assistent, der tief integriert ist, steht und fällt mit sauberen ERP-Schnittstellen. Das ist Ihr Hebel.
Zielstruktur (ca. 15 + 2–3 neue Stellen)
1. KI-Plattform-Team (2–3 Personen)
•	Besetzung: die 1–2 KI-interessierten Admins plus eine externe Einstellung (MLOps/Platform Engineer).
•	Aufgaben: Betrieb des GB300, Inferenz-Stack (z. B. vLLM, SGLang oder NVIDIA NIM), Modellauswahl und Updates, ein zentrales LLM-Gateway mit Authentifizierung, Logging, Quoten und Rechteprüfung, Monitoring, Sicherheit.
•	Das Team liefert „KI als interne Dienstleistung“. Kein anderes Team betreibt eigene Modelle.
2. KI-Assistent / Applications-Team (3–4 Personen)
•	Besetzung: die 3–5 KI-affinen Entwickler, idealerweise 3 davon fest.
•	Aufgaben: Kern des Assistenten, Agenten-Framework, RAG über Dokumente (Sicherheitsdatenblätter, SOPs, Verträge, REACH-Unterlagen), Modulsystem, damit neue Fähigkeiten als Plugins andocken können.
•	Wichtig: Hier sitzt auch der Bauplan für „das System soll wachsen“. Ein standardisiertes Tool-Protokoll wie MCP sorgt dafür, dass jedes neue Modul nach demselben Muster angebunden wird.
3. ERP-Team (6–7 Personen)
•	Bleibt der Kern, bekommt aber einen neuen Auftrag: das ERP „KI-fähig“ machen. Das heißt saubere, dokumentierte APIs, fachliche Berechtigungen auf API-Ebene und ein ERP-MCP-Server, den der Assistent nutzt.
•	Dieses Team nutzt KI-Coding-Assistenten, lokal über den GB300 oder über einen geprüften Dienst. Das ist der schnellste Produktivitätsgewinn, den Sie haben, und er schafft die Kapazität für alles andere.
4. Infrastruktur & Betrieb (3–4 Personen)
•	Muss entlastet werden, sonst bricht das Fundament weg. Zwei Optionen, die sich kombinieren lassen: 
o	1st-Level-Support teilweise auslagern oder eine Stelle nachbesetzen.
o	Erster interner Anwendungsfall für den Assistenten: IT-Helpdesk mit Ticket-Triage, Wissensdatenbank und Standardantworten (Passwort, VPN, Drucker). So profitiert das Team direkt vom Projekt, statt es nur zu tragen.
5. Querschnitt: Governance & Fachbereich
•	KI-Product-Owner: eine Person, die zwischen Fachbereichen und IT priorisiert, idealerweise jemand mit Prozesswissen aus der Verwaltung. Ohne diese Rolle bauen die Entwickler, was technisch spannend ist, nicht was den größten Nutzen bringt.
•	KI-Champions in Einkauf, Vertrieb, QS, Buchhaltung und HR: je eine Person als Ansprechpartner, Tester und Multiplikator.
•	Betriebsrat früh einbinden. Ein Assistent mit Logging ist praktisch immer mitbestimmungspflichtig (§ 87 Abs. 1 Nr. 6 BetrVG). Eine Rahmen-Betriebsvereinbarung „KI“ spart Ihnen später viele Einzelverhandlungen.
•	Dazu kommen Datenschutz, ISMS und die Pflicht zur KI-Kompetenz der Mitarbeitenden nach Art. 4 EU AI Act, die bereits gilt.
Phasen
•	0–3 Monate: Teams bilden, GB300 produktiv machen, Gateway und Rechtekonzept aufbauen, Betriebsvereinbarung starten. Coding-Assistenz für das ERP-Team einführen. Erster Pilot: IT-Helpdesk und Dokumentensuche, nur lesend.
•	3–9 Monate: ERP-Schnittstellen für den Assistenten. Lesende ERP-Abfragen wie „Wie ist der Lieferstatus von Auftrag X?“ oder „Welche Chargen sind offen?“. Rollout an die Verwaltung mit Schulung.
•	9–18 Monate: schreibende Aktionen mit Freigabe durch einen Menschen (Bestellvorschläge, Belegerfassung), Niederlassungen mehrsprachig anbinden, Vorbereitung auf Produktion/IoT.
Drei Risiken, die ich ansprechen würde
1.	Bus-Faktor: Ein KI-Plattform-Team mit einer einzigen Person, die den GB300 versteht, ist ein Ausfallrisiko. Deshalb mindestens zwei Personen plus Dokumentation.
2.	Datenqualität und Berechtigungen: Der Assistent darf nie mehr sehen als der Mensch, der ihn fragt. Das muss im ERP und nicht im Prompt gelöst werden.
3.	Erwartung an den GB300: Ein einzelnes System trägt ein bis zwei große Open-Weight-Modelle für einige hundert Nutzer mit moderater Last gut. Agentische Workflows mit vielen parallelen Aufrufen und gleichzeitig Coding-Assistenz für 10 Entwickler können es aber auslasten. Kapazitätsplanung gehört von Anfang an dazu.
Fragen, um weiterzudiskutieren
•	Ist es eine DGX Station GB300 oder ein GB300-Rack-System? Das ändert die Kapazitätsrechnung erheblich.
•	Haben Sie Budget für 2–3 neue Stellen, oder muss die Umstrukturierung kostenneutral sein?
•	Welche Abteilung hat aus Ihrer Sicht den größten Schmerz, der sich als Pilot neben dem IT-Helpdesk eignet?
