# Hermes

> Google Flow session token extractor & auto-reporter, powered by Camoufox.

Hermes automates the full lifecycle of Google Flow account credentials — from first login to periodic token refresh — and reports session tokens to a [Flow2API](https://github.com/TheSmallHanCat/flow2api) backend without any manual intervention.

---

## Features

- **Persistent login** — saves full browser state (including `HttpOnly` cookies) via Playwright storage state; no re-login needed across runs
- **Flow mode** — navigates to Google Flow, clicks the sign-in button, waits for `__Secure-next-auth.session-token`, and POSTs it to your Flow2API instance automatically
- **Multi-account support** — manage multiple Google accounts under `accounts/`, run them in batch
- **Anti-detect browser** — built on [Camoufox](https://camoufox.com), a hardened Firefox fork with fingerprint rotation

---

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- A running [Flow2API](https://github.com/TheSmallHanCat/flow2api) instance

```bash
uv add camoufox requests
uv run -m camoufox fetch
```

---

## Usage

### 1. First-time login

Opens a browser window. Sign in to Google manually, then press Enter to save.

```bash
uv run main.py --login <account-name>
# e.g. uv run main.py --login work
```

Credentials are saved to `accounts/<account-name>.json`.

### 2. Load a saved account

```bash
uv run main.py --load work
uv run main.py --load work --url https://mail.google.com
uv run main.py --load work --headless --wait 30
```

### 3. Flow mode — extract & report token

```bash
uv run main.py --flow work --flow-api-key "admin:yourpassword" --flow-api https://example.com/api/plugin/update-token
```

Hermes will:
1. Load the saved account state
2. Navigate to `https://labs.google/fx/tools/flow`
3. Click the Google sign-in button
4. Poll until `__Secure-next-auth.session-token` appears
5. Authenticate against your Flow2API admin endpoint
6. Retrieve the `connection_token` from plugin config
7. POST the session token to `/api/plugin/update-token`

### 4. Batch & utilities

```bash
# Run all saved accounts sequentially
uv run main.py --load-all --headless

# List saved accounts
uv run main.py --list
```

---

## CLI Reference

| Argument | Description |
|---|---|
| `--login NAME` | First-time login, saves browser state |
| `--load NAME` | Load a saved account |
| `--load-all` | Load all accounts sequentially |
| `--list` | List all saved accounts |
| `--url URL` | Target URL for `--load` (default: myaccount.google.com) |
| `--headless` | Run browser in headless mode |
| `--wait N` | Close browser after N seconds |
| `--flow NAME` | Flow mode: extract & report session token |
| `--flow-api URL` | Flow2API endpoint (default: `https://example.com/api/plugin/update-token`) |
| `--flow-api-key USER:PASS` | Flow2API admin credentials |

---

## Project Structure

```
hermes/
├── main.py           # Entry point
├── accounts/         # Saved browser states (gitignored)
│   ├── work.json
│   └── work_cookies_debug.json
└── README.md
```

> **Security:** `accounts/` contains live session credentials. Add it to `.gitignore` and never commit it.

```gitignore
accounts/
```

---

## How it works

Google's core authentication cookies (`SID`, `SSID`, `SAPISID`, `__Secure-1PSIDTS`, etc.) are all `HttpOnly` and invisible to JavaScript. Userscripts and browser extensions can only capture a subset of cookies. Hermes runs the full browser via Playwright, which operates at the network level and captures all cookies — including `HttpOnly` ones — through `context.storage_state()`.

The Flow mode targets `__Secure-next-auth.session-token`, a NextAuth.js session cookie set by Google Labs after OAuth completion. This token is what Flow2API uses to authenticate against the Veo generation API.

---

## License

MIT