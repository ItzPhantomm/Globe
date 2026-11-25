# Globe

**High-throughput asynchronous Discord client runtime, credential vault, and modular automation engine.**

Globe is an engineered Python runtime built on `discord.py-self`, designed for deterministic low-latency execution, minimal memory overhead, and zero-trust local credential storage across Linux servers, containers, and mobile Termux environments.

---

## Core Engineering

| Layer | Implementation | Purpose |
|---|---|---|
| **Credential Vault** | `core/vault.py` (`AES-256-GCM` + `PBKDF2-HMAC-SHA256`, 480k rounds) | Encrypts tokens on disk (`ENC:...`); plaintext exists strictly in volatile RAM via `--key` / `GLOBE_KEY` or masked `getpass` prompt. |
| **Telemetry & Forensics** | `data/tracker.py` (SQLite `WAL` + micro-batching) | Persistent message analytics, 500-row deleted-message forensics, bookmarks, and runtime `kv_state` with non-blocking batched commits. |
| **Network Diagnostics** | `modules/tools.py` (Connection-pooled `httpx.AsyncClient`) | Reuses TCP sockets and TLS sessions across IP/DNS/HTTP/OSINT lookups, webhook forwarding, and vanity monitoring. |
| **Rate-Limit Shield** | `footprint_handlers.py` | Adaptive bucket pacing, randomized human jitter, and automatic HTTP `429` `Retry-After` backoff. |
| **Hot-Reload Lifecycle** | `main.py` & `modules/utility.py` | Startup Git fast-forward updater, in-memory module hot-reloading (`g.update`, `g.reload`), and clean process restarts (`g.restart`). |

---

## Architecture & Modules

Globe decouples capabilities into **7 hot-reloadable cogs**:

- **`utility`** — Core lifecycle (`ping`, `about`, `update`, `restart`, `reload`, `vault`), Smart AFK digest (`afk`, `unafk`, `afkpings`), 10-deep attachment snipe (`snipe`, `esnipe`, `snipesearch`), bookmarks (`save`, `saved`), DM/channel management (`selfpurge`, `deletedm`, `exportchat`, `closedms`), and emoji cloning (`steal`, `stealall`).
- **`tools`** — Passive intelligence (`radar`, `stalk`, `stalklog`, `mutuals`, `activity`), relationship diffing (`friendsbackup`, `friendsdiff`, `acceptfriends`, `clearoutgoing`), global keyword & alert webhook forwarding (`kw`, `alertwebhook`), `vanitywatch`, `gsniper`, `schedule`, encoders (`morse`, `demorse`, `b64`, `hex`, `bin`), and network diagnostics (`iplookup`, `dns`, `headers`, `linkinfo`, `invinfo`, `qr`).
- **`moderation`** — Server permission security auditing (`auditperms`), channel analytics (`topchatters`), server snapshot & cloner (`backupserver`, `cloneserver`), lockdown controls (`lockdown`, `unlockdown`), targeted purges (`purgelinks`, `purgebots`), and webhook tooling.
- **`status`** — Presence controls (`hypesquad`, `bio`, `customstatus`, `statusrotate`), non-intrusive opt-in Rich Presence (`globerpc on|off`), and detectable game session telemetry (`badgespoofer`).
- **`voice`** — Persistent 24/7 voice stay with auto-reconnect (`joinvc`, `leavevc`), live target following (`vcfollow`), bulk member moves (`vcmoveall`), and channel diagnostics (`voiceinfo`, `vclist`).
- **`troll`** — Channel mimicry (`mimic`, `unmimic`), reaction targeting (`reactspam`), ghost-pings, and paced flood controls.
- **`fun`** — Lightweight deterministic social and RNG utilities.

---

## Quickstart

```bash
git clone https://github.com/ItzPhantomm/Globe.git
cd Globe
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Credential Encryption & Launch

```bash
# 1. (Optional) Extract token on headless/mobile environments
python ext_token.py

# 2. Encrypt your stored token in .env with AES-256-GCM
python main.py --encrypt "<your-passphrase>"

# 3. Launch Globe (unlocks token strictly in RAM)
python main.py --key "<your-passphrase>"
```

Supported CLI flags: `--token` / `-t`, `--prefix` / `-p`, `--key` / `-k` (`GLOBE_KEY`), `--encrypt`, `--debug` / `-d`.

---

## Verification

```bash
pytest
```

Automated unit tests cover authentication, AES-256-GCM vault roundtrips, encoding/translation logic, SQLite forensics/bookmarks persistence, and cross-cog command/alias collision checks.

---

## Security & Local-First Guarantee

Globe operates exclusively on your host environment with zero third-party telemetry servers. Credentials, SQLite state, and server snapshots remain strictly local under `.gitignore` isolation. Licensed under the MIT License.
