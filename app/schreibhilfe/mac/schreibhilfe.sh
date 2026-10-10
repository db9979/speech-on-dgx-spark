#!/bin/zsh
# Spark Schreibhilfe für den Mac: Schnellaktion „Mit Spark verbessern“ (Dienste-Menü, Rechtsklick auf markierten Text).
# Automator gibt den markierten Text auf stdin; was dieses Skript ausgibt, ersetzt die Markierung.
# Bei Abbruch oder Fehler kommt der ursprüngliche Text unverändert zurück, es geht also nie etwas verloren.
# Adresse und Schlüssel liegen im Schlüsselbund (Eintrag „Spark Schreibhilfe“), nie in einer Datei.
# Der Spark bekommt nur den markierten Text; er speichert ihn nicht und sendet nichts.

SVC="Spark Schreibhilfe"
text=$(cat)
keep() { print -rn -- "$text"; exit 0; }

# A dialog; every text goes in as an argument, never into the AppleScript source.
say_box() { osascript - "$1" >/dev/null 2>&1 <<'APPLESCRIPT'
on run argv
  display dialog (item 1 of argv) buttons {"OK"} default button "OK" with title "Spark Schreibhilfe" with icon caution
end run
APPLESCRIPT
}

detail() { print -r -- "$1" | plutil -extract detail raw -o - - 2>/dev/null || print -r -- "Der Spark hat nicht geantwortet."; }

is_home() {   # plain http only in the home network
  [[ "$1" =~ '^http://(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|[A-Za-z0-9-]+\.local)' ]]
}

base=$(security find-generic-password -s "$SVC" 2>/dev/null | sed -n 's/^ *"acct"<blob>="\(.*\)"$/\1/p')
key=$(security find-generic-password -s "$SVC" -w 2>/dev/null)

# ------------------------------------------------------------ pairing, once
if [[ -z "$key" || -z "$base" ]]; then
  line=$(osascript - 2>/dev/null <<'APPLESCRIPT'
on run
  text returned of (display dialog "Einrichtungszeile aus dem Panel einfügen (Ich → Schreibhilfe → Programm koppeln):" default answer "" with title "Spark Schreibhilfe")
end run
APPLESCRIPT
) || keep
  line=${line//[[:space:]]/}
  base=${line%%\#schreib=*}
  code=${line##*\#schreib=}
  code=${code//[^A-Za-z0-9-]/}
  base=${base%/}
  if [[ "$line" != *"#schreib="* || ! "$base" =~ '^https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?$' ]]; then
    say_box "Das ist keine Einrichtungszeile. Sie sieht so aus: https://spark.example.de#schreib=ABCD-EFGH"; keep
  fi
  if [[ "$base" == http://* ]] && ! is_home "$base"; then
    say_box "Unverschlüsselt (http) nur im Heimnetz. Bitte die https-Adresse des Spark nehmen."; keep
  fi
  name=$(scutil --get ComputerName 2>/dev/null | tr -cd 'A-Za-z0-9 ._-' | cut -c1-40)
  [[ -z "$name" ]] && name="Mac"
  resp=$(curl -sS --max-time 30 -H 'Content-Type: application/json' \
         --data-binary "{\"code\":\"$code\",\"name\":\"$name\",\"kind\":\"mac\"}" "$base/api/write/pair" 2>&1)
  key=$(print -r -- "$resp" | plutil -extract key raw -o - - 2>/dev/null)
  if [[ -z "$key" || "$key" != sd_* ]]; then
    say_box "Koppeln hat nicht geklappt: $(detail "$resp")"; keep
  fi
  security add-generic-password -U -s "$SVC" -a "$base" -w "$key" -T /usr/bin/security >/dev/null 2>&1 || {
    say_box "Der Schlüssel konnte nicht im Schlüsselbund gespeichert werden."; keep; }
fi

[[ -z "${text//[[:space:]]/}" ]] && { say_box "Erst Text markieren, dann „Mit Spark verbessern“."; keep; }

# ------------------------------------------------------------ what should happen
choice=$(osascript - 2>/dev/null <<'APPLESCRIPT'
on run
  set c to choose from list {"Korrigieren", "Glätten", "Kürzer", "Freundlicher", "Förmlicher", "Ins Englische", "Ins Deutsche"} default items {"Korrigieren"} with title "Spark Schreibhilfe" with prompt "Was soll mit dem Text passieren?"
  if c is false then return ""
  return item 1 of c
end run
APPLESCRIPT
)
case "$choice" in
  Korrigieren) q="art=korrigieren" ;;
  Glätten) q="art=glaetten" ;;
  Kürzer) q="art=kuerzer" ;;
  Freundlicher) q="art=freundlicher" ;;
  Förmlicher) q="art=foermlicher" ;;
  "Ins Englische") q="art=uebersetzen&sprache=en" ;;
  "Ins Deutsche") q="art=uebersetzen&sprache=de" ;;
  *) keep ;;
esac

# ------------------------------------------------------------ ask the Spark (the key goes in through a file
# descriptor, so it never shows in the list of running programs)
out=$(print -rn -- "$text" | curl -sS --max-time 180 -w '\n%{http_code}' \
      -H @<(print -r -- "X-Speech-Device: $key") -H 'Content-Type: text/plain; charset=utf-8' \
      --data-binary @- "$base/api/write/plain?$q" 2>&1)
status=${out##*$'\n'}
body=${out%$'\n'*}
if [[ "$status" != 200 ]]; then
  if [[ "$status" == 401 ]]; then
    security delete-generic-password -s "$SVC" >/dev/null 2>&1
    say_box "Der Spark kennt diesen Mac nicht mehr. Beim nächsten Mal neu koppeln (Ich → Schreibhilfe)."
  else
    say_box "$(detail "$body")"
  fi
  keep
fi

# ------------------------------------------------------------ look before it replaces the marked text
take=$(osascript - "$body" 2>/dev/null <<'APPLESCRIPT'
on run argv
  set t to item 1 of argv
  if (count of t) > 1500 then set t to (text 1 thru 1500 of t) & " …"
  set r to display dialog t buttons {"Abbrechen", "Übernehmen"} default button "Übernehmen" cancel button "Abbrechen" with title "Vorschlag vom Spark"
  return button returned of r
end run
APPLESCRIPT
)
[[ "$take" == "Übernehmen" ]] || keep
print -rn -- "$body"
