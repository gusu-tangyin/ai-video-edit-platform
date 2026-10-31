from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from ffmpeg_utils import (
    WORKSPACE,
    MediaError,
    find_ffmpeg,
    find_ffprobe,
    probe_media,
    resolve_input,
    resolve_output,
    write_json,
)


def _module(name: str) -> bool:
    try:
        importlib.import_module(name)
    except Exception:
        return False
    return True


def doctor() -> dict[str, Any]:
    from face_swap import DEFAULT_MODEL_DIR

    result: dict[str, Any] = {
        "python": sys.executable,
        "workspace": str(WORKSPACE),
        "dependencies": {
            "cv2": _module("cv2"),
            "numpy": _module("numpy"),
            "onnx": _module("onnx"),
            "onnxruntime": _module("onnxruntime"),
            "rembg": _module("rembg"),
            "imageio_ffmpeg": _module("imageio_ffmpeg"),
        },
        "models": {},
        "backends": {},
        "optional": {},
    }
    try:
        result["ffmpeg"] = str(find_ffmpeg())
    except Exception as exc:
        result["ffmpeg"] = None
        result["ffmpeg_error"] = str(exc)
    try:
        result["ffprobe"] = str(find_ffprobe())
    except Exception as exc:
        result["ffprobe"] = None
        result["ffprobe_error"] = str(exc)
    model_dir = Path(DEFAULT_MODEL_DIR)
    for filename in (
        "scrfd_10g.onnx",
        "arcface_w600k_r50.onnx",
        "inswapper_128.onnx",
    ):
        path = model_dir / filename
        result["models"][filename] = {
            "path": str(path),
            "ready": path.is_file(),
            "size": path.stat().st_size if path.is_file() else 0,
        }
    deps = result["dependencies"]
    all_models = all(item["ready"] for item in result["models"].values())
    result["backends"]["face_swap"] = all_models and all(
        deps[name] for name in ("cv2", "numpy", "onnx", "onnxruntime")
    )
    result["backends"]["background_chroma"] = bool(result["ffmpeg"])
    result["backends"]["background_rembg"] = deps["rembg"] and bool(result["ffmpeg"])
    wav2lip_dir = Path(
        os.environ.get("AIVIDEO_WAV2LIP_DIR", WORKSPACE / "models" / "Wav2Lip")
    ).expanduser()
    wav2lip_checkpoint = Path(
        os.environ.get(
            "AIVIDEO_WAV2LIP_CHECKPOINT",
            WORKSPACE / "models" / "wav2lip_gan.pth",
        )
    ).expanduser()
    wav2lip_python = Path(
        os.environ.get("AIVIDEO_PYTHON", sys.executable)
    ).expanduser()
    result["optional"]["wav2lip"] = {
        "inference": str(wav2lip_dir / "inference.py"),
        "inference_ready": (wav2lip_dir / "inference.py").is_file(),
        "checkpoint": str(wav2lip_checkpoint),
        "checkpoint_ready": wav2lip_checkpoint.is_file(),
        "python": str(wav2lip_python),
        "python_ready": wav2lip_python.is_file(),
    }
    result["backends"]["lip_sync"] = all(
        (
            result["optional"]["wav2lip"]["inference_ready"],
            result["optional"]["wav2lip"]["checkpoint_ready"],
            result["optional"]["wav2lip"]["python_ready"],
        )
    )
    return result


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _pipeline_path(base: Path, value: str | Path) -> str:
    path = Path(value).expanduser()
    return str(path if path.is_absolute() else (base / path).resolve())


def run_pipeline(config_path: str | Path) -> Path:
    from background_replace import run_background_replace
    from face_swap import DEFAULT_MODEL_DIR, run_face_swap
    from lip_sync import run_lip_sync

    config_file = resolve_input(config_path)
    config = json.loads(config_file.read_text(encoding="utf-8-sig"))
    if not config.get("confirm_authorized"):
        raise ValueError(
            "Pipeline uses identity-changing operations and requires "
            "\"confirm_authorized\": true."
        )
    base = config_file.parent
    input_path = Path(_pipeline_path(base, config["input"]))
    output_path = resolve_output(_pipeline_path(base, config["output"]))
    job_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
    job_dir = resolve_output(Path("runtime") / "jobs" / job_id / "job.json").parent
    job_state: dict[str, Any] = {
        "id": job_id,
        "config": str(config_file),
        "input": str(input_path),
        "output": str(output_path),
        "status": "running",
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        "steps": [],
    }
    write_json(job_dir / "job.json", job_state)
    current = input_path
    try:
        steps = config.get("steps") or []
        if not steps:
            raise ValueError("Pipeline must contain at least one step.")
        for index, step in enumerate(steps, start=1):
            step_type = str(step.get("type", "")).replace("-", "_")
            target = output_path if index == len(steps) else job_dir / f"{index:02d}-{step_type}.mp4"
            state = {"index": index, "type": step_type, "status": "running"}
            job_state["steps"].append(state)
            write_json(job_dir / "job.json", job_state)
            if step_type == "face_swap":
                run_face_swap(
                    current,
                    _pipeline_path(base, step["source"]),
                    target,
                    model_dir=(
                        _pipeline_path(base, step["model_dir"])
                        if step.get("model_dir")
                        else DEFAULT_MODEL_DIR
                    ),
                )
            elif step_type == "avatar_replace":
                face_temp = job_dir / f"{index:02d}-avatar-face.mp4"
                run_face_swap(
                    current,
                    _pipeline_path(base, step["source"]),
                    face_temp,
                    model_dir=(
                        _pipeline_path(base, step["model_dir"])
                        if step.get("model_dir")
                        else DEFAULT_MODEL_DIR
                    ),
                )
                current = face_temp
                if step.get("background"):
                    run_background_replace(
                        current,
                        _pipeline_path(base, step["background"]),
                        target,
                        engine=step.get("engine", "auto"),
                        chroma_color=step.get("chroma_color"),
                        similarity=float(step.get("similarity", 0.1)),
                        blend=float(step.get("blend", 0.05)),
                        rembg_model=step.get("rembg_model"),
                    )
                else:
                    target = current
            elif step_type == "background_replace":
                run_background_replace(
                    current,
                    _pipeline_path(base, step["background"]),
                    target,
                    engine=step.get("engine", "auto"),
                    chroma_color=step.get("chroma_color"),
                    similarity=float(step.get("similarity", 0.1)),
                    blend=float(step.get("blend", 0.05)),
                    rembg_model=step.get("rembg_model"),
                )
            elif step_type == "lip_sync":
                run_lip_sync(
                    current,
                    _pipeline_path(base, step["audio"]),
                    target,
                    wav2lip_dir=_pipeline_path(base, step["wav2lip_dir"]),
                    checkpoint=_pipeline_path(base, step["checkpoint"]),
                    python=(
                        _pipeline_path(base, step["python"])
                        if step.get("python")
                        else None
                    ),
                )
            else:
                raise ValueError(f"Unsupported pipeline step: {step_type}")
            current = target
            state["status"] = "completed"
            state["output"] = str(target)
            write_json(job_dir / "job.json", job_state)
        if current != output_path:
            import shutil

            shutil.copy2(current, output_path)
        job_state["status"] = "completed"
        job_state["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        write_json(job_dir / "job.json", job_state)
        return output_path
    except Exception as exc:
        job_state["status"] = "failed"
        job_state["error"] = str(exc)
        job_state["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        write_json(job_dir / "job.json", job_state)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Local modular AI video-editing pipeline."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Check dependencies, ffmpeg, and model files.").add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON."
    )
    probe = sub.add_parser("probe", help="Inspect media streams.")
    probe.add_argument("input")

    background = sub.add_parser("background", help="Replace a video background.")
    background.add_argument("--input", required=True)
    background.add_argument("--background", required=True)
    background.add_argument("--output", required=True)
    background.add_argument(
        "--engine", choices=("auto", "chroma", "matte", "rembg"), default="auto"
    )
    background.add_argument("--chroma-color")
    background.add_argument("--similarity", type=float, default=0.1)
    background.add_argument("--blend", type=float, default=0.05)
    background.add_argument("--rembg-model")

    face = sub.add_parser("face-swap", help="Swap the selected face.")
    face.add_argument("--input", required=True)
    face.add_argument("--source", required=True)
    face.add_argument("--output", required=True)
    face.add_argument("--model-dir")
    face.add_argument("--no-accelerator", action="store_true")
    face.add_argument("--confirm-authorized", action="store_true", required=True)

    avatar = sub.add_parser(
        "avatar-replace", help="Face swap with optional background replacement."
    )
    avatar.add_argument("--input", required=True)
    avatar.add_argument("--source", required=True)
    avatar.add_argument("--background")
    avatar.add_argument("--output", required=True)
    avatar.add_argument("--model-dir")
    avatar.add_argument("--engine", choices=("auto", "chroma", "matte", "rembg"), default="auto")
    avatar.add_argument("--chroma-color")
    avatar.add_argument("--confirm-authorized", action="store_true", required=True)

    lip = sub.add_parser("lip-sync", help="Run a configured Wav2Lip backend.")
    lip.add_argument("--input", required=True)
    lip.add_argument("--audio", required=True)
    lip.add_argument("--output", required=True)
    lip.add_argument("--wav2lip-dir", required=True)
    lip.add_argument("--checkpoint", required=True)
    lip.add_argument("--python")
    lip.add_argument("--resize-factor", type=int, default=1)
    lip.add_argument("--confirm-authorized", action="store_true", required=True)

    pipeline = sub.add_parser("run-pipeline", help="Run a JSON multi-step pipeline.")
    pipeline.add_argument("--config", required=True)
    status = sub.add_parser("status", help="Read a saved job status.")
    status.add_argument("job")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "doctor":
            data = doctor()
            _print_json(data)
            return 0
        if args.command == "probe":
            _print_json(probe_media(args.input))
            return 0
        if args.command == "background":
            from background_replace import run_background_replace

            result = run_background_replace(
                args.input,
                args.background,
                args.output,
                engine=args.engine,
                chroma_color=args.chroma_color,
                similarity=args.similarity,
                blend=args.blend,
                rembg_model=args.rembg_model,
            )
            print(result)
            return 0
        if args.command == "face-swap":
            from face_swap import DEFAULT_MODEL_DIR, run_face_swap

            result = run_face_swap(
                args.input,
                args.source,
                args.output,
                model_dir=args.model_dir or DEFAULT_MODEL_DIR,
                accelerator=not args.no_accelerator,
            )
            print(result)
            return 0
        if args.command == "avatar-replace":
            from face_swap import DEFAULT_MODEL_DIR, run_face_swap

            face_temp = resolve_output(
                Path("runtime") / "avatar-temp" / f"{uuid.uuid4().hex}.mp4"
            )
            face_output = face_temp.with_name(f"{face_temp.stem}-face.mp4")
            run_face_swap(
                args.input,
                args.source,
                face_output,
                model_dir=args.model_dir or DEFAULT_MODEL_DIR,
            )
            if args.background:
                from background_replace import run_background_replace

                result = run_background_replace(
                    face_output,
                    args.background,
                    args.output,
                    engine=args.engine,
                    chroma_color=args.chroma_color,
                )
                face_output.unlink(missing_ok=True)
            else:
                result = resolve_output(args.output)
                import shutil

                shutil.move(str(face_output), str(result))
            print(result)
            return 0
        if args.command == "lip-sync":
            from lip_sync import run_lip_sync

            result = run_lip_sync(
                args.input,
                args.audio,
                args.output,
                wav2lip_dir=args.wav2lip_dir,
                checkpoint=args.checkpoint,
                python=args.python,
                resize_factor=args.resize_factor,
            )
            print(result)
            return 0
        if args.command == "run-pipeline":
            print(run_pipeline(args.config))
            return 0
        if args.command == "status":
            job = Path(args.job)
            if job.is_dir():
                job = job / "job.json"
            _print_json(json.loads(resolve_input(job).read_text(encoding="utf-8-sig")))
            return 0
        raise ValueError(f"Unknown command: {args.command}")
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (MediaError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
