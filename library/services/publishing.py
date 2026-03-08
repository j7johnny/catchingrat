from __future__ import annotations

import contextlib
from datetime import date, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from accounts.models import User
from library.models import BasePage, Chapter, ChapterStatus, ChapterVersion, DailyPageCache, DeviceProfile

from .antiocr import (
    base_pages_need_regeneration,
    build_source_sha256,
    get_default_preset,
    render_chapter_page_images,
    save_base_page_image,
)
from .audit import log_event
from .signing import build_signed_page_key
from .storage import delete_relative_path, ensure_parent, media_relative
from .watermark import build_watermark_payload, embed_watermark

daily_page_layout_version = "v3"


def _maybe_enqueue(task, *args):
    if settings.CELERY_TASK_ALWAYS_EAGER:
        return
    with contextlib.suppress(Exception):
        task.delay(*args)


def delete_queryset_files(queryset) -> None:
    for item in queryset:
        delete_relative_path(item.relative_path)
    queryset.delete()


def purge_old_assets_for_chapter(chapter: Chapter, keep_version_id: int) -> None:
    old_versions = chapter.versions.exclude(id=keep_version_id)
    delete_queryset_files(BasePage.objects.filter(chapter_version__in=old_versions))
    delete_queryset_files(DailyPageCache.objects.filter(chapter_version__in=old_versions))


@transaction.atomic
def publish_chapter(chapter: Chapter, actor: User | None = None, request=None) -> ChapterVersion:
    if not chapter.content.strip():
        raise ValueError("Chapter content cannot be empty.")
    preset = chapter.anti_ocr_preset or get_default_preset()
    latest_version = chapter.versions.aggregate(max_version=Max("version_number"))["max_version"] or 0
    version = ChapterVersion.objects.create(
        chapter=chapter,
        version_number=latest_version + 1,
        content=chapter.content,
        source_sha256=build_source_sha256(chapter.content),
        preset_snapshot=preset.as_snapshot(),
        created_by=actor,
        published_at=timezone.now(),
    )
    chapter.current_version = version
    chapter.status = ChapterStatus.PUBLISHED
    chapter.published_at = timezone.now()
    chapter.save(update_fields=["current_version", "status", "published_at", "updated_at"])
    purge_old_assets_for_chapter(chapter, version.id)

    from library.tasks import render_base_pages_task

    _maybe_enqueue(render_base_pages_task, version.id, DeviceProfile.DESKTOP)
    _maybe_enqueue(render_base_pages_task, version.id, DeviceProfile.MOBILE)
    log_event(
        "chapter_published",
        user=actor,
        request=request,
        details={"chapter_id": chapter.id, "chapter_version_id": version.id},
    )
    return version


def render_base_pages_for_version(chapter_version: ChapterVersion, device_profile: str, force: bool = False) -> list[BasePage]:
    if force:
        delete_queryset_files(
            BasePage.objects.filter(chapter_version=chapter_version, device_profile=device_profile)
        )

    rendered_pages = render_chapter_page_images(
        chapter_version.content,
        chapter_version.preset_snapshot,
        device_profile,
    )

    pages: list[BasePage] = []
    try:
        for index, (image, char_count) in enumerate(rendered_pages, start=1):
            pages.append(save_base_page_image(chapter_version, device_profile, index, image, char_count))
            image.close()
    finally:
        for image, _ in rendered_pages[len(pages):]:
            image.close()

    stale_pages = BasePage.objects.filter(
        chapter_version=chapter_version,
        device_profile=device_profile,
        page_index__gt=len(rendered_pages),
    )
    delete_queryset_files(stale_pages)
    return pages


def ensure_base_pages(chapter_version: ChapterVersion, device_profile: str) -> list[BasePage]:
    pages = list(
        BasePage.objects.filter(
            chapter_version=chapter_version,
            device_profile=device_profile,
        ).order_by("page_index")
    )
    if base_pages_need_regeneration(pages, device_profile, chapter_version.preset_snapshot):
        return render_base_pages_for_version(chapter_version, device_profile, force=True)
    return pages


def ensure_base_page(chapter_version: ChapterVersion, device_profile: str, page_index: int) -> BasePage:
    pages = ensure_base_pages(chapter_version, device_profile)
    if page_index < 1 or page_index > len(pages):
        raise IndexError("page_index out of range")
    return pages[page_index - 1]


def get_page_count(chapter_version: ChapterVersion, device_profile: str) -> int:
    return len(ensure_base_pages(chapter_version, device_profile))


def daily_page_relative_path(
    chapter_version_id: int,
    reader_id: int,
    for_date: date,
    device_profile: str,
    page_index: int,
) -> str:
    return media_relative(
        "daily_pages",
        daily_page_layout_version,
        for_date.strftime("%Y%m%d"),
        f"reader_{reader_id}",
        f"version_{chapter_version_id}",
        device_profile,
        f"page_{page_index:04d}.png",
    )


def build_daily_page(
    chapter_version: ChapterVersion,
    reader: User,
    for_date: date,
    device_profile: str,
    page_index: int,
) -> DailyPageCache:
    page = DailyPageCache.objects.filter(
        chapter_version=chapter_version,
        reader=reader,
        for_date=for_date,
        device_profile=device_profile,
        page_index=page_index,
    ).first()
    expected_prefix = f"daily_pages/{daily_page_layout_version}/"
    if page and page.absolute_path.exists() and page.relative_path.startswith(expected_prefix):
        return page

    base_page = ensure_base_page(chapter_version, device_profile, page_index)
    relative_path = daily_page_relative_path(chapter_version.id, reader.id, for_date, device_profile, page_index)
    absolute_path = ensure_parent(relative_path)
    payload = build_watermark_payload(reader.reader_id, for_date)
    embed_watermark(str(base_page.absolute_path), str(absolute_path), payload)

    if page and page.relative_path != relative_path:
        delete_relative_path(page.relative_path)

    page, _ = DailyPageCache.objects.update_or_create(
        chapter_version=chapter_version,
        reader=reader,
        for_date=for_date,
        device_profile=device_profile,
        page_index=page_index,
        defaults={"relative_path": relative_path},
    )
    return page


def ensure_daily_bundle(
    chapter_version: ChapterVersion,
    reader: User,
    device_profile: str,
    for_date: date | None = None,
) -> dict:
    for_date = for_date or timezone.localdate()
    page_count = get_page_count(chapter_version, device_profile)
    first_page = build_daily_page(chapter_version, reader, for_date, device_profile, 1)

    from library.tasks import build_daily_pages_task

    if page_count > 1:
        _maybe_enqueue(
            build_daily_pages_task,
            chapter_version.id,
            reader.id,
            for_date.isoformat(),
            device_profile,
            2,
        )

    return {
        "first_page": first_page,
        "page_count": page_count,
        "signed_key": build_signed_page_key(chapter_version.id, reader.reader_id, for_date, device_profile),
    }


def build_remaining_daily_pages(
    chapter_version: ChapterVersion,
    reader: User,
    for_date: date,
    device_profile: str,
    start_page: int = 1,
) -> None:
    page_count = get_page_count(chapter_version, device_profile)
    for page_index in range(start_page, page_count + 1):
        build_daily_page(chapter_version, reader, for_date, device_profile, page_index)


def cleanup_daily_cache() -> int:
    cutoff = timezone.localdate() - timedelta(days=settings.DAILY_CACHE_RETENTION_DAYS)
    queryset = DailyPageCache.objects.filter(for_date__lt=cutoff)
    count = queryset.count()
    delete_queryset_files(queryset)
    return count
