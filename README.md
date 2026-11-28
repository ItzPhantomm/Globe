# Globe

Discord selfbot runtime built on `discord.py-self`, with an encrypted local token vault, SQLite message logs, and a browser dashboard.

Runs cleanly on Linux servers, Docker containers, and Android Termux.

---

## How it works

| Part | File | What it does |
|---|---|---|
| **Token vault** | `core/vault.py` | Encrypts your token on disk with AES-256-GCM (PBKDF2-HMAC-SHA256, 480k rounds). Plaintext stays in RAM only when unlocked via `--key`, `GLOBE_KEY`, or prompt. |
| **Web dashboard** | `web/` | Local `aiohttp` control panel + WebSocket log stream, protected by token login, HMAC-SHA256 cookies, and CSRF tokens. |
| **Local database** | `data/tracker.py` | SQLite WAL database storing message counts, a 500-row deleted-message snipe log, bookmarks, and saved feature toggles. |
| **Rate-limit pacing** | `footprint_handlers.py` | Adds human jitter and honors Discord HTTP 429 `Retry-After` windows. |
| **Updates & reload** | `main.py`, `modules/utility.py` | Optional `git pull` on boot plus in-memory cog reloading (`g.reload`, `g.update`). |

---

## Modules

Globe splits commands into **7 cogs**:

- **`utility`** — Core info and cleanup (`ping`, `about`, `update`, `restart`, `reload`, `vault`), AFK auto-replies with missed pings (`afk`, `unafk`, `afkpings`), 10-message snipe history (`snipe`, `esnipe`, `snipesearch`), bookmarks (`save`, `saved`), DM cleanup (`selfpurge`, `deletedm`, `exportchat`, `closedms`), and emoji stealing (`steal`, `stealall`).
- **`tools`** — Ghost-ping alerts (`radar`), user tracking (`stalk`, `stalklog`, `mutuals`, `activity`), friend list diffs (`friendsbackup`, `friendsdiff`, `acceptfriends`, `clearoutgoing`), keyword/webhook forwarding (`kw`, `alertwebhook`), vanity monitoring (`vanitywatch`), giveaways (`gsniper`), encoders (`morse`, `b64`, `hex`, `bin`), and network checks (`iplookup`, `dns`, `headers`, `linkinfo`, `invinfo`, `qr`).
- **`moderation`** — Permission audit (`auditperms`), top chatters (`topchatters`), server backups and cloning (`backupserver`, `cloneserver`), channel lockdowns (`lockdown`, `unlockdown`), purges (`purgelinks`, `purgebots`), and webhooks.
- **`status`** — HypeSquad, bio, custom status, status rotator, optional Globe Rich Presence (`globerpc on|off`), elapsed timer spoofing (`rpctime`), and game badge spoofer (`badgespoofer`).
- **`voice`** — 24/7 voice connection with auto-reconnect (`joinvc`, `leavevc`), user following (`vcfollow`), member moving (`vcmoveall`), and channel info (`voiceinfo`, `vclist`).
- **`troll`** — Channel mimicry (`mimic`, `unmimic`), auto-reactions (`reactspam`), ghost-pings, and flood controls.
- **`fun`** — Quick chat games and RNG helpers.

---

## Setup

```bash
git clone https://github.com/ItzPhantomm/Globe.git
cd Globe
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Encrypt your token and run

```bash
# Optional: extract token locally
python ext_token.py

# Encrypt the token inside .env with AES-256-GCM
python main.py --encrypt "<your-passphrase>"

# Start Globe (unlocks token only in RAM)
python main.py --key "<your-passphrase>"
```

CLI flags: `--token` / `-t`, `--prefix` / `-p`, `--key` / `-k` (`GLOBE_KEY`), `--encrypt`, `--debug` / `-d`.

### Web dashboard

By default, Globe serves the dashboard on `http://127.0.0.1:8787` (`DASHBOARD_ENABLED`, `DASHBOARD_HOST`, `DASHBOARD_PORT` in `.env`). Sign in with your Discord account token. To access it remotely, point a Cloudflare Tunnel (`cloudflared tunnel --url http://127.0.0.1:8787`) or SSH port forward at it.

---

## Tests

```bash
python3 -m pytest
```

Covers token vault encryption/decryption, auth cookies, CSRF checks, rate-limit lockouts, dashboard APIs, persistence, and duplicate-command checks across all 7 cogs.

---

## Privacy & storage

Everything runs on your own machine. No third-party servers receive your token or database; local `.env`, SQLite files, and server backups stay ignored by git. MIT License.
