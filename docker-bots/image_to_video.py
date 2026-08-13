"""
Image to Y4M Video Converter — Animated Avatar Video Generator
================================================================
Takes static portrait photos (PNG/JPG) and converts them into lightweight,
looping Y4M video files with subtle natural human motion effects:
  - Subtle breathing (micro-zoom)
  - Natural camera sway/pan
  - Ambient room light pulse

Usage:
  python image_to_video.py --image input_face.jpg --output video_pool/face1.y4m
"""

import argparse
import math
import os
from pathlib import Path
from typing import Optional


def convert_rgb_to_yuv420(rgb_bytes: bytes, width: int, height: int) -> bytes:
    """Convert RGB24 bytes to YUV420 planar bytes."""
    y_plane = bytearray(width * height)
    u_plane = bytearray((width // 2) * (height // 2))
    v_plane = bytearray((width // 2) * (height // 2))

    for r in range(height):
        for c in range(width):
            idx = (r * width + c) * 3
            R = rgb_bytes[idx]
            G = rgb_bytes[idx + 1]
            B = rgb_bytes[idx + 2]

            # BT.601 YUV conversion formula
            Y = int(0.299 * R + 0.587 * G + 0.114 * B)
            y_plane[r * width + c] = max(16, min(235, Y))

    # UV downsampled 2x2
    for r in range(height // 2):
        for c in range(width // 2):
            sr, sc = r * 2, c * 2
            idx = (sr * width + sc) * 3
            R = rgb_bytes[idx]
            G = rgb_bytes[idx + 1]
            B = rgb_bytes[idx + 2]

            U = int(-0.168736 * R - 0.331264 * G + 0.5 * B + 128)
            V = int(0.5 * R - 0.418688 * G - 0.081312 * B + 128)

            uv_idx = r * (width // 2) + c
            u_plane[uv_idx] = max(16, min(240, U))
            v_plane[uv_idx] = max(16, min(240, V))

    return bytes(y_plane) + bytes(u_plane) + bytes(v_plane)


def create_animated_y4m_from_image(
    image_path: str,
    output_path: str,
    width: int = 640,
    height: int = 480,
    fps: int = 15,
    duration_sec: int = 15
) -> bool:
    """Convert a single static image into an animated Y4M video with natural movement."""
    try:
        from PIL import Image, ImageEnhance
    except ImportError:
        print("[ERR] PIL (Pillow) is required for image to Y4M conversion. Install via: pip install Pillow")
        return False

    if not os.path.exists(image_path):
        print(f"[ERR] Image not found: {image_path}")
        return False

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Load base image
    base_img = Image.open(image_path).convert("RGB")

    total_frames = fps * duration_sec
    print(f"Creating animated Y4M: {image_path} → {output_path} ({width}x{height} @ {fps}fps, {total_frames} frames)")

    with open(output_path, "wb") as f:
        # Y4M Header
        header = f"YUV4MPEG2 W{width} H{height} F{fps}:1 Ip A1:1 C420\n"
        f.write(header.encode("ascii"))

        for i in range(total_frames):
            progress = i / total_frames
            # 1. Subtle breathing micro-zoom (1.00 to 1.025x scale)
            zoom = 1.0 + 0.025 * (0.5 + 0.5 * math.sin(progress * 2 * math.pi))
            
            # 2. Camera sway offset (+/- 3px)
            offset_x = int(3 * math.sin(progress * 4 * math.pi))
            offset_y = int(2 * math.cos(progress * 2 * math.pi))

            # 3. Ambient lighting fluctuation (+/- 2% brightness)
            bright_factor = 1.0 + 0.02 * math.sin(progress * 6 * math.pi)

            # Crop & Resize
            crop_w = int(width / zoom)
            crop_h = int(height / zoom)

            # Center crop with sway
            cx = (base_img.width // 2) + offset_x
            cy = (base_img.height // 2) + offset_y

            left = max(0, cx - crop_w // 2)
            top = max(0, cy - crop_h // 2)
            right = min(base_img.width, left + crop_w)
            bottom = min(base_img.height, top + crop_h)

            frame_img = base_img.crop((left, top, right, bottom))
            frame_img = frame_img.resize((width, height), Image.Resampling.LANCZOS)

            if abs(bright_factor - 1.0) > 0.005:
                enhancer = ImageEnhance.Brightness(frame_img)
                frame_img = enhancer.enhance(bright_factor)

            rgb_data = frame_img.tobytes()
            yuv_data = convert_rgb_to_yuv420(rgb_data, width, height)

            f.write(b"FRAME\n")
            f.write(yuv_data)

    file_size = os.path.getsize(output_path)
    print(f"✓ Created {output_path} ({file_size / (1024 * 1024):.1f} MB)")
    return True


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Convert portrait photos to animated Y4M video feeds")
    p.add_argument("--image", required=True, help="Input image file (JPG/PNG)")
    p.add_argument("--output", required=True, help="Output Y4M video file path")
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--fps", type=int, default=15)
    p.add_argument("--duration", type=int, default=15)
    args = p.parse_args()

    create_animated_y4m_from_image(
        args.image, args.output, args.width, args.height, args.fps, args.duration
    )
