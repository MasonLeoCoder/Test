import argparse
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageOps


# 支持处理的图片扩展名，统一用小写判断。
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png"}

# 目标输出规格：文件夹名称、目标 KB、允许误差 KB。
TARGET_SPECS = (
    ("100kb", 100, 10),
    ("300kb", 300, 10),
    ("500kb", 500, 10),
)

# JPEG quality 的允许范围，按需求限制在 1~95。
MIN_QUALITY = 1
MAX_QUALITY = 95

# 允许轻微缩放分辨率，最大不超过原图的 +/-10%。
MIN_SCALE = 0.90
MAX_SCALE = 1.10
SCALE_STEP = 0.02


@dataclass(frozen=True)
class EncodeResult:
    """保存一次压缩结果，方便后续比较和写入文件。"""

    data: bytes
    quality: int
    scale: float
    size_bytes: int
    padded: bool = False


def parse_args() -> argparse.Namespace:
    """解析命令行参数，支持指定输入目录和输出目录。"""
    parser = argparse.ArgumentParser(description="电商图片批处理工具")
    parser.add_argument("input_dir", help="输入图片文件夹，支持 jpg/jpeg/png")
    parser.add_argument(
        "-o",
        "--output-dir",
        default="output",
        help="输出文件夹，默认是当前目录下的 output",
    )
    return parser.parse_args()


def iter_images(input_dir: Path) -> Iterable[Path]:
    """遍历输入目录下所有支持格式的图片文件。"""
    for path in sorted(input_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path


def ensure_output_dirs(output_dir: Path) -> None:
    """自动创建 output/100kb、output/300kb、output/500kb 目录。"""
    for folder_name, _, _ in TARGET_SPECS:
        (output_dir / folder_name).mkdir(parents=True, exist_ok=True)


def normalize_image(image: Image.Image) -> Image.Image:
    """修正 EXIF 方向，并转换为适合 JPEG 输出的 RGB 图片。"""
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA"):
        # PNG 透明图转 JPEG 时需要白底，避免透明区域变黑。
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.getchannel("A"))
        return background
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def resize_by_scale(image: Image.Image, scale: float) -> Image.Image:
    """按比例缩放图片，保持宽高比，避免电商主图变形。"""
    if abs(scale - 1.0) < 0.0001:
        return image
    width, height = image.size
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def encode_jpeg(image: Image.Image, quality: int) -> bytes:
    """把图片按指定 JPEG quality 编码到内存，返回二进制数据。"""
    buffer = io.BytesIO()
    image.save(
        buffer,
        format="JPEG",
        quality=quality,
        optimize=True,
        progressive=True,
        subsampling=0,
    )
    return buffer.getvalue()


def pad_jpeg_to_target(data: bytes, target_bytes: int) -> bytes:
    """当图片过小无法靠质量和分辨率达标时，追加尾部填充字节补足大小。"""
    if len(data) >= target_bytes:
        return data
    # JPEG 解码器会在 EOI 结束标记后停止读取，尾部填充不改变图片像素内容。
    return data + (b"\0" * (target_bytes - len(data)))


def quality_search(
    image: Image.Image,
    target_bytes: int,
    tolerance_bytes: int,
    scale: float,
) -> EncodeResult:
    """在固定分辨率下用二分搜索寻找最接近目标大小的 JPEG quality。"""
    scaled_image = resize_by_scale(image, scale)
    low = MIN_QUALITY
    high = MAX_QUALITY
    best: EncodeResult | None = None

    while low <= high:
        quality = (low + high) // 2
        data = encode_jpeg(scaled_image, quality)
        size_bytes = len(data)
        result = EncodeResult(data, quality, scale, size_bytes)

        if best is None or abs(size_bytes - target_bytes) < abs(best.size_bytes - target_bytes):
            best = result

        if abs(size_bytes - target_bytes) <= tolerance_bytes:
            return result

        if size_bytes < target_bytes:
            low = quality + 1
        else:
            high = quality - 1

    if best is None:
        raise RuntimeError("图片编码失败，未生成任何压缩结果")
    return best


def build_scale_candidates() -> list[float]:
    """生成优先接近原始分辨率的缩放比例列表，限制在 +/-10% 范围内。"""
    candidates = [1.0]
    step_count = round((MAX_SCALE - 1.0) / SCALE_STEP)
    for index in range(1, step_count + 1):
        candidates.append(1.0 - index * SCALE_STEP)
        candidates.append(1.0 + index * SCALE_STEP)
    return [round(scale, 2) for scale in candidates if MIN_SCALE <= scale <= MAX_SCALE]


def compress_to_target(
    image: Image.Image,
    target_kb: int,
    tolerance_kb: int,
) -> EncodeResult:
    """先调 JPEG quality，必要时在 +/-10% 内轻微缩放分辨率逼近目标大小。"""
    target_bytes = target_kb * 1024
    tolerance_bytes = tolerance_kb * 1024
    best: EncodeResult | None = None

    for scale in build_scale_candidates():
        result = quality_search(image, target_bytes, tolerance_bytes, scale)
        if best is None or abs(result.size_bytes - target_bytes) < abs(best.size_bytes - target_bytes):
            best = result
        if abs(result.size_bytes - target_bytes) <= tolerance_bytes:
            return result

    if best is None:
        raise RuntimeError("压缩失败，未找到可用结果")

    if best.size_bytes < target_bytes - tolerance_bytes:
        padded_data = pad_jpeg_to_target(best.data, target_bytes)
        return EncodeResult(
            padded_data,
            best.quality,
            best.scale,
            len(padded_data),
            padded=True,
        )

    return best


def output_name(source_path: Path) -> str:
    """统一输出为 JPEG 文件名，避免 PNG 转 JPEG 后扩展名不匹配。"""
    return f"{source_path.stem}.jpg"


def process_image(image_path: Path, output_dir: Path) -> None:
    """处理单张图片，并输出 100KB、300KB、500KB 三个版本。"""
    original_size = image_path.stat().st_size
    with Image.open(image_path) as opened_image:
        image = normalize_image(opened_image)

        for folder_name, target_kb, tolerance_kb in TARGET_SPECS:
            result = compress_to_target(image, target_kb, tolerance_kb)
            destination = output_dir / folder_name / output_name(image_path)
            destination.write_bytes(result.data)

            print(
                f"{image_path.name} -> {folder_name}/{destination.name} | "
                f"原始: {original_size / 1024:.1f}KB | "
                f"输出: {result.size_bytes / 1024:.1f}KB | "
                f"quality: {result.quality} | "
                f"scale: {result.scale:.2f}"
                f"{' | 已填充体积' if result.padded else ''}"
            )


def main() -> None:
    """程序入口：检查目录、创建输出目录、批量处理图片。"""
    args = parse_args()
    input_dir = Path(args.input_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"输入目录不存在或不是文件夹: {input_dir}")

    ensure_output_dirs(output_dir)
    image_paths = list(iter_images(input_dir))

    if not image_paths:
        print(f"没有找到可处理图片: {input_dir}")
        return

    print(f"输入目录: {input_dir}")
    print(f"输出目录: {output_dir}")
    print(f"待处理图片数量: {len(image_paths)}")

    for image_path in image_paths:
        try:
            process_image(image_path, output_dir)
        except Exception as exc:
            # 单张失败不影响整批图片，方便后续人工排查。
            print(f"{image_path.name} 处理失败: {exc}")


if __name__ == "__main__":
    main()
