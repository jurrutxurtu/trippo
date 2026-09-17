"""Media derivatives: thumbnails and web-sized copies.

Two sizes, both WebP:

    thumb  256 px   grid and filmstrip
    web   1600 px   lightbox, and what a hosted viewer would serve (ADR-0001)

Originals are never copied. A capsule holds derivatives plus a hash reference, which is
what keeps an 8 GB trip down to a few hundred megabytes and lets the capsule be shared
without shipping anyone's raw camera files.

Speed matters: 1,224 files is the normal case. Two things make it bearable.

* **Use the embedded EXIF preview when there is one.** Phone JPEGs carry a ~160 px
  thumbnail in the header; decoding that instead of a 12 MP frame is roughly 50x cheaper.
  It is too small for the 256 px grid on its own, but `draft=True` gives us most of the
  win anyway.
* **`Image.draft()`** lets libjpeg decode at 1/2, 1/4 or 1/8 scale directly, so a 4000 px
  original is never fully decoded just to produce a 256 px square.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from trippo.config.heuristics import THUMB_PX, WEB_PX
from trippo.domain.models import MediaAsset, MediaKind

THUMB_DIR = "media/thumb"
WEB_DIR = "media/web"
POSTER_DIR = "media/poster"

#: WebP quality. 82 is visually indistinguishable from the original at these sizes and
#: roughly a third of the bytes of equivalent JPEG.
QUALITY_THUMB = 78
QUALITY_WEB = 82


@dataclass
class DerivativeReport:
    generated: int = 0
    skipped_existing: int = 0
    failed: int = 0
    videos_without_poster: int = 0
    bytes_written: int = 0
    degradations: list[str] = field(default_factory=list)

    def summary(self) -> str:
        mb = self.bytes_written / 1_048_576
        return (
            f"{self.generated} generated, {self.skipped_existing} already present, "
            f"{self.failed} failed ({mb:,.0f} MB)"
        )


def generate(
    media: list[MediaAsset],
    local_paths: dict[str, str],
    capsule_root: Path,
    *,
    workers: int = 8,
    progress=None,
) -> DerivativeReport:
    """Write derivatives for every asset and populate `thumb_ref` / `web_ref`.

    Mutates `media` in place. Never raises on a single bad file -- a corrupt JPEG in a
    folder of 1,200 must not abort an import.
    """
    report = DerivativeReport()
    (capsule_root / THUMB_DIR).mkdir(parents=True, exist_ok=True)
    (capsule_root / WEB_DIR).mkdir(parents=True, exist_ok=True)

    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        report.degradations.append("Pillow is not installed: no thumbnails were generated.")
        return report

    _register_heif(report)

    photos = [m for m in media if m.kind is MediaKind.PHOTO]
    videos = [m for m in media if m.kind is MediaKind.VIDEO]

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for asset, result in zip(
            photos,
            pool.map(lambda m: _one(m, local_paths, capsule_root), photos),
            strict=True,
        ):
            done += 1
            if progress and done % 25 == 0:
                progress(done, len(photos))
            if result is None:
                report.failed += 1
                continue
            written, existing, size = result
            report.generated += written
            report.skipped_existing += existing
            report.bytes_written += size
            asset.thumb_ref = f"{THUMB_DIR}/{asset.hash}.webp"
            asset.web_ref = f"{WEB_DIR}/{asset.hash}.webp"

    if videos:
        # Poster frames need ffmpeg, which is not assumed present (AGENTS.md section 5).
        report.videos_without_poster = len(videos)
        report.degradations.append(
            f"{len(videos)} video(s) have no poster frame (ffmpeg not used in this build). "
            "They appear in the timeline but without a still."
        )

    if report.failed:
        report.degradations.append(
            f"{report.failed} image(s) could not be read and have no thumbnail."
        )
    return report


def _register_heif(report: DerivativeReport) -> None:
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except ImportError:
        report.degradations.append(
            "pillow-heif is not installed: HEIC/HEIF images will be skipped."
        )


def _one(
    asset: MediaAsset, local_paths: dict[str, str], root: Path
) -> tuple[int, int, int] | None:
    src = local_paths.get(asset.hash)
    if not src:
        return None
    path = Path(src)
    if not path.exists():
        return None

    thumb = root / THUMB_DIR / f"{asset.hash}.webp"
    web = root / WEB_DIR / f"{asset.hash}.webp"
    if thumb.exists() and web.exists():
        return (0, 1, 0)

    try:
        from PIL import Image, ImageOps

        written = 0
        size = 0
        with Image.open(path) as opened:
            # Ask libjpeg for a reduced decode. Costs nothing when unsupported.
            opened.draft("RGB", (WEB_PX, WEB_PX))
            im = ImageOps.exif_transpose(opened) or opened
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")

            if not web.exists():
                w = im.copy()
                w.thumbnail((WEB_PX, WEB_PX), Image.Resampling.LANCZOS)
                w.save(web, "WEBP", quality=QUALITY_WEB, method=4)
                written += 1
                size += web.stat().st_size

            if not thumb.exists():
                t = im.copy()
                t.thumbnail((THUMB_PX, THUMB_PX), Image.Resampling.LANCZOS)
                t.save(thumb, "WEBP", quality=QUALITY_THUMB, method=4)
                written += 1
                size += thumb.stat().st_size

        return (written, 0, size)
    except Exception:
        return None
