# Third-party notices

This project includes two model files made by other people. Each keeps its own licence.

## Open_NSFW — `nsfw.tflite`

- Source: <https://github.com/yahoo/open_nsfw>
- Licence: BSD 2-Clause
- `nsfw.tflite` is the open_nsfw model converted to TensorFlow Lite.

```text
Copyright 2016, Yahoo Inc.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## NudeNet — `nudenet_320n.onnx`

- Source: <https://github.com/notAI-tech/NudeNet> (the `320n` detector shipped in the
  `nudenet` Python package, version 3.4.2, file unchanged)
- Licence: **GNU AGPL-3.0**, the licence in the NudeNet GitHub repository. The PyPI page of the
  `nudenet` package lists MIT; this project follows the stricter AGPL-3.0.
- The model is a YOLOv8 detector trained with Ultralytics, which is also AGPL-3.0.
- Full licence text: [LICENSE](LICENSE) (the same AGPL-3.0 text).

## Python dependencies

The packages in `pyproject.toml` (FastAPI, Pillow, NumPy, ai-edge-litert, onnxruntime,
pillow-heif and others) are not included in this repository. They are installed from PyPI
under their own licences.
