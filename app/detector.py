"""NudeNet 320n body-part detector (YOLOv8n, ONNX), without opencv.

Preprocessing follows the NudeNet package: pad the image bottom/right with black to a
square, resize to 320x320 with opencv-style bilinear sampling (no anti-aliasing), scale to
0-1, NCHW. One deliberate difference: the image is fed as RGB. The NudeNet package
(with opencv 5) feeds BGR by accident; on labelled test photos RGB scored the same or better.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from app.schemas import Detection, NudeNetResult

LABELS = (
    "FEMALE_GENITALIA_COVERED", "FACE_FEMALE", "BUTTOCKS_EXPOSED", "FEMALE_BREAST_EXPOSED",
    "FEMALE_GENITALIA_EXPOSED", "MALE_BREAST_EXPOSED", "ANUS_EXPOSED", "FEET_EXPOSED",
    "BELLY_COVERED", "FEET_COVERED", "ARMPITS_COVERED", "ARMPITS_EXPOSED", "FACE_MALE",
    "BELLY_EXPOSED", "MALE_GENITALIA_EXPOSED", "ANUS_COVERED", "FEMALE_BREAST_COVERED",
    "BUTTOCKS_COVERED",
)
# Body parts whose detection makes an image NSFW.
EXPLICIT_LABELS = (
    "FEMALE_BREAST_EXPOSED", "FEMALE_GENITALIA_EXPOSED", "MALE_GENITALIA_EXPOSED",
    "ANUS_EXPOSED", "BUTTOCKS_EXPOSED",
)
MIN_DETECTION_SCORE = 0.25  # same cut-off the NudeNet package uses for reported boxes
NMS_IOU = 0.45


@dataclass(frozen=True)
class PreparedImage:
    blob: np.ndarray  # (1, 3, size, size) float32
    side: int  # padded square side in original pixels
    width: int
    height: int


class NudeDetector:
    def __init__(self, model_path: Path, *, threads: int = 2, size: int = 320) -> None:
        if not Path(model_path).is_file():
            raise FileNotFoundError(f"NudeNet model not found: {model_path}")
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.log_severity_level = 3  # errors only
        # InferenceSession.run is thread-safe, so one session serves all requests.
        self._session = ort.InferenceSession(str(model_path), options, providers=["CPUExecutionProvider"])
        self._input = self._session.get_inputs()[0].name
        self.size = size
        self._explicit = np.array([LABELS.index(label) for label in EXPLICIT_LABELS])

        warm = self._session.run(None, {self._input: np.zeros((1, 3, size, size), np.float32)})[0]
        if warm.ndim != 3 or warm.shape[1] != 4 + len(LABELS):
            raise ValueError(f"Unexpected NudeNet output shape {warm.shape}")

    def prepare(self, image: Image.Image) -> PreparedImage:
        rgb = np.asarray(image.convert("RGB"))
        height, width = rgb.shape[:2]
        side = max(width, height)
        square = np.zeros((side, side, 3), dtype=np.uint8)
        square[:height, :width] = rgb
        resized = resize_bilinear(square, self.size, self.size) / 255.0
        blob = np.ascontiguousarray(resized.transpose(2, 0, 1)[np.newaxis], dtype=np.float32)
        return PreparedImage(blob=blob, side=side, width=width, height=height)

    def detect(self, image: PreparedImage, threshold: float) -> NudeNetResult:
        output = self._session.run(None, {self._input: image.blob})[0][0].T  # (anchors, 4 + classes)
        boxes, classes = output[:, :4], output[:, 4:]

        explicit = classes[:, self._explicit]
        anchor, column = np.unravel_index(int(explicit.argmax()), explicit.shape)
        score = float(explicit[anchor, column])

        return NudeNetResult(
            score=round(score, 4),
            label=EXPLICIT_LABELS[column] if score >= MIN_DETECTION_SCORE else None,
            threshold=threshold,
            detections=self._detections(boxes, classes, image),
        )

    def _detections(self, boxes: np.ndarray, classes: np.ndarray, image: PreparedImage) -> list[Detection]:
        confidence = classes.max(axis=1)
        keep = confidence >= MIN_DETECTION_SCORE
        if not keep.any():
            return []
        confidence, class_ids = confidence[keep], classes[keep].argmax(axis=1)

        # centre x/y + size in model pixels -> corner coordinates in original pixels
        scale = image.side / self.size
        cx, cy, w, h = (boxes[keep] * scale).T
        x1 = np.clip(cx - w / 2, 0, image.width)
        y1 = np.clip(cy - h / 2, 0, image.height)
        x2 = np.clip(cx + w / 2, 0, image.width)
        y2 = np.clip(cy + h / 2, 0, image.height)
        corners = np.stack([x1, y1, x2, y2], axis=1)

        detections = []
        for i in non_max_suppression(corners, confidence, NMS_IOU):
            label = LABELS[class_ids[i]]
            bx1, by1, bx2, by2 = corners[i]
            detections.append(Detection(
                label=label,
                score=round(float(confidence[i]), 4),
                box=[int(bx1), int(by1), int(bx2 - bx1), int(by2 - by1)],
                explicit=label in EXPLICIT_LABELS,
            ))
        return detections


def resize_bilinear(image: np.ndarray, out_height: int, out_width: int) -> np.ndarray:
    """Bilinear resize matching opencv INTER_LINEAR: half-pixel centres, no anti-aliasing."""

    def sample_points(n_out: int, n_in: int):
        source = np.clip((np.arange(n_out) + 0.5) * (n_in / n_out) - 0.5, 0, None)
        low = np.minimum(np.floor(source).astype(np.intp), n_in - 1)
        high = np.minimum(low + 1, n_in - 1)
        return low, high, (source - low).astype(np.float32)

    y0, y1, fy = sample_points(out_height, image.shape[0])
    x0, x1, fx = sample_points(out_width, image.shape[1])
    fx = fx[np.newaxis, :, np.newaxis]
    top, bottom = image[y0].astype(np.float32), image[y1].astype(np.float32)
    top = top[:, x0] * (1 - fx) + top[:, x1] * fx
    bottom = bottom[:, x0] * (1 - fx) + bottom[:, x1] * fx
    fy = fy[:, np.newaxis, np.newaxis]
    return top * (1 - fy) + bottom * fy


def non_max_suppression(corners: np.ndarray, scores: np.ndarray, iou_limit: float) -> list[int]:
    """Indices of boxes kept after class-agnostic NMS, highest score first."""
    order = list(np.argsort(-scores))
    areas = (corners[:, 2] - corners[:, 0]) * (corners[:, 3] - corners[:, 1])
    kept = []
    while order:
        best, rest = order[0], np.array(order[1:], dtype=np.intp)
        kept.append(int(best))
        if rest.size == 0:
            break
        ix1 = np.maximum(corners[best, 0], corners[rest, 0])
        iy1 = np.maximum(corners[best, 1], corners[rest, 1])
        ix2 = np.minimum(corners[best, 2], corners[rest, 2])
        iy2 = np.minimum(corners[best, 3], corners[rest, 3])
        overlap = np.clip(ix2 - ix1, 0, None) * np.clip(iy2 - iy1, 0, None)
        iou = overlap / np.maximum(areas[best] + areas[rest] - overlap, 1e-9)
        order = list(rest[iou <= iou_limit])
    return kept
