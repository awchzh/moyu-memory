#!/usr/bin/env python3
"""
encrypt.py — MOYU Encryption Module (Optional)

Optional layer: when enabled in config.yaml, all memory data files
are encrypted with AES-256-GCM before writing to disk.

Requires `pip install cryptography` when enabled.
No-op graceful degradation when the package is not installed.

Usage:
    from defense_toolkit.encrypt import encrypt_bytes, decrypt_bytes

    cipher = encrypt_bytes(b"plaintext", "mypassword")
    plain = decrypt_bytes(cipher, "mypassword")  # -> b"plaintext"
"""

import base64
import os

# ── Headers for detection ──
ENC_HEADER = b"ENCv1:"  # Prefix on all encrypted files

# ── Lazy-load cryptography (optional dep) ──
_CRYPTO_AVAILABLE = False
_CRYPTO_ERROR = None


def _check_crypto():
    global _CRYPTO_AVAILABLE, _CRYPTO_ERROR
    if not _CRYPTO_AVAILABLE and _CRYPTO_ERROR is None:
        try:
            import cryptography
            _CRYPTO_AVAILABLE = True
        except ImportError:
            _CRYPTO_ERROR = "cryptography library not installed. Run: pip install cryptography"
        except Exception as e:
            _CRYPTO_ERROR = str(e)
    return _CRYPTO_AVAILABLE


def check_availability() -> tuple:
    """Check if cryptography is available. Returns (available, error_message)."""
    ok = _check_crypto()
    return (ok, _CRYPTO_ERROR)


# ── PBKDF2 key derivation ──

def _derive_key(password: str, salt: bytes = None) -> tuple:
    """Derive a 32-byte AES-256 key from a password using PBKDF2.

    If salt is None, generates a new random 16-byte salt.
    Returns (key, salt).
    """
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    if salt is None:
        salt = os.urandom(16)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600000,  # OWASP recommended for PBKDF2-HMAC-SHA256
    )
    key = kdf.derive(password.encode("utf-8"))
    return key, salt


# ── Encrypt / Decrypt ──

def encrypt_bytes(data: bytes, password: str) -> bytes:
    """Encrypt bytes with AES-256-GCM. Returns base64-encoded ciphertext
    in format: ENCv1:{base64(salt + nonce + ciphertext)}.

    Raises RuntimeError if cryptography is not installed.
    """
    if not _check_crypto():
        raise RuntimeError(_CRYPTO_ERROR or "cryptography not available")

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key, salt = _derive_key(password)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce for GCM

    ciphertext = aesgcm.encrypt(nonce, data, None)  # None = no additional data

    # Pack: salt(16) + nonce(12) + ciphertext_plus_tag(variable)
    packed = salt + nonce + ciphertext
    b64 = base64.b64encode(packed)
    return ENC_HEADER + b64


def decrypt_bytes(payload: bytes, password: str) -> bytes:
    """Decrypt bytes that were encrypted with encrypt_bytes().

    Returns original plaintext bytes.
    Raises ValueError if the payload is not in the expected format
    (e.g., not encrypted, or wrong password).
    """
    if not _check_crypto():
        raise RuntimeError(_CRYPTO_ERROR or "cryptography not available")

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    # Strip header
    if not payload.startswith(ENC_HEADER):
        raise ValueError("Not an encrypted payload (missing ENCv1 header)")

    raw = base64.b64decode(payload[len(ENC_HEADER):])

    # Unpack: salt(16) + nonce(12) + ciphertext(rest)
    salt = raw[:16]
    nonce = raw[16:28]
    ciphertext = raw[28:]

    key, _ = _derive_key(password, salt)
    aesgcm = AESGCM(key)

    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext
    except Exception:
        raise ValueError("Decryption failed — wrong password or corrupted data")


def is_encrypted(data: bytes) -> bool:
    """Check if data starts with the ENCv1 header."""
    return data.startswith(ENC_HEADER)


# ── File-level helpers (optional convenience) ──

def encrypt_file(path: str, password: str):
    """Read a file, encrypt its content, write back encrypted.

    The file must exist and be readable.
    If the file is already encrypted, this is a no-op.
    """
    with open(path, "rb") as f:
        data = f.read()

    if is_encrypted(data):
        return  # Already encrypted

    encrypted = encrypt_bytes(data, password)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(encrypted)
    os.replace(tmp, path)  # atomic on POSIX and macOS


def decrypt_file(path: str, password: str) -> bytes:
    """Read an encrypted file, decrypt it.

    Returns the plaintext bytes.
    If the file is not encrypted, returns the raw content as-is.
    """
    with open(path, "rb") as f:
        data = f.read()

    if not is_encrypted(data):
        return data  # Not encrypted, return as-is

    return decrypt_bytes(data, password)


def demo() -> dict:
    """Quick demo for verification."""
    password = "test_password_123"
    plaintext = "Hello, MOYU! This is a test message with 中文.".encode("utf-8")

    cipher = encrypt_bytes(plaintext, password)
    decrypted = decrypt_bytes(cipher, password)

    passed = plaintext == decrypted
    return {
        "title": "Encryption Module",
        "output": f"  Plaintext:  {plaintext.decode()}\n"
                  f"  Encrypted:  {cipher[:40]}...\n"
                  f"  Decrypted:  {decrypted.decode()}\n"
                  f"  Roundtrip:  {'✅ PASS' if passed else '❌ FAIL'}",
    }


if __name__ == "__main__":
    ok, err = check_availability()
    if not ok:
        print(f"❌ {err}")
        exit(1)

    d = demo()
    print(d["title"])
    print(d["output"])

    # Also test big data (simulate JSON memory file)
    pw = "test_password_123"
    big = b"x" * 100000
    cipher = encrypt_bytes(big, pw)
    decrypted = decrypt_bytes(cipher, pw)
    assert big == decrypted
    print(f"  Big data (100KB): ✅ roundtrip OK")
