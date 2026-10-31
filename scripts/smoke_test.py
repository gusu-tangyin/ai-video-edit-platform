#!/usr/bin/env python3
"""FFmpeg-only end-to-end smoke test for the background replacement path."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ffmpeg_utils import (
    WORKSPACE,
    find_ffmpeg,
    probe_media,
    resolve_output,
    run_command,
)


def main() -> int:
    ffmpeg = find_ffmpeg()
    smoke_marker = (
        Path("runtime")
        / "smoke"
        / f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1000000:06d}"
        / "keep.json"
    )
    work = resolve_output(smoke_marker).parent
    source = work / "green.mp4"
    background = work / "background.png"
    output = work / "result.mp4"
    try:
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
                "color=c=green:s=320x240:r=24:d=1",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000:duration=1",
                "-vf",
                "drawbox=x=110:y=60:w=100:h=120:color=blue:t=fill",
                "-shortest",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                source,
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
                "color=c=0x203050:s=640x360",
                "-frames:v",
                "1",
                background,
            ]
        )
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("aivideo.py")),
                "background",
                "--input",
                str(source),
                "--background",
                str(background),
                "--output",
                str(output),
                "--engine",
                "chroma",
                "--chroma-color",
                "0x00FF00",
            ],
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout)
        metadata = probe_media(output)
        video = next(
            item
            for item in metadata.get("streams", [])
            if item.get("codec_type") == "video"
        )
        audio = next(
            (
                item
                for item in metadata.get("streams", [])
                if item.get("codec_type") == "audio"
            ),
            None,
        )
        print(
            json.dumps(
                {
                    "status": "ok",
                    "workspace": str(WORKSPACE),
                    "output": str(output),
                    "width": video.get("width"),
                    "height": video.get("height"),
                    "audio_preserved": audio is not None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        if work.exists() and output.is_file():
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
