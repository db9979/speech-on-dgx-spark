"""Linux an der Konsole des Krisenspiels (plan krisenspiel/plan.md, Paket 2, Dominik 2026-10-22: „Befehle erweitern,
damit wir auch cmd in der Linux-Welt erlernen“, „-h als Hilfe“, „nicht nur zum Lernen, durchsimuliert“): about 120
commands of the list at linux-commands.labex.io, simulated on the machines of the scenario. Nothing runs: every
command is a function here that reads and changes the game's own world in st["konsole"]["sim"]:
- a file system per machine: fixed files (/etc, /var/log, the files of the scenario) plus what the player made
  (mkdir, touch, cp, mv, rm, ln, tar, gzip, zip, scp, > and >>, tee), bounded by SIM_MAX entries, LINE_MAX and SIM_BYTES;
- users and groups (useradd, usermod -aG, passwd …), mounts, firewall rules (iptables), modes (chmod);
- services and processes: systemctl stop, kill or reboot on a machine of the game have effects on the game by fixed
  rules (stopping a service of a system degrades it, starting it again gives it back) and come back as a move;
- root is needed where Linux needs it: without sudo the answer is "Permission denied", like on a real machine.
Patterns (grep, sed, find) are plain text with ^ and $ at most, never a regular expression of the player, so no input
can make the panel work long. Every command answers -h and --help (help_lines) in German or English."""
import hashlib
import json
import posixpath

HOME = "/home/admin"
SIM_MAX = 200            # files and folders a player may make per machine
SIM_BYTES = 100_000      # what the player made on all machines of a game together (the game file stays small)
LINE_MAX = 200           # lines of a file the player writes
MAX_PATH = 120
# the groups of „help“: key -> (de, en)
GRUPPEN = {"datei": ("Dateien und Verzeichnisse", "Files and folders"), "text": ("Text", "Text"),
           "system": ("System", "System"), "benutzer": ("Benutzer und Rechte", "Users and permissions"),
           "netz": ("Netzwerk", "Network"), "platte": ("Platten und Dateisysteme", "Disks and file systems"),
           "archiv": ("Archive", "Archives"), "prozess": ("Prozesse und Dienste", "Processes and services")}
U = ("linux", "san", "net", "ups", "gen", "pbx")
A = None   # every machine
# name -> (where, group, kind, de, en, usage, options de, options en). kind: frei (no game time) or lesen (a minute)
LINUX = {
    "ls": (U, "datei", "frei", "Inhalt eines Verzeichnisses", "List a folder", "ls [-l] [-a] [pfad]", "-l lang mit Rechten und Größe, -a auch versteckte, -R mit Unterordnern", "-l long with modes and size, -a hidden too, -R with subfolders"),
    "cd": (U, "datei", "frei", "Verzeichnis wechseln", "Change folder", "cd [pfad]", "ohne Pfad nach ~, cd .. eine Ebene hoch, cd - zurück", "no path: ~, cd .. one up, cd - back"),
    "pwd": (U, "datei", "frei", "Aktuelles Verzeichnis", "Current folder", "pwd", "", ""),
    "mkdir": (U, "datei", "frei", "Verzeichnis anlegen", "Make a folder", "mkdir [-p] <pfad>", "-p auch fehlende Eltern", "-p missing parents too"),
    "touch": (U, "datei", "frei", "Leere Datei anlegen", "Make an empty file", "touch <datei>", "", ""),
    "cp": (U, "datei", "frei", "Kopieren", "Copy", "cp [-r] <quelle> <ziel>", "-r Verzeichnisse mit Inhalt", "-r folders with content"),
    "mv": (U, "datei", "frei", "Verschieben oder umbenennen", "Move or rename", "mv <quelle> <ziel>", "", ""),
    "rm": (U, "datei", "frei", "Löschen", "Remove", "rm [-r] [-f] <pfad>", "-r Verzeichnisse mit Inhalt, -f ohne Fehler", "-r folders with content, -f no errors"),
    "rmdir": (U, "datei", "frei", "Leeres Verzeichnis löschen", "Remove an empty folder", "rmdir <pfad>", "", ""),
    "ln": (U, "datei", "frei", "Verknüpfung anlegen", "Make a link", "ln -s <ziel> <name>", "-s symbolisch", "-s symbolic"),
    "cat": (U, "datei", "frei", "Datei zeigen", "Show a file", "cat <datei>", "-n mit Zeilennummern", "-n with line numbers"),
    "less": (U, "datei", "frei", "Datei seitenweise zeigen", "Show a file page by page", "less <datei>", "", ""),
    "more": (U, "datei", "frei", "Datei seitenweise zeigen", "Show a file page by page", "more <datei>", "", ""),
    "tree": (U, "datei", "frei", "Verzeichnisbaum", "Folder tree", "tree [pfad]", "", ""),
    "du": (U, "datei", "frei", "Platz eines Verzeichnisses", "Space of a folder", "du [-sh] [pfad]", "-s nur Summe, -h lesbar", "-s sum only, -h readable"),
    "stat": (U, "datei", "frei", "Angaben zu einer Datei", "Details of a file", "stat <pfad>", "", ""),
    "find": (U, "datei", "frei", "Dateien suchen", "Find files", "find [pfad] [-name muster] [-type f|d]", "-name mit * und ?, -type f Dateien, d Verzeichnisse", "-name with * and ?, -type f files, d folders"),
    "which": (U, "datei", "frei", "Wo liegt ein Befehl", "Where a command is", "which <befehl>", "", ""),
    "whereis": (U, "datei", "frei", "Befehl und Handbuch finden", "Find a command and its manual", "whereis <befehl>", "", ""),
    "file": (U, "datei", "frei", "Art einer Datei", "Kind of a file", "file <pfad>", "", ""),
    "basename": (U, "datei", "frei", "Dateiname ohne Pfad", "File name without path", "basename <pfad>", "", ""),
    "dirname": (U, "datei", "frei", "Pfad ohne Dateiname", "Path without file name", "dirname <pfad>", "", ""),
    "readlink": (U, "datei", "frei", "Ziel einer Verknüpfung", "Target of a link", "readlink -f <pfad>", "-f ganzer Pfad", "-f full path"),
    "realpath": (U, "datei", "frei", "Ganzer Pfad", "Full path", "realpath <pfad>", "", ""),
    "md5sum": (U, "datei", "frei", "Prüfsumme", "Checksum", "md5sum <datei>", "", ""),
    "sha256sum": (U, "datei", "frei", "Prüfsumme SHA-256", "SHA-256 checksum", "sha256sum <datei>", "", ""),
    "cksum": (U, "datei", "frei", "Prüfsumme", "Checksum", "cksum <datei>", "", ""),
    "cmp": (U, "datei", "frei", "Zwei Dateien vergleichen", "Compare two files", "cmp <a> <b>", "", ""),
    "echo": (A, "text", "frei", "Text ausgeben", "Print text", "echo <text> [> datei]", "> schreibt in eine Datei, >> hängt an", "> writes a file, >> appends"),
    "grep": (U, "text", "frei", "Zeilen mit einem Muster", "Lines with a pattern", "grep [-i] [-v] [-n] [-c] [-r] <muster> <datei>", "-i Groß/klein egal, -v ohne Muster, -n Nummern, -c zählen, -r in Verzeichnissen; ^ Anfang, $ Ende", "-i ignore case, -v without, -n numbers, -c count, -r in folders; ^ start, $ end"),
    "egrep": (U, "text", "frei", "Wie grep", "Like grep", "egrep <muster> <datei>", "", ""),
    "fgrep": (U, "text", "frei", "Wie grep", "Like grep", "fgrep <muster> <datei>", "", ""),
    "zgrep": (U, "text", "frei", "grep in .gz-Dateien", "grep in .gz files", "zgrep <muster> <datei.gz>", "", ""),
    "sed": (U, "text", "frei", "Text ersetzen", "Replace text", "sed 's/alt/neu/g' <datei>", "s/a/b/ ersetzt, g alle, -n 'Np' Zeile N, 'Nd' ohne Zeile N", "s/a/b/ replaces, g all, -n 'Np' line N, 'Nd' without line N"),
    "awk": (U, "text", "frei", "Spalten ausgeben", "Print columns", "awk [-F x] '{print $N}' <datei>", "-F Trennzeichen, $N Spalte N, $0 ganze Zeile, NF Spaltenzahl", "-F separator, $N column N, $0 whole line, NF number of columns"),
    "cut": (U, "text", "frei", "Spalten ausschneiden", "Cut columns", "cut -d <zeichen> -f <n> <datei>", "-d Trennzeichen, -f Feldnummer", "-d separator, -f field number"),
    "sort": (U, "text", "frei", "Zeilen sortieren", "Sort lines", "sort [-r] [-n] [-u] <datei>", "-r rückwärts, -n nach Zahl, -u ohne Doppelte", "-r reverse, -n numeric, -u unique"),
    "uniq": (U, "text", "frei", "Doppelte Zeilen zusammenfassen", "Fold repeated lines", "uniq [-c] <datei>", "-c mit Anzahl", "-c with count"),
    "tr": (U, "text", "frei", "Zeichen tauschen", "Translate characters", "tr <von> <nach> | tr -d <zeichen>", "-d löschen", "-d delete"),
    "head": (U, "text", "frei", "Anfang einer Datei", "Start of a file", "head [-n N] <datei>", "-n Anzahl Zeilen", "-n number of lines"),
    "tail": (U, "text", "frei", "Ende einer Datei", "End of a file", "tail [-n N] <datei>", "-n Anzahl Zeilen, -f folgen (hier einmal)", "-n number of lines, -f follow (once here)"),
    "wc": (U, "text", "frei", "Zeilen, Wörter, Zeichen zählen", "Count lines, words, characters", "wc [-l] [-w] [-c] <datei>", "-l Zeilen, -w Wörter, -c Zeichen", "-l lines, -w words, -c characters"),
    "diff": (U, "text", "frei", "Unterschiede zweier Dateien", "Differences of two files", "diff <a> <b>", "", ""),
    "tac": (U, "text", "frei", "Datei rückwärts", "File backwards", "tac <datei>", "", ""),
    "nl": (U, "text", "frei", "Zeilen nummerieren", "Number lines", "nl <datei>", "", ""),
    "tee": (U, "text", "frei", "Ausgabe auch in eine Datei", "Output to a file too", "tee [-a] <datei>", "-a anhängen; steht hinter einem |: ls | tee liste.txt", "-a append; goes after a |: ls | tee list.txt"),
    "column": (U, "text", "frei", "In Spalten setzen", "Set in columns", "column -t <datei>", "", ""),
    "vi": (U, "text", "frei", "Editor", "Editor", "vi <datei>", "", ""),
    "nano": (U, "text", "frei", "Editor", "Editor", "nano <datei>", "", ""),
    "top": (U, "system", "lesen", "Last und Prozesse", "Load and processes", "top", "", ""),
    "htop": (U, "system", "lesen", "Last und Prozesse", "Load and processes", "htop", "", ""),
    "free": (U, "system", "lesen", "Arbeitsspeicher", "Memory", "free [-h]", "-h lesbar", "-h readable"),
    "uname": (U, "system", "frei", "System und Kernel", "System and kernel", "uname [-a] [-r]", "-a alles, -r Kernel", "-a all, -r kernel"),
    "uptime": (U, "system", "lesen", "Laufzeit und Last", "Uptime and load", "uptime", "", ""),
    "vmstat": (U, "system", "lesen", "Speicher und CPU", "Memory and CPU", "vmstat", "", ""),
    "iostat": (U, "system", "lesen", "Platten-Ein/Ausgabe", "Disk input/output", "iostat", "", ""),
    "dmesg": (U, "system", "lesen", "Meldungen des Kernels", "Kernel messages", "dmesg", "", ""),
    "journalctl": (U, "system", "lesen", "Systemprotokoll", "System journal", "journalctl [-u dienst] [-n N]", "-u ein Dienst, -n Anzahl", "-u one service, -n number"),
    "lsof": (U, "system", "lesen", "Offene Dateien und Ports", "Open files and ports", "lsof -i", "-i Netzwerk", "-i network"),
    "date": (A, "system", "frei", "Spielzeit", "Game time", "date", "", ""),
    "cal": (U, "system", "frei", "Kalender", "Calendar", "cal", "", ""),
    "arch": (U, "system", "frei", "Prozessor-Architektur", "Processor architecture", "arch", "", ""),
    "hostname": (A, "system", "frei", "Name dieses Rechners", "Name of this machine", "hostname", "", ""),
    "hostnamectl": (U, "system", "frei", "Name und System", "Name and system", "hostnamectl", "", ""),
    "watch": (U, "system", "frei", "Befehl wiederholen", "Repeat a command", "watch <befehl>", "", ""),
    "env": (U, "system", "frei", "Umgebungsvariablen", "Environment variables", "env", "", ""),
    "printenv": (U, "system", "frei", "Umgebungsvariablen", "Environment variables", "printenv [name]", "", ""),
    "reboot": (U, "system", "frei", "Neu starten (root)", "Restart (root)", "sudo reboot", "", ""),
    "halt": (U, "system", "frei", "Anhalten (root)", "Halt (root)", "sudo halt", "", ""),
    "poweroff": (U, "system", "frei", "Ausschalten (root)", "Power off (root)", "sudo poweroff", "", ""),
    "whoami": (A, "benutzer", "frei", "Eigenes Konto", "Own account", "whoami", "", ""),
    "id": (U, "benutzer", "frei", "Konto und Gruppen", "Account and groups", "id [konto]", "", ""),
    "groups": (U, "benutzer", "frei", "Gruppen eines Kontos", "Groups of an account", "groups [konto]", "", ""),
    "who": (U, "benutzer", "frei", "Wer ist angemeldet", "Who is signed in", "who", "", ""),
    "w": (U, "benutzer", "frei", "Wer ist angemeldet und tut was", "Who is signed in and doing what", "w", "", ""),
    "users": (U, "benutzer", "frei", "Angemeldete Konten", "Signed-in accounts", "users", "", ""),
    "last": (U, "benutzer", "lesen", "Letzte Anmeldungen", "Last sign-ins", "last", "", ""),
    "sudo": (U, "benutzer", "frei", "Als root ausführen", "Run as root", "sudo <befehl>", "", ""),
    "su": (U, "benutzer", "frei", "Konto wechseln", "Switch account", "su [konto]", "", ""),
    "useradd": (U, "benutzer", "frei", "Konto anlegen (root)", "Add an account (root)", "sudo useradd [-m] [-G gruppe] <konto>", "-m mit Home, -G Gruppen", "-m with home, -G groups"),
    "userdel": (U, "benutzer", "frei", "Konto löschen (root)", "Delete an account (root)", "sudo userdel [-r] <konto>", "-r mit Home", "-r with home"),
    "usermod": (U, "benutzer", "frei", "Konto ändern (root)", "Change an account (root)", "sudo usermod -aG <gruppe> <konto> | -L <konto>", "-aG Gruppe dazu, -L sperren, -U entsperren", "-aG add group, -L lock, -U unlock"),
    "groupadd": (U, "benutzer", "frei", "Gruppe anlegen (root)", "Add a group (root)", "sudo groupadd <gruppe>", "", ""),
    "groupdel": (U, "benutzer", "frei", "Gruppe löschen (root)", "Delete a group (root)", "sudo groupdel <gruppe>", "", ""),
    "passwd": (U, "benutzer", "frei", "Passwort ändern", "Change a password", "passwd | sudo passwd <konto>", "-l sperren", "-l lock"),
    "chage": (U, "benutzer", "frei", "Passwort-Ablauf (root)", "Password ageing (root)", "sudo chage -l <konto>", "", ""),
    "chmod": (U, "benutzer", "frei", "Rechte ändern", "Change modes", "chmod <755|u+x> <pfad>", "", ""),
    "chown": (U, "benutzer", "frei", "Besitzer ändern (root)", "Change owner (root)", "sudo chown <konto>[:gruppe] <pfad>", "", ""),
    "chgrp": (U, "benutzer", "frei", "Gruppe ändern", "Change group", "chgrp <gruppe> <pfad>", "", ""),
    "umask": (U, "benutzer", "frei", "Standard-Rechte", "Default modes", "umask", "", ""),
    "ping": (A, "netz", "lesen", "Erreichbarkeit prüfen", "Check reachability", "ping <rechner|ip>", "", ""),
    "traceroute": (U, "netz", "lesen", "Weg zu einem Rechner", "Route to a machine", "traceroute <rechner|ip>", "", ""),
    "tracepath": (U, "netz", "lesen", "Weg zu einem Rechner", "Route to a machine", "tracepath <rechner|ip>", "", ""),
    "nslookup": (A, "netz", "lesen", "Namen auflösen", "Resolve a name", "nslookup <rechner>", "", ""),
    "dig": (U, "netz", "lesen", "Namen auflösen", "Resolve a name", "dig <rechner>", "+short nur die Adresse", "+short address only"),
    "host": (U, "netz", "lesen", "Namen auflösen", "Resolve a name", "host <rechner>", "", ""),
    "ip": (U, "netz", "lesen", "Adressen und Routen", "Addresses and routes", "ip a | ip route | ip link", "", ""),
    "ifconfig": (U, "netz", "lesen", "Netzwerkkarten", "Network interfaces", "ifconfig", "", ""),
    "route": (U, "netz", "lesen", "Routen", "Routes", "route -n", "", ""),
    "arp": (U, "netz", "lesen", "Nachbarn im Netz", "Neighbours on the network", "arp -a", "", ""),
    "ss": (U, "netz", "lesen", "Offene Ports", "Open ports", "ss -tlpn", "-t TCP, -l lauschend, -p Prozess, -n Zahlen", "-t TCP, -l listening, -p process, -n numeric"),
    "netstat": (A, "netz", "lesen", "Offene Ports", "Open ports", "netstat -tlpn", "", ""),
    "nmap": (U, "netz", "lesen", "Ports eines Rechners prüfen", "Scan the ports of a machine", "nmap <rechner>", "", ""),
    "curl": (U, "netz", "lesen", "Webseite abrufen", "Fetch a web page", "curl [-I] <rechner>[/pfad]", "-I nur Kopfzeilen, -o in eine Datei", "-I headers only, -o into a file"),
    "wget": (U, "netz", "lesen", "Datei herunterladen", "Download a file", "wget <rechner>[/pfad]", "", ""),
    "nc": (U, "netz", "lesen", "Port prüfen", "Check a port", "nc -zv <rechner> <port>", "", ""),
    "telnet": (U, "netz", "lesen", "Mit einem Port verbinden", "Connect to a port", "telnet <rechner> <port>", "", ""),
    "tcpdump": (U, "netz", "lesen", "Netzverkehr mitschneiden (root)", "Capture traffic (root)", "sudo tcpdump [-c N]", "", ""),
    "ethtool": (U, "netz", "lesen", "Netzwerkkarte", "Network interface", "ethtool eth0", "", ""),
    "scp": (U, "netz", "frei", "Datei auf einen anderen Rechner kopieren", "Copy a file to another machine", "scp <datei> <rechner>:<pfad>", "", ""),
    "iptables": (U, "netz", "frei", "Firewall-Regeln (root)", "Firewall rules (root)", "sudo iptables -L | -A INPUT -s <ip> -j DROP | -D … | -F", "-L zeigen, -A anhängen, -I vorne, -D löschen, -F alle löschen", "-L list, -A append, -I insert, -D delete, -F flush"),
    "mount": (U, "platte", "frei", "Dateisysteme einhängen", "Mount file systems", "mount | sudo mount <gerät> <ordner>", "", ""),
    "umount": (U, "platte", "frei", "Aushängen (root)", "Unmount (root)", "sudo umount <ordner>", "", ""),
    "df": (U, "platte", "lesen", "Plattenplatz", "Disk space", "df [-h]", "-h lesbar", "-h readable"),
    "lsblk": (U, "platte", "frei", "Platten und Partitionen", "Disks and partitions", "lsblk", "", ""),
    "blkid": (U, "platte", "frei", "Kennungen der Partitionen", "Partition IDs", "blkid", "", ""),
    "fdisk": (U, "platte", "frei", "Partitionen (root)", "Partitions (root)", "sudo fdisk -l", "", ""),
    "mkfs": (U, "platte", "frei", "Dateisystem anlegen (root)", "Make a file system (root)", "sudo mkfs.ext4 <gerät>", "", ""),
    "fsck": (U, "platte", "frei", "Dateisystem prüfen (root)", "Check a file system (root)", "sudo fsck <gerät>", "", ""),
    "dd": (U, "platte", "frei", "Blöcke kopieren (root)", "Copy blocks (root)", "sudo dd if=<a> of=<b>", "", ""),
    "mdadm": (U, "platte", "frei", "Software-RAID (root)", "Software RAID (root)", "sudo mdadm --detail /dev/md0", "", ""),
    "sync": (U, "platte", "frei", "Puffer schreiben", "Flush buffers", "sync", "", ""),
    "tar": (U, "archiv", "frei", "Archiv packen oder auspacken", "Pack or unpack an archive", "tar -czf <a.tgz> <pfad> | tar -tzf <a.tgz> | tar -xzf <a.tgz>", "-c packen, -x auspacken, -t zeigen, -z gzip, -f Datei, -v ausführlich", "-c create, -x extract, -t list, -z gzip, -f file, -v verbose"),
    "gzip": (U, "archiv", "frei", "Datei packen", "Compress a file", "gzip <datei>", "", ""),
    "gunzip": (U, "archiv", "frei", "Datei entpacken", "Uncompress a file", "gunzip <datei.gz>", "", ""),
    "zcat": (U, "archiv", "frei", "Gepackte Datei zeigen", "Show a compressed file", "zcat <datei.gz>", "", ""),
    "zip": (U, "archiv", "frei", "Zip-Archiv packen", "Make a zip archive", "zip [-r] <a.zip> <pfad>", "", ""),
    "unzip": (U, "archiv", "frei", "Zip-Archiv auspacken", "Unpack a zip archive", "unzip [-l] <a.zip>", "-l nur zeigen", "-l list only"),
    "ps": (U, "prozess", "lesen", "Prozesse", "Processes", "ps aux", "", ""),
    "pstree": (U, "prozess", "lesen", "Prozessbaum", "Process tree", "pstree", "", ""),
    "pidof": (U, "prozess", "frei", "Nummer eines Prozesses", "Number of a process", "pidof <name>", "", ""),
    "kill": (U, "prozess", "frei", "Prozess beenden", "End a process", "kill [-9] <pid>", "-9 sofort", "-9 at once"),
    "pkill": (U, "prozess", "frei", "Prozess nach Name beenden", "End a process by name", "pkill <name>", "", ""),
    "killall": (U, "prozess", "frei", "Alle Prozesse eines Namens beenden", "End all processes of a name", "killall <name>", "", ""),
    "nice": (U, "prozess", "frei", "Mit Priorität starten", "Start with a priority", "nice -n 10 <befehl>", "", ""),
    "renice": (U, "prozess", "frei", "Priorität ändern", "Change a priority", "renice 10 -p <pid>", "", ""),
    "systemctl": (U, "prozess", "lesen", "Dienste", "Services", "systemctl status|start|stop|restart|is-active [dienst]", "list-units alle Dienste", "list-units all services"),
    "service": (U, "prozess", "lesen", "Dienste (alt)", "Services (old style)", "service <dienst> status|start|stop", "", ""),
}
# commands that need root and what they say without it
ROOT = {"useradd", "userdel", "usermod", "groupadd", "groupdel", "chage", "chown", "iptables", "umount", "fdisk", "mkfs",
        "fsck", "dd", "mdadm", "tcpdump", "reboot", "halt", "poweroff", "renice"}
# a few services always run on a Linux machine of the game; the scenario's services come on top
GRUND = ["sshd", "cron", "rsyslog"]
PORTS = {"sshd": 22, "nginx": 443, "apache2": 80, "httpd": 443, "postgresql": 5432, "postfix": 25, "bind9": 53,
         "openvpn": 1194, "bgpd": 179, "graylog": 9000, "nut": 3493, "sip": 5060, "vpn-gw": 443, "php-fpm": 9000,
         "erp-app": 8080, "restic-server": 8000, "bareos-sd": 9103, "hostd": 443, "vpxa": 902, "bms": 502,
         "genset": 502, "routing": 179, "fabric": 23, "policy": 443, "ctrl-a": 3260, "ctrl-b": 3260}
MODES = {"d": "drwxr-xr-x", "f": "-rw-r--r--"}
SIZE = 1024   # bytes a line counts for du/ls (fixed)
_NONE = object()
VOLL = "spark: the game's disk is full (at most %d files and %d KB you made)" % (SIM_MAX, SIM_BYTES // 1000)


def help_lines(name, en, spec=None):
    """The help of a command (-h, --help, man): what it does, how to call it, the options and where it exists."""
    s = spec or LINUX.get(name)
    if not s:
        return []
    if len(s) == 8:
        where, grp, _, de, en_t, usage, od, oe = s
    else:
        where, _, de, en_t, usage = s
        od = oe = ""
    rows = [f"{name} - {en_t if en else de}", ("Usage: " if en else "Aufruf: ") + usage]
    if od:
        rows.append(("Options: " if en else "Optionen: ") + (oe if en else od))
    keep, depth = [], 0
    for ch in usage.split(" | ")[0]:          # the example: the usage without [optional parts] and alternatives
        depth += (ch == "[") - (ch == "]")
        if depth == 0 and ch not in "]<>":
            keep.append(ch)
    rows.append(("Example: " if en else "Beispiel: ") + " ".join(w.split("|")[0] for w in "".join(keep).split()))
    if where:
        rows.append(("Only on: " if en else "Nur auf: ") + (("Windows" if where == ("win",) else
                                                            "Linux and network devices" if en else "Linux und Netzgeräte")))
    rows.append("(simulated: nothing runs on the Spark)" if en else "(simuliert: nichts läuft auf dem Spark)")
    return rows


class Ctx:
    """What a command may see and change: the game state, the machine, the scenario's world and a few helpers."""

    def __init__(self, st, host, world, holds, en, status, asset_name, hosts):
        self.st, self.h, self.world, self.holds, self.en = st, host, world, holds, en
        self.status, self.asset_name, self.hosts = status, asset_name, hosts
        self.k = st["konsole"]
        self.effekt = None          # a move for the game (a stopped service, a reboot)
        self.lesen = False          # a reading command (costs a minute)

    @property
    def hid(self):
        return self.h["id"]

    def sim(self, hid=None):
        sims = self.k.setdefault("sim", {})
        return sims.setdefault(hid or self.hid, {"neu": {}, "weg": [], "aus": [], "user": [], "grp": {}, "mounts": [],
                                                 "fw": [], "mode": {}, "lock": []})

    @property
    def cwd(self):
        return self.k.setdefault("cwd", {}).get(self.hid, HOME)

    def chdir(self, p):
        self.k.setdefault("cwd", {})[self.hid] = p

    def say(self, de, en):
        return en if self.en else de


# ---------------------------------------------------------------- the file system of a machine
def _base(c, h):
    """The fixed files of a machine: path -> lines."""
    hid = h["id"]
    svc = _services(c, h)
    f = {"/etc/hostname": [hid],
         "/etc/hosts": ["127.0.0.1 localhost"] + [f"{x['ip']} {x['id']}" for x in c.hosts],
         "/etc/os-release": ['PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"', "VERSION_ID=12"],
         "/etc/passwd": ["root:x:0:0:root:/root:/bin/bash", "admin:x:1000:1000:Admin:/home/admin:/bin/bash"]
                        + [f"{u}:x:{1001 + i}:{1001 + i}::/home/{u}:/bin/bash" for i, u in enumerate(c.sim(hid)["user"])],
         "/etc/group": ["root:x:0:", "sudo:x:27:admin", "adm:x:4:admin"]
                       + [f"{g}:x:{2000 + i}:{','.join(m)}" for i, (g, m) in enumerate(sorted(c.sim(hid)["grp"].items()))],
         "/home/admin/README.txt": [c.say("Willkommen auf " + hid + ". Alles hier ist simuliert, nichts läuft wirklich.",
                                          "Welcome to " + hid + ". Everything here is simulated, nothing really runs."),
                                    c.say("help zeigt die Befehle, <befehl> -h die Hilfe dazu, hosts die Rechner.",
                                          "help shows the commands, <command> -h its help, hosts the machines.")],
         "/var/log/syslog": [f"{hid} systemd[1]: {s}: {'Stopped' if st == 'stopped' else 'Started'} {s}." for s, st in svc]
                            + [f"{hid} kernel: eth0: link {'down' if c.status(h) in ('Offline', 'Isolated') else 'up'}"]}
    for x in c.world.get("dateien", []):
        if x["host"] == hid and x["pfad"].startswith("/"):
            f[x["pfad"]] = [y[0] if isinstance(y, list) else y for y in x["zeilen"] if not isinstance(y, list) or c.holds(y[1], c.st)]
    return f


def tree(c, hid=None):
    """(files: path -> lines or {"archiv": …}, dirs: set) of a machine with what the player changed."""
    h = c.h if hid is None else next(x for x in c.hosts if x["id"] == hid)
    s = c.sim(h["id"])
    files = _base(c, h)
    dirs = {"/", "/etc", "/home", HOME, "/root", "/tmp", "/var", "/var/log", "/usr", "/usr/bin", "/mnt", "/srv", "/opt"}
    for p, v in s["neu"].items():
        if v is None:
            dirs.add(p)
        else:
            files[p] = v
    for w in s["weg"]:
        for p in [p for p in files if p == w or p.startswith(w.rstrip("/") + "/")]:
            if p not in s["neu"] or s["neu"][p] is None:
                files.pop(p, None)
        dirs = {d for d in dirs if not (d == w or d.startswith(w.rstrip("/") + "/")) or d in s["neu"]}
    for p in files:
        d = posixpath.dirname(p)
        while d and d not in dirs:
            dirs.add(d)
            d = posixpath.dirname(d) if d != "/" else ""
    return files, dirs


def norm(c, p):
    p = (p or "").strip()
    if p == "~" or p.startswith("~/"):
        p = HOME + p[1:]
    if not p.startswith("/"):
        p = posixpath.join(c.cwd, p)
    return posixpath.normpath(p).replace("//", "/") or "/"


def _writable(c, p, root):
    return root or p.startswith(HOME + "/") or p == HOME or p.startswith("/tmp/") or p == "/tmp"


def _put(c, p, v, hid=None):
    s = c.sim(hid)
    if p not in s["neu"] and len(s["neu"]) >= SIM_MAX:
        return False
    if isinstance(v, list):
        v = [str(x)[:200] for x in v][:LINE_MAX]
    old = s["neu"].get(p, _NONE)
    s["neu"][p] = v
    if len(json.dumps(c.k.get("sim", {}), ensure_ascii=False)) > SIM_BYTES:
        if old is _NONE:
            del s["neu"][p]
        else:
            s["neu"][p] = old
        return False
    if p in s["weg"]:
        s["weg"].remove(p)
    return True


def _drop(c, p, hid=None):
    s = c.sim(hid)
    for q in [q for q in s["neu"] if q == p or q.startswith(p.rstrip("/") + "/")]:
        del s["neu"][q]
    if p not in s["weg"] and len(s["weg"]) < SIM_MAX:
        s["weg"].append(p)


def _content(c, path):
    files, dirs = tree(c)
    p = norm(c, path)
    if p in dirs:
        return None, f"{path}: Is a directory"
    if p not in files:
        return None, f"{path}: No such file or directory"
    v = files[p]
    if isinstance(v, dict):
        return None, f"{path}: binary file ({'gzip' if 'gz' in v else 'archive'} data)"
    return v, ""


def write(c, path, lines, append, root):
    """> and >> and tee: into the game's file system; "" or an error line."""
    p = norm(c, path)
    if len(p) > MAX_PATH:
        return f"{path}: File name too long"
    files, dirs = tree(c)
    if p in dirs:
        return f"{path}: Is a directory"
    if posixpath.dirname(p) not in dirs:
        return f"{path}: No such file or directory"
    if not _writable(c, p, root):
        return f"{path}: Permission denied"
    old = files.get(p) if append and isinstance(files.get(p), list) else []
    if not _put(c, p, list(old) + list(lines)):
        return VOLL
    return ""


# ---------------------------------------------------------------- services and processes
def _services(c, h):
    names = (GRUND if h["os"] == "linux" else []) + list(h.get("dienste", []))
    down = c.status(h) in ("Offline", "Critical")
    aus = c.sim(h["id"])["aus"]
    return [(s, "stopped" if s in aus or down else "running") for s in names]


def _pid(name, i):
    return 1200 + 7 * i + (sum(map(ord, name)) % 5)


def _stop(c, svc, how):
    """A service of this machine stops (systemctl stop, kill, pkill): of a system of the game, the game feels it."""
    s = c.sim()
    if svc in s["aus"]:
        return
    s["aus"].append(svc)
    a = c.h.get("asset")
    if a and svc in c.h.get("dienste", []) and c.status(c.h) in ("Online", "Degraded") and not c.effekt:
        old = c.status(c.h)
        s["vorher"] = old
        name = c.asset_name(a)
        c.effekt = {"id": "konsole_dienst", "label": ["Dienst an der Konsole angehalten", "Service stopped at the console"],
                    "zeit": 2, "stress": 3, "kosten": 2000, "setzt": {a: "Degraded"} if old == "Online" else {},
                    "text": [f"{svc} auf {c.hid} ist angehalten ({how}): {name} läuft nur noch eingeschränkt.",
                             f"{svc} on {c.hid} is stopped ({how}): {name} only runs in part."]}


def _start(c, svc):
    s = c.sim()
    if svc not in s["aus"]:
        return
    s["aus"].remove(svc)
    a = c.h.get("asset")
    if a and not [x for x in s["aus"] if x in c.h.get("dienste", [])] and s.get("vorher") == "Online" \
            and c.status(c.h) == "Degraded" and not c.effekt:
        s.pop("vorher", None)
        c.effekt = {"id": "konsole_dienst_an", "label": ["Dienst an der Konsole gestartet", "Service started at the console"],
                    "zeit": 2, "setzt": {a: "Online"},
                    "text": [f"{svc} auf {c.hid} läuft wieder, {c.asset_name(a)} auch.", f"{svc} on {c.hid} runs again, so does {c.asset_name(a)}."]}


# ---------------------------------------------------------------- patterns (never a regular expression)
def glob(pat, name):
    """* and ? of find -name, matched by hand (one pass with a single point to go back to, no regular expression)."""
    p = n = 0
    star, mark = -1, 0
    while n < len(name):
        if p < len(pat) and pat[p] in ("?", name[n]):
            p, n = p + 1, n + 1
        elif p < len(pat) and pat[p] == "*":
            star, mark, p = p, n, p + 1
        elif star >= 0:
            p, mark = star + 1, mark + 1
            n = mark
        else:
            return False
    return all(x == "*" for x in pat[p:])


def hit(pat, line, ci=False):
    if ci:
        pat, line = pat.lower(), line.lower()
    if pat.startswith("^") and pat.endswith("$") and len(pat) > 1:
        return line == pat[1:-1]
    if pat.startswith("^"):
        return line.startswith(pat[1:])
    if pat.endswith("$"):
        return line.endswith(pat[:-1])
    return pat in line


def _num(args, default=10):
    for i, a in enumerate(args):
        if a == "-n" and i + 1 < len(args) and args[i + 1].lstrip("+").isdigit():
            return int(args[i + 1].lstrip("+"))
        if a.startswith("-") and a[1:].isdigit():
            return int(a[1:])
    return default


def _plain(args):
    """Arguments without options and without the value of -n, -d, -f, -F, -o, -G."""
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if a in ("-n", "-d", "-f", "-F", "-o", "-G", "-u", "-c", "-t", "-k", "-s", "-p", "-m") and not a == "-":
            skip = a in ("-n", "-d", "-f", "-F", "-o", "-G", "-u", "-k", "-p")
            continue
        if a.startswith("-") and len(a) > 1:
            continue
        out.append(a)
    return out


def text_cmd(c, name, args, data):
    """The text commands, on a file or on the lines of a pipe (data). Returns lines or None if not a text command."""
    if name in ("grep", "egrep", "fgrep", "zgrep"):
        pl = _plain(args)
        if not pl:
            return ["usage: grep [-i] [-v] [-n] [-c] [-r] <pattern> <file>"]
        pat, srcs = pl[0], pl[1:]
        flags = "".join(a[1:] for a in args if a.startswith("-") and not a[1:].isdigit())
        rows = []
        if data is not None and not srcs:
            groups = [("", data)]
        else:
            groups = []
            for s in srcs:
                if "r" in flags or "R" in flags:
                    files, dirs = tree(c)
                    base = norm(c, s)
                    for p in sorted(files):
                        if (p == base or p.startswith(base.rstrip("/") + "/")) and isinstance(files[p], list):
                            groups.append((p, files[p]))
                    continue
                v = _gz(c, s) if name == "zgrep" else _content(c, s)
                if v[0] is None:
                    rows.append(f"grep: {v[1]}")
                    continue
                groups.append((s if len(srcs) > 1 else "", v[0]))
        for src, lines in groups:
            n = 0
            for i, l in enumerate(lines):
                if hit(pat, l, "i" in flags) != ("v" in flags):
                    n += 1
                    if "c" not in flags:
                        rows.append((f"{src}:" if src else "") + (f"{i + 1}:" if "n" in flags else "") + l)
            if "c" in flags:
                rows.append((f"{src}:" if src else "") + str(n))
        return rows
    src = _plain(args)
    if name in ("cat", "less", "more", "tac", "nl", "head", "tail", "wc", "sort", "uniq", "cut", "awk", "sed", "column", "tr"):
        if name in ("sed", "awk", "tr") and src:
            src = src[1:] if name != "tr" else src[2:]
        if data is None:
            if not src:
                return [f"{name}: missing file operand"]
            lines = []
            for s in src[:5]:
                v, err = _content(c, s)
                if v is None:
                    return [f"{name}: {err}"]
                lines += v
        else:
            lines = list(data)
    else:
        return None
    if name in ("cat", "less", "more"):
        return [f"{i + 1:>6}  {l}" for i, l in enumerate(lines)] if "-n" in args else lines
    if name == "tac":
        return lines[::-1]
    if name == "nl":
        return [f"{i + 1:>6}  {l}" for i, l in enumerate(lines)]
    if name == "head":
        return lines[:_num(args)]
    if name == "tail":
        n = _num(args)
        return (lines[-n:] if n else []) + (["(tail -f: following is not possible here, run it again)"] if "-f" in args else [])
    if name == "wc":
        nl, nw, nc = len(lines), sum(len(l.split()) for l in lines), sum(len(l) + 1 for l in lines)
        if "-l" in args:
            return [str(nl)]
        if "-w" in args:
            return [str(nw)]
        if "-c" in args:
            return [str(nc)]
        return [f"{nl:>4} {nw:>5} {nc:>6}"]
    if name == "sort":
        key = (lambda l: (float(l.split()[0]) if l.split() and l.split()[0].replace(".", "", 1).isdigit() else 0.0, l)) \
            if "-n" in args or "-rn" in args or "-nr" in args else None
        out = sorted(lines, key=key, reverse=any(a in args for a in ("-r", "-rn", "-nr")))
        return list(dict.fromkeys(out)) if "-u" in args else out
    if name == "uniq":
        out, last, n = [], None, 0
        for l in lines + [None]:
            if l == last:
                n += 1
                continue
            if last is not None:
                out.append(f"{n:>7} {last}" if "-c" in args else last)
            last, n = l, 1
        return out
    if name == "cut":
        d = _opt(args, "-d", "\t")
        f = _opt(args, "-f", "1")
        idx = [int(x) - 1 for x in f.split(",") if x.isdigit()]
        return [d.join(p[i] for i in idx if i < len(p)) for p in (l.split(d) for l in lines)]
    if name == "awk":
        prog = next((a for a in args if a.startswith("{") or "print" in a), "")
        sep = _opt(args, "-F", None)
        out = []
        for l in lines:
            cols = l.split(sep) if sep else l.split()
            if "print" not in prog:
                out.append(l)
                continue
            parts = []
            for tok in prog.split("print", 1)[1].strip(" {}").split(","):
                tok = tok.strip()
                if tok == "$0":
                    parts.append(l)
                elif tok == "NF":
                    parts.append(str(len(cols)))
                elif tok.startswith("$") and tok[1:].isdigit():
                    i = int(tok[1:]) - 1
                    parts.append(cols[i] if 0 <= i < len(cols) else "")
                elif tok.startswith('"') and tok.endswith('"'):
                    parts.append(tok[1:-1])
            out.append(" ".join(parts))
        return out
    if name == "sed":
        prog = next((a for a in args if not a.startswith("-")), "")
        if prog.startswith("s") and len(prog) > 3:
            sep = prog[1]
            p = prog.split(sep)
            if len(p) >= 3:
                return [l.replace(p[1], p[2]) if "g" in (p[3] if len(p) > 3 else "") else l.replace(p[1], p[2], 1)
                        for l in lines]
        if prog[:-1].isdigit() and prog[-1:] in ("p", "d"):
            n = int(prog[:-1]) - 1
            return [lines[n]] if prog[-1] == "p" and 0 <= n < len(lines) else [l for i, l in enumerate(lines) if i != n] \
                if prog[-1] == "d" else []
        return ["sed: only s/old/new/[g], Np and Nd are simulated here"]
    if name == "tr":
        pl = [a for a in args if not a.startswith("-")]
        if "-d" in args and pl:
            return ["".join(ch for ch in l if ch not in pl[0]) for l in lines]
        if len(pl) >= 2:
            a, b = pl[0], pl[1]
            if a in ("a-z", "[:lower:]") and b in ("A-Z", "[:upper:]"):
                return [l.upper() for l in lines]
            if a in ("A-Z", "[:upper:]") and b in ("a-z", "[:lower:]"):
                return [l.lower() for l in lines]
            tab = {ord(x): (b[i] if i < len(b) else b[-1:]) for i, x in enumerate(a)}
            return [l.translate(tab) for l in lines]
        return ["usage: tr <from> <to> | tr -d <chars>"]
    if name == "column":
        rows = [l.split() for l in lines]
        w = [max(len(r[i]) for r in rows if i < len(r)) for i in range(max((len(r) for r in rows), default=0))]
        return ["  ".join(x.ljust(w[i]) for i, x in enumerate(r)).rstrip() for r in rows]
    return None


def _opt(args, key, default):
    for i, a in enumerate(args):
        if a == key and i + 1 < len(args):
            return args[i + 1]
        if a.startswith(key) and len(a) > len(key):
            return a[len(key):]
    return default


def _gz(c, s):
    files, _ = tree(c)
    v = files.get(norm(c, s))
    if isinstance(v, dict) and "gz" in v:
        return v["gz"], ""
    if isinstance(v, list):
        return v, ""
    return None, f"{s}: No such file or directory"


def pipe(c, part, lines, root):
    """A command after |: the text commands and tee."""
    name, args = part[0].lower(), part[1:]
    if name == "sudo" and args:
        name, args, root = args[0].lower(), args[1:], True
    if name == "tee":
        for f in [a for a in args if not a.startswith("-")][:3]:
            err = write(c, f, lines, "-a" in args, root)
            if err:
                return lines + [f"tee: {err}"]
        return lines
    out = text_cmd(c, name, args, lines)
    return out if out is not None else [f"{name}: cannot read from a pipe here"]


# ---------------------------------------------------------------- the commands
def run(c, name, args, root):
    """One Linux command on the machine of ctx; lines. c.effekt may be set to a move for the game."""
    spec = LINUX[name]
    c.lesen = spec[2] == "lesen"
    en = c.en
    if name in ROOT and not root:
        if name in ("reboot", "halt", "poweroff"):
            return ["Failed to set wall message: Access denied", f"Call to {name} failed: Interactive authentication required. (sudo {name})"]
        return [f"{name}: Permission denied (are you root? try: sudo {name} …)"]
    out = text_cmd(c, name, args, None)
    if out is not None:
        return out
    f = _CMDS.get(name)
    return f(c, args, root) if f else []


def _ls(c, args, root):
    files, dirs = tree(c)
    flags = "".join(a[1:] for a in args if a.startswith("-"))
    targets = [a for a in args if not a.startswith("-")] or ["."]
    s = c.sim()
    out = []
    for t in targets:
        p = norm(c, t)
        if p in files:
            out.append(_lsl(c, p, files[p], s) if "l" in flags else posixpath.basename(p))
            continue
        if p not in dirs:
            out.append(f"ls: cannot access '{t}': No such file or directory")
            continue
        kids = sorted({q[len(p.rstrip('/')) + 1:].split("/")[0] for q in list(files) + list(dirs)
                       if q.startswith(p.rstrip("/") + "/") and q != p})
        if "a" not in flags:
            kids = [x for x in kids if not x.startswith(".")]
        else:
            kids = [".", ".."] + kids
        if len(targets) > 1:
            out.append(f"{t}:")
        if "l" in flags:
            out.append(f"total {len(kids) * 4}")
            for x in kids:
                q = posixpath.normpath(posixpath.join(p, x))
                out.append(_lsl(c, q, files.get(q), s, x))
        elif kids:
            out.append("  ".join(x + ("/" if posixpath.normpath(posixpath.join(p, x)) in dirs and x not in (".", "..") else "")
                                 for x in kids))
    return out


def _lsl(c, p, v, s, name=None):
    kind = "d" if v is None else "f"
    mode = s["mode"].get(p) or MODES[kind]
    own = "admin" if p.startswith(HOME) or p.startswith("/tmp") else "root"
    size = 4096 if v is None else (len(v) * 64 if isinstance(v, list) else 2048)
    if isinstance(v, list) and v and str(v[0]).startswith("->"):
        mode = "lrwxrwxrwx"
    return f"{mode} 1 {own:<6} {own:<6} {size:>6} Oct 22 09:00 {name or posixpath.basename(p)}" + \
        (f" {v[0]}" if mode.startswith("l") else "")


def _cd(c, args, root):
    t = args[0] if args else "~"
    if t == "-":
        t = c.k.setdefault("oldcwd", {}).get(c.hid, HOME)
    p = norm(c, t)
    _, dirs = tree(c)
    if p not in dirs:
        return [f"bash: cd: {t}: No such file or directory"]
    if p == "/root" and not root:
        return [f"bash: cd: {t}: Permission denied"]
    c.k.setdefault("oldcwd", {})[c.hid] = c.cwd
    c.chdir(p)
    return []


def _mkdir(c, args, root):
    out = []
    for t in [a for a in args if not a.startswith("-")]:
        p = norm(c, t)
        files, dirs = tree(c)
        if p in dirs or p in files:
            out.append(f"mkdir: cannot create directory '{t}': File exists")
        elif posixpath.dirname(p) not in dirs and "-p" not in args:
            out.append(f"mkdir: cannot create directory '{t}': No such file or directory")
        elif not _writable(c, p, root):
            out.append(f"mkdir: cannot create directory '{t}': Permission denied")
        elif len(p) > MAX_PATH or not _put(c, p, None):
            out.append(f"mkdir: cannot create directory '{t}': No space left on device")
    return out


def _touch(c, args, root):
    out = []
    for t in [a for a in args if not a.startswith("-")]:
        p = norm(c, t)
        files, dirs = tree(c)
        if p in files or p in dirs:
            continue
        err = write(c, t, [], False, root)
        if err:
            out.append(f"touch: cannot touch '{t}': {err.split(': ', 1)[-1]}")
    return out


def _cp(c, args, root, move=False):
    pl = [a for a in args if not a.startswith("-")]
    nm = "mv" if move else "cp"
    if len(pl) < 2:
        return [f"{nm}: missing destination file operand"]
    files, dirs = tree(c)
    src, dst = norm(c, pl[0]), norm(c, pl[1])
    if dst in dirs:
        dst = posixpath.join(dst, posixpath.basename(src))
    if not _writable(c, dst, root) or move and not _writable(c, src, root):
        return [f"{nm}: cannot create '{pl[1]}': Permission denied"]
    if src in files:
        if not _put(c, dst, files[src]):
            return [f"{nm}: {VOLL}"]
    elif src in dirs:
        if not move and not ({"-r", "-R", "-a", "-rf"} & set(args)):
            return [f"cp: -r not specified; omitting directory '{pl[0]}'"]
        ok = _put(c, dst, None)
        for p, v in files.items():
            if p.startswith(src.rstrip("/") + "/"):
                ok = _put(c, dst + p[len(src):], v) and ok
        if not ok:
            return [f"{nm}: {VOLL}"]
    else:
        return [f"{nm}: cannot stat '{pl[0]}': No such file or directory"]
    if move:
        _drop(c, src)
    return []


def _rm(c, args, root):
    out = []
    files, dirs = tree(c)
    rec = any(a in args for a in ("-r", "-R", "-rf", "-fr"))
    force = any(a in args for a in ("-f", "-rf", "-fr"))
    for t in [a for a in args if not a.startswith("-")]:
        p = norm(c, t)
        if p in ("/", HOME, "/etc", "/var", "/usr", "/home"):
            out.append(f"rm: refusing to remove '{t}' (the game keeps its system folders)")
        elif p not in files and p not in dirs:
            if not force:
                out.append(f"rm: cannot remove '{t}': No such file or directory")
        elif p in dirs and not rec:
            out.append(f"rm: cannot remove '{t}': Is a directory")
        elif not _writable(c, p, root):
            out.append(f"rm: cannot remove '{t}': Permission denied")
        else:
            _drop(c, p)
    return out


def _rmdir(c, args, root):
    files, dirs = tree(c)
    out = []
    for t in [a for a in args if not a.startswith("-")]:
        p = norm(c, t)
        if p not in dirs:
            out.append(f"rmdir: failed to remove '{t}': No such file or directory")
        elif any(q.startswith(p.rstrip("/") + "/") for q in list(files) + list(dirs)):
            out.append(f"rmdir: failed to remove '{t}': Directory not empty")
        elif not _writable(c, p, root):
            out.append(f"rmdir: failed to remove '{t}': Permission denied")
        else:
            _drop(c, p)
    return out


def _ln(c, args, root):
    pl = [a for a in args if not a.startswith("-")]
    if len(pl) < 2:
        return ["ln: missing file operand"]
    return [] if not write(c, pl[1], ["-> " + pl[0]], False, root) else [f"ln: failed to create link '{pl[1]}': Permission denied"]


def _tree(c, args, root):
    files, dirs = tree(c)
    base = norm(c, next((a for a in args if not a.startswith("-")), "."))
    if base not in dirs:
        return [f"{base} [error opening dir]"]
    items = sorted(p for p in list(files) + list(dirs) if p.startswith(base.rstrip("/") + "/"))
    out = [base]
    for p in items[:80]:
        depth = p[len(base.rstrip('/')):].count("/") - 1
        out.append("    " * depth + "├── " + posixpath.basename(p))
    nd = sum(1 for p in items if p in dirs)
    out.append(f"\n{nd} directories, {len(items) - nd} files")
    return out


def _du(c, args, root):
    files, dirs = tree(c)
    t = next((a for a in args if not a.startswith("-")), ".")
    base = norm(c, t)
    size = sum(len(v) * 64 if isinstance(v, list) else 2048 for p, v in files.items()
               if p == base or p.startswith(base.rstrip("/") + "/"))
    shown = f"{max(4, size // 1024)}K" if "h" in "".join(args) else str(max(4, size // 1024))
    return [f"{shown}\t{t}"]


def _stat(c, args, root):
    files, dirs = tree(c)
    out = []
    for t in [a for a in args if not a.startswith("-")]:
        p = norm(c, t)
        if p not in files and p not in dirs:
            out.append(f"stat: cannot statx '{t}': No such file or directory")
            continue
        v = files.get(p)
        out += [f"  File: {t}", f"  Size: {4096 if p in dirs else len(v or []) * 64}\t" +
                ("directory" if p in dirs else "regular file"),
                f"Access: ({c.sim()['mode'].get(p) or MODES['d' if p in dirs else 'f']})  Uid: ({'admin' if p.startswith(HOME) else 'root'})"]
    return out


def _find(c, args, root):
    files, dirs = tree(c)
    start = next((a for a in args if not a.startswith("-")), ".")
    name = _opt(args, "-name", None) or _opt(args, "-iname", None)
    kind = _opt(args, "-type", None)
    base = norm(c, start)
    out = []
    for p in sorted(list(files) + list(dirs)):
        if not (p == base or p.startswith(base.rstrip("/") + "/")):
            continue
        if kind == "f" and p not in files or kind == "d" and p not in dirs:
            continue
        if name and not glob(name[:60].lower() if "-iname" in args else name[:60],
                             posixpath.basename(p).lower() if "-iname" in args else posixpath.basename(p)):
            continue
        out.append(p if start.startswith("/") else "." + p[len(base):] if p != base else ".")
    return out[:200]


def _which(c, args, root):
    from krisenkonsole import BEFEHLE   # noqa: E402 (krisenkonsole imports this module)
    out = []
    for a in args:
        if a in LINUX or a in BEFEHLE:
            out.append(f"/usr/bin/{a}" if c.k else a)
    return out


def _whereis(c, args, root):
    return [f"{a}: /usr/bin/{a} /usr/share/man/man1/{a}.1.gz" if a in LINUX else f"{a}:" for a in args]


def _file(c, args, root):
    files, dirs = tree(c)
    out = []
    for t in args:
        p = norm(c, t)
        v = files.get(p)
        kind = "directory" if p in dirs else "cannot open (No such file or directory)" if v is None and p not in files else \
            ("gzip compressed data" if "gz" in v else "POSIX tar archive (gzip compressed data)" if "tar" in v else "Zip archive data")\
            if isinstance(v, dict) else "symbolic link to " + v[0][3:] if v and str(v[0]).startswith("->") else \
            "empty" if not v else "ASCII text"
        out.append(f"{t}: {kind}")
    return out


def _sum(c, args, root, algo):
    out = []
    for t in [a for a in args if not a.startswith("-")]:
        v, err = _content(c, t)
        if v is None:
            out.append(f"{algo}: {err}")
            continue
        data = ("\n".join(v) + "\n").encode()
        if algo == "cksum":
            out.append(f"{int(hashlib.md5(data).hexdigest()[:8], 16)} {len(data)} {t}")
        else:
            out.append(f"{hashlib.new(algo.replace('sum', '')).hexdigest()}  {t}")
    return out


def _cmp(c, args, root):
    pl = [a for a in args if not a.startswith("-")]
    if len(pl) < 2:
        return ["cmp: missing operand"]
    a, ea = _content(c, pl[0])
    b, eb = _content(c, pl[1])
    if a is None or b is None:
        return [f"cmp: {ea or eb}"]
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return [f"{pl[0]} {pl[1]} differ: line {i + 1}"]
    return [] if len(a) == len(b) else [f"cmp: EOF on {pl[0] if len(a) < len(b) else pl[1]}"]


def _diff(c, args, root):
    pl = [a for a in args if not a.startswith("-")]
    if len(pl) < 2:
        return ["diff: missing operand"]
    a, ea = _content(c, pl[0])
    b, eb = _content(c, pl[1])
    if a is None or b is None:
        return [f"diff: {ea or eb}"]
    sb, sa = set(b), set(a)
    return [f"< {x}" for x in a if x not in sb] + (["---"] if any(x not in sb for x in a) and any(y not in sa for y in b) else []) \
        + [f"> {y}" for y in b if y not in sa]


def _echo(c, args, root):
    env = _env(c)
    words = []
    for a in args:
        if a == "-n" or a == "-e":
            continue
        for k, v in env.items():
            a = a.replace("$" + k, v)
        words.append(a)
    return [" ".join(words)]


def _env(c):
    return {"HOME": HOME, "USER": "admin", "SHELL": "/bin/bash", "PWD": c.cwd, "HOSTNAME": c.hid, "LANG": "de_DE.UTF-8",
            "PATH": "/usr/local/bin:/usr/bin:/bin"}


def _top(c, args, root):
    s = _services(c, c.h)
    busy = c.status(c.h) not in ("Online",)
    rows = [f"top - up 41 days,  load average: {'7.90, 6.12, 4.40' if busy else '0.42, 0.37, 0.30'}",
            f"Tasks: {len(s) + 80} total,   1 running", "  PID USER      %CPU %MEM COMMAND"]
    rows += [f"{_pid(n, i):>5} {'root':<9} {('85.0' if busy and i == len(s) - 1 else '0.3'):>5}  1.2 {n}"
             for i, (n, st) in enumerate(s) if st == "running"]
    return rows


def _ps(c, args, root):
    s = _services(c, c.h)
    return ["USER       PID %CPU %MEM COMMAND"] + [f"root     {_pid(n, i):>5}  0.3  1.2 /usr/sbin/{n}" for i, (n, st) in enumerate(s)
                                                  if st == "running"] + ["admin     4711  0.0  0.1 -bash"]


def _pstree(c, args, root):
    return ["systemd─┬─" + "\n        ├─".join(n for n, st in _services(c, c.h) if st == "running") + "\n        └─sshd───bash───pstree"]


def _pidof(c, args, root):
    s = _services(c, c.h)
    hits = [str(_pid(n, i)) for i, (n, st) in enumerate(s) if st == "running" and args and n == args[0]]
    return [" ".join(hits)] if hits else []


def _kill(c, args, root, by_name=False):
    s = _services(c, c.h)
    targets = [a for a in args if not a.startswith("-")]
    out = []
    for t in targets:
        found = [(n, i) for i, (n, st) in enumerate(s) if st == "running" and (n == t if by_name else str(_pid(n, i)) == t)]
        if t == "4711" and not by_name:
            out.append("spark: that is your own shell; it stays")
            continue
        if not found:
            out.append(f"kill: ({t}) - No such process" if not by_name else "")
            continue
        if not root:
            out.append(f"kill: ({_pid(found[0][0], found[0][1])}) - Operation not permitted")
            continue
        _stop(c, found[0][0], "kill")
    return [x for x in out if x]


def _systemctl(c, args, root, service_style=False):
    if service_style:   # service <name> <action>
        args = [args[1], args[0]] if len(args) >= 2 else ["status"] + args
    act = args[0] if args else "list-units"
    names = [n for n, _ in _services(c, c.h)]
    state = dict(_services(c, c.h))
    if act in ("list-units", "--type=service"):
        return ["UNIT                       LOAD   ACTIVE SUB"] + \
            [f"{n + '.service':<26} loaded {'active' if s == 'running' else 'failed':<6} {s}" for n, s in state.items()]
    svc = (args[1] if len(args) > 1 else "").replace(".service", "")
    if act == "status" and not svc:
        return [f"● {c.hid}", f"    State: {'degraded' if any(s != 'running' for s in state.values()) else 'running'}"]
    if svc not in names:
        return [f"Unit {svc}.service could not be found." if svc else "Too few arguments."]
    if act == "status":
        run_ = state[svc] == "running"
        return [f"● {svc}.service", f"     Loaded: loaded (/lib/systemd/system/{svc}.service; enabled)",
                f"     Active: {'active (running)' if run_ else 'inactive (dead)'}", f"   Main PID: {_pid(svc, names.index(svc)) if run_ else '-'}"]
    if act == "is-active":
        return ["active" if state[svc] == "running" else "inactive"]
    if act in ("start", "stop", "restart", "enable", "disable", "reload"):
        if not root:
            return [f"Failed to {act} {svc}.service: Access denied", f"(try: sudo systemctl {act} {svc})"]
        if c.status(c.h) in ("Offline",):
            return [f"Job for {svc}.service failed: the machine has no power or no system (see hosts)"]
        if act == "stop":
            _stop(c, svc, "systemctl stop")
        elif act in ("start", "restart"):
            _start(c, svc)
        return []
    return [f"Unknown command verb {act}."]


def _users(c, args, root, name):
    s = c.sim()
    pl = [a for a in args if not a.startswith("-")]
    if name == "useradd":
        if not pl:
            return ["useradd: missing user name"]
        u = pl[-1][:32]
        if u in s["user"] or u in ("root", "admin"):
            return [f"useradd: user '{u}' already exists"]
        if len(s["user"]) >= 50:
            return ["useradd: too many users in this game"]
        s["user"].append(u)
        g = _opt(args, "-G", None)
        if g:
            s["grp"].setdefault(g[:32], [])
            s["grp"][g[:32]].append(u)
        if "-m" in args:
            _put(c, f"/home/{u}", None)
        return []
    if name == "userdel":
        u = pl[-1] if pl else ""
        if u not in s["user"]:
            return [f"userdel: user '{u}' does not exist"]
        s["user"].remove(u)
        for m in s["grp"].values():
            if u in m:
                m.remove(u)
        if "-r" in args:
            _drop(c, f"/home/{u}")
        return []
    if name == "usermod":
        u = pl[-1] if pl else ""
        if u not in s["user"] and u != "admin":
            return [f"usermod: user '{u}' does not exist"]
        g = _opt(args, "-aG", None) or _opt(args, "-G", None)
        if g:
            s["grp"].setdefault(g[:32], [])
            if u not in s["grp"][g[:32]]:
                s["grp"][g[:32]].append(u)
        if "-L" in args and u not in s["lock"]:
            s["lock"].append(u)
        if "-U" in args and u in s["lock"]:
            s["lock"].remove(u)
        return []
    if name == "groupadd":
        g = pl[-1][:32] if pl else ""
        if not g:
            return ["groupadd: missing group name"]
        if g in s["grp"]:
            return [f"groupadd: group '{g}' already exists"]
        s["grp"][g] = []
        return []
    if name == "groupdel":
        g = pl[-1] if pl else ""
        return [] if s["grp"].pop(g, None) is not None else [f"groupdel: group '{g}' does not exist"]
    if name == "passwd":
        u = pl[-1] if pl else "admin"
        if u != "admin" and not root:
            return [f"passwd: You may not view or modify password information for {u}."]
        if u not in s["user"] and u not in ("admin", "root"):
            return [f"passwd: user '{u}' does not exist"]
        if "-l" in args:
            s["lock"].append(u)
            return [f"passwd: password changed. (account {u} locked)"]
        return ["New password: ********", "Retype new password: ********", "passwd: password updated successfully"]
    if name == "chage":
        return ["Last password change\t\t\t\t\t: Oct 01, 2026", "Password expires\t\t\t\t\t: never"]
    return []


def _id(c, args, root):
    s = c.sim()
    u = args[0] if args else "admin"
    if u not in s["user"] and u not in ("admin", "root"):
        return [f"id: '{u}': no such user"]
    grp = ["sudo", "adm"] if u == "admin" else []
    grp += [g for g, m in s["grp"].items() if u in m]
    uid = 0 if u == "root" else 1000 if u == "admin" else 1001 + s["user"].index(u)
    return [f"uid={uid}({u}) gid={uid}({u}) groups={uid}({u})" + "".join(f",{2000 + i}({g})" for i, g in enumerate(grp))]


def _groups(c, args, root):
    line = _id(c, args, root)[0]
    if line.startswith("id:"):
        return [line.replace("id:", "groups:")]
    return [" ".join(x.split("(")[1].rstrip(")") for x in line.split("groups=")[1].split(","))]


def _ports(c, h):
    return [(PORTS.get(n, 8000 + i), n) for i, (n, st) in enumerate(_services(c, h)) if st == "running"]


def _target(c, t):
    t = (t or "").split("@")[-1].split(":")[0].split("/")[0].lower()
    t = t.replace("http", "").lstrip(":/") if t.startswith("http") else t
    return next((x for x in c.hosts if x["id"] == t or x["ip"] == t), None)


def _ping(c, args, root):
    t = _target(c, next((a for a in args if not a.startswith("-")), ""))
    if not t:
        return [f"ping: {(args or [''])[-1][:40]}: Name or service not known"]
    s, ip = c.status(t), t["ip"]
    if s == "Offline":
        return [f"PING {t['id']} ({ip}) 56(84) bytes of data.", "From gateway icmp_seq=1 Destination Host Unreachable",
                "--- 3 packets transmitted, 0 received, 100% packet loss"]
    if s == "Isolated":
        return [f"PING {t['id']} ({ip}) 56(84) bytes of data.", "From gateway icmp_seq=1 Destination Net Unreachable",
                "--- 3 packets transmitted, 0 received, 100% packet loss"]
    ms, lost = {"Online": ("0.4", 0), "Degraded": ("183", 1), "Critical": ("912", 2)}[s]
    return [f"PING {t['id']} ({ip}) 56(84) bytes of data."] + \
        [f"64 bytes from {ip}: icmp_seq={i + 1} ttl=63 time={ms} ms" for i in range(3 - lost)] + \
        [f"--- 3 packets transmitted, {3 - lost} received, {lost * 33}% packet loss"]


def _trace(c, args, root):
    t = _target(c, next((a for a in args if not a.startswith("-")), ""))
    if not t:
        return ["traceroute: unknown host"]
    ok = c.status(t) in ("Online", "Degraded", "Critical")
    return [f"traceroute to {t['id']} ({t['ip']}), 30 hops max", " 1  gateway  0.3 ms",
            f" 2  {t['id']} ({t['ip']})  0.6 ms" if ok else " 2  * * *"]


def _resolve(c, args, root, style):
    name = next((a for a in args if not a.startswith("-") and not a.startswith("+")), "")
    t = _target(c, name)
    dns = next((x for x in c.hosts if x.get("asset") in ("dns", "ad")), None)
    if dns and c.status(dns) in ("Offline", "Critical"):
        return [f";; connection timed out; no servers could be reached ({dns['id']})"]
    if not t:
        return [f"** server can't find {name[:40]}: NXDOMAIN" if style != "host" else f"Host {name[:40]} not found: 3(NXDOMAIN)"]
    if style == "host":
        return [f"{t['id']} has address {t['ip']}"]
    if style == "dig":
        return [t["ip"]] if "+short" in args else [";; ANSWER SECTION:", f"{t['id']}.\t300\tIN\tA\t{t['ip']}"]
    return [f"Name:\t{t['id']}", f"Address: {t['ip']}"]


def _ip(c, args, root):
    a = args[0] if args else "a"
    if a.startswith("r"):
        return ["default via " + c.h["ip"].rsplit(".", 1)[0] + ".1 dev eth0"]
    if a.startswith("l"):
        return [f"2: eth0: <BROADCAST,MULTICAST,{'UP' if c.status(c.h) not in ('Offline', 'Isolated') else 'DOWN'}> mtu 1500"]
    return ["1: lo: inet 127.0.0.1/8", f"2: eth0: inet {c.h['ip']}/24"]


def _ifconfig(c, args, root):
    return [f"eth0: flags=4163<UP,BROADCAST,RUNNING>  mtu 1500", f"        inet {c.h['ip']}  netmask 255.255.255.0"]


def _route(c, args, root):
    gw = c.h["ip"].rsplit(".", 1)[0] + ".1"
    return ["Destination     Gateway         Genmask         Iface", f"0.0.0.0         {gw:<15} 0.0.0.0         eth0"]


def _arp(c, args, root):
    return [f"{x['id']} ({x['ip']}) at 52:54:00:{i:02x}:1a:2b [ether] on eth0" for i, x in enumerate(c.hosts)
            if x["id"] != c.hid and c.status(x) not in ("Offline", "Isolated")]


def _ss(c, args, root):
    if c.status(c.h) in ("Offline",):
        return []
    return ["State  Local Address:Port  Process"] + [f"LISTEN 0.0.0.0:{p:<12} users:((\"{n}\"))" for p, n in _ports(c, c.h)]


def _nmap(c, args, root):
    t = _target(c, next((a for a in args if not a.startswith("-")), ""))
    if not t:
        return ["Failed to resolve given hostname/IP"]
    if c.status(t) in ("Offline", "Isolated"):
        return [f"Note: Host seems down ({t['ip']})."]
    return [f"Nmap scan report for {t['id']} ({t['ip']})", "PORT      STATE SERVICE"] + \
        [f"{str(p) + '/tcp':<9} open  {n}" for p, n in _ports(c, t)]


def _curl(c, args, root, wget=False):
    raw = next((a for a in args if not a.startswith("-") and a != _opt(args, "-o", None) and a != _opt(args, "-O", None)), "")
    t = _target(c, raw)
    if not t:
        return [f"curl: (6) Could not resolve host: {raw[:40]}"]
    s = c.status(t)
    web = any(p in (80, 443, 8080, 9000) for p, _ in _ports(c, t))
    if s in ("Offline", "Isolated") or not web:
        return [f"curl: (7) Failed to connect to {t['id']} port 443: Connection refused" if web or s == "Online"
                else f"curl: (28) Connection timed out after 10000 ms"]
    code = {"Online": "200 OK", "Degraded": "200 OK", "Critical": "503 Service Unavailable"}[s]
    body = [f"<html><title>{t['id']}</title><body>{'ok' if code.startswith('200') else 'Service Unavailable'}</body></html>"]
    target = _opt(args, "-o", None) or (posixpath.basename(raw.split("/", 1)[1]) if wget and "/" in raw else "index.html" if wget else None)
    if target:
        err = write(c, target, body, False, root)
        return [f"HTTP request sent, awaiting response... {code}", err or f"Saving to: '{target}'"] if wget else ([err] if err else [])
    if "-I" in args:
        return [f"HTTP/1.1 {code}", "Server: nginx", f"X-Response-Time: {'40' if s == 'Online' else '2900'} ms"]
    return body


def _nc(c, args, root, telnet=False):
    pl = [a for a in args if not a.startswith("-")]
    t = _target(c, pl[0] if pl else "")
    port = int(pl[1]) if len(pl) > 1 and pl[1].isdigit() else 0
    if not t:
        return ["nc: getaddrinfo: Name or service not known"]
    open_ = any(p == port for p, _ in _ports(c, t)) and c.status(t) not in ("Offline", "Isolated")
    if telnet:
        return [f"Trying {t['ip']}...", f"Connected to {t['id']}." if open_ else "telnet: Unable to connect to remote host: Connection refused"]
    return [f"Connection to {t['id']} {port} port [tcp] succeeded!" if open_ else f"nc: connect to {t['id']} port {port} (tcp) failed: Connection refused"]


def _tcpdump(c, args, root):
    n = _num(args, 5) if "-c" not in args else int(_opt(args, "-c", "5")) if _opt(args, "-c", "5").isdigit() else 5
    others = [x for x in c.hosts if x["id"] != c.hid] or [c.h]
    ports = _ports(c, c.h) or [(22, "sshd")]
    return ["listening on eth0, link-type EN10MB (Ethernet)"] + [
        f"09:{10 + i:02d}:0{i % 10}.{i * 137 % 1000:03d} IP {others[i % len(others)]['ip']}.5{i}312 > {c.h['ip']}.{ports[i % len(ports)][0]}: Flags [S], length 0"
        for i in range(min(n, 20))] + [f"{min(n, 20)} packets captured"]


def _ethtool(c, args, root):
    up = c.status(c.h) not in ("Offline", "Isolated")
    return ["Settings for eth0:", "\tSpeed: 10000Mb/s", "\tDuplex: Full", f"\tLink detected: {'yes' if up else 'no'}"]


def _scp(c, args, root):
    pl = [a for a in args if not a.startswith("-")]
    if len(pl) < 2 or ":" not in pl[1]:
        return ["usage: scp <file> <host>:<path>"]
    v, err = _content(c, pl[0])
    if v is None:
        return [f"scp: {err}"]
    hname, path = pl[1].split(":", 1)
    t = _target(c, hname)
    if not t:
        return [f"ssh: Could not resolve hostname {hname[:40]}"]
    if c.status(t) in ("Offline", "Isolated"):
        return [f"ssh: connect to host {t['id']} port 22: No route to host"]
    path = path or HOME
    if not path.startswith("/"):
        path = posixpath.join(HOME, path)
    path = posixpath.normpath(path)
    files, dirs = tree(c, t["id"])
    if path in dirs:
        path = posixpath.join(path, posixpath.basename(norm(c, pl[0])))
    if not (path.startswith(HOME) or path.startswith("/tmp")):
        return [f"scp: {path}: Permission denied"]
    _put(c, path, v, t["id"])
    return [f"{posixpath.basename(pl[0])}    100%  {len(v) * 64}B  1.0MB/s   00:00"]


def _iptables(c, args, root):
    s = c.sim()
    if "-L" in args or not args or "-S" in args:
        return ["Chain INPUT (policy ACCEPT)", "target     prot source               destination"] + \
            [f"{r}" for r in s["fw"]] or ["(no rules)"]
    if "-F" in args:
        s["fw"] = []
        return []
    rule = " ".join(a for a in args if a not in ("-A", "-I", "-D") and a not in ("INPUT", "OUTPUT", "FORWARD"))
    chain = next((a for a in args if a in ("INPUT", "OUTPUT", "FORWARD")), "INPUT")
    line = f"{chain:<10} {rule[:80]}"
    if "-D" in args:
        if line in s["fw"]:
            s["fw"].remove(line)
            return []
        return ["iptables: Bad rule (does a matching rule exist in that chain?)."]
    if len(s["fw"]) >= 50:
        return ["iptables: too many rules in this game"]
    if "-I" in args:
        s["fw"].insert(0, line)
    else:
        s["fw"].append(line)
    return []


def _mount(c, args, root):
    s = c.sim()
    pl = [a for a in args if not a.startswith("-")]
    if not pl:
        return ["/dev/sda1 on / type ext4 (rw,relatime)", "tmpfs on /tmp type tmpfs (rw)"] + \
            [f"{d} on {m} type ext4 (rw)" for d, m in s["mounts"]]
    if not root:
        return ["mount: only root can do that (try: sudo mount …)"]
    if len(pl) < 2:
        return ["mount: can't find in /etc/fstab."]
    dev, mnt = pl[0], norm(c, pl[1])
    if dev not in ("/dev/sdb1", "/dev/sdc1", "/dev/md0"):
        return [f"mount: {mnt}: special device {dev} does not exist."]
    _, dirs = tree(c)
    if mnt not in dirs:
        return [f"mount: {mnt}: mount point does not exist."]
    if len(s["mounts"]) < 10:
        s["mounts"].append([dev, mnt])
    return []


def _umount(c, args, root):
    s = c.sim()
    pl = [norm(c, a) if a.startswith("/") or a.startswith(".") else a for a in args if not a.startswith("-")]
    before = len(s["mounts"])
    s["mounts"] = [m for m in s["mounts"] if m[1] not in pl and m[0] not in pl]
    return [] if len(s["mounts"]) < before else [f"umount: {(args or [''])[-1]}: not mounted."]


def _df(c, args, root):
    h = "-h" in args or "-H" in args
    rows = ["Filesystem      Size  Used Avail Use% Mounted on", f"/dev/sda1       {'200G' if h else '209715200'}   61G  139G  31% /",
            "tmpfs           7.8G     0  7.8G   0% /tmp"]
    return rows + [f"{d:<15} 2.0T  1.1T  0.9T  55% {m}" for d, m in c.sim()["mounts"]]


def _lsblk(c, args, root):
    return ["NAME   SIZE TYPE MOUNTPOINT", "sda    200G disk", "└─sda1 200G part /", "sdb    2.0T disk", "└─sdb1 2.0T part " +
            next((m for d, m in c.sim()["mounts"] if d == "/dev/sdb1"), "")]


def _danger(c, args, root, name):
    if name == "fdisk" and "-l" in args:
        return ["Disk /dev/sda: 200 GiB", "/dev/sda1  2048 419430366 419428319  200G 83 Linux", "Disk /dev/sdb: 2 TiB",
                "/dev/sdb1  2048 4294967262 4294965215  2T 83 Linux"]
    if name == "mdadm":
        return ["/dev/md0:", "        Raid Level : raid1", "             State : clean", "    Active Devices : 2"]
    return [f"spark: {name} would change or wipe a disk; in this game the disks are protected, nothing changed."]


def _archive(c, args, root, name):
    pl = [a for a in args if not a.startswith("-") and not (name == "tar" and set(a) <= set("cxtzvf"))]
    flags = "".join(a.lstrip("-") for a in args if a.startswith("-") or (name == "tar" and set(a) <= set("cxtzvf")))
    files, dirs = tree(c)
    if name == "tar" or name in ("zip", "unzip"):
        create = "c" in flags if name == "tar" else name == "zip"
        listing = "t" in flags if name == "tar" else name == "unzip" and "l" in flags
        if not pl:
            return [f"{name}: missing archive name"]
        arc = norm(c, pl[0])
        if create:
            members = {}
            for src in pl[1:]:
                p = norm(c, src)
                for q, v in files.items():
                    if (q == p or q.startswith(p.rstrip("/") + "/")) and isinstance(v, list):
                        members[q.lstrip("/")] = v
            if not members:
                return [f"{name}: {pl[1] if len(pl) > 1 else ''}: Cannot stat: No such file or directory"]
            err = "" if _writable(c, arc, root) else f"{name}: {pl[0]}: Cannot open: Permission denied"
            if err:
                return [err]
            _put(c, arc, {"tar" if name == "tar" else "zip": dict(list(members.items())[:50])})
            return [f"  adding: {m}" for m in members] if name == "zip" or "v" in flags else []
        v = files.get(arc)
        if not isinstance(v, dict) or not ("tar" in v or "zip" in v):
            return [f"{name}: {pl[0]}: Cannot open: No such file or directory"]
        members = v.get("tar") or v.get("zip")
        if listing:
            return list(members)
        for m, lines in members.items():
            write(c, posixpath.join(c.cwd, m.split("/", 1)[-1] if m.startswith("home/") else m), lines, False, root)
        return [f"  inflating: {m}" for m in members] if name == "unzip" or "v" in flags else []
    if name in ("gzip", "gunzip"):
        out = []
        for t in pl:
            p = norm(c, t)
            v = files.get(p)
            if name == "gzip":
                if not isinstance(v, list):
                    out.append(f"gzip: {t}: No such file or directory")
                    continue
                if not _writable(c, p, root):
                    out.append(f"gzip: {t}: Permission denied")
                    continue
                _put(c, p + ".gz", {"gz": v})
                _drop(c, p)
            else:
                if not isinstance(v, dict) or "gz" not in v:
                    out.append(f"gzip: {t}: not in gzip format")
                    continue
                _put(c, p[:-3] if p.endswith(".gz") else p + ".out", v["gz"])
                _drop(c, p)
        return out
    if name == "zcat":
        out = []
        for t in pl:
            v, err = _gz(c, t)
            out += v if v is not None else [f"zcat: {err}"]
        return out
    return []


def _misc(c, args, root, name):
    en = c.en
    if name == "pwd":
        return [c.cwd]
    if name in ("basename", "dirname"):
        p = args[0] if args else ""
        return [posixpath.basename(p.rstrip("/")) if name == "basename" else posixpath.dirname(p.rstrip("/")) or "."]
    if name in ("readlink", "realpath"):
        t = next((a for a in args if not a.startswith("-")), "")
        files, _ = tree(c)
        v = files.get(norm(c, t))
        return [v[0][3:] if name == "readlink" and v and str(v[0]).startswith("->") and "-f" not in args else norm(c, t)]
    if name in ("free",):
        h = "-h" in args
        busy = c.status(c.h) != "Online"
        return ["               total        used        free", f"Mem:     {'15Gi' if h else '16303424':>11} {('14Gi' if busy else '3.1Gi') if h else ('14811200' if busy else '3251200'):>11} {('1.0Gi' if busy else '12Gi') if h else ('1492224' if busy else '13052224'):>11}",
                "Swap:     " + ("2.0Gi" if h else "2097148")]
    if name == "uname":
        return ["Linux " + c.hid + " 6.1.0-26-amd64 #1 SMP Debian 6.1.112-1 x86_64 GNU/Linux"] if "-a" in args else \
            ["6.1.0-26-amd64"] if "-r" in args else ["Linux"]
    if name == "uptime":
        return [f" 09:41:00 up 41 days,  2 users,  load average: {'7.90' if c.status(c.h) != 'Online' else '0.42'}, 0.37, 0.30"]
    if name == "vmstat":
        return ["procs ---memory--- ---io--- -cpu-", " r  b   free   bi   bo us sy id wa",
                f" {'9' if c.status(c.h) != 'Online' else '1'}  {'6' if c.status(c.h) != 'Online' else '0'} 3251200  12  40  5  2 {'20' if c.status(c.h) != 'Online' else '93'} {'70' if c.status(c.h) != 'Online' else '0'}"]
    if name == "iostat":
        return ["Device   tps  kB_read/s  kB_wrtn/s", f"sda    {'812' if c.status(c.h) != 'Online' else '12'}   {'9000' if c.status(c.h) != 'Online' else '40'}   120"]
    if name == "dmesg":
        rows = ["[    0.000000] Linux version 6.1.0-26-amd64", "[    2.104112] eth0: link up, 10000 Mbps"]
        if c.status(c.h) in ("Critical", "Degraded"):
            rows.append("[3561021.12] blk_update_request: I/O error, dev sdb, sector 81920")
        return rows
    if name == "journalctl":
        u = _opt(args, "-u", None)
        rows = [f"Oct 22 09:{10 + i:02d} {c.hid} systemd[1]: {'Stopped' if st == 'stopped' else 'Started'} {n}.service"
                for i, (n, st) in enumerate(_services(c, c.h)) if not u or n == u.replace(".service", "")]
        return rows[-_num(args, 20):] if rows else ["-- No entries --"]
    if name == "lsof":
        return ["COMMAND   PID USER   TYPE NODE NAME"] + [f"{n[:9]:<9} {_pid(n, i)} root   IPv4 TCP  *:{p} (LISTEN)"
                                                       for i, (p, n) in enumerate(_ports(c, c.h))]
    if name == "date":
        return [("Spielminute " if not en else "game minute ") + str(c.st["m"]["zeit_start"] - c.st["m"]["zeit"])]
    if name == "cal":
        return ["    Oktober 2026" if not en else "    October 2026", "Mo Di Mi Do Fr Sa So" if not en else "Mo Tu We Th Fr Sa Su",
                "          1  2  3  4", " 5  6  7  8  9 10 11", "12 13 14 15 16 17 18", "19 20 21 22 23 24 25", "26 27 28 29 30 31"]
    if name == "arch":
        return ["x86_64"]
    if name == "hostname":
        return [c.hid]
    if name == "hostnamectl":
        return [f" Static hostname: {c.hid}", "Operating System: Debian GNU/Linux 12 (bookworm)", "          Kernel: Linux 6.1.0-26-amd64"]
    if name == "watch":
        return ["watch: not interactive here; run the command again to see it change"]
    if name in ("env", "printenv"):
        e = _env(c)
        pl = [a for a in args if not a.startswith("-")]
        return [e[pl[0]]] if pl and pl[0] in e else [] if pl else [f"{k}={v}" for k, v in e.items()]
    if name in ("whoami",):
        return ["corp\\admin" if c.h["os"] == "win" else "root" if root else "admin"]
    if name in ("who", "users", "w"):
        rows = ["admin    pts/0        2026-10-22 08:58 (10.0.99.5)"]
        if name == "users":
            return ["admin"]
        if name == "w":
            return [" 09:41:00 up 41 days,  1 user", "USER     TTY      FROM         LOGIN@   WHAT"] + \
                ["admin    pts/0    10.0.99.5    08:58    -bash"]
        return rows
    if name == "last":
        return ["admin    pts/0        10.0.99.5        Thu Oct 22 08:58   still logged in",
                "admin    pts/0        10.0.99.5        Wed Oct 21 17:02 - 18:40  (01:38)", "", "wtmp begins Thu Oct  1 00:00:01 2026"]
    if name == "su":
        return ["su: Authentication failure (use sudo <command>; a root shell is not simulated)"]
    if name == "umask":
        return ["0022"]
    if name in ("chmod", "chgrp", "chown"):
        pl = [a for a in args if not a.startswith("-")]
        if len(pl) < 2:
            return [f"{name}: missing operand"]
        files, dirs = tree(c)
        out = []
        for t in pl[1:]:
            p = norm(c, t)
            if p not in files and p not in dirs:
                out.append(f"{name}: cannot access '{t}': No such file or directory")
            elif not _writable(c, p, root):
                out.append(f"{name}: changing permissions of '{t}': Operation not permitted")
            elif name == "chmod":
                c.sim()["mode"][p] = _mode(pl[0], c.sim()["mode"].get(p) or MODES["d" if p in dirs else "f"])
        return out
    if name in ("vi", "nano"):
        return ["spark: no full-screen editor here; write with echo 'text' > file or echo 'text' >> file"]
    if name in ("nice",):
        return ["spark: nice only changes the priority; type the command itself"]
    if name == "renice":
        return [f"{args[-1] if args else '?'} (process ID) old priority 0, new priority {args[0] if args else '0'}"]
    if name in ("reboot", "halt", "poweroff"):
        s = c.sim()
        s["aus"] = []
        a = c.h.get("asset")
        if a and not c.effekt:
            back = {a: "Online"} if s.pop("vorher", None) == "Online" and c.status(c.h) == "Degraded" else {}
            c.effekt = {"id": "konsole_neustart", "label": ["Neustart an der Konsole", "Restart at the console"],
                        "zeit": 5, "stress": 2, "setzt": back,
                        "text": [f"{c.hid} startet neu, fünf Minuten ist {c.asset_name(a)} nicht erreichbar.",
                                 f"{c.hid} restarts, for five minutes {c.asset_name(a)} cannot be reached."]}
        return [f"Broadcast message from root@{c.hid}: The system will {'reboot' if name == 'reboot' else 'power off'} now!",
                f"Connection to {c.hid} closed by remote host." if name != "reboot" else "(the machine is back after the restart)"]
    if name == "sync":
        return []
    return []


def _mode(spec, old):
    if spec.isdigit() and len(spec) == 3:
        bits = "rwx"
        return old[0] + "".join("".join(b if int(d) & (4 >> i) else "-" for i, b in enumerate(bits)) for d in spec)
    m = list(old)
    if len(spec) >= 3 and spec[1] in "+-":
        who = {"u": [1], "g": [4], "o": [7], "a": [1, 4, 7]}.get(spec[0], [1, 4, 7])
        for ch in spec[2:]:
            off = "rwx".find(ch)
            if off < 0:
                continue
            for w in who:
                m[w + off] = ch if spec[1] == "+" else "-"
    return "".join(m)


_CMDS = {
    "ls": _ls, "cd": _cd, "mkdir": _mkdir, "touch": _touch, "cp": _cp, "mv": lambda c, a, r: _cp(c, a, r, True),
    "rm": _rm, "rmdir": _rmdir, "ln": _ln, "tree": _tree, "du": _du, "stat": _stat, "find": _find, "which": _which,
    "whereis": _whereis, "file": _file, "md5sum": lambda c, a, r: _sum(c, a, r, "md5sum"),
    "sha256sum": lambda c, a, r: _sum(c, a, r, "sha256sum"), "cksum": lambda c, a, r: _sum(c, a, r, "cksum"),
    "cmp": _cmp, "diff": _diff, "echo": _echo, "top": _top, "htop": _top, "ps": _ps, "pstree": _pstree, "pidof": _pidof,
    "kill": _kill, "pkill": lambda c, a, r: _kill(c, a, r, True), "killall": lambda c, a, r: _kill(c, a, r, True),
    "systemctl": _systemctl, "service": lambda c, a, r: _systemctl(c, a, r, True),
    "useradd": lambda c, a, r: _users(c, a, r, "useradd"), "userdel": lambda c, a, r: _users(c, a, r, "userdel"),
    "usermod": lambda c, a, r: _users(c, a, r, "usermod"), "groupadd": lambda c, a, r: _users(c, a, r, "groupadd"),
    "groupdel": lambda c, a, r: _users(c, a, r, "groupdel"), "passwd": lambda c, a, r: _users(c, a, r, "passwd"),
    "chage": lambda c, a, r: _users(c, a, r, "chage"), "id": _id, "groups": _groups,
    "ping": _ping, "traceroute": _trace, "tracepath": _trace, "nslookup": lambda c, a, r: _resolve(c, a, r, "nslookup"),
    "dig": lambda c, a, r: _resolve(c, a, r, "dig"), "host": lambda c, a, r: _resolve(c, a, r, "host"), "ip": _ip,
    "ifconfig": _ifconfig, "route": _route, "arp": _arp, "ss": _ss, "netstat": _ss, "nmap": _nmap, "curl": _curl,
    "wget": lambda c, a, r: _curl(c, a, r, True), "nc": _nc, "telnet": lambda c, a, r: _nc(c, a, r, True),
    "tcpdump": _tcpdump, "ethtool": _ethtool, "scp": _scp, "iptables": _iptables, "mount": _mount, "umount": _umount,
    "df": _df, "lsblk": _lsblk, "blkid": lambda c, a, r: ['/dev/sda1: UUID="3f1c…" TYPE="ext4"', '/dev/sdb1: UUID="9a7e…" TYPE="ext4"'],
    "fdisk": lambda c, a, r: _danger(c, a, r, "fdisk"), "mkfs": lambda c, a, r: _danger(c, a, r, "mkfs"),
    "fsck": lambda c, a, r: _danger(c, a, r, "fsck"), "dd": lambda c, a, r: _danger(c, a, r, "dd"),
    "mdadm": lambda c, a, r: _danger(c, a, r, "mdadm"),
    "tar": lambda c, a, r: _archive(c, a, r, "tar"), "gzip": lambda c, a, r: _archive(c, a, r, "gzip"),
    "gunzip": lambda c, a, r: _archive(c, a, r, "gunzip"), "zcat": lambda c, a, r: _archive(c, a, r, "zcat"),
    "zip": lambda c, a, r: _archive(c, a, r, "zip"), "unzip": lambda c, a, r: _archive(c, a, r, "unzip"),
}
for _n in LINUX:
    if _n not in _CMDS and _n not in ("cat", "less", "more", "tac", "nl", "head", "tail", "wc", "sort", "uniq", "cut",
                                     "awk", "sed", "column", "tr", "grep", "egrep", "fgrep", "zgrep", "tee", "sudo"):
        _CMDS[_n] = (lambda name: lambda c, a, r: _misc(c, a, r, name))(_n)
