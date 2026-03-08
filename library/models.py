from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class DeviceProfile(models.TextChoices):
    DESKTOP = "desktop", "桌機"
    MOBILE = "mobile", "手機"


class ChapterStatus(models.TextChoices):
    DRAFT = "draft", "草稿"
    PUBLISHED = "published", "已發布"
    UNPUBLISHED = "unpublished", "已下架"


class Novel(models.Model):
    title = models.CharField("書名", max_length=200)
    slug = models.SlugField("代稱", max_length=220, unique=True, allow_unicode=True)
    description = models.TextField("簡介", blank=True)
    is_active = models.BooleanField("啟用", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        verbose_name = "小說"
        verbose_name_plural = "小說"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=True)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.title


class AntiOcrPreset(models.Model):
    name = models.CharField("名稱", max_length=100, unique=True)
    is_default = models.BooleanField("預設", default=False)
    char_to_pinyin_ratio = models.FloatField(default=0)
    char_reverse_ratio = models.FloatField(default=0)
    desktop_width = models.PositiveIntegerField(default=600)
    desktop_min_font_size = models.PositiveIntegerField(default=22)
    desktop_max_font_size = models.PositiveIntegerField(default=28)
    desktop_bg_density = models.FloatField(default=0.08)
    mobile_width = models.PositiveIntegerField(default=420)
    mobile_min_font_size = models.PositiveIntegerField(default=20)
    mobile_max_font_size = models.PositiveIntegerField(default=24)
    mobile_bg_density = models.FloatField(default=0.06)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "name"]
        verbose_name = "Anti-OCR 參數集"
        verbose_name_plural = "Anti-OCR 參數集"

    def clean(self):
        if self.desktop_width > 600:
            raise ValidationError("desktop 寬度不得大於 600。")
        if self.mobile_width > 600:
            raise ValidationError("mobile 寬度不得大於 600。")
        if self.desktop_min_font_size > self.desktop_max_font_size:
            raise ValidationError("desktop 最小字級不可大於最大字級。")
        if self.mobile_min_font_size > self.mobile_max_font_size:
            raise ValidationError("mobile 最小字級不可大於最大字級。")

    def as_snapshot(self) -> dict:
        return {
            "char_to_pinyin_ratio": self.char_to_pinyin_ratio,
            "char_reverse_ratio": self.char_reverse_ratio,
            "desktop": {
                "width": self.desktop_width,
                "min_font_size": self.desktop_min_font_size,
                "max_font_size": self.desktop_max_font_size,
                "bg_density": self.desktop_bg_density,
            },
            "mobile": {
                "width": self.mobile_width,
                "min_font_size": self.mobile_min_font_size,
                "max_font_size": self.mobile_max_font_size,
                "bg_density": self.mobile_bg_density,
            },
        }

    def __str__(self) -> str:
        return self.name


class Chapter(models.Model):
    novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name="chapters")
    title = models.CharField("章節標題", max_length=200)
    slug = models.SlugField("章節代稱", max_length=220, allow_unicode=True)
    sort_order = models.PositiveIntegerField("排序", default=1)
    content = models.TextField("章節全文", blank=True)
    status = models.CharField(max_length=20, choices=ChapterStatus.choices, default=ChapterStatus.DRAFT)
    anti_ocr_preset = models.ForeignKey(
        AntiOcrPreset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chapters",
    )
    current_version = models.ForeignKey(
        "ChapterVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["novel__title", "sort_order", "id"]
        verbose_name = "章節"
        verbose_name_plural = "章節"
        constraints = [
            models.UniqueConstraint(fields=["novel", "slug"], name="unique_chapter_slug_per_novel"),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=True)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.novel.title} / {self.title}"


class ChapterVersion(models.Model):
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    content = models.TextField()
    source_sha256 = models.CharField(max_length=64)
    preset_snapshot = models.JSONField(default=dict)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_chapter_versions",
    )
    published_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-published_at", "-id"]
        verbose_name = "章節版本"
        verbose_name_plural = "章節版本"
        constraints = [
            models.UniqueConstraint(fields=["chapter", "version_number"], name="unique_version_per_chapter"),
        ]

    def __str__(self) -> str:
        return f"{self.chapter} v{self.version_number}"


class ReaderSiteGrant(models.Model):
    reader = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="site_grants")
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_site_permissions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["reader__username"]
        verbose_name = "閱讀者全站授權"
        verbose_name_plural = "閱讀者全站授權"
        constraints = [
            models.UniqueConstraint(fields=["reader"], name="unique_reader_site_grant"),
        ]

    def __str__(self) -> str:
        return f"{self.reader} -> 全站"


class ReaderNovelGrant(models.Model):
    reader = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="novel_grants")
    novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name="reader_novel_grants")
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_novel_permissions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["novel__title", "reader__username"]
        verbose_name = "閱讀者小說授權"
        verbose_name_plural = "閱讀者小說授權"
        constraints = [
            models.UniqueConstraint(fields=["reader", "novel"], name="unique_reader_novel_grant"),
        ]

    def __str__(self) -> str:
        return f"{self.reader} -> {self.novel}"


class ReaderChapterGrant(models.Model):
    reader = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chapter_grants")
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="reader_grants")
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_chapter_permissions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["chapter__novel__title", "chapter__sort_order"]
        verbose_name = "閱讀者章節授權"
        verbose_name_plural = "閱讀者章節授權"
        constraints = [
            models.UniqueConstraint(fields=["reader", "chapter"], name="unique_reader_chapter_grant"),
        ]

    def __str__(self) -> str:
        return f"{self.reader} -> {self.chapter}"


class BasePage(models.Model):
    chapter_version = models.ForeignKey(ChapterVersion, on_delete=models.CASCADE, related_name="base_pages")
    device_profile = models.CharField(max_length=20, choices=DeviceProfile.choices)
    page_index = models.PositiveIntegerField()
    relative_path = models.CharField(max_length=255)
    char_count = models.PositiveIntegerField(default=0)
    image_width = models.PositiveIntegerField(default=0)
    image_height = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["page_index"]
        verbose_name = "基底圖片"
        verbose_name_plural = "基底圖片"
        constraints = [
            models.UniqueConstraint(
                fields=["chapter_version", "device_profile", "page_index"],
                name="unique_base_page",
            ),
        ]

    @property
    def absolute_path(self) -> Path:
        return Path(settings.MEDIA_ROOT) / self.relative_path


class DailyPageCache(models.Model):
    chapter_version = models.ForeignKey(ChapterVersion, on_delete=models.CASCADE, related_name="daily_pages")
    reader = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="daily_pages")
    device_profile = models.CharField(max_length=20, choices=DeviceProfile.choices)
    for_date = models.DateField()
    page_index = models.PositiveIntegerField()
    relative_path = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["page_index"]
        verbose_name = "每日個人化圖片快取"
        verbose_name_plural = "每日個人化圖片快取"
        constraints = [
            models.UniqueConstraint(
                fields=["chapter_version", "reader", "device_profile", "for_date", "page_index"],
                name="unique_daily_page",
            ),
        ]

    @property
    def absolute_path(self) -> Path:
        return Path(settings.MEDIA_ROOT) / self.relative_path


class AuditLog(models.Model):
    class EventType(models.TextChoices):
        LOGIN_SUCCESS = "login_success", "登入成功"
        LOGIN_FAILURE = "login_failure", "登入失敗"
        PASSWORD_CHANGED = "password_changed", "密碼更新"
        CHAPTER_PUBLISHED = "chapter_published", "章節發布"
        CHAPTER_OPENED = "chapter_opened", "章節開啟"
        WATERMARK_EXTRACTED = "watermark_extracted", "浮水印提取"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    event_type = models.CharField(max_length=50, choices=EventType.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "稽核紀錄"
        verbose_name_plural = "稽核紀錄"

    def __str__(self) -> str:
        return f"{self.event_type} @ {self.created_at:%Y-%m-%d %H:%M:%S}"


class WatermarkExtractionRecord(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "等待處理"
        RUNNING = "running", "提取中"
        SUCCEEDED = "succeeded", "提取成功"
        FAILED = "failed", "提取失敗"

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="watermark_extraction_records",
        verbose_name="建立者",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="狀態")
    source_filename = models.CharField(max_length=255, verbose_name="原始檔名")
    upload_relative_path = models.CharField(max_length=255, verbose_name="上傳檔案路徑")
    image_width = models.PositiveIntegerField(default=0, verbose_name="圖片寬度")
    image_height = models.PositiveIntegerField(default=0, verbose_name="圖片高度")
    raw_payload = models.TextField(blank=True, verbose_name="原始提取文本")
    parsed_reader_id = models.CharField(max_length=16, blank=True, verbose_name="解析後 reader_id")
    parsed_yyyymmdd = models.CharField(max_length=8, blank=True, verbose_name="解析後日期")
    is_valid = models.BooleanField(default=False, verbose_name="是否有效")
    selected_method = models.CharField(max_length=32, blank=True, verbose_name="成功方法")
    attempt_count = models.PositiveIntegerField(default=0, verbose_name="嘗試次數")
    duration_ms = models.PositiveIntegerField(default=0, verbose_name="處理時間毫秒")
    process_log = models.JSONField(default=list, blank=True, verbose_name="處理紀錄")
    error_message = models.TextField(blank=True, verbose_name="錯誤訊息")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="開始時間")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="完成時間")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="建立時間")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "浮水印提取紀錄"
        verbose_name_plural = "浮水印提取紀錄"

    @property
    def absolute_upload_path(self) -> Path:
        return Path(settings.MEDIA_ROOT) / self.upload_relative_path

    def __str__(self) -> str:
        return f"{self.source_filename} ({self.get_status_display()})"
