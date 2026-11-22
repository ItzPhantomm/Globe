# Globe

A modular, lightweight, command-driven Discord framework built on top of discord.py-self. Designed for high performance, minimal resource usage, and local execution across Linux and mobile environments.

---

## Token Setup and Mobile Automation

Extracting your user credentials manually often requires browser inspection or desktop network monitoring. Globe includes an integrated terminal extraction script (`ext_token.py`) built directly for mobile and headless environments.

### Quick Setup Steps

1. Run the local extractor:
   ```bash
   python ext_token.py
   ```
2. Enter your account credentials via the interactive prompt.
3. If Multi-Factor Authentication (MFA) is active on your account, the tool prompts for your TOTP or SMS verification code, with support for backup codes.
4. Your token is verified locally and saved to `.env` and `token.txt` for immediate startup.

---

## Architecture Overview

Globe separates functionality into clean, decoupled modules without command duplication:

- **utility**: General administrative utilities, profile and asset inspection, contextual text translation, permission verification, local analytics, message caching, and token management.
- **moderation**: Server administrative tooling including message purging, role assignments, timeout handling, channel controls, and webhook configuration.
- **tools**: Operational utilities such as automated response rules, network inspection, URL metadata parsing, and server invite analytics.
- **troll**: Text styling, interactive prompts, and client-side testing routines.
- **fun**: General social utilities, math routines, and random selection tools.
- **status**: Presence management with custom activity support and persistent runtime status.
- **voice**: Channel connection diagnostics and audio state inspection.

---

## Installation

```bash
# Clone the repository
git clone https://github.com/ItzPhantomm/Globe.git
cd Globe

# Install Python requirements
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env

# Start Globe
python main.py
```

---

## Privacy and Architecture

We value your privacy. Globe is fully open source under the MIT License, allowing community review, modifications, and forks. The application operates entirely locally on your host environment—no external telemetry, analytics, or third-party servers are used. All credentials, messages, and configurations remain strictly on your machine.
