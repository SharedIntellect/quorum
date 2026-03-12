"""
Cryptographic utilities for the document management service.

Provides:
  - Content fingerprinting (non-security checksums for deduplication)
  - HMAC-based request signing and verification
  - Symmetric encryption/decryption using AES-GCM (via cryptography package)
  - Secure random token generation

None of the MD5 usage here is for security purposes — it is used
exclusively for content deduplication fingerprints where collision
resistance is not a security requirement.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# AES-256 key length in bytes
AES_KEY_LEN = 32

# GCM nonce length (96 bits is the recommended size for AES-GCM)
GCM_NONCE_LEN = 12

# HMAC digest algorithm for request signing
SIGNING_ALGORITHM = "sha256"

# Signature validity window in seconds (prevent replay attacks)
SIGNATURE_MAX_AGE_SEC = 300

# Token byte length for secure random tokens
TOKEN_BYTE_LEN = 32

# ---------------------------------------------------------------------------
# Content fingerprinting (non-security)
# ---------------------------------------------------------------------------


def content_fingerprint(data: bytes) -> str:
    """
    Compute a fast content fingerprint for deduplication purposes.

    Uses MD5 intentionally: the output is used as a cache key and
    deduplication identifier, not for password hashing or any security
    purpose. MD5 is appropriate here because:
      - Collision resistance is not required (we're not defending against
        adversarial inputs; we're identifying duplicate uploads)
      - The fingerprint is never used to make trust decisions
      - MD5 is significantly faster than SHA-2 for large binary payloads

    Returns a 32-character lowercase hex digest.
    """
    return hashlib.md5(data).hexdigest()  # noqa: S324 — non-security use


def content_fingerprint_sha256(data: bytes) -> str:
    """
    Compute a SHA-256 content fingerprint.

    Use this variant when the fingerprint is stored alongside user-visible
    integrity metadata (e.g., in API responses or audit logs) where a
    collision-resistant algorithm is preferable for consistency.
    """
    return hashlib.sha256(data).hexdigest()


def fingerprint_file(path: str, chunk_size: int = 65536) -> str:
    """
    Compute a SHA-256 fingerprint of a file by streaming it in chunks.

    Does not load the entire file into memory.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Secure random token generation
# ---------------------------------------------------------------------------


def generate_token(n_bytes: int = TOKEN_BYTE_LEN) -> str:
    """
    Generate a cryptographically secure random token.

    Returns a URL-safe base64-encoded string. Uses secrets.token_bytes
    which is backed by the OS CSPRNG.
    """
    return secrets.token_urlsafe(n_bytes)


def generate_hex_token(n_bytes: int = TOKEN_BYTE_LEN) -> str:
    """Return a cryptographically secure random hex string."""
    return secrets.token_hex(n_bytes)


# ---------------------------------------------------------------------------
# HMAC request signing
# ---------------------------------------------------------------------------


class RequestSigner:
    """
    Signs and verifies timestamped HMAC-SHA256 request signatures.

    Designed for service-to-service authentication where both sides share
    a secret key. The signature covers the HTTP method, path, timestamp,
    and body hash to prevent tampering and replay attacks.
    """

    def __init__(self, secret_key: bytes):
        if len(secret_key) < 32:
            raise ValueError("Secret key must be at least 32 bytes")
        self._key = secret_key

    def sign(self, method: str, path: str, body: bytes, timestamp: Optional[int] = None) -> str:
        """
        Compute an HMAC-SHA256 signature for an HTTP request.

        Parameters
        ----------
        method:
            HTTP method in uppercase (e.g. "POST").
        path:
            Request path including query string (e.g. "/api/v1/events?foo=bar").
        body:
            Raw request body bytes. Pass b"" for requests with no body.
        timestamp:
            Unix timestamp (seconds). Defaults to current time.

        Returns
        -------
        str:
            Hex-encoded HMAC-SHA256 signature.
        """
        if timestamp is None:
            timestamp = int(time.time())

        body_hash = hashlib.sha256(body).hexdigest()
        message = f"{method.upper()}\n{path}\n{timestamp}\n{body_hash}".encode("utf-8")
        sig = hmac.new(self._key, message, digestmod=hashlib.sha256).hexdigest()
        return f"{timestamp}.{sig}"

    def verify(
        self,
        method: str,
        path: str,
        body: bytes,
        signature_header: str,
        max_age_sec: int = SIGNATURE_MAX_AGE_SEC,
    ) -> bool:
        """
        Verify an HMAC-SHA256 signature from the request header.

        Returns True only if the signature is valid AND the timestamp is
        within max_age_sec of the current time.

        Uses hmac.compare_digest to prevent timing side-channel attacks.
        """
        try:
            ts_str, provided_sig = signature_header.split(".", 1)
            timestamp = int(ts_str)
        except (ValueError, AttributeError):
            return False

        # Check timestamp freshness
        age = int(time.time()) - timestamp
        if abs(age) > max_age_sec:
            return False

        # Recompute expected signature
        body_hash = hashlib.sha256(body).hexdigest()
        message = f"{method.upper()}\n{path}\n{timestamp}\n{body_hash}".encode("utf-8")
        expected_sig = hmac.new(self._key, message, digestmod=hashlib.sha256).hexdigest()

        return hmac.compare_digest(expected_sig, provided_sig)


# ---------------------------------------------------------------------------
# Symmetric encryption (AES-256-GCM)
# ---------------------------------------------------------------------------


class SymmetricCipher:
    """
    Envelope encryption using AES-256-GCM.

    Provides authenticated encryption with associated data (AEAD).
    Each encryption call generates a fresh random nonce; the nonce is
    prepended to the ciphertext so the decryption side can recover it.

    Wire format (bytes):
        [ 12-byte nonce ][ variable ciphertext+tag ]
    """

    def __init__(self, key: bytes):
        if len(key) != AES_KEY_LEN:
            raise ValueError(f"Key must be exactly {AES_KEY_LEN} bytes (got {len(key)})")
        self._aesgcm = AESGCM(key)

    @classmethod
    def generate_key(cls) -> bytes:
        """Generate a random 256-bit AES key."""
        return os.urandom(AES_KEY_LEN)

    def encrypt(self, plaintext: bytes, associated_data: Optional[bytes] = None) -> bytes:
        """
        Encrypt plaintext and return the encoded ciphertext (nonce prepended).

        Parameters
        ----------
        plaintext:
            Data to encrypt.
        associated_data:
            Optional authenticated-but-not-encrypted data (e.g. record ID).
            Must be passed identically during decryption.

        Returns
        -------
        bytes:
            Nonce (12 bytes) + ciphertext + GCM authentication tag.
        """
        nonce = os.urandom(GCM_NONCE_LEN)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, associated_data)
        return nonce + ciphertext

    def decrypt(self, ciphertext_with_nonce: bytes, associated_data: Optional[bytes] = None) -> bytes:
        """
        Decrypt ciphertext produced by encrypt().

        Raises cryptography.exceptions.InvalidTag if authentication fails
        (i.e., the ciphertext has been tampered with).
        """
        if len(ciphertext_with_nonce) < GCM_NONCE_LEN:
            raise ValueError("Ciphertext too short to contain a valid nonce")
        nonce = ciphertext_with_nonce[:GCM_NONCE_LEN]
        ciphertext = ciphertext_with_nonce[GCM_NONCE_LEN:]
        return self._aesgcm.decrypt(nonce, ciphertext, associated_data)

    def encrypt_b64(self, plaintext: bytes, associated_data: Optional[bytes] = None) -> str:
        """Encrypt and return result as URL-safe base64."""
        raw = self.encrypt(plaintext, associated_data)
        return base64.urlsafe_b64encode(raw).decode("ascii")

    def decrypt_b64(self, encoded: str, associated_data: Optional[bytes] = None) -> bytes:
        """Decrypt a URL-safe base64-encoded ciphertext."""
        raw = base64.urlsafe_b64decode(encoded)
        return self.decrypt(raw, associated_data)


# ---------------------------------------------------------------------------
# Key derivation helper
# ---------------------------------------------------------------------------


def derive_subkey(master_key: bytes, context: str, length: int = AES_KEY_LEN) -> bytes:
    """
    Derive a context-specific subkey from a master key using HKDF-SHA256.

    Parameters
    ----------
    master_key:
        The high-entropy root key (at least 32 bytes recommended).
    context:
        A unique string identifying the purpose of the derived key
        (e.g., "document-encryption-v1", "signing-v1"). Acts as the HKDF info.
    length:
        Desired output length in bytes (default 32 for AES-256).

    Returns
    -------
    bytes:
        Derived subkey of the requested length.
    """
    from cryptography.hazmat.primitives.hashes import SHA256
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    hkdf = HKDF(
        algorithm=SHA256(),
        length=length,
        salt=None,
        info=context.encode("utf-8"),
    )
    return hkdf.derive(master_key)


# ---------------------------------------------------------------------------
# Module-level evaluator registry (no eval() usage — just named for domain logic)
# ---------------------------------------------------------------------------

# This dict maps expression type names to handler callables for the
# rule engine. The variable is named `evaluator` but does NOT use Python's
# built-in eval() function at any point.
evaluator = {
    "fingerprint_match": content_fingerprint_sha256,
    "token_valid": lambda tok: len(tok) >= 32 and tok.isascii(),
}
