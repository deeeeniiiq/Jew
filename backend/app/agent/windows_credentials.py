"""Protect large OAuth tokens using Windows DPAPI, outside Credential Manager limits.

The encrypted blob is tied to the current Windows user. Existing keyring entries
are migrated on first read so previous Clew installations can keep their login.
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
from ctypes import wintypes
from pathlib import Path

from app.agent.chatgpt_auth import ChatGPTError, KeyringCredentialStore


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data: bytes) -> tuple[_Blob, object]:
    buffer = (ctypes.c_ubyte * max(1, len(data))).from_buffer_copy(data or b"\0")
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _protect(data: bytes, *, decrypt: bool, entropy: bytes = b"Jew ChatGPT OAuth v1") -> bytes:
    if sys.platform != "win32":
        raise OSError("DPAPI is only available on Windows")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    function.restype = wintypes.BOOL
    if decrypt:
        function.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob),
                             ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    else:
        function.argtypes = [ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.POINTER(_Blob),
                             ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    src, src_buffer = _blob(data)
    entropy, entropy_buffer = _blob(entropy)
    dst = _Blob()
    if decrypt:
        success = function(ctypes.byref(src), None, ctypes.byref(entropy), None, None, 1, ctypes.byref(dst))
    else:
        success = function(ctypes.byref(src), None, ctypes.byref(entropy), None, None, 1, ctypes.byref(dst))
    if not success:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(dst.pbData, dst.cbData)
    finally:
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree(ctypes.cast(dst.pbData, ctypes.c_void_p))


class WindowsCredentialStore:
    """Per-user encrypted credential blob with atomic writes and legacy migration."""

    def __init__(self, path: Path, legacy: KeyringCredentialStore):
        self.path = path
        self.legacy = legacy
        # Keep the stable, directory-scoped identifier exposed by the former
        # Keyring store (used by diagnostics and migration checks).
        self.account = legacy.account

    def read(self) -> dict | None:
        if self.path.exists():
            try:
                blob = self.path.read_bytes()
                if len(blob) > 2 * 1024 * 1024:
                    raise ValueError("oversized credential blob")
                value = json.loads(_protect(blob, decrypt=True))
                if not isinstance(value, dict):
                    raise ValueError("invalid credential data")
                return value
            except (OSError, ValueError, UnicodeError) as exc:
                raise ChatGPTError("credential_storage_corrupt", "Jew could not decrypt its saved ChatGPT sign-in. Disconnect and sign in again.") from exc
        try:
            old = self.legacy.read()
        except ChatGPTError as exc:
            if exc.code == "credential_storage_unavailable":
                return None
            raise
        if old is not None:
            self.write(old)
            # Check the durable DPAPI copy before touching the legacy credential.
            # Windows Credential Manager may refuse deletion even though the new
            # store is usable. Keep sign-in available and retry cleanup on logout.
            if self.read() != old:
                raise ChatGPTError("credential_storage_unavailable", "Jew could not verify the migrated ChatGPT connection.")
            try:
                self.legacy.delete()
            except ChatGPTError as exc:
                if exc.code != "credential_storage_unavailable":
                    raise
        return old

    def write(self, value: dict) -> None:
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            data = json.dumps(value, separators=(",", ":")).encode("utf-8")
            encrypted = _protect(data, decrypt=False)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temp_path.open("wb") as file:
                file.write(encrypted)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, self.path)
        except (OSError, ValueError) as exc:
            raise ChatGPTError("credential_storage_unavailable", "Windows could not securely save the Jew ChatGPT connection.") from exc
        finally:
            temp_path.unlink(missing_ok=True)

    def delete(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise ChatGPTError("credential_storage_unavailable", "Windows could not remove the Jew ChatGPT connection.") from exc
        try:
            self.legacy.delete()
        except ChatGPTError as exc:
            if exc.code != "credential_storage_unavailable":
                raise


class WindowsAPIKeyStore:
    """Separate DPAPI namespace for the OpenAI API key. Never stores plaintext."""

    _entropy = b"Jew OpenAI API credential v1"

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> str | None:
        if not self.path.exists():
            return None
        try:
            value = self.path.read_bytes()
            if not value or len(value) > 16384:
                raise ValueError("invalid credential length")
            key = _protect(value, decrypt=True, entropy=self._entropy).decode("utf-8")
            if not key or len(key) > 4096:
                raise ValueError("invalid credential data")
            return key
        except (OSError, ValueError, UnicodeError) as exc:
            raise ChatGPTError("api_key_unreadable", "The saved OpenAI API key could not be decrypted on this Windows account.") from exc

    def write(self, key: str) -> None:
        if not key or len(key) > 4096:
            raise ChatGPTError("api_key_invalid", "Enter a valid OpenAI API key.")
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            ciphertext = _protect(key.encode("utf-8"), decrypt=False, entropy=self._entropy)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temp.open("wb") as file:
                file.write(ciphertext)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp, self.path)
        except OSError as exc:
            raise ChatGPTError("api_key_storage_unavailable", "Windows could not securely save the OpenAI API key.") from exc
        finally:
            temp.unlink(missing_ok=True)

    def delete(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise ChatGPTError("api_key_storage_unavailable", "Windows could not remove the OpenAI API key.") from exc
