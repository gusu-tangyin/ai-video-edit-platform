# AI 视频剪辑平台

[![Windows CI](https://github.com/gusu-tangyin/ai-video-edit-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/gusu-tangyin/ai-video-edit-platform/actions/workflows/ci.yml)

`proj_004_skill_AI视频剪辑平台` 是一个本地、模块化的 Codex 视频技能工程。它把
视频探测、背景替换、换脸、头像替换、Wav2Lip 对口型和多步骤流水线统一到一个 CLI，
并把中间结果与运行状态保存在固定工作区内。

仓库包含完整源码、技能说明、配置和安装脚本；不包含模型权重、用户素材或 API Key。

## 能力

| 功能 | 当前实现 |
| --- | --- |
| 视频探测 | FFprobe 读取时长、分辨率、帧率、像素格式、音频流 |
| 背景替换 | FFmpeg 绿幕抠像、已有 Alpha 通道、可选 rembg |
| 换脸 | 本地 SCRFD + ArcFace + inswapper ONNX |
| 头像替换 | 换脸，可选继续替换背景 |
| 对口型 | 显式配置的 Wav2Lip checkout 和 checkpoint |
| 多步骤流水线 | JSON 步骤编排，逐步写入状态并允许失败后检查 |

身份修改功能必须由用户提供其拥有或获授权的素材；换脸和对口型命令要求
`--confirm-authorized`。本项目不会自动下载模型。

## 安装

安装运行时：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

需要可选 rembg 时：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -WithRembg
```

注册到 Codex 技能目录：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register.ps1
```

默认注册名为 `ai-video-edit-platform`。可用 `-SkillsRoot` 指定其他技能目录。

## 使用

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\aivideo.ps1 doctor --json
powershell -ExecutionPolicy Bypass -File .\scripts\aivideo.ps1 probe .\input.mp4
```

背景替换：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\aivideo.ps1 background `
  --input F:\workspace\inputs\subject.mp4 `
  --background F:\workspace\inputs\background.png `
  --output F:\workspace\outputs\composed.mp4 `
  --engine chroma --chroma-color 0x00FF00
```

多步骤配置见 [references/configuration.md](references/configuration.md)，后端说明见
[references/backends.md](references/backends.md)。

## 验证

只依赖 FFmpeg 的端到端冒烟测试：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\aivideo.ps1 doctor --json
F:\workspace\runtime\python\base\python.exe .\scripts\smoke_test.py
```

冒烟测试会在 `F:\workspace\runtime\smoke` 下生成合成绿幕素材，执行一次背景替换，
用 FFprobe 核验输出，并在成功后清理测试目录。

换脸模型和 Wav2Lip 属于可选重后端。未安装模型或依赖时，`doctor` 会报告
`ready: false`，不会把源码存在误报成可推理状态。

多步骤流水线和 Windows 中文路径回归测试：

```powershell
.\runtime\.venv\Scripts\python.exe .\scripts\smoke_pipeline.py
.\runtime\.venv\Scripts\python.exe .\scripts\smoke_unicode.py
```

## 许可证

本项目原创源码和文档使用 [MIT License](LICENSE)。

模型权重、外部 Wav2Lip 代码与权重、FFmpeg、Python 依赖以及用户素材
不属于本项目的 MIT 授权范围。使用或分发第三方模型前，必须单独核对其
上游许可证。详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
