import re
import time

from django.test import TestCase, override_settings

from accounts.models import User
from library.models import Chapter, Novel, ReaderChapterGrant, ReaderNovelGrant, ReaderSiteGrant
from library.services.publishing import publish_chapter
from testsupport import build_long_chinese_text, cleanup_temp_media_root, find_font_or_skip, make_temp_media_root

TEST_PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


class ReaderViewTests(TestCase):
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
        self.other_reader = User.objects.create_user(username="reader02", password="secret123")
        self.site_reader = User.objects.create_user(username="reader03", password="secret123")

        self.novel = Novel.objects.create(title="測試小說", slug="reader-novel")
        self.chapter = Chapter.objects.create(
            novel=self.novel,
            title="第一章",
            slug="reader-chapter",
            sort_order=1,
            content=build_long_chinese_text(paragraphs=3, repeats=6),
        )
        self.chapter_two = Chapter.objects.create(
            novel=self.novel,
            title="第二章",
            slug="reader-chapter-2",
            sort_order=2,
            content=build_long_chinese_text(paragraphs=2, repeats=5),
        )
        self.other_novel = Novel.objects.create(title="另一部作品", slug="other-novel")
        self.other_novel_chapter = Chapter.objects.create(
            novel=self.other_novel,
            title="別冊第一章",
            slug="other-chapter-1",
            sort_order=1,
            content=build_long_chinese_text(paragraphs=2, repeats=4),
        )

        publish_chapter(self.chapter, actor=self.admin)
        publish_chapter(self.chapter_two, actor=self.admin)
        publish_chapter(self.other_novel_chapter, actor=self.admin)

        ReaderChapterGrant.objects.create(reader=self.reader, chapter=self.chapter, granted_by=self.admin)

    def test_unauthorized_reader_cannot_open_chapter(self):
        self.client.force_login(self.other_reader)
        response = self.client.get(f"/reader/chapters/{self.chapter.id}")
        self.assertEqual(response.status_code, 404)

    def test_reader_page_headers_and_daily_cache_reuse(self):
        self.client.force_login(self.reader)

        response = self.client.get(f"/reader/chapters/{self.chapter.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("private, no-store", response["Cache-Control"])

        match = re.search(rb"/reader/pages/([^/]+)/1\.png", response.content)
        self.assertIsNotNone(match)
        image_path = f"/reader/pages/{match.group(1).decode('utf-8')}/1.png"

        first_image = self.client.get(image_path)
        second_image = self.client.get(image_path)

        self.assertEqual(first_image.status_code, 200)
        self.assertEqual(second_image.status_code, 200)
        self.assertIn("private, no-store", first_image["Cache-Control"])

    def test_first_page_render_stays_under_three_seconds(self):
        self.client.force_login(self.reader)
        started = time.perf_counter()
        response = self.client.get(f"/reader/chapters/{self.chapter.id}")
        elapsed = time.perf_counter() - started

        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 3.0)

    def test_novel_grant_allows_all_chapters_in_same_novel(self):
        ReaderNovelGrant.objects.create(reader=self.other_reader, novel=self.novel, granted_by=self.admin)
        self.client.force_login(self.other_reader)

        response = self.client.get("/reader/library")
        novel_response = self.client.get(f"/reader/novels/{self.novel.id}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.novel.title)
        self.assertNotContains(response, self.other_novel.title)
        self.assertEqual(novel_response.status_code, 200)
        self.assertContains(novel_response, self.chapter.title)
        self.assertContains(novel_response, self.chapter_two.title)
        self.assertNotContains(novel_response, self.other_novel_chapter.title)

    def test_site_grant_allows_all_published_chapters(self):
        ReaderSiteGrant.objects.create(reader=self.site_reader, granted_by=self.admin)
        self.client.force_login(self.site_reader)

        response = self.client.get("/reader/library")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.novel.title)
        self.assertContains(response, self.other_novel.title)

    def test_chapter_detail_includes_next_chapter_navigation(self):
        ReaderChapterGrant.objects.create(reader=self.reader, chapter=self.chapter_two, granted_by=self.admin)
        self.client.force_login(self.reader)

        response = self.client.get(f"/reader/chapters/{self.chapter.id}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"/reader/chapters/{self.chapter_two.id}")
