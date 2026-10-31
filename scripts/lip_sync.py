from __future__ import annotations

import os
import shutil
from pathlib import Path

from ffmpeg_utils import probe_media, resolve_input, resolve_output, run_command


def _python_path(explicit: str | Path | None) -> Path:
    value = explicit or os.environ.get("AIVIDEO_PYTHON")
    if value:
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Wav2Lip Python not found: {path}")
        return path
    found = shutil.which("python")
    if found:
        return Path(found).resolve()
    raise FileNotFoundError(
        "No Wav2Lip Python interpreter was supplied. Use --python or AIVIDEO_PYTHON."
    )


def run_lip_sync(
    input_path: str | Path,
    audio_path: str | Path,
    output_path: str | Path,
    *,
    wav2lip_dir: str | Path,
    checkpoint: str | Path,
    python: str | Path | None = None,
    resize_factor: int = 1,
    pads: tuple[int, int, int, int] = (0, 10, 0, 0),
) -> Path:
    video = resolve_input(input_path)
    audio = resolve_input(audio_path)
    output = resolve_output(output_path)
    repo = Path(wav2lip_dir).expanduser().resolve()
    inference = repo / "inference.py"
    weights = Path(checkpoint).expanduser().resolve()
    if not inference.is_file():
        raise FileNotFoundError(f"Wav2Lip inference.py not found: {inference}")
    if not weights.is_file():
        raise FileNotFoundError(f"Wav2Lip checkpoint not found: {weights}")
    interpreter = _python_path(python)
    command = [
        interpreter,
        inference,
        "--checkpoint_path",
        weights,
        "--face",
        video,
        "--audio",
        audio,
        "--outfile",
        output,
        "--resize_factor",
        str(resize_factor),
        "--pads",
        *(str(value) for value in pads),
    ]
    run_command(command)
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("Wav2Lip returned success but no usable output was created.")
    metadata = probe_media(output)
    streams = metadata.get("streams", [])
    if not any(item.get("codec_type") == "audio" for item in streams):
        raise RuntimeError("Wav2Lip output has no audio stream.")
    return output
