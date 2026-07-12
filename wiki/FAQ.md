# FAQ

**Is this official / affiliated with Anthropic?**
No. ClaudeMon is a personal community tool. It is not made, endorsed, or
supported by Anthropic.

**How does it get the usage numbers?**
The same undocumented endpoint Claude Code's `/usage` panel reads, authenticated
with an OAuth grant for **your own** account. Nothing is scraped, no third-party
service is involved, and nothing leaves your machine except the API calls to
Anthropic themselves.

**Could it stop working?**
Yes — the endpoint is undocumented and could change or disappear at any time.
The parser is deliberately strict: if the response shape changes, rows show
`DATA?` (instead of silently wrong numbers) and the raw response is logged so
it can be fixed quickly.

**Is it safe? Where are my tokens?**
Each account's OAuth tokens live in your macOS Keychain (service `claudemon`),
readable only by your user. They are never written to disk, never sent to the
device, and never shared with anything but Anthropic's own API. The ESP32 only
ever receives display strings ("PERSONAL", "63%", "WED 8PM").

**Will this mess with Claude Code's login?**
No. ClaudeMon never touches Claude Code's credential. That separation is
load-bearing: refresh tokens rotate on use, so two tools sharing one credential
would invalidate each other. Each ClaudeMon account is its own independent
grant.

**Does using ClaudeMon consume my usage?**
No — the usage endpoint reports the numbers; it doesn't run inference. Polling
is rate-limit-friendly (3-minute cadence with backoff).

**Can I run it on Linux/Windows?**
Not yet — the host tool uses the macOS Keychain and launchd. The polling and
serial code is portable; a `keyring`/systemd port is a welcome PR.

**Can I use a different display/board?**
Yes, with firmware work. The host↔device interface is a tiny documented
[serial JSON protocol](https://github.com/awizemann/ClaudeMon32/blob/main/docs/protocol.md);
reimplement the display side on your hardware and the host tool works unchanged.

**How many accounts?**
The display fits 4. The host will poll however many you log in; the 4
alphabetically-first are shown.

**The screen flashes black every so often — is it broken?**
No, that's the e-paper full refresh that prevents ghosting (every ~15 minutes).

**Why does my second login keep storing the first account?**
Browsers silently reuse the signed-in claude.ai session. Use a private/incognito
window for each additional account — `claudemon login` prints a reminder and
warns you when it detects a duplicate.
