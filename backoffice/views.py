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
from library.models import AntiOcrPreset, Chapter, ChapterStatus, CustomFontUpload, Novel, WatermarkExtractionRecord
from library.services.anti7ocr_config import summarize_preset
from library.services.anti7ocr_diagnostics import generate_preview, run_diagnostics
from library.services.publishing import publish_chapter
from library.services.watermark_records import (
    BLIND_EXTRACTION_KIND,
    VISIBLE_EXTRACTION_KIND,
    create_extraction_record,
    get_extraction_kind_filter,
)
from library.tasks import run_watermark_extraction_task

from .forms import (
    Anti7OcrDiagnosticsForm,
    AntiOcrPresetSimpleForm,
    ChapterBackofficeForm,
    CustomFontUploadForm,
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
        "page_title": "管理後台",
        "page_subtitle": "在這裡管理閱讀者、小說、章節、anti7ocr 設定與各種提取工具。",
        "font_summary": {
            "total": CustomFontUpload.objects.count(),
            "active": CustomFontUpload.objects.filter(is_active=True).count(),
        },
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
        messages.success(request, "第一位管理者已建立完成，現在可以開始設定小說與閱讀者。")
        return redirect("backoffice:dashboard")

    return render(
        request,
        "backoffice/setup.html",
        {
            "form": form,
            "page_title": "建立第一位管理者",
            "page_subtitle": "這台站點目前還沒有管理者帳號，請先完成初始化設定。",
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
        "page_title": "管理儀表板",
        "page_subtitle": "快速查看目前站點內容與常用操作入口。",
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
            "page_subtitle": "建立閱讀者、重設密碼，並設定全站、小說或章節授權。",
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
        access_form.reader = reader
        access_form.save(actor=request.user)
        messages.success(request, f"已建立閱讀者 {reader.username}")
        return redirect("backoffice:reader-update", user_id=reader.id)

    return render_manage(
        request,
        "backoffice/reader_form.html",
        {
            "manage_section": "readers",
            "page_title": "新增閱讀者",
            "page_subtitle": "建立新帳號，並直接設定可閱讀的範圍。",
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
        form.save()
        access_form.save(actor=request.user)
        messages.success(request, f"已更新閱讀者 {reader.username}")
        return redirect("backoffice:reader-update", user_id=reader.id)

    return render_manage(
        request,
        "backoffice/reader_form.html",
        {
            "manage_section": "readers",
            "page_title": f"編輯閱讀者：{reader.username}",
            "page_subtitle": "可在此更新密碼、啟用狀態與閱讀授權。",
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
            "page_subtitle": "建立小說、查看章節數量，並進入章節編輯。",
            "novels": novels,
        },
    )


@admin_required
@require_http_methods(["GET", "POST"])
def novel_create(request: HttpRequest) -> HttpResponse:
    form = NovelBackofficeForm(request.POST or None, initial={"is_active": True})
    if request.method == "POST" and form.is_valid():
        novel = form.save()
        messages.success(request, f"已建立小說 {novel.title}")
        return redirect("backoffice:novel-detail", novel_id=novel.id)

    return render_manage(
        request,
        "backoffice/novel_form.html",
        {
            "manage_section": "novels",
            "page_title": "新增小說",
            "page_subtitle": "建立小說名稱、代稱與簡介。",
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
        form.save()
        messages.success(request, f"已更新小說 {novel.title}")
        return redirect("backoffice:novel-detail", novel_id=novel.id)

    chapters = novel.chapters.select_related("current_version").order_by("sort_order", "id")
    return render_manage(
        request,
        "backoffice/novel_form.html",
        {
            "manage_section": "novels",
            "page_title": f"小說：{novel.title}",
            "page_subtitle": "可直接在此查看章節排序、發布狀態與目前版本。",
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
            except Exception as exc:
                messages.error(request, f"發布失敗：{exc}")
            else:
                messages.success(
                    request,
                    f"已發布章節 {chapter.title}，版本 v{version.version_number}。桌機與手機基底圖都完成後才會對閱讀者開放。",
                )
        else:
            messages.success(request, "章節草稿已儲存。")
        return redirect("backoffice:chapter-detail", chapter_id=chapter.id)

    return render_manage(
        request,
        "backoffice/chapter_form.html",
        {
            "manage_section": "novels",
            "page_title": "新增章節" if chapter is None else f"編輯章節：{chapter.title}",
            "page_subtitle": "貼入正文、選擇 anti7ocr 設定，並可直接儲存草稿或發布。",
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
                "page_subtitle": "建立草稿後，即可在同頁直接發布。",
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
    except Exception as exc:
        messages.error(request, f"發布失敗：{exc}")
    else:
        messages.success(request, f"已發布章節 {chapter.title}，版本 v{version.version_number}")
    return redirect("backoffice:novel-detail", novel_id=chapter.novel_id)


@admin_required
def anti_ocr_preset_list(request: HttpRequest) -> HttpResponse:
    preset_cards = [
        {"preset": preset, "summary": summarize_preset(preset.as_snapshot())}
        for preset in AntiOcrPreset.objects.order_by("-is_default", "name")
    ]
    fonts = CustomFontUpload.objects.order_by("name")
    return render_manage(
        request,
        "backoffice/anti_ocr_preset_list.html",
        {
            "manage_section": "settings",
            "page_title": "anti7ocr 設定",
            "page_subtitle": "管理輸出參數、上傳字體，並先用示範圖片確認效果。",
            "preset_cards": preset_cards,
            "fonts": fonts,
            "font_form": CustomFontUploadForm(),
        },
    )


def _render_preset_form(request: HttpRequest, preset: AntiOcrPreset | None = None) -> HttpResponse:
    form = AntiOcrPresetSimpleForm(request.POST or None, instance=preset)
    preview_result = None
    if request.method == "POST" and form.is_valid():
        action = request.POST.get("action", "save")
        if action == "preview":
            preview_result = generate_preview(
                snapshot=form.prepared_snapshot,
                text=form.cleaned_data.get("preview_text") or "",
                device_profile=form.cleaned_data["preview_device_profile"],
                output_prefix=f"preset-preview-{preset.id if preset else 'new'}",
            )
            messages.success(request, "示範圖片已產生，可先檢查閱讀效果再決定是否儲存。")
        else:
            saved_preset = form.save()
            messages.success(request, f"已儲存 anti7ocr 設定：{saved_preset.name}")
            return redirect("backoffice:anti-ocr-update", preset_id=saved_preset.id)

    return render_manage(
        request,
        "backoffice/anti_ocr_preset_form.html",
        {
            "manage_section": "settings",
            "page_title": "新增 anti7ocr 設定" if preset is None else f"編輯 anti7ocr 設定：{preset.name}",
            "page_subtitle": "表單已依閱讀性與實際用途分組，並可先產出示範圖片再儲存。",
            "form": form,
            "preset": preset,
            "preview_result": preview_result,
            "fonts": CustomFontUpload.objects.order_by("name"),
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
def font_library(request: HttpRequest) -> HttpResponse:
    form = CustomFontUploadForm(request.POST or None, request.FILES or None, initial={"is_active": True})
    if request.method == "POST" and form.is_valid():
        font = form.save()
        messages.success(request, f"已上傳字體 {font.name}")
        return redirect("backoffice:font-library")

    return render_manage(
        request,
        "backoffice/font_library.html",
        {
            "manage_section": "settings",
            "page_title": "字體管理",
            "page_subtitle": "上傳可供 anti7ocr 使用的自訂字體，並控制是否啟用。",
            "form": form,
            "fonts": CustomFontUpload.objects.order_by("name"),
        },
    )


@admin_required
@require_http_methods(["POST"])
def font_toggle(request: HttpRequest, font_id: int) -> HttpResponse:
    font = get_object_or_404(CustomFontUpload, pk=font_id)
    font.is_active = not font.is_active
    font.save(update_fields=["is_active", "updated_at"])
    status_text = "啟用" if font.is_active else "停用"
    messages.success(request, f"已{status_text}字體 {font.name}")
    return redirect("backoffice:font-library")


@admin_required
@require_http_methods(["POST"])
def font_delete(request: HttpRequest, font_id: int) -> HttpResponse:
    font = get_object_or_404(CustomFontUpload, pk=font_id)
    font_name = font.name
    font.font_file.delete(save=False)
    font.delete()
    messages.success(request, f"已刪除字體 {font_name}")
    return redirect("backoffice:font-library")


@admin_required
@require_http_methods(["GET", "POST"])
def anti7ocr_diagnostics(request: HttpRequest) -> HttpResponse:
    form = Anti7OcrDiagnosticsForm(request.POST or None)
    result = None
    if request.method == "POST" and form.is_valid():
        try:
            result = run_diagnostics(
                text=form.cleaned_data["text"],
                preset=form.cleaned_data["preset"],
                device_profile=form.cleaned_data["device_profile"],
                seed=form.cleaned_data.get("seed"),
                sensitive_keywords=form.cleaned_data["sensitive_keywords"],
            )
        except Exception as exc:
            messages.error(request, f"診斷失敗：{exc}")
        else:
            messages.success(request, "anti7ocr 診斷完成。")

    return render_manage(
        request,
        "backoffice/anti7ocr_diagnostics.html",
        {
            "manage_section": "tools",
            "page_title": "anti7ocr 診斷工具",
            "page_subtitle": "輸入測試文字，系統會產生示範圖並跑 Tesseract OCR 與 CER 分析。",
            "form": form,
            "result": result,
        },
    )


def _watermark_tool_meta(kind: str) -> dict:
    if kind == VISIBLE_EXTRACTION_KIND:
        return {
            "kind": VISIBLE_EXTRACTION_KIND,
            "title": "可見浮水印提取",
            "subtitle": "上傳閱讀頁截圖或站內原圖，系統會做顯影與 OCR，提取 reader_id|yyyymmdd。",
            "detail_name": "backoffice:visible-watermark-extract-detail",
            "tool_label": "可見浮水印",
        }
    return {
        "kind": BLIND_EXTRACTION_KIND,
        "title": "Blind Watermark 提取",
        "subtitle": "上傳站內原圖、截圖或長截圖，系統會執行 blind watermark 提取流程。",
        "detail_name": "backoffice:watermark-extract-detail",
        "tool_label": "blind watermark",
    }


def _render_watermark_tool(request: HttpRequest, *, kind: str, record_id: int | None = None) -> HttpResponse:
    tool_meta = _watermark_tool_meta(kind)
    form = WatermarkExtractToolForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        record = create_extraction_record(form.cleaned_data["image"], actor=request.user, kind=kind)
        try:
            run_watermark_extraction_task.delay(record.id, kind)
        except Exception:
            run_watermark_extraction_task(record.id, kind)
        messages.success(request, f"已建立{tool_meta['tool_label']}提取任務 #{record.id}")
        return redirect(tool_meta["detail_name"], record_id=record.id)

    recent_records = WatermarkExtractionRecord.objects.select_related("created_by").filter(
        get_extraction_kind_filter(kind)
    )[:10]
    active_record = None
    if record_id is not None:
        active_record = get_object_or_404(
            WatermarkExtractionRecord.objects.select_related("created_by").filter(get_extraction_kind_filter(kind)),
            pk=record_id,
        )

    subtitle = tool_meta["subtitle"]
    if active_record and active_record.status in {
        WatermarkExtractionRecord.Status.PENDING,
        WatermarkExtractionRecord.Status.RUNNING,
    }:
        subtitle = "提取仍在進行中，頁面會每 2 秒自動刷新一次。"

    return render_manage(
        request,
        "backoffice/watermark_extract.html",
        {
            "manage_section": "tools",
            "page_title": tool_meta["title"] if active_record is None else f"{tool_meta['title']} #{active_record.id}",
            "page_subtitle": subtitle,
            "form": form if active_record is None else WatermarkExtractToolForm(),
            "recent_records": recent_records,
            "active_record": active_record,
            "tool_meta": tool_meta,
            "extractor_kind": kind,
        },
    )


@admin_required
@require_http_methods(["GET", "POST"])
def watermark_extract(request: HttpRequest) -> HttpResponse:
    return _render_watermark_tool(request, kind=BLIND_EXTRACTION_KIND)


@admin_required
def watermark_extract_detail(request: HttpRequest, record_id: int) -> HttpResponse:
    return _render_watermark_tool(request, kind=BLIND_EXTRACTION_KIND, record_id=record_id)


@admin_required
@require_http_methods(["GET", "POST"])
def visible_watermark_extract(request: HttpRequest) -> HttpResponse:
    return _render_watermark_tool(request, kind=VISIBLE_EXTRACTION_KIND)


@admin_required
def visible_watermark_extract_detail(request: HttpRequest, record_id: int) -> HttpResponse:
    return _render_watermark_tool(request, kind=VISIBLE_EXTRACTION_KIND, record_id=record_id)
