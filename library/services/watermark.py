import re
from collections import Counter
from difflib import SequenceMatcher

import cv2
import numpy as np
from blind_watermark import WaterMark
from django.conf import settings

from accounts.models import User

watermark_pattern = re.compile(r"(?P<reader_id>[A-Za-z0-9_.-]{1,16})\|(?P<yyyymmdd>\d{8})")
bit_redundancy = 4
carrier_seed = 20260308


def build_watermark_payload(reader_id: str, for_date) -> str:
    payload = f"{reader_id}|{for_date:%Y%m%d}"
    fixed_length = settings.WATERMARK_FIXED_LENGTH
    if len(payload) > fixed_length:
        raise ValueError("Watermark payload exceeds the configured fixed length.")
    return payload.ljust(fixed_length, "~")


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


def build_carrier_image(input_path: str) -> np.ndarray:
    image = cv2.imread(input_path, flags=cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Unable to read carrier image: {input_path}")

    rng = np.random.default_rng(carrier_seed)
    noise = rng.integers(-6, 7, size=image.shape, dtype=np.int16)
    textured = np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    textured[::12, :, :] = np.clip(textured[::12, :, :].astype(np.int16) + 4, 0, 255).astype(np.uint8)
    textured[:, ::12, :] = np.clip(textured[:, ::12, :].astype(np.int16) - 4, 0, 255).astype(np.uint8)
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


def embed_watermark(input_path: str, output_path: str, payload: str) -> None:
    carrier = build_carrier_image(input_path)
    payload_bits = payload_to_bits(payload)

    last_error = None
    for extra_height in (0, 64, 128, 256, 384):
        watermark = get_watermark_client()
        watermark.read_img(img=pad_carrier_image(carrier, extra_height=extra_height))
        watermark.read_wm(payload_bits, mode="bit")
        try:
            watermark.embed(filename=output_path)
            return
        except AssertionError as exc:
            last_error = exc
            continue

    if last_error is not None:
        raise last_error


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
        window_heights = [250, 290, 330]
    else:
        window_heights = [220, 250, 280]

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


def iter_extraction_candidates(image: np.ndarray):
    bases = [crop_center(image, ratio) for ratio in (1.0, 0.95)]
    for base in bases:
        yield base

    for target_width in (600, 420):
        for base in bases:
            normalized = crop_center_width(base, target_width)
            normalized = resize_candidate(normalized, target_width)
            yield normalized
            for window in build_vertical_windows(normalized, target_width):
                yield window


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
        return parsed
    return parsed_candidates[0]


def resolve_reader_id(candidate: str) -> str:
    reader_ids = list(User.objects.filter(role=User.Role.READER, is_active=True).values_list("username", flat=True))
    if not reader_ids or candidate in reader_ids:
        return candidate

    scored = sorted(
        (
            (SequenceMatcher(None, candidate, reader_id).ratio(), reader_id)
            for reader_id in reader_ids
        ),
        reverse=True,
    )
    best_score, best_match = scored[0]
    if best_score < 0.6:
        return candidate
    if len(scored) > 1 and best_score - scored[1][0] < 0.08:
        return candidate
    if len(candidate) < max(4, len(best_match) - 3):
        return candidate
    return best_match


def normalize_parsed_candidate(parsed: dict) -> dict:
    resolved_reader_id = resolve_reader_id(parsed["reader_id"])
    if resolved_reader_id == parsed["reader_id"]:
        return parsed
    return {
        "reader_id": resolved_reader_id,
        "yyyymmdd": parsed["yyyymmdd"],
        "raw": f"{resolved_reader_id}|{parsed['yyyymmdd']}",
    }


def extract_watermark(uploaded_file) -> tuple[str, dict | None]:
    file_bytes = uploaded_file.read()
    np_buffer = np.frombuffer(file_bytes, dtype=np.uint8)
    image = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)
    if image is None:
        return "", None

    last_raw = ""
    parsed_candidates: list[dict] = []
    for candidate in iter_extraction_candidates(image):
        try:
            raw, parsed = try_extract_payload(candidate)
        except Exception:
            continue
        last_raw = raw
        if parsed is not None:
            parsed_candidates.append(normalize_parsed_candidate(parsed))
            if len(parsed_candidates) >= 3:
                break
    if parsed_candidates:
        best = choose_best_parsed_result(parsed_candidates)
        return best["raw"], best
    return last_raw, parse_watermark_payload(last_raw)
