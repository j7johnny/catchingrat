from datetime import date

from celery import shared_task

from accounts.models import User
from library.models import ChapterVersion
from library.services.publishing import (
    build_remaining_daily_pages,
    cleanup_daily_cache,
    render_base_pages_for_version,
)
from library.services.watermark_records import process_extraction_record


@shared_task
def render_base_pages_task(chapter_version_id: int, device_profile: str) -> int:
    chapter_version = ChapterVersion.objects.get(pk=chapter_version_id)
    pages = render_base_pages_for_version(chapter_version, device_profile, force=True)
    return len(pages)


@shared_task
def build_daily_pages_task(
    chapter_version_id: int,
    reader_id: int,
    for_date_iso: str,
    device_profile: str,
    start_page: int = 1,
) -> None:
    chapter_version = ChapterVersion.objects.get(pk=chapter_version_id)
    reader = User.objects.get(pk=reader_id)
    build_remaining_daily_pages(
        chapter_version,
        reader,
        date.fromisoformat(for_date_iso),
        device_profile,
        start_page=start_page,
    )


@shared_task
def cleanup_daily_cache_task() -> int:
    return cleanup_daily_cache()


@shared_task
def run_watermark_extraction_task(record_id: int) -> int:
    record = process_extraction_record(record_id)
    return record.id
