"""Fernzugang Stufe 5 (Windows): the file spark-anker-einrichten.cmd a pairing's „Einmal-Link“ hands out.

Dominik 2026-10-30: on Windows only with such a download (10 minutes, once): double-click, Windows asks „Ja“ (UAC),
the one-time key is in the file, nobody types a code; the new system then waits in the panel until the admin confirms
it with a fresh code or passkey (fernzugang.admin_confirm). The file holds, as plain text anyone can read before
running it:
- the panel's address (and the SHA-256 of its certificate when it is the panel at home),
- the one-time key (TOKEN_S seconds, once; only its hash stays in the panel, fernzugang.TOKENS),
- the anchor program spark-anker.py itself (Base64, checked against its SHA-256 before it is written),
- the Python for the anchor: python.org's embeddable package, version and SHA-256 from PY_EMBED in the anchor program
  (the one source; a new one comes with a signed anchor update).
Its steps (PowerShell inside the file, as Administrator): OpenSSH Server added when missing (Windows feature; taken
away again when the setup fails or the system is removed), Python only for the anchor unpacked to
%ProgramFiles%\\SparkAnker\\python-<version> (not on PATH), then `spark-anker.py einrichten <panel> --token -` with the
key on stdin (never an argument). The file deletes itself at the end. Nothing in it reaches a log."""
import base64
import hashlib
import importlib.util
import re

NAME = "spark-anker-einrichten.cmd"
URL = re.compile(r"https://[A-Za-z0-9.\-:\[\]]{1,300}")
_PINS = {}   # sha256 of the program -> PY_EMBED of it

# The batch part only elevates and starts the PowerShell part below the marker (read from this very file, so no line
# of it is ever parsed by cmd). CRLF throughout (cmd needs it).
HEAD = r"""@echo off
setlocal
rem Spark-Anker: richtet den Fernzugang des Spark-Panels auf diesem Windows ein (einmal, gilt 10 Minuten).
rem Was die Datei tut: OpenSSH-Server nur fuer 127.0.0.1, Benutzer spark nur mit dem Schluessel des Panels,
rem Python nur fuer den Anker in %ProgramFiles%\SparkAnker, zwei Aufgaben. Entfernen: Einstellungen, Apps, Spark Anker.
set "SPARK_DATEI=%~f0"
set "PSModulePath="
net session >nul 2>&1 || (powershell -NoProfile -Command "Start-Process -FilePath $env:SPARK_DATEI -Verb RunAs" & exit /b)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$t=[IO.File]::ReadAllText($env:SPARK_DATEI); iex $t.Substring($t.IndexOf('#SPARK'+'-PS'))"
echo.
pause
(goto) 2>nul & del "%~f0"
#SPARK-PS
"""

BODY = r"""$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
function Sag($t) {{ Write-Host "spark-anker: $t" }}
$Panel = '{url}'
$Fp = '{fp}'
$Token = '{token}'
$PyVersion = '{py_version}'
$PyHash = @{{ amd64 = '{py_amd64}'; arm64 = '{py_arm64}' }}
$AnkerSha = '{sha}'
$Anker = @'
{prog}
'@
$lib = Join-Path $env:ProgramFiles 'SparkAnker'
$sshdNeu = $false
try {{
  $arch = $env:PROCESSOR_ARCHITEW6432; if (-not $arch) {{ $arch = $env:PROCESSOR_ARCHITECTURE }}
  if ($arch -eq 'ARM64') {{ $arch = 'arm64' }} elseif ($arch -eq 'AMD64') {{ $arch = 'amd64' }} else {{ throw 'Nur 64-Bit-Windows (x64 oder ARM64).' }}
  if (Test-Path (Join-Path $env:ProgramData 'SparkAnker\anker.json')) {{ throw 'Schon eingerichtet. Neu koppeln: erst Einstellungen, Apps, Spark Anker deinstallieren.' }}
  if (-not (Get-Service sshd -ErrorAction SilentlyContinue)) {{
    Sag 'OpenSSH-Server wird hinzugefuegt (Windows-Funktion, das dauert einige Minuten) ...'
    Add-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0' | Out-Null
    if (-not (Get-Service sshd -ErrorAction SilentlyContinue)) {{ throw 'OpenSSH-Server liess sich nicht hinzufuegen.' }}
    $sshdNeu = $true
  }}
  $pydir = Join-Path $lib "python-$PyVersion"
  $py = Join-Path $pydir 'python.exe'
  if (-not (Test-Path $py)) {{
    Sag "Python $PyVersion nur fuer den Anker wird geladen (python.org) ..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $zip = Join-Path $env:TEMP "spark-anker-python-$PyVersion.zip"
    Invoke-WebRequest -UseBasicParsing -Uri "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-$arch.zip" -OutFile $zip
    $h = ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([IO.File]::ReadAllBytes($zip))) -replace '-', '').ToLower()
    if ($h -ne $PyHash[$arch]) {{ Remove-Item $zip; throw 'Python passt nicht zu seiner Pruefsumme.' }}
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory($zip, $pydir)
    Remove-Item $zip
  }}
  $bytes = [Convert]::FromBase64String(($Anker -replace '\s', ''))
  $sha = ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($bytes)) -replace '-', '').ToLower()
  if ($sha -ne $AnkerSha) {{ throw 'Das Programm in der Datei ist beschaedigt: die Datei im Panel neu laden.' }}
  $prog = Join-Path $lib 'spark-anker.py'
  [IO.File]::WriteAllBytes($prog, $bytes)
  $a = @('-I', $prog, 'einrichten', $Panel, '--token', '-')
  if ($Fp) {{ $a += @('--fp', $Fp) }}
  if ($sshdNeu) {{ $a += '--sshd-neu' }}
  $Token | & $py @a
  $rc = $LASTEXITCODE
  $Token = $null
  if ($rc -ne 0) {{ throw 'Es wurde nichts eingerichtet (siehe oben).' }}
  Sag 'fertig. Jetzt im Panel das neue System bestaetigen.'
}} catch {{
  Sag $_.Exception.Message
  if (-not (Test-Path (Join-Path $env:ProgramData 'SparkAnker\anker.json'))) {{
    Remove-Item -LiteralPath $lib -Recurse -Force -ErrorAction SilentlyContinue
    if ($sshdNeu) {{ Remove-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0' -ErrorAction SilentlyContinue | Out-Null }}
  }}
}}
"""


def _path():
    import fernzugang          # only here: the Windows check (tools/fernzugang_windows.py) runs this without the panel
    return fernzugang.PROGRAM


def pins(prog, path):
    """PY_EMBED of the anchor program (its own py_embed, the one source), cached per SHA-256; None when missing."""
    sha = hashlib.sha256(prog).hexdigest()
    if sha not in _PINS:
        spec = importlib.util.spec_from_file_location("spark_anker_pins", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _PINS.clear()
        _PINS[sha] = mod.py_embed(prog)
    return _PINS[sha]


def cmd_file(url, fp, token, path=None):
    """The file's bytes (CRLF) for this panel address, its pinned certificate ("" when checked by authorities) and the
    one-time key; None when the program or its Python pins are missing. path: the anchor program (the panel's own)."""
    if not URL.fullmatch(str(url or "")) or not re.fullmatch(r"[0-9a-f]{64}|", str(fp or "")) or \
            not re.fullmatch(r"[A-Za-z0-9_\-]{20,64}", str(token or "")):
        return None
    path = path or _path()
    try:
        with open(path, "rb") as f:
            prog = f.read()
    except OSError:
        return None
    p = pins(prog, path)
    if not p:
        return None
    b64 = base64.b64encode(prog).decode()
    body = BODY.format(url=url, fp=fp or "", token=token, py_version=p["version"], py_amd64=p["amd64"],
                       py_arm64=p["arm64"], sha=hashlib.sha256(prog).hexdigest(),
                       prog="\n".join(b64[i:i + 100] for i in range(0, len(b64), 100)))
    return (HEAD + body).replace("\r\n", "\n").replace("\n", "\r\n").encode("ascii")
