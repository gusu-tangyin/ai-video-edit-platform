from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from ffmpeg_utils import (
    VideoFrameReader,
    find_ffmpeg,
    read_image_bgr,
    resolve_input,
    resolve_output,
)


DEFAULT_MODEL_DIR = Path(
    os.environ.get("AIVIDEO_MODEL_DIR", r"F:\视频\.tools\models\insightface")
)

ARCFACE_DST = (
    (38.2946, 51.6963),
    (73.5318, 51.5014),
    (56.0252, 71.7366),
    (41.5493, 92.3655),
    (70.7299, 92.2041),
)


def _imports():
    try:
        import cv2
        import numpy as np
        import onnx
        import onnxruntime as ort
        from onnx import numpy_helper
    except ImportError as exc:
        raise RuntimeError(
            "Face-swap dependencies are missing. Run scripts\\setup.ps1 first."
        ) from exc
    return cv2, np, onnx, ort, numpy_helper


def _session(ort, model_path: Path, accelerator: bool):
    if not model_path.is_file():
        raise FileNotFoundError(f"Model not found: {model_path}")
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.intra_op_num_threads = min(8, os.cpu_count() or 4)
    options.log_severity_level = 3
    available = set(ort.get_available_providers())
    providers = ["CPUExecutionProvider"]
    if accelerator and "DmlExecutionProvider" in available:
        providers.insert(0, "DmlExecutionProvider")
    return ort.InferenceSession(str(model_path), sess_options=options, providers=providers)


class SCRFD:
    def __init__(self, model_path: Path, ort):
        self.np = __import__("numpy")
        self.session = _session(ort, model_path, accelerator=False)
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [item.name for item in self.session.get_outputs()]
        self.strides = (8, 16, 32)
        self.anchor_counts = (2, 2, 2)

    def _nms(self, detections, threshold):
        np = self.np
        if len(detections) == 0:
            return detections
        x1, y1, x2, y2 = detections[:, :4].T
        areas = np.maximum(0, x2 - x1 + 1) * np.maximum(0, y2 - y1 + 1)
        order = detections[:, -1].argsort()[::-1]
        keep = []
        while order.size:
            current = order[0]
            keep.append(current)
            xx1 = np.maximum(x1[current], x1[order[1:]])
            yy1 = np.maximum(y1[current], y1[order[1:]])
            xx2 = np.minimum(x2[current], x2[order[1:]])
            yy2 = np.minimum(y2[current], y2[order[1:]])
            intersection = np.maximum(0, xx2 - xx1 + 1) * np.maximum(
                0, yy2 - yy1 + 1
            )
            union = areas[current] + areas[order[1:]] - intersection
            overlap = intersection / np.maximum(union, 1e-6)
            order = order[1:][overlap <= threshold]
        return detections[keep]

    def detect(self, image, threshold=0.45):
        np = self.np
        height, width = image.shape[:2]
        ratio = width / max(height, 1)
        resized_width = 640
        resized_height = int(resized_width / max(ratio, 1e-6))
        if resized_height > 640:
            resized_height = 640
            resized_width = int(resized_height * ratio)
        scale = resized_height / max(height, 1)
        resized = __import__("cv2").resize(
            image, (resized_width, resized_height), interpolation=0
        )
        canvas = np.zeros((640, 640, 3), dtype=np.uint8)
        canvas[:resized_height, :resized_width] = resized
        blob = ((canvas.astype(np.float32) - 127.5) / 128.0).transpose(2, 0, 1)
        outputs = self.session.run(
            self.output_names, {self.input_name: np.ascontiguousarray(blob[None])}
        )
        feature_count = len(self.strides)
        all_detections = []
        for index, stride in enumerate(self.strides):
            scores = outputs[index].reshape(-1)
            boxes = outputs[index + feature_count].reshape(-1, 4) * stride
            keypoints = outputs[index + feature_count * 2].reshape(-1, 10) * stride
            grid_height = 640 // stride
            grid_width = 640 // stride
            centers = np.stack(
                np.mgrid[:grid_height, :grid_width][::-1], axis=-1
            ).astype(np.float32)
            centers = (centers * stride).reshape((-1, 2))
            centers = np.stack(
                [centers] * self.anchor_counts[index], axis=1
            ).reshape((-1, 2))
            positive = np.where(scores >= threshold)[0]
            if positive.size == 0:
                continue
            positive_boxes = np.empty_like(boxes[positive])
            positive_boxes[:, 0] = centers[positive, 0] - boxes[positive, 0]
            positive_boxes[:, 1] = centers[positive, 1] - boxes[positive, 1]
            positive_boxes[:, 2] = centers[positive, 0] + boxes[positive, 2]
            positive_boxes[:, 3] = centers[positive, 1] + boxes[positive, 3]
            positive_keypoints = np.empty_like(keypoints[positive])
            for offset in range(0, 10, 2):
                positive_keypoints[:, offset] = (
                    centers[positive, 0] + keypoints[positive, offset]
                )
                positive_keypoints[:, offset + 1] = (
                    centers[positive, 1] + keypoints[positive, offset + 1]
                )
            all_detections.append(
                np.concatenate(
                    [positive_boxes, positive_keypoints, scores[positive, None]],
                    axis=1,
                ).astype(np.float32)
            )
        if not all_detections:
            return np.empty((0, 15), dtype=np.float32)
        detections = self._nms(np.concatenate(all_detections), 0.4)
        detections[:, :14] /= max(scale, 1e-6)
        detections[:, [0, 2, 3, 5, 7, 9, 11, 13]] = np.clip(
            detections[:, [0, 2, 3, 5, 7, 9, 11, 13]], 0, width - 1
        )
        detections[:, [1, 4, 6, 8, 10, 12, 14]] = np.clip(
            detections[:, [1, 4, 6, 8, 10, 12, 14]], 0, height - 1
        )
        return detections


def _select_face(faces, previous=None):
    np = __import__("numpy")
    if len(faces) == 0:
        return None
    boxes = faces[:, :4]
    widths = np.maximum(boxes[:, 2] - boxes[:, 0], 1)
    heights = np.maximum(boxes[:, 3] - boxes[:, 1], 1)
    areas = widths * heights
    aspect = widths / heights
    valid = (aspect > 0.28) & (aspect < 1.8) & (areas > 900)
    if not np.any(valid):
        return None
    candidates = faces[valid]
    utilities = areas[valid] * np.sqrt(np.maximum(candidates[:, -1], 0.01))
    if previous is not None:
        previous_center = np.array(
            [
                (previous[0] + previous[2]) * 0.5,
                (previous[1] + previous[3]) * 0.5,
            ]
        )
        centers = np.stack(
            [
                (candidates[:, 0] + candidates[:, 2]) * 0.5,
                (candidates[:, 1] + candidates[:, 3]) * 0.5,
            ],
            axis=1,
        )
        utilities /= 1.0 + np.linalg.norm(centers - previous_center, axis=1) / 180.0
    return candidates[int(np.argmax(utilities))]


def _norm_matrix(landmarks, size=128):
    np = __import__("numpy")
    source = np.asarray(landmarks, dtype=np.float64).reshape(5, 2).T
    destination = np.asarray(ARCFACE_DST, dtype=np.float64) * (size / 112.0)
    target = destination.T
    source_mean = source.mean(axis=1)
    target_mean = target.mean(axis=1)
    source_centered = source - source_mean[:, None]
    target_centered = target - target_mean[:, None]
    covariance = target_centered @ source_centered.T / source.shape[1]
    u, singular_values, vt = np.linalg.svd(covariance)
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        u[:, -1] *= -1
        singular_values[-1] *= -1
        rotation = u @ vt
    scale = singular_values.sum() / max(
        np.mean(np.sum(source_centered**2, axis=0)), 1e-8
    )
    rotation *= scale
    translation = target_mean - rotation @ source_mean
    return np.hstack([rotation, translation[:, None]]).astype(np.float32)


class FaceSwapper:
    def __init__(self, model_dir: Path, ort, onnx, numpy_helper):
        self.cv2 = __import__("cv2")
        self.np = __import__("numpy")
        self.recognizer = _session(ort, model_dir / "arcface_w600k_r50.onnx", False)
        self.recognizer_input = self.recognizer.get_inputs()[0].name
        self.recognizer_output = self.recognizer.get_outputs()[0].name
        self.swapper = _session(ort, model_dir / "inswapper_128.onnx", True)
        self.swapper_inputs = [item.name for item in self.swapper.get_inputs()]
        model = onnx.load(str(model_dir / "inswapper_128.onnx"))
        self.embedding_map = numpy_helper.to_array(model.graph.initializer[-1])
        self.mask = self._face_mask()

    def embedding(self, aligned):
        face = self.cv2.resize(aligned, (112, 112), interpolation=1)
        blob = face[:, :, ::-1].transpose(2, 0, 1).astype("float32")
        blob = (blob - 127.5) / 127.5
        value = self.recognizer.run(
            [self.recognizer_output],
            {self.recognizer_input: self.np.ascontiguousarray(blob[None])},
        )[0][0]
        return value / max(self.np.linalg.norm(value), 1e-8)

    def _face_mask(self):
        mask = self.np.zeros((128, 128), dtype=self.np.float32)
        self.cv2.ellipse(mask, (64, 65), (51, 64), 0, 0, 360, 1.0, -1)
        mask = self.cv2.GaussianBlur(mask, (0, 0), 5.5)
        return self.np.clip(mask, 0, 1)

    def _match_color(self, fake, target):
        cv2, np = self.cv2, self.np
        central = np.zeros((128, 128), dtype=np.uint8)
        cv2.ellipse(central, (64, 68), (33, 43), 0, 0, 360, 255, -1)
        central = cv2.erode(central, np.ones((9, 9), np.uint8)) > 0
        fake_lab = cv2.cvtColor(fake, cv2.COLOR_BGR2LAB).astype(np.float32)
        target_lab = cv2.cvtColor(target, cv2.COLOR_BGR2LAB).astype(np.float32)
        fake_lab += (
            target_lab[central].mean(axis=0) - fake_lab[central].mean(axis=0)
        ) * 0.58
        return cv2.cvtColor(np.clip(fake_lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)

    def swap(self, image, landmarks, source_embedding):
        cv2, np = self.cv2, self.np
        matrix = _norm_matrix(landmarks)
        aligned = cv2.warpAffine(
            image,
            matrix,
            (128, 128),
            flags=cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_REPLICATE,
        )
        blob = aligned[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
        latent = np.dot(source_embedding.reshape(1, -1), self.embedding_map)
        latent /= max(np.linalg.norm(latent), 1e-8)
        fake = self.swapper.run(
            None,
            {
                self.swapper_inputs[0]: np.ascontiguousarray(blob[None]),
                self.swapper_inputs[1]: latent.astype(np.float32),
            },
        )[0][0]
        fake = np.clip(fake.transpose(1, 2, 0)[:, :, ::-1] * 255, 0, 255).astype(
            np.uint8
        )
        fake = self._match_color(fake, aligned)
        blurred = cv2.GaussianBlur(fake, (0, 0), 1.1)
        fake = cv2.addWeighted(fake, 1.32, blurred, -0.32, 0)
        inverse = cv2.invertAffineTransform(matrix)
        height, width = image.shape[:2]
        warped = cv2.warpAffine(
            fake,
            inverse,
            (width, height),
            flags=cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_REFLECT,
        )
        warped_mask = cv2.warpAffine(
            self.mask,
            inverse,
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
        )
        warped_mask = np.clip(cv2.GaussianBlur(warped_mask, (0, 0), 1.8), 0, 1)[
            ..., None
        ]
        return (
            warped.astype(np.float32) * warped_mask
            + image.astype(np.float32) * (1 - warped_mask)
        ).astype(np.uint8)


def run_face_swap(
    input_path: str | Path,
    source_path: str | Path,
    output_path: str | Path,
    *,
    model_dir: str | Path = DEFAULT_MODEL_DIR,
    accelerator: bool = True,
) -> Path:
    cv2, np, onnx, ort, numpy_helper = _imports()
    source = resolve_input(source_path)
    video = resolve_input(input_path)
    output = resolve_output(output_path)
    models = Path(model_dir).expanduser().resolve()
    detector_model = models / "scrfd_10g.onnx"
    if not detector_model.is_file():
        raise FileNotFoundError(f"Model not found: {detector_model}")
    detector = SCRFD(detector_model, ort)
    swapper = FaceSwapper(models, ort, onnx, numpy_helper)

    source_image = read_image_bgr(source)
    source_face = _select_face(detector.detect(source_image, threshold=0.45))
    if source_face is None:
        raise RuntimeError("No usable face was detected in the source image.")
    source_matrix = _norm_matrix(source_face[4:14])
    source_aligned = cv2.warpAffine(
        source_image,
        source_matrix,
        (128, 128),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_REPLICATE,
    )
    embedding = swapper.embedding(source_aligned)

    reader = VideoFrameReader(video)
    width = reader.width
    height = reader.height
    fps = reader.fps
    frame_total = reader.frame_count
    ffmpeg = find_ffmpeg()
    command = [
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
        "-i",
        str(video),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
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
        str(output),
    ]
    encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
    started = time.perf_counter()
    processed = 0
    swapped = 0
    previous = None
    try:
        for frame in reader:
            face = _select_face(detector.detect(frame, threshold=0.42), previous)
            result = frame if face is None else swapper.swap(frame, face[4:14], embedding)
            if face is not None:
                previous = face
                swapped += 1
            encoder.stdin.write(np.ascontiguousarray(result).tobytes())
            processed += 1
            if processed % 50 == 0:
                elapsed = max(time.perf_counter() - started, 1e-6)
                print(
                    f"face-swap {processed}/{frame_total or '?'} "
                    f"({processed / elapsed:.2f} fps), swapped={swapped}",
                    file=sys.stderr,
                    flush=True,
                )
    finally:
        if encoder.stdin:
            encoder.stdin.close()
    code = encoder.wait()
    if code != 0:
        raise RuntimeError(f"ffmpeg encoding failed with exit code {code}")
    if swapped == 0:
        output.unlink(missing_ok=True)
        raise RuntimeError("No usable target face was detected; output was discarded.")
    print(
        f"face-swap complete: {processed} frames, {swapped} swapped, output={output}",
        file=sys.stderr,
    )
    return output
