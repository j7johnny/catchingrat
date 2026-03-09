from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_http_methods

from library.models import Chapter
from library.services.publishing import schedule_chapter_publish


@staff_member_required
@require_http_methods(["GET", "POST"])
def publish_chapter_view(request, pk: int):
    chapter = get_object_or_404(Chapter, pk=pk)
    try:
        job = schedule_chapter_publish(chapter, actor=request.user, request=request)
    except ValueError as exc:
        messages.error(request, str(exc))
    except Exception as exc:
        messages.error(request, f"發布失敗：{exc}")
    else:
        if job.status in {"pending", "running"}:
            messages.success(request, f"章節「{chapter.title}」已加入背景發布佇列。")
        else:
            messages.success(request, f"章節「{chapter.title}」發布完成。")
    return redirect(f"/admin/library/chapter/{chapter.pk}/change/")


@staff_member_required
@require_http_methods(["GET", "POST"])
def watermark_extract_view(request):
    return redirect("backoffice:watermark-extract")


@staff_member_required
@require_http_methods(["GET", "POST"])
def visible_watermark_extract_view(request):
    return redirect("backoffice:visible-watermark-extract")


@staff_member_required
@require_http_methods(["GET", "POST"])
def anti7ocr_diagnostics_view(request):
    return redirect("backoffice:anti7ocr-diagnostics")


@staff_member_required
@require_http_methods(["GET", "POST"])
def publish_chapter_view(request, pk: int):
    chapter = get_object_or_404(Chapter, pk=pk)
    try:
        job = schedule_chapter_publish(chapter, actor=request.user, request=request)
    except ValueError as exc:
        messages.error(request, str(exc))
    except Exception as exc:
        messages.error(request, f"發布失敗：{exc}")
    else:
        if job.status in {"pending", "running"}:
            messages.success(request, f"章節「{chapter.title}」已加入背景發布佇列。")
        else:
            messages.success(request, f"章節「{chapter.title}」發布完成。")
    return redirect(f"/admin/library/chapter/{chapter.pk}/change/")
