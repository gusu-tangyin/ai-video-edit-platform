#!/usr/bin/env python3
"""Installation check for the AI Video Editing Studio skill."""

from __future__ import annotations

import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from aivideo import doctor  # noqa: E402


if __name__ == "__main__":
    result = doctor()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    core_ready = all(
        (
            result.get("ffmpeg"),
            result.get("ffprobe"),
            result["dependencies"].get("cv2"),
            result["dependencies"].get("numpy"),
            result["backends"].get("background_chroma"),
        )
    )
    raise SystemExit(0 if core_ready else 1)
