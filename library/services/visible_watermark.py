from __future__ import annotations

import contextlib
import re
import shutil
import time
from itertools import product
from typing import Callable

import cv2
import numpy as np
from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

from .font_library import list_runtime_font_paths
from .storage import ensure_parent, media_relative
from .watermark import (
    build_recovery_context,
    get_known_dates_for_reader,
    normalize_parsed_candidate,
    recover_from_raw_candidates,
)

VISIBLE_WATERMARK_PATTERN = re.compile(r"(?P<reader_id>[A-Za-z0-9_.-]{1,16})\|(?P<yyyymmdd>\d{8})")
VISIBLE_WATERMARK_FUZZY_PATTERN = re.compile(
    r"(?P<reader_id>[A-Za-z0-9_.-]{1,16})[|/\\:;!Il]{0,2}(?P<yyyymmdd>\d{8})"
)
VISIBLE_OCR_WHITELIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-|"
VISIBLE_SEPARATOR_TRANSLATION = str.maketrans(
    {
        " ": "",
        "\t": "",
        "\r": "",
        "/": "|",
        "\\": "|",
        ":": "|",
        ";": "|",
        "!": "|",
        "I": "|",
        "l": "|",
    }
)


def build_visible_watermark_payload(reader_id: str, for_date) -> str:
    if hasattr(for_date, "strftime"):
        return f"{reader_id}|{for_date:%Y%m%d}"
    return f"{reader_id}|{for_date}"


def _runtime_font_paths() -> list[str]:
    paths = list_runtime_font_paths()
    if paths:
        return paths
    return [str(path) for path in settings.ANTI_OCR_FONT_PATHS if path]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for font_path in _runtime_font_paths():
        with contextlib.suppress(Exception):
            return ImageFont.truetype(font_path, size=size)
    return ImageFont.load_default()


def _font_size(device_profile: str) -> int:
    if device_profile == "desktop":
        return settings.VISIBLE_WATERMARK_DESKTOP_FONT_SIZE
    return settings.VISIBLE_WATERMARK_MOBILE_FONT_SIZE


def _row_spacing(device_profile: str) -> int:
    if device_profile == "desktop":
        return settings.VISIBLE_WATERMARK_DESKTOP_ROW_SPACING
    return settings.VISIBLE_WATERMARK_MOBILE_ROW_SPACING


def _text_metrics(payload: str, device_profile: str) -> tuple[ImageFont.FreeTypeFont, int, int]:
    font = _load_font(_font_size(device_profile))
    probe = Image.new("L", (8, 8), 0)
    draw = ImageDraw.Draw(probe)
    left, top, right, bottom = draw.textbbox((0, 0), payload, font=font)
    return font, max(1, right - left), max(1, bottom - top)


def _build_text_mask(size: tuple[int, int], payload: str, device_profile: str) -> np.ndarray:
    width, height = size
    font, text_width, text_height = _text_metrics(payload, device_profile)
    mask_image = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask_image)

    x_step = max(text_width + settings.VISIBLE_WATERMARK_TEXT_GAP, width // 4)
    y_step = max(text_height + _row_spacing(device_profile), text_height + 24)
    top_margin = max(12, text_height // 2)

    for row_index, y in enumerate(range(top_margin, height + text_height, y_step)):
        x_offset = 12 if row_index % 2 == 0 else x_step // 2
        for x in range(-x_offset, width + text_width, x_step):
            draw.text((x, y), payload, fill=255, font=font)

    mask = np.asarray(mask_image, dtype=np.float32) / 255.0
    if settings.VISIBLE_WATERMARK_MASK_BLUR > 0:
        mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=settings.VISIBLE_WATERMARK_MASK_BLUR)
    return np.clip(mask * settings.VISIBLE_WATERMARK_MASK_OPACITY, 0.0, 1.0)


def _bright_background_mask(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return (gray >= settings.VISIBLE_WATERMARK_BACKGROUND_THRESHOLD).astype(np.float32)


def _checkerboard(shape: tuple[int, int], phase_x: int = 0, phase_y: int = 0) -> np.ndarray:
    height, width = shape
    ys, xs = np.indices((height, width))
    return np.where(((xs + phase_x) + (ys + phase_y)) % 2 == 0, 1.0, -1.0).astype(np.float32)


def apply_visible_watermark(image: np.ndarray, payload: str, *, device_profile: str) -> np.ndarray:
    if image is None:
        raise ValueError("Image is required.")

    mask = _build_text_mask((image.shape[1], image.shape[0]), payload, device_profile)
    mask *= _bright_background_mask(image)
    carrier = _checkerboard(mask.shape)

    lab_image = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
    if settings.VISIBLE_WATERMARK_DELTA_L:
        lab_image[:, :, 0] += settings.VISIBLE_WATERMARK_DELTA_L * mask
    lab_image[:, :, 1] += settings.VISIBLE_WATERMARK_DELTA_A * carrier * mask
    lab_image[:, :, 2] += settings.VISIBLE_WATERMARK_DELTA_B * carrier * mask
    lab_image = np.clip(lab_image, 0, 255).astype(np.uint8)
    return cv2.cvtColor(lab_image, cv2.COLOR_LAB2BGR)


def embed_visible_watermark(
    input_path: str,
    output_path: str,
    payload: str,
    *,
    device_profile: str,
) -> dict:
    image = cv2.imread(input_path, flags=cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Unable to read input image: {input_path}")

    watermarked = apply_visible_watermark(image, payload, device_profile=device_profile)
    if not cv2.imwrite(output_path, watermarked):
        raise RuntimeError(f"Unable to write visible watermark image: {output_path}")

    return {
        "payload": payload,
        "width": int(watermarked.shape[1]),
        "height": int(watermarked.shape[0]),
        "device_profile": device_profile,
    }


def _build_anchor_positions(length: int, window: int) -> list[int]:
    if window >= length:
        return [0]
    max_start = length - window
    anchors = {0, max_start // 2, max_start}
    return sorted(max(0, min(max_start, value)) for value in anchors)


def _iter_window_candidates(image: np.ndarray):
    height, width = image.shape[:2]
    yield "full image", image

    if min(height, width) < 260:
        return

    size_candidates = (
        (max(240, int(width * 0.78)), max(220, int(height * 0.34))),
        (max(260, int(width * 0.92)), max(240, int(height * 0.45))),
    )
    seen: set[tuple[int, int, int, int]] = set()
    for crop_width, crop_height in size_candidates:
        crop_width = min(width, crop_width)
        crop_height = min(height, crop_height)
        for x in _build_anchor_positions(width, crop_width):
            for y in _build_anchor_positions(height, crop_height):
                key = (x, y, crop_width, crop_height)
                if key in seen:
                    continue
                seen.add(key)
                yield f"window {crop_width}x{crop_height} @ {x},{y}", image[y : y + crop_height, x : x + crop_width]

    band_height = min(height, max(240, int(height * 0.45)))
    if band_height < height:
        for y in _build_anchor_positions(height, band_height):
            yield f"horizontal band y={y}", image[y : y + band_height, :]


def _normalize_to_uint8(image: np.ndarray) -> np.ndarray:
    positive = np.clip(image, 0, None)
    if float(positive.max()) <= 0:
        return np.zeros(positive.shape, dtype=np.uint8)
    normalized = cv2.normalize(positive, None, 0, 255, cv2.NORM_MINMAX)
    return normalized.astype(np.uint8)


def _build_reveal_variants(image: np.ndarray):
    bright_mask = _bright_background_mask(image)
    if float(bright_mask.mean()) < 0.05:
        return

    lab_image = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
    chroma_signal = (
        (lab_image[:, :, 1] - 128.0) * float(settings.VISIBLE_WATERMARK_DELTA_A)
        + (lab_image[:, :, 2] - 128.0) * float(settings.VISIBLE_WATERMARK_DELTA_B)
    )
    chroma_signal -= cv2.GaussianBlur(chroma_signal, (0, 0), sigmaX=5)
    chroma_signal *= bright_mask

    for phase_x, phase_y in product((0, 1), repeat=2):
        carrier = _checkerboard((image.shape[0], image.shape[1]), phase_x=phase_x, phase_y=phase_y)
        demodulated = chroma_signal * carrier
        demodulated = cv2.GaussianBlur(demodulated, (0, 0), sigmaX=1.0)
        demodulated = cv2.boxFilter(demodulated, ddepth=-1, ksize=(3, 3), normalize=True)
        revealed = _normalize_to_uint8(demodulated)
        if revealed.max() <= 0:
            continue

        enlarged = cv2.resize(revealed, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
        enhanced = cv2.createCLAHE(clipLimit=2.8, tileGridSize=(8, 8)).apply(enlarged)
        inverted = cv2.bitwise_not(enhanced)
        binary = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        dilated = cv2.dilate(binary, np.ones((2, 2), dtype=np.uint8), iterations=1)

        label = f"phase {phase_x},{phase_y}"
        yield f"{label} / dilated", dilated
        yield f"{label} / binary", binary
        yield f"{label} / grayscale", inverted


def _save_debug_image(debug_prefix: str | None, label: str, image: np.ndarray, index: int) -> tuple[str | None, str | None]:
    if not debug_prefix:
        return None, None
    safe_label = re.sub(r"[^A-Za-z0-9]+", "-", label.lower()).strip("-") or "preview"
    relative_path = media_relative(
        "visible_watermark_debug",
        debug_prefix,
        f"{index:03d}-{safe_label}.png",
    )
    absolute_path = ensure_parent(relative_path)
    cv2.imwrite(str(absolute_path), image)
    return relative_path, f"{settings.MEDIA_URL}{relative_path}"


def _ocr_text(image: np.ndarray, *, psm: int) -> str:
    import pytesseract

    config = f"--oem 1 --psm {psm} -c tessedit_char_whitelist={VISIBLE_OCR_WHITELIST}"
    return pytesseract.image_to_string(image, lang="eng", config=config)


def _iter_text_candidates(text: str) -> list[str]:
    compact = text.translate(VISIBLE_SEPARATOR_TRANSLATION)
    compact = re.sub(r"\n+", "\n", compact)
    candidates = [text, compact, compact.replace("\n", "")]
    candidates.extend(line for line in compact.splitlines() if line)
    alnum = re.sub(r"[^A-Za-z0-9_.|\n-]", "", compact)
    candidates.append(alnum)
    candidates.append(alnum.replace("\n", ""))
    return [candidate for candidate in candidates if candidate]


def _parse_visible_ocr_text(text: str, context: dict) -> tuple[dict | None, str]:
    text_candidates = _iter_text_candidates(text)
    for candidate in text_candidates:
        for match in VISIBLE_WATERMARK_PATTERN.finditer(candidate):
            parsed = normalize_parsed_candidate(
                {
                    "reader_id": match.group("reader_id"),
                    "yyyymmdd": match.group("yyyymmdd"),
                    "raw": match.group(0),
                },
                context,
            )
            if parsed is not None and (
                not context["reader_ids"] or parsed["reader_id"] in context["reader_ids"]
            ):
                return parsed, match.group(0)

        for match in VISIBLE_WATERMARK_FUZZY_PATTERN.finditer(candidate):
            parsed = normalize_parsed_candidate(
                {
                    "reader_id": match.group("reader_id"),
                    "yyyymmdd": match.group("yyyymmdd"),
                    "raw": f"{match.group('reader_id')}|{match.group('yyyymmdd')}",
                },
                context,
            )
            if parsed is not None and (
                not context["reader_ids"] or parsed["reader_id"] in context["reader_ids"]
            ):
                return parsed, match.group(0)

    recovered = recover_from_raw_candidates(text_candidates, context)
    if recovered is not None and (not context["reader_ids"] or recovered["reader_id"] in context["reader_ids"]):
        return recovered, recovered["raw"]
    return None, ""


def _coerce_known_date(parsed: dict | None, context: dict) -> dict | None:
    if parsed is None:
        return None

    known_dates = get_known_dates_for_reader(context, parsed["reader_id"])
    if not known_dates or parsed["yyyymmdd"] in known_dates:
        return parsed

    if len(known_dates) == 1:
        only_date = known_dates[0]
        return {
            "reader_id": parsed["reader_id"],
            "yyyymmdd": only_date,
            "raw": f"{parsed['reader_id']}|{only_date}",
        }

    scored = sorted(
        (
            (
                sum(1 for raw_ch, known_ch in zip(parsed["yyyymmdd"], known_date) if raw_ch == known_ch),
                known_date,
            )
            for known_date in known_dates
        ),
        reverse=True,
    )
    best_match_count, best_date = scored[0]
    if best_match_count < 5:
        return None
    return {
        "reader_id": parsed["reader_id"],
        "yyyymmdd": best_date,
        "raw": f"{parsed['reader_id']}|{best_date}",
    }


def _build_result(
    *,
    image: np.ndarray,
    trace: list[dict],
    raw_payload: str,
    parsed: dict | None,
    attempt_count: int,
    duration_ms: int,
    selected_method: str,
) -> dict:
    return {
        "raw_payload": raw_payload,
        "parsed": parsed,
        "trace": trace,
        "attempt_count": attempt_count,
        "duration_ms": duration_ms,
        "selected_method": selected_method,
        "is_valid": parsed is not None,
        "image_width": int(image.shape[1]),
        "image_height": int(image.shape[0]),
    }


def extract_visible_watermark_from_bytes(
    file_bytes: bytes,
    *,
    expected_reader_ids: list[str] | None = None,
    expected_dates: list[str] | None = None,
    progress_callback: Callable[[dict], None] | None = None,
    debug_prefix: str | None = None,
) -> dict:
    if shutil.which("tesseract") is None:
        raise RuntimeError("Tesseract is required for visible watermark extraction.")

    image = cv2.imdecode(np.frombuffer(file_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return {
            "raw_payload": "",
            "parsed": None,
            "trace": [
                {
                    "stage": "input",
                    "label": "decode image",
                    "success": False,
                    "duration_ms": 0,
                    "message": "Unable to decode uploaded image.",
                }
            ],
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
            "label": "decode image",
            "success": True,
            "duration_ms": 0,
            "message": f"Loaded image {image.shape[1]}x{image.shape[0]}",
        }
    ]
    if progress_callback:
        progress_callback(trace[0])

    attempt_count = 0
    raw_candidates: list[str] = []
    preview_index = 0

    for window_label, window_image in _iter_window_candidates(image):
        window_entry = {
            "stage": "window",
            "label": window_label,
            "success": False,
            "duration_ms": 0,
            "message": f"Testing region {window_image.shape[1]}x{window_image.shape[0]}",
        }
        trace.append(window_entry)
        if progress_callback:
            progress_callback(window_entry)

        for reveal_label, reveal_image in _build_reveal_variants(window_image):
            preview_relative_path = None
            preview_url = None
            if preview_index < 12:
                preview_relative_path, preview_url = _save_debug_image(
                    debug_prefix,
                    f"{window_label}-{reveal_label}",
                    reveal_image,
                    preview_index,
                )
                preview_index += 1

            for psm in (6, 11):
                attempt_count += 1
                ocr_started = time.perf_counter()
                try:
                    recognized_text = _ocr_text(reveal_image, psm=psm)
                except Exception as exc:
                    duration_ms = int((time.perf_counter() - ocr_started) * 1000)
                    entry = {
                        "stage": "ocr",
                        "label": f"{window_label} / {reveal_label} / PSM {psm}",
                        "success": False,
                        "duration_ms": duration_ms,
                        "message": f"OCR failed: {exc}",
                    }
                    if preview_url:
                        entry["preview_url"] = preview_url
                    if preview_relative_path:
                        entry["preview_relative_path"] = preview_relative_path
                    trace.append(entry)
                    if progress_callback and (attempt_count <= 4 or attempt_count % 8 == 0):
                        progress_callback(entry)
                    continue

                parsed, raw_payload = _parse_visible_ocr_text(recognized_text, context)
                parsed = _coerce_known_date(parsed, context)
                if parsed is not None:
                    raw_payload = parsed["raw"]
                raw_candidates.append(raw_payload or recognized_text)
                duration_ms = int((time.perf_counter() - ocr_started) * 1000)
                entry = {
                    "stage": "ocr",
                    "label": f"{window_label} / {reveal_label} / PSM {psm}",
                    "success": parsed is not None,
                    "duration_ms": duration_ms,
                    "message": (
                        f"OCR matched {raw_payload}"
                        if parsed is not None
                        else "OCR did not produce a valid reader_id|yyyymmdd payload."
                    ),
                    "ocr_text": recognized_text.strip()[:240],
                    "raw_preview": raw_payload or recognized_text.strip()[:48],
                }
                if preview_url:
                    entry["preview_url"] = preview_url
                if preview_relative_path:
                    entry["preview_relative_path"] = preview_relative_path
                trace.append(entry)
                if progress_callback and (parsed is not None or attempt_count <= 4 or attempt_count % 8 == 0):
                    progress_callback(entry)
                if parsed is not None:
                    duration_ms_total = int((time.perf_counter() - started) * 1000)
                    return _build_result(
                        image=image,
                        trace=trace,
                        raw_payload=raw_payload,
                        parsed=parsed,
                        attempt_count=attempt_count,
                        duration_ms=duration_ms_total,
                        selected_method=f"{window_label} / {reveal_label} / PSM {psm}",
                    )

    recovered = recover_from_raw_candidates(raw_candidates, context)
    duration_ms = int((time.perf_counter() - started) * 1000)
    recovered = _coerce_known_date(recovered, context)
    if recovered is not None and (not context["reader_ids"] or recovered["reader_id"] in context["reader_ids"]):
        trace.append(
            {
                "stage": "ocr",
                "label": "aggregate recovery",
                "success": True,
                "duration_ms": 0,
                "message": f"Recovered payload from OCR fragments: {recovered['raw']}",
                "raw_preview": recovered["raw"],
            }
        )
        return _build_result(
            image=image,
            trace=trace,
            raw_payload=recovered["raw"],
            parsed=recovered,
            attempt_count=attempt_count,
            duration_ms=duration_ms,
            selected_method="aggregate recovery",
        )

    return _build_result(
        image=image,
        trace=trace,
        raw_payload="",
        parsed=None,
        attempt_count=attempt_count,
        duration_ms=duration_ms,
        selected_method="",
    )


def extract_visible_watermark_from_path(
    image_path: str,
    *,
    expected_reader_ids: list[str] | None = None,
    expected_dates: list[str] | None = None,
    progress_callback: Callable[[dict], None] | None = None,
    debug_prefix: str | None = None,
) -> dict:
    with open(image_path, "rb") as image_file:
        return extract_visible_watermark_from_bytes(
            image_file.read(),
            expected_reader_ids=expected_reader_ids,
            expected_dates=expected_dates,
            progress_callback=progress_callback,
            debug_prefix=debug_prefix,
        )
