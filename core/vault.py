"""
Globe Selfbot — Military-Grade Encrypted Token Vault
Implements AES-256-GCM authenticated encryption with PBKDF2 HMAC-SHA256 key derivation.
Protects Discord tokens on un-trusted or remote VPS storage.
Tokens on disk exist strictly as encrypted ciphertext; decrypted only in-memory via one-time startup key.
"""

from __future__ import annotations

import base64
import os
from typing import Tuple

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


_SALT_LEN = 16
_NONCE_LEN = 12
_KDF_ITERATIONS = 480_000
_PREFIX = "ENC:"


class VaultError(Exception):
    """Base exception for Vault errors."""
    pass


class InvalidPassphraseError(VaultError):
    """Raised when the decryption passphrase or key is incorrect."""
    pass


def is_encrypted(token: str) -> bool:
    """Return True if the token string is encrypted with the Globe Vault."""
    if not isinstance(token, str):
        return False
    return token.strip().strip("'\"").startswith(_PREFIX)


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from passphrase and salt using PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_KDF_ITERATIONS,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt_token(raw_token: str, passphrase: str) -> str:
    """
    Encrypt a Discord token with AES-256-GCM using a user passphrase.
    Returns serialized ciphertext formatted as 'ENC:<base64(salt + nonce + ciphertext + tag)>'.
    """
    clean_token = raw_token.strip().strip("'\"")
    if not clean_token:
        raise VaultError("Cannot encrypt empty token.")
    if not passphrase:
        raise VaultError("Passphrase cannot be empty.")

    salt = os.urandom(_SALT_LEN)
    key = _derive_key(passphrase, salt)
    nonce = os.urandom(_NONCE_LEN)

    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, clean_token.encode("utf-8"), None)

    blob = salt + nonce + ciphertext
    encoded = base64.b64encode(blob).decode("utf-8")
    return f"{_PREFIX}{encoded}"


def decrypt_token(encrypted_token: str, passphrase: str) -> str:
    """
    Decrypt a Discord token from ciphertext using the user passphrase.
    Raises InvalidPassphraseError if authentication tag fails or passphrase is wrong.
    """
    clean_enc = encrypted_token.strip().strip("'\"")
    if not is_encrypted(clean_enc):
        return clean_enc
    if not passphrase:
        raise InvalidPassphraseError("A startup passphrase is required to decrypt this token.")

    payload = clean_enc[len(_PREFIX):]
    try:
        blob = base64.b64decode(payload)
    except Exception as e:
        raise VaultError(f"Corrupted encrypted token payload: {e}")

    if len(blob) < _SALT_LEN + _NONCE_LEN + 16:
        raise VaultError("Ciphertext payload is truncated or corrupted.")

    salt = blob[:_SALT_LEN]
    nonce = blob[_SALT_LEN:_SALT_LEN + _NONCE_LEN]
    ciphertext = blob[_SALT_LEN + _NONCE_LEN:]

    key = _derive_key(passphrase, salt)
    aesgcm = AESGCM(key)

    try:
        decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        return decrypted_bytes.decode("utf-8")
    except InvalidTag:
        raise InvalidPassphraseError("Decryption failed: Incorrect startup key or corrupted ciphertext.")
    except Exception as e:
        raise VaultError(f"Unexpected error during token decryption: {e}")
