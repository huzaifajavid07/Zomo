"""
Facial Expression Dataset to Y4M Video Converter
=================================================
Converts facial expression video clips (MP4, AVI, WEBM, MOV, MKV) or image frame sequences
from a facial expression dataset into lightweight, looping Y4M (YUV4MPEG2) webcam feeds.

Features:
  - Random 2-3 second realistic snippet extraction from source videos.
  - Seamless ping-pong / palindrome mirroring to prevent visual skipping on loop.
  - Dual conversion backend:
      1. Native FFmpeg (fast, high performance)
      2. Pure Python / OpenCV / Pillow fallback
  - Batch pool generation for multi-bot deployments (populates video_pool/).

Usage:
  python dataset_to_video.py --dataset-dir ./facial_dataset --output-dir ./video_pool --count 5
  python dataset_to_video.py --input-file clip.mp4 --output-file ./video_pool/face1.y4m --snippet-min 2.0 --snippet-max 3.0
"""

import argparse
import math
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple


VALID_VIDEO_EXTS = {".mp4", ".avi", ".mov", ".webm", ".mkv", ".m4v"}
VALID_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def is_ffmpeg_available() -> bool:
    """Check if ffmpeg executable is available in PATH."""
    return shutil.which("ffmpeg") is not None


def is_ffprobe_available() -> bool:
    """Check if ffprobe executable is available in PATH."""
    return shutil.which("ffprobe") is not None


def get_video_duration_ffmpeg(file_path: str) -> Optional[float]:
    """Get video duration in seconds using ffprobe."""
    if not is_ffprobe_available():
        return None
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except Exception:
        return None


def convert_rgb_to_yuv420(rgb_bytes: bytes, width: int, height: int) -> bytes:
    """Convert RGB24 bytes to YUV420 planar bytes (BT.601 standard)."""
    y_plane = bytearray(width * height)
    u_plane = bytearray((width // 2) * (height // 2))
    v_plane = bytearray((width // 2) * (height // 2))

    for r in range(height):
        for c in range(width):
            idx = (r * width + c) * 3
            R = rgb_bytes[idx]
            G = rgb_bytes[idx + 1]
            B = rgb_bytes[idx + 2]

            Y = int(0.299 * R + 0.587 * G + 0.114 * B)
            y_plane[r * width + c] = max(16, min(235, Y))

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


def extract_snippet_ffmpeg(
    input_file: str,
    output_y4m: str,
    start_sec: float,
    duration_sec: float,
    width: int = 640,
    height: int = 480,
    fps: int = 15,
    ping_pong: bool = True
) -> bool:
    """Extract a snippet using FFmpeg and convert directly to Y4M."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_y4m)), exist_ok=True)

        if ping_pong:
            # Ping-pong filter: play forward then reverse for seamless looping
            # [0:v]trim,setpts,split[f][r];[r]reverse[r_rev];[f][r_rev]concat=n=2:v=1[out]
            vf = (
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},"
                f"fps={fps},"
                f"split=2[fwd][rev];"
                f"[rev]reverse[rev2];"
                f"[fwd][rev2]concat=n=2:v=1[v]"
            )
            cmd = [
                "ffmpeg", "-y",
                "-ss", f"{start_sec:.2f}",
                "-t", f"{duration_sec:.2f}",
                "-i", input_file,
                "-filter_complex", vf,
                "-map", "[v]",
                "-pix_fmt", "yuv420p",
                output_y4m
            ]
        else:
            vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps}"
            cmd = [
                "ffmpeg", "-y",
                "-ss", f"{start_sec:.2f}",
                "-t", f"{duration_sec:.2f}",
                "-i", input_file,
                "-vf", vf,
                "-pix_fmt", "yuv420p",
                output_y4m
            ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0 and os.path.exists(output_y4m) and os.path.getsize(output_y4m) > 0:
            return True
        else:
            print(f"[FFmpeg Warning] Command failed: {res.stderr[:200]}")
            return False
    except Exception as e:
        print(f"[FFmpeg Error] {e}")
        return False


def extract_snippet_python(
    input_file: str,
    output_y4m: str,
    start_sec: float,
    duration_sec: float,
    width: int = 640,
    height: int = 480,
    fps: int = 15,
    ping_pong: bool = True
) -> bool:
    """Extract a snippet using OpenCV/PIL fallback and encode to Y4M."""
    try:
        import cv2
        from PIL import Image
    except ImportError:
        print("[ERR] OpenCV (`cv2`) and Pillow (`PIL`) are required for Python video extraction. pip install opencv-python Pillow")
        return False

    cap = cv2.VideoCapture(input_file)
    if not cap.isOpened():
        print(f"[ERR] Could not open video file: {input_file}")
        return False

    src_fps = cap.get(cv2.CAP_PROP_FPS) or fps
    total_src_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    start_frame = int(start_sec * src_fps)
    num_frames = int(duration_sec * src_fps)

    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, start_frame))

    raw_frames = []
    read_count = 0

    # Step size if src_fps differs from target fps
    step = src_fps / fps if src_fps > 0 else 1.0
    accum = 0.0

    while read_count < num_frames:
        ret, frame_bgr = cap.read()
        if not ret:
            break
        accum += 1.0
        if accum >= step:
            accum -= step
            # Convert BGR -> RGB
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)

            # Center-crop & Resize to target dimensions
            img_ratio = img.width / img.height
            target_ratio = width / height
            if img_ratio > target_ratio:
                new_w = int(img.height * target_ratio)
                left = (img.width - new_w) // 2
                img = img.crop((left, 0, left + new_w, img.height))
            else:
                new_h = int(img.width / target_ratio)
                top = (img.height - new_h) // 2
                img = img.crop((0, top, img.width, top + new_h))

            img = img.resize((width, height), Image.Resampling.LANCZOS)
            raw_frames.append(img.tobytes())
        read_count += 1

    cap.release()

    if not raw_frames:
        print(f"[ERR] No frames extracted from {input_file}")
        return False

    # Apply ping-pong if requested
    if ping_pong and len(raw_frames) > 2:
        output_frames = raw_frames + raw_frames[-2:0:-1]
    else:
        output_frames = raw_frames

    os.makedirs(os.path.dirname(os.path.abspath(output_y4m)), exist_ok=True)

    with open(output_y4m, "wb") as f:
        header = f"YUV4MPEG2 W{width} H{height} F{fps}:1 Ip A1:1 C420\n"
        f.write(header.encode("ascii"))

        for rgb_bytes in output_frames:
            yuv_data = convert_rgb_to_yuv420(rgb_bytes, width, height)
            f.write(b"FRAME\n")
            f.write(yuv_data)

    return True


def convert_dataset_clip_to_y4m(
    input_file: str,
    output_y4m: str,
    snippet_min: float = 2.0,
    snippet_max: float = 3.0,
    width: int = 640,
    height: int = 480,
    fps: int = 15,
    ping_pong: bool = True
) -> bool:
    """Extract a realistic random 2-3s snippet from a dataset video file and convert to Y4M."""
    snippet_duration = random.uniform(snippet_min, snippet_max)
    total_duration = get_video_duration_ffmpeg(input_file)

    if total_duration is None:
        # Fallback to OpenCV duration estimate
        try:
            import cv2
            cap = cv2.VideoCapture(input_file)
            f_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            f_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            total_duration = f_count / f_fps if f_fps > 0 else 5.0
            cap.release()
        except Exception:
            total_duration = 5.0

    # Pick random start offset, ensuring snippet fits inside video
    max_start = max(0.0, total_duration - snippet_duration)
    # Give a small 0.2s margin at beginning if possible to skip intro static
    min_start = min(0.2, max_start * 0.1)
    start_sec = random.uniform(min_start, max_start) if max_start > min_start else 0.0

    print(f"  Snippet: {Path(input_file).name} (offset {start_sec:.1f}s, len {snippet_duration:.1f}s) → {Path(output_y4m).name}")

    # Try FFmpeg first
    if is_ffmpeg_available():
        success = extract_snippet_ffmpeg(
            input_file, output_y4m, start_sec, snippet_duration, width, height, fps, ping_pong
        )
        if success:
            return True

    # Fallback to OpenCV/PIL
    return extract_snippet_python(
        input_file, output_y4m, start_sec, snippet_duration, width, height, fps, ping_pong
    )


def process_dataset_directory(
    dataset_dir: str,
    output_dir: str,
    count: int = 5,
    snippet_min: float = 2.0,
    snippet_max: float = 3.0,
    width: int = 640,
    height: int = 480,
    fps: int = 15,
    ping_pong: bool = True
) -> List[str]:
    """Scan dataset directory, select videos, extract random 2-3s snippets, and populate output video pool."""
    dataset_path = Path(dataset_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if not dataset_path.exists():
        print(f"[WARN] Dataset directory not found: {dataset_dir}")
        return []

    # Find all video files recursively
    video_files = [
        f for f in dataset_path.rglob("*")
        if f.is_file() and f.suffix.lower() in VALID_VIDEO_EXTS
    ]

    if not video_files:
        print(f"[WARN] No video files ({', '.join(VALID_VIDEO_EXTS)}) found in {dataset_dir}")
        return []

    print(f"\n📂 Found {len(video_files)} facial expression video(s) in {dataset_dir}")
    print(f"🎬 Generating {count} random 2-3s snippet feeds in {output_dir}...")

    # Shuffle for randomness
    random.shuffle(video_files)

    generated = []
    for i in range(count):
        src_video = video_files[i % len(video_files)]
        out_name = f"bot_face_{i:02d}.y4m"
        out_file = output_path / out_name

        ok = convert_dataset_clip_to_y4m(
            str(src_video),
            str(out_file),
            snippet_min=snippet_min,
            snippet_max=snippet_max,
            width=width,
            height=height,
            fps=fps,
            ping_pong=ping_pong
        )
        if ok:
            size_mb = out_file.stat().st_size / (1024 * 1024)
            print(f"    ✓ Ready: {out_name} ({size_mb:.2f} MB)")
            generated.append(str(out_file.resolve()))
        else:
            print(f"    ✗ Failed: {out_name}")

    print(f"✅ Video pool populated with {len(generated)} facial expression snippet feed(s).\n")
    return generated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process facial expression dataset into Y4M webcam feeds")
    parser.add_argument("--dataset-dir", type=str, default="./facial_dataset", help="Directory containing facial expression videos")
    parser.add_argument("--input-file", type=str, default=None, help="Single input video file to convert")
    parser.add_argument("--output-dir", type=str, default="./video_pool", help="Output directory for generated Y4M files")
    parser.add_argument("--output-file", type=str, default=None, help="Single output Y4M file path")
    parser.add_argument("--count", type=int, default=5, help="Number of bot video feeds to generate")
    parser.add_argument("--snippet-min", type=float, default=2.0, help="Min snippet duration in seconds")
    parser.add_argument("--snippet-max", type=float, default=3.0, help="Max snippet duration in seconds")
    parser.add_argument("--width", type=int, default=640, help="Video width in pixels")
    parser.add_argument("--height", type=int, default=480, help="Video height in pixels")
    parser.add_argument("--fps", type=int, default=15, help="Video framerate")
    parser.add_argument("--no-ping-pong", action="store_true", help="Disable forward-reverse ping-pong loop smoothing")

    args = parser.parse_args()

    if args.input_file:
        out = args.output_file or str(Path(args.output_dir) / f"{Path(args.input_file).stem}.y4m")
        convert_dataset_clip_to_y4m(
            args.input_file,
            out,
            snippet_min=args.snippet_min,
            snippet_max=args.snippet_max,
            width=args.width,
            height=args.height,
            fps=args.fps,
            ping_pong=not args.no_ping_pong
        )
    else:
        process_dataset_directory(
            args.dataset_dir,
            args.output_dir,
            count=args.count,
            snippet_min=args.snippet_min,
            snippet_max=args.snippet_max,
            width=args.width,
            height=args.height,
            fps=args.fps,
            ping_pong=not args.no_ping_pong
        )
