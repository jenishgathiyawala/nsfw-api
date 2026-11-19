"""FastAPI service for SFW/NSFW image classification."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hmac
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Security, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from app import __version__
from app.classifier import CLASSES, NSFWClassifier
from app.config import MB, Settings
from app.detector import NudeDetector
from app.preprocessing import ImageTooLargeError, InvalidImageError, UnsupportedFormatError
from app.schemas import (
    Base64Request,
    BatchItem,
    BatchResponse,
    ErrorResponse,
    Health,
    Prediction,
)

logger = logging.getLogger("nsfw_api")

ERRORS = {
    400: {"model": ErrorResponse, "description": "Not a valid image"},
    401: {"model": ErrorResponse, "description": "Missing or wrong API key"},
    413: {"model": ErrorResponse, "description": "File or image dimensions too large"},
    415: {"model": ErrorResponse, "description": "Unsupported image format"},
}

ThresholdQuery = Query(
    None, ge=0.0, le=1.0, description="Open_NSFW cutoff, 0-1 (server default if omitted)"
)
NudeNetThresholdQuery = Query(
    None, ge=0.0, le=1.0, description="NudeNet body-part cutoff, 0-1 (server default if omitted)"
)


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    valid_keys = [key.encode() for key in settings.api_keys]

    async def require_api_key(key: Optional[str] = Security(api_key_header)) -> None:
        if not valid_keys:
            return
        given = (key or "").encode()
        # Constant-time compare against every key, so timing reveals nothing.
        matched = False
        for valid in valid_keys:
            matched |= hmac.compare_digest(given, valid)
        if not matched:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid API key.",
                headers={"WWW-Authenticate": "API-Key"},
            )

    protected = [Depends(require_api_key)]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        detector = None
        if settings.enable_nudenet:
            detector = NudeDetector(
                settings.nudenet_model_path, threads=settings.threads_per_interpreter
            )
        app.state.classifier = NSFWClassifier(
            settings.model_path,
            num_interpreters=settings.num_interpreters,
            threads_per_interpreter=settings.threads_per_interpreter,
            max_pixels=settings.max_pixels,
            max_frames=settings.max_frames,
            detector=detector,
            nudenet_threshold=settings.nudenet_threshold,
        )
        logger.info(
            "Models loaded: %s (%d Open_NSFW interpreter(s))",
            ", ".join(app.state.classifier.models),
            settings.num_interpreters,
        )
        if not valid_keys:
            logger.warning("API_KEYS is not set: anyone who can reach this server can use it.")
        yield

    app = FastAPI(
        title="NSFW Image Classification API",
        description=(
            "Classifies images as SFW or NSFW with two models: Open_NSFW (whole-image score, TFLite) "
            "and NudeNet (exposed body-part detector, ONNX). NSFW if either model says so."
        ),
        version=__version__,
        lifespan=lifespan,
    )

    # ---- middleware -------------------------------------------------------

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def limit_body_and_add_headers(request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > settings.max_request_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": f"Request body exceeds {settings.max_request_bytes // MB} MB."},
            )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        return response

    # ---- error mapping (most specific class wins) -------------------------

    def _error(code: int):
        async def handler(_: Request, exc: Exception) -> JSONResponse:
            return JSONResponse(status_code=code, content={"detail": str(exc)})
        return handler

    app.add_exception_handler(InvalidImageError, _error(status.HTTP_400_BAD_REQUEST))
    app.add_exception_handler(UnsupportedFormatError, _error(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE))
    app.add_exception_handler(ImageTooLargeError, _error(413))

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Details go to the log, never to the client.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})

    # ---- helpers ----------------------------------------------------------

    def classifier(request: Request) -> NSFWClassifier:
        return request.app.state.classifier

    def threshold_or_default(value: Optional[float]) -> float:
        return settings.default_threshold if value is None else value

    async def read_upload(upload: UploadFile) -> bytes:
        """Read an upload in chunks, stopping as soon as it passes the size limit."""
        buffer = bytearray()
        while chunk := await upload.read(MB):
            buffer += chunk
            if len(buffer) > settings.max_upload_bytes:
                raise ImageTooLargeError(
                    f"File exceeds the {settings.max_upload_bytes // MB} MB limit."
                )
        if not buffer:
            raise InvalidImageError("Uploaded file is empty.")
        return bytes(buffer)

    # ---- routes -----------------------------------------------------------

    @app.get("/", include_in_schema=False)
    async def root():
        return {"service": app.title, "version": __version__, "docs": "/docs", "health": "/health"}

    @app.get("/health", response_model=Health, tags=["status"])
    async def health(request: Request):
        model = getattr(request.app.state, "classifier", None)
        return Health(
            status="ok",
            model_loaded=model is not None,
            models=model.models if model else [],
            input_shape=model.input_shape if model else [],
            classes=CLASSES,
            interpreters=model.num_interpreters if model else 0,
            version=__version__,
        )

    @app.post("/predict", dependencies=protected, response_model=Prediction, responses=ERRORS, tags=["classify"])
    async def predict(
        request: Request,
        file: UploadFile = File(..., description="JPEG, PNG, WebP, BMP, GIF or HEIC"),
        threshold: Optional[float] = ThresholdQuery,
        nudenet_threshold: Optional[float] = NudeNetThresholdQuery,
    ):
        """Classify one uploaded image (multipart/form-data, field name `file`)."""
        data = await read_upload(file)
        return await run_in_threadpool(
            classifier(request).classify,
            data,
            threshold=threshold_or_default(threshold),
            nudenet_threshold=nudenet_threshold,
            filename=file.filename,
        )

    @app.post("/predict/batch", dependencies=protected, response_model=BatchResponse, responses=ERRORS, tags=["classify"])
    async def predict_batch(
        request: Request,
        files: list[UploadFile] = File(..., description="Several images, field name `files`"),
        threshold: Optional[float] = ThresholdQuery,
        nudenet_threshold: Optional[float] = NudeNetThresholdQuery,
    ):
        """Classify several images at once. A bad image fails only its own item, not the batch."""
        if len(files) > settings.max_batch_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"At most {settings.max_batch_size} images per batch.",
            )
        started = time.perf_counter()
        cutoff = threshold_or_default(threshold)
        model = classifier(request)

        async def one(upload: UploadFile) -> BatchItem:
            try:
                data = await read_upload(upload)
                result = await run_in_threadpool(
                    model.classify,
                    data,
                    threshold=cutoff,
                    nudenet_threshold=nudenet_threshold,
                    filename=upload.filename,
                )
                return BatchItem(filename=upload.filename, result=result)
            except InvalidImageError as exc:
                return BatchItem(filename=upload.filename, error=str(exc))
            except Exception:
                logger.exception("Batch item %r failed", upload.filename)
                return BatchItem(filename=upload.filename, error="Internal error.")

        # Runs in parallel across the interpreter pool.
        items = await asyncio.gather(*(one(f) for f in files))
        succeeded = sum(item.error is None for item in items)
        return BatchResponse(
            total=len(items),
            succeeded=succeeded,
            failed=len(items) - succeeded,
            items=items,
            total_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    @app.post("/predict/base64", dependencies=protected, response_model=Prediction, responses=ERRORS, tags=["classify"])
    async def predict_base64(request: Request, payload: Base64Request):
        """Classify an image sent as base64 in a JSON body."""
        encoded = payload.image.strip()
        if encoded.startswith("data:"):
            encoded = encoded.partition(",")[2]
        encoded = "".join(encoded.split())  # tolerate line-wrapped base64

        if len(encoded) > (settings.max_upload_bytes * 4) // 3 + 4:
            raise ImageTooLargeError(f"Image exceeds the {settings.max_upload_bytes // MB} MB limit.")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            raise InvalidImageError("Invalid base64 data.") from None
        if not data:
            raise InvalidImageError("Image data is empty.")

        return await run_in_threadpool(
            classifier(request).classify,
            data,
            threshold=threshold_or_default(payload.threshold),
            nudenet_threshold=payload.nudenet_threshold,
        )

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
