from django.contrib import admin
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from library.forms import WatermarkExtractForm
from library.models import AuditLog, Chapter
from library.services.audit import log_event
from library.services.publishing import publish_chapter
from library.services.watermark import extract_watermark


@staff_member_required
@require_http_methods(["GET", "POST"])
def publish_chapter_view(request, pk: int):
    chapter = get_object_or_404(Chapter, pk=pk)
    try:
        version = publish_chapter(chapter, actor=request.user, request=request)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"已發布 {chapter.title}，版本 v{version.version_number}。")
    return redirect(f"/admin/library/chapter/{chapter.pk}/change/")


@staff_member_required
@require_http_methods(["GET", "POST"])
def watermark_extract_view(request):
    form = WatermarkExtractForm(request.POST or None, request.FILES or None)
    result = None
    if request.method == "POST" and form.is_valid():
        raw_payload, parsed = extract_watermark(form.cleaned_data["image"])
        result = {
            "raw_payload": raw_payload.replace("\x00", ""),
            "parsed": parsed,
            "is_valid": parsed is not None,
        }
        log_event(
            AuditLog.EventType.WATERMARK_EXTRACTED,
            user=request.user,
            request=request,
            details={"result": result},
        )
    context = {**admin.site.each_context(request), "title": "浮水印提取", "form": form, "result": result}
    return render(request, "admin/watermark_extract.html", context)
