from datetime import timedelta
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from accounts.models import User
from library.models import Chapter, DeviceProfile, Novel
from library.services.publishing import build_daily_page, cleanup_daily_cache, publish_chapter, render_base_pages_for_version
from library.services.watermark import (
    build_recovery_context,
    extract_watermark,
    extract_watermark_detailed,
    recover_candidate_payload,
)
from testsupport import build_long_chinese_text, cleanup_temp_media_root, find_font_or_skip, make_temp_media_root

TEST_PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


class RenderingFlowTests(TestCase):
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
        self.admin = User.objects.create_superuser(username="admin01", password="adminpass")
        self.reader = User.objects.create_user(username="reader01", password="secret123")
        self.novel = Novel.objects.create(title="測試小說", slug="test-novel")
        self.chapter = Chapter.objects.create(
            novel=self.novel,
            title="第一章",
            slug="chapter-1",
            sort_order=1,
            content=build_long_chinese_text(paragraphs=4, repeats=8),
        )

    def test_publish_generates_desktop_and_mobile_pages(self):
        version = publish_chapter(self.chapter, actor=self.admin)

        desktop_pages = render_base_pages_for_version(version, DeviceProfile.DESKTOP, force=True)
        mobile_pages = render_base_pages_for_version(version, DeviceProfile.MOBILE, force=True)

        self.assertGreaterEqual(desktop_pages[0].char_count, 200)
        self.assertTrue(all(page.image_width <= 600 for page in desktop_pages))
        self.assertTrue(all(page.image_width <= 600 for page in mobile_pages))

    def test_daily_cache_reuse_and_cleanup(self):
        version = publish_chapter(self.chapter, actor=self.admin)
        today = timezone.localdate()
        first_page = build_daily_page(version, self.reader, today, DeviceProfile.DESKTOP, 1)
        second_page = build_daily_page(version, self.reader, today, DeviceProfile.DESKTOP, 1)

        self.assertEqual(first_page.id, second_page.id)

        old_date = today - timedelta(days=4)
        old_page = build_daily_page(version, self.reader, old_date, DeviceProfile.DESKTOP, 1)
        removed = cleanup_daily_cache()

        self.assertGreaterEqual(removed, 1)
        self.assertFalse(old_page.absolute_path.exists())
        self.assertTrue(first_page.absolute_path.exists())

    def test_watermark_roundtrip_extracts_reader_and_date(self):
        version = publish_chapter(self.chapter, actor=self.admin)
        today = timezone.localdate()
        page = build_daily_page(version, self.reader, today, DeviceProfile.DESKTOP, 1)

        upload = SimpleUploadedFile("page.png", page.absolute_path.read_bytes(), content_type="image/png")
        _, parsed = extract_watermark(upload)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["reader_id"], "reader01")
        self.assertEqual(parsed["yyyymmdd"], today.strftime("%Y%m%d"))

    def test_detailed_extract_prefers_full_image_for_original_page(self):
        version = publish_chapter(self.chapter, actor=self.admin)
        today = timezone.localdate()
        page = build_daily_page(version, self.reader, today, DeviceProfile.DESKTOP, 1)

        upload = SimpleUploadedFile("page.png", page.absolute_path.read_bytes(), content_type="image/png")
        result = extract_watermark_detailed(upload)

        self.assertTrue(result["is_valid"])
        self.assertEqual(result["parsed"]["reader_id"], "reader01")
        self.assertEqual(result["trace"][1]["stage"], "full_image")
        self.assertNotIn("cropped", {entry["stage"] for entry in result["trace"]})

    def test_recovery_ignores_future_cached_dates_for_near_match(self):
        version = publish_chapter(self.chapter, actor=self.admin)
        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        build_daily_page(version, self.reader, today, DeviceProfile.DESKTOP, 1)
        build_daily_page(version, self.reader, tomorrow, DeviceProfile.DESKTOP, 1)

        context = build_recovery_context()
        recovered = recover_candidate_payload(f"Reader01|{today:%Y%m}0(", context)

        self.assertIsNotNone(recovered)
        self.assertEqual(recovered["reader_id"], "reader01")
        self.assertEqual(recovered["yyyymmdd"], today.strftime("%Y%m%d"))

    def test_recovery_can_fix_single_reader_prefix_noise(self):
        version = publish_chapter(self.chapter, actor=self.admin)
        today = timezone.localdate()
        build_daily_page(version, self.reader, today, DeviceProfile.DESKTOP, 1)

        context = build_recovery_context()
        recovered = recover_candidate_payload(f"$eader01|{today:%Y%m%d}~~~~", context)

        self.assertIsNotNone(recovered)
        self.assertEqual(recovered["reader_id"], "reader01")
        self.assertEqual(recovered["yyyymmdd"], today.strftime("%Y%m%d"))

    def test_stacked_screenshot_like_image_can_still_extract_watermark(self):
        version = publish_chapter(self.chapter, actor=self.admin)
        today = timezone.localdate()
        page_one = build_daily_page(version, self.reader, today, DeviceProfile.DESKTOP, 1)
        page_two = build_daily_page(version, self.reader, today, DeviceProfile.DESKTOP, 2)

        with Image.open(page_one.absolute_path) as image_one, Image.open(page_two.absolute_path) as image_two:
            canvas = Image.new("RGB", (image_one.width + 40, image_one.height + image_two.height + 60), "#f7efe5")
            canvas.paste(image_one, (20, 10))
            canvas.paste(image_two, (20, image_one.height + 30))
            buffer = BytesIO()
            canvas.save(buffer, format="PNG")

        upload = SimpleUploadedFile("stacked.png", buffer.getvalue(), content_type="image/png")
        result = extract_watermark_detailed(upload)

        self.assertTrue(result["is_valid"])
        self.assertEqual(result["parsed"]["reader_id"], "reader01")
        self.assertEqual(result["parsed"]["yyyymmdd"], today.strftime("%Y%m%d"))
        self.assertIn("cropped", {entry["stage"] for entry in result["trace"]})
