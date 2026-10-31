# Third-Party Notices and License Boundary

The repository's [MIT License](LICENSE) applies only to the original source
code, scripts, and documentation authored for this project. It does not apply
to third-party software, model weights, trademarks, media, or other materials.

## Model weights are not distributed or relicensed

This repository does not include model weights. The face-swap backend can use
externally supplied files such as:

- `scrfd_10g.onnx`
- `arcface_w600k_r50.onnx`
- `inswapper_128.onnx`
- Wav2Lip checkpoints such as `wav2lip_gan.pth`

Those files remain subject to the licenses and terms imposed by their
upstream authors or distributors. Do not assume that the repository's MIT
License grants permission to use, redistribute, modify, or commercialize
those files. Some model distributions may impose research-only,
non-commercial, attribution, or redistribution restrictions.

Relevant upstream projects include:

- InsightFace: <https://github.com/deepinsight/insightface>
- Wav2Lip: <https://github.com/Rudrabha/Wav2Lip>

Review the exact model files and distribution terms you obtain. Upstream terms
take precedence over any statement in this repository.

## External software and dependencies

The repository invokes or depends on separately licensed software, including
FFmpeg, ONNX Runtime, OpenCV, NumPy, and optional rembg packages. Installing or
using those components does not place them under this repository's MIT License.
Their own licenses and distribution terms continue to apply.

For FFmpeg licensing information, see <https://ffmpeg.org/legal.html>. For
Python dependencies, inspect the version-specific package metadata and source
distribution used in your environment.

## User media

No user media is included in this repository. Users are responsible for
holding the necessary rights, consent, and permissions for footage, images,
voices, likenesses, and other material processed with this project.

## No additional rights

Nothing in this repository grants rights to third-party trademarks, model
weights, datasets, media, patents, or proprietary technology owned by others.
