# Security checklist for new code

Go through before every commit. In the answer to Dominik briefly name which points the change touched. Part of the [Coding guideline](guidelines.md); German: [docs/de/sicherheits-checkliste.md](../de/sicherheits-checkliste.md). Created from the review of 08.10.2026 (V01.0.98); the brackets name the trap that was found there in each case. Since 12.10.2026 every change is additionally checked against the part **State of the art** at the end (Dominik: "everything secure and according to the latest technical security mechanisms").

## Access
- [ ] For every new endpoint it is defined: guest, profile in the browser, device key or admin.
- [ ] Secrets, addresses that receive a token, code word, push targets and mail accounts only with a browser login and a fresh code (`browser_profile` + `confirm_code`), never with the device key. (A device key could redirect the HA address and so steal the token.)
  - Only exception (V01.0.250, plan "iPhone app takes over the panel", stage 9): the key of the person's own iPhone app with the scope switch "Connect accounts in the app" ("Konten verbinden in der App"), via `secret_profile`: there the second login step is mandatory and every change needs a fresh code. Code word and MFA setup stay in the browser.
  - "Fresh" means since V01.0.289 (plan "Second login step less often"): a correct code of the same login (admin login, profile browser session or app key) from the last 10 minutes counts (`core.CONFIRM_WINDOW`). Really ask every time (`admin_code_fresh`, `secret_profile_fresh`, `confirm_code(..., fresh=True)`): the second step itself, admin password, roles, restoring/uploading/downloading/moving backups, code word, choosing the main admin, Spark update from the app. Admins (panel password or a profile with a role, signed in with the second step) are never asked at the confirm level (`core.admin_login`); admin rights never come from a PIN or handoff login. New endpoints of this kind belong in this list. A raw `fetch` to such endpoints only shows "code required": in the browser always use `api()`/`apiTry()`. A passkey (since V01.0.295, `passkey.py`, header `X-Speech-Passkey`) counts everywhere like a fresh code; new code prompts therefore always run via `confirm_code`, never via a separate `mfa.verify`. In the iPhone app (since V01.0.357) requests with a code run via `SparkAPI.confirmed(...)`, never with a separate `X-Speech-Code` header, so that "With passkey" ("Mit Passkey") works everywhere; creating passkeys stays in the browser. Since V01.0.427 (plan `plaene/zweiter-faktor-einheitlich.md`) every endpoint with a code is listed with level (confirm or change protection), area and text (de/en) in `app/panel/stufen.py` LIST; otherwise `test_stufen` fails. The list decides whether the 10 minutes count; new buttons with a code get the lock (`CODE_LOCKS` in `mfa.js`). Never read the second step of the emergency access directly from the file, always `mfa._path(ADMIN)` (linked to the main admin profile).
- [ ] If the address changes, the token must be entered again.
- [ ] State changes only via POST/PUT/DELETE, never via GET. (`?take=true`)
- [ ] Guests only get questions and answers: no tools, no personal data, no actions and no error texts, only error codes.
- [ ] An unknown recognised voice only gets non-personal tools. This also holds for parts a tool reads out along the way (briefing with reminders, Spark diary): personal parts only with `private_ok` or `ctx["own"]` and `ctx["private"]`. (Review 2026-10-14, 🧪 test_kontext_trennung)
- [ ] Shared devices (speakers in the room): the device key alone does not count as the owner. Personal things only when speaker recognition reliably recognises the owner's voice in the same recording; otherwise guest rights, and earlier history does not carry over. Whose voice it was is set only by the panel (request scope), never by the request. (V01.0.226: an unknown voice got the owner's mails.)
- [ ] Spoken code word (speaker, V01.0.297): only for a voice that is already almost certainly the owner, never for an unknown one; a code word of its own, not the smart-home code word; the sentence containing it never goes to the model, into history, diagnostics, display or log; lockout after failed attempts with a notification.
- [ ] Comparisons of keys and codes run with `hmac.compare_digest`.

## Size and load
- [ ] Size limit for the request body before anything is read. Read uploads with `read(limit+1)`. Parse the body only after login (FastAPI reads `File`/`Form` before the dependencies).
- [ ] For unpacked content (zip, docx, backup) limit the size after unpacking. (docx bomb)
- [ ] Audio: sample rate 8000 to 48000 Hz, duration limited (`ffmpeg -t`), read output with a byte limit. (1 Hz WAV, FLAC bomb)
- [ ] Downloads streamed and with a byte limit (CalDAV, CardDAV, webcal, pages).
- [ ] Text length for TTS and chat limited, also for the last message.
- [ ] Rate limit per IP and a global semaphore for LLM, ASR and TTS, especially for guests.
- [ ] Upper limit for jobs, tool calls per round, searches per answer and memory entries.
- [ ] Caches have an expiry date and a maximum size, and the key contains no times accurate to the second.
- [ ] Heavy synchronous work (RRULE expansion, large regex, ffmpeg) runs via `to_thread` with a time and quantity budget, never in the event loop. (A `FREQ=SECONDLY` appointment froze the panel.)
- [ ] New systemd units have `MemoryMax=` and `PrivateTmp=yes`.

## Outside text (prompt injection)
- [ ] Counts as outside: web, pages, mail, calendar, contacts, parcels, documents, HA states and attributes, Telegram, things overheard in the room as well as old answers built from them.
- [ ] Outside text is wrapped as data for the model (`_wrap`), and delimiters inside it are defused.
- [ ] A new reading tool goes into `READS_OUTSIDE`.
- [ ] After outside text, switching, memory, reminders, suggestions and drafts are blocked, and that also in the next turn. (The "outside" mark got lost in the next turn.)
- [ ] Answers from outside text are marked (`outside` event) and never learned into memory.
- [ ] Only offered tools run. A new tool is listed in the matching block lists.
- [ ] Code word and secrets never go to the model, to search, into history, the log or reminders (room cues).
- [ ] Content whose sender is not verified (DKIM/DMARC) is not presented as "from DHL" or "from contact X".

## Confirming and acting
- [ ] There is exactly one open suggestion per profile. It is valid only for the same device, a plain "Yes" and 15 minutes. Every new answer discards it.
- [ ] The voice check for "Yes" belongs to the same recording as the text.
- [ ] Home Assistant runs with an allowlist of domains, not with a block list (`script`, `automation`, `button` etc. stay out).
- [ ] Mail is never deleted. Moving only with a verified UIDVALIDITY and an exact match of sender and Message-ID after SEARCH.

## Outgoing requests (SSRF)
- [ ] Only http(s). Loopback, private and link-local addresses are blocked, unless the admin explicitly allows the home network.
- [ ] The checked IP is pinned (no second DNS lookup, so no DNS rebinding gap), and every redirect is checked again.
- [ ] Credentials go only to the same origin (also for hrefs from PROPFIND), there is never a fallback to http, and TLS verification is on.
- [ ] `ref_audio` and similar only as `data:` with a size limit, never as a URL.

## Injection
- [ ] `subprocess` only with list arguments, never `shell=True`, `eval` or `exec`. No `pickle` and no `allow_pickle` on outside data.
- [ ] IMAP values only from printable ASCII without CR/LF, quoted. (A Message-ID with `=0D=0A`)
- [ ] HTML is built via `textContent` or `esc()` plus `data-` attributes, never via inline `onclick` with values.
- [ ] Configuration values are checked the same way when saving, when restoring and in `install.sh`. In Bash only take over digits or fixed values.

## Secrets and logs
- [ ] Secrets live only in the vault and are never returned after saving.
- [ ] Logs and error texts contain no tokens. Bot tokens and keys are redacted, so do not output `str(e)` from httpx with a token in the URL.
- [ ] `/health` and similar open pages show only a status, no error texts and no names.
- [ ] The change log is written only by `guard.log` (hash chain); nothing writes, shortens or deletes `audit.log` another way.

## root boundary and update
- [ ] root follows no symlinks in folders owned by `speech` (`chown -h`, delete beforehand).
- [ ] New packages are installed with a fixed version.
- [ ] Nothing from the configuration ends up unchecked in a root script.

## Connection between two computers (Spark split)
- [ ] Everything between panel computer and model computer goes through the TLS-Tor (`common.model_url`, TLS 1.3, pinned certificate), never in plain text and never with "accept anything".
- [ ] New commands to the model computer only as fixed Wärter commands (`tarswart.COMMANDS`), signed, with a time stamp and a one-time number; values checked, never a version or a path from the panel.
- [ ] A pairing or moving step changes a computer's role only after a signed result from the other side and deletes nothing.

## Before the commit
- [ ] New switches are off by default: one admin switch, no new profile switch; only the admin blocks single profiles.
- [ ] Every new protection rule has a self-test.
- [ ] All self-tests are green.

## State of the art

Every change is checked not only against the traps above, but also against whether it matches today's state of security technology. If a standard is newly published or a method is classified as weak, this part is adjusted in the same commit and the list "Not yet met" is extended.

**Standards**
- [ ] Web and API: OWASP ASVS 5.0, level 2; login, secrets and admin paths level 3.
- [ ] Language model paths: OWASP Top 10 for LLM Applications 2025 (prompt injection, data leakage, excessive agency, unchecked output, unbounded consumption).
- [ ] Cryptography and TLS: BSI TR-02102 or NIST recommendations; TLS according to Mozilla "intermediate" or stricter.
- [ ] Supply chain: fixed versions with hash, pinned actions, signatures (SLSA idea: built traceably, loaded verified).

**Cryptography**
- [ ] Only proven libraries (`hashlib`, `secrets`, `hmac`, `cryptography`), never home-made schemes. Randomness only from `secrets`.
- [ ] New encryption only with AEAD (AES-256-GCM or ChaCha20-Poly1305), a key of its own per purpose, nonce never reused.
- [ ] New password derivation with scrypt or Argon2id; PBKDF2-SHA256 only with at least the current OWASP iteration count.
- [ ] Signatures with Ed25519; checks fail closed.

**Connections**
- [ ] Only TLS 1.2 or newer, TLS 1.3 preferred; certificate verification never off; no fallback to http.
- [ ] HSTS on https.

**Login and session**
- [ ] Passkeys (WebAuthn) before codes; second step as TOTP or passkey, never SMS.
- [ ] Session cookies `HttpOnly`, `Secure` on https, `SameSite=Strict` or `Lax`; new session identifier after login and change of rights; "sign out everywhere" possible.
- [ ] Lockout and delay after failed attempts per name and per browser.

**Browser**
- [ ] Strict CSP (`script-src 'self'`, no `unsafe-eval`, no inline scripts), `frame-ancestors`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`.
- [ ] Model output and outside texts are never executed as HTML in the interface.

**Supply chain and operation**
- [ ] New packages with version and hash in the lock; new actions pinned by SHA; adopt Dependabot alerts promptly.
- [ ] Secrets never in the repo (secret scanning with push protection is on).
- [ ] Known vulnerabilities in dependencies are checked before a version with new packages is shipped.

**Regular review**
- [ ] Before large versions and at least once a month a sceptical overall review against these standards (as on 08.10. and 11.10.2026). Every finding gets a self-test.

**Not yet met** (brought up to date the next time the place is touched; as of 12.10.2026)
- PBKDF2-SHA256 with 200,000 iterations for admin password and PIN (`core.ROUNDS`, `profiles.PIN_ROUNDS`); OWASP today recommends 600,000 or Argon2id/scrypt. Switch-over with recalculation at the next login.
- Fernet (AES-CBC plus HMAC) in the vault and for move keys: secure, but not AEAD; new parts use AES-GCM, a change only with migration of the existing data.
- No automatic vulnerability check of the Python packages (e.g. against the OSV database) in "Tests".
- Signed device updates are built, but off without a key (`UPDATE_SIGNING_KEY` is still missing).
- `style-src 'unsafe-inline'` remains because of older Safari versions in the iPhone app.
- Minimum TLS version of the own https server is not explicitly set (check).
