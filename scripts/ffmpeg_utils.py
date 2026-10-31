from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any


DEFAULT_WORKSPACE = Path(r"F:\workspace")
WORKSPACE = Path(os.environ.get("AIVIDEO_WORKSPACE", DEFAULT_WORKSPACE)).resolve()


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not reconfigure:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


_configure_utf8_stdio()


class MediaError(RuntimeError):
    pass


def resolve_input(path: str | Path) -> Path:
    value = Path(path).expanduser().resolve()
    if not value.exists():
        raise FileNotFoundError(f"Input does not exist: {value}")
    return value


def resolve_output(path: str | Path) -> Path:
    value = Path(path).expanduser()
    if not value.is_absolute():
        value = WORKSPACE / value
    value = value.resolve()
    try:
        value.relative_to(WORKSPACE)
    except ValueError as exc:
        raise ValueError(
            f"Output must stay under the configured workspace {WORKSPACE}: {value}"
        ) from exc
    value.parent.mkdir(parents=True, exist_ok=True)
    return value


def _candidate_paths(name: str) -> list[Path]:
    exe = f"{name}.exe" if os.name == "nt" else name
    env_value = os.environ.get(f"AIVIDEO_{name.upper()}")
    candidates: list[Path] = []
    if env_value:
        candidates.append(Path(env_value))
    which = shutil.which(name)
    if which:
        candidates.append(Path(which))
    candidates.extend(
        [
            WORKSPACE / "runtime" / "bin" / exe,
            WORKSPACE
            / "runtime"
            / "node"
            / "video-talkcraft"
            / "node_modules"
            / "@remotion"
            / "compositor-win32-x64-msvc"
            / exe,
            Path(r"C:\Users\Hp\Documents\Codex\tools\bin") / exe,
        ]
    )
    return candidates


def find_ffmpeg() -> Path:
    for candidate in _candidate_paths("ffmpeg"):
        if candidate.is_file():
            return candidate.resolve()
    raise MediaError(
        "ffmpeg was not found. Set AIVIDEO_FFMPEG or run scripts\\setup.ps1."
    )


def find_ffprobe() -> Path:
    for candidate in _candidate_paths("ffprobe"):
        if candidate.is_file():
            return candidate.resolve()
    ffmpeg = find_ffmpeg()
    sibling = ffmpeg.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    if sibling.is_file():
        return sibling.resolve()
    raise MediaError(
        "ffprobe was not found. Set AIVIDEO_FFPROBE or provide ffprobe beside ffmpeg."
    )


def run_command(command: list[str | Path], *, check: bool = True) -> subprocess.CompletedProcess:
    printable = " ".join(str(part) for part in command)
    print(f"[run] {printable}", file=sys.stderr, flush=True)
    result = subprocess.run(
        [str(part) for part in command],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise MediaError(
            f"Command failed with exit code {result.returncode}: {printable}\n{detail}"
        )
    return result


def probe_media(path: str | Path) -> dict[str, Any]:
    media = resolve_input(path)
    ffprobe = find_ffprobe()
    result = run_command(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,sample_rate,channels,pix_fmt",
            "-of",
            "json",
            media,
        ]
    )
    data = json.loads(result.stdout or "{}")
    data["path"] = str(media)
    return data


def first_stream(probe: dict[str, Any], codec_type: str) -> dict[str, Any] | None:
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == codec_type:
            return stream
    return None


class VideoFrameReader:
    """Decode BGR frames through FFmpeg, including Windows Unicode paths."""

    def __init__(self, path: str | Path):
        self.path = resolve_input(path)
        metadata = probe_media(self.path)
        video = first_stream(metadata, "video")
        if not video:
            raise MediaError(f"No video stream found: {self.path}")
        self.width = int(video.get("width") or 0)
        self.height = int(video.get("height") or 0)
        if self.width <= 0 or self.height <= 0:
            raise MediaError(f"Could not determine video dimensions: {self.path}")
        try:
            self.frame_count = int(video.get("nb_frames") or 0)
        except (TypeError, ValueError):
            self.frame_count = 0
        try:
            self.fps = float(Fraction(str(video.get("avg_frame_rate", "25/1"))))
        except (AttributeError, ValueError):
            self.fps = 25.0

    def __iter__(self):
        import numpy as np

        frame_size = self.width * self.height * 3
        completed = False
        process = subprocess.Popen(
            [
                str(find_ffmpeg()),
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(self.path),
                "-map",
                "0:v:0",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "bgr24",
                "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            assert process.stdout is not None
            while True:
                raw = process.stdout.read(frame_size)
                if not raw:
                    completed = True
                    break
                if len(raw) != frame_size:
                    raise MediaError(
                        f"FFmpeg returned an incomplete frame for {self.path}"
                    )
                yield np.frombuffer(raw, dtype=np.uint8).reshape(
                    self.height, self.width, 3
                )
        finally:
            if process.stdout:
                process.stdout.close()
            if not completed and process.poll() is None:
                process.terminate()
            error = b""
            if process.stderr:
                error = process.stderr.read()
                process.stderr.close()
            code = process.wait()
            if completed and code != 0:
                detail = error.decode("utf-8", errors="replace").strip()
                raise MediaError(
                    f"FFmpeg frame decode failed with exit code {code}: {detail}"
                )


def read_image_bgr(path: str | Path):
    """Read a BGR image without OpenCV's Windows ANSI-path limitation."""

    import cv2
    import numpy as np

    image_path = resolve_input(path)
    try:
        data = np.fromfile(str(image_path), dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Could not read image: {image_path}") from exc
    if image is None:
        raise RuntimeError(f"Could not decode image: {image_path}")
    return image


def require_video(path: str | Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    media = resolve_input(path)
    metadata = probe_media(media)
    video = first_stream(metadata, "video")
    if not video:
        raise MediaError(f"No video stream found: {media}")
    return media, metadata, video


def mux_audio(
    video_path: str | Path,
    audio_source: str | Path,
    output_path: str | Path,
) -> Path:
    video = resolve_input(video_path)
    audio = resolve_input(audio_source)
    output = resolve_output(output_path)
    audio_stream = first_stream(probe_media(audio), "audio")
    if not audio_stream:
        raise MediaError(f"No audio stream found: {audio}")
    run_command(
        [
            find_ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            video,
            "-i",
            audio,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            output,
        ]
    )
    return output


def write_json(path: str | Path, data: dict[str, Any]) -> Path:
    output = resolve_output(path)
    output.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output
