"""
Symmetric encryption for broker API credentials at rest.

Alpaca API keys are bearer credentials: whoever holds the pair can move real
money in that account. They must never be stored in plaintext in the SQLite
file, which is a single unencrypted file sitting on a Docker volume.

Key management
--------------
BROKER_ENCRYPTION_KEY must be a urlsafe-base64 32-byte Fernet key. Generate one
with:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

This key is deliberately SEPARATE from SECRET_KEY (the JWT signing key). Rotating
JWTs is harmless; rotating this key orphans every stored credential and forces
every user to re-link their brokerage. Keeping them separate means you can rotate
one without destroying the other.

Fail-closed policy
------------------
If BROKER_ENCRYPTION_KEY is unset, this module does NOT fall back to plaintext or
to a generated ephemeral key. Storing credentials becomes impossible and raises
CredentialEncryptionUnavailable. A trading app that silently degrades to
plaintext key storage is worse than one that refuses to store keys at all.
"""

import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


class CredentialEncryptionUnavailable(RuntimeError):
    """Raised when credential encryption is requested but no key is configured."""


class CredentialDecryptionError(RuntimeError):
    """Raised when stored ciphertext cannot be decrypted with the current key."""


_ENV_VAR = "BROKER_ENCRYPTION_KEY"
_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

    raw = os.getenv(_ENV_VAR)
    if not raw:
        raise CredentialEncryptionUnavailable(
            f"{_ENV_VAR} is not set. Broker credentials cannot be stored or read. "
            f"Generate one with: python -c \"from cryptography.fernet import Fernet; "
            f"print(Fernet.generate_key().decode())\""
        )

    try:
        _fernet = Fernet(raw.encode() if isinstance(raw, str) else raw)
    except (ValueError, TypeError) as exc:
        raise CredentialEncryptionUnavailable(
            f"{_ENV_VAR} is not a valid Fernet key (expected urlsafe-base64 32 bytes): {exc}"
        ) from exc

    return _fernet


def encryption_available() -> bool:
    """True if credentials can be encrypted/decrypted. Used for health checks and
    for showing a useful error in the UI before the user types their keys in."""
    try:
        _get_fernet()
        return True
    except CredentialEncryptionUnavailable:
        return False


def encrypt(plaintext: str) -> str:
    """Encrypt a credential. Returns urlsafe-base64 ciphertext safe for a TEXT column."""
    if plaintext is None:
        raise ValueError("Cannot encrypt None")
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a stored credential.

    Raises CredentialDecryptionError if the key has been rotated or the row is
    corrupt — callers should treat this as "this user's link is broken, make them
    re-link" rather than crashing the request.
    """
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise CredentialDecryptionError(
            "Stored broker credential could not be decrypted. The encryption key may "
            "have changed since it was saved; the user must re-link their account."
        ) from exc


def reset_cache() -> None:
    """Drop the memoised Fernet. Only needed by tests that swap the env var."""
    global _fernet
    _fernet = None
