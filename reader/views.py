from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from accounts.models import User
from library.models import AuditLog, Chapter, ChapterStatus, DeviceProfile, Novel
from library.services.access import (
    accessible_chapters_for_novel,
    accessible_novels_queryset,
    get_accessible_chapter_by_version,
    get_adjacent_chapters,
    reader_has_chapter_access,
)
from library.services.audit import log_event
from library.services.publishing import build_daily_page, ensure_daily_bundle
from library.services.signing import parse_signed_page_key


def set_private_no_store(response):
    response["Cache-Control"] = "private, no-store"
    response["Pragma"] = "no-cache"
    return response


def home(request):
    if not request.user.is_authenticated:
        return redirect("login")
    if request.user.role == User.Role.ADMIN:
        return redirect("/admin/")
    return redirect("reader:library")


def resolve_device_profile(request) -> str:
    requested = request.GET.get("device")
    if requested in DeviceProfile.values:
        return requested
    cookie_value = request.COOKIES.get("preferred_device")
    if cookie_value in DeviceProfile.values:
        return cookie_value
    user_agent = request.META.get("HTTP_USER_AGENT", "").lower()
    if any(keyword in user_agent for keyword in ("iphone", "android", "mobile")):
        return DeviceProfile.MOBILE
    return DeviceProfile.DESKTOP


def ensure_reader_access(user: User) -> None:
    if user.role != User.Role.READER:
        raise PermissionDenied


@login_required
def library_index(request):
    ensure_reader_access(request.user)
    novels = list(accessible_novels_queryset(request.user))
    response = render(request, "reader/library.html", {"novels": novels})
    return set_private_no_store(response)


@login_required
def novel_detail(request, novel_id: int):
    ensure_reader_access(request.user)
    novel = get_object_or_404(Novel, pk=novel_id, is_active=True)
    chapters = list(accessible_chapters_for_novel(request.user, novel))
    if not chapters:
        raise Http404
    response = render(
        request,
        "reader/novel_detail.html",
        {
            "novel": novel,
            "chapters": chapters,
        },
    )
    return set_private_no_store(response)


@login_required
def chapter_detail(request, chapter_id: int):
    ensure_reader_access(request.user)
    chapter = get_object_or_404(
        Chapter.objects.select_related("novel", "current_version"),
        pk=chapter_id,
        status=ChapterStatus.PUBLISHED,
    )
    if not reader_has_chapter_access(request.user, chapter):
        raise Http404
    if chapter.current_version is None:
        raise Http404

    device_profile = resolve_device_profile(request)
    bundle = ensure_daily_bundle(chapter.current_version, request.user, device_profile)
    previous_chapter, next_chapter = get_adjacent_chapters(request.user, chapter)
    page_urls = [
        reverse("reader:page", args=[bundle["signed_key"], page_index])
        for page_index in range(1, bundle["page_count"] + 1)
    ]
    base_pages = list(
        chapter.current_version.base_pages.filter(device_profile=device_profile)
        .order_by("page_index")
        .values("image_width", "image_height")
    )
    page_assets = []
    default_width = 600 if device_profile == DeviceProfile.DESKTOP else 420
    default_height = 290 if device_profile == DeviceProfile.DESKTOP else 250
    for index, page_url in enumerate(page_urls):
        page_meta = base_pages[index] if index < len(base_pages) else {}
        page_assets.append(
            {
                "url": page_url,
                "width": page_meta.get("image_width") or default_width,
                "height": page_meta.get("image_height") or default_height,
            }
        )
    log_event(
        AuditLog.EventType.CHAPTER_OPENED,
        user=request.user,
        request=request,
        details={
            "chapter_id": chapter.id,
            "chapter_version_id": chapter.current_version_id,
            "device_profile": device_profile,
        },
    )
    response = render(
        request,
        "reader/chapter_detail.html",
        {
            "chapter": chapter,
            "device_profile": device_profile,
            "page_assets": page_assets,
            "desktop_switch_url": f"{reverse('reader:chapter-detail', args=[chapter.id])}?device=desktop",
            "mobile_switch_url": f"{reverse('reader:chapter-detail', args=[chapter.id])}?device=mobile",
            "previous_chapter": previous_chapter,
            "next_chapter": next_chapter,
            "novel_detail_url": reverse("reader:novel-detail", args=[chapter.novel_id]),
        },
    )
    response.set_cookie("preferred_device", device_profile, max_age=60 * 60 * 24 * 30, samesite="Lax")
    return set_private_no_store(response)


@login_required
def reader_page_image(request, signed_key: str, page_index: int):
    ensure_reader_access(request.user)
    try:
        version_id, reader_id, for_date, device_profile = parse_signed_page_key(signed_key)
    except Exception as exc:
        raise Http404 from exc

    if reader_id != request.user.reader_id:
        raise Http404

    chapter = get_accessible_chapter_by_version(request.user, version_id)
    if chapter is None or chapter.current_version_id != version_id:
        raise Http404

    page = build_daily_page(chapter.current_version, request.user, for_date, device_profile, page_index)
    response = FileResponse(open(page.absolute_path, "rb"), content_type="image/png")
    response["Content-Disposition"] = f'inline; filename="page-{page_index}.png"'
    return set_private_no_store(response)
