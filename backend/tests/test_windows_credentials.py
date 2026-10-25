"""Check Windows DPAPI with harmless disposable credentials; never read live tokens."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from app.agent.windows_credentials import WindowsCredentialStore, WindowsAPIKeyStore


@unittest.skipUnless(sys.platform == "win32", "Windows DPAPI only")
class WindowsCredentialStoreTests(unittest.TestCase):
    def test_round_trip_large_oauth_data_without_credential_manager(self):
        class Legacy:
            account = "test"
            def read(self):
                return None
            def delete(self):
                return None

        with tempfile.TemporaryDirectory(prefix="jew-dpapi-test-") as folder:
            file = Path(folder) / "oauth.dpapi"
            store = WindowsCredentialStore(file, Legacy())
            original = {"access_token": "dummy-token-" * 800, "refresh_token": "dummy-refresh-" * 800}
            store.write(original)
            self.assertTrue(file.is_file())
            self.assertNotIn(b"dummy-token", file.read_bytes())
            self.assertEqual(store.read(), original)
            store.delete()
            self.assertFalse(file.exists())

    def test_separate_api_key_namespace(self):
        with tempfile.TemporaryDirectory(prefix="jew-dpapi-key-test-") as folder:
            store = WindowsAPIKeyStore(Path(folder) / "test.dpapi")
            store.write("example-key-that-is-not-live")
            self.assertEqual(store.read(), "example-key-that-is-not-live")
            store.delete()
            self.assertIsNone(store.read())


if __name__ == "__main__":
    unittest.main()
