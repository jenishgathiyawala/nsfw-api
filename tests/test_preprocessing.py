import io

import numpy as np
import pytest
from PIL import Image

from app.preprocessing import (
    ImageTooLargeError,
    InvalidImageError,
    UnsupportedFormatError,
    load_frames,
    square_views,
    to_tensor,
    to_tensors,
)
from tests.conftest import make_image

LIMITS = dict(max_pixels=50_000_000, max_frames=8)


def test_tensor_shape_dtype_and_bgr_mean():
    # Solid colour: every pixel should be [B-104, G-117, R-123].
    frame = load_frames(make_image("PNG", color=(200, 100, 50)), **LIMITS)[0]
    tensor = to_tensor(frame, 224)
    assert tensor.shape == (1, 224, 224, 3)
    assert tensor.dtype == np.float32
    np.testing.assert_allclose(tensor[0, 0, 0], [50 - 104, 100 - 117, 200 - 123])


def test_portrait_gives_three_undistorted_squares():
    # 100x300: top third red, middle green, bottom blue.
    image = Image.new("RGB", (100, 300))
    image.paste((255, 0, 0), (0, 0, 100, 100))
    image.paste((0, 255, 0), (0, 100, 100, 200))
    image.paste((0, 0, 255), (0, 200, 100, 300))
    views = square_views(image)
    assert [v.size for v in views] == [(100, 100)] * 3
    assert [v.getpixel((50, 50)) for v in views] == [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    assert len(to_tensors(image, 224)) == 3


def test_landscape_crops_along_width():
    views = square_views(Image.new("RGB", (300, 100)))
    assert [v.size for v in views] == [(100, 100)] * 3


def test_near_square_gives_one_view():
    assert len(square_views(Image.new("RGB", (100, 104)))) == 1


def test_transparency_becomes_white():
    data = make_image("PNG", mode="RGBA", color=(0, 0, 0, 0))
    tensor = to_tensor(load_frames(data, **LIMITS)[0], 224)
    np.testing.assert_allclose(tensor[0, 0, 0], [255 - 104, 255 - 117, 255 - 123])


def test_exif_rotation_applied():
    exif = Image.Exif()
    exif[0x0112] = 6  # "rotate 90° clockwise to display"
    data = make_image("JPEG", size=(300, 100), exif=exif)
    assert load_frames(data, **LIMITS)[0].size == (100, 300)


def test_heic_is_decoded():
    frames = load_frames(make_image("HEIF", size=(300, 200), color=(10, 200, 30)), **LIMITS)
    assert len(frames) == 1
    assert frames[0].size == (300, 200)
    r, g, b = frames[0].getpixel((150, 100))
    assert g > 150 and r < 60 and b < 80  # lossy, so only roughly the same colour


def test_heic_rotation_applied_once():
    exif = Image.Exif()
    exif[0x0112] = 6  # "rotate 90° clockwise to display"
    data = make_image("HEIF", size=(300, 100), exif=exif.tobytes())
    assert load_frames(data, **LIMITS)[0].size == (100, 300)


def test_animated_gif_frames_are_sampled():
    frames = [Image.new("RGB", (64, 64), (i * 10, 0, 0)) for i in range(20)]
    buffer = io.BytesIO()
    frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:])
    loaded = load_frames(buffer.getvalue(), max_pixels=10**7, max_frames=5)
    assert len(loaded) == 5


def test_garbage_bytes_rejected():
    with pytest.raises(InvalidImageError):
        load_frames(b"definitely not an image", **LIMITS)


def test_unsupported_format_rejected():
    with pytest.raises(UnsupportedFormatError):
        load_frames(make_image("TIFF"), **LIMITS)


def test_pixel_limit_checked_before_decoding():
    with pytest.raises(ImageTooLargeError):
        load_frames(make_image("PNG", size=(1000, 1000)), max_pixels=999_999, max_frames=1)


def test_truncated_image_rejected():
    data = make_image("JPEG", size=(500, 500))
    with pytest.raises(InvalidImageError):
        load_frames(data[: len(data) // 3], **LIMITS)
