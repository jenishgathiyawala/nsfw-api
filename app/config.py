"""Runtime settings, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MB = 1024 * 1024


def _int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


def _float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return float(value) if value else default


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str) -> tuple[str, ...]:
    value = os.environ.get(name, "")
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    model_path: Path = PROJECT_ROOT / "nsfw.tflite"
    # Interpreters in the pool = how many images can be classified in parallel.
    num_interpreters: int = field(default_factory=lambda: min(4, os.cpu_count() or 1))
    threads_per_interpreter: int = 2

    default_threshold: float = 0.8

    # NudeNet body-part detector, combined with Open_NSFW: NSFW if either model says so.
    enable_nudenet: bool = True
    nudenet_model_path: Path = PROJECT_ROOT / "nudenet_320n.onnx"
    nudenet_threshold: float = 0.6

    max_upload_bytes: int = 15 * MB
    max_batch_size: int = 20
    # Rejects decompression bombs: a tiny file that decodes to a huge bitmap.
    max_pixels: int = 50_000_000
    # Animated GIF/WebP/APNG: how many frames (evenly spaced) to check.
    max_frames: int = 8

    # Empty = CORS disabled (same-origin and non-browser clients only).
    cors_origins: tuple[str, ...] = ()

    # Keys accepted in the X-API-Key header. Several allow rotating a key without downtime.
    # Empty = no key needed (local development only).
    api_keys: tuple[str, ...] = ()

    @property
    def max_request_bytes(self) -> int:
        """Hard cap on a request body: a full batch plus multipart overhead."""
        return self.max_upload_bytes * self.max_batch_size + MB

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            model_path=Path(os.environ.get("MODEL_PATH", defaults.model_path)),
            num_interpreters=_int("NUM_INTERPRETERS", defaults.num_interpreters),
            threads_per_interpreter=_int("THREADS_PER_INTERPRETER", defaults.threads_per_interpreter),
            default_threshold=_float("DEFAULT_THRESHOLD", defaults.default_threshold),
            enable_nudenet=_bool("ENABLE_NUDENET", defaults.enable_nudenet),
            nudenet_model_path=Path(os.environ.get("NUDENET_MODEL_PATH", defaults.nudenet_model_path)),
            nudenet_threshold=_float("NUDENET_THRESHOLD", defaults.nudenet_threshold),
            max_upload_bytes=_int("MAX_UPLOAD_MB", defaults.max_upload_bytes // MB) * MB,
            max_batch_size=_int("MAX_BATCH_SIZE", defaults.max_batch_size),
            max_pixels=_int("MAX_PIXELS", defaults.max_pixels),
            max_frames=_int("MAX_FRAMES", defaults.max_frames),
            cors_origins=_list("CORS_ORIGINS"),
            api_keys=_list("API_KEYS"),
        )
