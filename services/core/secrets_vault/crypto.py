"""Envelope encryption for workspace secrets (threat T2, docs/11-security-privacy.md).

Each secret has its own random 256-bit data key. Values are sealed with AES-256-GCM under
that key; the data key is sealed under the master key (``SECRETS_MASTER_KEY``, 32 bytes,
base64), which lives outside the database. Both seals bind the secret's id as associated
data, so ciphertext copied onto another row will not decrypt.
"""

import base64
import json
import os
from functools import cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

KEY_VERSION = 1
NONCE = 12


@cache
def _master() -> AESGCM:
    raw = settings.SECRETS_MASTER_KEY.strip()
    try:
        key = base64.b64decode(raw, validate=True)
    except ValueError:
        key = b""
    if len(key) != 32:
        raise ImproperlyConfigured("SECRETS_MASTER_KEY must be 32 random bytes, base64-encoded.")
    return AESGCM(key)


def _seal(aead: AESGCM, data: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(NONCE)
    return nonce + aead.encrypt(nonce, data, aad)


def _open(aead: AESGCM, blob: bytes, aad: bytes) -> bytes:
    return aead.decrypt(blob[:NONCE], blob[NONCE:], aad)


def seal(secret_id: str, values: dict[str, str]) -> tuple[bytes, bytes, int]:
    """(ciphertext, data_key_ciphertext, key_version)."""
    data_key = AESGCM.generate_key(bit_length=256)
    ciphertext = _seal(
        AESGCM(data_key), json.dumps(values).encode(), f"values:{secret_id}".encode()
    )
    wrapped = _seal(_master(), data_key, f"key:{secret_id}".encode())
    return ciphertext, wrapped, KEY_VERSION


def unseal(
    secret_id: str, ciphertext: bytes | memoryview, data_key_ciphertext: bytes | memoryview
) -> dict[str, str]:
    data_key = _open(_master(), bytes(data_key_ciphertext), f"key:{secret_id}".encode())
    plain = _open(AESGCM(data_key), bytes(ciphertext), f"values:{secret_id}".encode())
    return json.loads(plain)
