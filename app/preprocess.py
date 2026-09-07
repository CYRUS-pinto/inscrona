"""Image pre-processing for Inscrona OCR pipeline.

Handles HEIC/HEIF detection, EXIF orientation, hard resizing,
and blur detection. Merges GLM + Chandra editions.
"""

from __future__ import annotations

import io
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from PIL import Image, ExifTags

logger = logging.getLogger(__name__)


class PreprocessError(Exception):
    """Raised when image pre-processing fails."""


@dataclass(frozen=True)
class PreparedImage:
    """Result of image preparation."""
    image: Image.Image
    path: str
    original_size: tuple[int, int]
    target_size: tuple[int, int]
    blur_score: float  # Laplacian variance; lower = blurrier
    is_blurry: bool
    format_hint: str  # "JPEG", "PNG", "HEIC", etc.


def _is_heic(raw: bytes) -> bool:
    """Detect HEIC/HEIF format from magic bytes."""
    if len(raw) < 12:
        return False
    # ftyp box at offset 4 (covers .heic, .heif, .avci)
    if raw[4:8] == b"ftyp":
        return True
    # Alternate detection: HEIF brand strings
    if raw[:12].startswith(b"\x00\x00\x00\x1cftyp"):
        return True
    if raw[:8] == b"ftypheic" or raw[:8] == b"ftypmif1":
        return True
    return False


def _fix_exif_orientation(img: Image.Image) -> Image.Image:
    """Rotate/flip image to match EXIF orientation tag."""
    try:
        exif_data = img.getexif()
        if not exif_data:
            return img
        orientation_key = None
        for k, v in ExifTags.TAGS.items():
            if v == "Orientation":
                orientation_key = k
                break
        if orientation_key is None:
            return img
        orientation = exif_data.get(orientation_key)
        if orientation is None:
            return img
        method = {
            2: Image.FLIP_LEFT_RIGHT,
            3: Image.ROTATE_180,
            4: Image.FLIP_TOP_BOTTOM,
            5: Image.TRANSPOSE,
            6: Image.ROTATE_270,
            7: Image.TRANSVERSE,
            8: Image.ROTATE_90,
        }.get(orientation)
        if method is not None:
            img = img.transpose(method)
            logger.debug("EXIF orientation %d applied", orientation)
    except Exception as exc:
        logger.debug("EXIF orientation fix skipped: %s", exc)
    return img


def _hard_resize(img: Image.Image, max_edge: int = 1400) -> Image.Image:
    """Resize so longest edge ≤ max_edge, preserving aspect ratio."""
    w, h = img.size
    longest = max(w, h)
    if longest <= max_edge:
        return img
    scale = max_edge / longest
    new_w = int(w * scale)
    new_h = int(h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    logger.debug("Resized %dx%d → %dx%d", w, h, new_w, new_h)
    return img


def laplacian_variance(img: Image.Image) -> float:
    """Compute Laplacian variance as a blur score.

    Returns variance of Laplacian convolution. Lower values indicate
    blurrier images. Typical thresholds:
      - Sharp: > 100
      - Acceptable: 50–100
      - Blurry: < 50
    """
    try:
        import cv2
        import numpy as np
        gray = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        return float(laplacian.var())
    except ImportError:
        # Fallback: simple edge-detection proxy using PIL
        gray = img.convert("L")
        pixels = list(gray.getdata())
        w, h = gray.size
        edges = 0
        total = 0
        for y in range(1, h - 1):
            for x in range(1, w - 1):
                idx = y * w + x
                center = pixels[idx]
                # Simple 3x3 Laplacian approximation
                lap = abs(
                    -4 * center
                    + pixels[idx - 1] + pixels[idx + 1]
                    + pixels[idx - w] + pixels[idx + w]
                )
                edges += lap * lap
                total += 1
        if total == 0:
            return 0.0
        return math.sqrt(edges / total)


def load_image(source: Union[str, Path, bytes, io.BytesIO]) -> tuple[Image.Image, str, str]:
    """Load an image from various sources, handling HEIC/HEIF.

    Returns:
        (image, source_path_or_label, format_hint)

    Raises:
        PreprocessError: If the image cannot be loaded.
    """
    format_hint = "UNKNOWN"
    source_label = str(source)

    try:
        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.exists():
                raise PreprocessError(f"Image file not found: {path}")
            raw = path.read_bytes()
            source_label = str(path)
            if _is_heic(raw):
                format_hint = "HEIC"
                try:
                    import pillow_heif
                    pillow_heif.register_heif_opener()
                except ImportError:
                    raise PreprocessError(
                        "HEIC/HEIF image detected but pillow-heif is not installed. "
                        "Install with: pip install pillow-heif"
                    )
                img = Image.open(io.BytesIO(raw))
            else:
                img = Image.open(io.BytesIO(raw))
                format_hint = img.format or "UNKNOWN"
        elif isinstance(source, bytes):
            raw = source
            source_label = "<bytes>"
            if _is_heic(raw):
                format_hint = "HEIC"
                try:
                    import pillow_heif
                    pillow_heif.register_heif_opener()
                except ImportError:
                    raise PreprocessError(
                        "HEIC/HEIF image detected but pillow-heif is not installed."
                    )
                img = Image.open(io.BytesIO(raw))
            else:
                img = Image.open(io.BytesIO(raw))
                format_hint = img.format or "UNKNOWN"
        elif isinstance(source, io.BytesIO):
            raw = source.read()
            source_label = "<BytesIO>"
            source.seek(0)
            if _is_heic(raw):
                format_hint = "HEIC"
                try:
                    import pillow_heif
                    pillow_heif.register_heif_opener()
                except ImportError:
                    raise PreprocessError(
                        "HEIC/HEIF image detected but pillow-heif is not installed."
                    )
                img = Image.open(io.BytesIO(raw))
            else:
                img = Image.open(io.BytesIO(raw))
                format_hint = img.format or "UNKNOWN"
        else:
            raise PreprocessError(f"Unsupported source type: {type(source)}")

        # Convert palette/transparency modes
        if img.mode in ("P", "PA", "LA"):
            img = img.convert("RGBA")
        elif img.mode == "CMYK":
            img = img.convert("RGB")
        elif img.mode not in ("RGB", "RGBA", "L"):
            img = img.convert("RGB")

        return img, source_label, format_hint

    except PreprocessError:
        raise
    except Exception as exc:
        raise PreprocessError(f"Failed to load image from {source_label}: {exc}") from exc


def prepare_image(
    source: Union[str, Path, bytes, io.BytesIO],
    *,
    max_edge: int = 1400,
    blur_threshold: float = 50.0,
) -> PreparedImage:
    """Full pre-processing pipeline: load → HEIC → EXIF → resize → blur score.

    Args:
        source: Image file path, bytes, or BytesIO stream.
        max_edge: Maximum longest edge after resize (pixels).
        blur_threshold: Laplacian variance below this is considered blurry.

    Returns:
        PreparedImage with all metadata.
    """
    img, source_label, format_hint = load_image(source)
    original_size = img.size

    # Fix EXIF orientation
    img = _fix_exif_orientation(img)

    # Hard resize
    img = _hard_resize(img, max_edge=max_edge)
    target_size = img.size

    # Blur detection
    blur_score = laplacian_variance(img)
    is_blurry = blur_score < blur_threshold

    if is_blurry:
        logger.warning(
            "Image may be blurry (score=%.1f < threshold=%.1f): %s",
            blur_score, blur_threshold, source_label,
        )

    return PreparedImage(
        image=img,
        path=source_label,
        original_size=original_size,
        target_size=target_size,
        blur_score=blur_score,
        is_blurry=is_blurry,
        format_hint=format_hint,
    )


def prepare_pdf_page(
    pil_image: Image.Image,
    *,
    max_edge: int = 1400,
    blur_threshold: float = 50.0,
) -> PreparedImage:
    """Prepare a single PDF page image (already loaded as PIL Image).

    Skips the load/HEIC detection step since PDF pages are already rasterized.
    """
    original_size = pil_image.size

    # Convert modes
    img = pil_image
    if img.mode in ("P", "PA", "LA", "CMYK"):
        img = img.convert("RGB")
    elif img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")

    # Fix EXIF
    img = _fix_exif_orientation(img)

    # Resize
    img = _hard_resize(img, max_edge=max_edge)
    target_size = img.size

    # Blur
    blur_score = laplacian_variance(img)
    is_blurry = blur_score < blur_threshold

    return PreparedImage(
        image=img,
        path="<pdf_page>",
        original_size=original_size,
        target_size=target_size,
        blur_score=blur_score,
        is_blurry=is_blurry,
        format_hint="PDF",
    )
