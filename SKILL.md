---
name: ai-video-edit-platform
description: Build and run local AI video-editing pipelines for authorized face replacement, avatar replacement, lip sync, background replacement, video probing, and multi-step composition. Use when the user asks for a modular video-editing workflow that combines these operations or needs model/backend readiness checks.
---

# AI Video Edit Platform

Run the local CLI from this skill instead of recreating video-processing code for each request.
The wrapper prefers `runtime\.venv` and falls back to a system Python:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\aivideo.ps1 --help
```

## Operating order

1. Run readiness checks and inspect the returned paths before promising an output:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\aivideo.ps1 doctor --json
   ```

2. Probe every source with `probe`. Confirm codec, dimensions, FPS, pixel format,
   duration, and whether audio exists.
3. Use one command for a single operation or a JSON pipeline for multiple steps.
4. Inspect the actual output with ffprobe and a small contact sheet or representative frames. A successful process exit is not sufficient.
5. Keep generated files under `F:\workspace`. The CLI rejects output paths outside that workspace unless `AIVIDEO_WORKSPACE` is deliberately changed.

## Commands

```powershell
# Background replacement: rembg, green-screen chroma key, or alpha matte.
powershell -ExecutionPolicy Bypass -File scripts\aivideo.ps1 background --input IN.mp4 --background BG.png --output OUT.mp4 --engine auto

# Face swap using the local InsightFace ONNX models.
powershell -ExecutionPolicy Bypass -File scripts\aivideo.ps1 face-swap --input TARGET.mp4 --source SOURCE.png --output OUT.mp4 --confirm-authorized

# Avatar replacement: face swap plus optional background replacement.
powershell -ExecutionPolicy Bypass -File scripts\aivideo.ps1 avatar-replace --input TARGET.mp4 --source SOURCE.png --background BG.png --output OUT.mp4 --confirm-authorized

# Lip sync through a configured Wav2Lip checkout.
powershell -ExecutionPolicy Bypass -File scripts\aivideo.ps1 lip-sync --input IN.mp4 --audio VOICE.wav --wav2lip-dir F:\workspace\models\Wav2Lip --checkpoint F:\workspace\models\wav2lip_gan.pth --output OUT.mp4 --confirm-authorized

# Multi-step orchestration.
powershell -ExecutionPolicy Bypass -File scripts\aivideo.ps1 run-pipeline --config F:\workspace\jobs\pipeline.json
```

## Constraints

- Face, avatar, and lip-sync processing must be limited to media the user owns or is authorized to modify. Require `--confirm-authorized`; do not infer consent from a generic editing request.
- Do not install or download model weights implicitly. Report missing backends and point to [references/backends.md](references/backends.md).
- Default model paths are machine configuration, not part of the skill package. Use `AIVIDEO_MODEL_DIR` or command options.
- Preserve source audio unless the selected operation explicitly replaces it. Lip sync must use the requested voice track, not silence.
- If a video has no audio, do not claim audio was preserved. If a face is not detected in a sampled frame, report that frame and do not silently substitute another identity.

## References

- Read [references/configuration.md](references/configuration.md) before editing the pipeline schema, model paths, or workspace rules.
- Read [references/backends.md](references/backends.md) when setting up InsightFace, Wav2Lip, rembg, or ffmpeg.
