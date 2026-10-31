# Backend setup

## InsightFace ONNX face swap

The face-swap backend uses three model files:

- `scrfd_10g.onnx`
- `arcface_w600k_r50.onnx`
- `inswapper_128.onnx`

Point `AIVIDEO_MODEL_DIR` at their directory. The current machine already has compatible copies in `F:\视频\.tools\models\insightface`. Model files are not copied or redistributed with this skill. Check the applicable model license before commercial use.

The repository's MIT License does not apply to these model files. See
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) for the project's license
boundary.

## Wav2Lip

Provide a Wav2Lip checkout containing `inference.py` and a compatible checkpoint such as `wav2lip_gan.pth`. The wrapper invokes that checkout in a separate Python process because Wav2Lip dependencies commonly conflict with the main skill runtime.

Recommended layout:

```text
F:\workspace\models\Wav2Lip\
  inference.py
  checkpoints\
  face_detection\
F:\workspace\models\wav2lip_gan.pth
```

Do not download weights without explicit user approval. Verify the output's lip movement, frame count, audio duration, and drift on representative clips.

Wav2Lip source code and checkpoints are external third-party materials and are
not licensed by this repository. Their upstream terms control their use and
redistribution.

## Background replacement

Backends are selected in this order by `engine=auto`:

1. `chroma`: ffmpeg chroma key for a solid green/blue background.
2. `matte`: an RGBA video with an existing alpha matte.
3. `rembg`: frame-by-frame AI segmentation when the `rembg` package and model are installed.

`chroma` works without model downloads. `rembg` requires optional installation and may download its first model unless a local model is configured.

## ffmpeg

The CLI searches `AIVIDEO_FFMPEG`, `PATH`, the skill runtime, and the known workspace/Codex tool locations. `doctor` reports the exact executable it found. Never substitute a different codec silently when the requested output format cannot preserve audio.
