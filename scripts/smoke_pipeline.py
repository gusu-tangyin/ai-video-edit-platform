#!/usr/bin/env python3
"""End-to-end smoke test for the JSON multi-step pipeline."""

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
    first_stream,
    probe_media,
    resolve_output,
    run_command,
)


def main() -> int:
    marker = (
        Path("runtime")
        / "pipeline-smoke"
        / f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1000000:06d}"
        / "keep.txt"
    )
    work = resolve_output(marker).parent
    source = work / "source.mp4"
    background = work / "background.png"
    output = work / "result.mp4"
    config = work / "pipeline.json"
    jobs_root = resolve_output(Path("runtime") / "jobs" / "keep.txt").parent
    before_jobs = {path.name for path in jobs_root.iterdir() if path.is_dir()}
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
                "color=c=green:s=320x240:r=12:d=1",
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
        config.write_text(
            json.dumps(
                {
                    "input": str(source),
                    "output": str(output),
                    "steps": [
                        {
                            "type": "background_replace",
                            "background": str(background),
                            "engine": "chroma",
                            "chroma_color": "0x00FF00",
                        }
                    ],
                    "confirm_authorized": True,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("aivideo.py")),
                "run-pipeline",
                "--config",
                str(config),
            ],
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout)
        metadata = probe_media(output)
        video = first_stream(metadata, "video")
        audio = first_stream(metadata, "audio")
        if not video or video.get("width") != 320 or video.get("height") != 240:
            raise RuntimeError(f"Unexpected pipeline video metadata: {video}")
        if not audio:
            raise RuntimeError("Pipeline output did not preserve source audio.")
        print(
            json.dumps(
                {
                    "status": "ok",
                    "workspace": str(WORKSPACE),
                    "output": str(output),
                    "width": video.get("width"),
                    "height": video.get("height"),
                    "audio_preserved": True,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)
        if jobs_root.exists():
            for path in jobs_root.iterdir():
                if path.is_dir() and path.name not in before_jobs:
                    shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
