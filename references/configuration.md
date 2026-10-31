# Configuration and pipeline schema

## Workspace

Generated output must stay under `F:\workspace` by default. Override only when the user explicitly requests another workspace:

```powershell
$env:AIVIDEO_WORKSPACE = 'F:\workspace'
```

Useful environment variables:

- `AIVIDEO_MODEL_DIR`: InsightFace ONNX model directory. Default: `F:\视频\.tools\models\insightface`.
- `AIVIDEO_FFMPEG`: explicit `ffmpeg.exe` path.
- `AIVIDEO_FFPROBE`: explicit `ffprobe.exe` path.
- `AIVIDEO_PYTHON`: Python executable used by the Wav2Lip backend.

The skill runtime is created under `runtime\.venv` by `scripts\setup.ps1`. Do not install generated Python packages or caches outside `F:\workspace`.

## Pipeline file

Paths may be absolute or relative to the pipeline file. `output` and every intermediate result must resolve under the configured workspace.

```json
{
  "name": "authorized-avatar-demo",
  "input": "inputs/target.mp4",
  "output": "outputs/final.mp4",
  "steps": [
    {
      "type": "background_replace",
      "background": "inputs/background.png",
      "engine": "auto"
    },
    {
      "type": "face_swap",
      "source": "inputs/source.png"
    },
    {
      "type": "lip_sync",
      "audio": "inputs/voice.wav",
      "wav2lip_dir": "F:/workspace/models/Wav2Lip",
      "checkpoint": "F:/workspace/models/wav2lip_gan.pth"
    }
  ],
  "confirm_authorized": true
}
```

Supported step types:

- `background_replace`: `background`, `engine` (`auto`, `rembg`, `chroma`, `matte`), and chroma/matte options.
- `face_swap`: `source` and an optional `model_dir`.
- `avatar_replace`: same fields as `face_swap`, plus optional `background`.
- `lip_sync`: `audio`, `wav2lip_dir`, `checkpoint`, and optional `python`.

Every intermediate and final media file is written beneath `runtime\jobs\<job-id>`. The adjacent `job.json` records step status and the last error.

## Exit behavior

- `0`: requested operation completed and the output file exists.
- `2`: invalid user input, missing model/backend, or authorization flag absent.
- `3`: ffmpeg or media-processing failure.

Never report success based only on exit code `0`; probe the output and inspect representative pixels.
