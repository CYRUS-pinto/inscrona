"""Image intake: HEIC/HEIF -> JPEG, hard resize to <= MAX_IMAGE_EDGE px, quality gate.

The resize guard is non-negotiable: high-resolution scans (>2300px) are known to
make GLM-OCR / vision-OCR servers silently drop requests. Everything is
normalized before it ever reaches a model.
"""
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps

from . import config

try:  # iPhone uploads default to HEIC
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIC_OK = True
except ImportError:  # pragma: no cover
    HEIC_OK = False


class PreprocessError(ValueError):
    pass


@dataclass
class PreparedImage:
    jpeg: bytes
    width: int
    height: int
    original_format: str
    resized: bool
    blur_score: float  # Laplacian variance; low => blurry scan


def load_image(raw: bytes) -> Image.Image:
    try:
        img = Image.open(BytesIO(raw))
        original_format = (img.format or "UNKNOWN").upper()
        img = ImageOps.exif_transpose(img)
        img.original_format = original_format  # exif_transpose drops .format
        return img
    except Exception as exc:
        if not HEIC_OK and raw[4:8] == b"ftyp" and raw[8:12].startswith((b"heic", b"heix", b"hevc", b"mif1")):
            raise PreprocessError(
                "HEIC image received but pillow-heif is not installed. "
                "Run: pip install pillow-heif"
            ) from exc
        raise PreprocessError(f"Unsupported or corrupt image: {exc}") from exc


def laplacian_variance(img: Image.Image) -> float:
    """Cheap blur estimate without OpenCV: variance of a grayscale Laplacian kernel."""
    g = img.convert("L")
    w, h = g.size
    px = g.load()
    if w < 3 or h < 3:
        return 0.0
    total = 0.0
    n = 0
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            v = (px[x - 1, y] + px[x + 1, y] + px[x, y - 1] + px[x, y + 1]
                 - 4 * px[x, y])
            total += v * v
            n += 1
    return total / max(n, 1)


def prepare(raw: bytes) -> PreparedImage:
    img = load_image(raw)
    original_format = getattr(img, "original_format", "UNKNOWN")

    # 1. Blur check on a downscaled copy (fast) — pure PIL, no cv2 dependency.
    small = img.copy()
    small.thumbnail((400, 400))
    blur = laplacian_variance(small)

    # 2. Grayscale conversion: eliminates chromatic aberration, desk wood tint,
    # and phone shadow gradients while reducing visual noise.
    gray = img.convert("L")

    # 3. Dynamic contrast normalization: sharpens faint graphite pencil and ballpoint ink against paper.
    try:
        gray = ImageOps.autocontrast(gray, cutoff=0.5)
    except Exception:
        pass

    # 4. Merge back to 3-channel grayscale (R=G=B) so vision models receive standard 3-channel tensors
    img = Image.merge("RGB", (gray, gray, gray))

    resized = False
    if max(img.size) > config.MAX_IMAGE_EDGE:
        img.thumbnail((config.MAX_IMAGE_EDGE, config.MAX_IMAGE_EDGE), Image.LANCZOS)
        resized = True

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90, optimize=True)
    return PreparedImage(
        jpeg=buf.getvalue(),
        width=img.size[0],
        height=img.size[1],
        original_format=original_format,
        resized=resized,
        blur_score=round(blur, 2),
    )
