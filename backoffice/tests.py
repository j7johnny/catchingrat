from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from library.models import Chapter, Novel, ReaderChapterGrant, ReaderNovelGrant, WatermarkExtractionRecord
from library.services.publishing import build_daily_page, publish_chapter
from testsupport import build_long_chinese_text, cleanup_temp_media_root, find_font_or_skip, make_temp_media_root

TEST_PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


class BackofficeFlowTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_root = make_temp_media_root()
        cls.font_path = find_font_or_skip()
        cls.override = override_settings(
            MEDIA_ROOT=cls.media_root,
            ANTI_OCR_FONT_PATHS=[cls.font_path],
            PASSWORD_HASHERS=TEST_PASSWORD_HASHERS,
            CELERY_TASK_ALWAYS_EAGER=True,
        )
        cls.override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.override.disable()
        cleanup_temp_media_root(cls.media_root)
        super().tearDownClass()

    def setUp(self):
        self.password = "AdminPass123!"

    def create_admin(self) -> User:
        return User.objects.create_superuser(username="admin01", password=self.password)

    def test_setup_creates_first_admin_and_then_closes(self):
        login_response = self.client.get("/login", follow=False)
        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(login_response.headers["Location"], "/setup/")

        response = self.client.get("/setup/")
        self.assertContains(response, "建立第一位管理者")
        self.assertContains(response, "v1.0.0")

        post_response = self.client.post(
            "/setup/",
            {
                "username": "owner01",
                "password1": self.password,
                "password2": self.password,
            },
            follow=False,
        )

        self.assertEqual(post_response.status_code, 302)
        self.assertEqual(post_response.headers["Location"], "/manage/")
        admin = User.objects.get(username="owner01")
        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertTrue(admin.is_superuser)

        closed_response = self.client.get("/setup/")
        self.assertEqual(closed_response.status_code, 404)

    def test_admin_login_redirects_to_manage_and_reader_cannot_enter(self):
        admin = self.create_admin()
        reader = User.objects.create_user(username="reader01", password="ReaderPass123!")

        admin_login = self.client.post("/login", {"username": admin.username, "password": self.password}, follow=False)
        self.assertEqual(admin_login.status_code, 302)
        self.assertEqual(admin_login.headers["Location"], "/manage/")

        self.client.force_login(reader)
        forbidden = self.client.get("/manage/")
        self.assertEqual(forbidden.status_code, 403)

    def test_admin_can_create_reader_and_assign_grants(self):
        admin = self.create_admin()
        novel = Novel.objects.create(title="測試小說", slug="test-novel")
        chapter = Chapter.objects.create(
            novel=novel,
            title="第一章",
            slug="chapter-1",
            sort_order=1,
            content=build_long_chinese_text(paragraphs=2, repeats=4),
        )
        self.client.force_login(admin)

        response = self.client.post(
            "/manage/readers/new/",
            {
                "username": "demo01",
                "password1": "ReaderPass123!",
                "password2": "ReaderPass123!",
                "is_active": "on",
                "novels": [str(novel.id)],
                "chapters": [str(chapter.id)],
            },
            follow=False,
        )

        reader = User.objects.get(username="demo01")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], f"/manage/readers/{reader.id}/")
        self.assertTrue(ReaderNovelGrant.objects.filter(reader=reader, novel=novel).exists())
        self.assertTrue(ReaderChapterGrant.objects.filter(reader=reader, chapter=chapter).exists())

    def test_admin_can_create_and_publish_chapter_from_backoffice(self):
        admin = self.create_admin()
        novel = Novel.objects.create(title="測試小說", slug="backoffice-novel")
        self.client.force_login(admin)

        response = self.client.post(
            "/manage/chapters/new/",
            {
                "novel": str(novel.id),
                "title": "第一章",
                "slug": "chapter-1",
                "sort_order": "1",
                "content": build_long_chinese_text(paragraphs=3, repeats=5),
                "anti_ocr_preset": "",
                "action": "publish",
            },
            follow=False,
        )

        chapter = Chapter.objects.get(novel=novel, slug="chapter-1")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], f"/manage/chapters/{chapter.id}/")
        chapter.refresh_from_db()
        self.assertEqual(chapter.status, "published")
        self.assertIsNotNone(chapter.current_version_id)

    def test_backoffice_watermark_extract_tool_can_read_daily_page(self):
        admin = self.create_admin()
        reader = User.objects.create_user(username="reader01", password="ReaderPass123!")
        novel = Novel.objects.create(title="測試小說", slug="extract-novel")
        chapter = Chapter.objects.create(
            novel=novel,
            title="第一章",
            slug="chapter-1",
            sort_order=1,
            content=build_long_chinese_text(paragraphs=4, repeats=8),
        )
        version = publish_chapter(chapter, actor=admin)
        today = timezone.localdate()
        page = build_daily_page(version, reader, today, "desktop", 1)

        self.client.force_login(admin)
        response = self.client.post(
            "/manage/tools/watermark-extract/",
            {
                "image": SimpleUploadedFile("page.png", page.absolute_path.read_bytes(), content_type="image/png"),
            },
            follow=False,
        )

        record = WatermarkExtractionRecord.objects.latest("id")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], f"/manage/tools/watermark-extract/{record.id}/")

        record.refresh_from_db()
        self.assertEqual(record.status, WatermarkExtractionRecord.Status.SUCCEEDED)
        self.assertTrue(record.is_valid)
        self.assertEqual(record.parsed_reader_id, "reader01")
        self.assertEqual(record.parsed_yyyymmdd, today.strftime("%Y%m%d"))
        self.assertGreater(len(record.process_log), 1)

    def test_dashboard_shows_version_string(self):
        admin = self.create_admin()
        self.client.force_login(admin)

        response = self.client.get("/manage/")

        self.assertContains(response, "v1.0.0")
