from __future__ import annotations

from collections import defaultdict
from io import BytesIO
import json
import random

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from PIL import Image

from library.models import DailyPageCache, DeviceProfile
from library.services.watermark import extract_watermark_from_bytes


def stitch_page_paths(page_paths: list[str]) -> Image.Image:
    images = [Image.open(path) for path in page_paths]
    try:
        total_height = sum(image.height for image in images) - max(0, len(images) - 1)
        canvas = Image.new("RGB", (images[0].width, total_height), "#000000")
        cursor = 0
        for index, image in enumerate(images):
            if index:
                cursor -= 1
            canvas.paste(image, (0, cursor))
            cursor += image.height
        return canvas
    finally:
        for image in images:
            image.close()


class Command(BaseCommand):
    help = "Benchmark watermark extraction with 1-3 stitched page screenshots and random crops."

    def add_arguments(self, parser):
        parser.add_argument("--reader", required=True, help="Reader username.")
        parser.add_argument("--device", choices=[DeviceProfile.DESKTOP, DeviceProfile.MOBILE], default=DeviceProfile.DESKTOP)
        parser.add_argument("--date", help="for_date in YYYYMMDD. Defaults to today.")
        parser.add_argument("--chapter-version-id", type=int, help="Optional chapter version filter.")
        parser.add_argument("--trials-per-count", type=int, default=10)
        parser.add_argument("--max-pages", type=int, default=3)
        parser.add_argument("--seed", type=int, default=20260309)
        parser.add_argument("--json", dest="json_output", action="store_true")

    def handle(self, *args, **options):
        for_date = timezone.localdate()
        if options["date"]:
            try:
                for_date = timezone.datetime.strptime(options["date"], "%Y%m%d").date()
            except ValueError as exc:
                raise CommandError(f"Invalid --date value: {exc}") from exc

        queryset = DailyPageCache.objects.filter(
            reader__username=options["reader"].lower(),
            device_profile=options["device"],
            for_date=for_date,
        ).order_by("chapter_version_id", "page_index")
        if options["chapter_version_id"]:
            queryset = queryset.filter(chapter_version_id=options["chapter_version_id"])

        pages = list(queryset)
        if not pages:
            raise CommandError("No DailyPageCache rows matched the given filters.")

        grouped: dict[int, list[DailyPageCache]] = defaultdict(list)
        for page in pages:
            grouped[page.chapter_version_id].append(page)

        bundles_by_count: dict[int, list[list[DailyPageCache]]] = defaultdict(list)
        for group in grouped.values():
            ordered = sorted(group, key=lambda item: item.page_index)
            for page_count in range(1, options["max_pages"] + 1):
                if len(ordered) < page_count:
                    continue
                for start in range(0, len(ordered) - page_count + 1):
                    bundle = ordered[start : start + page_count]
                    expected = list(range(bundle[0].page_index, bundle[0].page_index + page_count))
                    if [page.page_index for page in bundle] == expected:
                        bundles_by_count[page_count].append(bundle)

        if not any(bundles_by_count.values()):
            raise CommandError("No consecutive daily page bundles were found.")

        rng = random.Random(options["seed"])
        report = []
        for page_count in range(1, options["max_pages"] + 1):
            bundles = bundles_by_count.get(page_count, [])
            if not bundles:
                continue

            trial_results = []
            for trial_index in range(options["trials_per_count"]):
                bundle = rng.choice(bundles)
                stitched = stitch_page_paths([str(page.absolute_path) for page in bundle])
                try:
                    min_width = max(220, int(stitched.width * 0.58))
                    min_height = max(180, int(stitched.height * 0.28))
                    crop_width = rng.randint(min_width, stitched.width)
                    crop_height = rng.randint(min_height, stitched.height)
                    x = rng.randint(0, max(0, stitched.width - crop_width))
                    y = rng.randint(0, max(0, stitched.height - crop_height))
                    crop = stitched.crop((x, y, x + crop_width, y + crop_height))
                    buffer = BytesIO()
                    crop.save(buffer, format="PNG")
                    result = extract_watermark_from_bytes(buffer.getvalue())
                finally:
                    stitched.close()

                trial_results.append(
                    {
                        "trial": trial_index + 1,
                        "page_count": page_count,
                        "crop_box": [x, y, x + crop_width, y + crop_height],
                        "chapter_version_id": bundle[0].chapter_version_id,
                        "page_indexes": [page.page_index for page in bundle],
                        "is_valid": result["is_valid"],
                        "reader_id": result["parsed"]["reader_id"] if result["parsed"] else "",
                        "yyyymmdd": result["parsed"]["yyyymmdd"] if result["parsed"] else "",
                        "selected_method": result["selected_method"],
                        "duration_ms": result["duration_ms"],
                        "attempt_count": result["attempt_count"],
                    }
                )

            successes = [item for item in trial_results if item["is_valid"]]
            report.append(
                {
                    "page_count": page_count,
                    "trial_count": len(trial_results),
                    "success_count": len(successes),
                    "success_rate": round(len(successes) / len(trial_results), 4),
                    "avg_duration_ms": round(sum(item["duration_ms"] for item in trial_results) / len(trial_results), 2),
                    "avg_attempt_count": round(sum(item["attempt_count"] for item in trial_results) / len(trial_results), 2),
                    "trials": trial_results,
                }
            )

        if options["json_output"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return

        for section in report:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{section['page_count']} page(s): {section['success_count']}/{section['trial_count']} "
                    f"success, avg {section['avg_duration_ms']} ms, avg attempts {section['avg_attempt_count']}"
                )
            )
            for trial in section["trials"]:
                status = "OK" if trial["is_valid"] else "FAIL"
                self.stdout.write(
                    f"  - trial {trial['trial']}: {status}, pages={trial['page_indexes']}, "
                    f"method={trial['selected_method'] or 'none'}, duration={trial['duration_ms']} ms"
                )
