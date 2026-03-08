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
from library.services.watermark_records import create_extraction_record
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
        "page_subtitle": "這裡提供日常管理、章節發布、anti7ocr 設定與浮水印工具。",
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
        messages.success(request, "第一位管理者已建立完成，現在可以進入管理後台。")
        return redirect("backoffice:dashboard")

    return render(
        request,
        "backoffice/setup.html",
        {
            "form": form,
            "page_title": "建立第一位管理者",
            "page_subtitle": "只有第一次開站時可使用。完成後 `/setup/` 會自動關閉。",
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
        "page_subtitle": "建議由這裡開始：先新增閱讀者，再建立小說與章節，最後發布並檢查浮水印提取。",
        "stats": [
            {"label": "閱讀者帳號", "value": User.objects.filter(role=User.Role.READER).count()},
            {"label": "小說總數", "value": Novel.objects.count()},
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
            "page_subtitle": "建立閱讀者、重設密碼，並設定全站 / 指定小說 / 指定章節授權。",
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
        messages.success(request, f"已建立閱讀者帳號：{reader.username}")
        return redirect("backoffice:reader-update", user_id=reader.id)

    return render_manage(
        request,
        "backoffice/reader_form.html",
        {
            "manage_section": "readers",
            "page_title": "新增閱讀者",
            "page_subtitle": "建立帳號後，可以立刻設定授權範圍。",
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
        messages.success(request, f"已更新閱讀者帳號：{reader.username}")
        return redirect("backoffice:reader-update", user_id=reader.id)

    return render_manage(
        request,
        "backoffice/reader_form.html",
        {
            "manage_section": "readers",
            "page_title": f"編輯閱讀者：{reader.username}",
            "page_subtitle": "可在這裡重設密碼與調整授權。",
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
            "page_subtitle": "先建立小說，再進入小說頁建立章節、編輯內容與發布。",
            "novels": novels,
        },
    )


@admin_required
@require_http_methods(["GET", "POST"])
def novel_create(request: HttpRequest) -> HttpResponse:
    form = NovelBackofficeForm(request.POST or None, initial={"is_active": True})
    if request.method == "POST" and form.is_valid():
        novel = form.save()
        messages.success(request, f"已建立小說：{novel.title}")
        return redirect("backoffice:novel-detail", novel_id=novel.id)

    return render_manage(
        request,
        "backoffice/novel_form.html",
        {
            "manage_section": "novels",
            "page_title": "新增小說",
            "page_subtitle": "小說建立完成後，就能直接新增章節。",
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
        messages.success(request, f"已更新小說：{novel.title}")
        return redirect("backoffice:novel-detail", novel_id=novel.id)

    chapters = novel.chapters.select_related("current_version").order_by("sort_order", "id")
    return render_manage(
        request,
        "backoffice/novel_form.html",
        {
            "manage_section": "novels",
            "page_title": f"小說：{novel.title}",
            "page_subtitle": "在這裡編輯小說資訊、查看章節清單，或直接建立新章節。",
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
                    f"已完成發布：{chapter.title}（版本 v{version.version_number}）。桌機與手機基底圖都已準備完成，讀者現在才會看得到。",
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
            "page_subtitle": "發布時會先產生桌機與手機兩套基底圖。只有全部完成後，讀者才會看到新版本。",
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
                "page_subtitle": "先存草稿，確認 anti7ocr 設定後再正式發布。",
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
        messages.success(
            request,
            f"已完成發布：{chapter.title}（版本 v{version.version_number}）。桌機與手機基底圖都已完成。",
        )
    return redirect("backoffice:novel-detail", novel_id=chapter.novel_id)


@admin_required
def anti_ocr_preset_list(request: HttpRequest) -> HttpResponse:
    preset_cards = [{"preset": preset, "summary": summarize_preset(preset.as_snapshot())} for preset in AntiOcrPreset.objects.order_by("-is_default", "name")]
    fonts = CustomFontUpload.objects.order_by("name")
    return render_manage(
        request,
        "backoffice/anti_ocr_preset_list.html",
        {
            "manage_section": "settings",
            "page_title": "anti7ocr 設定",
            "page_subtitle": "管理全站 anti7ocr 參數、上傳自訂字體，並用示範圖片快速確認可讀性。",
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
            messages.success(request, "示範圖片已產生，可直接用來檢查字級與干擾強度。")
        else:
            saved_preset = form.save()
            messages.success(request, f"已儲存設定：{saved_preset.name}")
            return redirect("backoffice:anti-ocr-update", preset_id=saved_preset.id)

    return render_manage(
        request,
        "backoffice/anti_ocr_preset_form.html",
        {
            "manage_section": "settings",
            "page_title": "新增 anti7ocr 設定" if preset is None else f"編輯 anti7ocr 設定：{preset.name}",
            "page_subtitle": "先按示範圖片檢查閱讀感，再正式儲存。字體來源會自動包含系統字體與你上傳的自訂字體。",
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
        messages.success(request, f"已上傳字體：{font.name}")
        return redirect("backoffice:font-library")

    return render_manage(
        request,
        "backoffice/font_library.html",
        {
            "manage_section": "settings",
            "page_title": "字體庫",
            "page_subtitle": "上傳後的字體會自動加入 anti7ocr 可用字體來源，示範圖與正式發布都會使用。",
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
    messages.success(request, f"已{'啟用' if font.is_active else '停用'}字體：{font.name}")
    return redirect("backoffice:font-library")


@admin_required
@require_http_methods(["POST"])
def font_delete(request: HttpRequest, font_id: int) -> HttpResponse:
    font = get_object_or_404(CustomFontUpload, pk=font_id)
    font_name = font.name
    font.font_file.delete(save=False)
    font.delete()
    messages.success(request, f"已刪除字體：{font_name}")
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
            "page_subtitle": "輸入一段文字後，系統會產生示範圖、跑 Tesseract OCR，並顯示 CER 與詳細 metadata。",
            "form": form,
            "result": result,
        },
    )


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
        messages.success(request, f"已建立提取任務 #{record.id}")
        return redirect("backoffice:watermark-extract-detail", record_id=record.id)

    recent_records = WatermarkExtractionRecord.objects.select_related("created_by")[:10]
    return render_manage(
        request,
        "backoffice/watermark_extract.html",
        {
            "manage_section": "tools",
            "page_title": "blind watermark 提取",
            "page_subtitle": "系統會先做全圖提取，失敗後再改做大量裁切搜尋。適合原圖、單張截圖與長截圖。",
            "form": form,
            "recent_records": recent_records,
            "active_record": None,
        },
    )


@admin_required
def watermark_extract_detail(request: HttpRequest, record_id: int) -> HttpResponse:
    record = get_object_or_404(WatermarkExtractionRecord.objects.select_related("created_by"), pk=record_id)
    recent_records = WatermarkExtractionRecord.objects.select_related("created_by")[:10]
    subtitle = "這裡會顯示本次提取的圖片資訊、採用方法與每一步的處理紀錄。"
    if record.status in {WatermarkExtractionRecord.Status.PENDING, WatermarkExtractionRecord.Status.RUNNING}:
        subtitle = "提取任務仍在執行中，頁面會自動刷新以更新進度。"
    return render_manage(
        request,
        "backoffice/watermark_extract.html",
        {
            "manage_section": "tools",
            "page_title": f"提取紀錄 #{record.id}",
            "page_subtitle": subtitle,
            "form": WatermarkExtractToolForm(),
            "recent_records": recent_records,
            "active_record": record,
        },
    )
