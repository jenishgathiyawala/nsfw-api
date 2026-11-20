# NSFW Image Classification API

A FastAPI service that labels images **SFW** or **NSFW** with two small local models:

| Model | File | What it does |
|---|---|---|
| Open_NSFW (Yahoo, ResNet-50, TFLite) | [`nsfw.tflite`](nsfw.tflite), 23 MB | One NSFW probability for the whole image |
| NudeNet 320n (YOLOv8n, ONNX) | [`nudenet_320n.onnx`](nudenet_320n.onnx), 12 MB | Finds exposed body parts, with boxes |

An image is **NSFW if either model says so**. They catch different photos: Open_NSFW
judges the overall image, NudeNet finds small or partial nudity.

## Setup on a new machine

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) (it also installs Python if needed):

   ```bash
   # macOS / Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh
   # Windows (PowerShell)
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. Clone and start. The first start installs dependencies from `uv.lock` (about a minute):

   ```bash
   git clone <repo-url> nsfw-api && cd nsfw-api
   ./run.sh              # http://127.0.0.1:8000, docs at /docs
   ```

   Windows has no `./run.sh`; use:

   ```bash
   uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

Both model files are in the repository, so nothing else needs downloading.

**Supported:** Python 3.10–3.14 on macOS (Apple Silicon), Linux x86_64 / ARM64
(glibc 2.27+, e.g. Ubuntu 18.04+) and Windows x64.
**Not supported:** Intel Macs. The TFLite runtime (`ai-edge-litert`) has no build for them.

## Run

```bash
./run.sh              # http://127.0.0.1:8000, docs at /docs
./run.sh --reload     # restart on code changes (watches app/ only)
PORT=9000 ./run.sh    # another port
API_KEYS=mykey123 ./run.sh   # require the X-API-Key header (see API key below)
uv run pytest         # tests
```

## Docker

Compose needs an API key in a `.env` file (git ignores it):

```bash
echo "API_KEYS=$(openssl rand -hex 32)" > .env
docker compose up -d --build     # build and start in the background
docker compose logs -f           # follow logs
docker compose down              # stop
```

Or without compose:

```bash
docker build -t nsfw-api .
docker run --rm -p 8000:8000 -e API_KEYS=your-secret-key nsfw-api
```

To host it for free on Oracle Cloud, follow [docs/deploy-oracle.md](docs/deploy-oracle.md).

- The image uses Python 3.12, runs as a non-root user and includes both models. It does not
  include tests, scripts or test photos (see `.dockerignore`). Size is about 700 MB unpacked.
- `docker-compose.yml` publishes the port on **127.0.0.1 only**, with a read-only filesystem
  and a 1 GB memory limit. Set thresholds and the other variables from
  [Configuration](#configuration-environment-variables) under `environment:`.
- A container health check calls `/health` every 30 seconds.
- Memory use is about 160 MB with 2 interpreters.
- Docker on Apple Silicon builds an ARM64 image. To build for an x86_64 server from a Mac,
  use `docker build --platform linux/amd64 -t nsfw-api .`

## API key

When `API_KEYS` is set, every `/predict*` request needs the header `X-API-Key: <key>`,
otherwise it gets **401**. `/health`, `/` and `/docs` stay open. In `/docs`, click
**Authorize** and paste the key.

- Without `API_KEYS` anyone can use the API, which is only fine on your own machine.
  The server logs a warning at start.
- Several keys can be given, comma-separated. To change a key: add the new one, update the
  backend, then remove the old one.
- Keep the key only in your backend (e.g. Laravel `.env`). Never put it in a mobile or web
  app: anyone can pull it out of the app.

## Endpoints

| Method | Path | Body |
|---|---|---|
| `POST` | `/predict` | multipart, field `file` |
| `POST` | `/predict/batch` | multipart, field `files` (repeat) |
| `POST` | `/predict/base64` | JSON `{"image": "<base64 or data URI>", "threshold": 0.8, "nudenet_threshold": 0.6}` |
| `GET` | `/health` | – |

Optional query parameters on `/predict` and `/predict/batch`: `threshold` (Open_NSFW,
default 0.8) and `nudenet_threshold` (default 0.6).

```bash
curl -H "X-API-Key: your-secret-key" -F "file=@photo.jpg" "http://127.0.0.1:8000/predict"
```

```json
{
  "verdict": "NSFW",
  "is_nsfw": true,
  "flagged_by": ["nudenet"],
  "scores": { "sfw": 0.7369, "nsfw": 0.2631 },
  "threshold": 0.8,
  "nudenet": {
    "score": 0.694,
    "label": "FEMALE_BREAST_EXPOSED",
    "threshold": 0.6,
    "detections": [
      { "label": "FEMALE_BREAST_EXPOSED", "score": 0.694, "box": [212, 380, 160, 140], "explicit": true },
      { "label": "FACE_FEMALE", "score": 0.61, "box": [240, 90, 120, 130], "explicit": false }
    ]
  },
  "frames_analyzed": 1,
  "views_analyzed": 3,
  "timing": { "preprocess_ms": 11.6, "inference_ms": 24.2, "total_ms": 35.8 },
  "filename": "photo.jpg"
}
```

- `is_nsfw` = `scores.nsfw >= threshold` **or** `nudenet.score >= nudenet.threshold`.
- `flagged_by` says which model(s) decided. It is empty for SFW.
- `nudenet.score` is the highest score of an exposed explicit part (breast, genitalia, anus, buttocks).
- `nudenet.detections` lists every body part found, explicit or not. `box` is
  `[x, y, width, height]` in pixels of the (EXIF-rotated) image, so you can blur just that region.

Batch responses list every image separately. A broken image fails only its own item
(`error` set, `result` null), not the whole request.

Errors return `{"detail": "..."}`: **400** not an image / empty / bad base64,
**401** missing or wrong API key, **413** file or pixel count over the limit, **415** unsupported format, **422** invalid parameters.

## How an image is processed

1. **Format check from the bytes**: JPEG, PNG, WebP, BMP, GIF or HEIC (iPhone). File names and MIME types are ignored.
2. **Pixel limit**: dimensions are read from the header before decoding, which blocks decompression bombs.
3. **Normalize**: apply EXIF rotation and place transparent pixels on white.
4. **Open_NSFW**: instead of squashing the photo into a square, which distorts body shapes in
   portrait photos, cut up to 3 undistorted square crops along the long side (start, middle,
   end). Resize each crop to 224×224, convert to BGR and subtract the mean `[104, 117, 123]`.
   The highest score wins.
5. **NudeNet**: pad bottom/right with black to a square, then resize to 320×320 with
   opencv-style bilinear sampling (done in numpy, so opencv is not needed). RGB, 0–1.
6. **Animations**: up to `MAX_FRAMES` evenly spaced frames, each through both models.
7. **Inference**: a pool of TFLite interpreters and one thread-safe ONNX session, so
   requests run in parallel without blocking the event loop.

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `HOST` / `PORT` | `127.0.0.1` / `8000` | Bind address (`run.sh`) |
| `MODEL_PATH` | `./nsfw.tflite` | Open_NSFW model |
| `DEFAULT_THRESHOLD` | `0.8` | Open_NSFW cutoff when the request gives none |
| `ENABLE_NUDENET` | `true` | `false` = Open_NSFW only |
| `NUDENET_MODEL_PATH` | `./nudenet_320n.onnx` | NudeNet model |
| `NUDENET_THRESHOLD` | `0.6` | NudeNet cutoff when the request gives none |
| `NUM_INTERPRETERS` | min(4, CPU count) | Parallel Open_NSFW inferences |
| `THREADS_PER_INTERPRETER` | `2` | CPU threads per inference (both models) |
| `MAX_UPLOAD_MB` | `15` | Per image |
| `MAX_BATCH_SIZE` | `20` | Images per batch request |
| `MAX_PIXELS` | `50000000` | Decoded size limit |
| `MAX_FRAMES` | `8` | Frames checked per animation |
| `API_KEYS` | *(empty = no key needed)* | Comma-separated keys for the `X-API-Key` header |
| `CORS_ORIGINS` | *(empty = CORS off)* | Comma-separated allowed origins |

## Check accuracy on your own photos

Put labelled photos in `<folder>/sfw/` and `<folder>/nsfw/`, then:

```bash
uv run python scripts/evaluate.py <folder>
uv run python scripts/evaluate.py <folder> --nudenet-threshold 0.5
uv run python scripts/evaluate.py <folder> --no-nudenet
```

It prints how many NSFW photos are caught and how many SFW photos are wrongly flagged for
Open_NSFW thresholds 0.2–0.8 (combined with NudeNet), each model alone, and the files the
current settings get wrong.

On a 100-photo test set (50/50), at the defaults: Open_NSFW alone caught 41/50 NSFW with
2 SFW wrongly flagged. Both models together caught 45/50, still with 2 wrongly flagged.

## Layout

```text
app/
  config.py         settings from env
  preprocessing.py  decoding, validation, Open_NSFW tensors
  detector.py       NudeNet: preprocessing, inference, boxes, NMS
  classifier.py     Open_NSFW interpreter pool, combines both models
  schemas.py        request/response models
  main.py           FastAPI app, routes, error mapping
scripts/evaluate.py accuracy on your own labelled photos
tests/              pytest suite (runs against the real models)
```

## Licences

Open_NSFW is BSD-2-Clause (Yahoo). NudeNet is listed as MIT on PyPI. Its model is trained
with Ultralytics YOLOv8 (AGPL-3.0), so check the licence before using it in a commercial product.
