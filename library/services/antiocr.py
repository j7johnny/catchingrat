from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import random
import re

from antiocr.anti_ocr import AntiOcr
from django.conf import settings
import numpy as np
from PIL import Image

from library.models import AntiOcrPreset, BasePage, ChapterVersion, DeviceProfile

from .storage import delete_relative_path, ensure_parent, media_relative

anti_ocr_client = AntiOcr()
cjk_char_pattern = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
horizontal_space_pattern = re.compile(r"[ \t]+")
base_page_layout_version = "v3"


@dataclass(frozen=True)
class RenderProfile:
    code: str
    width: int
    min_font_size: int
    max_font_size: int
    bg_density: float
    initial_height: int
    slice_target_height: int
    min_slice_height: int
    min_watermark_height: int
    first_page_min_cn: int = 200


profile_targets = {
    DeviceProfile.DESKTOP: {
        "initial_height": 860,
        "slice_target_height": 290,
        "min_slice_height": 96,
        "min_watermark_height": 180,
    },
    DeviceProfile.MOBILE: {
        "initial_height": 760,
        "slice_target_height": 250,
        "min_slice_height": 110,
        "min_watermark_height": 220,
    },
}


def get_default_preset() -> AntiOcrPreset:
    preset, _ = AntiOcrPreset.objects.get_or_create(
        is_default=True,
        defaults={
            "name": "Default",
            "char_to_pinyin_ratio": 0,
            "char_reverse_ratio": 0,
            "desktop_width": 600,
            "desktop_min_font_size": 22,
            "desktop_max_font_size": 28,
            "desktop_bg_density": 0.08,
            "mobile_width": 420,
            "mobile_min_font_size": 20,
            "mobile_max_font_size": 24,
            "mobile_bg_density": 0.06,
        },
    )
    return preset


def build_source_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def resolve_font_path() -> str:
    for font_path in settings.ANTI_OCR_FONT_PATHS:
        if font_path and Path(font_path).is_file():
            return font_path
    raise FileNotFoundError("No usable anti-OCR font file was found.")


def count_cn_chars(text: str) -> int:
    return len(cjk_char_pattern.findall(text))


def normalize_content(content: str) -> str:
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    normalized_lines: list[str] = []
    blank_run = 0
    for raw_line in lines:
        line = horizontal_space_pattern.sub(" ", raw_line).strip()
        if line:
            blank_run = 0
            normalized_lines.append(line)
            continue
        if blank_run == 0:
            normalized_lines.append("")
        blank_run += 1

    while normalized_lines and not normalized_lines[0]:
        normalized_lines.pop(0)
    while normalized_lines and not normalized_lines[-1]:
        normalized_lines.pop()
    return "\n".join(normalized_lines).strip()


def build_render_profile(snapshot: dict, device_profile: str) -> RenderProfile:
    profile_snapshot = snapshot[device_profile]
    targets = profile_targets[device_profile]
    return RenderProfile(
        code=device_profile,
        width=profile_snapshot["width"],
        min_font_size=profile_snapshot["min_font_size"],
        max_font_size=profile_snapshot["max_font_size"],
        bg_density=profile_snapshot["bg_density"],
        initial_height=targets["initial_height"],
        slice_target_height=targets["slice_target_height"],
        min_slice_height=targets["min_slice_height"],
        min_watermark_height=targets["min_watermark_height"],
    )


def render_text_image(text: str, snapshot: dict, device_profile: str) -> Image.Image:
    font_path = resolve_font_path()
    profile = build_render_profile(snapshot, device_profile)
    normalized_text = normalize_content(text) or " "
    seed_source = f"{device_profile}\n{normalized_text}"
    seed = int(hashlib.sha256(seed_source.encode("utf-8")).hexdigest()[:8], 16)
    random_state = random.getstate()
    np_state = np.random.get_state()
    random.seed(seed)
    np.random.seed(seed)
    try:
        image = anti_ocr_client(
            normalized_text,
            font_fp=font_path,
            char_to_pinyin_ratio=snapshot["char_to_pinyin_ratio"],
            char_reverse_ratio=snapshot["char_reverse_ratio"],
            min_font_size=profile.min_font_size,
            max_font_size=profile.max_font_size,
            bg_gen_config={
                "image_size": (profile.width, profile.initial_height),
                "text_density": max(profile.bg_density, 0.01),
            },
        )
    finally:
        random.setstate(random_state)
        np.random.set_state(np_state)
    if image.width > profile.width:
        height = int(image.height * profile.width / image.width)
        image = image.resize((profile.width, height))
    return image


def build_slice_ranges(image_height: int, profile: RenderProfile) -> list[tuple[int, int]]:
    if image_height <= profile.slice_target_height:
        return [(0, image_height)]

    ranges: list[tuple[int, int]] = []
    start = 0
    while start < image_height:
        remaining = image_height - start
        if remaining <= profile.slice_target_height:
            end = image_height
        elif remaining - profile.slice_target_height < profile.min_slice_height:
            end = image_height
        else:
            end = start + profile.slice_target_height
        ranges.append((start, end))
        start = end
    return ranges


def distribute_char_counts(total_cn_chars: int, slice_heights: list[int], first_page_min_cn: int) -> list[int]:
    if not slice_heights:
        return []
    if total_cn_chars <= 0:
        return [0 for _ in slice_heights]

    total_height = sum(slice_heights) or 1
    raw_counts = [total_cn_chars * height / total_height for height in slice_heights]
    counts = [int(value) for value in raw_counts]

    remainder = total_cn_chars - sum(counts)
    if remainder > 0:
        order = sorted(
            range(len(raw_counts)),
            key=lambda index: raw_counts[index] - counts[index],
            reverse=True,
        )
        for index in order[:remainder]:
            counts[index] += 1

    if total_cn_chars >= first_page_min_cn and counts[0] < first_page_min_cn:
        needed = first_page_min_cn - counts[0]
        counts[0] += needed
        for index in range(len(counts) - 1, 0, -1):
            transferable = max(0, counts[index] - 1)
            taken = min(needed, transferable)
            counts[index] -= taken
            needed -= taken
            if needed == 0:
                break

    return counts


def pad_page_image(image: Image.Image, min_height: int) -> Image.Image:
    if image.height >= min_height:
        return image

    fill_height = min_height - image.height
    tail_height = min(8, image.height) or 1
    tail_strip = image.crop((0, image.height - tail_height, image.width, image.height))
    filler = tail_strip.resize((image.width, fill_height))
    padded = Image.new(image.mode, (image.width, min_height))
    padded.paste(image, (0, 0))
    padded.paste(filler, (0, image.height))
    return padded


def render_chapter_page_images(content: str, snapshot: dict, device_profile: str) -> list[tuple[Image.Image, int]]:
    profile = build_render_profile(snapshot, device_profile)
    chapter_image = render_text_image(content, snapshot, device_profile)
    slice_ranges = build_slice_ranges(chapter_image.height, profile)
    slice_heights = [end - start for start, end in slice_ranges]
    total_cn_chars = count_cn_chars(content)
    char_counts = distribute_char_counts(total_cn_chars, slice_heights, profile.first_page_min_cn)

    pages: list[tuple[Image.Image, int]] = []
    for index, (start, end) in enumerate(slice_ranges):
        page_image = chapter_image.crop((0, start, chapter_image.width, end)).copy()
        page_image = pad_page_image(page_image, profile.min_watermark_height)
        pages.append((page_image, char_counts[index]))

    chapter_image.close()
    return pages


def base_page_relative_path(chapter_version_id: int, device_profile: str, page_index: int) -> str:
    return media_relative(
        "base_pages",
        base_page_layout_version,
        f"version_{chapter_version_id}",
        device_profile,
        f"page_{page_index:04d}.png",
    )


def base_pages_need_regeneration(pages: list[BasePage], device_profile: str, snapshot: dict) -> bool:
    if not pages:
        return True

    profile = build_render_profile(snapshot, device_profile)
    expected_prefix = f"base_pages/{base_page_layout_version}/"
    for page in pages:
        if not page.relative_path.startswith(expected_prefix):
            return True
        if not page.absolute_path.exists():
            return True
        if page.image_height < profile.min_watermark_height:
            return True
    return False


def save_base_page_image(
    chapter_version: ChapterVersion,
    device_profile: str,
    page_index: int,
    image: Image.Image,
    char_count: int,
) -> BasePage:
    relative_path = base_page_relative_path(chapter_version.id, device_profile, page_index)
    absolute_path = ensure_parent(relative_path)
    image.save(absolute_path, format="PNG")

    existing = BasePage.objects.filter(
        chapter_version=chapter_version,
        device_profile=device_profile,
        page_index=page_index,
    ).first()
    if existing and existing.relative_path != relative_path:
        delete_relative_path(existing.relative_path)

    page, _ = BasePage.objects.update_or_create(
        chapter_version=chapter_version,
        device_profile=device_profile,
        page_index=page_index,
        defaults={
            "relative_path": relative_path,
            "char_count": char_count,
            "image_width": image.width,
            "image_height": image.height,
        },
    )
    return page
