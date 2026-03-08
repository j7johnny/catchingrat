from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from django.utils import timezone
from django.utils.text import get_valid_filename

from accounts.models import User
from library.models import AuditLog, WatermarkExtractionRecord

from .audit import log_event
from .storage import ensure_parent, media_relative
from .watermark import extract_watermark_from_path


def extraction_upload_relative_path(filename: str) -> str:
    safe_name = get_valid_filename(Path(filename).name) or "upload.png"
    today = timezone.localdate().strftime("%Y%m%d")
    return media_relative(
        "watermark_extract_uploads",
        today,
        f"{timezone.now():%H%M%S}-{uuid4().hex[:12]}-{safe_name}",
    )


def create_extraction_record(uploaded_file, actor: User | None = None) -> WatermarkExtractionRecord:
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    file_bytes = uploaded_file.read()

    image = cv2.imdecode(np.frombuffer(file_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    image_width = image.shape[1] if image is not None else 0
    image_height = image.shape[0] if image is not None else 0

    relative_path = extraction_upload_relative_path(uploaded_file.name)
    absolute_path = ensure_parent(relative_path)
    absolute_path.write_bytes(file_bytes)

    return WatermarkExtractionRecord.objects.create(
        created_by=actor,
        source_filename=uploaded_file.name,
        upload_relative_path=relative_path,
        image_width=image_width,
        image_height=image_height,
        process_log=[
            {
                "stage": "upload",
                "label": "收到上傳檔案",
                "success": True,
                "duration_ms": 0,
                "message": f"已收到圖片，尺寸 {image_width}x{image_height}。",
            }
        ],
    )


def append_extraction_log(record: WatermarkExtractionRecord, entry: dict) -> None:
    current_log = list(record.process_log or [])
    current_log.append(entry)
    record.process_log = current_log
    record.save(update_fields=["process_log"])


def process_extraction_record(record_id: int) -> WatermarkExtractionRecord:
    record = WatermarkExtractionRecord.objects.get(pk=record_id)
    record.status = WatermarkExtractionRecord.Status.RUNNING
    record.started_at = timezone.now()
    record.error_message = ""
    record.save(update_fields=["status", "started_at", "error_message"])
    append_extraction_log(
        record,
        {
            "stage": "start",
            "label": "開始背景提取",
            "success": True,
            "duration_ms": 0,
            "message": "先嘗試完整原圖提取；若失敗，會再進入自動裁切與多圖拼接判讀。",
        },
    )

    try:
        result = extract_watermark_from_path(str(record.absolute_upload_path))
    except Exception as exc:
        record.status = WatermarkExtractionRecord.Status.FAILED
        record.error_message = str(exc)
        record.finished_at = timezone.now()
        append_extraction_log(
            record,
            {
                "stage": "finish",
                "label": "提取結束",
                "success": False,
                "duration_ms": 0,
                "message": f"提取時發生錯誤：{exc}",
            },
        )
        record.save(update_fields=["status", "error_message", "finished_at"])
        return record

    record.raw_payload = result["raw_payload"]
    record.is_valid = result["is_valid"]
    record.selected_method = result["selected_method"]
    record.attempt_count = result["attempt_count"]
    record.duration_ms = result["duration_ms"]
    record.finished_at = timezone.now()
    record.process_log = list(record.process_log or []) + result["trace"][1:]
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
                f"成功解析為 {record.parsed_reader_id}|{record.parsed_yyyymmdd}。"
                if result["parsed"] is not None
                else "已完成所有嘗試，但仍無法穩定還原浮水印。"
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
        },
    )
    return record
