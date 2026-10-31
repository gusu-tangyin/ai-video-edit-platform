from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

from ffmpeg_utils import (
    MediaError,
    VideoFrameReader,
    find_ffmpeg,
    first_stream,
    probe_media,
    read_image_bgr,
    resolve_input,
    resolve_output,
    run_command,
)


PACKAGE_MISSING = (
    "Background replacement requires either a chroma color, an RGBA source, "
    "or the optional rembg package. Run scripts\\setup.ps1 -WithRembg."
)


def _chroma_filter(width: int, height: int, color: str, similarity: float, blend: float) -> str:
    return (
        f"[0:v]chromakey={color}:{similarity}:{blend},format=rgba[fg];"
        f"[1:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}[bg];"
        "[bg][fg]overlay=shortest=1:format=auto[v]"
    )


def _run_ffmpeg_composite(
    input_path: Path,
    background_path: Path,
    output_path: Path,
    filter_graph: str,
) -> Path:
    run_command(
        [
            find_ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            input_path,
            "-loop",
            "1",
            "-i",
            background_path,
            "-filter_complex",
            filter_graph,
            "-map",
            "[v]",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            output_path,
        ]
    )
    return output_path


def _run_chroma(
    input_path: Path,
    background_path: Path,
    output_path: Path,
    color: str,
    similarity: float,
    blend: float,
) -> Path:
    video = first_stream(probe_media(input_path), "video")
    if not video:
        raise MediaError("No video stream found.")
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    if width <= 0 or height <= 0:
        raise MediaError("Could not determine video dimensions.")
    return _run_ffmpeg_composite(
        input_path,
        background_path,
        output_path,
        _chroma_filter(width, height, color, similarity, blend),
    )


def _run_matte(input_path: Path, background_path: Path, output_path: Path) -> Path:
    video = first_stream(probe_media(input_path), "video")
    if not video:
        raise MediaError("No video stream found.")
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    graph = (
        "[0:v]format=rgba[fg];"
        f"[1:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}[bg];"
        "[bg][fg]overlay=shortest=1:format=auto[v]"
    )
    return _run_ffmpeg_composite(input_path, background_path, output_path, graph)


def _rembg_available() -> bool:
    try:
        import rembg  # noqa: F401
    except ImportError:
        return False
    return True


def _cover(image, width: int, height: int):
    cv2 = __import__("cv2")
    image_height, image_width = image.shape[:2]
    scale = max(width / max(image_width, 1), height / max(image_height, 1))
    resized = cv2.resize(
        image,
        (max(1, round(image_width * scale)), max(1, round(image_height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    y = max(0, (resized.shape[0] - height) // 2)
    x = max(0, (resized.shape[1] - width) // 2)
    return resized[y : y + height, x : x + width]


def _run_rembg(
    input_path: Path,
    background_path: Path,
    output_path: Path,
    model_name: str | None,
) -> Path:
    try:
        import cv2
        import numpy as np
        from rembg import new_session, remove
    except ImportError as exc:
        raise RuntimeError(PACKAGE_MISSING) from exc
    reader = VideoFrameReader(input_path)
    width = reader.width
    height = reader.height
    fps = reader.fps
    frame_total = reader.frame_count
    bg_image = read_image_bgr(background_path)
    background = _cover(bg_image, width, height)
    session = new_session(model_name) if model_name else new_session()
    silent = output_path.with_name(f"{output_path.stem}.video-only.mp4")
    ffmpeg = find_ffmpeg()
    encoder = __import__("subprocess").Popen(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s:v",
            f"{width}x{height}",
            "-r",
            str(fps),
            "-i",
            "-",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(silent),
        ],
        stdin=__import__("subprocess").PIPE,
    )
    started = time.perf_counter()
    processed = 0
    try:
        for frame in reader:
            rgba = remove(frame, session=session)
            alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0
            composite = (
                rgba[:, :, :3].astype(np.float32) * alpha
                + background.astype(np.float32) * (1.0 - alpha)
            ).astype(np.uint8)
            encoder.stdin.write(np.ascontiguousarray(composite).tobytes())
            processed += 1
            if processed % 20 == 0:
                elapsed = max(time.perf_counter() - started, 1e-6)
                print(
                    f"rembg {processed}/{frame_total or '?'} "
                    f"({processed / elapsed:.2f} fps)",
                    file=sys.stderr,
                    flush=True,
                )
    finally:
        if encoder.stdin:
            encoder.stdin.close()
    code = encoder.wait()
    if code != 0:
        silent.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg encoding failed with exit code {code}")
    if first_stream(probe_media(input_path), "audio"):
        run_command(
            [
                find_ffmpeg(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                silent,
                "-i",
                input_path,
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
                output_path,
            ]
        )
        silent.unlink(missing_ok=True)
    else:
        shutil.move(str(silent), str(output_path))
    return output_path


def run_background_replace(
    input_path: str | Path,
    background_path: str | Path,
    output_path: str | Path,
    *,
    engine: str = "auto",
    chroma_color: str | None = None,
    similarity: float = 0.1,
    blend: float = 0.05,
    rembg_model: str | None = None,
) -> Path:
    source = resolve_input(input_path)
    background = resolve_input(background_path)
    output = resolve_output(output_path)
    normalized = engine.lower().strip()
    if normalized == "auto":
        if chroma_color:
            normalized = "chroma"
        elif _rembg_available():
            normalized = "rembg"
        else:
            video = first_stream(probe_media(source), "video")
            pix_fmt = str((video or {}).get("pix_fmt", ""))
            normalized = "matte" if "a" in pix_fmt.lower() else ""
    if normalized == "chroma":
        if not chroma_color:
            raise ValueError("--chroma-color is required for chroma replacement.")
        return _run_chroma(
            source, background, output, chroma_color, similarity, blend
        )
    if normalized == "matte":
        return _run_matte(source, background, output)
    if normalized == "rembg":
        return _run_rembg(source, background, output, rembg_model)
    raise RuntimeError(PACKAGE_MISSING)
