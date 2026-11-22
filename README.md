# 🌐 Globe — All-in-One Discord Selfbot

A modular, clean, command-driven Discord selfbot built with `discord.py-self`.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env and add your DISCORD_TOKEN

# 3. Run
python main.py
```

## Commands (prefix: `g.`)

### 📦 General
| Command | Aliases | Description |
|---------|---------|-------------|
| `g.ping` | `g.p` | WebSocket latency |
| `g.uptime` | `g.up` | How long Globe has been running |
| `g.about` | `g.info`, `g.globe` | Globe stats |
| `g.help [module]` | `g.h`, `g.cmds` | List all commands |
| `g.modules` | `g.mods` | List loaded modules |
| `g.reload <module>` | `g.rl` | Hot-reload a module |

### 🔤 Utility
| Command | Aliases | Description |
|---------|---------|-------------|
| `g.say <text>` | `g.s`, `g.echo` | Re-send text (deletes your message) |
| `g.mock <text>` | — | AlTeRnAtInG cAsE |
| `g.reverse <text>` | `g.rev` | Reverse text |
| `g.clap <text>` | — | Add 👏 between words |
| `g.uwu <text>` | — | UwU-ify text |
| `g.big <text>` | — | Regional indicator emoji letters |
| `g.upper <text>` | `g.uc` | UPPERCASE |
| `g.lower <text>` | `g.lc` | lowercase |
| `g.charcount <text>` | `g.cc`, `g.chars` | Count characters |
| `g.wordcount <text>` | `g.wc`, `g.words` | Count words |
| `g.rand [low] [high]` | `g.rng` | Random number |
| `g.choose <a, b, c>` | `g.pick` | Pick from options |
| `g.copy <msg_id>` | — | Copy a message by ID |

### 📊 Info
| Command | Aliases | Description |
|---------|---------|-------------|
| `g.userinfo [@user]` | `g.ui`, `g.whois` | User info |
| `g.serverinfo` | `g.si`, `g.guild` | Server info |
| `g.roleinfo <role>` | `g.ri` | Role info |
| `g.channelinfo [#ch]` | `g.ci` | Channel info |
| `g.avatar [@user]` | `g.av`, `g.pfp` | Avatar URL |
| `g.id [@user]` | — | User ID |
| `g.membercount` | `g.mc`, `g.members` | Member count |

### 🎉 Fun
| Command | Aliases | Description |
|---------|---------|-------------|
| `g.8ball <question>` | `g.8b` | Magic 8-ball |
| `g.roast [user]` | `g.burn` | Roast someone |
| `g.compliment [user]` | `g.comp` | Compliment someone |
| `g.rate <thing>` | — | Rate something /10 |
| `g.ship <a> <b>` | — | Ship two people |
| `g.coinflip` | `g.coin`, `g.flip` | Flip a coin |
| `g.dice [sides]` | `g.roll`, `g.d` | Roll dice |
| `g.pp [user]` | `g.ppsize` | pp size 😳 |

### 🗑️ Purge
| Command | Aliases | Description |
|---------|---------|-------------|
| `g.selfpurge [n]` | `g.sp`, `g.cleanup` | Delete your last N msgs |
| `g.purge [n]` | `g.clear`, `g.del` | Bulk delete N msgs (Manage Messages) |
| `g.nuke` | — | Delete ALL your messages (owner, confirms) |

### 👻 Snipe
| Command | Aliases | Description |
|---------|---------|-------------|
| `g.snipe` | `g.sn` | Snipe last deleted message |
| `g.esnipe` | `g.es`, `g.editsnipe` | Snipe last edited message |
| `g.clearsnipe` | `g.cs` | Clear snipe cache |

### 💤 AFK
| Command | Description |
|---------|-------------|
| `g.afk [reason]` | Go AFK — auto-reply when mentioned |
| `g.unafk` | Come back from AFK |

### ⚡ Automation
| Command | Aliases | Description |
|---------|---------|-------------|
| `g.autoreact [emojis]` | `g.react` | Auto-react in channel (blank = clear) |
| `g.autoreply <trigger> <response>` | `g.arp` | Auto-reply on keyword |
| `g.stopar` | `g.clearar` | Clear all auto-reply rules |
| `g.listar` | `g.showar` | List active auto-reply rules |

### 🛠️ Tools
| Command | Aliases | Description |
|---------|---------|-------------|
| `g.remind <dur> <text>` | `g.remindme` | Set a reminder (`5m`, `2h`, `1d`) |
| `g.timestamp` | `g.ts`, `g.time` | Current Unix timestamp |
| `g.b64 <encode/decode> <text>` | `g.base64` | Base64 encode/decode |
| `g.hash <algo> <text>` | — | Hash text (md5/sha1/sha256/sha512) |
| `g.rot13 <text>` | — | ROT13 encode/decode |
| `g.urban <term>` | `g.ud`, `g.define` | Urban Dictionary lookup |
| `g.weather <location>` | `g.w`, `g.wttr` | Weather via wttr.in |

### 🔊 Voice
| Command | Aliases | Description |
|---------|---------|-------------|
| `g.voiceinfo` | `g.vi`, `g.vc` | Your current voice channel |
| `g.vclist` | `g.vcs` | All voice channels + occupancy |
| `g.vckick <@user>` | — | Disconnect a user from VC |

### 🎁 Nitro
| Command | Aliases | Description |
|---------|---------|-------------|
| `g.sniper` | `g.ns` | Toggle nitro sniper (owner only) |

## Project Structure

```
Globe/
├── main.py                  # Entry point (python main.py)
├── auth_handlers.py         # Token validation & session management
├── footprint_handlers.py    # Anti-detection, delays, rate limiting
├── requirements.txt
├── .env.example
│
├── config/
│   ├── __init__.py
│   └── settings.py          # Pydantic settings from .env
│
├── core/
│   ├── __init__.py
│   ├── bot.py               # GlobeBot (discord.py-self)
│   └── loader.py            # Cog auto-loader
│
├── modules/                 # Feature modules (auto-loaded)
│   ├── general.py           # ping, help, about, reload
│   ├── utility.py           # say, mock, reverse, rand, choose…
│   ├── info.py              # userinfo, serverinfo, avatar…
│   ├── fun.py               # 8ball, roast, ship, rate…
│   ├── purge.py             # selfpurge, purge, nuke
│   ├── snipe.py             # snipe, esnipe
│   ├── afk.py               # afk, unafk
│   ├── automation.py        # autoreact, autoreply
│   ├── tools.py             # remind, b64, hash, weather…
│   ├── voice.py             # voiceinfo, vclist, vckick
│   └── nitro.py             # nitro sniper
│
├── ui/
│   ├── __init__.py
│   └── console.py           # Rich console output
│
└── test/
    ├── __init__.py
    ├── test_core.py         # Config, auth, footprint tests
    └── test_modules.py      # Module logic tests
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_TOKEN` | — | Your Discord user token (required) |
| `PREFIX` | `g.` | Command prefix |
| `OWNER_ID` | — | Your Discord user ID |
| `LOG_LEVEL` | `INFO` | Log verbosity |
| `TYPING_DELAY_MIN` | `300` | Min human typing delay (ms) |
| `TYPING_DELAY_MAX` | `1200` | Max human typing delay (ms) |
| `AUTO_DELETE_DELAY` | `0` | Auto-delete bot responses (s, 0=off) |
| `NITRO_SNIPER` | `false` | Enable nitro sniper |
| `AFK_MESSAGE` | *(default)* | AFK auto-reply text |

## Running Tests

```bash
pytest
```

---

> **Disclaimer:** Selfbots violate Discord's Terms of Service. Use at your own risk.
