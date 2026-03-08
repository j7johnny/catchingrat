from __future__ import annotations

from collections import Counter
import contextlib
from datetime import datetime, timedelta
from difflib import SequenceMatcher
import re
import time

import cv2
import numpy as np
from blind_watermark import WaterMark
from django.conf import settings
from django.utils import timezone

from accounts.models import User
from library.models import DailyPageCache

watermark_pattern = re.compile(r"(?P<reader_id>[A-Za-z0-9_.-]{1,16})\|(?P<yyyymmdd>\d{8})")
bit_redundancy = 4
carrier_seed = 20260308

watermark_embed_profiles = (
    {"name": "default", "seed": carrier_seed, "noise_strength": 6, "grid_strength": 4},
    {"name": "strong", "seed": carrier_seed, "noise_strength": 8, "grid_strength": 5},
    {"name": "alt-seed", "seed": 99, "noise_strength": 6, "grid_strength": 4},
)


def build_watermark_payload(reader_id: str, for_date) -> str:
    payload = f"{reader_id}|{for_date:%Y%m%d}"
    fixed_length = settings.WATERMARK_FIXED_LENGTH
    if len(payload) > fixed_length:
        raise ValueError("Watermark payload exceeds the configured fixed length.")
    return payload.ljust(fixed_length, "~")


def sanitize_raw_payload(raw: str) -> str:
    sanitized = "".join(ch if 32 <= ord(ch) <= 126 else "?" for ch in raw)
    fixed_length = settings.WATERMARK_FIXED_LENGTH
    return sanitized[:fixed_length].ljust(fixed_length, "~")


def parse_watermark_payload(payload: str) -> dict | None:
    normalized = payload.replace("\x00", "").rstrip("~")
    matches = list(watermark_pattern.finditer(normalized))
    if not matches:
        return None
    match = max(matches, key=lambda item: (len(item.group("reader_id")), -item.start()))
    return {
        "reader_id": match.group("reader_id"),
        "yyyymmdd": match.group("yyyymmdd"),
        "raw": match.group(0),
    }


def get_watermark_client() -> WaterMark:
    return WaterMark(
        password_wm=settings.WATERMARK_PASSWORD_WM,
        password_img=settings.WATERMARK_PASSWORD_IMG,
    )


def payload_to_bits(payload: str) -> np.ndarray:
    raw_bits = "".join(f"{byte:08b}" for byte in payload.encode("ascii"))
    bit_array = np.array([bit == "1" for bit in raw_bits], dtype=bool)
    return np.repeat(bit_array, bit_redundancy)


def bits_to_payload(bit_values) -> str:
    normalized_bits = []
    for start in range(0, len(bit_values), bit_redundancy):
        chunk = np.asarray(bit_values[start:start + bit_redundancy]).astype(float)
        normalized_bits.append("1" if chunk.mean() >= 0.5 else "0")

    bytes_out = bytearray()
    for start in range(0, len(normalized_bits), 8):
        byte_bits = normalized_bits[start:start + 8]
        if len(byte_bits) == 8:
            bytes_out.append(int("".join(byte_bits), 2))
    return bytes(bytes_out).decode("ascii", errors="replace")


def build_carrier_image(
    input_path: str,
    *,
    seed: int = carrier_seed,
    noise_strength: int = 6,
    grid_strength: int = 4,
) -> np.ndarray:
    image = cv2.imread(input_path, flags=cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Unable to read carrier image: {input_path}")

    rng = np.random.default_rng(seed)
    noise = rng.integers(-noise_strength, noise_strength + 1, size=image.shape, dtype=np.int16)
    textured = np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    textured[::12, :, :] = np.clip(textured[::12, :, :].astype(np.int16) + grid_strength, 0, 255).astype(np.uint8)
    textured[:, ::12, :] = np.clip(textured[:, ::12, :].astype(np.int16) - grid_strength, 0, 255).astype(np.uint8)
    return textured


def minimum_carrier_height(width: int) -> int:
    if width <= 420:
        return 220
    return 180


def pad_carrier_image(image: np.ndarray, extra_height: int = 0) -> np.ndarray:
    target_height = max(image.shape[0], minimum_carrier_height(image.shape[1]) + extra_height)
    if image.shape[0] >= target_height:
        return image

    fill_height = target_height - image.shape[0]
    tail_height = min(8, image.shape[0]) or 1
    tail_strip = image[image.shape[0] - tail_height :, :, :]
    filler = cv2.resize(tail_strip, (image.shape[1], fill_height), interpolation=cv2.INTER_LINEAR)
    return np.vstack([image, filler])


def try_extract_payload(image: np.ndarray) -> tuple[str, dict | None]:
    watermark = get_watermark_client()
    extracted_bits = watermark.extract(
        embed_img=image,
        wm_shape=settings.WATERMARK_FIXED_LENGTH * 8 * bit_redundancy,
        mode="bit",
    )
    extracted = bits_to_payload(extracted_bits)
    return extracted, parse_watermark_payload(extracted)


def crop_center(image: np.ndarray, width_ratio: float) -> np.ndarray:
    if width_ratio >= 0.999:
        return image
    width = image.shape[1]
    crop_width = max(int(width * width_ratio), 1)
    start_x = max((width - crop_width) // 2, 0)
    return image[:, start_x:start_x + crop_width]


def crop_center_width(image: np.ndarray, target_width: int) -> np.ndarray:
    width = image.shape[1]
    if width <= target_width:
        return image
    start_x = max((width - target_width) // 2, 0)
    return image[:, start_x:start_x + target_width]


def build_vertical_windows(image: np.ndarray, target_width: int) -> list[np.ndarray]:
    height = image.shape[0]
    if target_width >= 510:
        window_heights = [220, 250, 290, 330]
    else:
        window_heights = [200, 220, 250, 280]

    windows: list[np.ndarray] = []
    for window_height in window_heights:
        if window_height >= height:
            continue
        max_top = height - window_height
        positions = list(range(0, max_top + 1, 20))
        if positions[-1] != max_top:
            positions.append(max_top)
        for top in positions:
            windows.append(image[top:top + window_height, :])
    return windows


def resize_candidate(image: np.ndarray, target_width: int) -> np.ndarray:
    if image.shape[1] == target_width:
        return image
    target_height = max(int(image.shape[0] * target_width / image.shape[1]), minimum_carrier_height(target_width))
    return cv2.resize(image, (target_width, target_height), interpolation=cv2.INTER_LINEAR)


def iter_full_image_candidates(image: np.ndarray):
    yield "完整原圖", image

    padded = pad_carrier_image(image)
    if padded.shape != image.shape:
        yield "完整原圖補高", padded

    for target_width in (600, 420):
        if image.shape[1] > target_width:
            normalized = resize_candidate(crop_center_width(image, target_width), target_width)
            yield f"完整原圖對齊 {target_width} 寬", normalized


def iter_cropped_candidates(image: np.ndarray):
    bases = [crop_center(image, ratio) for ratio in (0.95, 0.9)]
    for base in bases:
        yield "中心裁切", base

    for target_width in (600, 420):
        for base in bases:
            normalized = crop_center_width(base, target_width)
            normalized = resize_candidate(normalized, target_width)
            yield f"中心裁切並對齊 {target_width} 寬", normalized
            for window in build_vertical_windows(normalized, target_width):
                yield f"裁切視窗 {target_width}x{window.shape[0]}", window


def estimate_background_color(image: np.ndarray) -> np.ndarray:
    border_width = min(8, max(image.shape[0] // 40, 4), max(image.shape[1] // 40, 4))
    samples = np.concatenate(
        [
            image[:border_width, :, :].reshape(-1, 3),
            image[-border_width:, :, :].reshape(-1, 3),
            image[:, :border_width, :].reshape(-1, 3),
            image[:, -border_width:, :].reshape(-1, 3),
        ],
        axis=0,
    )
    return np.median(samples, axis=0)


def iter_component_candidates(image: np.ndarray):
    if image.shape[0] < 260:
        return
    background = estimate_background_color(image)
    diff = np.abs(image.astype(np.int16) - background.astype(np.int16)).sum(axis=2)
    mask = (diff > 24).astype(np.uint8) * 255
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = max((image.shape[0] * image.shape[1]) // 15, 50000)
    boxes = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if width * height < min_area:
            continue
        if width < min(320, image.shape[1] // 3):
            continue
        boxes.append((x, y, width, height))

    for index, (x, y, width, height) in enumerate(sorted(boxes, key=lambda item: (item[1], item[0])), start=1):
        yield f"偵測區塊 {index}", image[y : y + height, x : x + width]


def build_recovery_context(
    expected_reader_ids: list[str] | None = None,
    expected_dates: list[str] | None = None,
) -> dict:
    today = timezone.localdate()
    recent_dates = [
        (today - timedelta(days=offset)).strftime("%Y%m%d")
        for offset in range(60)
    ]
    context = {
        "expected_reader_ids": [item.lower() for item in (expected_reader_ids or []) if item],
        "expected_dates": [item for item in (expected_dates or []) if item],
        "reader_ids": [],
        "global_dates": [],
        "reader_date_cache": {},
    }
    if context["expected_reader_ids"]:
        context["reader_ids"] = context["expected_reader_ids"]
    else:
        context["reader_ids"] = list(
            User.objects.filter(role=User.Role.READER, is_active=True).values_list("username", flat=True)
        )

    if context["expected_dates"]:
        context["global_dates"] = list(dict.fromkeys(context["expected_dates"] + recent_dates))
    else:
        cached_dates = list(
            DailyPageCache.objects.filter(for_date__lte=today)
            .order_by("-for_date")
            .values_list("for_date", flat=True)
            .distinct()
        )
        formatted_dates = [item.strftime("%Y%m%d") for item in cached_dates]
        context["global_dates"] = list(dict.fromkeys(formatted_dates + recent_dates))
    return context


def get_known_dates_for_reader(context: dict, reader_id: str | None = None) -> list[str]:
    if context["expected_dates"]:
        return context["expected_dates"]
    if not reader_id:
        return context["global_dates"]
    if reader_id not in context["reader_date_cache"]:
        today = timezone.localdate()
        cached_dates = list(
            DailyPageCache.objects.filter(reader__username=reader_id, for_date__lte=today)
            .order_by("-for_date")
            .values_list("for_date", flat=True)
            .distinct()
        )
        formatted_dates = [item.strftime("%Y%m%d") for item in cached_dates]
        context["reader_date_cache"][reader_id] = formatted_dates or context["global_dates"]
    return context["reader_date_cache"][reader_id]


def valid_yyyymmdd(candidate: str) -> bool:
    if not candidate.isdigit() or len(candidate) != 8:
        return False
    with contextlib.suppress(ValueError):
        datetime.strptime(candidate, "%Y%m%d")
        return True
    return False


def resolve_reader_id(candidate: str, context: dict) -> str:
    reader_ids = context["reader_ids"]
    if not reader_ids:
        return candidate
    lower_candidate = candidate.lower()
    if lower_candidate in reader_ids:
        return lower_candidate
    if len(reader_ids) == 1:
        only_reader = reader_ids[0]
        if lower_candidate and (
            lower_candidate in only_reader
            or only_reader.endswith(lower_candidate)
            or SequenceMatcher(None, lower_candidate, only_reader).ratio() >= 0.45
        ):
            return only_reader

    scored = sorted(
        (
            (SequenceMatcher(None, lower_candidate, reader_id).ratio(), reader_id)
            for reader_id in reader_ids
        ),
        reverse=True,
    )
    best_score, best_match = scored[0]
    if best_score < 0.62:
        return candidate
    if len(scored) > 1 and best_score - scored[1][0] < 0.08 and not context["expected_reader_ids"]:
        return candidate
    return best_match


def resolve_reader_from_raw(raw: str, context: dict) -> tuple[str | None, int]:
    reader_ids = context["reader_ids"]
    if not reader_ids:
        return None, 0

    sanitized = sanitize_raw_payload(raw).lower()
    best = None
    second = None
    for reader_id in reader_ids:
        for offset in range(0, 3):
            fragment = sanitized[offset:offset + len(reader_id)]
            score = SequenceMatcher(None, fragment, reader_id).ratio()
            candidate = (score, -offset, reader_id)
            if best is None or candidate > best:
                second = best
                best = candidate
            elif second is None or candidate > second:
                second = candidate

    if best is None or best[0] < 0.62:
        return None, 0
    if len(reader_ids) == 1:
        return best[2], -best[1]
    if second is not None and best[0] - second[0] < 0.08 and not context["expected_reader_ids"]:
        return None, 0
    return best[2], -best[1]


def resolve_yyyymmdd(candidate: str, context: dict, reader_id: str | None = None) -> str | None:
    token = sanitize_raw_payload(candidate)[:8]
    exact_valid = token if valid_yyyymmdd(token) else None
    known_dates = get_known_dates_for_reader(context, reader_id)
    if exact_valid and exact_valid in known_dates:
        return exact_valid

    def score(date_value: str) -> tuple[float, int, float]:
        digit_matches = sum(1 for raw_ch, date_ch in zip(token, date_value) if raw_ch.isdigit() and raw_ch == date_ch)
        known_digit_count = sum(1 for raw_ch in token if raw_ch.isdigit())
        ratio = digit_matches / max(known_digit_count, 1)
        sequence_ratio = SequenceMatcher(None, token.replace("?", "0"), date_value).ratio()
        return ratio, digit_matches, sequence_ratio

    if known_dates:
        ranked = sorted(((score(date_value), date_value) for date_value in known_dates), reverse=True)
        best_score, best_date = ranked[0]
        second_score = ranked[1][0] if len(ranked) > 1 else None
        if best_score[0] >= 0.75 or best_score[1] >= 6:
            if second_score is None or best_score[0] - second_score[0] >= 0.08 or best_score[1] - second_score[1] >= 1:
                if (
                    exact_valid is None
                    or best_date == exact_valid
                    or best_date in context["expected_dates"]
                    or exact_valid not in known_dates
                    or len(known_dates) == 1
                ):
                    return best_date

    return exact_valid


def normalize_parsed_candidate(parsed: dict, context: dict) -> dict | None:
    resolved_reader_id = resolve_reader_id(parsed["reader_id"], context)
    resolved_yyyymmdd = resolve_yyyymmdd(parsed["yyyymmdd"], context, resolved_reader_id)
    if resolved_yyyymmdd is None:
        return None
    return {
        "reader_id": resolved_reader_id,
        "yyyymmdd": resolved_yyyymmdd,
        "raw": f"{resolved_reader_id}|{resolved_yyyymmdd}",
    }


def recover_candidate_payload(raw: str, context: dict) -> dict | None:
    parsed = parse_watermark_payload(raw)
    if parsed is not None:
        return normalize_parsed_candidate(parsed, context)

    reader_id, offset = resolve_reader_from_raw(raw, context)
    if not reader_id:
        return None

    sanitized = sanitize_raw_payload(raw)
    expected_sep = offset + len(reader_id)
    separator_index = next(
        (
            index
            for index in range(max(expected_sep - 1, 0), min(expected_sep + 2, len(sanitized)))
            if sanitized[index] == "|"
        ),
        expected_sep,
    )
    date_fragment = sanitized[separator_index + 1 : separator_index + 9]
    if len(date_fragment) < 8:
        date_fragment = sanitized[expected_sep + 1 : expected_sep + 9]
    resolved_yyyymmdd = resolve_yyyymmdd(date_fragment, context, reader_id)
    if not resolved_yyyymmdd:
        return None

    return {
        "reader_id": reader_id,
        "yyyymmdd": resolved_yyyymmdd,
        "raw": f"{reader_id}|{resolved_yyyymmdd}",
    }


def choose_best_parsed_result(parsed_candidates: list[dict]) -> dict:
    raw_counts = Counter(item["raw"] for item in parsed_candidates)
    raw, count = raw_counts.most_common(1)[0]
    if count > 1:
        return next(item for item in parsed_candidates if item["raw"] == raw)

    max_length = max(len(item["raw"]) for item in parsed_candidates)
    padded = [item["raw"].ljust(max_length, "~") for item in parsed_candidates]
    consensus_raw = "".join(
        Counter(candidate[index] for candidate in padded).most_common(1)[0][0]
        for index in range(max_length)
    )
    parsed = parse_watermark_payload(consensus_raw)
    if parsed is not None:
        return parsed_candidates[0] if parsed["raw"] == parsed_candidates[0]["raw"] else parsed
    return parsed_candidates[0]


def recover_from_raw_candidates(raw_candidates: list[str], context: dict) -> dict | None:
    sanitized_candidates = [sanitize_raw_payload(raw) for raw in raw_candidates if raw]
    recovered_candidates = [
        candidate
        for candidate in (recover_candidate_payload(raw, context) for raw in sanitized_candidates)
        if candidate is not None
    ]
    if recovered_candidates:
        return choose_best_parsed_result(recovered_candidates)
    if not sanitized_candidates:
        return None

    max_length = max(len(item) for item in sanitized_candidates)
    padded = [item.ljust(max_length, "~") for item in sanitized_candidates]
    consensus_raw = "".join(
        Counter(candidate[index] for candidate in padded).most_common(1)[0][0]
        for index in range(max_length)
    )
    return recover_candidate_payload(consensus_raw, context)


def build_trace_entry(
    *,
    stage: str,
    label: str,
    raw: str,
    parsed: dict | None,
    duration_ms: int,
) -> dict:
    return {
        "stage": stage,
        "label": label,
        "raw_preview": sanitize_raw_payload(raw)[:32],
        "success": parsed is not None,
        "duration_ms": duration_ms,
        "message": f"{label}：{'成功' if parsed is not None else '失敗'}",
    }


def run_candidate_extraction(
    candidate_image: np.ndarray,
    *,
    stage: str,
    label: str,
    context: dict,
) -> tuple[str, dict | None, dict]:
    started = time.perf_counter()
    try:
        raw, parsed = try_extract_payload(candidate_image)
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        trace = {
            "stage": stage,
            "label": label,
            "raw_preview": "",
            "success": False,
            "duration_ms": duration_ms,
            "message": f"{label}：發生錯誤 {exc}",
        }
        return "", None, trace

    recovered = normalize_parsed_candidate(parsed, context) if parsed is not None else recover_candidate_payload(raw, context)
    duration_ms = int((time.perf_counter() - started) * 1000)
    trace = build_trace_entry(stage=stage, label=label, raw=raw, parsed=recovered, duration_ms=duration_ms)
    if recovered and recovered["raw"] != sanitize_raw_payload(raw).rstrip("~"):
        trace["message"] = f"{label}：成功，已自動修正 reader_id 或日期"
    return raw, recovered, trace


def extract_watermark_from_bytes(
    file_bytes: bytes,
    *,
    allow_crops: bool = True,
    expected_reader_ids: list[str] | None = None,
    expected_dates: list[str] | None = None,
) -> dict:
    np_buffer = np.frombuffer(file_bytes, dtype=np.uint8)
    image = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)
    if image is None:
        return {
            "raw_payload": "",
            "parsed": None,
            "trace": [{"stage": "input", "label": "讀取圖片", "success": False, "duration_ms": 0, "message": "無法讀取圖片。"}],
            "attempt_count": 0,
            "duration_ms": 0,
            "selected_method": "",
            "is_valid": False,
            "image_width": 0,
            "image_height": 0,
        }

    started = time.perf_counter()
    context = build_recovery_context(expected_reader_ids=expected_reader_ids, expected_dates=expected_dates)
    trace = [
        {
            "stage": "input",
            "label": "讀取圖片",
            "success": True,
            "duration_ms": 0,
            "message": f"已讀取圖片，尺寸 {image.shape[1]}x{image.shape[0]}。",
        }
    ]
    raw_candidates: list[str] = []
    parsed_candidates: list[dict] = []
    attempt_count = 0

    for label, candidate in iter_full_image_candidates(image):
        attempt_count += 1
        raw, parsed, attempt_trace = run_candidate_extraction(candidate, stage="full_image", label=label, context=context)
        raw_candidates.append(raw)
        trace.append(attempt_trace)
        if parsed is not None:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return {
                "raw_payload": parsed["raw"],
                "parsed": parsed,
                "trace": trace,
                "attempt_count": attempt_count,
                "duration_ms": duration_ms,
                "selected_method": label,
                "is_valid": True,
                "image_width": image.shape[1],
                "image_height": image.shape[0],
            }

    recovered = recover_from_raw_candidates(raw_candidates, context)
    if recovered is not None:
        trace.append(
            {
                "stage": "full_image",
                "label": "全圖綜合判讀",
                "success": True,
                "duration_ms": 0,
                "message": "完整原圖雖未直接命中，但已從多個全圖結果綜合修復。",
                "raw_preview": recovered["raw"],
            }
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        return {
            "raw_payload": recovered["raw"],
            "parsed": recovered,
            "trace": trace,
            "attempt_count": attempt_count,
            "duration_ms": duration_ms,
            "selected_method": "全圖綜合判讀",
            "is_valid": True,
            "image_width": image.shape[1],
            "image_height": image.shape[0],
        }

    if allow_crops:
        trace.append(
            {
                "stage": "cropped",
                "label": "進入裁切模式",
                "success": False,
                "duration_ms": 0,
                "message": "完整原圖未成功，開始嘗試自動裁切與多圖截圖情境。",
            }
        )
        for label, candidate in iter_component_candidates(image):
            attempt_count += 1
            raw, parsed, attempt_trace = run_candidate_extraction(candidate, stage="cropped", label=label, context=context)
            raw_candidates.append(raw)
            trace.append(attempt_trace)
            if parsed is not None:
                parsed_candidates.append(parsed)
                if len(parsed_candidates) >= 2:
                    break

        if parsed_candidates:
            best = choose_best_parsed_result(parsed_candidates)
            trace.append(
                {
                    "stage": "cropped",
                    "label": "區塊結果整合",
                    "success": True,
                    "duration_ms": 0,
                    "message": "已從偵測到的頁面區塊中整合出最佳結果。",
                    "raw_preview": best["raw"],
                }
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            return {
                "raw_payload": best["raw"],
                "parsed": best,
                "trace": trace,
                "attempt_count": attempt_count,
                "duration_ms": duration_ms,
                "selected_method": "區塊結果整合",
                "is_valid": True,
                "image_width": image.shape[1],
                "image_height": image.shape[0],
            }

        for label, candidate in iter_cropped_candidates(image):
            attempt_count += 1
            raw, parsed, attempt_trace = run_candidate_extraction(candidate, stage="cropped", label=label, context=context)
            raw_candidates.append(raw)
            trace.append(attempt_trace)
            if parsed is not None:
                parsed_candidates.append(parsed)
                if len(parsed_candidates) >= 3:
                    break

        if parsed_candidates:
            best = choose_best_parsed_result(parsed_candidates)
            trace.append(
                {
                    "stage": "cropped",
                    "label": "裁切結果整合",
                    "success": True,
                    "duration_ms": 0,
                    "message": "已從多個裁切候選中整合出最佳結果。",
                    "raw_preview": best["raw"],
                }
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            return {
                "raw_payload": best["raw"],
                "parsed": best,
                "trace": trace,
                "attempt_count": attempt_count,
                "duration_ms": duration_ms,
                "selected_method": "裁切候選整合",
                "is_valid": True,
                "image_width": image.shape[1],
                "image_height": image.shape[0],
            }

        recovered = recover_from_raw_candidates(raw_candidates, context)
        if recovered is not None:
            trace.append(
                {
                    "stage": "cropped",
                    "label": "裁切綜合判讀",
                    "success": True,
                    "duration_ms": 0,
                    "message": "裁切候選雖未直接命中，但已從多個結果綜合修復。",
                    "raw_preview": recovered["raw"],
                }
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            return {
                "raw_payload": recovered["raw"],
                "parsed": recovered,
                "trace": trace,
                "attempt_count": attempt_count,
                "duration_ms": duration_ms,
                "selected_method": "裁切綜合判讀",
                "is_valid": True,
                "image_width": image.shape[1],
                "image_height": image.shape[0],
            }

    duration_ms = int((time.perf_counter() - started) * 1000)
    return {
        "raw_payload": sanitize_raw_payload(raw_candidates[-1]) if raw_candidates else "",
        "parsed": None,
        "trace": trace,
        "attempt_count": attempt_count,
        "duration_ms": duration_ms,
        "selected_method": "",
        "is_valid": False,
        "image_width": image.shape[1],
        "image_height": image.shape[0],
    }


def extract_watermark_from_path(
    image_path: str,
    *,
    allow_crops: bool = True,
    expected_reader_ids: list[str] | None = None,
    expected_dates: list[str] | None = None,
) -> dict:
    with open(image_path, "rb") as image_file:
        return extract_watermark_from_bytes(
            image_file.read(),
            allow_crops=allow_crops,
            expected_reader_ids=expected_reader_ids,
            expected_dates=expected_dates,
        )


def extract_watermark_detailed(
    uploaded_file,
    *,
    allow_crops: bool = True,
    expected_reader_ids: list[str] | None = None,
    expected_dates: list[str] | None = None,
) -> dict:
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    file_bytes = uploaded_file.read()
    return extract_watermark_from_bytes(
        file_bytes,
        allow_crops=allow_crops,
        expected_reader_ids=expected_reader_ids,
        expected_dates=expected_dates,
    )


def extract_watermark(uploaded_file) -> tuple[str, dict | None]:
    result = extract_watermark_detailed(uploaded_file)
    return result["raw_payload"], result["parsed"]


def embed_watermark(
    input_path: str,
    output_path: str,
    payload: str,
    *,
    expected_reader_id: str | None = None,
    expected_yyyymmdd: str | None = None,
) -> dict:
    payload_bits = payload_to_bits(payload)
    expected_reader_ids = [expected_reader_id] if expected_reader_id else None
    expected_dates = [expected_yyyymmdd] if expected_yyyymmdd else None
    verification_trace = []
    last_error = None
    last_meta = None

    for profile in watermark_embed_profiles:
        carrier = build_carrier_image(
            input_path,
            seed=profile["seed"],
            noise_strength=profile["noise_strength"],
            grid_strength=profile["grid_strength"],
        )
        for extra_height in (0, 64, 128, 256):
            watermark = get_watermark_client()
            watermark.read_img(img=pad_carrier_image(carrier, extra_height=extra_height))
            watermark.read_wm(payload_bits, mode="bit")
            try:
                watermark.embed(filename=output_path)
            except AssertionError as exc:
                last_error = exc
                verification_trace.append(
                    {
                        "profile": profile["name"],
                        "extra_height": extra_height,
                        "verified": False,
                        "message": f"嵌入失敗：{exc}",
                    }
                )
                continue

            meta = extract_watermark_from_path(
                output_path,
                allow_crops=False,
                expected_reader_ids=expected_reader_ids,
                expected_dates=expected_dates,
            )
            verified = bool(
                meta["parsed"] is not None
                and (expected_reader_id is None or meta["parsed"]["reader_id"] == expected_reader_id)
                and (expected_yyyymmdd is None or meta["parsed"]["yyyymmdd"] == expected_yyyymmdd)
            )
            verification_trace.append(
                {
                    "profile": profile["name"],
                    "extra_height": extra_height,
                    "verified": verified,
                    "message": f"驗證{'成功' if verified else '失敗'}，方法：{meta['selected_method'] or '無'}",
                }
            )
            last_meta = meta
            if verified:
                return {
                    "verified": True,
                    "profile_name": profile["name"],
                    "extra_height": extra_height,
                    "verification_trace": verification_trace,
                    "verification_result": meta,
                }

    if last_error is not None and last_meta is None:
        raise last_error

    return {
        "verified": False,
        "profile_name": watermark_embed_profiles[-1]["name"],
        "extra_height": 256,
        "verification_trace": verification_trace,
        "verification_result": last_meta,
    }
