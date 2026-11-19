"""Open_NSFW (TFLite) + optional NudeNet (ONNX) inference.

A single TFLite interpreter cannot run two inferences at once, so the classifier keeps
several and hands one to each request. Requests only wait when every interpreter is busy.
An image is NSFW when either model says so.
"""

from __future__ import annotations

import queue
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

import numpy as np
from ai_edge_litert.interpreter import Interpreter

from app.detector import NudeDetector
from app.preprocessing import load_frames, to_tensors
from app.schemas import Prediction, Scores, Timing

CLASSES = ["SFW", "NSFW"]  # Open_NSFW output index 0, 1


class NSFWClassifier:
    def __init__(
        self,
        model_path: Path,
        *,
        num_interpreters: int = 2,
        threads_per_interpreter: int = 2,
        max_pixels: int = 50_000_000,
        max_frames: int = 8,
        detector: Optional[NudeDetector] = None,
        nudenet_threshold: float = 0.6,
    ) -> None:
        if not Path(model_path).is_file():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        if num_interpreters < 1:
            raise ValueError("num_interpreters must be >= 1")

        self.max_pixels = max_pixels
        self.max_frames = max_frames
        self.detector = detector
        self.nudenet_threshold = nudenet_threshold
        self._pool: "queue.Queue[Interpreter]" = queue.Queue()

        for _ in range(num_interpreters):
            interpreter = Interpreter(model_path=str(model_path), num_threads=threads_per_interpreter)
            interpreter.allocate_tensors()
            self._pool.put(interpreter)
        self.num_interpreters = num_interpreters

        with self._borrow() as interpreter:
            inp = interpreter.get_input_details()[0]
            out = interpreter.get_output_details()[0]
        self._input_index = inp["index"]
        self._output_index = out["index"]
        self.input_shape = [int(d) for d in inp["shape"]]
        output_shape = [int(d) for d in out["shape"]]

        if len(self.input_shape) != 4 or self.input_shape[1] != self.input_shape[2]:
            raise ValueError(f"Expected a square NHWC input, got {self.input_shape}")
        if output_shape != [1, len(CLASSES)]:
            raise ValueError(f"Expected output shape [1, 2], got {output_shape}")
        self.input_size = self.input_shape[1]

        self._warm_up()

    @property
    def models(self) -> list[str]:
        return ["open_nsfw"] + (["nudenet"] if self.detector else [])

    def classify(
        self,
        data: bytes,
        *,
        threshold: float,
        nudenet_threshold: Optional[float] = None,
        filename: Optional[str] = None,
    ) -> Prediction:
        """Classify image bytes. Raises InvalidImageError (or a subclass) for bad input."""
        nudenet_threshold = self.nudenet_threshold if nudenet_threshold is None else nudenet_threshold

        started = time.perf_counter()
        frames = load_frames(data, max_pixels=self.max_pixels, max_frames=self.max_frames)
        tensors = [t for frame in frames for t in to_tensors(frame, self.input_size)]
        prepared = [self.detector.prepare(frame) for frame in frames] if self.detector else []
        preprocessed = time.perf_counter()

        with self._borrow() as interpreter:
            # The most explicit view (crop or animation frame) decides.
            sfw, nsfw = max((self._run(interpreter, t) for t in tensors), key=lambda s: s[1])
        nudenet = max(
            (self.detector.detect(p, nudenet_threshold) for p in prepared),
            key=lambda r: r.score,
            default=None,
        )
        finished = time.perf_counter()

        flagged_by = []
        if nsfw >= threshold:
            flagged_by.append("open_nsfw")
        if nudenet is not None and nudenet.score >= nudenet_threshold:
            flagged_by.append("nudenet")

        return Prediction(
            verdict="NSFW" if flagged_by else "SFW",
            is_nsfw=bool(flagged_by),
            flagged_by=flagged_by,
            scores=Scores(sfw=round(sfw, 4), nsfw=round(nsfw, 4)),
            threshold=threshold,
            nudenet=nudenet,
            frames_analyzed=len(frames),
            views_analyzed=len(tensors),
            timing=Timing(
                preprocess_ms=_ms(preprocessed - started),
                inference_ms=_ms(finished - preprocessed),
                total_ms=_ms(finished - started),
            ),
            filename=filename,
        )

    @contextmanager
    def _borrow(self) -> Iterator[Interpreter]:
        interpreter = self._pool.get()
        try:
            yield interpreter
        finally:
            self._pool.put(interpreter)

    def _run(self, interpreter: Interpreter, tensor: np.ndarray) -> tuple[float, float]:
        interpreter.set_tensor(self._input_index, tensor)
        interpreter.invoke()
        output = interpreter.get_tensor(self._output_index)[0]
        return float(output[0]), float(output[1])

    def _warm_up(self) -> None:
        dummy = np.zeros(self.input_shape, dtype=np.float32)
        borrowed = [self._pool.get() for _ in range(self.num_interpreters)]
        try:
            for interpreter in borrowed:
                self._run(interpreter, dummy)
        finally:
            for interpreter in borrowed:
                self._pool.put(interpreter)


def _ms(seconds: float) -> float:
    return round(seconds * 1000, 2)
