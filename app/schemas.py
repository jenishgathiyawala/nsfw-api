from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Verdict = Literal["SFW", "NSFW"]
ModelName = Literal["open_nsfw", "nudenet"]


class Scores(BaseModel):
    sfw: float = Field(description="Open_NSFW: probability the image is safe, 0-1")
    nsfw: float = Field(description="Open_NSFW: probability the image is NSFW, 0-1 (sfw + nsfw = 1)")


class Detection(BaseModel):
    label: str = Field(description="Body part, e.g. FEMALE_BREAST_EXPOSED, FACE_FEMALE")
    score: float
    box: list[int] = Field(description="[x, y, width, height] in pixels of the (EXIF-rotated) image")
    explicit: bool = Field(description="True for the exposed parts that count towards NSFW")


class NudeNetResult(BaseModel):
    score: float = Field(description="Highest score of any exposed explicit body part, 0-1")
    label: Optional[str] = Field(None, description="The body part behind `score` (null if nothing found)")
    threshold: float
    detections: list[Detection] = Field(
        description="Body parts found (all kinds). Use `box` to blur regions. For animations: the frame with the highest score"
    )


class Timing(BaseModel):
    preprocess_ms: float = Field(description="Decoding, resizing and normalizing")
    inference_ms: float = Field(description="Model execution only (both models)")
    total_ms: float


class Prediction(BaseModel):
    verdict: Verdict
    is_nsfw: bool = Field(
        description="True when Open_NSFW scores.nsfw >= threshold OR nudenet.score >= nudenet.threshold"
    )
    flagged_by: list[ModelName] = Field(description="Which models called it NSFW (empty when SFW)")
    scores: Scores
    threshold: float = Field(description="Open_NSFW threshold")
    nudenet: Optional[NudeNetResult] = Field(None, description="Null when NudeNet is disabled")
    frames_analyzed: int = Field(description="1 for still images; for animations, the frames checked")
    views_analyzed: int = Field(
        description="Open_NSFW square crops scored across all frames (highest NSFW score wins)"
    )
    timing: Timing
    filename: Optional[str] = None


class BatchItem(BaseModel):
    filename: Optional[str] = None
    result: Optional[Prediction] = None
    error: Optional[str] = Field(None, description="Set when this image could not be classified")


class BatchResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    items: list[BatchItem]
    total_ms: float


class Base64Request(BaseModel):
    image: str = Field(description="Base64 image, raw or as a data URI (data:image/jpeg;base64,...)")
    threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    nudenet_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)


class Health(BaseModel):
    status: Literal["ok"]
    model_loaded: bool
    models: list[ModelName]
    input_shape: list[int]
    classes: list[str]
    interpreters: int
    version: str


class ErrorResponse(BaseModel):
    detail: str
