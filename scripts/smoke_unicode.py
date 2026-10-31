#!/usr/bin/env python3
"""Regression test for FFmpeg and OpenCV calls with Windows Unicode paths."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from ffmpeg_utils import (
    VideoFrameReader,
    find_ffmpeg,
    read_image_bgr,
    resolve_output,
    run_command,
)


def main() -> int:
    marker = (
        Path("runtime")
        / "unicode-smoke"
        / f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1000000:06d}"
        / "keep.txt"
    )
    work = resolve_output(marker).parent
    video = work / "中文视频.mp4"
    image = work / "中文背景.png"
    try:
        ffmpeg = find_ffmpeg()
        run_command(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=green:s=160x120:r=12:d=1",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                video,
            ]
        )
        run_command(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x203050:s=160x120",
                "-frames:v",
                "1",
                image,
            ]
        )
        reader = VideoFrameReader(video)
        frame_count = sum(1 for _ in reader)
        background = read_image_bgr(image)
        if frame_count != 12:
            raise RuntimeError(f"Expected 12 frames, decoded {frame_count}.")
        if background.shape[:2] != (120, 160):
            raise RuntimeError(f"Unexpected image shape: {background.shape}")
        print(
            json.dumps(
                {
                    "status": "ok",
                    "unicode_video": str(video),
                    "frame_count": frame_count,
                    "unicode_image": str(image),
                    "image_shape": list(background.shape),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
