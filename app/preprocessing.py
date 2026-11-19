"""Image decoding and conversion to the Open_NSFW input tensor.

Pipeline per image:
  up to 3 undistorted square crops -> resize each to 224x224 -> RGB to BGR
  -> subtract the Open_NSFW BGR mean [104, 117, 123]
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

BGR_MEAN = np.array([104.0, 117.0, 123.0], dtype=np.float32)

# Formats are detected from the file's bytes, not from its name or MIME type.
# MPO is what many phone cameras produce for JPEG photos.
ALLOWED_FORMATS = frozenset({"JPEG", "MPO", "PNG", "WEBP", "BMP", "GIF"})


class InvalidImageError(ValueError):
    """The bytes are not a usable image (client error)."""


class UnsupportedFormatError(InvalidImageError):
    """A real image, but in a format this service does not accept."""


class ImageTooLargeError(InvalidImageError):
    """The file or its decoded bitmap is over the configured limit."""


def load_frames(data: bytes, *, max_pixels: int, max_frames: int) -> list[Image.Image]:
    """Decode bytes into RGB frames: one for still images, several for animations."""
    try:
        image = Image.open(io.BytesIO(data))
    except UnidentifiedImageError:
        raise InvalidImageError("Could not decode the file as an image.") from None
    except Exception as exc:  # Pillow raises a variety of errors for malformed headers
        raise InvalidImageError(f"Could not decode the file as an image: {exc}") from None

    if image.format not in ALLOWED_FORMATS:
        raise UnsupportedFormatError(
            f"Unsupported image format '{image.format}'. Allowed: {sorted(ALLOWED_FORMATS)}"
        )

    width, height = image.size  # read from the header, before decoding pixels
    if width * height > max_pixels:
        raise ImageTooLargeError(
            f"Image is {width}x{height} pixels; the limit is {max_pixels:,} pixels."
        )

    # MPO "frames" are depth maps / previews, not animation; only use the main image.
    animated = getattr(image, "is_animated", False) and image.format != "MPO"
    indices = _spread(image.n_frames, max_frames) if animated else [0]

    frames = []
    try:
        for index in indices:
            image.seek(index)
            frames.append(_to_rgb(image))
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise InvalidImageError(f"Image data is truncated or corrupted: {exc}") from None
    return frames


def to_tensors(image: Image.Image, size: int) -> list[np.ndarray]:
    """RGB image -> one tensor per square view (see `square_views`)."""
    return [to_tensor(view, size) for view in square_views(image)]


def square_views(image: Image.Image) -> list[Image.Image]:
    """Square crops along the long side: start, middle and end.

    Squashing a portrait photo into a square distorts body shapes and lowers NSFW
    scores; undistorted crops caught more NSFW photos in testing on labelled data.
    A (nearly) square image gives a single view.
    """
    width, height = image.size
    side = min(width, height)
    extra = max(width, height) - side
    offsets = sorted({0, extra // 2, extra}) if extra > side * 0.05 else [extra // 2]
    if height >= width:
        return [image.crop((0, o, side, o + side)) for o in offsets]
    return [image.crop((o, 0, o + side, side)) for o in offsets]


def to_tensor(image: Image.Image, size: int) -> np.ndarray:
    """Square RGB image -> float32 array of shape (1, size, size, 3), BGR, mean-subtracted."""
    resized = image.resize((size, size), Image.Resampling.BILINEAR)
    bgr = np.asarray(resized, dtype=np.float32)[:, :, ::-1] - BGR_MEAN
    return np.ascontiguousarray(bgr[np.newaxis])


def _to_rgb(image: Image.Image) -> Image.Image:
    """Apply EXIF rotation and flatten transparency onto white."""
    image = ImageOps.exif_transpose(image)
    has_alpha = image.mode in ("RGBA", "LA", "PA") or (
        image.mode == "P" and "transparency" in image.info
    )
    if not has_alpha:
        return image.convert("RGB")
    rgba = image.convert("RGBA")
    background = Image.new("RGB", rgba.size, (255, 255, 255))
    background.paste(rgba, mask=rgba.getchannel("A"))
    return background


def _spread(count: int, limit: int) -> list[int]:
    """Up to `limit` evenly spaced indices in range(count), always including first and last."""
    if count <= limit:
        return list(range(count))
    if limit <= 1:
        return [0]
    return sorted({round(i * (count - 1) / (limit - 1)) for i in range(limit)})
