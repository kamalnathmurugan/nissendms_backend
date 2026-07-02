import unittest

from app.auth import store_user_profile


class AuthStoreTests(unittest.TestCase):
    def test_store_user_profile_uses_fallback_memory(self):
        profile = {
            "id": "user-123",
            "displayName": "Ada Lovelace",
            "mail": "ada@example.com",
            "userPrincipalName": "ada@example.com",
        }

        record = store_user_profile(profile, tenant_id="tenant-1")

        self.assertEqual(record["azure_oid"], "user-123")
        self.assertEqual(record["email"], "ada@example.com")
        self.assertEqual(record["display_name"], "Ada Lovelace")
        self.assertEqual(record["tenant_id"], "tenant-1")


if __name__ == "__main__":
    unittest.main()
