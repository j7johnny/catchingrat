from django.contrib import admin
from django.db.models import QuerySet
from django.urls import reverse
from django.utils.html import format_html

from .forms import AntiOcrPresetAdminForm, ChapterAdminForm, NovelAdminForm
from .models import (
    AntiOcrPreset,
    AuditLog,
    BasePage,
    Chapter,
    ChapterVersion,
    DailyPageCache,
    Novel,
    ReaderChapterGrant,
    ReaderNovelGrant,
    ReaderSiteGrant,
)
from .services.publishing import publish_chapter

admin.site.site_header = "CatchingRat 管理後台"
admin.site.site_title = "CatchingRat 後台"
admin.site.index_title = "內容管理與授權工具"


@admin.register(Novel)
class NovelAdmin(admin.ModelAdmin):
    form = NovelAdminForm
    list_display = ("title", "slug", "is_active", "updated_at")
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(AntiOcrPreset)
class AntiOcrPresetAdmin(admin.ModelAdmin):
    form = AntiOcrPresetAdminForm
    list_display = ("name", "is_default", "desktop_width", "mobile_width", "updated_at")
    list_filter = ("is_default",)
    search_fields = ("name",)
    fieldsets = (
        ("基本設定", {"fields": ("name", "is_default")}),
        (
            "整體防護",
            {
                "description": "這兩個比例依你的需求預設建議維持 0，以可讀性優先。",
                "fields": ("char_to_pinyin_ratio", "char_reverse_ratio"),
            },
        ),
        (
            "桌機版輸出",
            {
                "fields": (
                    "desktop_width",
                    "desktop_min_font_size",
                    "desktop_max_font_size",
                    "desktop_bg_density",
                )
            },
        ),
        (
            "手機版輸出",
            {
                "fields": (
                    "mobile_width",
                    "mobile_min_font_size",
                    "mobile_max_font_size",
                    "mobile_bg_density",
                )
            },
        ),
    )


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    form = ChapterAdminForm
    list_display = ("title", "novel", "status", "sort_order", "published_at", "publish_link")
    list_filter = ("status", "novel")
    search_fields = ("title", "novel__title", "content", "slug")
    autocomplete_fields = ("novel", "anti_ocr_preset", "current_version")
    actions = ("publish_selected",)
    fieldsets = (
        (
            "章節內容",
            {
                "fields": ("novel", "title", "slug", "sort_order", "status", "content"),
                "description": "章節代稱目前只用於資料整理、唯一性與後台辨識；前台閱讀網址仍使用章節 ID。",
            },
        ),
        ("發布設定", {"fields": ("anti_ocr_preset", "current_version", "published_at")}),
    )

    def publish_link(self, obj: Chapter):
        return format_html('<a class="button" href="{}">發布</a>', reverse("admin-chapter-publish", args=[obj.pk]))

    publish_link.short_description = "快速發布"

    @admin.action(description="發布所選章節")
    def publish_selected(self, request, queryset: QuerySet):
        for chapter in queryset:
            try:
                publish_chapter(chapter, actor=request.user, request=request)
            except ValueError:
                continue


@admin.register(ChapterVersion)
class ChapterVersionAdmin(admin.ModelAdmin):
    list_display = ("chapter", "version_number", "published_at", "created_by")
    list_filter = ("published_at",)
    readonly_fields = ("source_sha256", "preset_snapshot", "content")
    search_fields = ("chapter__title", "chapter__novel__title")


@admin.register(ReaderSiteGrant)
class ReaderSiteGrantAdmin(admin.ModelAdmin):
    list_display = ("reader", "granted_by", "created_at")
    search_fields = ("reader__username", "granted_by__username")
    autocomplete_fields = ("reader", "granted_by")


@admin.register(ReaderNovelGrant)
class ReaderNovelGrantAdmin(admin.ModelAdmin):
    list_display = ("reader", "novel", "granted_by", "created_at")
    search_fields = ("reader__username", "novel__title", "granted_by__username")
    autocomplete_fields = ("reader", "novel", "granted_by")


@admin.register(ReaderChapterGrant)
class ReaderChapterGrantAdmin(admin.ModelAdmin):
    list_display = ("reader", "chapter", "granted_by", "created_at")
    search_fields = ("reader__username", "chapter__title", "chapter__novel__title", "granted_by__username")
    autocomplete_fields = ("reader", "chapter", "granted_by")


@admin.register(BasePage)
class BasePageAdmin(admin.ModelAdmin):
    list_display = ("chapter_version", "device_profile", "page_index", "char_count", "image_width", "image_height")
    list_filter = ("device_profile",)
    readonly_fields = ("relative_path",)


@admin.register(DailyPageCache)
class DailyPageCacheAdmin(admin.ModelAdmin):
    list_display = ("chapter_version", "reader", "for_date", "device_profile", "page_index", "created_at")
    list_filter = ("device_profile", "for_date")
    readonly_fields = ("relative_path",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("event_type", "user", "ip_address", "created_at")
    list_filter = ("event_type", "created_at")
    readonly_fields = ("details",)
