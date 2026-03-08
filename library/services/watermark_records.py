from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from django.db.models import Q
from django.utils import timezone
from django.utils.text import get_valid_filename

from accounts.models import User
from library.models import AuditLog, WatermarkExtractionRecord

from .audit import log_event
from .storage import ensure_parent, media_relative
from .visible_watermark import extract_visible_watermark_from_path
from .watermark import extract_watermark_from_path

BLIND_EXTRACTION_KIND = "blind"
VISIBLE_EXTRACTION_KIND = "visible"

BLIND_UPLOAD_PREFIXES = ("watermark_extract_uploads/", "blind_watermark_extract_uploads/")
VISIBLE_UPLOAD_PREFIXES = ("visible_watermark_extract_uploads/",)


def get_extraction_kind_prefixes(kind: str) -> tuple[str, ...]:
    if kind == VISIBLE_EXTRACTION_KIND:
        return VISIBLE_UPLOAD_PREFIXES
    return BLIND_UPLOAD_PREFIXES


def get_extraction_kind_filter(kind: str) -> Q:
    query = Q()
    for prefix in get_extraction_kind_prefixes(kind):
        query |= Q(upload_relative_path__startswith=prefix)
    return query


def infer_extraction_kind(upload_relative_path: str) -> str:
    for prefix in VISIBLE_UPLOAD_PREFIXES:
        if upload_relative_path.startswith(prefix):
            return VISIBLE_EXTRACTION_KIND
    return BLIND_EXTRACTION_KIND


def extraction_upload_relative_path(filename: str, *, kind: str) -> str:
    safe_name = get_valid_filename(Path(filename).name) or "upload.png"
    today = timezone.localdate().strftime("%Y%m%d")
    root = "visible_watermark_extract_uploads" if kind == VISIBLE_EXTRACTION_KIND else "blind_watermark_extract_uploads"
    return media_relative(
        root,
        today,
        f"{timezone.now():%H%M%S}-{uuid4().hex[:12]}-{safe_name}",
    )


def create_extraction_record(
    uploaded_file,
    *,
    actor: User | None = None,
    kind: str = BLIND_EXTRACTION_KIND,
) -> WatermarkExtractionRecord:
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    file_bytes = uploaded_file.read()

    image = cv2.imdecode(np.frombuffer(file_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    image_width = image.shape[1] if image is not None else 0
    image_height = image.shape[0] if image is not None else 0

    relative_path = extraction_upload_relative_path(uploaded_file.name, kind=kind)
    absolute_path = ensure_parent(relative_path)
    absolute_path.write_bytes(file_bytes)

    tool_label = "可見浮水印" if kind == VISIBLE_EXTRACTION_KIND else "blind watermark"
    return WatermarkExtractionRecord.objects.create(
        created_by=actor,
        source_filename=uploaded_file.name,
        upload_relative_path=relative_path,
        image_width=image_width,
        image_height=image_height,
        process_log=[
            {
                "stage": "upload",
                "label": "已收到圖片",
                "success": True,
                "duration_ms": 0,
                "message": f"已上傳 {tool_label} 提取圖片，尺寸 {image_width}x{image_height}。",
            }
        ],
    )


def append_extraction_log(record: WatermarkExtractionRecord, entry: dict) -> None:
    current_log = list(record.process_log or [])
    current_log.append(entry)
    record.process_log = current_log
    record.save(update_fields=["process_log"])


def process_extraction_record(
    record_id: int,
    *,
    kind: str | None = None,
) -> WatermarkExtractionRecord:
    record = WatermarkExtractionRecord.objects.get(pk=record_id)
    extractor_kind = kind or infer_extraction_kind(record.upload_relative_path)
    extractor_label = "可見浮水印" if extractor_kind == VISIBLE_EXTRACTION_KIND else "blind watermark"

    record.status = WatermarkExtractionRecord.Status.RUNNING
    record.started_at = timezone.now()
    record.error_message = ""
    record.save(update_fields=["status", "started_at", "error_message"])
    append_extraction_log(
        record,
        {
            "stage": "start",
            "label": "開始提取",
            "success": True,
            "duration_ms": 0,
            "message": f"開始執行 {extractor_label} 提取流程。",
        },
    )

    def progress_callback(entry: dict) -> None:
        if entry.get("success") or entry.get("stage") in {"input", "window", "ocr", "source_match", "cropped"}:
            append_extraction_log(record, entry)

    try:
        if extractor_kind == VISIBLE_EXTRACTION_KIND:
            result = extract_visible_watermark_from_path(
                str(record.absolute_upload_path),
                progress_callback=progress_callback,
                debug_prefix=f"record-{record.id}",
            )
        else:
            result = extract_watermark_from_path(
                str(record.absolute_upload_path),
                progress_callback=progress_callback,
            )
    except Exception as exc:
        record.status = WatermarkExtractionRecord.Status.FAILED
        record.error_message = str(exc)
        record.finished_at = timezone.now()
        append_extraction_log(
            record,
            {
                "stage": "finish",
                "label": "提取失敗",
                "success": False,
                "duration_ms": 0,
                "message": f"提取流程發生錯誤：{exc}",
            },
        )
        record.save(update_fields=["status", "error_message", "finished_at"])
        return record

    record.raw_payload = result["raw_payload"]
    record.is_valid = result["is_valid"]
    record.selected_method = f"{extractor_kind} / {result['selected_method']}" if result["selected_method"] else extractor_kind
    record.attempt_count = result["attempt_count"]
    record.duration_ms = result["duration_ms"]
    record.finished_at = timezone.now()

    current_log = list(record.process_log or [])
    for entry in result["trace"][1:]:
        if entry not in current_log:
            current_log.append(entry)
    record.process_log = current_log

    if result["parsed"] is not None:
        record.parsed_reader_id = result["parsed"]["reader_id"]
        record.parsed_yyyymmdd = result["parsed"]["yyyymmdd"]
        record.status = WatermarkExtractionRecord.Status.SUCCEEDED
    else:
        record.status = WatermarkExtractionRecord.Status.FAILED

    record.process_log.append(
        {
            "stage": "finish",
            "label": "提取完成",
            "success": bool(result["parsed"] is not None),
            "duration_ms": 0,
            "message": (
                f"成功提取：{record.parsed_reader_id}|{record.parsed_yyyymmdd}"
                if result["parsed"] is not None
                else "未能提取出有效的 reader_id|yyyymmdd。"
            ),
        }
    )
    record.save(
        update_fields=[
            "raw_payload",
            "is_valid",
            "selected_method",
            "attempt_count",
            "duration_ms",
            "finished_at",
            "process_log",
            "parsed_reader_id",
            "parsed_yyyymmdd",
            "status",
        ]
    )

    log_event(
        AuditLog.EventType.WATERMARK_EXTRACTED,
        user=record.created_by,
        details={
            "record_id": record.id,
            "status": record.status,
            "is_valid": record.is_valid,
            "reader_id": record.parsed_reader_id,
            "yyyymmdd": record.parsed_yyyymmdd,
            "selected_method": record.selected_method,
            "attempt_count": record.attempt_count,
            "extractor_kind": extractor_kind,
        },
    )
    return record
