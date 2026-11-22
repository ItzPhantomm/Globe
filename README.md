# 🌐 Globe — All-in-One Discord Selfbot

> `-` **Welcome to Globe! The most complete, lightweight, and modern all-in-one Discord selfbot.**
> Built with precision on `discord.py-self`, Globe gives you effortless control over your account with an ultra-clean block-quote UI, intelligent anti-detection footprint safeguards, and modular architecture.

---

### 🚀 Don't know how to extract your token? Don't worry, Globe makes this easier than ever!

> `—` **Zero PC Required · Mobile & Terminal First**
> Extracting your Discord token usually requires inspecting network requests or running scripts on a desktop browser. Globe ships with an automated, native token extraction engine (`ext_token.py`) that works directly from your phone (Termux) or server terminal.

> `—` **Step-by-Step Instant Extraction:**
> 1. Launch the standalone extractor:
>    ```bash
>    python ext_token.py
>    ```
> 2. Enter your Discord **Email** and **Password**.
> 3. Globe emulates a native Android Discord client handshake.
> 4. If your account has MFA enabled, Globe automatically detects your authenticator app (TOTP) or SMS and prompts for the code. Backup codes are supported out of the box.
> 5. Your token is verified against the Discord API, displayed, and automatically archived into your `token.txt` and `.env` files for immediate use.

---

### 📦 Modular Architecture

Globe organizes its extensive feature set into seven focused modules. No cluttered commands or fragmented cogs — everything runs under clean, hot-reloadable namespaces:

> `•` `utility`
> The core command and control center. Houses presence auditing, asset extraction, multi-lingual contextual translation (including Romanized Hinglish), permissions diagnostic suites, message analytics, snipe engines, token banking, and the paginated help system.

> `•` `moderation`
> Complete administrative suite for servers you manage. Features high-speed bulk purge tools, kick/ban/unban workflows, timeout enforcement, nickname locking, and full lifecycle managers for channels, roles, and webhooks.

> `•` `tools`
> Advanced practical utilities. Includes real-time Nitro sniper, channel automation rules (auto-react, auto-reply), network OSINT (deep URL link analysis, IP lookup, DNS inspection), and deep Discord invite/guild intelligence.

> `•` `troll`
> Micro-interactions and playful trolling utilities. Built with ghost-pings, flood and mass mention generators, fake terminal execution animations, and background typing simulators.

> `•` `fun`
> Casual games and social commands. Includes classic 8-ball, randomized roasts, compliments, coin flips, dice rolls, ship compatibility calculators, and rating generators.

> `•` `status`
> Full Rich Presence control. Broadcasts custom streaming, playing, listening, or watching states, featuring the official default Globe Rich Presence with live runtime counters, high-resolution media proxy assets, and interactive profile buttons.

> `•` `voice`
> Voice channel management and diagnostics. Inspects active voice states, member lists, and provides quick voice disconnection utilities.

---

### ⚡ Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/ItzPhantomm/Globe.git
cd Globe

# 2. Install dependencies
pip install -r requirements.txt

# 3. Setup Token (or run python ext_token.py)
cp .env.example .env
# Add your DISCORD_TOKEN to .env

# 4. Start Globe
python main.py
```

---

> `°` **Globe** — Shaping Modern Selfbot Architecture. Minimal, Clean & Fast.
