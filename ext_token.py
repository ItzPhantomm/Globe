"""
Globe — Mobile Token Extractor (ext_token.py)
Allows users on mobile (Termux/Android/iOS) or without a desktop DevTools console
to authenticate via email & password and retrieve their Discord user token.

Features:
- Automated Discord API v9 authentication handshake
- Realistic Discord mobile client fingerprint spoofing (super-properties)
- Comprehensive MFA challenge negotiation:
    1. Authenticator / TOTP code challenge
    2. SMS / backup codes fallback
    3. Passkey detection & graceful stoppage
- CLI terminal interactive mode (masked input, rich console UI)
- Programmatic async Python API for Discord in-chat command integration
"""

from __future__ import annotations

import asyncio
import base64
import getpass
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable, Awaitable

import httpx
from dotenv import set_key

from ui import console, log_info, log_warn, log_err

DISCORD_LOGIN_API = "https://discord.com/api/v9/auth/login"
DISCORD_MFA_TOTP_API = "https://discord.com/api/v9/auth/mfa/totp"
DISCORD_MFA_SMS_API = "https://discord.com/api/v9/auth/mfa/sms"
ENV_PATH = Path(".env")

# Mobile client fingerprint properties (Discord Android stable)
MOBILE_SUPER_PROPERTIES = {
    "os": "Android",
    "browser": "Discord Android",
    "device": "Pixel 7 Pro",
    "system_locale": "en-US",
    "client_version": "225.17 - rn",
    "release_channel": "googleRelease",
    "device_vendor_id": "8fbbce30-bf52-44ec-9429-546beef21870",
    "browser_user_agent": "",
    "browser_version": "",
    "os_version": "34",
    "client_build_number": 225017,
    "client_event_source": None,
}

ENCODED_SUPER_PROPERTIES = base64.b64encode(json.dumps(MOBILE_SUPER_PROPERTIES).encode()).decode()

DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Discord-Android/225017; Mozilla/5.0 (Linux; Android 14; Pixel 7 Pro Build/UQ1A.240205.004; wv)",
    "X-Super-Properties": ENCODED_SUPER_PROPERTIES,
    "X-Discord-Locale": "en-US",
    "Accept-Language": "en-US",
}


@dataclass
class TokenExtractionResult:
    success: bool
    token: Optional[str] = None
    user_id: Optional[str] = None
    error: Optional[str] = None
    requires_passkey_only: bool = False


class TokenExtractor:
    """Manages the full automated Discord authentication and multi-step MFA challenge pipeline."""

    def __init__(self) -> None:
        self.headers = dict(DEFAULT_HEADERS)

    async def authenticate(
        self,
        login: str,
        password: str,
        mfa_prompt: Optional[Callable[[str], Awaitable[str]]] = None,
    ) -> TokenExtractionResult:
        """
        Authenticate with Discord using email/phone and password.
        Handles TOTP, SMS, and Backup Codes seamlessly.
        """
        payload = {
            "login": login.strip(),
            "password": password,
            "undelete": False,
            "login_source": None,
            "gift_code_sku_id": None,
        }

        async with httpx.AsyncClient(headers=self.headers, timeout=12.0) as client:
            try:
                resp = await client.post(DISCORD_LOGIN_API, json=payload)
                data = resp.json()
            except Exception as e:
                return TokenExtractionResult(success=False, error=f"Network error: {e}")

            # 1. Direct login success (No 2FA active)
            if resp.status_code == 200 and "token" in data:
                token = data["token"]
                user_id = data.get("user_id")
                return TokenExtractionResult(success=True, token=token, user_id=user_id)

            # 2. MFA / Two-Factor Authentication Triggered
            if resp.status_code == 200 and data.get("mfa") is True:
                ticket = data.get("ticket")
                totp = data.get("totp", False)
                sms = data.get("sms", False)
                backup = data.get("backup", False)
                webauthn = data.get("webauthn", False)

                if not ticket:
                    return TokenExtractionResult(success=False, error="Received MFA challenge without a valid ticket.")

                # Evaluation order: Authenticator/TOTP -> SMS / Backup -> Passkey
                if totp:
                    prompt_msg = "🔑 2FA Authenticator enabled: Enter your 6-digit Authenticator App code:"
                elif sms:
                    prompt_msg = "📱 SMS 2FA enabled: Enter the SMS verification code sent to your phone:"
                elif backup:
                    prompt_msg = "🛡️ Backup codes available: Enter your 8-digit Discord backup code:"
                elif webauthn and not (totp or sms or backup):
                    return TokenExtractionResult(
                        success=False,
                        requires_passkey_only=True,
                        error="Security Passkey (WebAuthn/FIDO2) is the only active MFA method on this account. Automated extraction cannot bypass physical hardware security keys.",
                    )
                else:
                    prompt_msg = "🔒 2FA verification required: Enter your Authenticator, SMS, or Backup code:"

                # Request code from callback or stdin
                if mfa_prompt:
                    code = await mfa_prompt(prompt_msg)
                else:
                    code = input(f"\n{prompt_msg} ").strip()

                if not code:
                    return TokenExtractionResult(success=False, error="No 2FA code provided.")

                # Clean input (remove spaces/dashes)
                clean_code = code.replace(" ", "").replace("-", "")

                # Attempt TOTP / Backup code resolution
                mfa_payload = {"code": clean_code, "ticket": ticket, "login_source": None}
                try:
                    mfa_resp = await client.post(DISCORD_MFA_TOTP_API, json=mfa_payload)
                    mfa_data = mfa_resp.json()
                except Exception as e:
                    return TokenExtractionResult(success=False, error=f"Failed to submit 2FA code: {e}")

                if mfa_resp.status_code == 200 and "token" in mfa_data:
                    return TokenExtractionResult(
                        success=True,
                        token=mfa_data["token"],
                        user_id=mfa_data.get("user_id"),
                    )

                # If TOTP failed and SMS is available, attempt SMS endpoint
                if sms and mfa_resp.status_code != 200:
                    try:
                        sms_resp = await client.post(DISCORD_MFA_SMS_API, json=mfa_payload)
                        sms_data = sms_resp.json()
                        if sms_resp.status_code == 200 and "token" in sms_data:
                            return TokenExtractionResult(
                                success=True,
                                token=sms_data["token"],
                                user_id=sms_data.get("user_id"),
                            )
                    except Exception:
                        pass

                err_msg = mfa_data.get("message", "Invalid 2FA or backup code.")
                return TokenExtractionResult(success=False, error=f"2FA verification failed: {err_msg}")

            # 3. Handle errors (Bad credentials, Captcha, Suspended)
            message = data.get("message", "Unknown authentication error.")
            errors = data.get("errors", {})
            if "login" in errors:
                message = "Account does not exist or invalid email/phone."
            elif "password" in errors:
                message = "Incorrect password."
            elif data.get("captcha_key"):
                message = "Discord required Cloudflare / hCaptcha verification. Please login in a mobile browser once to clear captcha."

            return TokenExtractionResult(success=False, error=f"{message} (HTTP {resp.status_code})")


# ── Interactive Terminal CLI ──────────────────────────────────────────────────

async def _cli_main() -> None:
    from ui import banner
    banner()
    console.print("[globe.brand]Discord Mobile Token Extractor[/] · [globe.muted]No PC required[/]\n")

    email = input("  Email or Phone Number › ").strip()
    if not email:
        log_err("Login identifier cannot be empty.")
        return

    password = getpass.getpass("  Password › ").strip()
    if not password:
        log_err("Password cannot be empty.")
        return

    log_info("Contacting Discord authentication gateway via Android client spoofing…")

    extractor = TokenExtractor()
    result = await extractor.authenticate(email, password)

    if result.success and result.token:
        masked = result.token[:6] + "●" * 16 + result.token[-4:]
        console.print(f"\n[bold bright_green]✅ Successfully Authenticated![/]")
        console.print(f"  [globe.muted]User ID:[/]  [bold white]{result.user_id or 'Extracted'}[/]")
        console.print(f"  [globe.muted]Token:[/]    [bold cyan]{result.token}[/]")
        console.print(f"  [globe.muted]Masked:[/]   [dim]{masked}[/]\n")

        save_choice = input("  Save token to .env and token.txt for Globe? (y/n) [y] › ").strip().lower()
        if save_choice in ("", "y", "yes"):
            if not ENV_PATH.exists():
                ENV_PATH.write_text("")
            set_key(str(ENV_PATH), "DISCORD_TOKEN", result.token)

            # Also persist in token.txt for multi-account archive
            token_file = Path("token.txt")
            existing = [l.strip() for l in token_file.read_text().splitlines()] if token_file.exists() else []
            if result.token not in existing:
                with open(token_file, "a", encoding="utf-8") as f:
                    f.write(f"{result.token}\n")

            log_info("Token written directly to .env and token.txt. Ready for 'python main.py'!")
    else:
        if result.requires_passkey_only:
            log_err(f"Passkey Block: {result.error}")
        else:
            log_err(f"Authentication Failed: {result.error}")


if __name__ == "__main__":
    try:
        asyncio.run(_cli_main())
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)
