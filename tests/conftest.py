import io
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import MB, Settings
from app.main import create_app


def make_image(fmt="JPEG", size=(320, 240), color=(40, 120, 200), mode="RGB", **save_kwargs) -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, format=fmt, **save_kwargs)
    return buffer.getvalue()


@pytest.fixture(scope="session")
def settings() -> Settings:
    return replace(
        Settings(),
        num_interpreters=2,
        threads_per_interpreter=1,
        max_upload_bytes=2 * MB,
        max_batch_size=3,
    )


@pytest.fixture(scope="session")
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client
