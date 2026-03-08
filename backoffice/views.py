from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.models import User
from library.models import AntiOcrPreset, Chapter, ChapterStatus, Novel, WatermarkExtractionRecord
from library.services.publishing import publish_chapter
from library.services.watermark_records import create_extraction_record
from library.tasks import run_watermark_extraction_task

from .forms import (
    AntiOcrPresetSimpleForm,
    ChapterBackofficeForm,
    NovelBackofficeForm,
    ReaderAccessForm,
    ReaderCreateForm,
    ReaderUpdateForm,
    SetupAdminForm,
    WatermarkExtractToolForm,
)


def has_admin_account() -> bool:
    return User.objects.filter(role=User.Role.ADMIN).exists()


def admin_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapped(request: HttpRequest, *args, **kwargs):
        if request.user.role != User.Role.ADMIN:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped


def render_manage(request: HttpRequest, template_name: str, context: dict) -> HttpResponse:
    defaults = {
        "manage_section": "dashboard",
        "page_title": "管理首頁",
        "page_subtitle": "用任務方式完成日常管理工作。",
    }
    defaults.update(context)
    return render(request, template_name, defaults)


@require_http_methods(["GET", "POST"])
def setup_view(request: HttpRequest) -> HttpResponse:
    if has_admin_account():
        raise Http404

    form = SetupAdminForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "第一位管理者已建立完成，現在可開始設定網站內容。")
        return redirect("backoffice:dashboard")

    return render(
        request,
        "backoffice/setup.html",
        {
            "form": form,
            "page_title": "首次開站設定",
            "page_subtitle": "尚未偵測到管理者帳號，請先建立第一位管理者。",
        },
    )


@admin_required
def dashboard(request: HttpRequest) -> HttpResponse:
    chapter_counts = Chapter.objects.aggregate(
        total=Count("id"),
        published=Count("id", filter=Q(status=ChapterStatus.PUBLISHED)),
        draft=Count("id", filter=Q(status=ChapterStatus.DRAFT)),
    )
    context = {
        "manage_section": "dashboard",
        "page_title": "管理首頁",
        "page_subtitle": "常用工作集中在這裡，不需要先理解 Django admin。",
        "stats": [
            {"label": "閱讀者帳號", "value": User.objects.filter(role=User.Role.READER).count()},
            {"label": "小說數量", "value": Novel.objects.count()},
            {"label": "已發布章節", "value": chapter_counts["published"]},
            {"label": "草稿章節", "value": chapter_counts["draft"]},
        ],
        "recent_chapters": Chapter.objects.select_related("novel", "current_version").order_by("-updated_at")[:6],
    }
    return render_manage(request, "backoffice/dashboard.html", context)


@admin_required
def reader_list(request: HttpRequest) -> HttpResponse:
    readers = (
        User.objects.filter(role=User.Role.READER)
        .annotate(
            site_grant_count=Count("site_grants", distinct=True),
            novel_grant_count=Count("novel_grants", distinct=True),
            chapter_grant_count=Count("chapter_grants", distinct=True),
        )
        .order_by("username")
    )
    return render_manage(
        request,
        "backoffice/reader_list.html",
        {
            "manage_section": "readers",
            "page_title": "閱讀者管理",
            "page_subtitle": "建立帳號、重設密碼，並設定全站、小說或章節授權。",
            "readers": readers,
        },
    )


@admin_required
@require_http_methods(["GET", "POST"])
def reader_create(request: HttpRequest) -> HttpResponse:
    form = ReaderCreateForm(request.POST or None, initial={"is_active": True})
    blank_reader = User(role=User.Role.READER)
    access_form = ReaderAccessForm(request.POST or None, reader=blank_reader)
    if request.method == "POST" and form.is_valid() and access_form.is_valid():
        reader = form.save()
        bound_access_form = ReaderAccessForm(request.POST, reader=reader)
        if bound_access_form.is_valid():
            bound_access_form.save(actor=request.user)
        messages.success(request, f"已建立閱讀者帳號 {reader.username}。")
        return redirect("backoffice:reader-update", user_id=reader.id)

    return render_manage(
        request,
        "backoffice/reader_form.html",
        {
            "manage_section": "readers",
            "page_title": "新增閱讀者",
            "page_subtitle": "先建立帳號，再一次設定可閱讀的範圍。",
            "account_form": form,
            "access_form": access_form,
            "reader_obj": None,
        },
    )


@admin_required
@require_http_methods(["GET", "POST"])
def reader_update(request: HttpRequest, user_id: int) -> HttpResponse:
    reader = get_object_or_404(User, pk=user_id, role=User.Role.READER)
    form = ReaderUpdateForm(request.POST or None, instance=reader)
    access_form = ReaderAccessForm(request.POST or None, reader=reader)
    if request.method == "POST" and form.is_valid() and access_form.is_valid():
        reader = form.save()
        access_form.save(actor=request.user)
        messages.success(request, f"已更新閱讀者帳號 {reader.username}。")
        return redirect("backoffice:reader-update", user_id=reader.id)

    return render_manage(
        request,
        "backoffice/reader_form.html",
        {
            "manage_section": "readers",
            "page_title": f"編輯閱讀者：{reader.username}",
            "page_subtitle": "在同一頁完成帳號狀態、密碼與三層授權設定。",
            "account_form": form,
            "access_form": access_form,
            "reader_obj": reader,
        },
    )


@admin_required
def novel_list(request: HttpRequest) -> HttpResponse:
    novels = Novel.objects.annotate(
        chapter_count=Count("chapters", distinct=True),
        published_count=Count("chapters", filter=Q(chapters__status=ChapterStatus.PUBLISHED), distinct=True),
    ).order_by("title")
    return render_manage(
        request,
        "backoffice/novel_list.html",
        {
            "manage_section": "novels",
            "page_title": "小說管理",
            "page_subtitle": "先建立小說，再進入小說頁面管理章節與發布。",
            "novels": novels,
        },
    )


@admin_required
@require_http_methods(["GET", "POST"])
def novel_create(request: HttpRequest) -> HttpResponse:
    form = NovelBackofficeForm(request.POST or None, initial={"is_active": True})
    if request.method == "POST" and form.is_valid():
        novel = form.save()
        messages.success(request, f"已建立小說《{novel.title}》。")
        return redirect("backoffice:novel-detail", novel_id=novel.id)

    return render_manage(
        request,
        "backoffice/novel_form.html",
        {
            "manage_section": "novels",
            "page_title": "新增小說",
            "page_subtitle": "先建立小說基本資料，之後再新增章節。",
            "form": form,
            "novel": None,
            "chapters": [],
        },
    )


@admin_required
@require_http_methods(["GET", "POST"])
def novel_detail(request: HttpRequest, novel_id: int) -> HttpResponse:
    novel = get_object_or_404(Novel, pk=novel_id)
    form = NovelBackofficeForm(request.POST or None, instance=novel)
    if request.method == "POST" and form.is_valid():
        novel = form.save()
        messages.success(request, f"已更新小說《{novel.title}》。")
        return redirect("backoffice:novel-detail", novel_id=novel.id)

    chapters = novel.chapters.select_related("current_version").order_by("sort_order", "id")
    return render_manage(
        request,
        "backoffice/novel_form.html",
        {
            "manage_section": "novels",
            "page_title": f"小說管理：{novel.title}",
            "page_subtitle": "這裡可以直接新增章節、進入編輯頁，或重新發布既有章節。",
            "form": form,
            "novel": novel,
            "chapters": chapters,
        },
    )


def _render_chapter_editor(request: HttpRequest, chapter: Chapter | None = None) -> HttpResponse:
    form = ChapterBackofficeForm(request.POST or None, instance=chapter)
    if request.method == "POST" and form.is_valid():
        chapter = form.save()
        action = request.POST.get("action", "save")
        if action == "publish":
            try:
                version = publish_chapter(chapter, actor=request.user, request=request)
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f"已發布章節《{chapter.title}》，版本 v{version.version_number}。")
        else:
            messages.success(request, "章節內容已儲存。若要讓讀者看到更新內容，請再按一次「立即發布」。")
        return redirect("backoffice:chapter-detail", chapter_id=chapter.id)

    return render_manage(
        request,
        "backoffice/chapter_form.html",
        {
            "manage_section": "novels",
            "page_title": "新增章節" if chapter is None else f"編輯章節：{chapter.title}",
            "page_subtitle": "可先存成草稿，確認後再發布成讀者可閱讀的圖片版本。",
            "form": form,
            "chapter": chapter,
        },
    )


@admin_required
@require_http_methods(["GET", "POST"])
def chapter_create(request: HttpRequest) -> HttpResponse:
    initial = {}
    novel_id = request.GET.get("novel")
    if novel_id and novel_id.isdigit():
        initial["novel"] = int(novel_id)
    if request.method == "GET":
        form = ChapterBackofficeForm(initial=initial)
        return render_manage(
            request,
            "backoffice/chapter_form.html",
            {
                "manage_section": "novels",
                "page_title": "新增章節",
                "page_subtitle": "新增後可先存草稿，再按立即發布產生圖片。",
                "form": form,
                "chapter": None,
            },
        )
    return _render_chapter_editor(request)


@admin_required
@require_http_methods(["GET", "POST"])
def chapter_detail(request: HttpRequest, chapter_id: int) -> HttpResponse:
    chapter = get_object_or_404(
        Chapter.objects.select_related("novel", "anti_ocr_preset", "current_version"),
        pk=chapter_id,
    )
    return _render_chapter_editor(request, chapter=chapter)


@admin_required
@require_http_methods(["POST"])
def chapter_publish(request: HttpRequest, chapter_id: int) -> HttpResponse:
    chapter = get_object_or_404(Chapter, pk=chapter_id)
    try:
        version = publish_chapter(chapter, actor=request.user, request=request)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"已發布章節《{chapter.title}》，版本 v{version.version_number}。")
    return redirect("backoffice:novel-detail", novel_id=chapter.novel_id)


@admin_required
def anti_ocr_preset_list(request: HttpRequest) -> HttpResponse:
    presets = AntiOcrPreset.objects.order_by("-is_default", "name")
    return render_manage(
        request,
        "backoffice/anti_ocr_preset_list.html",
        {
            "manage_section": "settings",
            "page_title": "Anti-OCR 參數集",
            "page_subtitle": "以可讀性優先調整桌機、手機的圖片寬度、字級與背景干擾。",
            "presets": presets,
        },
    )


def _render_preset_form(request: HttpRequest, preset: AntiOcrPreset | None = None) -> HttpResponse:
    form = AntiOcrPresetSimpleForm(request.POST or None, instance=preset)
    if request.method == "POST" and form.is_valid():
        preset = form.save()
        messages.success(request, f"已儲存參數集「{preset.name}」。")
        return redirect("backoffice:anti-ocr-update", preset_id=preset.id)

    return render_manage(
        request,
        "backoffice/anti_ocr_preset_form.html",
        {
            "manage_section": "settings",
            "page_title": "新增參數集" if preset is None else f"編輯參數集：{preset.name}",
            "page_subtitle": "建議先維持可讀性優先，再逐步調高干擾強度。",
            "form": form,
            "preset": preset,
        },
    )


@admin_required
@require_http_methods(["GET", "POST"])
def anti_ocr_preset_create(request: HttpRequest) -> HttpResponse:
    return _render_preset_form(request)


@admin_required
@require_http_methods(["GET", "POST"])
def anti_ocr_preset_update(request: HttpRequest, preset_id: int) -> HttpResponse:
    preset = get_object_or_404(AntiOcrPreset, pk=preset_id)
    return _render_preset_form(request, preset=preset)


@admin_required
@require_http_methods(["GET", "POST"])
def watermark_extract(request: HttpRequest) -> HttpResponse:
    form = WatermarkExtractToolForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        record = create_extraction_record(form.cleaned_data["image"], actor=request.user)
        try:
            run_watermark_extraction_task.delay(record.id)
        except Exception:
            run_watermark_extraction_task(record.id)
        messages.success(request, f"已建立提取任務 #{record.id}。")
        return redirect("backoffice:watermark-extract-detail", record_id=record.id)

    recent_records = WatermarkExtractionRecord.objects.select_related("created_by")[:10]
    return render_manage(
        request,
        "backoffice/watermark_extract.html",
        {
            "manage_section": "tools",
            "page_title": "浮水印提取工具",
            "page_subtitle": "先做完整原圖提取，失敗後再自動裁切，整個過程會留下可追蹤紀錄。",
            "form": form,
            "recent_records": recent_records,
            "active_record": None,
        },
    )


@admin_required
def watermark_extract_detail(request: HttpRequest, record_id: int) -> HttpResponse:
    record = get_object_or_404(WatermarkExtractionRecord.objects.select_related("created_by"), pk=record_id)
    recent_records = WatermarkExtractionRecord.objects.select_related("created_by")[:10]
    subtitle = "可查看目前執行進度、每一步處理方式與最後結果。"
    if record.status in {WatermarkExtractionRecord.Status.PENDING, WatermarkExtractionRecord.Status.RUNNING}:
        subtitle = "任務正在背景處理中，頁面會自動更新。"
    return render_manage(
        request,
        "backoffice/watermark_extract.html",
        {
            "manage_section": "tools",
            "page_title": f"浮水印提取紀錄 #{record.id}",
            "page_subtitle": subtitle,
            "form": WatermarkExtractToolForm(),
            "recent_records": recent_records,
            "active_record": record,
        },
    )
