import base64

import pytest

from app.config import MB
from tests.conftest import make_image


def upload(data: bytes, name: str = "photo.jpg", mime: str = "image/jpeg"):
    return {"file": (name, data, mime)}


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True
    assert body["input_shape"] == [1, 224, 224, 3]
    assert body["classes"] == ["SFW", "NSFW"]
    assert body["models"] == ["open_nsfw", "nudenet"]


def test_predict_jpeg(client):
    response = client.post("/predict", files=upload(make_image()))
    assert response.status_code == 200
    body = response.json()
    assert body["scores"]["sfw"] + body["scores"]["nsfw"] == pytest.approx(1.0, abs=1e-3)
    nude = body["nudenet"]
    expected = (["open_nsfw"] if body["scores"]["nsfw"] >= body["threshold"] else []) + (
        ["nudenet"] if nude["score"] >= nude["threshold"] else []
    )
    assert body["flagged_by"] == expected
    assert body["is_nsfw"] == bool(expected)
    assert body["verdict"] == ("NSFW" if body["is_nsfw"] else "SFW")
    assert nude["threshold"] == 0.6
    assert isinstance(nude["detections"], list)
    assert body["threshold"] == 0.8
    assert body["frames_analyzed"] == 1
    assert body["views_analyzed"] == 3  # 320x240 landscape -> 3 square crops
    assert body["filename"] == "photo.jpg"
    assert set(body["timing"]) == {"preprocess_ms", "inference_ms", "total_ms"}


def test_threshold_controls_verdict(client):
    data = make_image()
    body = client.post("/predict?threshold=0&nudenet_threshold=1", files=upload(data)).json()
    assert (body["verdict"], body["flagged_by"]) == ("NSFW", ["open_nsfw"])
    body = client.post("/predict?threshold=1&nudenet_threshold=0", files=upload(data)).json()
    assert (body["verdict"], body["flagged_by"]) == ("NSFW", ["nudenet"])
    body = client.post("/predict?threshold=1&nudenet_threshold=1", files=upload(data)).json()
    assert (body["verdict"], body["flagged_by"]) == ("SFW", [])


def test_nudenet_can_be_disabled(settings):
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(replace(settings, enable_nudenet=False))) as c:
        assert c.get("/health").json()["models"] == ["open_nsfw"]
        body = c.post("/predict", files=upload(make_image())).json()
        assert body["nudenet"] is None


def test_threshold_out_of_range(client):
    assert client.post("/predict?threshold=1.5", files=upload(make_image())).status_code == 422


def test_format_detected_from_bytes_not_name(client):
    # A PNG sent with a wrong name and generic MIME type is still accepted.
    response = client.post(
        "/predict", files=upload(make_image("PNG"), "upload.bin", "application/octet-stream")
    )
    assert response.status_code == 200


def test_predict_heic(client):
    response = client.post("/predict", files=upload(make_image("HEIF"), "IMG_0001.HEIC", "image/heic"))
    assert response.status_code == 200
    assert response.json()["filename"] == "IMG_0001.HEIC"


@pytest.mark.parametrize(
    "data, code",
    [
        (b"not an image", 400),
        (b"", 400),
        (make_image("TIFF"), 415),
        (b"\xff" * (2 * MB + 1), 413),
    ],
    ids=["garbage", "empty", "tiff", "too-big"],
)
def test_predict_rejects_bad_input(client, data, code):
    response = client.post("/predict", files=upload(data))
    assert response.status_code == code
    assert "detail" in response.json()


def test_request_body_cap(client, settings):
    response = client.post(
        "/predict",
        content=b"x" * (settings.max_request_bytes + 1),
        headers={"content-type": "multipart/form-data; boundary=x"},
    )
    assert response.status_code == 413


def test_batch_reports_each_item(client):
    files = [
        ("files", ("good.jpg", make_image(), "image/jpeg")),
        ("files", ("bad.jpg", b"broken", "image/jpeg")),
    ]
    body = client.post("/predict/batch", files=files).json()
    assert (body["total"], body["succeeded"], body["failed"]) == (2, 1, 1)
    good, bad = body["items"]
    assert good["result"]["filename"] == "good.jpg" and good["error"] is None
    assert bad["result"] is None and bad["error"]


def test_batch_size_limit(client, settings):
    files = [("files", (f"{i}.jpg", make_image(), "image/jpeg")) for i in range(settings.max_batch_size + 1)]
    assert client.post("/predict/batch", files=files).status_code == 400


@pytest.mark.parametrize("prefix", ["", "data:image/png;base64,"])
def test_base64(client, prefix):
    encoded = prefix + base64.b64encode(make_image("PNG")).decode()
    response = client.post("/predict/base64", json={"image": encoded, "threshold": 0.5})
    assert response.status_code == 200
    assert response.json()["threshold"] == 0.5


def test_base64_invalid(client):
    assert client.post("/predict/base64", json={"image": "%%%not base64%%%"}).status_code == 400


def test_security_headers(client):
    headers = client.get("/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
