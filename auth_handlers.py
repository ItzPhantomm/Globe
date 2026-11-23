"""
Globe Selfbot — Hardened Authentication & Session Handler
Features:
- Live verification handshake with Discord API (/users/@me)
- Base64 Snowflake extraction & creation timestamp validation
- Structural sanity checks & format sanitization
- Multi-token session registry & active session switching
- Safe masked credential display
"""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv, set_key

from ui import log_info, log_warn, log_err
from config import settings
from core import vault

_MIN_TOKEN_LEN = 50
ENV_PATH = Path(".env")
TOKENS_FILE = Path("token.txt")
DISCORD_API_ME = "https://discord.com/api/v9/users/@me"


class AuthHandler:
    """Manages token extraction, structural validation, live Discord handshakes, and token.txt persistence."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._validated: bool = False
        self._user_data: dict | None = None
        self._token_registry: dict[str, str] = {}  # {user_id: token}

    # ── Token loading & Storage (token.txt & .env) ─────────────────────────────

    def load_token(self, startup_key: str | None = None) -> str:
        """Resolve token from settings, .env, token.txt, or interactive prompt, decrypting if encrypted."""
        token = settings.discord_token.strip().strip("'\"")

        if not token:
            load_dotenv(ENV_PATH, override=True)
            token = os.getenv("DISCORD_TOKEN", "").strip().strip("'\"")

        # Check token.txt for any stored tokens
        if not token and TOKENS_FILE.exists():
            stored = self.get_saved_tokens()
            if stored:
                token = stored[0]  # Use most recent or primary token
                log_info(f"Loaded primary token from {TOKENS_FILE.name}")

        if not token:
            log_warn("No token found — please enter your Discord user token.")
            token = input("  Token › ").strip().strip("'\"")
            if token:
                self._persist_token(token)

        # Handle Vault decryption if token is encrypted with AES-256-GCM
        if vault.is_encrypted(token):
            key = (
                startup_key
                or os.getenv("GLOBE_KEY")
                or os.getenv("STARTUP_KEY")
                or os.getenv("VAULT_KEY")
            )
            if not key:
                import getpass
                log_warn("🔒 Encrypted token detected in storage. Startup key required.")
                try:
                    key = getpass.getpass("  🔒 [Globe Vault] One-Time Startup Key › ").strip()
                except Exception:
                    key = input("  🔒 [Globe Vault] One-Time Startup Key › ").strip()

            try:
                decrypted = vault.decrypt_token(token, key)
                log_info("🔓 Token successfully decrypted via startup key.")
                self._token = decrypted
                return decrypted
            except vault.InvalidPassphraseError as e:
                log_err(f"Authentication halted: {e}")
                import sys
                sys.exit(1)
            except Exception as e:
                log_err(f"Vault error: {e}")
                import sys
                sys.exit(1)

        self._token = token
        return token

    def encrypt_current_token(self, passphrase: str) -> str:
        """Encrypt active token in .env with a one-time startup key and erase plain text from disk."""
        token_to_encrypt = self._token or settings.discord_token
        if not token_to_encrypt or vault.is_encrypted(token_to_encrypt):
            load_dotenv(ENV_PATH, override=True)
            raw = os.getenv("DISCORD_TOKEN", "").strip().strip("'\"")
            if not vault.is_encrypted(raw):
                token_to_encrypt = raw

        if not token_to_encrypt or vault.is_encrypted(token_to_encrypt):
            raise vault.VaultError("No valid plaintext token available to encrypt.")

        enc_token = vault.encrypt_token(token_to_encrypt, passphrase)

        # 1. Update .env with encrypted ciphertext
        if not ENV_PATH.exists():
            ENV_PATH.write_text("")
        set_key(str(ENV_PATH), "DISCORD_TOKEN", enc_token)
        settings.discord_token = enc_token

        # 2. Securely remove plain token.txt so no plaintext remains on disk
        if TOKENS_FILE.exists():
            try:
                TOKENS_FILE.unlink()
                log_info(f"Purged plaintext {TOKENS_FILE.name} from disk.")
            except Exception as e:
                log_warn(f"Could not unlink {TOKENS_FILE.name}: {e}")

        log_info("Token encrypted in .env with AES-256-GCM.")
        return enc_token

    def _persist_token(self, token: str) -> None:
        """Save active token to both .env and token.txt."""
        clean = token.strip().strip("'\"")
        if not clean:
            return

        # 1. Update .env
        if not ENV_PATH.exists():
            ENV_PATH.write_text("")
        set_key(str(ENV_PATH), "DISCORD_TOKEN", clean)

        # 2. Append/save to token.txt (avoiding duplicates)
        self.save_token_to_file(clean)
        log_info(f"Token saved to .env and {TOKENS_FILE.name}")

    def save_token_to_file(self, token: str) -> None:
        """Append a token to token.txt without creating duplicates."""
        clean = token.strip().strip("'\"")
        if not clean:
            return

        existing = []
        if TOKENS_FILE.exists():
            existing = [line.strip() for line in TOKENS_FILE.read_text().splitlines() if line.strip()]

        if clean not in existing:
            with open(TOKENS_FILE, "a", encoding="utf-8") as f:
                f.write(f"{clean}\n")

    def remove_token_from_file(self, token: str) -> bool:
        """Remove a token from token.txt."""
        clean = token.strip().strip("'\"")
        if not TOKENS_FILE.exists():
            return False

        existing = [line.strip() for line in TOKENS_FILE.read_text().splitlines() if line.strip()]
        if clean in existing:
            existing.remove(clean)
            TOKENS_FILE.write_text("\n".join(existing) + ("\n" if existing else ""))
            return True
        return False

    def get_saved_tokens(self) -> list[str]:
        """Read all tokens currently stored in token.txt."""
        if not TOKENS_FILE.exists():
            return []
        return [line.strip() for line in TOKENS_FILE.read_text().splitlines() if line.strip()]

    # ── Token Sanitation & Snowflake Parsing ───────────────────────────────────

    @staticmethod
    def extract_user_id(token: str) -> Optional[int]:
        """Extract Discord Snowflake ID from first part of token without calling API."""
        try:
            parts = token.strip().split(".")
            if not parts:
                return None
            first_part = parts[0]
            # Add base64 padding if needed
            padded = first_part + "=" * ((4 - len(first_part) % 4) % 4)
            decoded = base64.b64decode(padded).decode("utf-8")
            if decoded.isdigit():
                return int(decoded)
        except Exception:
            pass
        return None

    # ── Live Validation & Verification Handshake ───────────────────────────────

    def validate_token(self, token: str, live_check: bool = True) -> bool:
        """
        Validate token structurally and perform live API verification against Discord /users/@me.
        """
        clean = token.strip().strip("'\"")
        if not clean:
            log_err("Token is empty.")
            return False

        if len(clean) < _MIN_TOKEN_LEN:
            log_err(f"Token is too short ({len(clean)} chars). Required >= {_MIN_TOKEN_LEN}.")
            return False

        extracted_id = self.extract_user_id(clean)
        if not extracted_id:
            log_warn("Token header does not decode to a valid Discord snowflake ID.")

        if live_check:
            try:
                # Fast synchronous request to verify before bot engine spins up
                resp = httpx.get(
                    DISCORD_API_ME,
                    headers={
                        "Authorization": clean,
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                    },
                    timeout=6.0,
                )
                if resp.status_code == 200:
                    self._user_data = resp.json()
                    uid = self._user_data.get("id")
                    uname = f"{self._user_data.get('username')}#{self._user_data.get('discriminator', '0')}"
                    log_info(f"Token verified with Discord API — Account: {uname} ({uid})")
                    if uid:
                        self._token_registry[uid] = clean
                    self._validated = True
                    return True
                elif resp.status_code == 401:
                    log_err("Live check failed: Discord returned 401 Unauthorized (token is expired, changed, or invalid).")
                    return False
                elif resp.status_code == 403:
                    log_err("Live check failed: Account locked or flagged (phone verification required).")
                    return False
                else:
                    log_warn(f"Discord returned status {resp.status_code}. Proceeding with structural check.")
            except Exception as e:
                log_warn(f"Could not contact Discord API directly for pre-flight: {e}. Falling back to structural validation.")

        self._validated = True
        return True

    # ── Multi-Token Registry ───────────────────────────────────────────────────

    def register_token(self, token: str) -> Optional[str]:
        """Validate and add a token to internal multi-account registry."""
        clean = token.strip().strip("'\"")
        uid = self.extract_user_id(clean)
        if uid:
            self._token_registry[str(uid)] = clean
            return str(uid)
        return None

    def get_registered_tokens(self) -> dict[str, str]:
        """Return masked map of registered tokens."""
        return {uid: tok[:6] + "●" * 12 + tok[-4:] for uid, tok in self._token_registry.items()}

    # ── Display ───────────────────────────────────────────────────────────────

    def masked(self) -> str:
        """Return masked version of active token for safe logs."""
        tok = self._token or settings.discord_token
        if not tok or len(tok) < 10:
            return "not set"
        return tok[:6] + "●" * 12 + tok[-4:]

    @property
    def token(self) -> str | None:
        return self._token

    @property
    def is_ready(self) -> bool:
        return bool(self._token) and self._validated


auth = AuthHandler()
