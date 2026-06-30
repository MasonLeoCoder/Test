# Agent Guide

## 项目概述

这是一个使用 Python + Pillow 开发的电商图片批处理工具。工具会读取指定文件夹中的图片，并为每张图片生成三个目标体积版本：

- `100kb`
- `300kb`
- `500kb`

输出目录会自动创建为：

```text
output/
  100kb/
  300kb/
  500kb/
```

当前入口文件是 `main.py`，依赖文件是 `requirements.txt`。

## 运行环境

- Python: 3.11
- 依赖库: Pillow
- 推荐使用项目内虚拟环境 `.venv`

安装依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

运行工具：

```powershell
.\.venv\Scripts\python.exe .\main.py 图片文件夹路径
```

指定输出目录：

```powershell
.\.venv\Scripts\python.exe .\main.py 图片文件夹路径 -o 输出文件夹路径
```

示例：

```powershell
.\.venv\Scripts\python.exe .\main.py D:\images\shop -o D:\images\processed
```

## 功能要求

工具需要满足以下行为：

- 支持批量读取输入文件夹中的 `.jpg`、`.jpeg`、`.png` 图片。
- 每张图片输出三个 JPEG 版本。
- 目标文件大小分别接近 100KB、300KB、500KB。
- 默认允许误差是 ±10KB。
- 优先通过 JPEG quality 控制文件大小，quality 范围是 1 到 95。
- 如果仅调整 quality 无法达到目标大小，可以在原始分辨率的 ±10% 范围内轻微缩放。
- 缩放必须保持宽高比，不能让电商主图变形。
- PNG 透明背景转 JPEG 时使用白色背景。
- 单张图片处理失败时，不应中断整批任务。
- 控制台需要输出处理前后的文件大小对比。

## 当前实现说明

`main.py` 的主要模块如下：

- `parse_args()`：解析命令行参数。
- `iter_images()`：遍历输入目录中的图片。
- `ensure_output_dirs()`：创建输出目录。
- `normalize_image()`：修正 EXIF 方向，并转换为 RGB。
- `resize_by_scale()`：等比例缩放图片。
- `encode_jpeg()`：按指定 quality 输出 JPEG 数据。
- `quality_search()`：用二分搜索寻找接近目标大小的 quality。
- `build_scale_candidates()`：生成 0.90 到 1.10 之间的缩放候选值。
- `compress_to_target()`：组合 quality 搜索和轻微缩放，逼近目标体积。
- `pad_jpeg_to_target()`：当图片过小且无法通过最高质量和 10% 放大达到目标体积时，追加 JPEG 尾部填充字节补足大小。
- `process_image()`：处理单张图片并写出三个版本。
- `main()`：程序入口。

## 重要实现约束

后续维护或修改时，请遵守这些约束：

- 不要改变图片宽高比。
- 不要超过 `MIN_SCALE = 0.90` 和 `MAX_SCALE = 1.10` 的缩放范围。
- 不要把 JPEG quality 提高到 95 以上。
- 输出文件统一使用 `.jpg` 后缀。
- 不要把生成的 `output/`、`test_run/`、`test_images/`、`__pycache__/` 提交到 Git。
- 如果修改压缩逻辑，必须重新验证 100KB、300KB、500KB 三档输出是否接近目标。

## 验证方式

语法检查：

```powershell
python -m py_compile .\main.py
```

使用测试图片运行：

```powershell
.\.venv\Scripts\python.exe .\main.py .\test_images
```

检查输出图片是否可被 Pillow 正常打开：

```powershell
.\.venv\Scripts\python.exe -c "from PIL import Image; from pathlib import Path; [print(p, Image.open(p).size, round(p.stat().st_size/1024, 1)) for p in sorted(Path('output').rglob('*.jpg'))]"
```

## 已知注意点

- 对于原始图片非常小的情况，300KB 或 500KB 目标可能无法仅靠 quality 和 10% 放大达到。当前实现会在 JPEG 文件尾部追加填充字节，让文件体积达到目标大小，同时不改变实际像素内容。
- Pillow 输出的是 JPEG，因此 PNG 的透明区域会被合成为白色背景。
- 如果 PowerShell 显示中文注释乱码，优先检查终端编码；Python 文件本身仍可正常运行。

