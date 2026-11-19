import numpy as np
import pytest
from PIL import Image

from app.config import Settings
from app.detector import EXPLICIT_LABELS, NudeDetector, non_max_suppression, resize_bilinear


@pytest.fixture(scope="module")
def detector():
    return NudeDetector(Settings().nudenet_model_path, threads=1)


def test_resize_matches_opencv_half_pixel_rule():
    # Downscaling 4 -> 2 with half-pixel centres samples at 0.5 and 2.5: averages of neighbours.
    row = np.array([[[0], [10], [20], [30]]], dtype=np.uint8)  # 1x4, 1 channel
    out = resize_bilinear(np.repeat(row, 2, axis=0), 1, 2)
    np.testing.assert_allclose(out[0, :, 0], [5, 25])


def test_resize_constant_image_stays_constant():
    image = np.full((37, 53, 3), 77, dtype=np.uint8)
    np.testing.assert_allclose(resize_bilinear(image, 320, 320), 77, atol=1e-3)


def test_prepare_pads_bottom_right_and_scales(detector):
    prepared = detector.prepare(Image.new("RGB", (100, 200), (255, 0, 0)))
    assert prepared.blob.shape == (1, 3, 320, 320)
    assert prepared.blob.dtype == np.float32
    assert (prepared.side, prepared.width, prepared.height) == (200, 100, 200)
    assert prepared.blob[0, :, 10, 10].tolist() == [1.0, 0.0, 0.0]  # red, RGB order, 0-1
    assert prepared.blob[0, :, 10, 300].tolist() == [0.0, 0.0, 0.0]  # black padding on the right


def test_detect_plain_image_finds_nothing_explicit(detector):
    result = detector.detect(detector.prepare(Image.new("RGB", (300, 300), (90, 160, 220))), 0.6)
    assert 0.0 <= result.score < 0.6
    assert all(not d.explicit or d.label in EXPLICIT_LABELS for d in result.detections)


def test_nms_drops_overlapping_box():
    corners = np.array([[0, 0, 10, 10], [1, 1, 10, 10], [50, 50, 60, 60]], dtype=np.float32)
    scores = np.array([0.9, 0.8, 0.7], dtype=np.float32)
    assert non_max_suppression(corners, scores, 0.45) == [0, 2]
