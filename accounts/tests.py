from django.core.cache import cache
from django.test import TestCase, override_settings

from .models import User

TEST_PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@override_settings(PASSWORD_HASHERS=TEST_PASSWORD_HASHERS)
class AuthFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_superuser(username="admin01", password="adminpass")
        self.reader = User.objects.create_user(username="reader01", password="secret123")

    def test_bruteforce_lock_after_repeated_failures(self):
        for _ in range(5):
            self.client.post("/login", {"username": "reader01", "password": "wrongpass"})

        response = self.client.post("/login", {"username": "reader01", "password": "wrongpass"})

        self.assertContains(response, "嘗試次數過多")

    def test_reader_can_change_password(self):
        login_response = self.client.post("/login", {"username": "reader01", "password": "secret123"})
        self.assertEqual(login_response.status_code, 302)

        response = self.client.post(
            "/me/password",
            {
                "old_password": "secret123",
                "new_password1": "newpass456",
                "new_password2": "newpass456",
            },
            follow=True,
        )

        self.reader.refresh_from_db()
        self.assertTrue(self.reader.check_password("newpass456"))
        self.assertContains(response, "密碼已更新")

    def test_reader_can_logout_via_get(self):
        self.client.post("/login", {"username": "reader01", "password": "secret123"})

        response = self.client.get("/logout", follow=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")
        self.assertNotIn("_auth_user_id", self.client.session)
