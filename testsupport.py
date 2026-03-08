from pathlib import Path
import shutil
import tempfile
from unittest import SkipTest

from django.conf import settings


def find_font_or_skip() -> str:
    for font_path in settings.ANTI_OCR_FONT_PATHS:
        if font_path and Path(font_path).is_file():
            return font_path
    raise SkipTest("No usable Chinese font found for anti-OCR rendering tests.")


def make_temp_media_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="catchingrat-test-media-"))


def cleanup_temp_media_root(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def build_long_chinese_text(paragraphs: int = 6, repeats: int = 16) -> str:
    sentence = "春夜的風穿過舊城牆，燈影沿著青石路慢慢鋪開，茶香與雨聲交錯成一種柔軟的節奏。"
    blocks = []
    for index in range(paragraphs):
        blocks.append((sentence + f"第{index + 1}段的記憶在此停留。") * repeats)
    return "\n\n".join(blocks)
